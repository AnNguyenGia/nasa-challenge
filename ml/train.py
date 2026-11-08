"""Reproducible synthetic benchmark, not a clinically validated dataset."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score

FEATURES = ["heart_rate", "temperature", "sleep_hours", "mood"]

def train(root=None):
    root = Path(root or os.getenv("MODEL_DIR", "models"))
    rng = np.random.default_rng(42)
    mean, scale = [72, 36.7, 7.5, 3.5], [8, .2, .8, .5]
    training = rng.normal(mean, scale, (2000, 4))
    validation_normal = rng.normal(mean, scale, (400, 4))
    validation_unusual = rng.normal([110, 38, 4, 1.5], [12, .3, .8, .3], (100, 4))
    validation = np.concatenate([validation_normal, validation_unusual])
    labels = np.r_[np.zeros(400), np.ones(100)]
    model = IsolationForest(n_estimators=150, contamination=.05, random_state=42, n_jobs=1)
    model.fit(training)
    auc = float(roc_auc_score(labels, -model.decision_function(validation)))
    fpr = float(np.mean(model.predict(validation_normal) == -1))
    passed = auc >= .90 and fpr <= .12
    data_hash = hashlib.sha256(training.tobytes() + validation.tobytes()).hexdigest()
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = root / version
    folder.mkdir(parents=True, exist_ok=False)
    artifact = folder / "model.joblib"
    joblib.dump(model, artifact)
    metadata = {"version": version, "artifact": f"{version}/model.joblib",
                "features": FEATURES, "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "data_sha256": data_hash, "seed": 42,
                "metrics": {"roc_auc": auc, "false_positive_rate": fpr},
                "approved_by_gate": passed, "synthetic_only": True,
                "feature_mean": training.mean(axis=0).tolist(),
                "feature_std": training.std(axis=0).tolist()}
    (folder / "manifest.json").write_text(json.dumps(metadata, indent=2))
    if os.getenv("MLFLOW_TRACKING_URI"):
        import mlflow
        mlflow.set_experiment("space-health-synthetic")
        with mlflow.start_run():
            mlflow.log_params({"seed": 42, "dataset": "synthetic-v1", "data_sha256": data_hash})
            mlflow.log_metrics(metadata["metrics"])
            mlflow.log_artifacts(str(folder))
            mlflow.sklearn.log_model(model, "model", registered_model_name="space-health-demo")
    print(json.dumps(metadata, indent=2))
    if not passed:
        raise RuntimeError("Quality gate failed; model cannot be promoted")
    return metadata

if __name__ == "__main__":
    train()
