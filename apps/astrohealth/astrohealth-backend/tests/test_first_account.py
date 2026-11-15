"""The one-time local setup must create only the first demo account."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_first_account_setup(tmp_path: Path) -> None:
    script = """
from fastapi.testclient import TestClient
from app.api import app
from app.cli import seed
from app.core import crew, engine
from sqlalchemy import select

origin = {"Origin": "http://127.0.0.1:8000"}
account = {"username": "medical", "password": "local-demo-pass-123"}
with TestClient(app) as client:
    assert client.get("/api/v1/auth/setup-status").json() == {"required": True}
    assert client.post(
        "/api/v1/auth/self-register",
        json={"username": "early", "display_name": "Early", "password": "local-self-pass-123"},
        headers=origin,
    ).status_code == 409
    assert client.post("/api/v1/auth/setup", json=account, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/v1/auth/setup", json={**account, "password": "short"}, headers=origin).status_code == 422
    created = client.post("/api/v1/auth/setup", json=account, headers=origin)
    assert created.status_code == 201, created.text
    token = created.json()["access_token"]
    profile = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
    assert profile.json()["role"] == "Medical Officer"
    assert client.get("/api/v1/auth/setup-status").json() == {"required": False}
    assert client.post("/api/v1/auth/setup", json=account, headers=origin).status_code == 409
    assert client.post("/api/v1/auth/login", json=account).status_code == 200
    seed(0)
    with engine.connect() as conn:
        crew_id = conn.execute(select(crew.c.id).limit(1)).scalar_one()
    new_user = {
        "username": "astro2", "password": "astronaut-new-pass-123",
        "role": "Astronaut", "crew_id": crew_id,
    }
    med_auth = {"Authorization": "Bearer " + token}
    assert client.get("/api/v1/crew", headers=med_auth).json() == []
    simulated = {"crew_id": crew_id, "metric": "hr", "value": 78, "unit": "bpm", "source_type": "simulated"}
    assert client.post("/api/v1/measurements", json=[simulated], headers=med_auth).status_code == 200
    assert client.get("/api/v1/vitals/" + crew_id, headers=med_auth).json() == []
    assert client.get("/api/v1/alerts?crew_id=" + crew_id, headers=med_auth).json() == []
    real_profile = {"name": "Test Crew", "callsign": "TC-01", "mission_id": "TEST-MISSION"}
    assert client.post("/api/v1/crew", json=real_profile).status_code == 401
    created_crew = client.post("/api/v1/crew", json=real_profile, headers=med_auth)
    assert created_crew.status_code == 201, created_crew.text
    real_id = created_crew.json()["id"]
    assert [row["id"] for row in client.get("/api/v1/crew", headers=med_auth).json()] == [real_id]
    assert client.post("/api/v1/crew", json=real_profile, headers=med_auth).status_code == 409
    measured = {"crew_id": real_id, "metric": "hr", "value": 71, "unit": "bpm", "source_type": "measured"}
    assert client.post("/api/v1/measurements", json=[measured], headers=med_auth).status_code == 200
    assert client.get("/api/v1/vitals/" + real_id, headers=med_auth).json()[0]["value"] == 71
    history = client.get("/api/v1/vitals/" + real_id + "/history", headers=med_auth).json()
    assert [point["value"] for point in history["points"]] == [71]
    assert client.post("/api/v1/auth/register", json=new_user).status_code == 401
    assert client.post("/api/v1/auth/register", json={**new_user, "crew_id": None}, headers=med_auth).status_code == 422
    registered = client.post("/api/v1/auth/register", json=new_user, headers=med_auth)
    assert registered.status_code == 201, registered.text
    assert registered.json()["crew_id"] == crew_id
    assert "password" not in registered.json()
    assert client.post("/api/v1/auth/register", json=new_user, headers=med_auth).status_code == 409
    assert len(client.get("/api/v1/auth/accounts", headers=med_auth).json()) == 2
    astronaut = client.post(
        "/api/v1/auth/login", json={"username": new_user["username"], "password": new_user["password"]}
    ).json()["access_token"]
    astro_auth = {"Authorization": "Bearer " + astronaut}
    assert client.post("/api/v1/crew", json={**real_profile, "callsign": "TC-02"}, headers=astro_auth).status_code == 403
    assert client.post("/api/v1/auth/register", json={**new_user, "username": "astro3"}, headers=astro_auth).status_code == 403
    assert client.get("/api/v1/auth/accounts", headers=astro_auth).status_code == 403
    self_data = {
        "username": "newpilot", "display_name": "Pilot Demo", "password": "local-self-pass-123",
    }
    assert client.post("/api/v1/auth/self-register", json=self_data).status_code == 403
    signed_up = client.post("/api/v1/auth/self-register", json=self_data, headers=origin)
    assert signed_up.status_code == 201, signed_up.text
    own_auth = {"Authorization": "Bearer " + signed_up.json()["access_token"]}
    own_profile = client.get("/api/v1/auth/me", headers=own_auth).json()
    assert own_profile["role"] == "Astronaut"
    own_crew = client.get("/api/v1/crew", headers=own_auth).json()
    assert len(own_crew) == 1 and own_crew[0]["id"] == own_profile["crew_id"]
    assert own_crew[0]["mission_id"] == "LOCAL-DEMO"
    assert client.get("/api/v1/vitals/" + crew_id, headers=own_auth).status_code == 403
    assert client.get("/api/v1/vitals/" + own_profile["crew_id"], headers=own_auth).json() == []
    assert client.post("/api/v1/auth/self-register", json={**self_data, "username": "NEWPILOT"}, headers=origin).status_code == 409
    assert client.post("/api/v1/auth/login", json={"username": self_data["username"], "password": self_data["password"]}).status_code == 200
    changed = client.post(
        "/api/v1/auth/password",
        json={"old_password": account["password"], "new_password": "new-local-pass-456"},
        headers={"Authorization": "Bearer " + token},
    )
    assert changed.status_code == 200, changed.text
    assert client.post("/api/v1/auth/login", json=account).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"username": account["username"], "password": "new-local-pass-456"},
    ).status_code == 200
"""
    environment = {
        **os.environ,
        "ASTRO_DATA_DIR": str(tmp_path),
        "ASTRO_MODE": "demo",
        "ASTRO_SHOW_DEMO_DATA": "0",
        "ASTRO_SIMULATOR_ENABLED": "0",
        "ASTRO_JWT_SECRET": "first-account-test-only-secret-32-chars",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
