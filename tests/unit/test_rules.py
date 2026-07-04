"""Unit tests for the deterministic rule engine (FR-6, M3).

Each real rule fires deterministically on constructed fixtures and produces an
auditable RuleHit; parameters come from config; the engine is independent of the
ML score; and mule_passthrough is a documented no-op pending M4 peer evidence
(IC-M3-01).

Spec: FR-6, FR-7, §6.5, §6.6; Addendum §4.
"""

from __future__ import annotations

import inspect

from tfm.config.settings import KNOWN_RULE_IDS, RulesConfig, Settings, load_config
from tfm.rules.definitions import (
    REGISTRY,
    account_draining,
    mule_passthrough,
    new_beneficiary_large,
    velocity,
)
from tfm.rules.engine import RuleEngine
from tfm.schema.evidence import FeatureVector, RuleHit

_DRAINING_PARAMS = {"min_fraction_of_balance": 0.9}
_VELOCITY_PARAMS = {"window_hours": 24.0, "max_transactions": 10.0}
_NBL_PARAMS = {"amount_threshold": 200000.0}
_MULE_PARAMS = {"inbound_outbound_window_hours": 2.0, "min_passthrough_fraction": 0.9}


def _fv(**overrides: object) -> FeatureVector:
    """Build a FeatureVector for rule tests (benign defaults; override to trigger)."""
    base: dict[str, object] = {
        "txn_id": "t1",
        "account_id": "C1",
        "counterparty_id": "M1",
        "amount": 100.0,
        "type_payment": False,
        "type_transfer": True,
        "type_cash_out": False,
        "type_cash_in": False,
        "type_debit": False,
        "bal_orig_before": 1000.0,
        "bal_orig_after": 900.0,
        "bal_dest_before": None,
        "bal_dest_after": None,
        "frac_bal_orig_moved": 0.1,
        "orig_account_emptied": False,
        "txn_count_24h": 0,
        "amount_sum_24h": 0.0,
        "is_new_counterparty": True,
        "distinct_counterparties_seen": 0,
    }
    base.update(overrides)
    return FeatureVector(**base)  # type: ignore[arg-type]


def _rules_config(enabled: list[str] | None = None) -> RulesConfig:
    return RulesConfig(
        enabled=enabled or sorted(KNOWN_RULE_IDS),
        parameters={
            "account_draining": dict(_DRAINING_PARAMS),
            "velocity": dict(_VELOCITY_PARAMS),
            "new_beneficiary_large": dict(_NBL_PARAMS),
            "mule_passthrough": dict(_MULE_PARAMS),
        },
    )


# ── account_draining ──────────────────────────────────────────────────────────


def test_account_draining_fires_at_or_above_threshold() -> None:
    fv = _fv(frac_bal_orig_moved=0.95, orig_account_emptied=True)
    hit = account_draining(fv, _DRAINING_PARAMS)
    assert hit is not None
    assert hit.rule_id == "account_draining"
    assert hit.evidence["frac_bal_orig_moved"] == 0.95
    assert hit.evidence["min_fraction_of_balance"] == 0.9


def test_account_draining_does_not_fire_below_threshold() -> None:
    assert account_draining(_fv(frac_bal_orig_moved=0.5), _DRAINING_PARAMS) is None


def test_account_draining_none_fraction_does_not_fire() -> None:
    # frac is None when the origin balance was 0 (can't drain an empty account).
    assert account_draining(_fv(frac_bal_orig_moved=None), _DRAINING_PARAMS) is None


# ── velocity ──────────────────────────────────────────────────────────────────


def test_velocity_fires_at_threshold() -> None:
    hit = velocity(_fv(txn_count_24h=10), _VELOCITY_PARAMS)
    assert hit is not None
    assert hit.rule_id == "velocity"
    assert hit.evidence["txn_count_24h"] == 10


def test_velocity_does_not_fire_below_threshold() -> None:
    assert velocity(_fv(txn_count_24h=9), _VELOCITY_PARAMS) is None


# ── new_beneficiary_large ─────────────────────────────────────────────────────


def test_new_beneficiary_large_fires_when_new_and_large() -> None:
    hit = new_beneficiary_large(_fv(is_new_counterparty=True, amount=250000.0), _NBL_PARAMS)
    assert hit is not None
    assert hit.rule_id == "new_beneficiary_large"


def test_new_beneficiary_large_not_fire_when_not_new() -> None:
    fv = _fv(is_new_counterparty=False, amount=250000.0)
    assert new_beneficiary_large(fv, _NBL_PARAMS) is None


def test_new_beneficiary_large_not_fire_when_small() -> None:
    assert new_beneficiary_large(_fv(is_new_counterparty=True, amount=100.0), _NBL_PARAMS) is None


# ── mule_passthrough (documented no-op — IC-M3-01) ────────────────────────────


def test_mule_passthrough_never_fires_pending_m4_peer_evidence() -> None:
    # Even on a full-passthrough-looking transaction it is a no-op until M4.
    fv = _fv(frac_bal_orig_moved=1.0, orig_account_emptied=True)
    assert mule_passthrough(fv, _MULE_PARAMS) is None


# ── engine ────────────────────────────────────────────────────────────────────


def test_engine_returns_firing_rules_in_enabled_order() -> None:
    engine = RuleEngine(_rules_config(["account_draining", "velocity", "new_beneficiary_large"]))
    fv = _fv(
        frac_bal_orig_moved=1.0,
        orig_account_emptied=True,
        txn_count_24h=12,
        is_new_counterparty=True,
        amount=300000.0,
    )
    assert [h.rule_id for h in engine.evaluate(fv)] == [
        "account_draining",
        "velocity",
        "new_beneficiary_large",
    ]


def test_engine_no_hits_on_benign_transaction() -> None:
    engine = RuleEngine(_rules_config())
    fv = _fv(frac_bal_orig_moved=0.05, txn_count_24h=1, is_new_counterparty=False, amount=100.0)
    assert engine.evaluate(fv) == []


def test_engine_respects_enabled_subset() -> None:
    engine = RuleEngine(_rules_config(["account_draining"]))
    fv = _fv(frac_bal_orig_moved=1.0, txn_count_24h=99, is_new_counterparty=True, amount=1e9)
    assert [h.rule_id for h in engine.evaluate(fv)] == ["account_draining"]


def test_engine_is_deterministic() -> None:
    engine = RuleEngine(_rules_config())
    fv = _fv(frac_bal_orig_moved=1.0, orig_account_emptied=True)
    assert engine.evaluate(fv) == engine.evaluate(fv)


def test_engine_evaluate_is_independent_of_score() -> None:
    # Structural guarantee: evaluate consumes only the FeatureVector, never a Score.
    assert list(inspect.signature(RuleEngine.evaluate).parameters) == ["self", "features"]


def test_registry_covers_exactly_known_rule_ids() -> None:
    assert set(REGISTRY) == set(KNOWN_RULE_IDS)


def test_rule_hit_is_auditable_evidence() -> None:
    hit = account_draining(_fv(frac_bal_orig_moved=0.95, amount=500.0), _DRAINING_PARAMS)
    assert isinstance(hit, RuleHit)
    assert hit.summary  # human-readable statement
    assert hit.evidence["amount"] == 500.0
    assert hit.evidence["min_fraction_of_balance"] == 0.9


def test_shipped_rules_config_evaluates() -> None:
    config = load_config(Settings(config_dir="config"))
    engine = RuleEngine(config.rules)
    fv = _fv(frac_bal_orig_moved=1.0, orig_account_emptied=True)
    assert "account_draining" in [h.rule_id for h in engine.evaluate(fv)]
