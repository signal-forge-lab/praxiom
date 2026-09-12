"""R3-07 contract fixture runner: deterministic acceptance tests R2-A01..A10.

Drives the REAL public runtime (``praxiom.ios_runtime.NativeIosRuntime``,
the exact six-operation surface) with a fake transport injected at the upstream
boundary — the documented ``IosTransport`` operation surface in
``praxiom.ios_runtime.transport``, the only place the runtime reaches
device plumbing. No phone is required and no Phone Harness code is referenced.

Normative expectations come from the copied fixture artifact
``tests/fixtures/native-ios-runtime-v0.json`` (see ``tests/fixtures/PROVENANCE.md``
for provenance). Every test is named after its fixture ID and asserts the
fixture's semantic ``expect`` values — outcomes, error codes/phases/effects,
device-call counts/order, revision binding — never internal class or file
layout. Scenario R2-A11 needs a physical iPhone and is deliberately excluded.

``device_call_count`` is measured with the fake transport's call recorder: one
recorded entry per action-primitive call sent toward the device (plumbing such
as ``connect`` is not a device action call), so preflight rejections can be
proven to make zero device calls.
"""

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

from praxiom.ios_runtime.models import (
    Home,
    LifecycleState,
    RuntimeOperationError,
    TapElement,
    TapPoint,
    TransportKind,
    TypeText,
    WdaState,
)
from praxiom.ios_runtime.runtime import NativeIosRuntime
from praxiom.ios_runtime.transport import (
    TransportClosedError,
    TransportStatus,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "native-ios-runtime-v0.json"
_fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
SCENARIOS = {scenario["id"]: scenario for scenario in _fixture["scenarios"]}

# WDA logical points == screenshot pixels (1:1), so public pixel coordinates
# map identically; (100, 200) and (300, 400) from the fixture are in bounds.
_SCREEN = (390, 844)
# 24-byte PNG header: signature + IHDR length/type + pixel dimensions.
_PNG_HEADER = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    + _SCREEN[0].to_bytes(4, "big")
    + _SCREEN[1].to_bytes(4, "big")
)
_ACCESSIBILITY = (
    "<root>"
    '<window x="0" y="0" width="390" height="844"/>'
    '<button label="Go" x="10" y="20" width="30" height="40" enabled="true"/>'
    "</root>"
)

# Transport primitive -> public v0 action kind, for checking fixture
# ``device_call_order`` against the recorded device calls.
_DEVICE_CALL_KIND = {
    "tap_at_point": "tap_point",
    "drag": "drag",
    "send_keys": "type_text",
    "press_home": "home",
    "launch_app": "launch_app",
}


class _FakeOwnedTunnel:
    """Owned RSD tunnel handle; ``closed`` marks release."""

    def __init__(self) -> None:
        self.closed = False


