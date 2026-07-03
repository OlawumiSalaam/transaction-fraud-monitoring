"""Unit and property tests for the Feature Builder (§6.5).

The highest-priority test in this module is the Hypothesis property test that
verifies the point-in-time invariant: no feature for transaction t may use
information from any transaction that occurred at or after t (Implementation
Plan §10, R2 in Addendum §5).

Spec: §6.5, FR-5, R2 (Addendum §5).
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from tfm.data.features import FEATURE_COLUMNS, build_features, to_feature_vector
from tfm.data.ingest import PAYSIM_BASE_EPOCH
from tfm.schema.evidence import FeatureVector

# ── Shared fixture helpers ────────────────────────────────────────────────────

_STEP_EPOCH = PAYSIM_BASE_EPOCH


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal features-ready DataFrame from plain dicts."""
    records = []
    for idx, r in enumerate(rows):
        step = r.get("step", idx + 1)
        records.append(
            {
                "txn_id": r.get("txn_id", f"t{idx:04d}"),
                "step": step,
                "event_ts": _STEP_EPOCH + timedelta(hours=int(step)),
                "type": r.get("type", "PAYMENT"),
                "amount": r.get("amount", 100.0),
                "account_id": r.get("account_id", "C1"),
                "counterparty_id": r.get("counterparty_id", "M1"),
                "bal_orig_before": r.get("bal_orig_before", 1000.0),
                "bal_orig_after": r.get("bal_orig_after", 900.0),
                "bal_dest_before": r.get("bal_dest_before", None),
                "bal_dest_after": r.get("bal_dest_after", None),
                "is_merchant_dest": r.get("is_merchant_dest", False),
                "direction": "outbound",
                "sim_flagged": False,
                "label": r.get("label", False),
            }
        )
    return pd.DataFrame(records)


# ── FEATURE_COLUMNS invariants ────────────────────────────────────────────────


def test_feature_columns_excludes_sim_flagged() -> None:
    """sim_flagged must never appear in the feature set (§6.5, §9)."""
    assert "sim_flagged" not in FEATURE_COLUMNS


def test_feature_columns_excludes_label() -> None:
    assert "label" not in FEATURE_COLUMNS


def test_feature_columns_excludes_identifiers() -> None:
    for col in ("txn_id", "account_id", "counterparty_id"):
        assert col not in FEATURE_COLUMNS


# ── Transaction-intrinsic features ────────────────────────────────────────────


def test_type_encoding_payment() -> None:
    df = _make_df([{"type": "PAYMENT"}])
    result = build_features(df)
    row = result.iloc[0]
    assert bool(row["type_payment"]) is True
    assert bool(row["type_transfer"]) is False
    assert bool(row["type_cash_out"]) is False


def test_type_encoding_transfer() -> None:
    df = _make_df([{"type": "TRANSFER"}])
    result = build_features(df)
    row = result.iloc[0]
    assert bool(row["type_transfer"]) is True
    assert bool(row["type_payment"]) is False


def test_type_encoding_cash_out() -> None:
    df = _make_df([{"type": "CASH_OUT"}])
    result = build_features(df)
    row = result.iloc[0]
    assert bool(row["type_cash_out"]) is True


# ── Balance / sequence features ───────────────────────────────────────────────


def test_frac_bal_orig_moved_normal() -> None:
    df = _make_df([{"amount": 200.0, "bal_orig_before": 1000.0, "bal_orig_after": 800.0}])
    result = build_features(df)
    assert abs(result.iloc[0]["frac_bal_orig_moved"] - 0.2) < 1e-9


def test_frac_bal_orig_moved_zero_balance_is_none() -> None:
    df = _make_df([{"amount": 100.0, "bal_orig_before": 0.0, "bal_orig_after": 0.0}])
    result = build_features(df)
    frac = result.iloc[0]["frac_bal_orig_moved"]
    assert frac is None or pd.isna(frac)


def test_orig_account_emptied_true() -> None:
    df = _make_df([{"amount": 500.0, "bal_orig_before": 500.0, "bal_orig_after": 0.0}])
    result = build_features(df)
    assert bool(result.iloc[0]["orig_account_emptied"]) is True


def test_orig_account_emptied_false() -> None:
    df = _make_df([{"amount": 100.0, "bal_orig_before": 500.0, "bal_orig_after": 400.0}])
    result = build_features(df)
    assert bool(result.iloc[0]["orig_account_emptied"]) is False


def test_orig_account_emptied_zero_before_is_false() -> None:
    # Empty before AND empty after: not "emptied" (it was already empty)
    df = _make_df([{"amount": 0.0, "bal_orig_before": 0.0, "bal_orig_after": 0.0}])
    result = build_features(df)
    assert bool(result.iloc[0]["orig_account_emptied"]) is False


# ── Velocity features (point-in-time) ────────────────────────────────────────


def test_first_transaction_velocity_zero() -> None:
    """The very first transaction of an account has no prior history."""
    df = _make_df([{"account_id": "C1", "step": 1}])
    result = build_features(df)
    assert int(result.iloc[0]["txn_count_24h"]) == 0
    assert float(result.iloc[0]["amount_sum_24h"]) == 0.0


