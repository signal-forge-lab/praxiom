"""R3-05 runtime integration tests: unknown effects, recovery, close.

Covers the runtime-level slice of the R2 acceptance fixtures on a fake
transport injected at the runtime/transport boundary (fault injection, no
device required):

- R2-A06 — mid-batch timeout after send -> EFFECT_UNKNOWN with completed
  count / failed index, retry_safe=false, revision invalidated, and the fake
  device call count never grows after the failure (zero automatic replay);
- R2-A07 — recover() with a stale WDA session rebuilds the plumbing,
  invalidates the pre-recovery revision, and replays zero actions;
- R2-A08 — close is idempotent, releases only owned resources, and leaves
  status() callable reporting CLOSED;

plus the runtime-owned status/limit surface and the no-effect rejections
(stale revision, foreign element ref, empty/over-limit batch, closed runtime,
failed recovery, failed observation) that must make zero device calls.
"""

import asyncio

import pytest

from praxiom.ios_runtime.models import (
    ErrorCode,
    ErrorEffect,
    ErrorPhase,
    Home,
    LifecycleState,
    RuntimeOperationError,
    TapElement,
    TapPoint,
    TransportKind,
    TypeText,
    WdaState,
)
from praxiom.ios_runtime.runtime import INVALIDATE_REASON_MAX_LENGTH, NativeIosRuntime
from praxiom.ios_runtime.transport import (
    TransportError,
    TransportStatus,
    WdaUnreachableError,
)

# 24-byte PNG header: signature + IHDR length/type + 100x200 pixel dimensions.
_PNG_HEADER = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    + (100).to_bytes(4, "big")
    + (200).to_bytes(4, "big")
)
_ACCESSIBILITY = (
    '<root><button label="Go" x="10" y="20" width="30" height="40" '
    'enabled="true"/></root>'
)


class FakeWdaSession:
    """Owned WDA client/session handle standing in for the upstream client."""

    def __init__(self, session_id: str | None) -> None:
        self.session_id = session_id


class FakeOwnedTunnel:
    """Owned RSD tunnel handle with a closed flag."""

    def __init__(self) -> None:
        self.closed = False


class FakeTransport:
    """Duck-typed IosTransport with owned-resource accounting and faults.

    - ``actions`` records every ordered action-primitive call (one call per
      action), so rejected preflights can be proven to make zero device calls;
    - ``faults`` maps an action ordinal to an exception raised after the call
      was recorded — i.e. after the request was sent (timeout-after-send);
    - owned resources: the RSD tunnel handle and the WDA session, released
      only by ``close()``; ``unowned_tunnel`` models an unrelated resource the
      runtime must never touch;
    - ``recreate()`` discards the stale session/tunnel and rebuilds them.
    """

    def __init__(self, *, faults=None, connect_error=None, recreate_error=None):
        self.tunnel = FakeOwnedTunnel()
        self.wda = FakeWdaSession("session-1")
        self.unowned_tunnel = FakeOwnedTunnel()
        self.actions: list[tuple[str, tuple]] = []
        self.discarded_sessions: list[FakeWdaSession] = []
        self.connect_count = 0
        self.recreate_count = 0
        self.close_count = 0
        self.closed = False
        self.connected = False
        self._session_counter = 1
        self._faults = dict(faults or {})
        self._connect_error = connect_error
        self._recreate_error = recreate_error

    # --- lifecycle ---

    def snapshot(self) -> TransportStatus:
        if self.closed:
            return TransportStatus(
                LifecycleState.CLOSED, TransportKind.NONE, WdaState.NONE, has_session=False
            )
        if not self.connected:
            return TransportStatus(
                LifecycleState.DISCONNECTED, TransportKind.NONE, WdaState.NONE, has_session=False
            )
        has_session = self.wda is not None and bool(self.wda.session_id)
        return TransportStatus(
            LifecycleState.READY if has_session else LifecycleState.DEGRADED,
            TransportKind.RSD_USERSPACE,
            WdaState.READY if has_session else WdaState.UNAVAILABLE,
            has_session=has_session,
        )

    async def connect(self) -> TransportStatus:
        self.connect_count += 1
        if self._connect_error is not None:
            raise self._connect_error
        self.connected = True
        if self.wda is not None and self.wda.session_id is None:
            self._session_counter += 1
            self.wda.session_id = f"session-{self._session_counter}"
        return self.snapshot()

    async def recreate(self) -> TransportStatus:
        self.recreate_count += 1
        if self._recreate_error is not None:
            raise self._recreate_error
        self.connected = False
        self.discarded_sessions.append(self.wda)
        self._session_counter += 1
        self.wda = FakeWdaSession(f"session-{self._session_counter}")
        self.tunnel = FakeOwnedTunnel()
        self.connected = True
        return self.snapshot()

    async def close(self) -> TransportStatus:
        self.close_count += 1
        self.closed = True
        self.tunnel.closed = True  # owned: released
        self.discarded_sessions.append(self.wda)  # owned: released
        self.wda = None
        # self.unowned_tunnel is deliberately never touched.
        return self.snapshot()

    # --- capture primitives ---

    async def screenshot(self) -> bytes:
        return _PNG_HEADER

    async def accessibility_source(self) -> str:
        return _ACCESSIBILITY

    async def screen_size(self) -> tuple[int, int]:
        return (100, 200)  # 1:1 with the 100x200 pixel frame

    # --- action primitives (record, then inject the fault) ---

    async def tap_at_point(self, x, y):
        self.actions.append(("tap_at_point", (x, y)))
        self._fault()

    async def drag(self, x1, y1, x2, y2, duration):
        self.actions.append(("drag", (x1, y1, x2, y2, duration)))
        self._fault()

    async def send_keys(self, text):
        self.actions.append(("send_keys", (text,)))
        self._fault()

    async def press_home(self):
        self.actions.append(("press_home", ()))
        self._fault()

    async def launch_app(self, bundle_id):
        self.actions.append(("launch_app", (bundle_id,)))
        self._fault()

    def _fault(self):
        exc = self._faults.get(len(self.actions) - 1)
        if exc is not None:
            raise exc


