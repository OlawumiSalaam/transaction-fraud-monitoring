"""Rule Engine: deterministic if-then evaluation over the shared substrate.

The ``RuleEngine`` evaluates the config-enabled rules against a single transaction's
``FeatureVector`` and returns the ``RuleHit``s — the primary operational **evidence**
source for a case. It is a pure deterministic function: no I/O, no probabilistic
step, and NO dependence on the ML score. The score and the rule hits are produced
independently and both preserved as evidence (Principle: Layer
Separation). Rule outputs are kept visibly distinct from model outputs.

This matters especially now that the scorer is gate-ineligible (excluded from the
operational path under): the deterministic rule engine continues to operate as
designed and is the case's primary evidence source — graceful degradation, not a
workaround.

Contract (Rule Engine):
  In:  the feature substrate for a transaction (``FeatureVector``).
  Out: ```` (each carrying the fields that made it fire).
"""

from __future__ import annotations

from tfm.config.settings import RulesConfig
from tfm.rules.definitions import REGISTRY
from tfm.schema.evidence import FeatureVector, RuleHit


class RuleEngine:
    """Evaluate the enabled deterministic rules. Independent of the score.

    Constructed from the versioned ``RulesConfig`` (enablement + parameters). The API
    layer injects a ``RuleEngine`` so the enabled rule set is a configuration change,
    not a code change (Governance: parameters are versioned config, not literals).
    """

    def __init__(self, config: RulesConfig) -> None:
        self._config = config

    def evaluate(self, features: FeatureVector) -> list[RuleHit]:
        """Return the RuleHits for one transaction, in the config's enabled order.

        Pure and deterministic: identical inputs always yield identical hits, and no
        ML score is consulted. Rules that do not fire contribute nothing.
        """
        hits: list[RuleHit] = []
        for rule_id in self._config.enabled:
            definition = REGISTRY[rule_id]
            params = self._config.parameters[rule_id]
            hit = definition(features, params)
            if hit is not None:
                hits.append(hit)
        return hits
