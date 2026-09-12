"""R3-01: contract model / error-semantics checks (R2 contract sections 4-6).

One test per acceptance fixture (R2-A01..A10) proving every fixture field and
condition is representable with the public models, plus model-level checks
(frozen records, closed enum sets, error distinction enforcement, surface
purity). No device, transport, or runtime code is exercised here.
"""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime

import pytest

from praxiom.ios_runtime import models
from praxiom.ios_runtime.models import (
    ATTEMPTED_EFFECT_CODES,
    NO_EFFECT_CODES,
    ActionOutcome,
    Drag,
    Element,
    ErrorCode,
    ErrorEffect,
    ErrorPhase,
    ExecutionResult,
    FrameInfo,
    Home,
    LaunchApp,
    LifecycleState,
    ObserveRequest,
    Observation,
    Rect,
    RecoveryResult,
    RuntimeLimits,
    RuntimeOperationError,
    RuntimeStatus,
    ScreenSize,
    Swipe,
    TapElement,
    TapPoint,
    TransportKind,
    TypeText,
    WdaState,
)


def make_status(**overrides):
    base = {
        "contract_version": "v0",
        "lifecycle_state": LifecycleState.READY,
        "transport": TransportKind.RSD_USERSPACE,
        "wda_state": WdaState.READY,
        "limits": RuntimeLimits(max_batch_actions=32),
    }
    base.update(overrides)
    return RuntimeStatus(**base)


def make_observation(**overrides):
    base = {
        "revision": "rev-opaque-1",
        "captured_at": datetime.now(UTC),
        "screen": ScreenSize(width=390, height=844),
        "frame": FrameInfo(width=390, height=844, format="png"),
        "sources": ("screenshot", "accessibility"),
    }
    base.update(overrides)
    return Observation(**base)


# --- fixture representability (R2-A01 .. R2-A10) ------------------------------


def test_a01_ready_status_snapshot_is_representable():
    status = make_status(
        current_revision=None,
        capabilities={"actions": "v0", "screenshot": True, "accessibility": True},
    )
    assert status.contract_version == "v0"
    assert status.lifecycle_state == "READY"  # StrEnum compares to contract strings
    assert status.transport == "RSD_USERSPACE"
    assert status.wda_state == "READY"
    assert status.current_revision is None
    assert status.limits.max_batch_actions == 32
    assert status.last_error_code is None
    rendered = repr(status)
    for forbidden in ("udid", "pair_record", "screen_text", "raw_action_payload"):
        assert forbidden not in rendered.lower()


def test_a02_observation_creates_revision_and_bound_elements():
    obs = make_observation(
        elements=(
            Element(
                ref="el-1",
                role="button",
                source="accessibility",
                label="Buy",
                value="Buy now",
                rect=Rect(x=100, y=200, width=50, height=24),
                enabled=True,
                visible=True,
            ),
        ),
    )
    assert isinstance(obs.revision, str) and obs.revision  # opaque, non-empty
    assert obs.screen.width > 0 and obs.screen.height > 0
    assert obs.sources == ("screenshot", "accessibility")
    assert obs.captured_at.tzinfo is not None
    el = obs.elements[0]
    assert el.ref and el.role == "button" and el.label == "Buy"
    assert el.text is None and el.value == "Buy now"
    assert el.rect == Rect(x=100, y=200, width=50, height=24)  # screenshot pixels
    assert el.enabled is True and el.visible is True
    assert el.source == "accessibility"
    # Screenshot-only observations are representable without elements.
    assert make_observation(revision="rev-2").elements == ()


def test_a03_execution_result_records_order_and_invalidation():
    result = ExecutionResult(
        completed_actions=2,
        accepted_revision_invalidated=True,
        outcomes=(
            ActionOutcome(index=0, kind="tap_point", duration_ms=12.5),
            ActionOutcome(index=1, kind="type_text", duration_ms=3.0),
        ),
    )
    assert result.completed_actions == 2
    assert result.accepted_revision_invalidated is True
    assert [o.kind for o in result.outcomes] == ["tap_point", "type_text"]
    assert [o.index for o in result.outcomes] == [0, 1]


def test_a04_stale_revision_error_is_no_effect():
    err = RuntimeOperationError(
        code="STALE_REVISION", phase="preflight", effect="NONE", retry_safe=True
    )
    assert err.code == "STALE_REVISION"
    assert err.phase == "preflight"
    assert err.effect == "NONE"
    assert err.retry_safe is True
    assert err.completed_actions is None
    assert err.failed_action_index is None
    assert err.revision_invalidated is False
    assert str(err) == "STALE_REVISION: phase=preflight effect=NONE retry_safe=True"


def test_a05_invalid_action_is_constructible_for_whole_batch_preflight():
    # Models stay permissive: an invalid action (empty required text) must be
    # constructible so the executor can reject the WHOLE batch before any
    # device call; the rejection itself is a no-effect error.
    batch = [TapPoint(x=100, y=200), TypeText(text="")]
    assert len(batch) == 2
    err = RuntimeOperationError(
        code="INVALID_REQUEST", phase="preflight", effect="NONE", retry_safe=True
    )
    assert err.code == "INVALID_REQUEST" and err.effect == "NONE"


