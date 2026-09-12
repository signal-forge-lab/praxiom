"""Evidence-gated Phase-C promotion readiness (authorization-free).

This module decides only whether an operation class has enough measured
evidence to *enter* a narrowly scoped live canary.  It never enables a Runtime
path, never mints Skill authority, and never flips the global live optimization
feature gate.  A ready decision therefore remains observational until an
explicit Phase-C activation step consumes it.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "OperationEvidence",
    "PromotionPolicy",
    "PromotionReadiness",
    "CanaryEnvironment",
    "CanaryPreflight",
    "evaluate_promotion_readiness",
    "evaluate_canary_preflight",
]


@dataclass(frozen=True, kw_only=True)
class OperationEvidence:
    operation_class: str
    current_device_success_none: int
    partial_count: int = 0
    unknown_count: int = 0
    replay_count: int = 0
    shadow_evaluations: int = 0
    shadow_stable: bool = False
    causal_validator_proven: bool = False
    fallback_proven: bool = False
    teaching_conflicts: int = 0
    risk: str = "low"
    reversibility: str = "reversible"
    human_gate: bool = False
    observed_execute_p90_ms: int | None = None
    observed_recovery_rate: float | None = None


@dataclass(frozen=True, kw_only=True)
class PromotionPolicy:
    operation_class: str
    min_current_device_success_none: int
    min_shadow_evaluations: int
    max_partial: int = 0
    max_unknown: int = 0
    max_replay: int = 0
    max_teaching_conflicts: int = 0
    require_causal_validator: bool = True
    require_fallback_proof: bool = True
    required_risk: str = "low"
    required_reversibility: str = "reversible"
    allow_human_gate: bool = False
    allowed_surface: str = "observation-only"
    sequence_live_allowed: bool = False
    max_execute_p90_ms: int | None = None
    min_recovery_rate: float | None = None


@dataclass(frozen=True, kw_only=True)
class PromotionReadiness:
    ready: bool
    operation_class: str
    allowed_surface: str
    sequence_live_allowed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class CanaryEnvironment:
    """Dynamic, authority-free environment facts checked at canary start.

    Adaptive code deliberately consumes booleans/opaque error classes rather
    than importing Runtime/transport types.  The caller is responsible for
    projecting the live Runtime snapshot into this DTO immediately before the
    Phase-C canary is armed.

    This is a *start gate*, not a recovery policy.  Any failed condition blocks
    the canary before mutation; it never retries, reconnects, unlocks, or
    otherwise changes device state.
    """

    runtime_ready: bool
    device_channel_ready: bool
    fresh_observation_ready: bool
    mutation_lane_idle: bool
    device_locked: bool = False
    environment_error_class: str = ""


@dataclass(frozen=True, kw_only=True)
class CanaryPreflight:
    ready: bool
    operation_class: str
    allowed_surface: str
    sequence_live_allowed: bool
    reasons: tuple[str, ...]


def evaluate_promotion_readiness(
    policy: PromotionPolicy, evidence: OperationEvidence
) -> PromotionReadiness:
    """Fail closed against one exact operation-class policy."""
    reasons: list[str] = []
    if evidence.operation_class != policy.operation_class:
        reasons.append("operation-class-mismatch")
    if evidence.current_device_success_none < policy.min_current_device_success_none:
        reasons.append("insufficient-current-device-success-none")
    if evidence.partial_count > policy.max_partial:
        reasons.append("partial-budget-exceeded")
    if evidence.unknown_count > policy.max_unknown:
        reasons.append("unknown-budget-exceeded")
    if evidence.replay_count > policy.max_replay:
        reasons.append("replay-budget-exceeded")
    if evidence.shadow_evaluations < policy.min_shadow_evaluations:
        reasons.append("insufficient-shadow-evidence")
    if not evidence.shadow_stable:
        reasons.append("shadow-not-stable")
    if policy.require_causal_validator and not evidence.causal_validator_proven:
        reasons.append("causal-validator-not-proven")
    if policy.require_fallback_proof and not evidence.fallback_proven:
        reasons.append("fallback-not-proven")
    if evidence.teaching_conflicts > policy.max_teaching_conflicts:
        reasons.append("teaching-conflict-budget-exceeded")
    if evidence.risk != policy.required_risk:
        reasons.append("risk-class-mismatch")
    if evidence.reversibility != policy.required_reversibility:
        reasons.append("reversibility-class-mismatch")
    if evidence.human_gate and not policy.allow_human_gate:
        reasons.append("human-gate-not-allowed")
    if policy.allowed_surface != "observation-only":
        reasons.append("unsupported-live-surface")
    if policy.sequence_live_allowed:
        reasons.append("sequence-live-must-remain-off")
    if policy.max_execute_p90_ms is not None:
        if evidence.observed_execute_p90_ms is None:
            reasons.append("missing-execute-latency")
        elif evidence.observed_execute_p90_ms > policy.max_execute_p90_ms:
            reasons.append("execute-latency-budget-exceeded")
    if policy.min_recovery_rate is not None:
        if evidence.observed_recovery_rate is None:
            reasons.append("missing-recovery-rate")
        elif evidence.observed_recovery_rate < policy.min_recovery_rate:
            reasons.append("recovery-rate-budget-missed")
    return PromotionReadiness(
        ready=not reasons,
        operation_class=policy.operation_class,
        allowed_surface=policy.allowed_surface,
        sequence_live_allowed=policy.sequence_live_allowed,
        reasons=tuple(reasons),
    )


def evaluate_canary_preflight(
    readiness: PromotionReadiness,
    environment: CanaryEnvironment,
) -> CanaryPreflight:
    """Fail closed on dynamic conditions immediately before Phase-C entry.

    Promotion readiness answers whether retained evidence/policy permit a
    candidate.  This second gate answers whether the *current* device lane is
    safe enough to start that canary now.  Availability failures therefore do
    not rewrite historical readiness, but they do block every live start until
    a fresh preflight passes.
    """

    reasons: list[str] = []
    if not readiness.ready:
        reasons.append("promotion-not-ready")
    if readiness.sequence_live_allowed:
        reasons.append("sequence-live-must-remain-off")
    if not environment.runtime_ready:
        reasons.append("runtime-not-ready")
    if not environment.device_channel_ready:
        reasons.append("device-channel-not-ready")
    if not environment.fresh_observation_ready:
        reasons.append("fresh-observation-not-ready")
    if not environment.mutation_lane_idle:
        reasons.append("mutation-lane-not-idle")
    if environment.device_locked:
        reasons.append("device-locked")
    if environment.environment_error_class:
        reasons.append("environment-error-present")
    return CanaryPreflight(
        ready=not reasons,
        operation_class=readiness.operation_class,
        allowed_surface=readiness.allowed_surface,
        sequence_live_allowed=readiness.sequence_live_allowed,
        reasons=tuple(reasons),
    )
