import asyncio
import hmac
import json
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, ConfigDict
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from app.core import config
from app.core.db import connect, initialize
from app.modules import telemetry, agent, event_bus

REQUESTS = Counter("health_requests_total", "HTTP requests", ["method", "status"])

@asynccontextmanager
async def lifespan(app):
    if len(config.API_TOKEN) < 24 or config.API_TOKEN.startswith("replace-"):
        raise RuntimeError("Set a random API_TOKEN of at least 24 characters")
    initialize()
    stop = asyncio.Event()
    worker = asyncio.create_task(event_bus.run(stop))
    yield
    stop.set()
    await worker

app = FastAPI(title="Space Health Modular Monolith", lifespan=lifespan)

@app.middleware("http")
async def metrics(request, call_next):
    response = await call_next(request)
    REQUESTS.labels(request.method, str(response.status_code)).inc()
    return response

def authorize(authorization: str = Header(default="")):
    if not config.API_TOKEN or not hmac.compare_digest(authorization, "Bearer " + config.API_TOKEN):
        raise HTTPException(401, "Invalid token")

@app.get("/healthz")
def health():
    with connect() as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok", "role": config.NODE_ROLE}

@app.get("/metrics", dependencies=[Depends(authorize)])
def metric_output():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.post("/api/readings", dependencies=[Depends(authorize)])
def create_reading(reading: telemetry.Reading):
    try:
        return telemetry.record(reading, from_cloud=config.NODE_ROLE == "cloud")
    except telemetry.ConflictError as error:
        raise HTTPException(409, str(error))

@app.get("/api/readings", dependencies=[Depends(authorize)])
def readings():
    return telemetry.recent()

class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    type: Literal["health.reading.recorded.v1"]
    reading: telemetry.Reading

@app.post("/api/events", dependencies=[Depends(authorize)])
def ingest_event(event: EventEnvelope):
    if config.NODE_ROLE != "cloud":
        raise HTTPException(403, "Cloud ingestion only")
    try:
        return telemetry.record(event.reading, from_cloud=True)
    except telemetry.ConflictError as error:
        raise HTTPException(409, str(error))

@app.get("/api/status", dependencies=[Depends(authorize)])
def status():
    with connect() as db:
        pending = db.execute("SELECT count(*) FROM events WHERE synced=0 AND dead_letter=0").fetchone()[0]
        dead = db.execute("SELECT count(*) FROM events WHERE dead_letter=1").fetchone()[0]
        assessments = [dict(r) for r in db.execute("SELECT * FROM assessments ORDER BY rowid DESC LIMIT 100")]
    return {"role": config.NODE_ROLE, "cloud_configured": bool(config.CLOUD_URL),
            "cloud_pending": pending, "dead_letters": dead,
            "assessments": [{"reading_id": r["reading_id"], **json.loads(r["payload"])} for r in assessments]}

class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

@app.post("/api/agent", dependencies=[Depends(authorize)])
async def ask(body: Question):
    return await agent.answer(body.question)
