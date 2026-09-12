"""R6-E Reasoning Escalation v1 (model-neutral, deterministic)."""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ReasoningSignals", "ReasoningRoute", "route", "escalation_chain"]

# Freeze escalation order (T11): deterministic -> lightweight -> heavy ->
# human/physical gate. Provider/model-neutral; tiers only.
ESCALATION_ORDER = ("deterministic", "lightweight", "heavy", "human-gate")


@dataclass(frozen=True, kw_only=True)
class ReasoningSignals:
    unknown_state: bool = False
    conflicts_knowledge: bool = False
    repeated_failures: int = 0
    low_confidence_near_side_effect: bool = False
    unexplained_transition: bool = False
    teaching_contradicts_knowledge: bool = False
    security_boundary: bool = False


@dataclass(frozen=True, kw_only=True)
class ReasoningRoute:
    tier: str  # deterministic | lightweight | heavy
    reason: str
    latency_ms: int = 0
    outcome: str = ""


def route(signals: ReasoningSignals, *, latency_ms: int = 0) -> ReasoningRoute:
    """Select the cheapest sufficient tier; record tier+reason+latency."""
    if signals.security_boundary or signals.repeated_failures >= 3:
        return ReasoningRoute(tier="heavy", reason="heavy:repeated-or-security",
                              latency_ms=latency_ms)
    if (
        signals.unknown_state
        or signals.conflicts_knowledge
        or signals.low_confidence_near_side_effect
        or signals.unexplained_transition
        or signals.teaching_contradicts_knowledge
    ):
        return ReasoningRoute(tier="lightweight", reason="lightweight:escalation-trigger",
                              latency_ms=latency_ms)
    if signals.repeated_failures >= 2:
        return ReasoningRoute(tier="lightweight", reason="lightweight:repeated-failure",
                              latency_ms=latency_ms)
    return ReasoningRoute(tier="deterministic", reason="deterministic:known-confident",
                          latency_ms=latency_ms)


def escalation_chain(tier: str) -> tuple[str, ...]:
    """Return the ordered escalation prefix ending at *tier* (inclusive).

    Unknown tiers raise; the chain never invents a provider/model step.
    """
    if tier not in ESCALATION_ORDER:
        raise ValueError(f"unknown reasoning tier: {tier!r}")
    return ESCALATION_ORDER[:ESCALATION_ORDER.index(tier) + 1]
