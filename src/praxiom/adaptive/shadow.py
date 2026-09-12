"""Shadow-first adaptive policy (live optimization feature-gated OFF).

Runs the already-certified adaptive signals against real execution context
and records what they *would* recommend, without ever applying a
recommendation or touching the Runtime. The actual decision is always the
current certified safe behavior. Per the frozen activation decision:

- every recommendation records the actual decision, the shadow
  recommendation, its reason, confidence/evidence inputs, whether it would
  reduce observe/action counts, and the fallback reason when a shadow
  optimization is refused;
- shadowed surfaces: ObservationPolicy (full-observe vs cheap-validate),
  bounded batch size, latency-aware routing, reasoning/execution strategy,
  macro/path reuse eligibility, and regression-budget fallback;
- no shadow recommendation may itself mutate the device;
- live application stays feature-gated OFF: ``LIVE_OPTIMIZATION_ENABLED``
  is a frozen-phase constant ``False`` and the default gate refuses every
  authorization; even an explicitly enabled gate only ever authorizes
  low-risk, reversible, non-human-gated classes.
"""
from __future__ import annotations

from dataclasses import dataclass

from praxiom.adaptive.batching import BatchDecision, decide_batch
from praxiom.adaptive.fallback import RegressionBudget, check_budget, safe_fallback
from praxiom.adaptive.observation import (
    CONFIDENCE_FLOOR,
    ObservationDecision,
    ObservationPolicy,
)
from praxiom.adaptive.routing import (
    RouteDecision,
    StrategyDecision,
    adapt_strategy,
    route_latency_aware,
)
from praxiom.adaptive.telemetry import PerformanceBaseline
from praxiom.retrieval.validator import ValidationContext, ValidationDecision

__all__ = [
    "LIVE_OPTIMIZATION_ENABLED",
    "ShadowContext",
    "ShadowRecommendation",
    "ShadowAdvisor",
    "LiveOptimizationGate",
    "LiveOptimizationDisabledError",
    "LiveOptimizationRefusedError",
]

LIVE_OPTIMIZATION_ENABLED = False

ACTUAL_DECISION = "certified-safe-behavior"


@dataclass(frozen=True, kw_only=True)
class ShadowContext:
    """Real execution-context inputs for one shadow evaluation."""

    validated_confidence: float
    next_is_state_sensitive: bool = False
    revision_invalidated: bool = False
    risk: str = "low"
    reversibility: str = "reversible"
    human_gate: bool = False
    validator_decision: ValidationDecision | None = None
    validation_context: ValidationContext | None = None
    confidence_floor: float = CONFIDENCE_FLOOR
    pending: int = 1
    revision: str = ""
    max_batch: int = 8
    baseline: PerformanceBaseline | None = None
    kind: str = "execute"
    budget_ms: int = 0
    failure_streak: int = 0
    loop_detected: bool = False
    validator_failed: bool = False
    macro_reuse_eligible: bool = False
    path_reuse_eligible: bool = False
    selector_hit_rate: float | None = None
    recovery_rate: float | None = None
    observe_rate: float = 0.0
    regression_budget: RegressionBudget | None = None


@dataclass(frozen=True, kw_only=True)
class ShadowRecommendation:
    actual_decision: str
    observation: ObservationDecision | None
    batch: BatchDecision | None
    route: RouteDecision | None
    strategy: StrategyDecision | None
    fallback: dict | None
    macro_reuse_eligible: bool
    path_reuse_eligible: bool
    reason: str
    confidence: float
    would_reduce_observe: bool
    would_reduce_actions: bool
    fallback_reason: str
    live_applied: bool = False
    selector_hit_rate: float | None = None
    recovery_rate: float | None = None


