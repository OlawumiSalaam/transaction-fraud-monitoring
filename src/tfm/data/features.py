"""Feature Builder: point-in-time interpretable features (§6.5).

Contract (Addendum §4 — Feature Builder):
  In:  canonical transactions DataFrame (from load_paysim_csv) + account
       history up to each transaction's event_ts.
  Out: the same DataFrame with feature columns appended.

Responsibilities:
  - Compute interpretable, behaviourally-grounded features from the shared
    canonical column substrate.
  - Guarantee point-in-time correctness: features for transaction t use only
    data with event_ts strictly before t (within each account group).
  - Expose FEATURE_COLUMNS — the ordered list of ML input columns shared by
    the scorer (M2), rule engine (M3), and assembler (M4).
  - Provide to_feature_vector() to extract a typed FeatureVector from a single
    DataFrame row (used by the online scoring path in M2+).

Invariants:
  - sim_flagged (isFlaggedFraud) is NEVER a feature column (§6.5, §9).
  - label (isFraud) is NEVER a feature column (it is the prediction target).
  - Random reordering of the input DataFrame does not change feature values
    (output is always sorted by account_id, event_ts before computing history).

Not responsible for: the train/test split policy (splits.py); scoring; deciding.

Spec references: §6.5, FR-1, FR-5, R2 (temporal leakage, Addendum §5).
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from tfm.schema.evidence import FeatureVector

# Ordered list of ML input feature columns.  Shared verbatim by the scorer
# (M2), the rule engine (M3), and the evidence assembler (M4).
# bal_dest_before / bal_dest_after are excluded here: they are None for
# merchant counterparties and require imputation before use in ML training;
# the scorer (M2) decides the imputation strategy.  They remain in the
# DataFrame and in the FeatureVector for evidence and rule use.
FEATURE_COLUMNS: list[str] = [
    "amount",
    "type_payment",
    "type_transfer",
    "type_cash_out",
    "type_cash_in",
    "type_debit",
    "bal_orig_before",
    "bal_orig_after",
    "frac_bal_orig_moved",
    "orig_account_emptied",
    "txn_count_24h",
    "amount_sum_24h",
    "is_new_counterparty",
    "distinct_counterparties_seen",
]


def _account_features(group: pd.DataFrame) -> pd.DataFrame:
    """Compute history-dependent features for a single account's transactions.

    group must be sorted by event_ts ascending — guaranteed by build_features.
    All computed values reference only rows at positions j < i in the group
    (point-in-time invariant).
    """
    n = len(group)
    timestamps = group["event_ts"].tolist()
    amounts = group["amount"].tolist()
    counterparties = group["counterparty_id"].tolist()

    txn_count_24h = [0] * n
    amount_sum_24h = [0.0] * n
    is_new_cp = [True] * n
    distinct_cp = [0] * n

    seen_cps: set[str] = set()
    lo = 0  # sliding-window left boundary for the 24 h lookback
    window_count = 0
    window_sum = 0.0

    for i in range(n):
        # Add the immediately preceding row to the sliding 24 h window.
        if i > 0:
            window_count += 1
            window_sum += amounts[i - 1]

        # Evict rows that have fallen outside the 24 h window.
        cutoff = timestamps[i] - timedelta(hours=24)
        while lo < i and timestamps[lo] < cutoff:
            window_count -= 1
            window_sum -= amounts[lo]
            lo += 1

        txn_count_24h[i] = window_count
        amount_sum_24h[i] = window_sum

        # Counterparty features: check against prior transactions only.
        cp = counterparties[i]
        is_new_cp[i] = cp not in seen_cps
        distinct_cp[i] = len(seen_cps)
        seen_cps.add(cp)

    result = group.copy()
    result["txn_count_24h"] = txn_count_24h
    result["amount_sum_24h"] = amount_sum_24h
    result["is_new_counterparty"] = is_new_cp
    result["distinct_counterparties_seen"] = distinct_cp
    return result


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build point-in-time feature vectors for all transactions in the DataFrame.

    Input:  normalised PaySim DataFrame produced by load_paysim_csv (or a
            compatible DataFrame with the same canonical column names).
    Output: the same rows with feature columns appended; rows are sorted by
            (account_id, event_ts) — callers that need the original order
            should sort by txn_id or reset_index after calling.

    Critical invariant: for any row i (after sorting by account_id, event_ts),
    all history-dependent features (txn_count_24h, amount_sum_24h,
    is_new_counterparty, distinct_counterparties_seen) are computed from
    rows j < i only.  The property test test_features_no_future_row verifies
    this invariant.

    Spec: §6.5, FR-5, R2 (Addendum §5 — temporal leakage guard).
    """
    df = df.sort_values(["account_id", "event_ts"], kind="stable").reset_index(drop=True)

    # ── Transaction-intrinsic ─────────────────────────────────────────────────
    df["type_payment"] = df["type"] == "PAYMENT"
    df["type_transfer"] = df["type"] == "TRANSFER"
    df["type_cash_out"] = df["type"] == "CASH_OUT"
    df["type_cash_in"] = df["type"] == "CASH_IN"
    df["type_debit"] = df["type"] == "DEBIT"

    # ── Balance / sequence ────────────────────────────────────────────────────
    bal_before = df["bal_orig_before"].fillna(0.0)
    bal_after = df["bal_orig_after"].fillna(0.0)

    # NaN where bal_before == 0 (can't compute fraction; division undefined).
    bal_before_safe = bal_before.where(bal_before > 0)
    df["frac_bal_orig_moved"] = df["amount"] / bal_before_safe

    df["orig_account_emptied"] = (bal_before > 0) & (bal_after == 0.0)

    # ── Account-behavioural and counterparty (point-in-time, per account) ────
    account_groups = []
    for _, grp in df.groupby("account_id", sort=False):
        grp_sorted = grp.sort_values("event_ts", kind="stable")
        account_groups.append(_account_features(grp_sorted))

    df = pd.concat(account_groups).sort_index()
    return df


