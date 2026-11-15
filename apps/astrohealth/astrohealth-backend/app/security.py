"""Local authentication with rotating, revocable sessions and crew-scoped authorization."""

from __future__ import annotations

import hashlib
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core import audit, base, engine, sessions, settings, transaction, users

hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)


def issue(conn: Any, user: Any, session_id: str | None = None) -> dict[str, str]:
    refresh = secrets.token_urlsafe(48)
    expires = time.time() + 86400
    if session_id:
        conn.execute(
            sessions.update()
            .where(sessions.c.id == session_id)
            .values(refresh_hash=hashlib.sha256(refresh.encode()).hexdigest(), expires=expires)
        )
    else:
        row = base(
            user_id=user["id"],
            refresh_hash=hashlib.sha256(refresh.encode()).hexdigest(),
            expires=expires,
            revoked=0,
        )
        session_id = row["id"]
        conn.execute(sessions.insert().values(**row))
    token = jwt.encode(
        {
            "sub": user["id"],
            "sid": session_id,
            "iss": "astrohealth-local",
            "aud": "astrohealth",
            "exp": datetime.now(UTC) + timedelta(minutes=settings.token_minutes),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"access_token": token, "refresh_token": refresh, "token_type": "bearer"}


def login(username: str, password: str) -> dict[str, str]:
    # Commit failed-login counters before returning errors.
    error = None
    result: dict[str, str] = {}
    with transaction() as conn:
        user = conn.execute(select(users).where(users.c.username == username)).mappings().first()
        if not user:
            hasher.hash(password)  # Avoid a cheap username-enumeration path.
            error = (401, "Invalid credentials")
        elif user["locked_until"] > time.time():
            error = (429, "Account temporarily locked")
        else:
            valid = False
            try:
                valid = hasher.verify(user["password_hash"], password)
            except VerificationError:
                pass
            if not valid:
                failures = user["failures"] + 1
                conn.execute(
                    users.update()
                    .where(users.c.id == user["id"])
                    .values(failures=failures, locked_until=time.time() + 300 if failures >= 5 else 0)
                )
                audit(conn, user["id"], "login_failed", "auth")
                error = (401, "Invalid credentials")
            else:
                conn.execute(
                    users.update().where(users.c.id == user["id"]).values(failures=0, locked_until=0)
                )
                result = issue(conn, user)
                audit(conn, user["id"], "login", "auth")
    if error:
        raise HTTPException(*error)
    return result


def authenticate(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer="astrohealth-local",
            audience="astrohealth",
        )
        with engine.connect() as conn:
            session = conn.execute(select(sessions).where(sessions.c.id == claims["sid"])).mappings().first()
            user = conn.execute(select(users).where(users.c.id == claims["sub"])).mappings().first()
        if (
            not session
            or session["revoked"]
            or session["expires"] < time.time()
            or not user
            or user["deleted_at"]
        ):
            raise ValueError("Expired or revoked session")
        return {**user, "session_id": session["id"]}
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(401, "Invalid or revoked token") from exc


def current(auth: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any]:
    if not auth:
        raise HTTPException(401, "Login required")
    return authenticate(auth.credentials)


def scope(user: dict[str, Any], crew_id: str) -> None:
    if user["role"] in {"Admin", "Medical Officer"}:
        return
    if user["role"] == "Astronaut" and user["crew_id"] == crew_id:
        return
    raise HTTPException(403, "Crew detail access denied")


def medical(user: dict[str, Any]) -> None:
    if user["role"] not in {"Medical Officer", "Admin"}:
        raise HTTPException(403, "Medical Officer/Admin required")
