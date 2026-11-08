"""Offline feature drift report. Input JSON array with the same feature names.
This heuristic flags standardized mean shifts; it does not trigger retraining.
"""
import json
import sys
import numpy as np
from pathlib import Path

if __name__ == "__main__":
    manifest = json.loads(Path(sys.argv[1]).read_text())
    readings = json.loads(Path(sys.argv[2]).read_text())
    if len(readings) < 30:
        raise SystemExit("Need >=30 measurements; insufficient evidence")
    x = np.array([[r[f] for f in manifest["features"]] for r in readings], dtype=float)
    if not np.isfinite(x).all():
        raise SystemExit("Invalid measurements")
    shifts = np.abs((x.mean(axis=0) - manifest["feature_mean"]) / np.array(manifest["feature_std"]))
    print(json.dumps({"count": len(x), "review_needed": bool((shifts > 2).any()),
                      "standardized_mean_shift": dict(zip(manifest["features"], shifts.tolist()))}, indent=2))
