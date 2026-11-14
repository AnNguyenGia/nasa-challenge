"""Prototype astronaut health signal agent.

This is a research triage/orchestration layer, NOT a medical diagnostic system.
ECG input must be a preprocessed 187-sample beat matching the MIT-BIH training pipeline.
Respiratory tables are descriptive HRV/RR protocol data, not disease labels.
Lung ultrasound is unavailable until a labeled image dataset and trained model are added.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any
import numpy as np

ECG_CLASSES = [
    "N - Normal", "S - Supraventricular", "V - Ventricular",
    "F - Fusion", "Q - Unknown/Other"
]


def summarize_rr_intervals(rr_ms) -> Dict[str, Any]:
    """Summarize RR intervals in milliseconds; does not infer respiratory rate."""
    x = np.asarray(rr_ms, dtype=float).reshape(-1)
    x = x[np.isfinite(x) & (x > 0)]
    if x.size == 0:
        return {"available": False, "reason": "No valid RR intervals"}
    med = float(np.median(x))
    return {
        "available": True,
        "n_intervals": int(x.size),
        "median_rr_ms": med,
        "mean_rr_ms": float(np.mean(x)),
        "rr_std_ms": float(np.std(x, ddof=1)) if x.size > 1 else 0.0,
        "estimated_mean_hr_bpm": float(60000.0 / med),
        "interpretation": "HR estimate derived from median inter-beat interval; protocol/context dependent"
    }


def summarize_respiratory_metrics(metrics: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Accept a row/dict from hrv_indexes_clean; avoid treating protocol output as disease label."""
    if not metrics:
        return {"available": False, "reason": "No respiratory/HRV metrics supplied"}
    keys = ["MeanHR", "mRR", "SDNN", "RMSSD", "pNN50", "LF_HF_ratio", "protocol_step", "output"]
    out = {k: _to_float(metrics.get(k)) for k in keys if metrics.get(k) is not None}
    out["available"] = bool(out)
    out["limitation"] = (
        "These are protocol/HRV measurements. The dataset does not provide a continuous respiratory waveform "
        "or validated healthy/disease labels. 'output' is not a clinical diagnosis label."
    )
    return out


def _to_float(value):
    try:
        v = float(value)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


class HealthSignalAgent:
    """Combines available module outputs into a transparent screening summary."""
    def __init__(self, ecg_checkpoint: Optional[str | Path] = None):
        self.ecg_checkpoint = Path(ecg_checkpoint) if ecg_checkpoint else None
        self._ecg_model = None
        self._ecg_error = None

    def load_ecg_model(self):
        if self._ecg_model is not None:
            return True
        if not self.ecg_checkpoint or not self.ecg_checkpoint.exists():
            self._ecg_error = "ECG checkpoint not found"
            return False
        try:
            import torch
            from torch import nn
            class ECGNet(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.features = nn.Sequential(
                        nn.Conv1d(1, 32, 7, padding=3, bias=False), nn.BatchNorm1d(32), nn.ReLU(), nn.MaxPool1d(2),
                        nn.Conv1d(32, 64, 5, padding=2, bias=False), nn.BatchNorm1d(64), nn.ReLU(), nn.MaxPool1d(2),
                        nn.Conv1d(64, 128, 3, padding=1, bias=False), nn.BatchNorm1d(128), nn.ReLU(),
                        nn.AdaptiveAvgPool1d(1)
                    )
                    self.classifier = nn.Sequential(
                        nn.Identity(), nn.Identity(), nn.Linear(128, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, 5)
                    )
                def forward(self, x):
                    x = self.features(x).squeeze(-1)
                    return self.classifier(x)
            ckpt = torch.load(self.ecg_checkpoint, map_location="cpu", weights_only=False)
            model = ECGNet()
            model.load_state_dict(ckpt["model_state_dict"], strict=True)
            model.eval()
            self._ecg_model = model
            return True
        except Exception as exc:
            self._ecg_error = f"Could not load ECG model: {exc}"
            return False

    def predict_ecg(self, beat_187):
        """Predict one preprocessed 187-point beat; input scaling must match training."""
        if not self.load_ecg_model():
            return {"available": False, "reason": self._ecg_error}
        import torch
        x = np.asarray(beat_187, dtype=np.float32).reshape(-1)
        if x.size != 187 or not np.isfinite(x).all():
            return {"available": False, "reason": "ECG input must contain exactly 187 finite preprocessed samples"}
        with torch.no_grad():
            logits = self._ecg_model(torch.from_numpy(x).view(1, 1, 187))
            probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
        idx = int(np.argmax(probs))
        return {"available": True, "class_index": idx, "class_name": ECG_CLASSES[idx],
                "confidence": float(probs[idx]),
                "probabilities": {ECG_CLASSES[i]: float(probs[i]) for i in range(5)},
                "caveat": "Research classifier; not a diagnosis. Confirm clinically, especially abnormal/uncertain outputs."}

    def assess(self, ecg_beat=None, rr_intervals_ms=None, respiratory_metrics=None, lung_result=None):
        ecg = self.predict_ecg(ecg_beat) if ecg_beat is not None else {"available": False, "reason": "No ECG beat supplied"}
        rr = summarize_rr_intervals(rr_intervals_ms) if rr_intervals_ms is not None else {"available": False, "reason": "No RR intervals supplied"}
        resp = summarize_respiratory_metrics(respiratory_metrics)
        lung = lung_result or {"available": False, "reason": "Lung ultrasound images/model not present in project archive"}
        alerts = []
        if ecg.get("available") and ecg.get("class_index") in (1, 2, 3):
            alerts.append("ECG model returned a non-N rhythm class; clinical review required")
        if rr.get("available"):
            hr = rr.get("estimated_mean_hr_bpm")
            if hr is not None and (hr < 50 or hr > 120):
                alerts.append("Derived heart-rate estimate is outside the broad 50–120 bpm screening band; verify context and repeat measurement")
        return {
            "status": "REVIEW_REQUIRED" if alerts else "INSUFFICIENT_DATA" if not (ecg.get("available") or rr.get("available") or resp.get("available") or lung.get("available")) else "NO_AUTOMATED_ALERT",
            "modules": {"ecg": ecg, "rr_intervals": rr, "respiratory_hrv": resp, "lung_ultrasound": lung},
            "alerts": alerts,
            "missing_data": [name for name, result in [("ECG",ecg),("RR",rr),("Respiratory HRV",resp),("Lung ultrasound",lung)] if not result.get("available")],
            "disclaimer": "Decision-support prototype only. Not for diagnosis, flight clearance, or treatment decisions. A qualified clinician must interpret findings."
        }
