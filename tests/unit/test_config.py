"""Config loading and validation tests (fail-fast on drift — register risk R13)."""

from __future__ import annotations

import pytest

from tfm.config.settings import (
    KNOWN_RULE_IDS,
    AppConfig,
    QueuePolicyConfig,
    RulesConfig,
    ScoreBandsConfig,
    Settings,
    ThresholdsConfig,
    load_config,
)


def test_load_config_from_repo_files(settings: Settings) -> None:
    config = load_config(settings)
    assert isinstance(config, AppConfig)
    # Queue defaults to risk (FR-14).
    assert config.queue_policy.default_sort == "risk"
    # Only the four V1-demonstrable rules are enabled (FR-6/FR-7).
    assert set(config.rules.enabled) <= KNOWN_RULE_IDS


def test_score_bands_reject_inverted_boundaries() -> None:
    with pytest.raises(ValueError):
        ThresholdsConfig(score_bands=ScoreBandsConfig(low_max=0.9, high_min=0.1))


def test_rules_reject_unknown_rule() -> None:
    with pytest.raises(ValueError):
        RulesConfig(enabled=["not_a_rule"], parameters={"not_a_rule": {}})


def test_rules_reject_missing_parameters() -> None:
    with pytest.raises(ValueError):
        RulesConfig(enabled=["velocity"], parameters={})


def test_queue_policy_default_must_be_allowed() -> None:
    with pytest.raises(ValueError):
        QueuePolicyConfig(default_sort="risk", allowed_sorts=["case_age"])
