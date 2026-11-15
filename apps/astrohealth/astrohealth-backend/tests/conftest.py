import os
import tempfile
import threading
import time

os.environ["ASTRO_DATA_DIR"] = tempfile.mkdtemp(prefix="astro-test-")
os.environ["ASTRO_MODE"] = "demo"
os.environ["ASTRO_SHOW_DEMO_DATA"] = "1"
os.environ["ASTRO_SIMULATOR_ENABLED"] = "0"
os.environ["ASTRO_JWT_SECRET"] = "tests-only-secret-32-characters-long"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import app
from app.cli import seed
from app.core import base, crew, initialize, transaction, users
from app.jobs import run_once
from app.security import hasher


@pytest.fixture(scope="session")
def client():
    initialize()
    seed(1)
    with transaction() as conn:
        ids = list(conn.execute(select(crew.c.id)).scalars())
        for name, role, crew_id in [
            ("med", "Medical Officer", None),
            ("med2", "Medical Officer", None),
            ("astro", "Astronaut", ids[0]),
            ("ground", "Ground Control Operator", None),
        ]:
            conn.execute(
                users.insert().values(
                    **base(
                        username=name,
                        password_hash=hasher.hash("testing-pass-123"),
                        role=role,
                        crew_id=crew_id,
                        failures=0,
                        locked_until=0,
                    )
                )
            )
    stop = threading.Event()

    def tasks():
        while not stop.is_set():
            for kind in ["ai-inference-service", "xai-service", "report-service"]:
                run_once(kind)
            time.sleep(0.02)

    thread = threading.Thread(target=tasks, daemon=True)
    thread.start()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        stop.set()
        thread.join(3)


@pytest.fixture
def token(client):
    def login(name="med"):
        response = client.post("/api/v1/auth/login", json={"username": name, "password": "testing-pass-123"})
        assert response.status_code == 200, response.text
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    return login
