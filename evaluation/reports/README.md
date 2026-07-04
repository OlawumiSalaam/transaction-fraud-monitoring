# Evaluation reports

The reports in evaluation/reports/ are committed for the hackathon submission to
document the real PaySim training run and leakage-gate outcome. Each run is
retained per model version as `<model_version_id>_training_report.json` (which
embeds the metrics, calibration report, DF-1 comparison, and leakage verdict);
`leakage_verdict.json` holds the standalone verdict for the most recent run. In a
production repository these would typically be generated artifacts rather than
version-controlled files.
