"""Shared test fixtures.

Unit tests run against an in-memory SQLite database via the same models and
data-access layer used by the running app, keeping the suite fast and hermetic.

For M2 (scorer / leakage gate) the fixtures also provide a lean ``ModelConfig``
and a synthetic feature-dataset factory. The synthetic generator can produce a
"behavioural" dataset (fraud driven by behavioural features; balance artifacts are
noise) or a "leaky" dataset (fraud driven almost entirely by a balance artifact),
so the leakage gate can be exercised in both directions.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.orm import Session, sessionmaker

from tfm.config.settings import (
    CalibrationConfig,
    LeakageGateConfig,
    ModelConfig,
    Settings,
    SplitConfig,
)
from tfm.data.features import FEATURE_COLUMNS
from tfm.persistence.db import create_db_engine, create_session_factory
from tfm.persistence.models import Base

_BALANCE_ARTIFACTS = [
    "bal_orig_before",
    "bal_orig_after",
    "frac_bal_orig_moved",
    "orig_account_emptied",
]
_AUGMENTED = ["bal_dest_before", "bal_dest_after"]
_TYPES = ["type_payment", "type_transfer", "type_cash_out", "type_cash_in", "type_debit"]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="ci",
        log_format="console",
        database_url="sqlite+pysqlite:///:memory:",
        config_dir="config",
    )


@pytest.fixture
def session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = create_db_engine(settings)
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    sess = session_factory()
    try:
        yield sess
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# M2 fixtures: model config + synthetic feature datasets
# ---------------------------------------------------------------------------


@pytest.fixture
def m2_model_config() -> ModelConfig:
    """A lean ModelConfig for fast M2 tests (fewer permutation repeats)."""
    return ModelConfig(
        split=SplitConfig(train_end_step=500, val_end_step=580),
        seed=42,
        eval_threshold=0.5,
        balance_artifact_features=list(_BALANCE_ARTIFACTS),
        augmented_features=list(_AUGMENTED),
        calibration=CalibrationConfig(method="auto", min_fraud_for_isotonic=500),
        leakage_gate=LeakageGateConfig(
            importance_repeats=2,
            min_behavioural_pr_auc=0.50,
            max_ablation_pr_auc_delta=0.20,
        ),
    )


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def _zscore(x: np.ndarray) -> np.ndarray:
    std = x.std()
    return (x - x.mean()) / std if std > 0 else x - x.mean()


def _build_synth(kind: str, n: int, seed: int) -> pd.DataFrame:
    """Construct a features-shaped DataFrame with a controllable fraud signal.

    Columns: all of FEATURE_COLUMNS, the augmented destination-balance features,
    plus ``step``, ``label`` and identifier columns. The output is already in the
    shape produced by ``build_features`` (M2 does not re-derive features).
    """
    rng = np.random.default_rng(seed)

    amount = rng.lognormal(mean=5.0, sigma=1.5, size=n)
    txn_count_24h = rng.poisson(3, size=n)
    amount_sum_24h = amount * rng.uniform(0.0, 3.0, size=n)
    is_new = rng.random(n) < 0.3
    distinct = rng.poisson(2, size=n)

    bal_before = rng.lognormal(mean=8.0, sigma=1.0, size=n)

    if kind == "behavioural":
        # Fraud driven by behavioural features; balance artifacts are noise.
        emptied = rng.random(n) < 0.2
        frac = rng.uniform(0.0, 1.0, size=n)
        bal_after = bal_before * rng.uniform(0.0, 1.0, size=n)
        z = (
            1.3 * _zscore(txn_count_24h.astype(float))
            + 1.1 * is_new.astype(float)
            + 0.9 * _zscore(np.log1p(amount))
            - 1.0
        )
        label = rng.random(n) < _sigmoid(z)
    elif kind == "leaky":
        # Fraud driven almost entirely by a balance artifact; behavioural = noise.
        emptied = rng.random(n) < 0.3
        flip = rng.random(n) < 0.03
        label = np.logical_xor(emptied, flip)
        frac = np.where(emptied, rng.uniform(0.9, 1.0, size=n), rng.uniform(0.0, 0.5, size=n))
        bal_after = np.where(emptied, 0.0, bal_before * rng.uniform(0.1, 1.0, size=n))
    else:  # pragma: no cover - guard
        raise ValueError(f"unknown synth kind: {kind}")

    # One-hot transaction types (exactly one true per row).
    type_idx = rng.integers(0, len(_TYPES), size=n)
    type_cols = {t: (type_idx == i) for i, t in enumerate(_TYPES)}

    # Merchant destinations (~40%) carry no destination-balance signal (NaN).
    is_merchant = rng.random(n) < 0.4
    bal_dest_before = np.where(is_merchant, np.nan, rng.lognormal(7.0, 1.0, size=n))
    bal_dest_after = np.where(is_merchant, np.nan, rng.lognormal(7.0, 1.0, size=n))

    data = {
        "txn_id": [f"synth-{i:07d}" for i in range(n)],
        "account_id": [f"C{rng.integers(0, n):06d}" for _ in range(n)],
        "counterparty_id": [f"X{rng.integers(0, n):06d}" for _ in range(n)],
        "step": rng.integers(1, 745, size=n),
        "amount": amount,
        "bal_orig_before": bal_before,
        "bal_orig_after": bal_after,
        "frac_bal_orig_moved": frac,
        "orig_account_emptied": emptied,
        "txn_count_24h": txn_count_24h,
        "amount_sum_24h": amount_sum_24h,
        "is_new_counterparty": is_new,
        "distinct_counterparties_seen": distinct,
        "bal_dest_before": bal_dest_before,
        "bal_dest_after": bal_dest_after,
        "label": label,
    }
    data.update(type_cols)
    frame = pd.DataFrame(data)

    # Ensure every FEATURE_COLUMNS entry is present.
    missing = [c for c in FEATURE_COLUMNS if c not in frame.columns]
    assert not missing, f"synthetic frame missing feature columns: {missing}"
    return frame


@pytest.fixture
def make_synth() -> Callable[..., pd.DataFrame]:
    """Factory: ``make_synth(kind, n=1600, seed=0)`` → synthetic features DataFrame."""

    def _factory(kind: str = "behavioural", n: int = 1600, seed: int = 0) -> pd.DataFrame:
        return _build_synth(kind, n, seed)

    return _factory
