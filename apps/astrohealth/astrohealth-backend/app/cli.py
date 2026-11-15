"""Administrative CLI and supervised process entry points."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import math
import os
import random
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from app.core import (
    ROOT,
    audit,
    base,
    canonical,
    crew,
    engine,
    heartbeat,
    initialize,
    partition,
    records,
    settings,
    transaction,
    users,
)
from app.security import hasher
from app.telemetry import Measurement, RuleState, evaluate_once, ingest

log = logging.getLogger("astrohealth")


def seed(days: int = 30) -> None:
    if settings.mode != "demo":
        raise RuntimeError("Seeding is disabled outside demo mode")
    rng = random.Random(31)
    names = ["Nguyễn Minh Quân", "Linh Nguyễn", "Minh Trần", "An Phạm", "Hà Lê", "Duy Hoàng"]
    with transaction() as conn:
        if conn.execute(select(crew.c.id)).first():
            print("Crew already exists; seed skipped (idempotent)")
            return
        members = [
            base(name=name, callsign=call, mission_id="ORBITAL-03", is_demo=1)
            for name, call in zip(names, ["CDR", "PLT", "MED", "ENG", "SCI", "MSP"], strict=True)
        ]
        conn.execute(crew.insert(), members)
        end = datetime.now(UTC)
        # Hourly history, explicitly not a 1 Hz 30-day recording.
        buckets: dict[str, list[dict[str, Any]]] = {}
        for i, member in enumerate(members):
            for hour in range(days * 24):
                ts = end - timedelta(hours=days * 24 - hour)
                for metric, value, unit in [
                    ("hr", 77 + i + 8 * math.sin(hour * 0.25) + rng.uniform(-3, 3), "bpm"),
                    ("spo2", 98 + rng.uniform(-0.5, 0.5), "%"),
                    ("rr", 16 + rng.uniform(-2, 2), "/min"),
                    ("temp", 36.7 + rng.uniform(-0.2, 0.2), "degC"),
                    ("hrv", 46 + rng.uniform(-6, 6), "ms"),
                    ("sbp", 118 + rng.uniform(-5, 5), "mmHg"),
                    ("dbp", 76 + rng.uniform(-4, 4), "mmHg"),
                ]:
                    row = base(
                        crew_id=member["id"],
                        metric=metric,
                        value=round(value, 1),
                        unit=unit,
                        ts_utc=ts.isoformat(),
                        ts_mission=(ts - datetime.fromisoformat(settings.mission_epoch)).total_seconds(),
                        source_type="simulated",
                        device_id="SIMULATOR",
                        quality_score=1.0,
                        flags="[]",
                    )
                    buckets.setdefault(ts.strftime("%Y%m"), []).append(row)
            for day in range(days):
                for kind, payload in [
                    ("sleep", {"hours": round(rng.uniform(6, 8.5), 1)}),
                    ("nutrition", {"calories": rng.randint(2000, 2700), "water": rng.randint(1800, 3000)}),
                    ("environment", {"co2": rng.randint(400, 900), "temperature": 22.4}),
                ]:
                    conn.execute(
                        records.insert().values(
                            **base(
                                created_at=(end - timedelta(days=day)).isoformat(),
                                kind=kind,
                                crew_id=member["id"],
                                source_type="simulated",
                                payload=canonical(payload),
                            )
                        )
                    )
        for rows in buckets.values():
            name = partition(conn, rows[0]["ts_utc"])
            conn.execute(
                text(
                    f"INSERT INTO {name} ({','.join(rows[0])}) VALUES ({','.join(':' + k for k in rows[0])})"
                ),
                rows,
            )
        audit(conn, "seed", "demo_seed", "crew", {"crew": 6, "days": days, "cadence": "hourly"})
    print(f"Seeded six simulated crew members, {days} days (hourly history)")


def bootstrap(username: str, role: str, crew_id: str | None = None) -> None:
    password = os.environ.get("ASTRO_BOOTSTRAP_PASSWORD") or getpass.getpass("New local account password: ")
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    with transaction() as conn:
        if role == "Astronaut" and not conn.execute(select(crew.c.id).where(crew.c.id == crew_id)).first():
            raise ValueError("Astronaut requires an existing --crew-id")
        conn.execute(
            users.insert().values(
                **base(
                    username=username,
                    password_hash=hasher.hash(password),
                    role=role,
                    crew_id=crew_id,
                    failures=0,
                    locked_until=0,
                )
            )
        )
        audit(conn, "local-cli", "user_created", username, {"role": role})
    print("Local account created (password not logged)")


async def mqtt_loop() -> None:
    import aiomqtt

    while True:
        try:
            async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as client:
                await client.subscribe("astrohealth/measurements")
                heartbeat("ingestion-service", "mqtt subscribed")
                async for message in client.messages:
                    try:
                        payload = json.loads(bytes(message.payload))
                        ingest([Measurement.model_validate(payload)], "mqtt-adapter")
                    except (ValueError, TypeError):
                        log.error(canonical({"event": "invalid_sensor_packet"}))
                    heartbeat("ingestion-service", "mqtt subscribed")
        except aiomqtt.MqttError:
            heartbeat("ingestion-service", "mqtt disconnected; retrying")
            await asyncio.sleep(3)


def simulator_tick() -> None:
    if settings.mode != "demo":
        raise RuntimeError("Simulator is forbidden outside demo mode")
    with engine.connect() as conn:
        ids = list(conn.execute(select(crew.c.id).where(crew.c.is_demo == 1)).scalars())
    data = []
    for i, identifier in enumerate(ids):
        for metric, value, unit in [
            ("hr", 78 + i + math.sin(time.time() / 15) * 4, "bpm"),
            ("spo2", 98, "%"),
            ("rr", 16, "/min"),
            ("temp", 36.7, "degC"),
            ("hrv", 46, "ms"),
            ("sbp", 118, "mmHg"),
            ("dbp", 76, "mmHg"),
        ]:
            data.append(
                Measurement(
                    crew_id=identifier,
                    metric=metric,
                    value=round(value, 1),
                    unit=unit,
                    source_type="simulated",
                    device_id="SIMULATOR",
                )
            )
    if data:
        ingest(data, "simulator")


def backup() -> Path:
    # DBAPI backup uses a consistent snapshot, including WAL pages, and preserves SQLCipher driver.
    directory = settings.data_dir / "backups"
    directory.mkdir(exist_ok=True)
    target = directory / (datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + ".db")
    raw = engine.raw_connection()
    try:
        if settings.mode != "demo":
            assert raw.driver_connection is not None
            cursor = raw.driver_connection.cursor()
            escaped_path = str(target).replace("'", "''")
            escaped_key = settings.db_key.replace("'", "''")
            cursor.execute(f"ATTACH DATABASE '{escaped_path}' AS encrypted_backup KEY '{escaped_key}'")
            cursor.execute("SELECT sqlcipher_export('encrypted_backup')")
            if cursor.execute("PRAGMA encrypted_backup.integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Encrypted backup integrity failure")
            raw.commit()
            cursor.execute("DETACH DATABASE encrypted_backup")
            cursor.close()
        else:
            import sqlite3

            with sqlite3.connect(target) as destination:
                assert raw.driver_connection is not None
                raw.driver_connection.backup(destination)
                if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup integrity failure")
    finally:
        raw.close()
    # Only files generated in this backup directory are rotated.
    for old in sorted(directory.glob("*.db"), reverse=True)[7:]:
        old.unlink()
    return target


def worker(name: str) -> None:
    states: dict[tuple[str, str, str], RuleState] = {}
    cursor = ""
    last_backup = 0.0
    if name in {"ai-inference-service", "xai-service", "report-service"}:
        from app.core import jobs

        with transaction() as conn:
            conn.execute(
                jobs.update().where(jobs.c.kind == name, jobs.c.status == "running").values(status="pending")
            )
    if name == "ingestion-service" and not (settings.mode == "demo" and settings.simulator_enabled):
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(mqtt_loop())
        return
    while True:
        if name == "ingestion-service":
            simulator_tick()
        elif name == "alert-engine":
            cursor = evaluate_once(states, cursor)
        elif name == "sync-service":
            from app.sync import FileDrop, Intermittent, sync_once

            transport = Intermittent(
                FileDrop(settings.data_dir / "ground-simulator"),
                online=(settings.data_dir / "sim-contact-enabled").exists(),
            )
            sync_once(transport)
        elif name in {"ai-inference-service", "xai-service", "report-service"}:
            from app.jobs import run_once

            run_once(name)
            if name == "ai-inference-service":
                from app.ml import release_idle

                release_idle()
        elif name == "scheduler" and time.time() - last_backup > 3600:
            with engine.connect() as conn:
                if conn.exec_driver_sql("PRAGMA quick_check").scalar() != "ok":
                    raise RuntimeError("Database integrity check failed")
            backup()
            last_backup = time.time()
        heartbeat(name)
        time.sleep(0.1 if name == "alert-engine" else 1)


def supervise() -> None:
    commands = {
        "api-gateway": [
            sys.executable,
            "-m",
            "uvicorn",
            "app.api:app",
            "--host",
            settings.bind_host,
            "--port",
            "8000",
        ],
        **{
            name: [sys.executable, "-m", "app.cli", "worker", name]
            for name in [
                "ingestion-service",
                "alert-engine",
                "ai-inference-service",
                "xai-service",
                "report-service",
                "sync-service",
                "scheduler",
            ]
        },
    }
    children: dict[str, subprocess.Popen[Any]] = {}
    stopped = False

    def stop(*_: Any) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not stopped:
            for name, command in commands.items():
                process = children.get(name)
                if process is None or process.poll() is not None:
                    if process:
                        log.warning(
                            canonical(
                                {"service": name, "event": "watchdog_restart", "exit": process.returncode}
                            )
                        )
                    children[name] = subprocess.Popen(command, cwd=ROOT)
            time.sleep(1)
    finally:
        for process in children.values():
            process.terminate()
        for process in children.values():
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    seed_parser = sub.add_parser("seed")
    seed_parser.add_argument("--days", type=int, default=30)
    account = sub.add_parser("bootstrap")
    account.add_argument("username")
    account.add_argument(
        "--role",
        choices=["Admin", "Medical Officer", "Astronaut", "Ground Control Operator"],
        default="Medical Officer",
    )
    account.add_argument("--crew-id")
    worker_parser = sub.add_parser("worker")
    worker_parser.add_argument(
        "name",
        choices=[
            "ingestion-service",
            "alert-engine",
            "ai-inference-service",
            "xai-service",
            "report-service",
            "sync-service",
            "scheduler",
        ],
    )
    sub.add_parser("serve")
    sub.add_parser("backup")
    args = parser.parse_args()
    initialize()
    if args.command == "seed":
        seed(args.days)
    elif args.command == "bootstrap":
        bootstrap(args.username, args.role, args.crew_id)
    elif args.command == "worker":
        worker(args.name)
    elif args.command == "serve":
        supervise()
    elif args.command == "backup":
        print(backup())


if __name__ == "__main__":
    main()