class _FakeWdaSession:
    """Owned WDA client/session handle."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id


class FakeTransport:
    """Duck-typed stand-in for ``IosTransport`` at the upstream boundary.

    Implements the downstream operation surface documented in
    ``praxiom.ios_runtime.transport``:

    - ``device_calls`` records every ordered action-primitive call (the
      device-call recorder used for ``device_call_count`` assertions);
    - ``faults`` maps an action ordinal to an exception raised AFTER the call
      was recorded — i.e. after the request was sent (timeout-after-send);
    - owned resources are the RSD tunnel handle and the WDA session, released
      only by ``close()``; ``unowned_tunnel`` models a resource the runtime
      does not own and must never touch;
    - ``snapshot()`` projects the same lifecycle states as the real transport,
      so ``status()``/DEGRADED arrangements behave as with real plumbing.
    """

    def __init__(self, *, faults=None, connected: bool = False) -> None:
        # Privacy sentinel for R2-A01: a fake device identifier the status
        # projection must never be able to leak.
        self.udid = "00008101-FAKEUDIDNOTAREALDEVICE"
        self.tunnel = _FakeOwnedTunnel()
        self.wda = _FakeWdaSession("wda-session-1")
        self.unowned_tunnel = _FakeOwnedTunnel()
        self.device_calls: list[tuple[str, tuple]] = []
        self.close_count = 0
        self.recreate_count = 0
        self.connected = connected
        self.closed = False
        self._faults = dict(faults or {})

    # --- lifecycle ---

    def snapshot(self) -> TransportStatus:
        if self.closed:
            return TransportStatus(
                LifecycleState.CLOSED, TransportKind.NONE, WdaState.NONE,
                has_session=False,
            )
        if not self.connected:
            return TransportStatus(
                LifecycleState.DISCONNECTED, TransportKind.NONE, WdaState.NONE,
                has_session=False,
            )
        has_session = self.wda is not None and bool(self.wda.session_id)
        return TransportStatus(
            LifecycleState.READY if has_session else LifecycleState.DEGRADED,
            TransportKind.RSD_USERSPACE,
            WdaState.READY if has_session else WdaState.UNAVAILABLE,
            has_session=has_session,
        )

    async def connect(self) -> TransportStatus:
        if self.closed:
            raise TransportClosedError("transport is closed")
        self.connected = True
        return self.snapshot()

    async def recreate(self) -> TransportStatus:
        if self.closed:
            raise TransportClosedError("transport is closed")
        self.recreate_count += 1
        self.wda = _FakeWdaSession(f"wda-session-{self.recreate_count + 1}")
        return self.snapshot()

    async def close(self) -> TransportStatus:
        self.close_count += 1
        self.closed = True
        self.tunnel.closed = True  # owned: released
        self.wda = None  # owned: released
        # self.unowned_tunnel is deliberately never touched.
        return self.snapshot()

    # --- capture primitives ---

    async def screenshot(self) -> bytes:
        return _PNG_HEADER

    async def accessibility_source(self) -> str:
        return _ACCESSIBILITY

    async def screen_size(self) -> tuple[int, int]:
        return _SCREEN

    # --- action primitives (record the call, then inject the fault) ---

    async def tap_at_point(self, x, y):
        self._device_call("tap_at_point", (x, y))

    async def drag(self, x1, y1, x2, y2, duration):
        self._device_call("drag", (x1, y1, x2, y2, duration))

    async def send_keys(self, text):
        self._device_call("send_keys", (text,))

    async def press_home(self):
        self._device_call("press_home", ())

    async def launch_app(self, bundle_id):
        self._device_call("launch_app", (bundle_id,))

    def _device_call(self, method: str, args: tuple) -> None:
        self.device_calls.append((method, args))
        fault = self._faults.get(len(self.device_calls) - 1)
        if fault is not None:
            raise fault  # raised after the request was sent (recorded)


def run(awaitable):
    return asyncio.run(awaitable)


def make_runtime(max_batch_actions=32, **fake_kwargs):
    """Real public runtime over a fresh fake transport (fixture-style)."""
    fake = FakeTransport(**fake_kwargs)
    return NativeIosRuntime(fake, max_batch_actions=max_batch_actions), fake


def assert_preflight_rejection(error: RuntimeOperationError, scenario: dict) -> None:
    """Check a no-effect rejection against the fixture's error triple."""
    expect = scenario["expect"]
    assert expect["outcome"] == "error"
    assert error.code.value == expect["code"]
    assert error.phase.value == expect["phase"]
    assert error.effect.value == expect["effect"]
    assert error.retry_safe is True  # no-effect errors are safe to retry


# --- R2-A01 ---------------------------------------------------------------------


def test_r2_a01_ready_status_is_privacy_safe_and_advertises_limits():
    scenario = SCENARIOS["R2-A01"]
    expect = scenario["expect"]
    fake = FakeTransport(connected=True)  # given: runtime_state READY
    runtime = NativeIosRuntime(fake)  # R2-A01 uses the default 32

    status = run(runtime.status())

    assert expect["lifecycle_state"] == "READY"
    assert status.lifecycle_state.value == expect["lifecycle_state"]
    assert status.current_revision is None
    assert status.limits.max_batch_actions == expect["max_batch_actions"] == 32

    # Privacy: serialize the whole status projection and scan it — no
    # forbidden field name and no device identifier may appear anywhere.
    rendered = json.dumps(dataclasses.asdict(status), default=str).lower()
    for forbidden in expect["must_not_expose"]:
        assert forbidden not in rendered
    assert fake.udid.lower() not in rendered


# --- R2-A02 ---------------------------------------------------------------------


def test_r2_a02_observe_creates_revision_bound_element_refs():
    scenario = SCENARIOS["R2-A02"]
    expect = scenario["expect"]
    runtime, fake = make_runtime()

    observation = run(runtime.observe())

    assert expect["revision"] == "opaque-non-empty"
    assert isinstance(observation.revision, str) and observation.revision
    assert observation.screen.width > 0 and observation.screen.height > 0
    assert observation.elements  # the fake source supplies elements
    refs = [element.ref for element in observation.elements]
    assert all(isinstance(ref, str) and ref for ref in refs)  # opaque tokens
    assert len(set(refs)) == len(refs)  # unique per revision
    assert run(runtime.status()).current_revision == observation.revision

    # Revision-bound: a ref is usable with the revision that created it
    # (cross-revision rejection is proven by R2-A09).
    tappable = next(el for el in observation.elements if el.rect is not None)
    result = run(
        runtime.execute(
            [TapElement(ref=tappable.ref)], expected_revision=observation.revision
        )
    )
    assert result.completed_actions == 1
    assert fake.device_calls[0][0] == "tap_at_point"


