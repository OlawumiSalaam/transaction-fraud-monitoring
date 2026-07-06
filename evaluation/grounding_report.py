"""Offline grounding-integrity report.

Grounding is one of the few things genuinely *measured* in V1: on synthetic cases
the groundable evidence set is known, so we can run the deterministic grounding
gate over assembled explanations and count any number/entity that does not trace
to the evidence. On the templated floor the ungrounded rate is ≈ 0 by construction;
this report measures it rather than asserting it.

Offline component only — it assembles synthetic cases and reads no operational
store and writes nothing back to the online path.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd

from evaluation.labels import measured
from tfm.assembly.assembler import assemble_evidence
from tfm.config.settings import Settings, load_config
from tfm.data.features import build_features, to_feature_vector
from tfm.data.ingest import PAYSIM_BASE_EPOCH
from tfm.explanation.explainer import explain
from tfm.explanation.grounding import GroundingGate
from tfm.recommendation.policy import recommend
from tfm.rules.engine import RuleEngine
from tfm.schema.entities import Counterparty, Transaction, TransactionType
from tfm.schema.evidence import ScoreStatus

# A held-out synthetic sample exercising the fired-rule and thin-evidence paths.
# (account, counterparty, type, amount, bal_before, bal_after, step)
_SAMPLE: list[tuple[str, str, str, float, float, float, int]] = [
    (
        "E1000000001",
        "E9000000001",
        "TRANSFER",
        441423.00,
        441423.00,
        0.00,
        120,
    ),  # drain + new-benef
    ("E1000000002", "E9000000002", "CASH_OUT", 985210.50, 985210.50, 0.00, 205),  # full drain
    ("E1000000003", "E9000000003", "TRANSFER", 250000.00, 812340.00, 562340.00, 90),  # new-benef
    ("E1000000004", "M9000000004", "PAYMENT", 120.35, 5400.00, 5279.65, 44),  # thin hold
    ("E1000000005", "M9000000005", "PAYMENT", 64.90, 2210.00, 2145.10, 300),  # thin hold
    (
        "E1000000006",
        "E9000000006",
        "TRANSFER",
        610000.00,
        610000.00,
        0.00,
        410,
    ),  # drain + new-benef
]

_EXCLUDED = ScoreStatus(
    available=False,
    model_version_id="tfm-scorer-20260704053632",
    leakage_verdict="fail",
    exclusion_reason="failed the simulator-leakage gate; excluded from operational scoring",
)


def _row(txn_id: str, rec: tuple[str, str, str, float, float, float, int]) -> dict[str, object]:
    account, counterparty, ttype, amount, bal_before, bal_after, step = rec
    is_merchant = counterparty.startswith("M")
    return {
        "txn_id": txn_id,
        "step": step,
        "event_ts": PAYSIM_BASE_EPOCH + timedelta(hours=step),
        "type": ttype,
        "amount": amount,
        "account_id": account,
        "counterparty_id": counterparty,
        "bal_orig_before": bal_before,
        "bal_orig_after": bal_after,
        "bal_dest_before": None if is_merchant else 0.0,
        "bal_dest_after": None if is_merchant else amount,
        "is_merchant_dest": is_merchant,
        "direction": "outbound",
        "sim_flagged": False,
        "label": False,
    }


def build_grounding_report(*, llm_enabled: bool = False) -> dict[str, Any]:
    """Assemble the synthetic sample, explain, and measure grounding integrity."""
    config = load_config(Settings(config_dir="config"))
    engine = RuleEngine(config.rules)
    gate = GroundingGate()

    rows = [_row(f"eval-{i:04d}", rec) for i, rec in enumerate(_SAMPLE)]
    features_df = build_features(pd.DataFrame(rows))

    n_ungrounded = 0
    total_violations = 0
    pathway_counts: dict[str, int] = {}
    for _, frow in features_df.iterrows():
        is_merchant = str(frow["counterparty_id"]).startswith("M")
        features = to_feature_vector(frow)
        transaction = Transaction(
            txn_id=str(frow["txn_id"]),
            step=int(frow["step"]),
            event_ts=frow["event_ts"].to_pydatetime(),
            type=TransactionType(str(frow["type"])),
            amount=float(frow["amount"]),
            account_id=str(frow["account_id"]),
            counterparty_id=str(frow["counterparty_id"]),
            direction="outbound",
            bal_orig_before=float(frow["bal_orig_before"]),
            bal_orig_after=float(frow["bal_orig_after"]),
            bal_dest_before=None if is_merchant else float(frow["bal_dest_before"]),
            bal_dest_after=None if is_merchant else float(frow["bal_dest_after"]),
            sim_flagged=False,
            label=False,
        )
        rule_hits = engine.evaluate(features)
        package = assemble_evidence(
            transaction=transaction,
            features=features,
            prior_transaction_count=0,
            counterparty=Counterparty(
                counterparty_id=transaction.counterparty_id, is_merchant=is_merchant
            ),
            score=_EXCLUDED,
            rule_hits=rule_hits,
        )
        recommendation = recommend(score=_EXCLUDED, rule_hits=rule_hits, config=config.thresholds)
        explanation = explain(package, recommendation, llm_enabled=llm_enabled)
        # Independent post-check of the explanation actually shown.
        result = gate.verify(explanation.text, package, recommendation)
        pathway_counts[explanation.pathway] = pathway_counts.get(explanation.pathway, 0) + 1
        if result.violations:
            n_ungrounded += 1
            total_violations += len(result.violations)

    n = len(rows)
    templated = pathway_counts.get("templated", 0)
    return {
        "sample": "synthetic PaySim-shaped cases (held-out; not the operational store)",
        "n_cases": n,
        "llm_enabled": llm_enabled,
        "ungrounded_statement_rate": measured(
            round(n_ungrounded / n, 6) if n else 0.0,
            "fraction of explanations with any ungrounded number/entity; ≈0 on the templated floor",
        ).model_dump(),
        "total_ungrounded_tokens": measured(total_violations).model_dump(),
        "templated_fallback_rate": measured(
            round(templated / n, 6) if n else 0.0,
            "share on the templated pathway; 1.0 with the LLM disabled (NFR-2 floor)",
        ).model_dump(),
        "pathway_counts": pathway_counts,
    }
