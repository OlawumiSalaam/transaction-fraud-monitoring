"""Offline evaluation package (Implementation Plan §7).

Model evaluation (PR-AUC, precision, recall, ROC-AUC, Brier), the simulator-
leakage gate (feature-importance + ablation + evidence-based verdict), and the
calibration report. These are offline/learning-path components (§5.1); nothing
here feeds back into the online operational path.

Report artefacts are written under ``evaluation/reports/``.
"""
