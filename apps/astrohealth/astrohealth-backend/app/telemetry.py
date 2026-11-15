"""Validated immutable measurements, source-aware analytics and deterministic alert processing."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from typing import Any, Literal

import yaml
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.engine import Connection

from app.core import (
    ROOT,
    alerts,
    audit,
    base,
    canonical,
    crew,
    domains,
    engine,
    now,
    partition,
    settings,
    transaction,
)

Source = Literal["measured", "simulated", "self_reported", "model_inferred"]
UNITS = {
    "hr": "bpm",
    "sbp": "mmHg",
    "dbp": "mmHg",
    "spo2": "%",
    "rr": "/min",
    "temp": "degC",
    "hrv": "ms",
    "co2": "ppm",
    "o2": "%",
    "radiation": "mSv/h",
}


class Measurement(BaseModel):
    crew_id: str
    metric: str
    value: float = Field(allow_inf_nan=False)
    unit: str
    ts_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_type: Source
    device_id: str | None = None
    quality_score: float = Field(default=1, ge=0, le=1)
    flags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("ts_utc")
    @classmethod
    def timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Timezone is required")
        if value.timestamp() > datetime.now(UTC).timestamp() + 300:
            raise ValueError("Clock offset exceeds +300 seconds")
        return value.astimezone(UTC)

    @field_validator("metric")
    @classmethod
    def metric_known(cls, value: str) -> str:
        if value not in UNITS:
            raise ValueError("Unsupported metric")
        return value


def ingest(items: list[Measurement], actor: str) -> list[str]:
    ids = []
    with transaction() as conn:
        known = set(conn.execute(select(crew.c.id)).scalars())
        partitions: dict[str, str] = {}
        for item in items:
            if item.crew_id not in known:
                raise HTTPException(404, "Unknown crew member")
            if UNITS[item.metric] != item.unit:
                raise HTTPException(422, "Canonical unit mismatch")
            ts = item.ts_utc.isoformat()
            month = ts[:7]
            if month not in partitions:
                partitions[month] = partition(conn, ts)
            flags = list(item.flags)
            if abs((datetime.now(UTC) - item.ts_utc).total_seconds()) > 60:
                flags.append("stale_or_clock_offset")
            row = base(
                **item.model_dump(exclude={"ts_utc", "flags"}),
                ts_utc=ts,
                ts_mission=(item.ts_utc - datetime.fromisoformat(settings.mission_epoch)).total_seconds(),
                flags=canonical(flags),
            )
            columns = ",".join(row)
            params = ",".join(":" + key for key in row)
            conn.execute(text(f"INSERT INTO {partitions[month]} ({columns}) VALUES ({params})"), row)
            ids.append(row["id"])
        audit(conn, actor, "ingest", "measurements", {"count": len(items), "ids": ids[:10]})
    return ids


def latest(crew_id: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        result = conn.execute(
            text("""SELECT * FROM (SELECT *,ROW_NUMBER() OVER
          (PARTITION BY metric ORDER BY ts_utc DESC,id DESC) AS rn FROM measurements
          WHERE crew_id=:crew AND deleted_at IS NULL) WHERE rn=1"""),
            {"crew": crew_id},
        ).mappings()
        return [
            {
                **r,
                "flags": __import__("json").loads(r["flags"]),
                "stale": (datetime.now(UTC) - datetime.fromisoformat(r["ts_utc"])).total_seconds() > 60,
            }
            for r in result
        ]


def recent_history(
    conn: Connection, crew_id: str, metric: str, cutoff: str, limit: int = 200000
) -> list[dict[str, Any]]:
    """Keep the newest bounded sample window, then restore chronological order."""
    if limit < 1:
        raise ValueError("History limit must be positive")
    rows = [
        dict(row)
        for row in conn.execute(
            text("""SELECT * FROM measurements WHERE crew_id=:crew
              AND metric=:metric AND ts_utc>=:cutoff AND deleted_at IS NULL
              ORDER BY ts_utc DESC,id DESC LIMIT :limit"""),
            {"crew": crew_id, "metric": metric, "cutoff": cutoff, "limit": limit},
        ).mappings()
    ]
    rows.reverse()
    return rows


def lttb(rows: list[dict[str, Any]], threshold: int) -> list[dict[str, Any]]:
    if len(rows) <= threshold or threshold < 3:
        return rows[:threshold]
    every = (len(rows) - 2) / (threshold - 2)
    picked, a = [rows[0]], 0
    points = [(datetime.fromisoformat(r["ts_utc"]).timestamp(), r["value"]) for r in rows]
    for i in range(threshold - 2):
        start = min(int((i + 1) * every) + 1, len(rows) - 1)
        end = min(int((i + 2) * every) + 1, len(rows))
        window = points[start:end] or [points[-1]]
        avgx = sum(p[0] for p in window) / len(window)
        avgy = sum(p[1] for p in window) / len(window)
        candidates = range(int(i * every) + 1, min(int((i + 1) * every) + 1, len(rows) - 1))
        ax, ay = points[a]
        a = max(
            candidates,
            key=lambda j: abs((ax - avgx) * (points[j][1] - ay) - (ax - points[j][0]) * (avgy - ay)),
        )
        picked.append(rows[a])
    return [*picked, rows[-1]]


class RuleState:
    """Rebuilt by replaying durable input after restart, never by an AI output."""

    def __init__(self) -> None:
        self.since: float | None = None
        self.active = False
        self.last_ts: float | None = None

    def step(self, rule: dict[str, Any], value: float, ts: float, quality: float, valid: bool = True) -> str:
        if self.last_ts is not None:
            if ts < self.last_ts:
                return "insufficient_data"
            if ts - self.last_ts > rule.get("max_gap_seconds", 5):
                self.since = None
        self.last_ts = ts
        if not valid or quality < rule["min_quality"] or not math.isfinite(value):
            self.since = None
            return "insufficient_data"
        high = rule["direction"] == "above"
        breach = value > rule["threshold"] if high else value < rule["threshold"]
        clear = value < rule["clear"] if high else value > rule["clear"]
        if self.active:
            if clear:
                self.active, self.since = False, None
                return "resolved"
            return "active"
        if not breach:
            self.since = None
            return "normal"
        if self.since is None:
            self.since = ts
        if ts - self.since >= rule["duration_seconds"]:
            self.active = True
            return "triggered"
        return "pending"


def load_rules() -> list[dict[str, Any]]:
    config = yaml.safe_load((ROOT / "configs/rules.yaml").read_text(encoding="utf-8"))
    # Demo examples stay active when a separately approved rule is added.
    # Operational mode starts empty and accepts only approved database rules.
    active: dict[str, dict[str, Any]] = (
        {str(rule["id"]): rule for rule in config["rules"]} if settings.mode == "demo" else {}
    )
    with engine.connect() as conn:
        versions = list(
            conn.execute(
                select(domains["alert_rules"])
                .where(domains["alert_rules"].c.deleted_at.is_(None))
                .order_by(domains["alert_rules"].c.created_at, domains["alert_rules"].c.id)
            ).mappings()
        )
    import json

    for entry in versions:
        data = json.loads(entry["payload"])
        if data.get("approved_by") and data.get("active"):
            active[str(data["id"])] = data
    return list(active.values())


def evaluate_once(states: dict[tuple[str, str, str], RuleState], cursor: str) -> str:
    rules = load_rules()
    with engine.connect() as conn:
        rows = list(
            conn.execute(
                text(
                    "SELECT * FROM measurements WHERE id>:cursor AND ts_utc>=:cutoff ORDER BY id LIMIT 2000"
                ),
                {
                    "cursor": cursor,
                    "cutoff": datetime.fromtimestamp(datetime.now(UTC).timestamp() - 60, UTC).isoformat(),
                },
            ).mappings()
        )
    import json

    for row in rows:
        for rule in rules:
            if row["metric"] != rule["metric"]:
                continue
            if settings.mode != "demo" and row["source_type"] != "measured":
                continue
            key = (row["crew_id"], rule["id"], row["source_type"])
            state = states.setdefault(key, RuleState())
            # Gaps must not count toward a duration threshold.
            ts = datetime.fromisoformat(row["ts_utc"]).timestamp()
            valid = not json.loads(row["flags"])
            result = state.step(rule, row["value"], ts, row["quality_score"], valid)
            evaluation_id = hashlib.sha256(f"{row['id']}:{rule['id']}".encode()).hexdigest()
            with transaction() as conn:
                t = domains["alert_evaluations"]
                if conn.execute(select(t.c.id).where(t.c.id == evaluation_id)).first():
                    continue
                conn.execute(
                    t.insert().values(**base(id=evaluation_id, payload=canonical({"result": result})))
                )
                active = list(
                    conn.execute(
                        select(alerts).where(
                            alerts.c.crew_id == row["crew_id"],
                            alerts.c.rule_id == rule["id"],
                            alerts.c.source_type == row["source_type"],
                            alerts.c.status != "resolved",
                        )
                    ).mappings()
                )
                if result == "triggered" and not active:
                    item = base(
                        crew_id=row["crew_id"],
                        metric=row["metric"],
                        level=rule["level"],
                        status="open",
                        rule_id=rule["id"],
                        source_type=row["source_type"],
                        measurement_id=row["id"],
                        payload=canonical({"rule": rule, "value": row["value"], "ts_utc": row["ts_utc"]}),
                    )
                    conn.execute(alerts.insert().values(**item))
                    audit(conn, "alert-engine", "alert_triggered", item["id"])
                    from app.sync import enqueue

                    enqueue(conn, "alert", item, priority=0 if rule["level"] == "Critical" else 1)
                elif result == "resolved":
                    for alert in active:
                        conn.execute(
                            alerts.update()
                            .where(alerts.c.id == alert["id"])
                            .values(status="resolved", updated_at=now(), version=alert["version"] + 1)
                        )
                        audit(conn, "alert-engine", "alert_resolved", alert["id"])
        cursor = row["id"]
    return cursor
