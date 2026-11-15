"""Hash-checked local ONNX registry with explicit synthetic-model provenance."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Protocol

import numpy as np
import onnxruntime as ort
import yaml
from sqlalchemy import select

from app.core import ROOT, audit, base, canonical, domains, engine, inference, settings, transaction


class ModelContract(Protocol):
    def load(self) -> None: ...
    def preprocess(self, data: list[float]) -> np.ndarray[Any, Any]: ...
    def predict(self, data: list[float]) -> list[float]: ...
    def explain(self, data: list[float]) -> dict[str, Any]: ...
    def metadata(self) -> dict[str, Any]: ...


class ONNXModel:
    def __init__(self, manifest: dict[str, Any]) -> None:
        self.manifest = manifest
        self.session: ort.InferenceSession | None = None
        self.used = 0.0

    def load(self) -> None:
        path = ROOT / "models_registry" / self.manifest["checkpoint"]
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Model exceeds 64 MiB edge budget")
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.manifest["sha256"]:
            raise ValueError("Checkpoint integrity mismatch")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )

    def preprocess(self, data: list[float]) -> np.ndarray[Any, Any]:
        array = np.array([data], dtype=np.float32)
        if array.shape != (1, self.manifest["input_features"]) or not np.isfinite(array).all():
            raise ValueError("Input shape or finite-value contract failed")
        return array

    def predict(self, data: list[float]) -> list[float]:
        if self.session is None:
            self.load()
        assert self.session is not None
        self.used = time.monotonic()
        result = self.session.run(None, {"features": self.preprocess(data)})[0]
        return list(result.flatten().astype(float))

    def explain(self, data: list[float]) -> dict[str, Any]:
        # Exact attribution for these linear demonstration models. Do not call this SHAP/IG.
        return {
            "method": "exact_linear_zero_baseline",
            "baseline": [0] * len(data),
            "attribution": [v * w for v, w in zip(data, self.manifest["weights"], strict=True)],
            "uncertainty": None,
            "limitation": "Synthetic linear demo; no clinical validation",
        }

    def metadata(self) -> dict[str, Any]:
        return self.manifest


_cache: dict[str, ONNXModel] = {}
_lock = threading.Lock()


def manifests() -> list[dict[str, Any]]:
    path = ROOT / "models_registry/manifest.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["models"] if path.exists() else []


def activated_versions() -> dict[str, dict[str, Any]]:
    """Return the latest approved activation record for each model ID."""
    table = domains["model_versions"]
    with engine.connect() as conn:
        rows = conn.execute(
            select(table.c.payload)
            .where(table.c.deleted_at.is_(None))
            .order_by(table.c.created_at.desc(), table.c.id.desc())
        ).scalars()
        records = [json.loads(payload) for payload in rows]
    active: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("status") == "active":
            active.setdefault(str(record["model_id"]), record)
    return active


def active_manifest(model_id: str) -> dict[str, Any]:
    available = [model for model in manifests() if model["id"] == model_id]
    record = activated_versions().get(model_id)
    if record:
        selected = next(
            (
                model
                for model in available
                if model["version"] == record["version"] and model.get("sha256") == record["hash"]
            ),
            None,
        )
        if selected is None or not selected.get("checkpoint"):
            raise ValueError("Activated checkpoint is missing or its hash changed")
        return selected
    if settings.mode != "demo":
        raise ValueError("No activated model version")
    selected = next((model for model in available if model.get("checkpoint")), None)
    if selected is None:
        raise ValueError("Insufficient conditions for inference: checkpoint unavailable")
    return selected


def run(
    model_id: str, crew_id: str, features: list[float], actor: str, run_id: str | None = None
) -> dict[str, Any]:
    if run_id:
        with engine.connect() as conn:
            existing = conn.execute(select(inference).where(inference.c.id == run_id)).mappings().first()
        if existing:
            return {"id": run_id, **json.loads(existing["payload"])}
    manifest = active_manifest(model_id)
    if settings.mode != "demo" and manifest["model_is_placeholder"]:
        raise ValueError("Placeholder models are disabled in operational mode")
    start = time.perf_counter()
    with _lock:
        for key in list(_cache):
            if time.monotonic() - _cache[key].used > 60:
                del _cache[key]
        cache_key = f"{model_id}:{manifest['version']}:{manifest['sha256']}"
        model = _cache.setdefault(cache_key, ONNXModel(manifest))
        scores = model.predict(features)
    result = {
        "model_id": model_id,
        "version": manifest["version"],
        "checkpoint_hash": manifest["sha256"],
        "scores": scores,
        "input": features,
        "quality": "caller_supplied_unverified",
        "elapsed_ms": (time.perf_counter() - start) * 1000,
        "uncertainty": None,
        "model_is_placeholder": manifest["model_is_placeholder"],
        "source_type": "model_inferred",
    }
    row = base(crew_id=crew_id, payload=canonical(result))
    if run_id:
        row["id"] = run_id
    with transaction() as conn:
        conn.execute(inference.insert().values(**row))
        audit(conn, actor, "inference", row["id"])
    return {"id": row["id"], **result}


def release_idle() -> None:
    with _lock:
        for key in list(_cache):
            if time.monotonic() - _cache[key].used > 60:
                del _cache[key]


def explain_run(identifier: str) -> dict[str, Any]:
    target = domains["explanations"]
    with engine.connect() as conn:
        cached = conn.execute(select(target).where(target.c.id == identifier)).mappings().first()
        row = conn.execute(select(inference).where(inference.c.id == identifier)).mappings().one()
    result: dict[str, Any] = json.loads(row["payload"])
    if cached:
        explanation = json.loads(cached["payload"])
    else:
        manifest = next(
            (
                model
                for model in manifests()
                if model["id"] == result["model_id"]
                and model["version"] == result["version"]
                and model.get("sha256") == result["checkpoint_hash"]
            ),
            None,
        )
        if manifest is None:
            raise ValueError("Explanation checkpoint does not match inference checkpoint")
        explanation = ONNXModel(manifest).explain(result["input"])
        with transaction() as conn:
            conn.execute(
                target.insert().values(
                    **base(
                        id=identifier,
                        crew_id=row["crew_id"],
                        source_type="model_inferred",
                        payload=canonical(explanation),
                    )
                )
            )
    return {"id": identifier, **result, "explanation": explanation}
