"""Offline training entry point (M2).

Trains the bounded candidate set on real PaySim data, runs the simulator-leakage
gate, calibrates the primary, and writes:

- the online scorer artifact (joblib), loadable by the operational path only if it
  passed the leakage gate (FR-4);
- the training report JSON and the leakage-verdict JSON under
  ``evaluation/reports/``.

This is a developer/offline step. It is not run in CI at full scale; the M2 unit
tests exercise the same pipeline on small synthetic data. Producing the committed
model artifact (Release Plan §5) means running this script against the PaySim CSV.

Usage:
    python scripts/train_model.py --data path/to/paysim.csv [--out models/scorer.joblib]

Spec references: FR-3, FR-4, FR-22, FR-23, FR-26; Release Plan §5.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tfm.config.settings import Settings, load_model_config  # noqa: E402
from tfm.data.features import build_features  # noqa: E402
from tfm.data.ingest import load_paysim_csv  # noqa: E402
from tfm.ml.registry import save_scorer  # noqa: E402
from tfm.ml.train import run_training  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the M2 scorer and run the leakage gate.")
    parser.add_argument("--data", required=True, type=Path, help="Path to the PaySim CSV.")
    parser.add_argument(
        "--out", type=Path, default=ROOT / "models" / "scorer.joblib",
        help="Output path for the scorer artifact.",
    )
    parser.add_argument(
        "--reports", type=Path, default=ROOT / "evaluation" / "reports",
        help="Directory for the training report and leakage verdict JSON.",
    )
    parser.add_argument("--config-dir", type=str, default=str(ROOT / "config"))
    args = parser.parse_args()

    settings = Settings(config_dir=args.config_dir)
    model_config = load_model_config(settings)

    print(f"Loading PaySim from {args.data} ...")
    raw = load_paysim_csv(args.data)
    print(f"Building point-in-time features for {len(raw):,} transactions ...")
    features = build_features(raw)

    print("Running bounded candidate comparison + leakage gate ...")
    outcome = run_training(features, model_config)

    args.reports.mkdir(parents=True, exist_ok=True)
    report_path = args.reports / f"{outcome.report.model_version_id}_training_report.json"
    report_path.write_text(outcome.report.model_dump_json(indent=2), encoding="utf-8")

    verdict = outcome.report.selected_leakage_verdict
    verdict_path = args.reports / "leakage_verdict.json"
    verdict_path.write_text(verdict.model_dump_json(indent=2), encoding="utf-8")

    manifest = {
        "model_version_id": outcome.report.model_version_id,
        "metrics": outcome.report.candidate_reports[0].metrics.model_dump(),
        "leakage_verdict": verdict.summary_string(),
        "calibration_method": outcome.report.calibration.method,
        "eligible": outcome.eligible,
    }
    save_scorer(
        outcome.scorer,
        leakage_passed=outcome.eligible,
        manifest=manifest,
        path=args.out,
    )

    print("\n=== Leakage Verdict ===")
    print(verdict.rationale)
    print("\n=== Selected model ===")
    print(json.dumps(manifest, indent=2, default=str))
    print(f"\nArtifact written to {args.out} (eligible={outcome.eligible}).")
    print(f"Reports written to {args.reports}/.")

    if not outcome.eligible:
        print(
            "\nWARNING: the selected primary FAILED the simulator-leakage gate. "
            "It is ineligible for the online path (FR-4). The failure and its evidence "
            "are recorded; remediation is required before this model can advance.",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
