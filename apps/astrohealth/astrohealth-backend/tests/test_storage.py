from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core import Settings, crew, engine, make_engine, settings
from app.telemetry import Measurement, RuleState, ingest, recent_history


def test_gap_does_not_count_as_continuous_exposure():
    rule = {"direction": "above", "threshold": 120, "clear": 110, "duration_seconds": 3, "min_quality": 0.8}
    state = RuleState()
    assert state.step(rule, 130, 0, 1) == "pending"
    assert state.step(rule, 130, 100, 1) == "pending"
    assert state.step(rule, 130, 101, 1) == "pending"
    assert state.step(rule, 130, 103, 1) == "triggered"
    assert state.step(rule, 130, 102, 1) == "insufficient_data"


def test_history_limit_keeps_newest_samples_in_time_order(client):
    with engine.connect() as conn:
        crew_id = conn.execute(select(crew.c.id).limit(1)).scalar_one()
    start = datetime.now(UTC)
    ingest(
        [
            Measurement(
                crew_id=crew_id,
                metric="radiation",
                value=float(value),
                unit="mSv/h",
                ts_utc=start + timedelta(seconds=value),
                source_type="simulated",
            )
            for value in (1, 2, 3)
        ],
        "test",
    )
    with engine.connect() as conn:
        rows = recent_history(
            conn, crew_id, "radiation", (start - timedelta(seconds=1)).isoformat(), limit=2
        )
    assert [row["value"] for row in rows] == [2, 3]


def test_operational_mode_refuses_missing_keys(tmp_path):
    with pytest.raises(RuntimeError, match="requires SQLCipher"):
        make_engine(Settings(mode="operational", data_dir=tmp_path, jwt_secret="", db_key=""))


def test_waveform_checksum_and_duckdb(client, token):
    auth = token()
    crew_id = client.get("/api/v1/crew", headers=auth).json()[0]["id"]
    payload = {
        "crew_id": crew_id,
        "kind": "ECG",
        "sample_rate": 100,
        "start_utc": datetime.now(UTC).isoformat(),
        "source_type": "simulated",
        "quality_score": 0.9,
        "samples": [0, 0.5, 1, 0.5, 0] * 100,
    }
    result = client.post("/api/v1/waveforms", headers=auth, json=payload)
    assert result.status_code == 200, result.text
    identifier = result.json()["id"]
    read = client.get("/api/v1/waveforms/" + identifier, headers=auth)
    assert read.status_code == 200, read.text
    assert read.json()["stats"]["count"] == 500 and read.json()["stats"]["max"] == 1
    assert read.json()["source_type"] == "simulated"
    assert client.get("/api/v1/waveforms/" + identifier, headers=token("ground")).status_code == 403


def test_waveform_rejects_unknown_crew_and_removes_unindexed_file(client, monkeypatch):
    from contextlib import contextmanager

    from app import waveforms

    directory = settings.data_dir / "waveforms"
    before = set(directory.glob("*.parquet")) if directory.exists() else set()
    sample = waveforms.Waveform(
        crew_id="not-a-crew",
        kind="ECG",
        sample_rate=100,
        start_utc=datetime.now(UTC),
        source_type="simulated",
        quality_score=1,
        samples=[0, 1, 0],
    )
    with pytest.raises(ValueError, match="Unknown crew"):
        waveforms.archive(sample, "test")
    assert set(directory.glob("*.parquet")) == before

    with engine.connect() as conn:
        sample.crew_id = conn.execute(select(crew.c.id).limit(1)).scalar_one()

    @contextmanager
    def unavailable():
        raise RuntimeError("Database unavailable")
        yield

    monkeypatch.setattr(waveforms, "transaction", unavailable)
    with pytest.raises(RuntimeError, match="Database unavailable"):
        waveforms.archive(sample, "test")
    assert set(directory.glob("*.parquet")) == before


def test_encrypted_waveform_wrapper(client, token, monkeypatch):
    from app.waveforms import Waveform, archive, read

    auth = token()
    crew_id = client.get("/api/v1/crew", headers=auth).json()[0]["id"]
    monkeypatch.setattr(settings, "mode", "operational")
    monkeypatch.setattr(settings, "sync_key", "11" * 32)
    record = archive(
        Waveform(
            crew_id=crew_id,
            kind="EEG",
            sample_rate=100,
            start_utc=datetime.now(UTC),
            source_type="simulated",
            quality_score=1,
            samples=[0, 0.5, 1],
        ),
        "test",
    )
    stored = (settings.data_dir / "waveforms" / record["file"]).read_bytes()
    assert not stored.startswith(b"PAR1")
    assert read(record["id"])[1]["stats"]["count"] == 3


def test_backup_restorable(client):
    import sqlite3

    from app.cli import backup

    target = backup()
    with sqlite3.connect(target) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT count(*) FROM crew_members").fetchone()[0] == 6


def test_offline_docs_and_model_permissions(client, token):
    docs = client.get("/docs")
    assert docs.status_code == 200 and "/vendor/swagger-ui-bundle.js" in docs.text
    assert "cdn.jsdelivr.net" not in docs.text
    assert client.get("/design").status_code == 200
    assert client.get("/api/v1/health").json()["audit_chain_valid"]
    assert (
        client.put(
            "/api/v1/ai/models/anomaly-demo/activate", json={"version": "synthetic-1"}, headers=token("astro")
        ).status_code
        == 403
    )


def test_wal_durability_configuration(client):
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA synchronous").scalar() == 2
