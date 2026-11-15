import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy import select

from app import ml
from app.core import audit, audit_log, domains, engine, outbox, settings, transaction, verify_audit
from app.sync import FileDrop, Intermittent, enqueue, sync_once
from app.telemetry import RuleState, evaluate_once, load_rules

RULE = {"direction": "above", "threshold": 120, "clear": 110, "duration_seconds": 3, "min_quality": 0.8}


def test_self_registration_disabled_in_operational_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "mode", "operational")
    response = client.post(
        "/api/v1/auth/self-register",
        json={"username": "unapproved", "display_name": "Unapproved", "password": "testing-pass-123"},
        headers={"Origin": "http://127.0.0.1:8000"},
    )
    assert response.status_code == 403


@given(st.floats(min_value=-1000, max_value=1000), st.floats(min_value=0, max_value=0.7999))
def test_bad_signal_never_triggers(value, quality):
    assert RuleState().step(RULE, value, 100, quality) == "insufficient_data"


def test_hysteresis_duration_and_recovery():
    state = RuleState()
    assert state.step(RULE, 130, 0, 1) == "pending"
    assert state.step(RULE, 130, 2, 1) == "pending"
    assert state.step(RULE, 130, 3, 1) == "triggered"
    assert state.step(RULE, 115, 4, 1) == "active"
    assert state.step(RULE, 109, 5, 1) == "resolved"


def test_quality_breaks_duration():
    state = RuleState()
    state.step(RULE, 130, 0, 1)
    state.step(RULE, 130, 2, 0.2)
    assert state.step(RULE, 130, 3, 1) == "pending"


def test_scope_sessions_and_replay(client, token):
    medical = token()
    roster = client.get("/api/v1/crew", headers=medical).json()
    personal = token("astro")
    assert client.get("/api/v1/vitals/" + roster[1]["id"], headers=personal).status_code == 403
    assert client.get("/api/v1/vitals/" + roster[0]["id"], headers=token("ground")).status_code == 403
    assert client.get("/api/v1/vitals/" + roster[0]["id"]).status_code == 401
    auth = client.post("/api/v1/auth/login", json={"username": "med", "password": "testing-pass-123"}).json()
    old_refresh = auth["refresh_token"]
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh}).status_code == 200
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401
    header = {"Authorization": "Bearer " + auth["access_token"]}
    assert client.post("/api/v1/auth/logout", headers=header).status_code == 200
    assert client.get("/api/v1/crew", headers=header).status_code == 401


def test_measurements_alerts_and_no_ai_dependency(client, token):
    medical = token()
    identifier = client.get("/api/v1/crew", headers=medical).json()[0]["id"]
    payload = {
        "crew_id": identifier,
        "metric": "spo2",
        "value": 85,
        "unit": "%",
        "source_type": "simulated",
        "ts_utc": datetime.now(UTC).isoformat(),
        "quality_score": 1,
    }
    assert client.post("/api/v1/measurements", json=[payload], headers=medical).status_code == 200
    states = {}
    evaluate_once(states, "")
    found = client.get("/api/v1/alerts?crew_id=" + identifier, headers=medical).json()
    critical = next(a for a in found if a["level"] == "Critical")
    assert critical["source_type"] == "simulated"
    assert (
        client.post("/api/v1/alerts/" + critical["id"] + "/acknowledge", headers=medical).status_code == 200
    )
    assert len(client.get("/api/v1/alerts?crew_id=" + identifier, headers=medical).json()) == len(found)
    # Full replay after worker restart does not duplicate durable alerts.
    evaluate_once({}, "")
    assert len(client.get("/api/v1/alerts?crew_id=" + identifier, headers=medical).json()) == len(found)
    payload["unit"] = "bpm"
    assert client.post("/api/v1/measurements", json=[payload], headers=medical).status_code == 422
    payload["unit"] = "%"
    payload["ts_utc"] = "2026-11-14T12:00:00"
    assert client.post("/api/v1/measurements", json=[payload], headers=medical).status_code == 422