# --- R2-A03 ---------------------------------------------------------------------


def test_r2_a03_valid_bounded_batch_executes_in_order():
    scenario = SCENARIOS["R2-A03"]
    expect = scenario["expect"]
    runtime, fake = make_runtime()  # default max_batch_actions = 32
    observation = run(runtime.observe())

    result = run(
        runtime.execute(
            [TapPoint(x=100, y=200), TypeText(text="abc")],
            expected_revision=observation.revision,
        )
    )

    assert expect["outcome"] == "success"
    assert result.completed_actions == expect["completed_actions"] == 2
    assert (
        result.accepted_revision_invalidated
        is expect["accepted_revision_invalidated"]
        is True
    )
    assert len(fake.device_calls) == expect["device_call_count"] == 2
    device_order = [_DEVICE_CALL_KIND[method] for method, _ in fake.device_calls]
    assert device_order == expect["device_call_order"] == ["tap_point", "type_text"]
    assert [outcome.kind for outcome in result.outcomes] == expect["device_call_order"]
    # After the first attempted mutation the accepted revision is invalidated.
    assert run(runtime.status()).current_revision is None


# --- R2-A04 ---------------------------------------------------------------------


def test_r2_a04_stale_revision_is_rejected_before_side_effects():
    scenario = SCENARIOS["R2-A04"]
    runtime, fake = make_runtime()
    current = run(runtime.observe())  # the current revision ("rev-new" role)

    with pytest.raises(RuntimeOperationError) as err:
        run(
            runtime.execute(
                [TapPoint(x=100, y=200)], expected_revision="rev-old"
            )
        )

    assert_preflight_rejection(err.value, scenario)
    assert len(fake.device_calls) == scenario["expect"]["device_call_count"] == 0
    # A no-effect rejection leaves the accepted revision intact.
    assert run(runtime.status()).current_revision == current.revision


# --- R2-A05 ---------------------------------------------------------------------


def test_r2_a05_invalid_later_action_rejects_entire_batch_before_side_effects():
    scenario = SCENARIOS["R2-A05"]
    runtime, fake = make_runtime()
    observation = run(runtime.observe())
    # The later type_text action omits its text (None) — models are deliberately
    # permissive so the whole batch can still reach whole-batch preflight.
    batch = [TapPoint(x=100, y=200), TypeText(text=None)]

    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.execute(batch, expected_revision=observation.revision))

    assert_preflight_rejection(err.value, scenario)
    # The valid first action must NOT have executed either: zero device calls.
    assert len(fake.device_calls) == scenario["expect"]["device_call_count"] == 0
    assert run(runtime.status()).current_revision == observation.revision


# --- R2-A06 ---------------------------------------------------------------------


def test_r2_a06_ambiguous_mid_batch_failure_is_never_blindly_retryable():
    scenario = SCENARIOS["R2-A06"]
    expect = scenario["expect"]
    # fault: transport timeout AFTER the request was sent, at action index 1.
    runtime, fake = make_runtime(faults={1: TimeoutError()})
    observation = run(runtime.observe())
    batch = [TapPoint(x=100, y=200), TapPoint(x=300, y=400)]

    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.execute(batch, expected_revision=observation.revision))

    error = err.value
    assert error.code.value == expect["code"] == "EFFECT_UNKNOWN"
    assert error.phase.value == expect["phase"] == "execution"
    assert error.effect.value == expect["effect"] == "UNKNOWN"
    assert error.completed_actions == expect["completed_actions"] == 1
    assert error.failed_action_index == expect["failed_action_index"] == 1
    assert error.retry_safe is expect["retry_safe"] is False
    assert (
        error.revision_invalidated is expect["accepted_revision_invalidated"] is True
    )
    assert run(runtime.status()).current_revision is None

    # automatic_replay_count stays 0: after the failure the device-call count
    # never grows — not on the settled loop, and not through any re-attempt
    # (a blind replay would resend an action whose effect is unprovable).
    calls_at_failure = len(fake.device_calls)

    async def settle():
        for _ in range(3):
            await asyncio.sleep(0)
        return len(fake.device_calls)

    assert run(settle()) == calls_at_failure
    with pytest.raises(RuntimeOperationError) as err:
        run(runtime.execute(batch, expected_revision=observation.revision))
    assert err.value.code.value == "STALE_REVISION"  # re-attempt fails closed
    replayed = len(fake.device_calls) - calls_at_failure
    assert replayed == expect["automatic_replay_count"] == 0


