"""Typed configuration for Transaction Fraud Monitoring (V1).

Two kinds of configuration are loaded and validated at startup (fail-fast):

* Environment settings (``Settings``): process/runtime configuration from env vars.
* Governance-configurable knobs (``AppConfig``): the score-band thresholds,
  rule parameters, queue-ordering policy, and the
  rationale-depth policy. These live in versioned YAML under ``CONFIG_DIR``.

This module only *loads and validates* configuration. It contains no scoring,
rule, recommendation, or workflow logic. The values shipped in ``config/*.yaml``
are placeholders to be justified within their milestones (for thresholds,
for rule parameters).

Note on the rationale engagement floor: the requirement that every disposition
carry at least a structured reason code is an *architectural invariant* enforced
by the Disposition Service and a database ``NOT NULL`` constraint. It is
deliberately not represented here; this file configures only the depth of
rationale *above* the floor.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The four V1-demonstrable rule identifiers. Dormant-account reactivation
# is explicitly out of V1 scope and is not listed.
KNOWN_RULE_IDS: frozenset[str] = frozenset(
    {"velocity", "new_beneficiary_large", "mule_passthrough", "account_draining"}
)
DISPOSITION_ACTIONS: frozenset[str] = frozenset({"clear", "hold", "escalate"})


class Settings(BaseSettings):
    """Process/runtime settings, read from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "ci", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    database_url: str = "postgresql+psycopg://tfm:tfm@db:5432/tfm"
    config_dir: str = "config"

    default_analyst_id: str = "demo-analyst"

    # LLM is optional; unset means the templated explanation pathway.
    llm_enabled: bool = False
    llm_provider: str = ""
    llm_api_key: str = ""

    api_base_url: str = "http://api:8000"


class ScoreBandsConfig(BaseModel):
    """Score-band boundaries mapped by the recommendation policy.

    band = low       if score < low_max
         = high      if score >= high_min
         = borderline otherwise
    """

    low_max: float = Field(ge=0.0, le=1.0)
    high_min: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> ScoreBandsConfig:
        if self.low_max > self.high_min:
            raise ValueError("thresholds: low_max must be <= high_min")
        return self


class RecommendationConfig(BaseModel):
    """Recommendation-policy parameters.

    ``escalating_rules`` are the rule ids that, when fired, warrant an *escalate*
    recommendation; any other fired rule contributes a *hold*. Governance-owned;
    the policy sources escalation from config, not code.
    """

    escalating_rules: list[str] = []

    @model_validator(mode="after")
    def _known_rules(self) -> RecommendationConfig:
        unknown = set(self.escalating_rules) - KNOWN_RULE_IDS
        if unknown:
            raise ValueError(f"recommendation: unknown escalating rule ids: {sorted(unknown)}")
        return self


class ThresholdsConfig(BaseModel):
    score_bands: ScoreBandsConfig
    recommendation: RecommendationConfig = Field(default_factory=RecommendationConfig)


class RulesConfig(BaseModel):
    """Rule enablement and parameters."""

    enabled: list[str]
    parameters: dict[str, dict[str, float]]

    @model_validator(mode="after")
    def _known_and_parameterised(self) -> RulesConfig:
        unknown = set(self.enabled) - KNOWN_RULE_IDS
        if unknown:
            raise ValueError(f"rules: unknown rule ids enabled: {sorted(unknown)}")
        missing = [r for r in self.enabled if r not in self.parameters]
        if missing:
            raise ValueError(f"rules: enabled rules missing parameters: {missing}")
        return self


class QueuePolicyConfig(BaseModel):
    """Configurable, visible, re-sortable queue ordering. Default: risk."""

    default_sort: str
    allowed_sorts: list[str]
    order: Literal["asc", "desc"] = "desc"

    @model_validator(mode="after")
    def _default_allowed(self) -> QueuePolicyConfig:
        if self.default_sort not in self.allowed_sorts:
            raise ValueError("queue_policy: default_sort must be within allowed_sorts")
        return self


class GovernanceConfig(BaseModel):
    """Rationale depth *above* the architectural engagement floor."""

    richer_rationale_required_for_actions: list[str]
    richer_rationale_required_on_deviation: bool

    @model_validator(mode="after")
    def _valid_actions(self) -> GovernanceConfig:
        unknown = set(self.richer_rationale_required_for_actions) - DISPOSITION_ACTIONS
        if unknown:
            raise ValueError(f"governance: unknown actions: {sorted(unknown)}")
        return self


class AppConfig(BaseModel):
    """Aggregate of the governance-configurable knobs."""

    thresholds: ThresholdsConfig
    rules: RulesConfig
    queue_policy: QueuePolicyConfig
    governance: GovernanceConfig


# ---------------------------------------------------------------------------
# Model / scoring configuration — config/model.yaml
# ---------------------------------------------------------------------------


class SplitConfig(BaseModel):
    """Out-of-time split boundaries by PaySim step."""

    train_end_step: int = Field(gt=0)
    val_end_step: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> SplitConfig:
        if self.train_end_step >= self.val_end_step:
            raise ValueError("model.split: train_end_step must be < val_end_step")
        return self


class CalibrationConfig(BaseModel):
    """Probability-calibration policy."""

    method: Literal["auto", "isotonic", "sigmoid"] = "auto"
    min_fraud_for_isotonic: int = Field(ge=0, default=500)


class LeakageGateConfig(BaseModel):
    """Decision-support defaults for the simulator-leakage gate.

    These parameters *support* the evidence-based verdict; they do not define it.
    """

    importance_repeats: int = Field(gt=0, default=5)
    min_behavioural_pr_auc: float = Field(ge=0.0, le=1.0, default=0.50)
    max_ablation_pr_auc_delta: float = Field(ge=0.0, le=1.0, default=0.20)


class ModelConfig(BaseModel):
    """Scorer/training configuration.

    Versioned configuration for the scoring milestone: split boundaries, seed,
    evaluation reporting threshold, the quarantined balance-artifact feature set,
    the comparator-only augmented features, the calibration policy, and the
    leakage-gate decision-support defaults.
    """

    split: SplitConfig
    seed: int = 42
    eval_threshold: float = Field(ge=0.0, le=1.0, default=0.5)
    balance_artifact_features: list[str]
    augmented_features: list[str]
    calibration: CalibrationConfig
    leakage_gate: LeakageGateConfig


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"missing config file: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"config file is not a mapping: {path}")
    return data


def load_config(settings: Settings) -> AppConfig:
    """Load and validate all governance-configurable knobs. Fails fast on drift."""

    config_dir = Path(settings.config_dir)
    return AppConfig(
        thresholds=ThresholdsConfig(**_read_yaml(config_dir / "thresholds.yaml")),
        rules=RulesConfig(**_read_yaml(config_dir / "rules.yaml")),
        queue_policy=QueuePolicyConfig(**_read_yaml(config_dir / "queue_policy.yaml")),
        governance=GovernanceConfig(**_read_yaml(config_dir / "governance.yaml")),
    )


def load_model_config(settings: Settings) -> ModelConfig:
    """Load and validate the scorer/training configuration. Fails fast."""

    config_dir = Path(settings.config_dir)
    return ModelConfig(**_read_yaml(config_dir / "model.yaml"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
