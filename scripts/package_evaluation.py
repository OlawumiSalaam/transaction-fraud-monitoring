"""Packaging integrity check for the evaluation artifacts (M10).

Reads ``evaluation/reports/evaluation_manifest.json`` — the single source of truth
produced by M9 — and verifies every artifact it lists exists. Packaging (and the
GitHub Release) therefore never relies on hardcoded filenames: the manifest is the
one place that enumerates the evaluation outputs, and this check fails loudly if any
listed artifact is missing.

Usage:  python scripts/package_evaluation.py
Exit 0 if every listed artifact resolves; exit 1 (with the missing paths) otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "evaluation" / "reports" / "evaluation_manifest.json"


def main() -> int:
    if not MANIFEST.is_file():
        print(f"MISSING manifest: {MANIFEST} — run `python -m evaluation.run_all` first.")
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", [])
    if not artifacts:
        print("manifest lists no artifacts")
        return 1

    missing: list[str] = []
    print(
        f"evaluation manifest: model={manifest.get('model_version_id')} "
        f"dataset={manifest.get('dataset')} leakage_verdict={manifest.get('leakage_verdict')}"
    )
    for artifact in artifacts:
        path = ROOT / artifact["path"]
        status = "ok" if path.is_file() else "MISSING"
        if status == "MISSING":
            missing.append(artifact["path"])
        print(f"  [{status:>7}] {artifact['name']:<18} {artifact['path']}  ({artifact['source']})")

    if missing:
        print(f"\nFAILED — {len(missing)} artifact(s) missing: {missing}")
        return 1
    print(f"\nOK — all {len(artifacts)} evaluation artifacts present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
