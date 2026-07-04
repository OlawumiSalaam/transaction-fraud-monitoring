"""Unit and property tests for the Feature Builder (§6.5).

The highest-priority test in this module is the Hypothesis property test that
verifies the point-in-time invariant: no feature for transaction t may use
information from any transaction that occurred at or after t (Implementation
Plan §10, R2 in Addendum §5).

Spec: §6.5, FR-5, R2 (Addendum §5).
"""

from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest
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
    with np.errstate(over="ignore"):  # denormal-tiny Hypothesis amounts (see note above)
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
    with np.errstate(over="ignore"):  # denormal-tiny Hypothesis amounts (see note above)
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


# ── EQUIVALENCE REGRESSION: single-pass output == grouped reference (IMP-009) ──
#
# The production build_features was optimised (IMP-009) from a per-account
# groupby/concat implementation to a single linear pass over the globally
# (account_id, event_ts)-sorted frame, to remove an O(number-of-accounts)
# DataFrame-object memory footprint that destabilised full-scale PaySim runs.
#
# _reference_grouped_build below is the *frozen* pre-optimisation grouped
# implementation, retained here (and only here) as a reference oracle.  The
# regression test asserts the optimised build_features reproduces it exactly on
# a representative, shuffled multi-account dataset.  This oracle is deliberately
# NOT imported from production code: production carries a single implementation
# (no dead code), and this test remains a permanent guard that any future change
# to build_features preserves the exact engineered feature values.


def _reference_account_features(group: pd.DataFrame) -> pd.DataFrame:
    """Frozen pre-IMP-009 per-account history features (reference oracle)."""
    n = len(group)
    timestamps = group["event_ts"].tolist()
    amounts = group["amount"].tolist()
    counterparties = group["counterparty_id"].tolist()

    txn_count_24h = [0] * n
    amount_sum_24h = [0.0] * n
    is_new_cp = [True] * n
    distinct_cp = [0] * n

    seen_cps: set[str] = set()
    lo = 0
    window_count = 0
    window_sum = 0.0

    for i in range(n):
        if i > 0:
            window_count += 1
            window_sum += amounts[i - 1]

        cutoff = timestamps[i] - timedelta(hours=24)
        while lo < i and timestamps[lo] < cutoff:
            window_count -= 1
            window_sum -= amounts[lo]
            lo += 1

        txn_count_24h[i] = window_count
        amount_sum_24h[i] = window_sum

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


def _reference_grouped_build(df: pd.DataFrame) -> pd.DataFrame:
    """Frozen pre-IMP-009 grouped build_features (reference oracle)."""
    df = df.sort_values(["account_id", "event_ts"], kind="stable").reset_index(drop=True)

    df["type_payment"] = df["type"] == "PAYMENT"
    df["type_transfer"] = df["type"] == "TRANSFER"
    df["type_cash_out"] = df["type"] == "CASH_OUT"
    df["type_cash_in"] = df["type"] == "CASH_IN"
    df["type_debit"] = df["type"] == "DEBIT"

    bal_before = df["bal_orig_before"].fillna(0.0)
    bal_after = df["bal_orig_after"].fillna(0.0)
    bal_before_safe = bal_before.where(bal_before > 0)
    df["frac_bal_orig_moved"] = df["amount"] / bal_before_safe
    df["orig_account_emptied"] = (bal_before > 0) & (bal_after == 0.0)

    account_groups = []
    for _, grp in df.groupby("account_id", sort=False):
        grp_sorted = grp.sort_values("event_ts", kind="stable")
        account_groups.append(_reference_account_features(grp_sorted))

    return pd.concat(account_groups).sort_index()


# Every column build_features engineers (a superset of the ML FEATURE_COLUMNS
# plus the None-carrying frac_bal_orig_moved), compared value-for-value.
_ENGINEERED_COLUMNS = [
    "type_payment",
    "type_transfer",
    "type_cash_out",
    "type_cash_in",
    "type_debit",
    "frac_bal_orig_moved",
    "orig_account_emptied",
    "txn_count_24h",
    "amount_sum_24h",
    "is_new_counterparty",
    "distinct_counterparties_seen",
]


