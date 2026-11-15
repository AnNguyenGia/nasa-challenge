"""Generate two small ONNX artifacts from synthetic formulas; never clinical models."""

import hashlib
from pathlib import Path

import onnx
import yaml
from onnx import TensorProto, helper

root = Path(__file__).resolve().parents[1] / "models_registry"
root.mkdir(exist_ok=True)
models = []
for name, weights in [("anomaly-demo", [0.1, -0.05, 0.02]), ("forecast-demo", [0.2, 0.3, 0.5])]:
    graph = helper.make_graph(
        [helper.make_node("MatMul", ["features", "weights"], ["score"])],
        name,
        [helper.make_tensor_value_info("features", TensorProto.FLOAT, [1, 3])],
        [helper.make_tensor_value_info("score", TensorProto.FLOAT, [1, 1])],
        [helper.make_tensor("weights", TensorProto.FLOAT, [3, 1], weights)],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
    onnx.checker.check_model(model)
    path = root / f"{name}-1.onnx"
    onnx.save(model, path)
    models.append(
        {
            "id": name,
            "version": "synthetic-1",
            "checkpoint": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "input_features": 3,
            "weights": weights,
            "model_is_placeholder": True,
            "clinical_validation": False,
            "metrics": None,
            "limits": "Synthetic formula for integration testing only",
        }
    )
for name in ["ecg-classification", "sleep-eeg", "multimodal", "biomedical-text"]:
    models.append(
        {
            "id": name,
            "version": "unavailable",
            "checkpoint": None,
            "model_is_placeholder": True,
            "status": "insufficient_conditions",
        }
    )
(root / "manifest.yaml").write_text(yaml.safe_dump({"models": models}), encoding="utf-8")
print("Created two synthetic ONNX models and four unavailable model declarations")