def test_audit_tamper_and_transaction_rollback(client):
    with transaction() as conn:
        audit(conn, "test", "verify", "test")
        assert verify_audit(conn)
    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        conn.execute(audit_log.update().where(audit_log.c.sequence == 1).values(action="tampered"))
        assert not verify_audit(conn)
        conn.rollback()
    with engine.connect() as conn:
        assert verify_audit(conn)


def test_offline_resumable_and_idempotent(tmp_path, client):
    with transaction() as conn:
        identifier = enqueue(conn, "report", {"test": "abc" * 50000}, 2)
    transport = Intermittent(FileDrop(tmp_path), False)
    # Isolate from any alert bundle created by previous tests.
    with transaction() as conn:
        conn.execute(outbox.update().where(outbox.c.id != identifier).values(status="sent"))
    failed_at = datetime.now(UTC)
    sync_once(transport, at=failed_at)
    with engine.connect() as conn:
        row = conn.execute(select(outbox).where(outbox.c.id == identifier)).mappings().one()
        assert row["status"] == "needs_retry"
    transport.online = True
    for step in range(20):
        sync_once(transport, at=failed_at + timedelta(seconds=step + 3))
    target = tmp_path / (identifier + ".bundle")
    assert target.exists()
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    with engine.connect() as conn:
        row = conn.execute(select(outbox).where(outbox.c.id == identifier)).mappings().one()
        assert row["status"] == "sent" and row["checksum"] == digest
    assert transport.send(identifier, target.read_bytes(), 0, digest) == target.stat().st_size


def test_sync_retry_backoff_does_not_block_other_work(tmp_path, client):
    with transaction() as conn:
        high = enqueue(conn, "alert", {"priority": "high"}, 0)
        low = enqueue(conn, "report", {"priority": "low"}, 2)
        conn.execute(outbox.update().where(outbox.c.id.not_in([high, low])).values(status="sent"))
    started = datetime.now(UTC)
    transport = Intermittent(FileDrop(tmp_path), False)
    sync_once(transport, at=started)
    with engine.connect() as conn:
        row = conn.execute(select(outbox).where(outbox.c.id == high)).mappings().one()
        assert row["status"] == "needs_retry" and row["attempts"] == 1
    transport.online = True
    sync_once(transport, at=started + timedelta(seconds=1))
    with engine.connect() as conn:
        high_row = conn.execute(select(outbox).where(outbox.c.id == high)).mappings().one()
        low_row = conn.execute(select(outbox).where(outbox.c.id == low)).mappings().one()
        assert high_row["status"] == "needs_retry" and high_row["attempts"] == 1
        assert low_row["status"] == "sent"
    sync_once(transport, at=started + timedelta(seconds=3))
    with engine.connect() as conn:
        assert conn.execute(select(outbox.c.status).where(outbox.c.id == high)).scalar_one() == "sent"


def test_sync_transport_without_progress_is_retried(client):
    class Stalled:
        def send(self, identifier, data, offset, checksum):
            return offset

    with transaction() as conn:
        identifier = enqueue(conn, "report", {"test": "stalled"}, 1)
        conn.execute(outbox.update().where(outbox.c.id != identifier).values(status="sent"))
    sync_once(Stalled())
    with engine.connect() as conn:
        row = conn.execute(select(outbox).where(outbox.c.id == identifier)).mappings().one()
        assert row["status"] == "needs_retry" and row["attempts"] == 1


def test_rule_dual_approval(client, token):
    auth = token()
    result = client.post(
        "/api/v1/alert-rules",
        headers=auth,
        json={**RULE, "id": "TEST-HR-v1", "metric": "hr", "level": "Warning"},
    )
    assert result.status_code == 200, result.text
    path = "/api/v1/alert-rules/" + result.json()["id"] + "/approve"
    assert client.post(path, headers=auth).status_code == 409
    assert client.post(path, headers=token("med2")).status_code == 200
    active_ids = {rule["id"] for rule in load_rules()}
    assert {"DEMO-HR-HIGH-v1", "DEMO-SPO2-LOW-v1", "TEST-HR-v1"} <= active_ids