def _representative_dataset() -> pd.DataFrame:
    """A representative, deliberately shuffled multi-account PaySim-like frame.

    Exercises: single- and multi-transaction accounts, repeated and new
    counterparties, the 24 h window boundary (evicted and retained prior rows),
    every transaction type, merchant and non-merchant destinations, and zero /
    non-zero origin balances.  Input order is shuffled to also prove that the
    optimised traversal is invariant to input ordering.
    """
    rows: list[dict] = []
    types = ["PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN", "DEBIT"]
    counterparties = ["M1", "M2", "C900", "C901", "C902"]

    # 12 accounts, varying history lengths, steps spanning >24 h boundaries.
    for a in range(12):
        acct = f"C{a:03d}"
        n_txns = 1 + (a % 6) * 3  # 1, 1, 4, 7, 10, 13, 1, ...
        for k in range(n_txns):
            # Steps chosen so some prior rows fall inside and some outside 24 h.
            step = 1 + k * (13 + (a % 5)) + (k % 3)
            bal_before = 0.0 if (a + k) % 7 == 0 else float(1000 + 137 * k + 11 * a)
            bal_after = 0.0 if (k % 4 == 0 and bal_before > 0) else max(bal_before - 100.0, 0.0)
            rows.append(
                {
                    "account_id": acct,
                    "step": step,
                    "amount": float(50 + 37 * k + 5 * a),
                    "type": types[(a + k) % len(types)],
                    "counterparty_id": counterparties[(a * 2 + k) % len(counterparties)],
                    "bal_orig_before": bal_before,
                    "bal_orig_after": bal_after,
                }
            )

    df = _make_df(rows)
    # Deterministic shuffle to prove ordering-invariance of the traversal.
    return df.sample(frac=1.0, random_state=20260703).reset_index(drop=True)


def test_single_pass_matches_grouped_reference() -> None:
    """The optimised single-pass build_features == the frozen grouped reference.

    Asserts identical values for every engineered feature column on a
    representative shuffled multi-account dataset (IMP-009).  Guards the
    point-in-time invariants (R2) against future changes to the optimised path.
    """
    df = _representative_dataset()

    produced = build_features(df.copy()).reset_index(drop=True)
    reference = _reference_grouped_build(df.copy()).reset_index(drop=True)

    # Row identity must align first: same rows in the same (account_id, event_ts)
    # order, so a column-wise comparison is meaningful.
    pdt.assert_series_equal(produced["txn_id"], reference["txn_id"], check_names=True)

    for col in _ENGINEERED_COLUMNS:
        pdt.assert_series_equal(
            produced[col],
            reference[col],
            check_exact=True,
            check_names=True,
            obj=f"engineered column {col!r}",
        )


# ── Account-baseline deviation & sequence features (point-in-time, IMP-011) ───
#
# amount_to_prior_mean_ratio and amount_to_prior_max_ratio implement §9's
# "deviation from the account's baseline"; hours_since_last_txn implements §9's
# "sequence signals". All three are computed in the single-pass traversal from
# strictly-prior rows within the account. Per the IMP-005 standing rule, these
# introduce new accumulations (running mean/max, prior timestamp), so each is
# covered below by a Hypothesis property test verifying the point-in-time
# boundary (no feature at row i reads any row j >= i).


def test_baseline_features_none_on_first_transaction() -> None:
    row = build_features(_make_df([{"account_id": "C1", "step": 1, "amount": 100.0}])).iloc[0]
    assert pd.isna(row["amount_to_prior_mean_ratio"])
    assert pd.isna(row["amount_to_prior_max_ratio"])
    assert pd.isna(row["hours_since_last_txn"])


def test_amount_to_prior_mean_ratio_values() -> None:
    df = _make_df(
        [
            {"account_id": "C1", "step": 1, "amount": 100.0},
            {"account_id": "C1", "step": 2, "amount": 300.0},
            {"account_id": "C1", "step": 3, "amount": 200.0},
        ]
    )
    result = build_features(df).sort_values("step").reset_index(drop=True)
    assert result.iloc[1]["amount_to_prior_mean_ratio"] == pytest.approx(3.0)  # 300 / 100
    assert result.iloc[2]["amount_to_prior_mean_ratio"] == pytest.approx(1.0)  # 200 / ((100+300)/2)


def test_amount_to_prior_max_ratio_values() -> None:
    df = _make_df(
        [
            {"account_id": "C1", "step": 1, "amount": 100.0},
            {"account_id": "C1", "step": 2, "amount": 300.0},
            {"account_id": "C1", "step": 3, "amount": 150.0},
        ]
    )
    result = build_features(df).sort_values("step").reset_index(drop=True)
    assert result.iloc[1]["amount_to_prior_max_ratio"] == pytest.approx(3.0)  # 300 / 100
    assert result.iloc[2]["amount_to_prior_max_ratio"] == pytest.approx(0.5)  # 150 / 300


