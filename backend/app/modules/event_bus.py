"""Durable at-least-once bus inside ONE modular monolith process.
Handlers and their receipt commit together. Cloud HTTP is outside DB transactions.
"""
import asyncio
import json
import logging
import random
import time
import httpx
from app.core import config
from app.core.db import connect
from app.modules.analytics import assess

log = logging.getLogger(__name__)

def process_batch():
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        events = db.execute("SELECT * FROM events WHERE processed=0 LIMIT 25").fetchall()
        for event in events:
            result = assess(json.loads(event["payload"]))
            db.execute("INSERT OR REPLACE INTO assessments VALUES(?,?)",
                       (event["id"], json.dumps(result)))
            db.execute("UPDATE events SET processed=1 WHERE id=?", (event["id"],))
    return len(events)

async def sync_batch():
    if config.NODE_ROLE != "edge" or not config.CLOUD_URL:
        return
    with connect() as db:
        rows = db.execute("""SELECT * FROM events WHERE synced=0 AND dead_letter=0
            AND retry_at<=? ORDER BY created_at LIMIT 25""", (time.time(),)).fetchall()
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3)) as client:
        for row in rows:
            try:
                response = await client.post(config.CLOUD_URL, json={
                    "schema_version": 1, "type": row["type"],
                    "reading": json.loads(row["payload"])},
                    headers={"Authorization": "Bearer " + config.CLOUD_TOKEN})
                response.raise_for_status()
                if response.json().get("id") != row["id"]:
                    raise ValueError("invalid acknowledgment")
                with connect() as db:
                    db.execute("UPDATE events SET synced=1,last_error=NULL WHERE id=?", (row["id"],))
            except (httpx.HTTPError, ValueError) as error:
                status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else 0
                # Auth/config failures pause and retry. Schema/conflict errors need operator repair.
                dead = int(status in (400, 404, 409, 413, 422))
                delay = min(300, 2 ** min(row["attempts"] + 1, 8)) + random.uniform(0, 2)
                with connect() as db:
                    db.execute("""UPDATE events SET attempts=attempts+1,retry_at=?,
                        dead_letter=?,last_error=? WHERE id=?""",
                        (time.time() + delay, dead, f"sync_http_{status}" if status else "sync_unreachable", row["id"]))
                if not dead:
                    break  # Circuit break this batch; do not hammer an unavailable cloud.

async def run(stop: asyncio.Event):
    while not stop.is_set():
        try:
            await asyncio.to_thread(process_batch)
        except Exception:
            log.exception("analytics_worker_failed")
        try:
            await sync_batch()
        except Exception:
            log.exception("cloud_sync_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=2)
        except asyncio.TimeoutError:
            pass
