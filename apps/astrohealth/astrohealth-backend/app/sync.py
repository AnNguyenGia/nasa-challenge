"""Encrypted, compressed, resumable file-drop transport; no implicit external connections."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import zstandard
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text

from app.core import base, canonical, now, outbox, settings, transaction


def encryption_key() -> bytes:
    if settings.sync_key:
        return bytes.fromhex(settings.sync_key)
    if settings.mode != "demo":
        raise RuntimeError("ASTRO_SYNC_KEY is required")
    path = settings.data_dir / "demo-sync.key"
    try:
        with path.open("xb") as stream:
            stream.write(AESGCM.generate_key(bit_length=256))
    except FileExistsError:
        pass
    return path.read_bytes()


def enqueue(conn: Any, kind: str, payload: Any, priority: int = 2) -> str:
    packed = zstandard.ZstdCompressor().compress(canonical(payload).encode())
    nonce = secrets.token_bytes(12)
    identifier = base()["id"]
    ciphertext = nonce + AESGCM(encryption_key()).encrypt(nonce, packed, identifier.encode())
    row = base(
        id=identifier,
        kind=kind,
        priority=priority,
        status="pending",
        attempts=0,
        offset=0,
        checksum=hashlib.sha256(ciphertext).hexdigest(),
        payload=base64.b64encode(ciphertext).decode(),
    )
    conn.execute(outbox.insert().values(**row))
    return str(identifier)


class Transport(Protocol):
    def send(self, identifier: str, data: bytes, offset: int, checksum: str) -> int: ...


class FileDrop:
    """Idempotent receiver commits only after checksum verification and fsync."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def send(self, identifier: str, data: bytes, offset: int, checksum: str) -> int:
        target = self.directory / f"{identifier}.bundle"
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
                raise ValueError("Receiver checksum conflict")
            return len(data)
        partial = target.with_suffix(".partial")
        received = partial.stat().st_size if partial.exists() else 0
        if received > len(data) or partial.exists() and partial.read_bytes() != data[:received]:
            raise ValueError("Receiver partial payload conflict")
        with partial.open("ab") as stream:
            stream.write(data[received : received + 16384])
            stream.flush()
            os.fsync(stream.fileno())
        received = partial.stat().st_size
        if received == len(data):
            if hashlib.sha256(partial.read_bytes()).hexdigest() != checksum:
                raise ValueError("Checksum mismatch")
            partial.replace(target)
        return received


class Intermittent:
    def __init__(self, inner: Transport, online: bool = False) -> None:
        self.inner, self.online = inner, online

    def send(self, identifier: str, data: bytes, offset: int, checksum: str) -> int:
        if not self.online:
            raise ConnectionError("Simulated loss of contact")
        return self.inner.send(identifier, data, offset, checksum)


def sync_once(transport: Transport, at: datetime | None = None) -> None:
    """Send one eligible bundle with capped exponential retry after contact loss.

    A failed high-priority bundle must not block newly queued work while its
    retry timer is running. The timestamp argument is for deterministic tests.
    """
    current = at or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("Sync clock must be timezone-aware")
    # Single worker; do not hold a database writer lock during transport I/O.
    with transaction() as conn:
        row = (
            conn.execute(
                text("""SELECT * FROM sync_outbox WHERE deleted_at IS NULL AND (
                  status IN ('pending','sending') OR
                  (status='needs_retry' AND
                   julianday(updated_at) + MIN((1 << MIN(attempts,9)),300)/86400.0 <= julianday(:at))
                  ) ORDER BY priority,created_at LIMIT 1"""),
                {"at": current.astimezone(UTC).isoformat()},
            )
            .mappings()
            .first()
        )
        if not row:
            return
        conn.execute(outbox.update().where(outbox.c.id == row["id"]).values(status="sending"))
    try:
        data = base64.b64decode(row["payload"])
        offset = transport.send(row["id"], data, row["offset"], row["checksum"])
        if not isinstance(offset, int) or not row["offset"] < offset <= len(data):
            raise ValueError("Transport made no valid forward progress")
        values = {
            "offset": offset,
            "status": "sent" if offset == len(data) else "pending",
            "last_error": None,
            "attempts": 0,
        }
    except (OSError, ValueError) as exc:
        values = {
            "status": "needs_retry",
            "last_error": type(exc).__name__,
            "attempts": row["attempts"] + 1,
        }
    with transaction() as conn:
        conn.execute(
            outbox.update()
            .where(outbox.c.id == row["id"])
            .values(**values, updated_at=at.isoformat() if at else now())
        )