def test_hours_since_last_txn_values() -> None:
    df = _make_df(
        [
            {"account_id": "C1", "step": 1},
            {"account_id": "C1", "step": 5},  # +4 h
            {"account_id": "C1", "step": 30},  # +25 h
        ]
    )
    result = build_features(df).sort_values("step").reset_index(drop=True)
    assert result.iloc[1]["hours_since_last_txn"] == pytest.approx(4.0)
    assert result.iloc[2]["hours_since_last_txn"] == pytest.approx(25.0)


def test_baseline_features_isolated_per_account() -> None:
    """Account C1's history must never influence account C2's baseline/sequence."""
    df = _make_df(
        [
            {"account_id": "C1", "step": 1, "amount": 100.0},
            {"account_id": "C2", "step": 2, "amount": 500.0},
        ]
    )
    result = build_features(df)
    c2 = result[result["account_id"] == "C2"].iloc[0]
    assert pd.isna(c2["amount_to_prior_mean_ratio"])
    assert pd.isna(c2["amount_to_prior_max_ratio"])
    assert pd.isna(c2["hours_since_last_txn"])


def test_prior_mean_ratio_none_when_prior_amounts_zero() -> None:
    df = _make_df(
        [
            {"account_id": "C1", "step": 1, "amount": 0.0},
            {"account_id": "C1", "step": 2, "amount": 100.0},
        ]
    )
    result = build_features(df).sort_values("step").reset_index(drop=True)
    # Prior mean and max are both 0 → ratios undefined → NaN (mirrors frac guard).
    assert pd.isna(result.iloc[1]["amount_to_prior_mean_ratio"])
    assert pd.isna(result.iloc[1]["amount_to_prior_max_ratio"])


@given(st.lists(_ROW_STRATEGY, min_size=1, max_size=15))
@settings(max_examples=200, deadline=None)
def test_features_amount_baseline_prior_invariant(rows: list[dict]) -> None:
    """amount_to_prior_{mean,max}_ratio reference only strictly-prior rows (R2).

    Ground truth uses the prior amounts of rows j < i within each account group;
    a value that read any row j >= i would diverge. Covers the running-mean and
    running-max accumulations introduced in IMP-011 (IMP-005 standing rule).
    """
    pairs = [(r["account_id"], r["step"]) for r in rows]
    assume(len(pairs) == len(set(pairs)))

    # Hypothesis can generate denormal-tiny amounts whose ratio overflows to inf;
    # both the code and the ground truth compute inf and agree, so silence the
    # cosmetic numpy overflow warning (unreachable with real, bounded PaySim data).
    with np.errstate(over="ignore"):
        result = build_features(_make_df(rows))
    for _, group in result.groupby("account_id"):
        grp = group.sort_values("event_ts", kind="stable").reset_index(drop=True)
        for i in range(len(grp)):
            amt = float(grp.iloc[i]["amount"])
            prior = [float(grp.iloc[j]["amount"]) for j in range(i)]
            mean_actual = grp.iloc[i]["amount_to_prior_mean_ratio"]
            max_actual = grp.iloc[i]["amount_to_prior_max_ratio"]

            if not prior:
                assert pd.isna(mean_actual) and pd.isna(max_actual)
                continue

            mean_prior = sum(prior) / len(prior)
            if mean_prior > 0.0:
                assert math.isclose(mean_actual, amt / mean_prior, rel_tol=1e-9, abs_tol=1e-9)
            else:
                assert pd.isna(mean_actual)

            max_prior = max(prior)
            if max_prior > 0.0:
                assert math.isclose(max_actual, amt / max_prior, rel_tol=1e-9, abs_tol=1e-9)
            else:
                assert pd.isna(max_actual)


@given(st.lists(_ROW_STRATEGY, min_size=1, max_size=15))
@settings(max_examples=200, deadline=None)
def test_features_hours_since_last_prior_invariant(rows: list[dict]) -> None:
    """hours_since_last_txn is the gap to the immediately prior row (j = i-1) only.

    Covers the prior-timestamp sequence accumulation introduced in IMP-011
    (IMP-005 standing rule): row 0 of each account has no prior (NaN); every
    later row equals the elapsed hours since its account's previous transaction.
    """
    pairs = [(r["account_id"], r["step"]) for r in rows]
    assume(len(pairs) == len(set(pairs)))

    with np.errstate(over="ignore"):
        result = build_features(_make_df(rows))
    for _, group in result.groupby("account_id"):
        grp = group.sort_values("event_ts", kind="stable").reset_index(drop=True)
        for i in range(len(grp)):
            actual = grp.iloc[i]["hours_since_last_txn"]
            if i == 0:
                assert pd.isna(actual)
            else:
                gap = grp.iloc[i]["event_ts"] - grp.iloc[i - 1]["event_ts"]
                expected = gap.total_seconds() / 3600.0
                assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