def make_runtime(max_batch_actions=32, **transport_kwargs):
    transport = FakeTransport(**transport_kwargs)
    return NativeIosRuntime(transport, max_batch_actions=max_batch_actions), transport


def run(awaitable):
    return asyncio.run(awaitable)


def expect_no_effect(error, code, phase):
    assert (error.code, error.phase, error.effect, error.retry_safe) == (
        code,
        phase,
        ErrorEffect.NONE,
        True,
    )


# --- status surface ------------------------------------------------------------


def test_status_reports_contract_fields_and_runtime_owned_batch_limit():
    runtime, transport = make_runtime()
    status = run(runtime.status())
    assert status.contract_version == "v0"
    assert status.lifecycle_state == LifecycleState.DISCONNECTED
    assert status.transport == TransportKind.NONE
    assert status.wda_state == WdaState.NONE
    assert status.current_revision is None
    assert status.limits.max_batch_actions == 32  # runtime-owned default
    assert status.capabilities["actions"][0] == "tap_point"
    assert status.last_error_code is None
    rendered = repr(status)
    for forbidden in ("udid", "pair_record", "screen_text", "raw_action_payload"):
        assert forbidden not in rendered.lower()

    runtime, _ = make_runtime(max_batch_actions=2)  # constructor-overridable
    assert run(runtime.status()).limits.max_batch_actions == 2


# --- R2-A06 --------------------------------------------------------------------


def test_r2_a06_mid_batch_timeout_after_send_is_effect_unknown_and_never_replayed():
    runtime, transport = make_runtime(faults={1: TimeoutError()})
    observation = run(runtime.observe())
    batch = [TapPoint(x=10, y=20), TapPoint(x=30, y=40), Home()]
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.execute(batch, expected_revision=observation.revision))
    error = err.value
    assert (error.code, error.phase, error.effect) == (
        ErrorCode.EFFECT_UNKNOWN,
        ErrorPhase.EXECUTION,
        ErrorEffect.UNKNOWN,
    )
    assert error.completed_actions == 1
    assert error.failed_action_index == 1
    assert error.retry_safe is False
    assert error.revision_invalidated is True
    # The second request was sent (recorded) before the timeout; the third was
    # never attempted, and the accepted revision is gone.
    assert len(transport.actions) == 2
    assert run(runtime.status()).current_revision is None
    assert run(runtime.status()).last_error_code == ErrorCode.EFFECT_UNKNOWN

    # No automatic replay: even after settling the event loop, the fake device
    # call count never grows after the failure.
    calls_after_failure = len(transport.actions)

    async def settle():
        for _ in range(3):
            await asyncio.sleep(0)
        return len(transport.actions)

    assert run(settle()) == calls_after_failure

    # A re-attempt of the same intent is fail-closed: the invalidated revision
    # rejects the whole batch preflight with zero device calls.
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.execute(batch, expected_revision=observation.revision))
    expect_no_effect(err.value, ErrorCode.STALE_REVISION, ErrorPhase.PREFLIGHT)
    assert len(transport.actions) == calls_after_failure