def test_reports_assistant_and_onnx(client, token):
    auth = token()
    identifier = client.get("/api/v1/crew", headers=auth).json()[0]["id"]
    csv = client.get("/api/v1/reports/" + identifier + "/export", headers=auth)
    assert csv.status_code == 200 and "simulated" in csv.text
    pdf = client.get("/api/v1/reports/" + identifier + "/export?format=pdf", headers=auth)
    assert pdf.content.startswith(b"%PDF")
    response = client.post(
        "/api/v1/assistant/query", headers=auth, json={"crew_id": identifier, "query": "chẩn đoán và thuốc"}
    )
    assert response.json()["intent"] == "out_of_scope"
    response = client.post(
        "/api/v1/ai/inference",
        headers=auth,
        json={"crew_id": identifier, "model_id": "anomaly-demo", "features": [0.2, 0.4, 0.6]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["model_is_placeholder"] is True
    assert response.json()["scores"][0] == pytest.approx(0.012, abs=1e-5)
    response = client.post(
        "/api/v1/ai/inference",
        headers=auth,
        json={"crew_id": identifier, "model_id": "ecg-classification", "features": [0.2, 0.4, 0.6]},
    )
    assert response.status_code == 422
    history = client.get("/api/v1/vitals/" + identifier + "/history?days=7&points=10", headers=auth).json()
    assert len(history["points"]) <= 10
    assert "simulated" in history["by_source"]


def test_model_activation_changes_inference_and_rollback(client, token, monkeypatch):
    installed = ml.manifests()
    alternate = {
        **next(model for model in installed if model["id"] == "forecast-demo"),
        "id": "anomaly-demo",
        "version": "synthetic-2",
    }
    monkeypatch.setattr(ml, "manifests", lambda: [*installed, alternate])
    auth = token()
    path = "/api/v1/ai/models/anomaly-demo"
    activation_ids = []
    try:
        first = client.put(path + "/activate", json={"version": "synthetic-1"}, headers=auth)
        assert first.status_code == 200, first.text
        activation_ids.append(first.json()["id"])
        second = client.put(path + "/activate", json={"version": "synthetic-2"}, headers=auth)
        assert second.status_code == 200, second.text
        activation_ids.append(second.json()["id"])
        listed = client.get("/api/v1/ai/models", headers=auth).json()
        assert next(m for m in listed if m["id"] == "anomaly-demo" and m["version"] == "synthetic-2")[
            "active"
        ]
        crew_id = client.get("/api/v1/crew", headers=auth).json()[0]["id"]
        run = ml.run("anomaly-demo", crew_id, [0.2, 0.4, 0.6], "test")
        assert run["version"] == "synthetic-2"
        assert run["scores"][0] == pytest.approx(0.46, abs=1e-5)
        rollback = client.put(path + "/rollback", json={"version": "synthetic-1"}, headers=auth)
        assert rollback.status_code == 200, rollback.text
        activation_ids.append(rollback.json()["id"])
        restored = ml.run("anomaly-demo", crew_id, [0.2, 0.4, 0.6], "test")
        assert restored["version"] == "synthetic-1"
        assert restored["scores"][0] == pytest.approx(0.012, abs=1e-5)
        explanation = ml.explain_run(run["id"])
        assert explanation["version"] == "synthetic-2"
        assert explanation["explanation"]["attribution"] == pytest.approx([0.04, 0.12, 0.3])
    finally:
        with transaction() as conn:
            conn.execute(
                domains["model_versions"].delete().where(domains["model_versions"].c.id.in_(activation_ids))
            )


def test_websocket_requires_auth(client):
    with client.websocket_connect("/ws/live") as socket:
        socket.send_json({"token": "invalid", "crew_id": "invalid"})
        assert socket.receive()["type"] == "websocket.close"
