from __future__ import annotations

from praxiom.adaptive.promotion import (
    CanaryEnvironment,
    OperationEvidence,
    PromotionPolicy,
    evaluate_canary_preflight,
    evaluate_promotion_readiness,
)
from praxiom.adaptive.shadow import (
    LIVE_OPTIMIZATION_ENABLED,
    LiveOptimizationDisabledError,
    LiveOptimizationGate,
    ShadowContext,
    shadow_recommend,
)
import pytest


def _policy() -> PromotionPolicy:
    return PromotionPolicy(
        operation_class="system:return-home",
        min_current_device_success_none=4,
        min_shadow_evaluations=4,
        max_execute_p90_ms=550,
        min_recovery_rate=1.0,
    )


def _evidence(**overrides) -> OperationEvidence:
    base = dict(
        operation_class="system:return-home",
        current_device_success_none=4,
        shadow_evaluations=4,
        shadow_stable=True,
        causal_validator_proven=True,
        fallback_proven=True,
        observed_execute_p90_ms=502,
        observed_recovery_rate=1.0,
    )
    base.update(overrides)
    return OperationEvidence(**base)


def test_promotion_readiness_accepts_only_narrow_observation_canary():
    result = evaluate_promotion_readiness(_policy(), _evidence())
    assert result.ready is True
    assert result.allowed_surface == "observation-only"
    assert result.sequence_live_allowed is False
    assert result.reasons == ()


def test_promotion_readiness_refuses_partial_unknown_replay_or_conflict():
    for overrides, reason in [
        ({"partial_count": 1}, "partial-budget-exceeded"),
        ({"unknown_count": 1}, "unknown-budget-exceeded"),
        ({"replay_count": 1}, "replay-budget-exceeded"),
        ({"teaching_conflicts": 1}, "teaching-conflict-budget-exceeded"),
    ]:
        result = evaluate_promotion_readiness(_policy(), _evidence(**overrides))
        assert result.ready is False
        assert reason in result.reasons


def test_promotion_readiness_requires_validator_fallback_and_stable_shadow():
    result = evaluate_promotion_readiness(
        _policy(),
        _evidence(
            causal_validator_proven=False,
            fallback_proven=False,
            shadow_stable=False,
        ),
    )
    assert result.ready is False
    assert "causal-validator-not-proven" in result.reasons
    assert "fallback-not-proven" in result.reasons
    assert "shadow-not-stable" in result.reasons


def test_promotion_readiness_refuses_sequence_live_or_non_observation_surface():
    sequence_policy = PromotionPolicy(
        operation_class="system:return-home",
        min_current_device_success_none=4,
        min_shadow_evaluations=4,
        sequence_live_allowed=True,
    )
    result = evaluate_promotion_readiness(sequence_policy, _evidence())
    assert result.ready is False
    assert "sequence-live-must-remain-off" in result.reasons

    action_policy = PromotionPolicy(
        operation_class="system:return-home",
        min_current_device_success_none=4,
        min_shadow_evaluations=4,
        allowed_surface="action-batching",
    )
    result = evaluate_promotion_readiness(action_policy, _evidence())
    assert result.ready is False
    assert "unsupported-live-surface" in result.reasons


def test_promotion_readiness_enforces_measured_latency_and_recovery_budgets():
    slow = evaluate_promotion_readiness(
        _policy(), _evidence(observed_execute_p90_ms=551)
    )
    assert "execute-latency-budget-exceeded" in slow.reasons
    weak_recovery = evaluate_promotion_readiness(
        _policy(), _evidence(observed_recovery_rate=0.99)
    )
    assert "recovery-rate-budget-missed" in weak_recovery.reasons


def test_fixed_policy_refuses_fewer_than_four_clean_current_device_samples():
    result = evaluate_promotion_readiness(
        _policy(), _evidence(current_device_success_none=3)
    )
    assert result.ready is False
    assert "insufficient-current-device-success-none" in result.reasons


def test_ready_promotion_never_enables_global_live_gate_or_sequence_live():
    readiness = evaluate_promotion_readiness(_policy(), _evidence())
    assert readiness.ready is True
    assert LIVE_OPTIMIZATION_ENABLED is False
    assert readiness.sequence_live_allowed is False

    recommendation = shadow_recommend(
        ShadowContext(validated_confidence=1.0, pending=1, revision="r-home")
    )
    gate = LiveOptimizationGate()
    assert gate.enabled is False
    with pytest.raises(LiveOptimizationDisabledError):
        gate.authorize(
            recommendation,
            risk="low",
            reversibility="reversible",
            human_gate=False,
        )


def test_canary_preflight_requires_current_runtime_wda_observation_and_idle_lane():
    readiness = evaluate_promotion_readiness(_policy(), _evidence())
    result = evaluate_canary_preflight(
        readiness,
        CanaryEnvironment(
            runtime_ready=True,
            device_channel_ready=True,
            fresh_observation_ready=True,
            mutation_lane_idle=True,
        ),
    )
    assert result.ready is True
    assert result.reasons == ()
    assert result.sequence_live_allowed is False


def test_canary_preflight_blocks_transport_availability_without_changing_promotion():
    readiness = evaluate_promotion_readiness(_policy(), _evidence())
    assert readiness.ready is True
    result = evaluate_canary_preflight(
        readiness,
        CanaryEnvironment(
            runtime_ready=False,
            device_channel_ready=False,
            fresh_observation_ready=False,
            mutation_lane_idle=True,
            environment_error_class="DEVICE_CHANNEL_STARTUP_TIMEOUT",
        ),
    )
    assert result.ready is False
    assert "runtime-not-ready" in result.reasons
    assert "device-channel-not-ready" in result.reasons
    assert "fresh-observation-not-ready" in result.reasons
    assert "environment-error-present" in result.reasons
    # A transient environment failure must not rewrite evidence readiness.
    assert readiness.ready is True


def test_canary_preflight_blocks_locked_or_busy_lane_before_live_start():
    readiness = evaluate_promotion_readiness(_policy(), _evidence())
    result = evaluate_canary_preflight(
        readiness,
        CanaryEnvironment(
            runtime_ready=True,
            device_channel_ready=True,
            fresh_observation_ready=True,
            mutation_lane_idle=False,
            device_locked=True,
        ),
    )
    assert result.ready is False
    assert "mutation-lane-not-idle" in result.reasons
    assert "device-locked" in result.reasons