def test_velocity_accumulates_prior_rows_only() -> None:
    df = _make_df(
        [
            {"account_id": "C1", "step": 1, "amount": 100.0},
            {"account_id": "C1", "step": 2, "amount": 200.0},
            {"account_id": "C1", "step": 3, "amount": 300.0},
        ]
    )
    result = build_features(df).sort_values("step").reset_index(drop=True)
    assert int(result.iloc[0]["txn_count_24h"]) == 0
    assert int(result.iloc[1]["txn_count_24h"]) == 1
    assert abs(result.iloc[1]["amount_sum_24h"] - 100.0) < 1e-9
    assert int(result.iloc[2]["txn_count_24h"]) == 2
    assert abs(result.iloc[2]["amount_sum_24h"] - 300.0) < 1e-9


def test_velocity_window_evicts_old_rows() -> None:
    """Transactions older than 24 h must be evicted from txn_count_24h."""
    df = _make_df(
        [
            {"account_id": "C1", "step": 1, "amount": 100.0},  # step 1 = hour 1
            {
                "account_id": "C1",
                "step": 26,
                "amount": 200.0,
            },  # step 26 = hour 26 (>24h after step 1)
        ]
    )
    result = build_features(df).sort_values("step").reset_index(drop=True)
    # Row at step 26: step 1 is 25h before → outside the 24h window
    assert int(result.iloc[1]["txn_count_24h"]) == 0
    assert float(result.iloc[1]["amount_sum_24h"]) == 0.0


def test_velocity_window_keeps_within_24h() -> None:
    df = _make_df(
        [
            {"account_id": "C1", "step": 1, "amount": 100.0},
            {"account_id": "C1", "step": 24, "amount": 200.0},  # 23h after step 1 — inside window
        ]
    )
    result = build_features(df).sort_values("step").reset_index(drop=True)
    assert int(result.iloc[1]["txn_count_24h"]) == 1


def test_velocity_isolated_per_account() -> None:
    """Account B's history must never influence account A's features."""
    df = _make_df(
        [
            {"account_id": "C1", "step": 1},
            {"account_id": "C2", "step": 1},
            {"account_id": "C2", "step": 2},
        ]
    )
    result = build_features(df)
    c1_row = result[result["account_id"] == "C1"].iloc[0]
    assert int(c1_row["txn_count_24h"]) == 0  # C2 must not contaminate C1's window


# ── Counterparty features ─────────────────────────────────────────────────────


def test_first_counterparty_is_new() -> None:
    df = _make_df([{"account_id": "C1", "counterparty_id": "M1"}])
    result = build_features(df)
    assert bool(result.iloc[0]["is_new_counterparty"]) is True
    assert int(result.iloc[0]["distinct_counterparties_seen"]) == 0


def test_repeat_counterparty_is_not_new() -> None:
    df = _make_df(
        [
            {"account_id": "C1", "step": 1, "counterparty_id": "M1"},
            {"account_id": "C1", "step": 2, "counterparty_id": "M1"},
        ]
    )
    result = build_features(df).sort_values("step").reset_index(drop=True)
    assert bool(result.iloc[0]["is_new_counterparty"]) is True
    assert bool(result.iloc[1]["is_new_counterparty"]) is False
    assert int(result.iloc[1]["distinct_counterparties_seen"]) == 1


def test_distinct_counterparties_seen_increments() -> None:
    df = _make_df(
        [
            {"account_id": "C1", "step": 1, "counterparty_id": "M1"},
            {"account_id": "C1", "step": 2, "counterparty_id": "C99"},
            {"account_id": "C1", "step": 3, "counterparty_id": "C98"},
        ]
    )
    result = build_features(df).sort_values("step").reset_index(drop=True)
    assert int(result.iloc[0]["distinct_counterparties_seen"]) == 0
    assert int(result.iloc[1]["distinct_counterparties_seen"]) == 1
    assert int(result.iloc[2]["distinct_counterparties_seen"]) == 2


# ── to_feature_vector ────────────────────────────────────────────────────────


def test_to_feature_vector_returns_feature_vector() -> None:
    df = _make_df([{"account_id": "C1", "step": 1, "amount": 100.0}])
    result = build_features(df)
    fv = to_feature_vector(result.iloc[0])
    assert isinstance(fv, FeatureVector)


def test_to_feature_vector_fields_match_row() -> None:
    df = _make_df(
        [
            {
                "account_id": "C1",
                "step": 1,
                "amount": 250.0,
                "type": "TRANSFER",
                "counterparty_id": "C99",
                "bal_orig_before": 1000.0,
                "bal_orig_after": 750.0,
            }
        ]
    )
    result = build_features(df)
    fv = to_feature_vector(result.iloc[0])
    assert fv.amount == 250.0
    assert fv.type_transfer is True
    assert fv.type_payment is False
    assert fv.account_id == "C1"
    assert fv.counterparty_id == "C99"


