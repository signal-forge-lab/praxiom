"""R9 safe fallback + regression budgets (optimization fails closed)."""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["RegressionBudget", "check_budget", "safe_fallback", "BudgetVerdict"]


@dataclass(frozen=True, kw_only=True)
class RegressionBudget:
    max_latency_ms: int = 500
    max_observe_rate: float = 1.0
    min_recovery_rate: float = 0.5
    kind: str = "execute"


@dataclass(frozen=True)
class BudgetVerdict:
    within: bool
    reason: str
    fallback: bool  # True => disable optimization for this kind


def check_budget(budget: RegressionBudget, *, p90_ms: int | None,
                 observe_rate: float, recovery_rate: float) -> BudgetVerdict:
    if budget.max_latency_ms <= 0 or not (0.0 <= budget.max_observe_rate <= 1.0) \
            or not (0.0 <= budget.min_recovery_rate <= 1.0):
        return BudgetVerdict(False, "invalid-budget-fail-closed", True)
    if p90_ms is None:
        return BudgetVerdict(False, "missing-latency-signal", True)
    if p90_ms < 0:
        return BudgetVerdict(False, "invalid-latency-signal", True)
    if not (0.0 <= observe_rate <= 1.0) or not (0.0 <= recovery_rate <= 1.0):
        return BudgetVerdict(False, "invalid-rate-signal", True)
    if p90_ms > budget.max_latency_ms:
        return BudgetVerdict(False, "latency-budget-exceeded", True)
    if observe_rate > budget.max_observe_rate:
        return BudgetVerdict(False, "observe-budget-exceeded", True)
    if recovery_rate < budget.min_recovery_rate:
        return BudgetVerdict(False, "recovery-budget-missed", True)
    return BudgetVerdict(True, "within-budget", False)


def safe_fallback(*, signal_failed: bool, reason: str = "signal-failed") -> dict:
    """Fail closed to the R7-safe baseline whenever optimization signals fail."""
    _ = signal_failed
    return {"mode": "r7-safe-baseline", "optimization": "disabled", "reason": reason,
            "reobserve": True}
