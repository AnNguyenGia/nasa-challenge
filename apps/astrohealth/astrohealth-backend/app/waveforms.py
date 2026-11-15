"""Atomic waveform archive. AES-GCM wraps Parquet files outside explicit demo mode."""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core import audit, base, canonical, crew, domains, engine, settings, transaction, uid
from app.sync import encryption_key
from app.telemetry import Source


class Waveform(BaseModel):
    crew_id: str
    kind: Literal["ECG", "EEG"]
    sample_rate: int = Field(ge=1, le=2000)
    start_utc: datetime
    source_type: Source
    quality_score: float = Field(ge=0, le=1)
    samples: list[float] = Field(min_length=1, max_length=100000)


def archive(data: Waveform, actor: str) -> dict[str, Any]:
    if data.start_utc.tzinfo is None or not all(__import__("math").isfinite(x) for x in data.samples):
        raise ValueError("Timezone and finite samples are required")
    if data.start_utc.timestamp() > datetime.now(UTC).timestamp() + 300:
        raise ValueError("Waveform clock offset exceeds +300 seconds")
    with engine.connect() as conn:
        known = conn.execute(
            select(crew.c.id).where(crew.c.id == data.crew_id, crew.c.deleted_at.is_(None))
        ).first()
    if known is None:
        raise ValueError("Unknown crew member")
    identifier = uid()
    directory = settings.data_dir / "waveforms"
    directory.mkdir(exist_ok=True)
    table = pa.table({"sample": pa.array(data.samples, type=pa.float32())})
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="zstd")
    content = buffer.getvalue()
    encrypted = settings.mode != "demo"
    if encrypted:
        nonce = secrets.token_bytes(12)
        content = nonce + AESGCM(encryption_key()).encrypt(nonce, content, identifier.encode())
    name = identifier + (".parquet.aes" if encrypted else ".parquet")
    temporary = directory / (name + ".partial")
    with temporary.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    final = directory / name
    temporary.replace(final)
    metadata = {
        "kind": data.kind,
        "sample_rate": data.sample_rate,
        "sample_count": len(data.samples),
        "start_utc": data.start_utc.astimezone(UTC).isoformat(),
        "end_utc": (data.start_utc + timedelta(seconds=len(data.samples) / data.sample_rate))
        .astimezone(UTC)
        .isoformat(),
        "file": name,
        "checksum": hashlib.sha256(content).hexdigest(),
        "encrypted": encrypted,
        "quality_score": data.quality_score,
    }
    try:
        with transaction() as conn:
            conn.execute(
                domains["waveform_segments"]
                .insert()
                .values(
                    **base(
                        id=identifier,
                        crew_id=data.crew_id,
                        source_type=data.source_type,
                        payload=canonical(metadata),
                    )
                )
            )
            audit(conn, actor, "waveform_archived", identifier)
    except BaseException:
        final.unlink(missing_ok=True)
        raise
    return {"id": identifier, **metadata}


def read(identifier: str) -> tuple[str, dict[str, Any]]:
    t = domains["waveform_segments"]
    with engine.connect() as conn:
        row = conn.execute(select(t).where(t.c.id == identifier)).mappings().first()
    if not row:
        raise ValueError("Unknown waveform")
    metadata = json.loads(row["payload"])
    name = metadata["file"]
    if name not in {f"{identifier}.parquet", f"{identifier}.parquet.aes"} or os.path.basename(name) != name:
        raise ValueError("Invalid waveform archive path")
    content = (settings.data_dir / "waveforms" / name).read_bytes()
    if hashlib.sha256(content).hexdigest() != metadata["checksum"]:
        raise ValueError("Waveform checksum mismatch")
    if metadata["encrypted"]:
        content = AESGCM(encryption_key()).decrypt(content[:12], content[12:], identifier.encode())
    table = pq.read_table(io.BytesIO(content))
    with duckdb.connect(":memory:") as db:
        db.register("signal", table)
        stats = db.execute("SELECT min(sample),max(sample),avg(sample),count(*) FROM signal").fetchone()
        assert stats is not None
    samples = table.column("sample").to_pylist()
    stride = max(1, len(samples) // 2000)
    return row["crew_id"], {
        **metadata,
        "source_type": row["source_type"],
        "samples": samples[::stride][:2000],
        "stride": stride,
        "stats": {"min": stats[0], "max": stats[1], "mean": stats[2], "count": stats[3]},
    }
