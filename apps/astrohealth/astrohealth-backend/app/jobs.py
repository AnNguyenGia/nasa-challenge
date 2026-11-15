"""Durable bounded service queues. Heavy work executes in supervised worker processes."""

from __future__ import annotations

import base64
import csv
import io
import json
import time
from typing import Any, cast

from sqlalchemy import select

from app.core import audit, base, canonical, engine, jobs, now, transaction


def dispatch(kind: str, payload: dict[str, Any], timeout: float = 10) -> dict[str, Any]:
    row = base(kind=kind, priority=5, status="pending", payload=canonical(payload))
    with transaction() as conn:
        queued = conn.execute(select(jobs.c.id).where(jobs.c.status == "pending").limit(65)).all()
        if len(queued) >= 64:
            raise RuntimeError("Service queue is full (64 jobs)")
        conn.execute(jobs.insert().values(**row))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with engine.connect() as conn:
            result = conn.execute(select(jobs).where(jobs.c.id == row["id"])).mappings().one()
        if result["status"] == "done":
            return cast(dict[str, Any], json.loads(result["result"]))
        if result["status"] == "failed":
            raise ValueError(result["error"])
        time.sleep(0.05)
    raise RuntimeError(f"{kind} worker did not respond; job persisted as {row['id']}")


def report_bytes(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload["rows"]
    if payload["format"] == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream)
        keys = ["ts_utc", "metric", "value", "unit", "source_type", "quality_score", "stale"]
        writer.writerow(keys)
        for row in rows:
            writer.writerow([row[k] for k in keys])
        content = ("\ufeff" + stream.getvalue()).encode()
    else:
        from reportlab.pdfgen.canvas import Canvas

        output = io.BytesIO()
        canvas = Canvas(output)
        canvas.setTitle("AstroHealth monitoring report")
        canvas.drawString(45, 795, "ASTROHEALTH / LOCAL MONITORING REPORT")
        canvas.drawString(45, 774, "Monitoring support only. No diagnosis or treatment.")
        canvas.drawString(45, 753, "UTC: " + now()[:19])
        for i, row in enumerate(rows):
            canvas.drawString(
                45,
                715 - i * 22,
                f"{row['metric']}  {row['value']} {row['unit']}  "
                f"SOURCE={row['source_type']}  QUALITY={row['quality_score']} STALE={row['stale']}",
            )
        canvas.save()
        content = output.getvalue()
    return {"content": base64.b64encode(content).decode()}


def run_once(kind: str) -> None:
    with transaction() as conn:
        row = (
            conn.execute(
                select(jobs)
                .where(jobs.c.kind == kind, jobs.c.status == "pending")
                .order_by(jobs.c.priority, jobs.c.created_at)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if not row:
            return
        conn.execute(jobs.update().where(jobs.c.id == row["id"]).values(status="running", updated_at=now()))
    payload = json.loads(row["payload"])
    try:
        if kind == "ai-inference-service":
            from app.ml import run

            result = run(**payload, run_id=row["id"])
        elif kind == "report-service":
            result = report_bytes(payload)
        elif kind == "xai-service":
            from app.ml import explain_run

            result = explain_run(**payload)
        else:
            raise ValueError("Unsupported service task")
        values = {"status": "done", "result": canonical(result), "error": None}
    except Exception as exc:
        # Explicitly persisted failure; the worker continues and never returns a fabricated result.
        values = {"status": "failed", "error": type(exc).__name__ + ": " + str(exc)[:300]}
    with transaction() as conn:
        conn.execute(jobs.update().where(jobs.c.id == row["id"]).values(**values, updated_at=now()))
        audit(conn, kind, "job_" + str(values["status"]), row["id"])
