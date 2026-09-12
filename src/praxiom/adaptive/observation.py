"""R9 observation-strategy optimization (R7 validator is the floor)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from praxiom.retrieval.validator import AdaptiveValidator, ValidationContext, ValidationDecision

__all__ = ["ObservationPolicy", "ObservationDecision"]

CONFIDENCE_FLOOR = 0.8


@dataclass(frozen=True)
class ObservationDecision:
    method: str  # cheap-validate | full-observe
    reason: str


@dataclass(frozen=True, kw_only=True)
class ObservationPolicy:
    confidence_floor: float = CONFIDENCE_FLOOR

    def decide(self, *, validated_confidence: float, next_is_state_sensitive: bool,
               revision_invalidated: bool,
               validator_decision: ValidationDecision | None = None,
               validation_context: ValidationContext | None = None,
               risk: str = "low", reversibility: str = "reversible",
               human_gate: bool = False) -> ObservationDecision:
        if (
            type(validated_confidence) not in (int, float)
            or not math.isfinite(float(validated_confidence))
            or type(next_is_state_sensitive) is not bool
            or type(revision_invalidated) is not bool
            or type(human_gate) is not bool
            or type(self.confidence_floor) not in (int, float)
            or not math.isfinite(float(self.confidence_floor))
        ):
            return ObservationDecision("full-observe", "malformed-optimization-signal")
        decision = validator_decision
        if validation_context is not None:
            if (
                not isinstance(validation_context, ValidationContext)
                or type(validation_context.confidence) not in (int, float)
                or not math.isfinite(float(validation_context.confidence))
                or not (0.0 <= float(validation_context.confidence) <= 1.0)
                or type(validation_context.high_risk) is not bool
                or type(validation_context.mismatch) is not bool
                or type(validation_context.effect) is not str
                or type(validation_context.expected_anchor) is not str
                or not validation_context.expected_anchor
                or type(validation_context.observed_labels) is not frozenset
                or not all(type(label) is str for label in validation_context.observed_labels)
            ):
                return ObservationDecision("full-observe", "malformed-validator-context")
            authoritative = AdaptiveValidator().decide(validation_context)
            if decision is not None and decision != authoritative:
                return ObservationDecision("full-observe", "validator-decision-context-mismatch")
            decision = authoritative
        if not isinstance(decision, ValidationDecision):
            return ObservationDecision("full-observe", "validator-decision-required")
        if (
            type(decision.sufficient) is not bool
            or type(decision.creates_revision) is not bool
            or type(decision.confidence) not in (int, float)
            or not math.isfinite(float(decision.confidence))
            or not (0.0 <= float(decision.confidence) <= 1.0)
            or type(decision.method) is not str
            or type(decision.reason) is not str
            or type(decision.cost) is not str
        ):
            return ObservationDecision("full-observe", "malformed-validator-decision")
        if decision.creates_revision:
            return ObservationDecision("full-observe", "validator-cannot-author-revision")
        if risk not in ("low", "medium", "high"):
            return ObservationDecision("full-observe", "unknown-risk-fail-closed")
        if reversibility not in ("reversible", "compensable", "irreversible"):
            return ObservationDecision("full-observe", "unknown-reversibility-fail-closed")
        if human_gate or risk != "low" or reversibility != "reversible":
            return ObservationDecision("full-observe", "risk-lifecycle-floor-requires-observe")
        if revision_invalidated and next_is_state_sensitive:
            return ObservationDecision("full-observe", "invalidated-state-sensitive-requires-observe")
        if not decision.sufficient:
            return ObservationDecision("full-observe", "validator-floor-not-sufficient")
        if not (0.0 <= validated_confidence <= 1.0):
            return ObservationDecision("full-observe", "untrusted-confidence")
        if validated_confidence >= self.confidence_floor and not next_is_state_sensitive:
            return ObservationDecision("cheap-validate", "proven-decision-cheap-sufficient")
        return ObservationDecision("full-observe", "default-safe-observe")