def to_feature_vector(row: pd.Series) -> FeatureVector:
    """Extract a typed FeatureVector from a single build_features output row.

    Used by the online scoring path (M2+) to produce a typed, validated feature
    vector from a single transaction's row in the features DataFrame.

    The caller must ensure the row comes from build_features output (i.e., all
    feature columns are present).

    Spec: Addendum §4 (Feature Builder output contract), §6.5.
    """

    def _opt_float(val: object) -> float | None:
        if val is None:
            return None
        try:
            f = float(val)  # type: ignore[arg-type]
            return None if pd.isna(f) else f
        except (TypeError, ValueError):
            return None

    orig_before = row.get("bal_orig_before")
    orig_after = row.get("bal_orig_after")
    return FeatureVector(
        txn_id=str(row["txn_id"]),
        account_id=str(row["account_id"]),
        counterparty_id=str(row["counterparty_id"]),
        amount=float(row["amount"]),
        type_payment=bool(row["type_payment"]),
        type_transfer=bool(row["type_transfer"]),
        type_cash_out=bool(row["type_cash_out"]),
        type_cash_in=bool(row["type_cash_in"]),
        type_debit=bool(row["type_debit"]),
        bal_orig_before=float(orig_before) if orig_before is not None else 0.0,
        bal_orig_after=float(orig_after) if orig_after is not None else 0.0,
        bal_dest_before=_opt_float(row.get("bal_dest_before")),
        bal_dest_after=_opt_float(row.get("bal_dest_after")),
        frac_bal_orig_moved=_opt_float(row.get("frac_bal_orig_moved")),
        orig_account_emptied=bool(row["orig_account_emptied"]),
        txn_count_24h=int(row["txn_count_24h"]),
        amount_sum_24h=float(row["amount_sum_24h"]),
        is_new_counterparty=bool(row["is_new_counterparty"]),
        distinct_counterparties_seen=int(row["distinct_counterparties_seen"]),
    )
