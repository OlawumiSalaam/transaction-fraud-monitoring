"""Reproducible offline evaluation report.

One command consolidates the submission's evaluation evidence:

    python -m evaluation.run_all

It **reads the committed artifacts verbatim** — it does not retrain, recalibrate,
or regenerate any model metric. Model metrics, eligibility, and the model version
come from the committed scorer manifest (``models/scorer.joblib``); the full leakage
verdict comes from ``evaluation/reports/leakage_verdict.json``. Only the grounding
report (genuinely measurable on synthetic cases) is computed fresh. The leakage
verdict is surfaced *alongside* the headline metrics so the FAIL and the scorer's
ineligibility are impossible to miss. Every number is labelled measured or
modelled estimate. Nothing here feeds back into the online path.

Outputs under ``evaluation/reports/``: ``grounding_report.json``,
``evaluation_summary.json``, and ``evaluation_manifest.json`` (the single source of
truth uses to package the outputs without hardcoded filenames).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.grounding_report import build_grounding_report
from evaluation.labels import modelled
from tfm.ml.registry import load_manifest

REPORTS_DIR = Path("evaluation/reports")
MODEL_PATH = Path("models/scorer.joblib")
LEAKAGE_VERDICT_PATH = REPORTS_DIR / "leakage_verdict.json"
DATASET = "PaySim (synthetic)"

_HEADLINE_METRICS = ("pr_auc", "precision", "recall", "roc_auc", "brier")
_INELIGIBLE_NOTE = (
    "measured on synthetic OOT; modelled estimate of real-world; model INELIGIBLE (leakage FAIL)"
)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


def build_summary(*, llm_enabled: bool = False) -> dict[str, Any]:
    """Consolidate the committed evidence + a fresh grounding report. No re-eval."""
    manifest = load_manifest(MODEL_PATH)  # committed model artifact, read verbatim
    metrics = manifest["metrics"]  # verbatim — not recomputed
    model_version_id = str(manifest["model_version_id"])
    eligible = bool(manifest["eligible"])
    verdict = _read_json(LEAKAGE_VERDICT_PATH)  # committed verdict, read verbatim
    grounding = build_grounding_report(llm_enabled=llm_enabled)

    # Headline: the verdict and ineligibility lead, then the metrics inline — so a
    # reader of the numbers cannot miss that the scorer is excluded.
    headline_metrics = {
        name: modelled(metrics[name], _INELIGIBLE_NOTE).model_dump()
        for name in _HEADLINE_METRICS
        if name in metrics
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": DATASET,
        "model_version_id": model_version_id,
        "scorer_eligible": eligible,
        "leakage_verdict": verdict["verdict"],
        "headline": {
            "status": (
                f"SCORER INELIGIBLE — leakage gate verdict: {verdict['verdict'].upper()} "
                "(FR-4 / FR-26). The metrics below are a modelled estimate on synthetic PaySim "
                "and do NOT qualify this model for operational scoring; the operational path runs "
                "with the scorer excluded."
            ),
            "leakage_verdict": verdict["verdict"],
            "scorer_eligible": eligible,
            "model_version_id": model_version_id,
            "metrics": headline_metrics,
        },
        "leakage_gate": {"verdict": verdict["verdict"], "rationale": verdict["rationale"]},
        "calibration": {
            "method": manifest.get("calibration_method"),
            "brier": modelled(metrics.get("brier"), _INELIGIBLE_NOTE).model_dump(),
        },
        "grounding": grounding,
        "provenance": {
            "model_metrics": (
                "models/scorer.joblib manifest (M2 artifact, read verbatim; not regenerated)"
            ),
            "leakage_verdict": (
                "evaluation/reports/leakage_verdict.json (M2 artifact, read verbatim)"
            ),
            "grounding": (
                "computed by evaluation.grounding_report on a synthetic held-out sample (M9)"
            ),
        },
        "disclosures": [
            "Trained and evaluated on synthetic PaySim data; reported model metrics are a modelled "
            "estimate of real-world performance, not a production result.",
            "The operational scorer is excluded under FR-4 (leakage gate: FAIL); the product "
            "runs on deterministic rule evidence with the scorer disabled.",
            "Generated text is templated (LLM disabled by default, NFR-2); grounding measured on "
            "synthetic cases.",
        ],
    }


def build_manifest(summary: dict[str, Any]) -> dict[str, Any]:
    """The single source of truth for packaging — no hardcoded filenames."""
    model_version_id = summary["model_version_id"]
    return {
        "generated_at": summary["generated_at"],
        "model_version_id": model_version_id,
        "dataset": DATASET,
        "leakage_verdict": summary["leakage_verdict"],
        "scorer_eligible": summary["scorer_eligible"],
        "artifacts": [
            {
                "name": "evaluation_summary",
                "path": "evaluation/reports/evaluation_summary.json",
                "source": "M9 (consolidated)",
            },
            {
                "name": "grounding_report",
                "path": "evaluation/reports/grounding_report.json",
                "source": "M9 (computed)",
            },
            {
                "name": "training_report",
                "path": f"evaluation/reports/{model_version_id}_training_report.json",
                "source": "M2 (verbatim)",
            },
            {
                "name": "leakage_verdict",
                "path": "evaluation/reports/leakage_verdict.json",
                "source": "M2 (verbatim)",
            },
            {"name": "model_artifact", "path": "models/scorer.joblib", "source": "M2 (committed)"},
        ],
    }


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def main() -> int:
    grounding = build_grounding_report()
    _write(REPORTS_DIR / "grounding_report.json", grounding)

    summary = build_summary()
    _write(REPORTS_DIR / "evaluation_summary.json", summary)
    _write(REPORTS_DIR / "evaluation_manifest.json", build_manifest(summary))

    h = summary["headline"]
    print(h["status"])
    print(
        f"\nmodel {summary['model_version_id']} · eligible={summary['scorer_eligible']} · "
        f"leakage_verdict={summary['leakage_verdict'].upper()}"
    )
    for name, m in h["metrics"].items():
        print(f"  {name:>10} = {m['value']:.4f}  [{m['label']}]")
    g = summary["grounding"]["ungrounded_statement_rate"]
    print(f"  {'ungrounded':>10} = {g['value']:.4f}  [{g['label']}]")
    print("\nwrote: grounding_report.json, evaluation_summary.json, evaluation_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
