import asyncio
from datetime import datetime, timezone
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from app.core import config
from app.core.db import initialize, connect
from app.modules import telemetry, event_bus, agent
from app.main import app

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "MODEL_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "API_TOKEN", "test-token-that-is-long-enough")
    monkeypatch.setattr(config, "CLOUD_URL", "")
    monkeypatch.setattr(config, "NODE_ROLE", "edge")
    initialize()

def reading():
    return telemetry.Reading(id=uuid4(), astronaut_id="crew-01", observed_at=datetime.now(timezone.utc),
        heart_rate=72, temperature=36.7, sleep_hours=7.5, mood=4)

def test_dedup_and_conflict():
    r = reading()
    assert not telemetry.record(r)["duplicate"]
    assert telemetry.record(r)["duplicate"]
    with pytest.raises(telemetry.ConflictError):
        telemetry.record(r.model_copy(update={"heart_rate": 75}))
    with connect() as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1

def test_transaction_rolls_back_reading_if_event_fails():
    with connect() as db:
        db.execute("CREATE TRIGGER fail_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(Exception):
        telemetry.record(reading())
    assert telemetry.recent() == []

def test_worker_restart_and_idempotent_handler():
    telemetry.record(reading())
    initialize()  # Reopening storage after a process restart preserves the work.
    assert event_bus.process_batch() == 1
    assert event_bus.process_batch() == 0
    with connect() as db:
        assert db.execute("SELECT count(*) FROM assessments").fetchone()[0] == 1

def test_api_auth_and_validation():
    with TestClient(app) as client:
        assert client.get('/api/readings').status_code == 401
        headers={"Authorization":"Bearer " + config.API_TOKEN}
        body=reading().model_dump(mode='json')
        assert client.post('/api/readings',json=body,headers=headers).status_code==200
        body['temperature']=99
        assert client.post('/api/readings',json=body,headers=headers).status_code==422
        assert client.post('/api/events',json={'schema_version':1,'type':'health.reading.recorded.v1',
          'reading':reading().model_dump(mode='json')},headers=headers).status_code==403

def test_cloud_ack_loss_and_retry(monkeypatch):
    r=reading();telemetry.record(r)
    monkeypatch.setattr(config,'CLOUD_URL','https://ground.example/api/events')
    real_client=httpx.AsyncClient
    seen=[]
    def handler(request):
        seen.append(request.read())
        if len(seen)==1:
            raise httpx.ReadError('lost ACK',request=request)
        return httpx.Response(200,json={'id':str(r.id),'duplicate':True})
    monkeypatch.setattr(event_bus.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    asyncio.run(event_bus.sync_batch())
    with connect() as db:
        row=db.execute('SELECT * FROM events').fetchone()
        assert row['synced']==0 and row['attempts']==1
        db.execute('UPDATE events SET retry_at=0')
    asyncio.run(event_bus.sync_batch())
    with connect() as db:
        assert db.execute('SELECT synced FROM events').fetchone()[0]==1
    assert seen[0]==seen[1]

def test_bad_schema_goes_to_dead_letter(monkeypatch):
    telemetry.record(reading())
    monkeypatch.setattr(config,'CLOUD_URL','https://ground.example/api/events')
    real_client=httpx.AsyncClient
    monkeypatch.setattr(event_bus.httpx,'AsyncClient',lambda **kw:real_client(
      transport=httpx.MockTransport(lambda request:httpx.Response(422)),**kw))
    asyncio.run(event_bus.sync_batch())
    with connect() as db:
        assert db.execute('SELECT dead_letter FROM events').fetchone()[0]==1

def test_agent_falls_back_when_ollama_unavailable(monkeypatch):
    real_client=httpx.AsyncClient
    def fail(request): raise httpx.ConnectError('offline',request=request)
    monkeypatch.setattr(agent.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(fail),**kw))
    assert asyncio.run(agent.answer('How to log sleep?'))['mode']=='fallback'

def test_cloud_ingests_duplicate_without_sync_loop(monkeypatch):
    monkeypatch.setattr(config,'NODE_ROLE','cloud')
    r=reading()
    event={'schema_version':1,'type':'health.reading.recorded.v1','reading':r.model_dump(mode='json')}
    headers={'Authorization':'Bearer '+config.API_TOKEN}
    with TestClient(app) as client:
        assert client.post('/api/events',json=event,headers=headers).json()['duplicate'] is False
        assert client.post('/api/events',json=event,headers=headers).json()['duplicate'] is True
        event['schema_version']=2
        assert client.post('/api/events',json=event,headers=headers).status_code==422
    with connect() as db:
        assert db.execute('SELECT synced FROM events').fetchone()[0]==1

def test_concurrent_duplicate_ingest():
    from concurrent.futures import ThreadPoolExecutor
    r=reading()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:telemetry.record(r),range(16)))
    assert sum(not result['duplicate'] for result in results)==1
