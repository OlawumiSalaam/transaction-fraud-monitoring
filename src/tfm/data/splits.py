"""Out-of-time split policy.

Random train/test splits are prohibited: a random split can leak future
information into the training set through features that aggregate over time.
The only permitted split is temporal: train
on earlier data, evaluate on later data that the model never saw during training.

PaySim has 744 steps (~31 days of hourly simulation).  The reference split:
  train:  steps in [1, TRAIN_END]           — the earlier window
  val:    steps in (TRAIN_END, VAL_END]      — calibration and threshold tuning
  test:   steps in (VAL_END, 744]            — out-of-time evaluation

Both boundaries are fixed constants, not random seeds, so the split is
reproducible from the data file alone.

The split is determined by step (PaySim's original time index), not event_ts,
to avoid any dependence on the base-epoch implementation choice in ingest.py.
Architectural responsibility: owns the train/val/test temporal boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Reference split boundaries for PaySim's 744-step simulation.
# Approximate proportions: 67 % train, 11 % val, 22 % test.
# These are the V1 defaults; they may be overridden via the function arguments.
DEFAULT_TRAIN_END_STEP: int = 500
DEFAULT_VAL_END_STEP: int = 580


@dataclass(frozen=True)
class DataSplit:
    """The three disjoint temporal subsets of the PaySim dataset.

    Invariant: all transactions in train have step <= train_end_step,
    all in val have train_end_step < step <= val_end_step, and all in test
    have step > val_end_step.  The three sets are disjoint and their union
    equals the input DataFrame.

    """

    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    train_end_step: int
    val_end_step: int


def make_out_of_time_split(
    df: pd.DataFrame,
    train_end_step: int = DEFAULT_TRAIN_END_STEP,
    val_end_step: int = DEFAULT_VAL_END_STEP,
) -> DataSplit:
    """Partition transactions into train / val / test by step value.

    The split is purely temporal — no random sampling.  The same input
    DataFrame and boundary parameters always produce the same split.

    INVARIANT: max(train.step) <= train_end_step < min(val.step) <=
    val_end_step < min(test.step).

    Raises ValueError if the 'step' column is absent or boundaries are
    invalid (train_end_step must be strictly less than val_end_step).

    The temporal split prevents test-set information from leaking into
    training features.
    """
    if "step" not in df.columns:
        raise ValueError("DataFrame must contain a 'step' column for the OOT split")
    if train_end_step >= val_end_step:
        raise ValueError(
            f"train_end_step ({train_end_step}) must be strictly less than "
            f"val_end_step ({val_end_step})"
        )

    train = df[df["step"] <= train_end_step].copy()
    val = df[(df["step"] > train_end_step) & (df["step"] <= val_end_step)].copy()
    test = df[df["step"] > val_end_step].copy()

    return DataSplit(
        train=train,
        val=val,
        test=test,
        train_end_step=train_end_step,
        val_end_step=val_end_step,
    )