def test_a06_ambiguous_mid_batch_failure_error():
    err = RuntimeOperationError(
        code="EFFECT_UNKNOWN",
        phase="execution",
        effect="UNKNOWN",
        retry_safe=False,
        completed_actions=1,
        failed_action_index=1,
        revision_invalidated=True,
    )
    assert err.code == "EFFECT_UNKNOWN"
    assert err.phase == "execution"
    assert err.effect == "UNKNOWN"
    assert err.completed_actions == 1
    assert err.failed_action_index == 1
    assert err.retry_safe is False
    assert err.revision_invalidated is True
    # A known device-side failure mid-batch is representable too.
    known = RuntimeOperationError(
        code="ACTION_FAILED",
        phase="execution",
        effect="PARTIAL",
        retry_safe=False,
        completed_actions=1,
        failed_action_index=1,
        revision_invalidated=True,
    )
    assert known.code == "ACTION_FAILED" and known.effect == "PARTIAL"


def test_a07_recovery_result_representable():
    assert RecoveryResult(repaired=True).repaired is True
    assert RecoveryResult(repaired=False).repaired is False
    failed = RuntimeOperationError(
        code="RECOVERY_FAILED", phase="lifecycle", effect="NONE", retry_safe=True
    )
    assert failed.code == "RECOVERY_FAILED" and failed.effect == "NONE"
    # Recovery always invalidates the pre-recovery revision: the post-recovery
    # status has no current revision.
    assert make_status(lifecycle_state=LifecycleState.DEGRADED).current_revision is None


def test_a08_closed_status_and_runtime_closed_error():
    err = RuntimeOperationError(
        code="RUNTIME_CLOSED", phase="lifecycle", effect="NONE", retry_safe=False
    )
    # No-effect codes stay effect=NONE even when a retry cannot succeed.
    assert err.effect == "NONE" and err.retry_safe is False
    status = make_status(
        lifecycle_state=LifecycleState.CLOSED,
        transport=TransportKind.NONE,
        wda_state=WdaState.NONE,
        current_revision=None,
    )
    assert status.lifecycle_state == "CLOSED"


def test_a09_foreign_revision_element_ref_condition_representable():
    action = TapElement(ref="element-from-rev-a")
    assert action.kind == "tap_element" and action.ref == "element-from-rev-a"
    # Executed against expected_revision="rev-b" (ref was created by rev-a):
    # the rejection is a preflight STALE_REVISION with zero device calls.
    err = RuntimeOperationError(
        code="STALE_REVISION", phase="preflight", effect="NONE", retry_safe=True
    )
    assert err.code == "STALE_REVISION" and err.phase == "preflight"


def test_a10_over_limit_batch_condition_representable():
    limits = RuntimeLimits(max_batch_actions=2)
    batch = [Home(), Home(), Home()]
    assert len(batch) > limits.max_batch_actions  # the condition preflight rejects on
    err = RuntimeOperationError(
        code="INVALID_REQUEST", phase="preflight", effect="NONE", retry_safe=True
    )
    assert err.code == "INVALID_REQUEST"


# --- model-level checks --------------------------------------------------------


def test_v0_action_union_is_frozen_value_records():
    drag = Drag(start_x=1, start_y=2, end_x=3, end_y=4, duration=0.5)
    actions = [
        TapPoint(x=1, y=2),
        TapElement(ref="el"),
        drag,
        Swipe(direction="up", distance=0.5),
        TypeText(text="abc"),
        Home(),
        LaunchApp(bundle_id="com.example.app"),
    ]
    assert {a.kind for a in actions} == {
        "tap_point",
        "tap_element",
        "drag",
        "swipe",
        "type_text",
        "home",
        "launch_app",
    }
    assert drag.end_y == 4  # contract 4.3: drag carries both end coordinates
    assert actions[0] == TapPoint(x=1, y=2)  # value equality
    assert actions[5] == Home()
    with pytest.raises(FrozenInstanceError):
        actions[0].x = 5  # type: ignore[misc]


def test_status_and_error_enums_are_closed_contract_sets():
    assert {s.value for s in LifecycleState} == {
        "READY",
        "DEGRADED",
        "DISCONNECTED",
        "CLOSED",
    }
    assert {s.value for s in TransportKind} == {
        "LOCKDOWN",
        "RSD_USERSPACE",
        "RSD_NATIVE",
        "RSD_TUNNELD",
        "NONE",
    }
    assert {s.value for s in WdaState} == {
        "READY",
        "UNAVAILABLE",
        "RECOVERING",
        "NONE",
    }
    assert {s.value for s in ErrorPhase} == {"preflight", "lifecycle", "execution"}
    assert {s.value for s in ErrorEffect} == {"NONE", "PARTIAL", "UNKNOWN"}


