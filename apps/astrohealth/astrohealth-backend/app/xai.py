"""Optional explanation adapters for validated future models, imported only when requested."""

from __future__ import annotations

from typing import Any


def tree_shap(model: Any, background: Any, samples: Any) -> Any:
    """SHAP for a compatible local tree model; no remote model/data loading."""
    import shap

    explainer = shap.TreeExplainer(model, data=background)
    return explainer(samples)


def integrated_gradients(model: Any, inputs: Any, baselines: Any, target: int | None = None) -> Any:
    """Captum IG for a differentiable local PyTorch model; return convergence delta."""
    from captum.attr import IntegratedGradients

    return IntegratedGradients(model).attribute(
        inputs, baselines=baselines, target=target, n_steps=64, return_convergence_delta=True
    )
