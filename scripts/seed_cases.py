"""Seed curated demo cases into the case store (M7 demo readiness).

The demo must open on *compelling* cases. Most PaySim transactions produce an
honest "hold, no rules fired" — real, but a poor first impression. This script
seeds a small curated set where the strong cases (account-draining, large transfer
to a new beneficiary) surface first in the risk-ordered queue, with a couple of
honest thin-evidence holds present because they are real.

This is demo data preparation — it composes the M1–M6 pipeline (no new logic) and
persists queued cases via the case service. It runs the whole online path per case:
features -> rules -> assemble -> recommend -> explain -> enqueue.

Usage:  python scripts/seed_cases.py
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tfm.config.settings import Settings, load_config  # noqa: E402
from tfm.data.features import build_features, to_feature_vector  # noqa: E402
from tfm.data.ingest import PAYSIM_BASE_EPOCH  # noqa: E402
from tfm.persistence.db import create_db_engine, create_session_factory, session_scope  # noqa: E402
from tfm.persistence.models import Account, Base, Counterparty  # noqa: E402
from tfm.persistence.models import Transaction as TxnRow  # noqa: E402
from tfm.schema.entities import Counterparty as CounterpartyEntity  # noqa: E402
from tfm.schema.entities import Transaction as TxnEntity  # noqa: E402
from tfm.schema.entities import TransactionType  # noqa: E402
from tfm.schema.evidence import ScoreStatus  # noqa: E402
from tfm.services.case_service import assemble_and_persist_case  # noqa: E402

# The gate-ineligible model, captured as the operational score-exclusion provenance.
_EXCLUDED = ScoreStatus(
    available=False,
    model_version_id="tfm-scorer-20260704053632",
    leakage_verdict="fail",
    exclusion_reason="failed the simulator-leakage gate; excluded from operational scoring",
)

# Curated demo transactions — strong first, honest holds present.
# (account, counterparty, type, amount, bal_before, bal_after, step)
_CURATED: list[tuple[str, str, str, float, float, float, int]] = [
    (
        "C1231006815",
        "C1900112025",
        "TRANSFER",
        441423.00,
        441423.00,
        0.00,
        212,
    ),  # drain + new-benef
    ("C2044968985", "C7788112233", "CASH_OUT", 985210.50, 985210.50, 0.00, 305),  # full drain
    (
        "C3355128844",
        "C9911223344",
        "TRANSFER",
        250000.00,
        812340.00,
        562340.00,
        190,
    ),  # large new-benef
    ("C4460091277", "M1979787155", "PAYMENT", 120.35, 5400.00, 5279.65, 88),  # thin hold
    ("C5561230098", "M2044108453", "PAYMENT", 64.90, 2210.00, 2145.10, 401),  # thin hold
]


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


def main() -> int:
    settings = Settings(config_dir=str(ROOT / "config"))
    config = load_config(settings)
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)

    rows = [_row(f"demo-{i:04d}", rec) for i, rec in enumerate(_CURATED)]
    features_df = build_features(pd.DataFrame(rows))

    with session_scope(factory) as session:
        for _, frow in features_df.iterrows():
            is_merchant = str(frow["counterparty_id"]).startswith("M")
            session.merge(Account(account_id=str(frow["account_id"]), is_merchant=False))
            session.merge(
                Counterparty(counterparty_id=str(frow["counterparty_id"]), is_merchant=is_merchant)
            )
            session.merge(
                TxnRow(
                    txn_id=str(frow["txn_id"]),
                    step=int(frow["step"]),
                    event_ts=frow["event_ts"].to_pydatetime(),
                    type=str(frow["type"]),
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
            )
            session.flush()

            transaction = TxnEntity(
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
            counterparty = CounterpartyEntity(
                counterparty_id=str(frow["counterparty_id"]), is_merchant=is_merchant
            )
            case = assemble_and_persist_case(
                session,
                transaction=transaction,
                features=to_feature_vector(frow),
                prior_transaction_count=0,  # curated: each account is first-observed
                counterparty=counterparty,
                score=_EXCLUDED,
                config=config,
                llm_enabled=settings.llm_enabled,
            )
            print(f"seeded {case.case_id[:8]} · {transaction.type} · {case.recommendation_action}")

    engine.dispose()
    print(f"\nSeeded {len(rows)} demo cases. Strong (escalate) cases sort first in the queue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
