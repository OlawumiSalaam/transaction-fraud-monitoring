"""Ingestion: PaySim CSV to canonical schema (FR-1).

Contract (Addendum §4 — Ingestion):
  In:  raw PaySim CSV file.
  Out: canonical rows persisted to accounts, counterparties, transactions.

Responsibilities:
  - Map PaySim column names to the canonical schema (§6.2).
  - Derive event_ts from the PaySim step field (fixed epoch documented below).
  - Flag merchant destinations (PaySim nameDest 'M' prefix).
  - Null out destination balances for merchant counterparties (no balance signal).
  - Persist accounts, counterparties, and transactions idempotently.

Invariants (Addendum §4):
  - No discriminating field is dropped: direction, both-side balances,
    counterparty are all preserved.
  - Every transaction has an account_id → accounts and counterparty_id →
    counterparties.
  - event_ts is non-decreasing in step (monotonic time ordering).
  - sim_flagged (isFlaggedFraud) is persisted for provenance and excluded from
    every downstream feature computation (§6.5, §9).

Not responsible for: computing features; scoring; interpreting fraud.

Spec references: FR-1, §6.2, §6.3, R1 (Addendum §5).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from tfm.persistence.models import Account, Counterparty, Transaction

# PaySim step 0 → 2024-01-01T00:00:00Z (arbitrary but fixed for reproducibility, NFR-5).
# All downstream code uses event_ts for time-ordering and OOT splits, not the raw step.
PAYSIM_BASE_EPOCH: datetime = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

# Column renames: raw PaySim names → canonical schema names.
_PAYSIM_COLUMNS: dict[str, str] = {
    "step": "step",
    "type": "type",
    "amount": "amount",
    "nameOrig": "account_id",
    "oldbalanceOrg": "bal_orig_before",
    "newbalanceOrig": "bal_orig_after",
    "nameDest": "counterparty_id",
    "oldbalanceDest": "bal_dest_before",
    "newbalanceDest": "bal_dest_after",
    "isFraud": "label",
    "isFlaggedFraud": "sim_flagged",
}

_REQUIRED_PAYSIM_COLUMNS: frozenset[str] = frozenset(_PAYSIM_COLUMNS)


def _step_to_event_ts(step: int) -> datetime:
    return PAYSIM_BASE_EPOCH + timedelta(hours=int(step))


def _is_merchant(name: str) -> bool:
    """PaySim merchant destinations are prefixed with 'M' (R1 guard, Addendum §4)."""
    return str(name).startswith("M")


def load_paysim_csv(path: Path) -> pd.DataFrame:
    """Load a PaySim CSV and normalise to canonical column names.

    Returns a DataFrame with canonical column names, a stable txn_id per row,
    event_ts derived from step, is_merchant_dest flag, direction='outbound', and
    destination balances nulled for merchant counterparties.

    No feature computation occurs here.

    Raises ValueError if any expected PaySim columns are missing.
    """
    df = pd.read_csv(path, dtype={"nameOrig": str, "nameDest": str})

    missing = _REQUIRED_PAYSIM_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"PaySim CSV missing expected columns: {sorted(missing)}")

    df = df.rename(columns=_PAYSIM_COLUMNS)

    # Stable, deterministic transaction id from row position in the CSV (NFR-5).
    df["txn_id"] = [f"paysim-{i:07d}" for i in range(len(df))]

    df["event_ts"] = df["step"].apply(_step_to_event_ts)
    df["is_merchant_dest"] = df["counterparty_id"].apply(_is_merchant)
    df["direction"] = "outbound"  # PaySim: all transactions are origin → destination

    # Merchant destinations carry no balance signal (R1, Addendum §4, §3.2).
    merchant_mask = df["is_merchant_dest"]
    df.loc[merchant_mask, "bal_dest_before"] = None
    df.loc[merchant_mask, "bal_dest_after"] = None

    return df


def ingest_to_db(df: pd.DataFrame, session: Session) -> int:
    """Persist a normalised PaySim DataFrame into the canonical relational store.

    Upserts accounts and counterparties (idempotent on re-ingest), then inserts
    transactions that do not already exist (keyed on txn_id).

    Returns the count of new Transaction rows inserted.

    Invariants:
    - sim_flagged is persisted for provenance; it is not a feature (§6.5, §9).
    - Every Transaction row has a valid account_id and counterparty_id.
    - Existing rows are skipped; this function is safe to call incrementally.
    """
    # ── Accounts (nameOrig / account_id) ────────────────────────────────────
    # Collect first-seen step per account.
    first_step: dict[str, int] = {}
    for _, row in df[["account_id", "step"]].iterrows():
        acct_id = str(row["account_id"])
        s = int(row["step"])
        if acct_id not in first_step or first_step[acct_id] > s:
            first_step[acct_id] = s

    existing_accounts: set[str] = {a.account_id for a in session.query(Account.account_id).all()}
    new_accounts = [
        Account(
            account_id=acct_id,
            first_seen_step=s,
            is_merchant=_is_merchant(acct_id),
        )
        for acct_id, s in first_step.items()
        if acct_id not in existing_accounts
    ]
    if new_accounts:
        session.add_all(new_accounts)

    # ── Counterparties (nameDest / counterparty_id) ──────────────────────────
    cp_merchant: dict[str, bool] = {
        str(cp): _is_merchant(str(cp)) for cp in df["counterparty_id"].unique()
    }
    existing_cps: set[str] = {
        c.counterparty_id for c in session.query(Counterparty.counterparty_id).all()
    }
    new_cps = [
        Counterparty(counterparty_id=cp_id, is_merchant=is_merch)
        for cp_id, is_merch in cp_merchant.items()
        if cp_id not in existing_cps
    ]
    if new_cps:
        session.add_all(new_cps)

    session.flush()  # write accounts/counterparties before FK-constrained transactions

    # ── Transactions ─────────────────────────────────────────────────────────
    existing_txns: set[str] = {t.txn_id for t in session.query(Transaction.txn_id).all()}

    def _float_or_none(val: object) -> float | None:
        if val is None:
            return None
        try:
            f = float(val)  # type: ignore[arg-type]
            return None if pd.isna(f) else f
        except (TypeError, ValueError):
            return None

    new_txns: list[Transaction] = []
    for row in df.itertuples(index=False):
        txn_id = str(row.txn_id)
        if txn_id in existing_txns:
            continue
        new_txns.append(
            Transaction(
                txn_id=txn_id,
                step=int(row.step),
                event_ts=row.event_ts,
                type=str(row.type),
                amount=float(row.amount),
                account_id=str(row.account_id),
                counterparty_id=str(row.counterparty_id),
                direction=str(row.direction),
                bal_orig_before=_float_or_none(row.bal_orig_before),
                bal_orig_after=_float_or_none(row.bal_orig_after),
                bal_dest_before=_float_or_none(row.bal_dest_before),
                bal_dest_after=_float_or_none(row.bal_dest_after),
                sim_flagged=bool(row.sim_flagged),
                label=bool(row.label),
            )
        )

    if new_txns:
        session.add_all(new_txns)
    session.flush()

    return len(new_txns)