def test_error_code_partition_matches_contract():
    assert {c.value for c in NO_EFFECT_CODES} == {
        "INVALID_REQUEST",
        "STALE_REVISION",
        "NOT_READY",
        "RUNTIME_CLOSED",
        "UNSUPPORTED_ACTION",
        "OBSERVATION_FAILED",
        "RECOVERY_FAILED",
    }
    assert {c.value for c in ATTEMPTED_EFFECT_CODES} == {
        "ACTION_FAILED",
        "EFFECT_UNKNOWN",
    }
    assert not NO_EFFECT_CODES & ATTEMPTED_EFFECT_CODES
    assert NO_EFFECT_CODES | ATTEMPTED_EFFECT_CODES == set(ErrorCode)


def test_error_model_enforces_no_effect_vs_attempted_distinction():
    # A no-effect code cannot claim a device effect.
    with pytest.raises(ValueError):
        RuntimeOperationError(
            code="INVALID_REQUEST", phase="preflight", effect="PARTIAL", retry_safe=True
        )
    with pytest.raises(ValueError):
        RuntimeOperationError(
            code="STALE_REVISION", phase="execution", effect="NONE", retry_safe=True
        )
    with pytest.raises(ValueError):
        RuntimeOperationError(
            code="NOT_READY",
            phase="lifecycle",
            effect="NONE",
            retry_safe=True,
            completed_actions=1,
            failed_action_index=0,
        )
    # An attempted-effect code cannot be presented as clean, retryable, or
    # revision-preserving, and must know its counts.
    with pytest.raises(ValueError):
        RuntimeOperationError(
            code="EFFECT_UNKNOWN",
            phase="preflight",
            effect="UNKNOWN",
            retry_safe=False,
            completed_actions=0,
            failed_action_index=0,
            revision_invalidated=True,
        )
    with pytest.raises(ValueError):
        RuntimeOperationError(
            code="EFFECT_UNKNOWN",
            phase="execution",
            effect="NONE",
            retry_safe=False,
            completed_actions=0,
            failed_action_index=0,
            revision_invalidated=True,
        )
    with pytest.raises(ValueError):
        RuntimeOperationError(
            code="ACTION_FAILED",
            phase="execution",
            effect="PARTIAL",
            retry_safe=True,
            completed_actions=1,
            failed_action_index=1,
            revision_invalidated=True,
        )
    with pytest.raises(ValueError):
        RuntimeOperationError(
            code="ACTION_FAILED",
            phase="execution",
            effect="PARTIAL",
            retry_safe=False,
            completed_actions=1,
            failed_action_index=1,
            revision_invalidated=False,
        )
    with pytest.raises(ValueError):
        RuntimeOperationError(
            code="EFFECT_UNKNOWN",
            phase="execution",
            effect="UNKNOWN",
            retry_safe=False,
            revision_invalidated=True,
        )


def test_revision_tokens_are_opaque_plain_strings():
    status = make_status(current_revision="tok-123")
    obs = make_observation(revision="tok-456")
    assert isinstance(status.current_revision, str)
    assert isinstance(obs.revision, str)
    assert status.current_revision != obs.revision  # plain compare, no parsing
    # The surface has no revision parsing/decoding helper.
    assert not any(
        part in name.lower() for name in models.__all__ for part in ("parse", "decode")
    )


def test_observe_request_defaults_to_generic_sources():
    assert ObserveRequest().sources == frozenset({"screenshot", "accessibility"})
    assert ObserveRequest(sources=frozenset({"screenshot"})).sources == frozenset(
        {"screenshot"}
    )


def test_records_are_frozen():
    status = make_status()
    with pytest.raises(FrozenInstanceError):
        status.lifecycle_state = LifecycleState.CLOSED  # type: ignore[misc]
    obs = make_observation(
        elements=(Element(ref="el", role="button", source="accessibility"),)
    )
    with pytest.raises(FrozenInstanceError):
        obs.revision = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        obs.elements[0].ref = "x"  # type: ignore[misc]


def test_observation_carries_no_image_bytes():
    names = {f.name for f in fields(Observation)}
    assert not names & {"image", "bytes", "data", "png"}


def test_public_surface_is_exactly_the_contract_models():
    assert set(models.__all__) == {
        "ATTEMPTED_EFFECT_CODES",
        "NO_EFFECT_CODES",
        "Action",
        "ActionOutcome",
        "Drag",
        "Element",
        "ErrorEffect",
        "ErrorCode",
        "ErrorPhase",
        "ExecutionResult",
        "FrameInfo",
        "Home",
        "LaunchApp",
        "LifecycleState",
        "ObserveRequest",
        "Observation",
        "Rect",
        "RecoveryResult",
        "RuntimeLimits",
        "RuntimeOperationError",
        "RuntimeStatus",
        "ScreenSize",
        "Swipe",
        "TapElement",
        "TapPoint",
        "TransportKind",
        "TypeText",
        "WdaState",
    }


def test_no_agent_teaching_knowledge_or_domain_types():
    forbidden = (
        "agent",
        "teaching",
        "knowledge",
        "goal",
        "game",
        "ocr",
        "skill",
        "policy",
        "domain",
    )
    for name in models.__all__:
        lowered = name.lower()
        assert not any(word in lowered for word in forbidden), name