def test_to_feature_vector_sim_flagged_absent() -> None:
    df = _make_df([{"account_id": "C1", "step": 1}])
    result = build_features(df)
    fv = to_feature_vector(result.iloc[0])
    assert not hasattr(fv, "sim_flagged")


# ── PROPERTY TEST: point-in-time invariant ────────────────────────────────────


_ROW_STRATEGY = st.fixed_dictionaries(
    {
        "account_id": st.sampled_from(["C1", "C2", "C3"]),
        "step": st.integers(min_value=1, max_value=100),
        "amount": st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
        "counterparty_id": st.sampled_from(["M1", "C99", "C98", "C97"]),
        "type": st.sampled_from(["PAYMENT", "TRANSFER", "CASH_OUT"]),
        "bal_orig_before": st.floats(
            min_value=0.0, max_value=1e7, allow_nan=False, allow_infinity=False
        ),
        "bal_orig_after": st.floats(
            min_value=0.0, max_value=1e7, allow_nan=False, allow_infinity=False
        ),
    }
)


@given(st.lists(_ROW_STRATEGY, min_size=1, max_size=15))
@settings(max_examples=200, deadline=None)
def test_features_point_in_time_invariant(rows: list[dict]) -> None:
    """For every transaction t, txn_count_24h counts only prior transactions.

    Verifies the non-negotiable R2 guard (Addendum §5): no feature for row i
    may incorporate data from any row j >= i (in account-sorted order).
    Specifically, txn_count_24h must equal the count of rows with the same
    account_id, event_ts strictly less than the current row's event_ts, and
    within a 24 h lookback window.

    Implementation Plan §10 designates this as the highest-priority property
    test for M1.
    """
    # Skip cases with duplicate (account_id, step) pairs — they would produce
    # ambiguous positional ordering within a tie that is implementation-defined.
    pairs = [(r["account_id"], r["step"]) for r in rows]
    assume(len(pairs) == len(set(pairs)))

    df = _make_df(rows)
    result = build_features(df)

    for acct_id, group in result.groupby("account_id"):
        grp = group.sort_values("event_ts", kind="stable").reset_index(drop=True)
        for i in range(len(grp)):
            ts_i = grp.iloc[i]["event_ts"]
            window_start = ts_i - timedelta(hours=24)

            # Count all rows j < i (strictly prior) within the 24 h window.
            expected_count = sum(1 for j in range(i) if grp.iloc[j]["event_ts"] >= window_start)
            actual_count = int(grp.iloc[i]["txn_count_24h"])

            assert actual_count == expected_count, (
                f"Point-in-time violation for account={acct_id!r}, row={i}: "
                f"txn_count_24h={actual_count} but expected {expected_count} "
                f"(event_ts={ts_i}, window_start={window_start})"
            )


@given(st.lists(_ROW_STRATEGY, min_size=1, max_size=15))
@settings(max_examples=200, deadline=None)
def test_features_counterparty_prior_transactions_invariant(rows: list[dict]) -> None:
    """is_new_counterparty and distinct_counterparties_seen reference only prior rows.

    The counterparty traversal in _account_features uses a different mechanism
    from the 24 h sliding window: a monotonically growing set (seen_cps) that is
    read before being mutated.  Both features read from the same set state at row i,
    which contains exactly the counterparty_ids from rows 0..i-1 (same account group).

    This is a distinct invariant from test_features_point_in_time_invariant because:
    - No time window: all prior transactions contribute (not just those within 24 h).
    - Proves the set-accumulation boundary, not the sliding-window boundary.

    See IMP-005 for the shared-mechanism rationale that makes these two property
    tests sufficient coverage for all four history-dependent features.

    Spec: §6.5, FR-5, R2 (Addendum §5), IMP-005.
    """
    pairs = [(r["account_id"], r["step"]) for r in rows]
    assume(len(pairs) == len(set(pairs)))

    df = _make_df(rows)
    result = build_features(df)

    for acct_id, group in result.groupby("account_id"):
        grp = group.sort_values("event_ts", kind="stable").reset_index(drop=True)
        for i in range(len(grp)):
            cp_i = str(grp.iloc[i]["counterparty_id"])

            # Ground truth: counterparties seen in strictly prior rows (j < i).
            prior_cps = {str(grp.iloc[j]["counterparty_id"]) for j in range(i)}

            expected_is_new = cp_i not in prior_cps
            expected_distinct = len(prior_cps)

            actual_is_new = bool(grp.iloc[i]["is_new_counterparty"])
            actual_distinct = int(grp.iloc[i]["distinct_counterparties_seen"])

            assert actual_is_new == expected_is_new, (
                f"is_new_counterparty violation for account={acct_id!r}, row={i}: "
                f"got {actual_is_new}, expected {expected_is_new} "
                f"(counterparty={cp_i!r}, prior={prior_cps!r})"
            )
            assert actual_distinct == expected_distinct, (
                f"distinct_counterparties_seen violation for account={acct_id!r}, "
                f"row={i}: got {actual_distinct}, expected {expected_distinct}"
            )