# --- R2-A07 --------------------------------------------------------------------


def test_r2_a07_recover_replaces_stale_plumbing_without_replaying_actions():
    runtime, transport = make_runtime()
    observation = run(runtime.observe())
    stale_wda = transport.wda
    stale_tunnel = transport.tunnel
    stale_wda.session_id = None  # the WDA session went stale

    result = run(runtime.recover())
    assert result.repaired is True
    assert transport.recreate_count == 1
    assert transport.wda is not stale_wda
    assert transport.wda.session_id == "session-2"
    assert stale_wda in transport.discarded_sessions
    assert transport.tunnel is not stale_tunnel

    # The pre-recovery revision is invalid, and replaying the planned action
    # is rejected preflight with zero device calls.
    assert run(runtime.status()).current_revision is None
    with pytest.raises(RuntimeOperationError) as err:
        run(
            runtime.execute(
                [TapPoint(x=10, y=20)], expected_revision=observation.revision
            )
        )
    expect_no_effect(err.value, ErrorCode.STALE_REVISION, ErrorPhase.PREFLIGHT)
    assert transport.actions == []  # recover replayed nothing, replay made no calls

    # The rebuilt plumbing is usable again through a fresh observation.
    fresh = run(runtime.observe())
    assert fresh.revision != observation.revision
    assert run(runtime.status()).lifecycle_state == LifecycleState.READY


def test_recover_failure_is_recovery_failed_no_effect():
    runtime, transport = make_runtime(recreate_error=TransportError("rsd rebuild failed"))
    observation = run(runtime.observe())
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.recover())
    error = err.value
    expect_no_effect(error, ErrorCode.RECOVERY_FAILED, ErrorPhase.LIFECYCLE)
    assert error.completed_actions is None
    assert error.failed_action_index is None
    assert transport.actions == []  # recovery never replays actions
    # The pre-recovery revision is invalidated even when recovery fails.
    assert run(runtime.status()).current_revision is None
    assert run(runtime.status()).last_error_code == ErrorCode.RECOVERY_FAILED


# --- R2-A08 --------------------------------------------------------------------


def test_r2_a08_close_is_idempotent_and_releases_only_owned_resources():
    runtime, transport = make_runtime()
    run(runtime.observe())
    unowned = transport.unowned_tunnel

    run(runtime.close())
    run(runtime.close())  # idempotent: no error, no second teardown
    assert transport.close_count == 1
    assert transport.tunnel.closed is True  # owned resource released
    assert transport.wda is None  # owned session handle released
    assert unowned.closed is False  # unowned resource untouched

    status = run(runtime.status())  # still callable
    assert status.lifecycle_state == LifecycleState.CLOSED
    assert status.transport == TransportKind.NONE
    assert status.wda_state == WdaState.NONE
    assert status.current_revision is None

    run(runtime.invalidate("post-close hygiene"))  # local-only no-op after close
    assert run(runtime.status()).lifecycle_state == LifecycleState.CLOSED


def test_operations_after_close_raise_runtime_closed_with_no_effect():
    runtime, transport = make_runtime()
    observation = run(runtime.observe())
    run(runtime.close())
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.observe())
    expect_no_effect(err.value, ErrorCode.RUNTIME_CLOSED, ErrorPhase.LIFECYCLE)
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.recover())
    expect_no_effect(err.value, ErrorCode.RUNTIME_CLOSED, ErrorPhase.LIFECYCLE)
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.execute([Home()], expected_revision=observation.revision))
    expect_no_effect(err.value, ErrorCode.RUNTIME_CLOSED, ErrorPhase.LIFECYCLE)
    assert transport.actions == []  # a closed runtime never touches the device


# --- no-effect execute rejections (zero device calls) ---------------------------


def test_stale_revision_rejected_before_any_device_call():
    runtime, transport = make_runtime()
    observation = run(runtime.observe())
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.execute([TapPoint(x=10, y=20)], expected_revision="rev-other"))
    expect_no_effect(err.value, ErrorCode.STALE_REVISION, ErrorPhase.PREFLIGHT)
    assert transport.actions == []
    # A no-effect rejection leaves the accepted revision intact.
    assert run(runtime.status()).current_revision == observation.revision


def test_empty_and_over_limit_batches_rejected_before_any_device_call():
    runtime, transport = make_runtime(max_batch_actions=2)
    observation = run(runtime.observe())
    for batch in ([], [Home(), Home(), Home()]):
        with pytest.raises(RuntimeOperationError) as err:
            run(runtime.execute(batch, expected_revision=observation.revision))
        expect_no_effect(err.value, ErrorCode.INVALID_REQUEST, ErrorPhase.PREFLIGHT)
    assert transport.actions == []
    assert run(runtime.status()).current_revision == observation.revision