def shadow_recommend(ctx: ShadowContext) -> ShadowRecommendation:
    """Evaluate every shadowed signal; any signal failure fails closed."""
    if not isinstance(ctx, ShadowContext):
        raise TypeError("shadow-context-required")

    notes: list[str] = []

    try:
        observation = ObservationPolicy(confidence_floor=ctx.confidence_floor).decide(
            validated_confidence=ctx.validated_confidence,
            next_is_state_sensitive=ctx.next_is_state_sensitive,
            revision_invalidated=ctx.revision_invalidated,
            validator_decision=ctx.validator_decision,
            validation_context=ctx.validation_context,
            risk=ctx.risk,
            reversibility=ctx.reversibility,
            human_gate=ctx.human_gate,
        )
    except Exception:
        observation = None
        notes.append("observation-signal-failed")

    try:
        batch = decide_batch(
            pending=ctx.pending,
            validated_confidence=ctx.validated_confidence,
            revision=ctx.revision,
            state_sensitive=ctx.next_is_state_sensitive,
            risk=ctx.risk,
            reversibility=ctx.reversibility,
            human_gate=ctx.human_gate,
            max_batch=ctx.max_batch,
        )
    except Exception:
        batch = None
        notes.append("batch-signal-failed")

    if ctx.baseline is None:
        route = None
        notes.append("no-baseline")
    else:
        try:
            route = route_latency_aware(
                baseline=ctx.baseline,
                kind=ctx.kind,
                budget_ms=ctx.budget_ms,
                risk=ctx.risk,
                reversibility=ctx.reversibility,
                human_gate=ctx.human_gate,
            )
        except Exception:
            route = None
            notes.append("route-signal-failed")

    try:
        strategy = adapt_strategy(
            failure_streak=ctx.failure_streak,
            loop_detected=ctx.loop_detected,
            validator_failed=ctx.validator_failed,
        )
    except Exception:
        strategy = None
        notes.append("strategy-signal-failed")

    fallback: dict | None = None
    fallback_reason = ""
    if ctx.regression_budget is not None:
        try:
            p90_ms = (
                ctx.baseline.per_kind_p90_ms.get(ctx.kind)
                if ctx.baseline is not None else None
            )
            verdict = check_budget(
                ctx.regression_budget,
                p90_ms=p90_ms,
                observe_rate=ctx.observe_rate,
                recovery_rate=0.0 if ctx.recovery_rate is None else ctx.recovery_rate,
            )
            if verdict.fallback:
                fallback = safe_fallback(
                    signal_failed=not verdict.within, reason=verdict.reason)
                fallback_reason = verdict.reason
        except Exception:
            fallback = safe_fallback(signal_failed=True, reason="budget-signal-failed")
            fallback_reason = "budget-signal-failed"
            notes.append("budget-signal-failed")

    try:
        confidence = float(ctx.validated_confidence)
        if not (0.0 <= confidence <= 1.0):
            confidence = 0.0
            notes.append("untrusted-confidence-clamped")
    except (TypeError, ValueError):
        confidence = 0.0
        notes.append("untrusted-confidence-clamped")

    if notes:
        reason = "shadow-fail-closed:" + "+".join(notes)
    else:
        reason = observation.reason if observation is not None else "no-shadow-signals"

    return ShadowRecommendation(
        actual_decision=ACTUAL_DECISION,
        observation=observation,
        batch=batch,
        route=route,
        strategy=strategy,
        fallback=fallback,
        macro_reuse_eligible=bool(ctx.macro_reuse_eligible),
        path_reuse_eligible=bool(ctx.path_reuse_eligible),
        reason=reason,
        confidence=confidence,
        would_reduce_observe=bool(
            observation is not None and observation.method == "cheap-validate"),
        would_reduce_actions=bool(batch is not None and batch.size > 1),
        fallback_reason=fallback_reason,
        live_applied=False,
        selector_hit_rate=ctx.selector_hit_rate,
        recovery_rate=ctx.recovery_rate,
    )


class ShadowAdvisor:
    """Bounded in-memory shadow recorder; never applies and never mutates."""

    def __init__(self, *, max_history: int = 256) -> None:
        if not isinstance(max_history, int) or max_history < 1:
            raise ValueError("max-history-positive")
        self._max = max_history
        self._history: list[ShadowRecommendation] = []

    def recommend(self, ctx: ShadowContext) -> ShadowRecommendation:
        rec = shadow_recommend(ctx)
        self._history.append(rec)
        if len(self._history) > self._max:
            del self._history[: len(self._history) - self._max]
        return rec

    @property
    def history(self) -> tuple[ShadowRecommendation, ...]:
        return tuple(self._history)

    @property
    def last_recommendation(self) -> ShadowRecommendation | None:
        return self._history[-1] if self._history else None


class LiveOptimizationDisabledError(RuntimeError):
    pass


class LiveOptimizationRefusedError(RuntimeError):
    pass


class LiveOptimizationGate:
    """Feature gate for shadow-first promotion; default OFF.

    The gate never applies anything by itself: it can only authorize, and
    only for explicitly accepted low-risk classes once a real-device
    baseline justifies promotion. The default-constructed gate refuses
    every request while live optimization is feature-gated OFF.
    """

    def __init__(self, *, enabled: bool = False) -> None:
        self._enabled = bool(enabled)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def authorize(
        self,
        rec: ShadowRecommendation,
        *,
        risk: str,
        reversibility: str,
        human_gate: bool,
    ) -> str:
        if not self._enabled:
            raise LiveOptimizationDisabledError("live-optimization-feature-gated-off")
        if rec is None or not isinstance(rec, ShadowRecommendation):
            raise LiveOptimizationRefusedError("recommendation-required")
        if human_gate or risk != "low" or reversibility != "reversible":
            raise LiveOptimizationRefusedError("risk-lifecycle-floor-refuses-live-apply")
        if not (rec.would_reduce_observe or rec.would_reduce_actions):
            raise LiveOptimizationRefusedError("no-reduction-to-apply")
        return "live-apply-authorized"
