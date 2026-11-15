"""Versioned REST/WebSocket gateway, serving the offline console on the same origin."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import threading
import time
import unicodedata
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncIterator, Literal

from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app import ml, security
from app.core import (
    ROOT,
    alerts,
    audit,
    base,
    canonical,
    crew,
    domains,
    engine,
    heartbeat,
    inference,
    initialize,
    now,
    outbox,
    records,
    sessions,
    settings,
    transaction,
    users,
    verify_audit,
)
from app.extra import router
from app.jobs import dispatch
from app.telemetry import Measurement, ingest, latest, lttb, recent_history


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize()
    _integrity_status()
    heartbeat("api-gateway")
    yield


app = FastAPI(
    title="AstroHealth local monitoring",
    version="3.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    description="Decision support only. Demo sources and placeholder models are explicitly labeled.",
)
P = "/api/v1"
User = dict[str, Any]

_integrity_lock = threading.Lock()
_integrity_checked_at = 0.0
_integrity_result: tuple[str, bool] = ("unchecked", False)


def _integrity_status() -> tuple[str, bool]:
    """Cache the expensive database and audit scan for one minute."""
    global _integrity_checked_at, _integrity_result
    with _integrity_lock:
        if time.monotonic() - _integrity_checked_at < 60:
            return _integrity_result
        with engine.connect() as conn:
            integrity = str(conn.exec_driver_sql("PRAGMA quick_check").scalar())
            audit_ok = verify_audit(conn)
        _integrity_result = (integrity, audit_ok)
        _integrity_checked_at = time.monotonic()
        return _integrity_result

if settings.mode == "demo":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["null", "http://127.0.0.1:8000"],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.get("/docs", include_in_schema=False)
def api_docs() -> Response:
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="AstroHealth offline API",
        swagger_js_url="/vendor/swagger-ui-bundle.js",
        swagger_css_url="/vendor/swagger-ui.css",
        swagger_favicon_url="/vendor/favicon.svg",
        swagger_ui_parameters={"validatorUrl": None, "persistAuthorization": False},
    )


@app.exception_handler(RuntimeError)
async def service_unavailable(_: Request, exc: RuntimeError) -> Response:
    return Response(canonical({"detail": str(exc)}), status_code=503, media_type="application/json")


@app.exception_handler(SQLAlchemyError)
async def storage_unavailable(_: Request, exc: SQLAlchemyError) -> Response:
    full = "disk is full" in str(exc) or "disk full" in str(exc)
    return Response(
        canonical(
            {
                "detail": "Local storage full; write was not confirmed"
                if full
                else "Local database unavailable; write was not confirmed"
            }
        ),
        status_code=507 if full else 503,
        media_type="application/json",
    )


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class FirstAccount(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=256)


class Registration(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["Astronaut", "Medical Officer", "Ground Control Operator"]
    crew_id: str | None = None


class SelfRegistration(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=256)


class CrewRegistration(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    callsign: str = Field(min_length=1, max_length=20)
    mission_id: str = Field(min_length=1, max_length=80)


class Refresh(BaseModel):
    refresh_token: str = Field(max_length=200)


class Password(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12, max_length=256)


class Note(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@app.get(P + "/auth/setup-status", tags=["Auth"])
def setup_status() -> dict[str, bool]:
    with engine.connect() as conn:
        has_account = conn.execute(select(users.c.id).where(users.c.deleted_at.is_(None)).limit(1)).first()
    return {"required": settings.mode == "demo" and not bool(has_account)}


@app.post(P + "/auth/setup", status_code=201, tags=["Auth"])
def setup_first_account(data: FirstAccount, request: Request) -> dict[str, str]:
    if settings.mode != "demo":
        raise HTTPException(403, "First account setup is available only in local demo mode")
    if request.headers.get("origin") not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        raise HTTPException(403, "Open the local AstroHealth app to create the first account")
    username = data.username.strip()
    if len(username) < 3:
        raise HTTPException(422, "Username must have at least three characters")
    with transaction() as conn:
        if conn.execute(select(users.c.id).where(users.c.deleted_at.is_(None)).limit(1)).first():
            raise HTTPException(409, "First account has already been created")
        row = base(
            username=username,
            password_hash=security.hasher.hash(data.password),
            role="Medical Officer",
            crew_id=None,
            failures=0,
            locked_until=0,
        )
        conn.execute(users.insert().values(**row))
        audit(conn, row["id"], "first_account_created", username, {"role": "Medical Officer"})
        return security.issue(conn, row)


@app.post(P + "/auth/login", tags=["Auth"])
def login(data: Login) -> dict[str, str]:
    return security.login(data.username, data.password)


@app.post(P + "/auth/self-register", status_code=201, tags=["Auth"])
def self_register(data: SelfRegistration, request: Request) -> dict[str, str]:
    if settings.mode != "demo":
        raise HTTPException(403, "Self-registration is available only for local demo profiles")
    if request.headers.get("origin") not in {"http://127.0.0.1:8000", "http://localhost:8000"}:
        raise HTTPException(403, "Open the local AstroHealth app to register")
    username = data.username.strip()
    display_name = data.display_name.strip()
    if len(username) < 3 or not display_name:
        raise HTTPException(422, "Username and display name are required")
    with transaction() as conn:
        if not conn.execute(
            select(users.c.id)
            .where(users.c.role.in_(["Medical Officer", "Admin"]), users.c.deleted_at.is_(None))
            .limit(1)
        ).first():
            raise HTTPException(409, "Create the first Medical Officer account before registration")
        if conn.execute(
            select(users.c.id).where(func.lower(users.c.username) == username.lower()).limit(1)
        ).first():
            raise HTTPException(409, "Username already exists")
        profile = base(name=display_name, callsign="SELF-" + username[:20], mission_id="LOCAL-DEMO", is_demo=1)
        conn.execute(crew.insert().values(**profile))
        row = base(
            username=username,
            password_hash=security.hasher.hash(data.password),
            role="Astronaut", crew_id=profile["id"], failures=0, locked_until=0,
        )
        conn.execute(users.insert().values(**row))
        audit(conn, row["id"], "self_registered", row["id"], {"crew_id": profile["id"], "mode": "demo"})
        return security.issue(conn, row)


@app.get(P + "/auth/accounts", tags=["Auth"])
def accounts(user: User = Depends(security.current)) -> list[dict[str, Any]]:
    security.medical(user)
    with engine.connect() as conn:
        rows = conn.execute(
            select(users.c.id, users.c.username, users.c.role, users.c.crew_id, users.c.created_at)
            .where(users.c.deleted_at.is_(None))
            .order_by(users.c.created_at)
        ).mappings()
        return [dict(row) for row in rows]


@app.post(P + "/auth/register", status_code=201, tags=["Auth"])
def register(data: Registration, user: User = Depends(security.current)) -> dict[str, Any]:
    security.medical(user)
    username = data.username.strip()
    if len(username) < 3:
        raise HTTPException(422, "Username must have at least three characters")
    with transaction() as conn:
        existing = conn.execute(
            select(users.c.id).where(func.lower(users.c.username) == username.lower()).limit(1)
        ).first()
        if existing:
            raise HTTPException(409, "Username already exists")
        if data.role == "Astronaut":
            if not data.crew_id or not conn.execute(
                select(crew.c.id).where(crew.c.id == data.crew_id, crew.c.deleted_at.is_(None))
            ).first():
                raise HTTPException(422, "Astronaut requires an existing crew member")
        elif data.crew_id:
            raise HTTPException(422, "Crew member can only be assigned to an Astronaut")
        row = base(
            username=username,
            password_hash=security.hasher.hash(data.password),
            role=data.role,
            crew_id=data.crew_id if data.role == "Astronaut" else None,
            failures=0,
            locked_until=0,
        )
        conn.execute(users.insert().values(**row))
        audit(conn, user["id"], "account_registered", row["id"], {"role": data.role, "crew_id": row["crew_id"]})
    return {key: row[key] for key in ("id", "username", "role", "crew_id", "created_at")}


@app.post(P + "/auth/refresh", tags=["Auth"])
def refresh(data: Refresh) -> dict[str, str]:
    with transaction() as conn:
        row = (
            conn.execute(
                select(sessions).where(
                    sessions.c.refresh_hash == hashlib.sha256(data.refresh_token.encode()).hexdigest()
                )
            )
            .mappings()
            .first()
        )
        if not row or row["revoked"] or row["expires"] < time.time():
            raise HTTPException(401, "Invalid refresh token")
        user = conn.execute(select(users).where(users.c.id == row["user_id"])).mappings().one()
        return security.issue(conn, user, row["id"])


@app.post(P + "/auth/logout", tags=["Auth"])
def logout(user: User = Depends(security.current)) -> dict[str, bool]:
    with transaction() as conn:
        conn.execute(sessions.update().where(sessions.c.id == user["session_id"]).values(revoked=1))
        audit(conn, user["id"], "logout", "auth")
    return {"ok": True}


@app.get(P + "/auth/me", tags=["Auth"])
def me(user: User = Depends(security.current)) -> dict[str, Any]:
    return {k: user[k] for k in ["id", "username", "role", "crew_id"]}


@app.post(P + "/auth/password", tags=["Auth"])
def password(data: Password, user: User = Depends(security.current)) -> dict[str, bool]:
    try:
        security.hasher.verify(user["password_hash"], data.old_password)
    except VerificationError as exc:
        raise HTTPException(401, "Invalid current password") from exc
    with transaction() as conn:
        conn.execute(
            users.update()
            .where(users.c.id == user["id"])
            .values(password_hash=security.hasher.hash(data.new_password))
        )
        conn.execute(sessions.update().where(sessions.c.user_id == user["id"]).values(revoked=1))
        audit(conn, user["id"], "password_changed", "auth")
    return {"ok": True}


@app.get(P + "/crew", tags=["Crew"])
def list_crew(user: User = Depends(security.current)) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        query = select(crew).where(crew.c.deleted_at.is_(None))
        if user["role"] == "Astronaut":
            query = query.where(crew.c.id == user["crew_id"])
        elif not settings.show_demo_data:
            query = query.where(crew.c.is_demo == 0)
        rows = list(conn.execute(query).mappings())
    if user["role"] == "Ground Control Operator":
        return [{"id": r["id"], "callsign": r["callsign"]} for r in rows]
    return [dict(r) for r in rows]


@app.post(P + "/crew", status_code=201, tags=["Crew"])
def create_crew(data: CrewRegistration, user: User = Depends(security.current)) -> dict[str, Any]:
    security.medical(user)
    name, callsign, mission_id = data.name.strip(), data.callsign.strip(), data.mission_id.strip()
    if not all((name, callsign, mission_id)):
        raise HTTPException(422, "Name, callsign and mission are required")
    with transaction() as conn:
        existing = conn.execute(
            select(crew.c.id).where(
                func.lower(crew.c.callsign) == callsign.lower(),
                func.lower(crew.c.mission_id) == mission_id.lower(),
                crew.c.deleted_at.is_(None),
            ).limit(1)
        ).first()
        if existing:
            raise HTTPException(409, "Callsign already exists in this mission")
        row = base(name=name, callsign=callsign, mission_id=mission_id, is_demo=0)
        conn.execute(crew.insert().values(**row))
        audit(conn, user["id"], "crew_created", row["id"], {"mission_id": mission_id})
    return row


@app.post(P + "/measurements", tags=["Ingestion"])
def measurements(data: list[Measurement], user: User = Depends(security.current)) -> dict[str, Any]:
    if not 1 <= len(data) <= 2000:
        raise HTTPException(422, "Batch must contain 1–2000 measurements")
    for item in data:
        security.scope(user, item.crew_id)
        if user["role"] == "Astronaut" and item.source_type != "self_reported":
            raise HTTPException(403, "Astronaut ingestion must be self_reported")
    return {"ids": ingest(data, user["id"])}


@app.get(P + "/vitals/{crew_id}", tags=["Vitals"])
def vitals(crew_id: str, user: User = Depends(security.current)) -> list[dict[str, Any]]:
    security.scope(user, crew_id)
    with transaction() as conn:
        audit(conn, user["id"], "read_sensitive", crew_id)
    return latest(crew_id)


@app.get(P + "/vitals/{crew_id}/history", tags=["Vitals", "Analytics"])
def history(
    crew_id: str,
    metric: str = "hr",
    days: int = Query(7, ge=1, le=365),
    points: int = Query(300, ge=3, le=2000),
    user: User = Depends(security.current),
) -> dict[str, Any]:
    security.scope(user, crew_id)
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with transaction() as conn:
        rows = recent_history(conn, crew_id, metric, cutoff)
        audit(conn, user["id"], "history_read", crew_id, {"metric": metric, "days": days})
    groups: dict[str, list[float]] = {}
    for row in rows:
        groups.setdefault(row["source_type"], []).append(row["value"])
    return {
        "points": lttb(rows, points),
        "sample_count": len(rows),
        "by_source": {
            s: {"count": len(v), "mean": sum(v) / len(v), "min": min(v), "max": max(v)}
            for s, v in groups.items()
        },
        "limit": 200000,
    }


ORGAN_METRICS = {
    "cardio": ["hr", "sbp", "dbp", "hrv"],
    "resp": ["spo2", "rr"],
    "neuro": [],
    "musculoskeletal": [],
    "immune": [],
}


@app.get(P + "/body/{crew_id}/status", tags=["Body"])
def body_status(crew_id: str, user: User = Depends(security.current)) -> dict[str, Any]:
    values = vitals(crew_id, user)
    active = list_alerts(crew_id, user=user)
    result = {}
    for organ, metrics in ORGAN_METRICS.items():
        available = [
            r for r in values if r["metric"] in metrics and not r["stale"] and r["quality_score"] >= 0.8
        ]
        warnings = [a for a in active if a["metric"] in metrics and a["status"] != "resolved"]
        state = "warning" if warnings else "insufficient_data"
        reason = (
            "Active deterministic rule" if warnings else "No validated assessment or insufficient fresh data"
        )
        result[organ] = {"status": state, "reason": reason, "metrics": available}
    return result


@app.get(P + "/organs/{organ}/metrics", tags=["Body"])
def organ_metrics(organ: str, crew_id: str, user: User = Depends(security.current)) -> list[dict[str, Any]]:
    if organ not in ORGAN_METRICS:
        raise HTTPException(404, "Unknown organ system")
    return [r for r in vitals(crew_id, user) if r["metric"] in ORGAN_METRICS[organ]]


@app.get(P + "/alerts", tags=["Alerts"])
def list_alerts(
    crew_id: str, status: str | None = None, user: User = Depends(security.current)
) -> list[dict[str, Any]]:
    security.scope(user, crew_id)
    with engine.connect() as conn:
        stmt = select(alerts).where(alerts.c.crew_id == crew_id)
        if not settings.show_demo_data:
            stmt = stmt.where(alerts.c.source_type != "simulated")
        if status:
            stmt = stmt.where(alerts.c.status == status)
        rows = [
            dict(r) for r in conn.execute(stmt.order_by(alerts.c.created_at.desc()).limit(500)).mappings()
        ]
    return sorted(rows, key=lambda r: {"Critical": 0, "Warning": 1, "Watch": 2, "Normal": 3}[r["level"]])


@app.post(P + "/alerts/{alert_id}/acknowledge", tags=["Alerts"])
def acknowledge(alert_id: str, user: User = Depends(security.current)) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(select(alerts).where(alerts.c.id == alert_id)).mappings().first()
        if not row:
            raise HTTPException(404, "Unknown alert")
        security.scope(user, row["crew_id"])
        if row["status"] == "open":
            conn.execute(
                alerts.update()
                .where(alerts.c.id == alert_id)
                .values(status="acknowledged", ack_by=user["id"], ack_at=now(), version=row["version"] + 1)
            )
            audit(conn, user["id"], "alert_acknowledged", alert_id)
    return {"id": alert_id, "status": "acknowledged" if row["status"] == "open" else row["status"]}


@app.post(P + "/alerts/{alert_id}/notes", tags=["Alerts"])
def alert_note(alert_id: str, data: Note, user: User = Depends(security.current)) -> dict[str, str]:
    with transaction() as conn:
        row = conn.execute(select(alerts).where(alerts.c.id == alert_id)).mappings().first()
        if not row:
            raise HTTPException(404, "Unknown alert")
        security.scope(user, row["crew_id"])
        item = base(
            kind="alert_note",
            crew_id=row["crew_id"],
            source_type="self_reported",
            payload=canonical({"alert_id": alert_id, "note": data.text, "actor": user["id"]}),
        )
        conn.execute(records.insert().values(**item))
        audit(conn, user["id"], "alert_note", alert_id)
    return {"id": item["id"]}


class Rule(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    metric: str
    direction: Literal["above", "below"]
    threshold: float = Field(allow_inf_nan=False)
    clear: float = Field(allow_inf_nan=False)
    duration_seconds: float = Field(ge=0, le=3600)
    min_quality: float = Field(ge=0, le=1)
    level: Literal["Watch", "Warning", "Critical"]


@app.post(P + "/alert-rules", tags=["Rules"])
def propose_rule(data: Rule, user: User = Depends(security.current)) -> dict[str, Any]:
    security.medical(user)
    if (
        data.direction == "above"
        and data.clear >= data.threshold
        or data.direction == "below"
        and data.clear <= data.threshold
    ):
        raise HTTPException(422, "Invalid hysteresis")
    payload = {**data.model_dump(), "proposed_by": user["id"], "approved_by": None, "active": False}
    item = base(payload=canonical(payload))
    with transaction() as conn:
        conn.execute(domains["alert_rules"].insert().values(**item))
        audit(conn, user["id"], "rule_proposed", item["id"], payload)
    return {**payload, "id": item["id"]}


@app.post(P + "/alert-rules/{rule_id}/approve", tags=["Rules"])
def approve_rule(rule_id: str, user: User = Depends(security.current)) -> dict[str, bool]:
    security.medical(user)
    t = domains["alert_rules"]
    with transaction() as conn:
        row = conn.execute(select(t).where(t.c.id == rule_id)).mappings().first()
        if not row:
            raise HTTPException(404, "Unknown rule")
        payload = json.loads(row["payload"])
        if payload["proposed_by"] == user["id"]:
            raise HTTPException(409, "Approval requires a second Medical Officer/Admin")
        payload.update(approved_by=user["id"], active=True)
        conn.execute(
            t.update().where(t.c.id == rule_id).values(payload=canonical(payload), version=row["version"] + 1)
        )
        audit(conn, user["id"], "rule_approved", rule_id, payload)
    return {"ok": True}


@app.get(P + "/ai/models", tags=["AI"])
def models(user: User = Depends(security.current)) -> list[dict[str, Any]]:
    listed = ml.manifests()
    activated = ml.activated_versions()
    defaults: dict[str, str] = {}
    if settings.mode == "demo":
        for model in listed:
            if model.get("checkpoint"):
                defaults.setdefault(model["id"], model["version"])
    return [
        {
            **model,
            "active": (
                model["version"] == activated[model["id"]]["version"]
                and model.get("sha256") == activated[model["id"]]["hash"]
                if model["id"] in activated
                else defaults.get(model["id"]) == model["version"]
            ),
        }
        for model in listed
    ]


class Infer(BaseModel):
    crew_id: str
    model_id: str
    features: list[float] = Field(min_length=1, max_length=128)


@app.post(P + "/ai/inference", tags=["AI"])
def infer(data: Infer, user: User = Depends(security.current)) -> dict[str, Any]:
    security.scope(user, data.crew_id)
    try:
        result = dispatch(
            "ai-inference-service",
            {
                "model_id": data.model_id,
                "crew_id": data.crew_id,
                "features": data.features,
                "actor": user["id"],
            },
        )
        return dispatch("xai-service", {"identifier": result["id"]})
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get(P + "/inference/{identifier}/explanation", tags=["XAI"])
def explanation(identifier: str, user: User = Depends(security.current)) -> dict[str, Any]:
    with transaction() as conn:
        row = conn.execute(select(inference).where(inference.c.id == identifier)).mappings().first()
        if not row:
            raise HTTPException(404, "Inference not found")
        security.scope(user, row["crew_id"])
        audit(conn, user["id"], "explanation_read", identifier)
    return dispatch("xai-service", {"identifier": identifier})


KINDS = {"sleep", "nutrition", "environment", "radiation", "questionnaire", "cognitive", "lab", "event"}


class Record(BaseModel):
    crew_id: str
    source_type: Literal["self_reported", "simulated", "measured"]
    payload: dict[str, Any]


@app.get(P + "/records/{kind}", tags=["Domain records"])
def list_records(kind: str, crew_id: str, user: User = Depends(security.current)) -> list[dict[str, Any]]:
    security.scope(user, crew_id)
    if kind not in KINDS:
        raise HTTPException(404, "Unknown record type")
    with transaction() as conn:
        rows = list(
            conn.execute(
                select(records)
                .where(records.c.kind == kind, records.c.crew_id == crew_id)
                .order_by(records.c.created_at.desc())
                .limit(500)
            ).mappings()
        )
        audit(conn, user["id"], "domain_read", crew_id, {"kind": kind})
    return [{**r, "payload": json.loads(r["payload"])} for r in rows]


@app.post(P + "/records/{kind}", tags=["Domain records"])
def add_record(kind: str, data: Record, user: User = Depends(security.current)) -> dict[str, str]:
    security.scope(user, data.crew_id)
    if kind not in KINDS:
        raise HTTPException(404, "Unknown record type")
    if user["role"] == "Astronaut" and data.source_type != "self_reported":
        raise HTTPException(403, "Astronaut records must be self_reported")
    item = base(
        kind=kind, crew_id=data.crew_id, source_type=data.source_type, payload=canonical(data.payload)
    )
    with transaction() as conn:
        conn.execute(records.insert().values(**item))
        audit(conn, user["id"], "record_created", item["id"])
    return {"id": item["id"]}


@app.get(P + "/reports/{crew_id}/export", tags=["Reports"])
def report(
    crew_id: str, format: Literal["csv", "pdf"] = "csv", user: User = Depends(security.current)
) -> Response:
    rows = vitals(crew_id, user)
    with transaction() as conn:
        audit(conn, user["id"], "report_export", crew_id, {"format": format})
    import base64

    try:
        result = dispatch("report-service", {"rows": rows, "format": format})
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(
        base64.b64decode(result["content"]),
        media_type="text/csv" if format == "csv" else "application/pdf",
        headers={"Content-Disposition": f'attachment; filename="astrohealth.{format}"'},
    )


class Question(BaseModel):
    crew_id: str
    query: str = Field(max_length=2000)


@app.post(P + "/assistant/query", tags=["Assistant"])
def assistant(data: Question, user: User = Depends(security.current)) -> dict[str, Any]:
    security.scope(user, data.crew_id)
    q = "".join(c for c in unicodedata.normalize("NFD", data.query.lower()) if not unicodedata.combining(c))
    q = q.replace("đ", "d")
    if any(k in q for k in ["chan doan", "dieu tri", "thuoc", "diagnos", "treatment", "medication"]):
        return {
            "intent": "out_of_scope",
            "answer": "Trợ lý chỉ hỗ trợ giám sát; không chẩn đoán hoặc chỉ định điều trị.",
        }
    if any(k in q for k in ["7 ngay", "7 day", "so sanh", "compare"]):
        result = history(data.crew_id, "hr", 7, 100, user)
        return {
            "intent": "hr_history",
            "answer": "Thống kê HR 7 ngày, phân tách theo nguồn dữ liệu.",
            "data": result,
        }
    if any(k in q for k in ["ngu", "sleep"]):
        return {
            "intent": "sleep",
            "answer": "Nhật ký giấc ngủ cục bộ.",
            "data": list_records("sleep", data.crew_id, user),
        }
    if any(k in q for k in ["canh bao", "alert", "why"]):
        return {
            "intent": "alerts",
            "answer": "Cảnh báo phát sinh từ quy tắc xác định, độc lập AI.",
            "data": list_alerts(data.crew_id, user=user),
        }
    if any(k in q for k in ["bao cao", "report"]):
        return {
            "intent": "report",
            "answer": "Có thể xuất báo cáo CSV/PDF trong trang REPORTS.",
            "export_path": f"{P}/reports/{data.crew_id}/export",
        }
    if "ecg" in q:
        return {
            "intent": "ecg",
            "answer": "Sóng trên giao diện demo là SIMULATED. Chưa có bản ghi ECG đo thực.",
        }
    if any(k in q for k in ["hr", "nhip tim", "vital", "chi so", "latest", "moi nhat"]):
        return {
            "intent": "latest",
            "answer": "Chỉ số mới nhất; kiểm tra nguồn, thời gian và chất lượng dữ liệu.",
            "data": vitals(data.crew_id, user),
        }
    return {
        "intent": "help",
        "answer": "Hỗ trợ: chỉ số mới nhất, cảnh báo, HR 7 ngày, ECG, giấc ngủ, báo cáo.",
    }


@app.get(P + "/sync/status", tags=["Sync"])
def sync_status(user: User = Depends(security.current)) -> dict[str, Any]:
    if user["role"] == "Astronaut":
        raise HTTPException(403, "Operator access required")
    with engine.connect() as conn:
        counts: dict[str, int] = {
            str(r[0]): int(r[1])
            for r in conn.execute(select(outbox.c.status, func.count()).group_by(outbox.c.status))
        }
    return {"counts": counts, "transport": "local_file_drop_simulator", "ground_connected": False}


@app.post(P + "/sync/retry", tags=["Sync"])
def retry(user: User = Depends(security.current)) -> dict[str, bool]:
    if user["role"] == "Astronaut":
        raise HTTPException(403, "Operator access required")
    with transaction() as conn:
        conn.execute(
            outbox.update().where(outbox.c.status.in_(["failed", "needs_retry"])).values(status="pending")
        )
        audit(conn, user["id"], "sync_retry", "sync")
    return {"ok": True}


@app.get("/health", tags=["System"])
@app.get(P + "/health", tags=["System"])
def health() -> dict[str, Any]:
    heartbeat("api-gateway")
    integrity, audit_ok = _integrity_status()
    with engine.connect() as conn:
        services = {
            r[0]: {
                "age_seconds": round(time.time() - r[1], 1),
                "status": "running" if time.time() - r[1] < 15 else "stale",
                "detail": r[2],
            }
            for r in conn.exec_driver_sql("SELECT * FROM service_heartbeats")
        }
    for name in [
        "ingestion-service",
        "alert-engine",
        "ai-inference-service",
        "xai-service",
        "sync-service",
        "report-service",
        "scheduler",
    ]:
        services.setdefault(name, {"status": "not_running"})
    disk_free = shutil.disk_usage(settings.data_dir).free
    return {
        "status": "ok"
        if integrity == "ok"
        and audit_ok
        and disk_free >= 64 * 1024 * 1024
        and all(s["status"] == "running" for s in services.values())
        else "degraded",
        "mode": settings.mode,
        "encryption": "plaintext_demo" if settings.mode == "demo" else "sqlcipher",
        "integrity": integrity,
        "audit_chain_valid": audit_ok,
        "services": services,
        "version": "3.0.0",
        "disk_free_bytes": disk_free,
        "disk_low": disk_free < 64 * 1024 * 1024,
        "power": "unavailable",
        "ground": "disconnected",
    }


@app.websocket("/ws/live")
async def live(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        # Bearer token in first frame; never put credentials in query strings/access logs.
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=5)
        user = security.authenticate(auth["token"])
        crew_id = auth["crew_id"]
        security.scope(user, crew_id)
        while True:
            security.authenticate(auth["token"])
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "vitals": latest(crew_id),
                    "alerts": list_alerts(crew_id, user=user),
                    "utc": now(),
                }
            )
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except (HTTPException, KeyError, asyncio.TimeoutError):
        await websocket.close(code=1008)


app.include_router(router)

DIST = ROOT.parent / "dist"
if DIST.exists():

    @app.get("/design", include_in_schema=False)
    def design() -> FileResponse:
        return FileResponse(DIST / "index.html")

    app.mount("/", StaticFiles(directory=DIST, html=True), name="console")