# --- R2-A07 ---------------------------------------------------------------------


def test_r2_a07_recover_replaces_stale_plumbing_without_replaying_actions():
    scenario = SCENARIOS["R2-A07"]
    expect = scenario["expect"]
    runtime, fake = make_runtime()
    revision_before = run(runtime.observe())  # the "rev-before" role
    # given: stale WDA session -> DEGRADED runtime with WDA UNAVAILABLE.
    fake.wda.session_id = None
    stale_wda = fake.wda
    status = run(runtime.status())
    assert status.lifecycle_state.value == "DEGRADED"
    assert status.wda_state.value == scenario["given"]["wda_state"] == "UNAVAILABLE"

    result = run(runtime.recover())

    assert expect["outcome"] == "recovered"
    assert result.repaired is True
    assert fake.wda is not stale_wda  # plumbing was replaced, not reused
    # recover replays zero actions: it knows nothing about actions.
    assert len(fake.device_calls) == expect["action_replay_count"] == 0
    # The pre-recovery revision is invalid: a stale-revision batch with the
    # pre-recovery token is rejected preflight with zero device calls.
    assert expect["revision_before_is_invalid"] is True
    assert run(runtime.status()).current_revision is None
    with pytest.raises(RuntimeOperationError) as err:
        run(
            runtime.execute(
                [TapPoint(x=100, y=200)],
                expected_revision=revision_before.revision,
            )
        )
    assert err.value.code.value == "STALE_REVISION"
    assert len(fake.device_calls) == 0
    # A fresh observe is required before any further action — and it works
    # against the rebuilt plumbing.
    assert expect["future_observe_required"] is True
    fresh = run(runtime.observe())
    assert fresh.revision != revision_before.revision


# --- R2-A08 ---------------------------------------------------------------------


def test_r2_a08_close_is_idempotent_and_releases_only_owned_resources():
    scenario = SCENARIOS["R2-A08"]
    expect = scenario["expect"]
    runtime, fake = make_runtime()
    run(runtime.observe())  # establish the owned plumbing (rsd handle + wda session)

    for _ in range(scenario["when"]["call_count"]):  # close is called twice
        run(runtime.close())

    assert expect["outcome"] == "success"
    assert fake.close_count == 1  # idempotent: owned resources released once
    assert expect["owned_resources_closed"] is True
    assert fake.tunnel.closed is True  # owned rsd handle released
    assert fake.wda is None  # owned wda session released
    # Nothing the runtime does not own is ever killed or released.
    assert expect["unowned_processes_killed"] == 0
    assert fake.unowned_tunnel.closed is False
    # status() stays callable and reports CLOSED.
    assert expect["status_still_callable"] is True
    status = run(runtime.status())
    assert status.lifecycle_state.value == expect["lifecycle_state"] == "CLOSED"


# --- R2-A09 ---------------------------------------------------------------------


def test_r2_a09_element_reference_from_another_revision_is_rejected():
    scenario = SCENARIOS["R2-A09"]
    runtime, fake = make_runtime()
    revision_a = run(runtime.observe())  # the "rev-a" role: created the ref
    revision_b = run(runtime.observe())  # the current "rev-b" role
    foreign_ref = revision_a.elements[0].ref  # a ref created by rev-a

    with pytest.raises(RuntimeOperationError) as err:
        run(
            runtime.execute(
                [TapElement(ref=foreign_ref)], expected_revision=revision_b.revision
            )
        )

    assert_preflight_rejection(err.value, scenario)
    assert err.value.code.value == "STALE_REVISION"
    assert len(fake.device_calls) == scenario["expect"]["device_call_count"] == 0


# --- R2-A10 ---------------------------------------------------------------------


def test_r2_a10_over_limit_batch_is_rejected_before_side_effects():
    scenario = SCENARIOS["R2-A10"]
    runtime, fake = make_runtime(
        max_batch_actions=scenario["given"]["max_batch_actions"]  # fixture: 2
    )
    observation = run(runtime.observe())
    assert run(runtime.status()).limits.max_batch_actions == 2

    with pytest.raises(RuntimeOperationError) as err:
        run(
            runtime.execute(
                [Home(), Home(), Home()], expected_revision=observation.revision
            )
        )

    assert_preflight_rejection(err.value, scenario)
    assert len(fake.device_calls) == scenario["expect"]["device_call_count"] == 0
    assert run(runtime.status()).current_revision == observation.revision
