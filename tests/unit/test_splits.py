"""Unit tests for the out-of-time split policy (§8.3).

Verifies temporal ordering, disjointness, full coverage, reproducibility, and
that invalid boundary parameters are rejected.

Spec: §8.3, FR-22, R2 (Addendum §5 — temporal leakage guard).
"""

from __future__ import annotations

import pandas as pd
import pytest

from tfm.data.splits import (
    DEFAULT_TRAIN_END_STEP,
    DEFAULT_VAL_END_STEP,
    DataSplit,
    make_out_of_time_split,
)


@pytest.fixture
def paysim_like_df() -> pd.DataFrame:
    """Minimal DataFrame spanning steps 1–600 with one row per step."""
    return pd.DataFrame({"step": list(range(1, 601)), "label": [0] * 600})


# ── DataSplit structure ───────────────────────────────────────────────────────


def test_make_out_of_time_split_returns_data_split(paysim_like_df) -> None:
    result = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    assert isinstance(result, DataSplit)


def test_split_boundaries_stored(paysim_like_df) -> None:
    split = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    assert split.train_end_step == 400
    assert split.val_end_step == 500


# ── Temporal ordering invariants ─────────────────────────────────────────────


def test_train_steps_all_le_train_end(paysim_like_df) -> None:
    split = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    assert split.train["step"].max() <= 400


def test_val_steps_between_boundaries(paysim_like_df) -> None:
    split = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    assert split.val["step"].min() > 400
    assert split.val["step"].max() <= 500


def test_test_steps_all_gt_val_end(paysim_like_df) -> None:
    split = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    assert split.test["step"].min() > 500


# ── Disjointness ─────────────────────────────────────────────────────────────


def test_no_overlap_train_val(paysim_like_df) -> None:
    split = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    common = set(split.train["step"]) & set(split.val["step"])
    assert len(common) == 0


def test_no_overlap_val_test(paysim_like_df) -> None:
    split = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    common = set(split.val["step"]) & set(split.test["step"])
    assert len(common) == 0


def test_no_overlap_train_test(paysim_like_df) -> None:
    split = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    common = set(split.train["step"]) & set(split.test["step"])
    assert len(common) == 0


# ── Full coverage ─────────────────────────────────────────────────────────────


def test_union_covers_all_rows(paysim_like_df) -> None:
    split = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    total = len(split.train) + len(split.val) + len(split.test)
    assert total == len(paysim_like_df)


def test_union_steps_equals_input_steps(paysim_like_df) -> None:
    split = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    all_steps = set(split.train["step"]) | set(split.val["step"]) | set(split.test["step"])
    assert all_steps == set(paysim_like_df["step"])


# ── Reproducibility ───────────────────────────────────────────────────────────


def test_split_is_deterministic(paysim_like_df) -> None:
    """Same input always produces same split — no random sampling (NFR-5)."""
    s1 = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    s2 = make_out_of_time_split(paysim_like_df, train_end_step=400, val_end_step=500)
    pd.testing.assert_frame_equal(s1.train.reset_index(drop=True), s2.train.reset_index(drop=True))
    pd.testing.assert_frame_equal(s1.val.reset_index(drop=True), s2.val.reset_index(drop=True))
    pd.testing.assert_frame_equal(s1.test.reset_index(drop=True), s2.test.reset_index(drop=True))


# ── Default boundaries ────────────────────────────────────────────────────────


def test_default_boundaries_match_constants() -> None:
    assert DEFAULT_TRAIN_END_STEP == 500
    assert DEFAULT_VAL_END_STEP == 580


def test_default_split_proportions() -> None:
    """Default boundaries should give roughly 67 / 11 / 22 % for 744 steps."""
    df = pd.DataFrame({"step": list(range(1, 745))})
    split = make_out_of_time_split(df)
    train_frac = len(split.train) / len(df)
    val_frac = len(split.val) / len(df)
    test_frac = len(split.test) / len(df)
    assert 0.65 < train_frac < 0.70
    assert 0.09 < val_frac < 0.13
    assert 0.20 < test_frac < 0.25


# ── Invalid inputs ────────────────────────────────────────────────────────────


def test_raises_if_step_column_missing() -> None:
    df = pd.DataFrame({"amount": [100.0, 200.0]})
    with pytest.raises(ValueError, match="step"):
        make_out_of_time_split(df)


def test_raises_if_train_end_equals_val_end(paysim_like_df) -> None:
    with pytest.raises(ValueError, match="strictly less than"):
        make_out_of_time_split(paysim_like_df, train_end_step=500, val_end_step=500)


def test_raises_if_train_end_greater_than_val_end(paysim_like_df) -> None:
    with pytest.raises(ValueError, match="strictly less than"):
        make_out_of_time_split(paysim_like_df, train_end_step=600, val_end_step=400)
