"""R9 latency-aware + reasoning/execution strategy routing (provider-neutral)."""
from __future__ import annotations

from dataclasses import dataclass

from praxiom.adaptive.telemetry import PerformanceBaseline, _baseline_sample

__all__ = ["RouteDecision", "route_latency_aware", "StrategyDecision", "adapt_strategy"]

TIERS = ("deterministic", "lightweight", "heavy")


@dataclass(frozen=True)
class RouteDecision:
    route: str  # fast-path | standard | careful
    reason: str


def route_latency_aware(*, baseline: PerformanceBaseline, kind: str, budget_ms: int,
                        risk: str, reversibility: str, human_gate: bool) -> RouteDecision:
    if budget_ms <= 0:
        return RouteDecision("careful", "invalid-budget-fail-closed")
    if not isinstance(baseline, PerformanceBaseline):
        return RouteDecision("careful", "baseline-required")
    if type(kind) is not str or not kind:
        return RouteDecision("careful", "invalid-kind-fail-closed")
    if risk not in ("low", "medium", "high"):
        return RouteDecision("careful", "unknown-risk-fail-closed")
    if reversibility not in ("reversible", "compensable", "irreversible"):
        return RouteDecision("careful", "unknown-reversibility-fail-closed")
    if human_gate or risk == "high" or reversibility == "irreversible":
        return RouteDecision("careful", "risk-or-human-gate-never-fast")
    sample = _baseline_sample(baseline, kind)
    if sample is None:
        return RouteDecision("careful", "baseline-required")
    p90_ms, sample_count = sample
    if sample_count < 2 or p90_ms is None:
        return RouteDecision("careful", "no-telemetry-fail-closed")
    if p90_ms < 0:
        return RouteDecision("careful", "invalid-telemetry-fail-closed")
    if risk == "medium" or reversibility == "compensable":
        return RouteDecision("standard", "non-low-risk-capped-standard")
    if p90_ms <= budget_ms // 2:
        return RouteDecision("fast-path", "p90-within-half-budget")
    if p90_ms <= budget_ms:
        return RouteDecision("standard", "p90-within-budget")
    return RouteDecision("careful", "p90-exceeds-budget")


@dataclass(frozen=True)
class StrategyDecision:
    tier: str
    explain: str


def adapt_strategy(*, failure_streak: int, loop_detected: bool, validator_failed: bool) -> StrategyDecision:
    if validator_failed or loop_detected or failure_streak >= 3:
        return StrategyDecision("heavy", "escalate:loop-failure-validator")
    if failure_streak >= 1:
        return StrategyDecision("lightweight", "cautious:recent-failure")
    return StrategyDecision("deterministic", "steady:deterministic-cheapest")
