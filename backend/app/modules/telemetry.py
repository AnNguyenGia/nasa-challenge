"""Telemetry owns validation + reading persistence + transactional event publication."""
import json
from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.core.db import connect

class Reading(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: UUID
    astronaut_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    observed_at: datetime
    heart_rate: float = Field(ge=20, le=250)
    temperature: float = Field(ge=30, le=45)
    sleep_hours: float = Field(ge=0, le=24)
    mood: int = Field(ge=1, le=5)

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("observed_at requires timezone")
        return value.astimezone(timezone.utc)

class ConflictError(Exception):
    pass

def record(reading: Reading, from_cloud=False):
    payload = json.dumps(reading.model_dump(mode="json"), sort_keys=True)
    key = str(reading.id)
    with connect() as db:
        # Serializes competing writers. Same ID + same body is acknowledged, not duplicated.
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT payload FROM readings WHERE id=?", (key,)).fetchone()
        if previous:
            if previous["payload"] != payload:
                raise ConflictError("ID exists with different content")
            return {"id": key, "duplicate": True}
        db.execute("INSERT INTO readings VALUES(?,?,?,?)",
                   (key, reading.astronaut_id, reading.observed_at.isoformat(), payload))
        db.execute("INSERT INTO events(id,type,payload,created_at,synced) VALUES(?,?,?,?,?)",
                   (key, "health.reading.recorded.v1", payload,
                    datetime.now(timezone.utc).isoformat(), int(from_cloud)))
    return {"id": key, "duplicate": False}

def recent(limit=100):
    with connect() as db:
        return [json.loads(r["payload"]) for r in db.execute(
            "SELECT payload FROM readings ORDER BY observed_at DESC LIMIT ?", (limit,))]
