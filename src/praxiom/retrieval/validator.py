"""R7-06 Post-Action Adaptive Validator (cheapest sufficient check).

Cheap causal validation defers expensive observation only when its
postcondition suffices; cheap validation never creates a Runtime revision,
so the next revision-bound state-sensitive mutation still requires a fresh
observe(). Ambiguity forces full reconciliation/escalation.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ValidationContext", "ValidationDecision", "AdaptiveValidator"]


@dataclass(frozen=True, kw_only=True)
class ValidationContext:
    effect: str  # NONE | PARTIAL | UNKNOWN
    expected_anchor: str
    observed_labels: frozenset[str]
    confidence: float
    high_risk: bool = False
    mismatch: bool = False


@dataclass(frozen=True, kw_only=True)
class ValidationDecision:
    method: str  # cheap-causal | full-observe | escalate
    sufficient: bool
    confidence: float
    reason: str
    cost: str
    creates_revision: bool = False  # cheap never creates a revision


class AdaptiveValidator:
    def decide(self, ctx: ValidationContext) -> ValidationDecision:
        # NONE is the only definitive success/no-error effect. Unknown future
        # or malformed values must not accidentally pass a cheap causal check.
        if ctx.effect != "NONE" or ctx.mismatch \
                or ctx.confidence < 0.5 or ctx.high_risk:
            return ValidationDecision(method="full-observe", sufficient=False,
                                      confidence=ctx.confidence,
                                      reason="ambiguity-requires-full-observe",
                                      cost="expensive")
        if ctx.expected_anchor in ctx.observed_labels:
            return ValidationDecision(method="cheap-causal", sufficient=True,
                                      confidence=ctx.confidence,
                                      reason="sufficient-postcondition",
                                      cost="cheap")
        return ValidationDecision(method="full-observe", sufficient=False,
                                  confidence=ctx.confidence,
                                  reason="postcondition-not-proven",
                                  cost="expensive")

    def next_requires_observe(self, *, mutation_invalidated_revision: bool,
                              next_is_state_sensitive: bool) -> bool:
        """After a mutation invalidates the revision, fresh observe() with
        execute(expected_revision=...) is mandatory for state-sensitive next."""
        return bool(mutation_invalidated_revision and next_is_state_sensitive)
