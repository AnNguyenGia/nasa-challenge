"""Configuration, durable SQL storage and serialized audit chain."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from sqlalchemy import Column, Float, Integer, MetaData, String, Table, Text, create_engine, event
from sqlalchemy.engine import Connection, Engine
from uuid6 import uuid7

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASTRO_", env_file=str(ROOT / ".env"))
    data_dir: Path = ROOT / "data"
    mode: str = "demo"
    db_key: str = ""
    db_key_file: Path | None = None
    jwt_secret: str = ""
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mission_epoch: str = "2026-11-03T00:00:00+00:00"
    token_minutes: int = 15
    sync_key: str = ""
    bind_host: str = "127.0.0.1"
    show_demo_data: bool = False
    simulator_enabled: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=ROOT / "configs/settings.yaml"),
            file_secret_settings,
        )


settings = Settings()


def now() -> str:
    return datetime.now(UTC).isoformat()


def uid() -> str:
    return str(uuid7())


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


metadata = MetaData()


def table(name: str, *columns: Column[Any]) -> Table:
    return Table(
        name,
        metadata,
        Column("id", String, primary_key=True),
        Column("created_at", String, nullable=False),
        Column("updated_at", String, nullable=False),
        Column("version", Integer, nullable=False, default=1),
        Column("deleted_at", String),
        *columns,
    )


jobs = table(
    "service_jobs",
    Column("kind", String, index=True),
    Column("priority", Integer),
    Column("status", String, index=True),
    Column("payload", Text),
    Column("result", Text),
    Column("error", Text),
)

users = table(
    "users",
    Column("username", String, unique=True),
    Column("password_hash", Text),
    Column("role", String),
    Column("crew_id", String),
    Column("failures", Integer, default=0),
    Column("locked_until", Float, default=0),
)
sessions = table(
    "sessions",
    Column("user_id", String, index=True),
    Column("refresh_hash", String),
    Column("expires", Float),
    Column("revoked", Integer, default=0),
)
crew = table(
    "crew_members",
    Column("name", String),
    Column("callsign", String),
    Column("mission_id", String),
    Column("is_demo", Integer, nullable=False, server_default="0"),
)
audit_log = table(
    "audit_log",
    Column("sequence", Integer, unique=True),
    Column("actor", String),
    Column("action", String),
    Column("resource", String),
    Column("previous_hash", String),
    Column("hash", String),
    Column("payload", Text),
)
alerts = table(
    "alerts",
    Column("crew_id", String, index=True),
    Column("metric", String),
    Column("level", String),
    Column("status", String),
    Column("rule_id", String),
    Column("source_type", String),
    Column("measurement_id", String),
    Column("payload", Text),
    Column("ack_by", String),
    Column("ack_at", String),
)
outbox = table(
    "sync_outbox",
    Column("kind", String),
    Column("priority", Integer, index=True),
    Column("status", String),
    Column("attempts", Integer, default=0),
    Column("offset", Integer, default=0),
    Column("checksum", String),
    Column("payload", Text),
    Column("last_error", String),
)
inference = table("inference_runs", Column("crew_id", String, index=True), Column("payload", Text))
records = table(
    "records",
    Column("kind", String, index=True),
    Column("crew_id", String, index=True),
    Column("source_type", String),
    Column("payload", Text),
)
heartbeats = Table(
    "service_heartbeats",
    metadata,
    Column("name", String, primary_key=True),
    Column("ts", Float),
    Column("detail", Text),
)
# Each named domain entity is independently versioned and migratable. JSON payloads are extension fields.
DOMAIN_TABLES = (
    "roles permissions missions environments mission_phases devices sensors calibrations data_sources "
    "waveform_segments lab_results cognitive_tests questionnaires sleep_sessions nutrition_logs food_items "
    "nutrition_targets environment_readings radiation_exposure_cumulative alert_rules ai_models model_versions "
    "explanations reports report_items sync_inbox sync_state alert_evaluations"
).split()
domains = {
    name: table(
        name, Column("crew_id", String, index=True), Column("source_type", String), Column("payload", Text)
    )
    for name in DOMAIN_TABLES
}


def base(**values: Any) -> dict[str, Any]:
    return {"id": uid(), "created_at": now(), "updated_at": now(), "version": 1, **values}


def make_engine(config: Settings) -> Engine:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    if config.db_key_file:
        config.db_key = config.db_key_file.read_text(encoding="utf-8").strip()
    kwargs: dict[str, Any] = {}
    if config.mode != "demo":
        if not config.db_key or len(config.jwt_secret) < 32:
            raise RuntimeError("Operational mode requires SQLCipher key and JWT secret (>=32 characters)")
        try:
            if len(bytes.fromhex(config.sync_key)) != 32:
                raise ValueError("Expected 256-bit AES key")
        except ValueError as exc:
            raise RuntimeError(
                "Operational mode requires ASTRO_SYNC_KEY with 64 hexadecimal characters"
            ) from exc
        from sqlcipher3 import dbapi2  # Fail closed: never silently substitute plaintext SQLite.

        kwargs["module"] = dbapi2
    eng = create_engine(
        f"sqlite:///{config.data_dir / 'astrohealth.db'}",
        hide_parameters=True,
        connect_args={"check_same_thread": False, "timeout": 15},
        **kwargs,
    )

    @event.listens_for(eng, "connect")
    def pragmas(db: Any, _: Any) -> None:
        cursor = db.cursor()
        if config.mode != "demo":
            passphrase = config.db_key.replace("'", "''")
            cursor.execute(f"PRAGMA key = '{passphrase}'")
            if not cursor.execute("PRAGMA cipher_version").fetchone():
                raise RuntimeError("SQLCipher is unavailable")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.close()

    return eng


engine = make_engine(settings)


@contextmanager
def transaction() -> Iterator[Connection]:
    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def audit(conn: Connection, actor: str, action: str, resource: str, payload: Any = None) -> None:
    row = conn.execute(audit_log.select().order_by(audit_log.c.sequence.desc()).limit(1)).mappings().first()
    previous = row["hash"] if row else "0" * 64
    item = base(
        sequence=(row["sequence"] + 1 if row else 1),
        actor=actor,
        action=action,
        resource=resource,
        previous_hash=previous,
        payload=canonical(payload),
    )
    item["hash"] = hashlib.sha256(canonical(item).encode()).hexdigest()
    conn.execute(audit_log.insert().values(**item))


def verify_audit(conn: Connection) -> bool:
    previous = "0" * 64
    sequence = 1
    for row in conn.execute(audit_log.select().order_by(audit_log.c.sequence)).mappings():
        item = dict(row)
        digest = item.pop("hash")
        # deleted_at is present in SQL rows but was omitted on append.
        item.pop("deleted_at")
        if item["previous_hash"] != previous or item["sequence"] != sequence:
            return False
        if hashlib.sha256(canonical(item).encode()).hexdigest() != digest:
            return False
        previous, sequence = digest, sequence + 1
    return True


def partition(conn: Connection, timestamp: str) -> str:
    month = datetime.fromisoformat(timestamp).strftime("%Y%m")
    name = f"measurements_{month}"
    if not re.fullmatch(r"measurements_\d{6}", name):
        raise ValueError("Invalid partition")
    conn.exec_driver_sql(f"""CREATE TABLE IF NOT EXISTS {name} (
      id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL,
      deleted_at TEXT, crew_id TEXT NOT NULL, metric TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL,
      ts_utc TEXT NOT NULL, ts_mission REAL NOT NULL, source_type TEXT NOT NULL, device_id TEXT,
      quality_score REAL NOT NULL, flags TEXT NOT NULL)""")
    conn.exec_driver_sql(
        f"CREATE INDEX IF NOT EXISTS ix_{name}_crew_metric_ts ON {name}(crew_id,metric,ts_utc)"
    )
    names = [
        r[0]
        for r in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'measurements_[0-9]*'"
        )
    ]
    conn.exec_driver_sql("DROP VIEW IF EXISTS measurements")
    conn.exec_driver_sql(
        "CREATE VIEW measurements AS " + " UNION ALL ".join(f"SELECT * FROM {n}" for n in names)
    )
    return name


def initialize() -> None:
    metadata.create_all(engine)
    with transaction() as conn:
        partition(conn, now())
    # Demo signing key is local and persistent; no fixed built-in credential.
    if not settings.jwt_secret:
        import secrets

        path = settings.data_dir / "demo-jwt.key"
        try:
            with path.open("x", encoding="ascii") as stream:
                stream.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        settings.jwt_secret = path.read_text(encoding="ascii")
    # Resolve/validate encryption before any alert transaction uses the outbox.
    from app.sync import encryption_key

    encryption_key()


def heartbeat(name: str, detail: str = "running") -> None:
    import time

    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO service_heartbeats VALUES(?,?,?) ON CONFLICT(name) "
            "DO UPDATE SET ts=excluded.ts,detail=excluded.detail",
            (name, time.time(), detail),
        )
