"""R9 Adaptive Execution Performance public surface (safe-baseline-first)."""
from praxiom.adaptive.telemetry import TelemetryEvent, aggregate, PerformanceBaseline
from praxiom.adaptive.dag import DagPlan, plan_dag
from praxiom.adaptive.batching import BatchDecision, decide_batch
from praxiom.adaptive.learning import (
    MacroStats, learn_macros, macro_reusable, PathStats, score_path, path_reusable,
)
from praxiom.adaptive.temporal import Countdown, MonotonicClock, remaining_ms
from praxiom.adaptive.observation import ObservationPolicy, ObservationDecision
from praxiom.adaptive.routing import RouteDecision, route_latency_aware
from praxiom.adaptive.feedback import SelectorStats, record_selector, RecoveryStats
from praxiom.adaptive.fallback import RegressionBudget, check_budget, safe_fallback
from praxiom.adaptive.experience_bridge import (
    ExtractionContext, RebindResult, build_episode, rebind_history,
)
from praxiom.adaptive.shadow import (
    LIVE_OPTIMIZATION_ENABLED, LiveOptimizationDisabledError,
    LiveOptimizationGate, LiveOptimizationRefusedError, ShadowAdvisor,
    ShadowContext, ShadowRecommendation, shadow_recommend,
)
from praxiom.adaptive.promotion import (
    CanaryEnvironment, CanaryPreflight, OperationEvidence, PromotionPolicy,
    PromotionReadiness, evaluate_canary_preflight,
    evaluate_promotion_readiness,
)

__all__ = [
    "TelemetryEvent", "aggregate", "PerformanceBaseline",
    "DagPlan", "plan_dag",
    "BatchDecision", "decide_batch",
    "MacroStats", "learn_macros", "macro_reusable", "PathStats", "score_path", "path_reusable",
    "Countdown", "MonotonicClock", "remaining_ms",
    "ObservationPolicy", "ObservationDecision",
    "RouteDecision", "route_latency_aware",
    "SelectorStats", "record_selector", "RecoveryStats",
    "RegressionBudget", "check_budget", "safe_fallback",
    "ExtractionContext", "RebindResult", "build_episode", "rebind_history",
    "LIVE_OPTIMIZATION_ENABLED", "LiveOptimizationDisabledError",
    "LiveOptimizationGate", "LiveOptimizationRefusedError", "ShadowAdvisor",
    "ShadowContext", "ShadowRecommendation", "shadow_recommend",
    "OperationEvidence", "PromotionPolicy", "PromotionReadiness",
    "CanaryEnvironment", "CanaryPreflight", "evaluate_promotion_readiness",
    "evaluate_canary_preflight",
]