def test_element_ref_from_another_revision_rejected_before_any_device_call():
    runtime, transport = make_runtime()
    first = run(runtime.observe())
    second = run(runtime.observe())  # supersedes the first revision
    with pytest.raises(RuntimeOperationError) as err:
        run(
            runtime.execute(
                [TapElement(ref=first.elements[-1].ref)],
                expected_revision=second.revision,
            )
        )
    expect_no_effect(err.value, ErrorCode.STALE_REVISION, ErrorPhase.PREFLIGHT)
    assert transport.actions == []


# --- happy path -----------------------------------------------------------------


def test_observe_then_execute_success_invalidates_revision():
    runtime, transport = make_runtime()
    observation = run(runtime.observe())
    assert observation.revision  # opaque non-empty revision token
    assert (observation.screen.width, observation.screen.height) == (100, 200)
    status = run(runtime.status())
    assert status.current_revision == observation.revision
    assert status.lifecycle_state == LifecycleState.READY

    result = run(
        runtime.execute(
            [TapPoint(x=10, y=20), TypeText(text="abc")],
            expected_revision=observation.revision,
        )
    )
    assert result.completed_actions == 2
    assert result.accepted_revision_invalidated is True
    assert transport.actions == [("tap_at_point", (10, 20)), ("send_keys", ("abc",))]
    assert run(runtime.status()).current_revision is None
    assert run(runtime.status()).last_error_code is None


def test_invalidate_is_local_only_and_never_a_device_call():
    runtime, transport = make_runtime()
    observation = run(runtime.observe())
    run(runtime.invalidate("caller replans"))
    assert run(runtime.status()).current_revision is None
    assert transport.actions == []
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.execute([Home()], expected_revision=observation.revision))
    expect_no_effect(err.value, ErrorCode.STALE_REVISION, ErrorPhase.PREFLIGHT)
    for bad_reason in ("", None, 7):
        with pytest.raises(RuntimeOperationError) as err:
            run(runtime.invalidate(bad_reason))
        expect_no_effect(err.value, ErrorCode.INVALID_REQUEST, ErrorPhase.PREFLIGHT)
    assert transport.actions == []


def test_invalidate_reason_is_bounded_and_rejected_before_side_effect():
    # R2 contract 4.4: the reason is machine-oriented and bounded for
    # traceability. The bound is finite and documented; anything outside it
    # is rejected with INVALID_REQUEST before any side effect (the accepted
    # revision stays current and zero device calls are made).
    assert INVALIDATE_REASON_MAX_LENGTH == 128
    runtime, transport = make_runtime()
    observation = run(runtime.observe())
    bad_reasons = [
        "",
        "   ",
        None,
        7,
        ["caller-replans"],
        "x" * (INVALIDATE_REASON_MAX_LENGTH + 1),
        "line1\nline2",
        "tab\there",
        "caf\u00e9",
    ]
    for bad_reason in bad_reasons:
        with pytest.raises(RuntimeOperationError) as err:
            run(runtime.invalidate(bad_reason))
        expect_no_effect(err.value, ErrorCode.INVALID_REQUEST, ErrorPhase.PREFLIGHT)
    # Every rejection left the revision intact and touched no device call.
    assert run(runtime.status()).current_revision == observation.revision
    assert transport.actions == []
    # The exact bound is accepted and invalidates locally. Traceability keeps
    # only a keyed fingerprint, never the raw reason.
    boundary = "r" * INVALIDATE_REASON_MAX_LENGTH
    run(runtime.invalidate(boundary))
    assert run(runtime.status()).current_revision is None
    assert transport.actions == []
    records = [r for r in runtime.trace.records if r.operation == "invalidate"]
    assert len(records) == 1
    assert records[0].detail is not None
    assert records[0].detail.startswith("reason#")
    assert boundary not in records[0].detail
    assert records[0].error_code is None


def test_observe_plumbing_failure_is_observation_failed_no_effect():
    runtime, transport = make_runtime(connect_error=WdaUnreachableError("probe failed"))
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.observe())
    expect_no_effect(err.value, ErrorCode.OBSERVATION_FAILED, ErrorPhase.LIFECYCLE)
    assert run(runtime.status()).last_error_code == ErrorCode.OBSERVATION_FAILED

    # Once the plumbing recovers, a successful observe clears the last error.
    transport._connect_error = None
    fresh = run(runtime.observe())
    assert fresh.revision
    assert run(runtime.status()).last_error_code is None
