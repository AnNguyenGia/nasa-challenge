"""Authenticated load probe. Supply ASTRO_LOAD_USERNAME/PASSWORD; never a built-in credential."""

import os

from locust import HttpUser, between, task


class ConsoleUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self):
        result = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": os.environ["ASTRO_LOAD_USERNAME"],
                "password": os.environ["ASTRO_LOAD_PASSWORD"],
            },
        ).json()
        self.client.headers.update(Authorization="Bearer " + result["access_token"])
        self.crew = self.client.get("/api/v1/crew").json()[0]["id"]

    @task
    def vitals(self):
        self.client.get("/api/v1/vitals/" + self.crew, name="/api/v1/vitals/{crew}")
