"""Local inference. Only load a locally promoted, checksum-verified trusted artifact."""
import hashlib
import json
import joblib
from app.core import config

FEATURES = ["heart_rate", "temperature", "sleep_hours", "mood"]
_cached = None
_cached_hash = None

def assess(reading):
    global _cached, _cached_hash
    manifest = config.MODEL_DIR / "current.json"
    result = {"kind": "unavailable", "model_version": None,
              "message": "Chưa có mô hình đã duyệt; chỉ hiển thị dữ liệu đo.",
              "clinical_use": False}
    if not manifest.exists():
        return result
    try:
        meta = json.loads(manifest.read_text())
        if meta["features"] != FEATURES:
            raise ValueError("feature schema mismatch")
        artifact = (config.MODEL_DIR / meta["artifact"]).resolve()
        if not artifact.is_relative_to(config.MODEL_DIR.resolve()):
            raise ValueError("invalid artifact path")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if digest != meta["sha256"]:
            raise ValueError("checksum mismatch")
        if _cached_hash != digest:
            _cached = joblib.load(artifact)
            _cached_hash = digest
        sample = [[reading[f] for f in FEATURES]]
        anomaly = int(_cached.predict(sample)[0]) == -1
        return {"kind": "unusual" if anomaly else "within_demo_pattern",
                "score": float(_cached.decision_function(sample)[0]),
                "model_version": meta["version"], "clinical_use": False,
                "message": "Khác mẫu dữ liệu demo — kiểm tra lại phép đo." if anomaly
                else "Gần mẫu dữ liệu demo; không khẳng định tình trạng sức khỏe."}
    except (OSError, ValueError, KeyError, TypeError, EOFError):
        return {**result, "message": "Artifact lỗi hoặc không tương thích; inference đã tắt."}
