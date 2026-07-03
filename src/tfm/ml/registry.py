"""Model registry: only a leakage-gate-passing version is loadable (FR-4, FR-26).

The registry persists and loads the online scorer artifact. FR-4 is enforced
here: a model version that did not pass the simulator-leakage gate is **not
loadable in the online path**. Offline inspection may override the check
explicitly, but the operational loader never does.

Spec references: FR-4, FR-26; Addendum §4.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib

from tfm.ml.model import FittedScorer


class IneligibleModelError(RuntimeError):
    """Raised when an online load is attempted on a non-gate-passing model (FR-4)."""


def save_scorer(
    scorer: FittedScorer,
    *,
    leakage_passed: bool,
    manifest: dict[str, Any],
    path: Path,
) -> None:
    """Persist a fitted scorer plus its eligibility flag and manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "scorer": scorer,
        "leakage_passed": leakage_passed,
        "model_version_id": scorer.model_version_id,
        "manifest": manifest,
    }
    joblib.dump(bundle, path)


def load_scorer(path: Path, *, require_pass: bool = True) -> FittedScorer:
    """Load a fitted scorer.

    In the online path (``require_pass=True``, the default) a model that did not
    pass the leakage gate raises ``IneligibleModelError`` (FR-4). Offline tools may
    pass ``require_pass=False`` to inspect an ineligible model.
    """
    bundle: dict[str, Any] = joblib.load(path)
    if require_pass and not bundle.get("leakage_passed", False):
        raise IneligibleModelError(
            f"model version {bundle.get('model_version_id')!r} did not pass the "
            f"simulator-leakage gate and is not eligible for the online path (FR-4)"
        )
    scorer: FittedScorer = bundle["scorer"]
    return scorer


def load_manifest(path: Path) -> dict[str, Any]:
    """Load only the manifest (metrics, calibration, leakage verdict) from an artifact."""
    bundle: dict[str, Any] = joblib.load(path)
    manifest: dict[str, Any] = bundle.get("manifest", {})
    return manifest
