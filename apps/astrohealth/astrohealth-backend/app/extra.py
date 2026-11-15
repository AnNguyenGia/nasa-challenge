"""Waveform, version management and aggregate API extensions."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text

from app import ml, security
from app.core import audit, base, canonical, crew, domains, engine, settings, transaction
from app.waveforms import Waveform, archive, read

router = APIRouter(prefix="/api/v1")


@router.post("/waveforms", tags=["Waveforms"])
def upload(data: Waveform, user: dict[str, Any] = Depends(security.current)) -> dict[str, Any]:
    security.medical(user)
    security.scope(user, data.crew_id)
    with engine.connect() as conn:
        if not conn.execute(select(crew.c.id).where(crew.c.id == data.crew_id)).first():
            raise HTTPException(404, "Crew not found")
    try:
        return archive(data, user["id"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/waveforms/{identifier}", tags=["Waveforms"])
def download(identifier: str, user: dict[str, Any] = Depends(security.current)) -> dict[str, Any]:
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(domains["waveform_segments"]).where(domains["waveform_segments"].c.id == identifier)
            )
            .mappings()
            .first()
        )
    if not row:
        raise HTTPException(404, "Waveform not found")
    security.scope(user, row["crew_id"])
    _, result = read(identifier)
    with transaction() as conn:
        audit(conn, user["id"], "waveform_read", identifier)
    return result


@router.get("/analytics/{crew_id}", tags=["Analytics"])
def analytics(
    crew_id: str,
    metric: str = "hr",
    bucket: str = Query("day", pattern="^(hour|day|month)$"),
    user: dict[str, Any] = Depends(security.current),
) -> dict[str, Any]:
    security.scope(user, crew_id)
    size = {"hour": 13, "day": 10, "month": 7}[bucket]
    with transaction() as conn:
        rows = conn.execute(
            text(
                "SELECT substr(ts_utc,1,:size) bucket,source_type,avg(value) mean,"
                "min(value) minimum,max(value) maximum,count(*) count FROM measurements "
                "WHERE crew_id=:crew AND metric=:metric AND deleted_at IS NULL "
                "GROUP BY bucket,source_type ORDER BY bucket LIMIT 10000"
            ),
            {"size": size, "crew": crew_id, "metric": metric},
        ).mappings()
        result = [dict(r) for r in rows]
        audit(conn, user["id"], "analytics_read", crew_id, {"metric": metric, "bucket": bucket})
    return {"metric": metric, "bucket": bucket, "by_source": result}


@router.get("/alert-rules", tags=["Rules"])
def rules(user: dict[str, Any] = Depends(security.current)) -> list[dict[str, Any]]:
    security.medical(user)
    with engine.connect() as conn:
        return [
            {**r, "payload": json.loads(r["payload"])}
            for r in conn.execute(select(domains["alert_rules"])).mappings()
        ]


class Activation(BaseModel):
    version: str


@router.put("/ai/models/{model_id}/activate", tags=["AI"])
def activate(
    model_id: str, data: Activation, user: dict[str, Any] = Depends(security.current)
) -> dict[str, Any]:
    security.medical(user)
    model = next((m for m in ml.manifests() if m["id"] == model_id and m["version"] == data.version), None)
    if not model or not model.get("checkpoint"):
        raise HTTPException(422, "No installed checkpoint for this version")
    if settings.mode != "demo" and model["model_is_placeholder"]:
        raise HTTPException(422, "Placeholder models cannot be activated in operational mode")
    checked = ml.ONNXModel(model)
    checked.load()  # Validate integrity and ONNX runtime compatibility before accepting activation.
    t = domains["model_versions"]
    item = base(
        payload=canonical(
            {
                "model_id": model_id,
                "version": data.version,
                "hash": model["sha256"],
                "status": "active",
                "actor": user["id"],
                "model_is_placeholder": model["model_is_placeholder"],
            }
        )
    )
    with transaction() as conn:
        conn.execute(t.insert().values(**item))
        audit(conn, user["id"], "model_activated", item["id"])
    return {
        "id": item["id"],
        "model_id": model_id,
        "version": data.version,
        "model_is_placeholder": model["model_is_placeholder"],
    }


@router.put("/ai/models/{model_id}/rollback", tags=["AI"])
def rollback(
    model_id: str, data: Activation, user: dict[str, Any] = Depends(security.current)
) -> dict[str, Any]:
    security.medical(user)
    with engine.connect() as conn:
        history = [json.loads(r[0]) for r in conn.execute(select(domains["model_versions"].c.payload))]
    if not any(
        r.get("model_id") == model_id and r.get("version") == data.version and r.get("status") == "active"
        for r in history
    ):
        raise HTTPException(409, "Version has no previous activation record")
    result = activate(model_id, data, user)
    with transaction() as conn:
        audit(conn, user["id"], "model_rollback", result["id"])
    return result
