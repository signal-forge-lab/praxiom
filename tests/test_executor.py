"""R3-04 executor tests: whole-batch preflight + ordered execution.

Covers the executor slice of the R2 acceptance fixtures: R2-A03 (in-order
batch), R2-A04 (stale revision), R2-A05 (invalid later action), R2-A06
(timeout after send -> EFFECT_UNKNOWN, never replayed), R2-A09 (foreign
element ref), R2-A10 (over-limit), plus coordinate conversion and the absence
of any display-name-to-bundle heuristic.

Deterministic: fakes at the transport and revision-registry seams, no device
required. The fake transport records every device-facing call so rejected
preflights can be proven to make zero calls.
"""

import asyncio
import math

import pytest
from pymobiledevice3.exceptions import ConnectionTerminatedError, StreamClosedError, WdaError

import praxiom.ios_runtime.executor as executor_module
from praxiom.ios_runtime.executor import (
    _MAX_DRAG_DURATION_S,
    _SWIPE_DURATION_S,
    ActionExecutor,
)
from praxiom.ios_runtime.models import (
    Drag,
    Element,
    ErrorCode,
    ErrorEffect,
    ErrorPhase,
    Home,
    LaunchApp,
    Rect,
    RuntimeOperationError,
    ScreenSize,
    Swipe,
    TapElement,
    TapPoint,
    TypeText,
)
from praxiom.ios_runtime.transport import WdaUnreachableError

REVISION = "rev-1"


class WdaRejection(Exception):
    """Stands in for upstream WdaError: definitive WDA-level rejection."""


class FakeTransport:
    """Records every device-facing call; injects faults after a call is made.

    ``faults`` maps the device-call ordinal (== action index, since every v0
    action maps to exactly one device call) to the exception the primitive
    raises after the request was sent.
    """

    def __init__(self, *, connect_error=None, faults=None):
        self.connect_count = 0
        self.calls = []
        self._connect_error = connect_error
        self._faults = faults or {}

    async def connect(self):
        self.connect_count += 1
        if self._connect_error is not None:
            raise self._connect_error

    async def tap_at_point(self, x, y):
        self.calls.append(("tap_at_point", (x, y)))
        self._fault()

    async def drag(self, x1, y1, x2, y2, duration):
        self.calls.append(("drag", (x1, y1, x2, y2, duration)))
        self._fault()

    async def send_keys(self, text):
        self.calls.append(("send_keys", (text,)))
        self._fault()

    async def press_home(self):
        self.calls.append(("press_home", ()))
        self._fault()

    async def launch_app(self, bundle_id):
        self.calls.append(("launch_app", (bundle_id,)))
        self._fault()

    def _fault(self):
        exc = self._faults.get(len(self.calls) - 1)
        if exc is not None:
            raise exc


class FakeRegistry:
    """Revision registry standing in for the runtime-owned R3-03/R3-05 state."""

    def __init__(self, *, current=REVISION, px=(400, 800), logical=(200, 400), elements=None):
        self._current = current
        self._px = ScreenSize(width=px[0], height=px[1])
        self._logical = logical
        self._elements = elements or {}

    def current_revision(self):
        return self._current

    def screen_size(self, revision):
        return self._px if revision == self._current else None

    def logical_screen_size(self, revision):
        return self._logical if revision == self._current else None

    def element(self, revision, ref):
        if revision != self._current:
            return None
        return self._elements.get(ref)


def make_executor(transport=None, registry=None, max_batch_actions=32):
    return ActionExecutor(
        transport if transport is not None else FakeTransport(),
        registry if registry is not None else FakeRegistry(),
        max_batch_actions=max_batch_actions,
    )


def run(executor, actions, *, expected_revision=REVISION):
    return asyncio.run(executor.execute(actions, expected_revision=expected_revision))


def expect_no_effect(exc_info, code):
    error = exc_info.value
    assert (error.code, error.phase, error.effect, error.retry_safe) == (
        code,
        ErrorPhase.PREFLIGHT,
        ErrorEffect.NONE,
        True,
    )


# --- R2-A03 ------------------------------------------------------------------


def test_r2_a03_valid_batch_executes_in_order_and_invalidates_revision():
    transport = FakeTransport()
    executor = make_executor(transport)
    result = run(executor, [TapPoint(x=100, y=200), TypeText(text="abc")])
    assert transport.calls == [("tap_at_point", (50, 100)), ("send_keys", ("abc",))]
    assert transport.connect_count == 1  # one connect, one shared session
    assert result.completed_actions == 2
    assert result.accepted_revision_invalidated is True
    assert [(o.index, o.kind) for o in result.outcomes] == [
        (0, "tap_point"),
        (1, "type_text"),
    ]


def test_all_seven_action_kinds_map_to_transport_primitives_in_order():
    transport = FakeTransport()
    executor = make_executor(transport)
    result = run(
        executor,
        [
            TapPoint(x=100, y=200),
            Swipe(direction="up", distance=0.5),
            Drag(start_x=10, start_y=20, end_x=300, end_y=700, duration=0.5),
            TypeText(text="hi"),
            Home(),
            LaunchApp(bundle_id="com.apple.Preferences"),
        ],
    )
    assert [o.kind for o in result.outcomes] == [
        "tap_point",
        "swipe",
        "drag",
        "type_text",
        "home",
        "launch_app",
    ]
    assert transport.calls == [
        ("tap_at_point", (50, 100)),
        ("drag", (100, 300, 100, 100, _SWIPE_DURATION_S)),
        ("drag", (5, 10, 150, 350, 0.5)),
        ("send_keys", ("hi",)),
        ("press_home", ()),
        ("launch_app", ("com.apple.Preferences",)),
    ]


# --- R2-A04 ------------------------------------------------------------------


def test_r2_a04_stale_revision_rejects_before_any_device_call():
    transport = FakeTransport()
    executor = make_executor(transport, FakeRegistry(current="rev-new"))
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapPoint(x=100, y=200)], expected_revision="rev-old")
    expect_no_effect(err, ErrorCode.STALE_REVISION)
    assert transport.calls == []
    assert transport.connect_count == 0


def test_malformed_expected_revision_is_invalid_request():
    transport = FakeTransport()
    executor = make_executor(transport)
    for bad in (None, "", 7):
        with pytest.raises(RuntimeOperationError) as err:
            run(executor, [Home()], expected_revision=bad)
        expect_no_effect(err, ErrorCode.INVALID_REQUEST)
    assert transport.calls == []


# --- R2-A05 ------------------------------------------------------------------


def test_r2_a05_invalid_later_action_rejects_whole_batch():
    transport = FakeTransport()
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapPoint(x=100, y=200), TypeText(text="")])
    expect_no_effect(err, ErrorCode.INVALID_REQUEST)
    assert transport.calls == []
    assert transport.connect_count == 0


def test_empty_batch_rejected_before_any_device_call():
    transport = FakeTransport()
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [])
    expect_no_effect(err, ErrorCode.INVALID_REQUEST)
    assert transport.calls == []


def test_over_limit_batch_rejected_before_any_device_call():
    transport = FakeTransport()
    executor = make_executor(transport, max_batch_actions=2)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [Home(), Home(), Home()])
    expect_no_effect(err, ErrorCode.INVALID_REQUEST)
    assert transport.calls == []
    assert transport.connect_count == 0


def test_non_sequence_batch_rejected():
    transport = FakeTransport()
    executor = make_executor(transport)
    for bad in ("tap_point", {"kind": "tap_point"}, None):
        with pytest.raises(RuntimeOperationError) as err:
            run(executor, bad)
        expect_no_effect(err, ErrorCode.INVALID_REQUEST)
    assert transport.calls == []


def test_unsupported_action_kind_rejected_before_any_device_call():
    transport = FakeTransport()
    executor = make_executor(transport)
    for foreign in (object(), {"kind": "tap_point"}, None):
        with pytest.raises(RuntimeOperationError) as err:
            run(executor, [foreign])
        error = err.value
        assert (error.code, error.phase, error.effect) == (
            ErrorCode.UNSUPPORTED_ACTION,
            ErrorPhase.PREFLIGHT,
            ErrorEffect.NONE,
        )
    assert transport.calls == []


# --- coordinate conversion -----------------------------------------------------


def test_tap_point_pixel_to_logical_conversion():
    transport = FakeTransport()
    executor = make_executor(transport)  # px 400x800 -> logical 200x400 (x0.5)
    run(executor, [TapPoint(x=101, y=201)])
    assert transport.calls == [("tap_at_point", (50, 100))]


def test_tap_point_at_pixel_boundary_clamps_inside_logical_screen():
    transport = FakeTransport()
    executor = make_executor(transport)
    run(executor, [TapPoint(x=399, y=799)])
    assert transport.calls == [("tap_at_point", (199, 399))]


@pytest.mark.parametrize(
    ("x", "y"), [(-1, 0), (0, -1), (400, 0), (0, 800), (400, 800)]
)
def test_out_of_bounds_tap_point_rejected_before_any_device_call(x, y):
    transport = FakeTransport()
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapPoint(x=x, y=y)])
    expect_no_effect(err, ErrorCode.INVALID_REQUEST)
    assert transport.calls == []


@pytest.mark.parametrize(("x", "y"), [(100.0, 0), (0, True), (None, 0), (0, "10")])
def test_non_integer_coordinates_rejected(x, y):
    transport = FakeTransport()
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapPoint(x=x, y=y)])
    expect_no_effect(err, ErrorCode.INVALID_REQUEST)
    assert transport.calls == []


# --- element refs (R2-A09) -----------------------------------------------------


def _registry_with_button():
    return FakeRegistry(
        elements={
            "btn": Element(
                ref="btn",
                role="button",
                source="accessibility",
                rect=Rect(x=100, y=200, width=50, height=50),
            )
        }
    )


def test_tap_element_taps_element_center_in_logical_points():
    transport = FakeTransport()
    executor = make_executor(transport, _registry_with_button())
    run(executor, [TapElement(ref="btn")])
    # center (125.0, 225.0) px -> (62.5, 112.5) logical -> (62, 112)
    assert transport.calls == [("tap_at_point", (62, 112))]


def test_r2_a09_element_ref_from_other_revision_rejected():
    transport = FakeTransport()
    executor = make_executor(transport, FakeRegistry(current="rev-b"))
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapElement(ref="element-from-rev-a")], expected_revision="rev-b")
    expect_no_effect(err, ErrorCode.STALE_REVISION)
    assert transport.calls == []


@pytest.mark.parametrize(
    "rect", [None, Rect(x=0, y=0, width=0, height=10), Rect(x=0, y=0, width=10, height=0)]
)
def test_tap_element_without_tappable_rect_rejected(rect):
    transport = FakeTransport()
    registry = FakeRegistry(
        elements={"btn": Element(ref="btn", role="button", source="accessibility", rect=rect)}
    )
    executor = make_executor(transport, registry)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapElement(ref="btn")])
    expect_no_effect(err, ErrorCode.INVALID_REQUEST)
    assert transport.calls == []


# --- drag / swipe ----------------------------------------------------------------


def test_drag_maps_to_logical_transport_drag():
    transport = FakeTransport()
    executor = make_executor(transport)
    run(executor, [Drag(start_x=10, start_y=20, end_x=300, end_y=700, duration=0.5)])
    assert transport.calls == [("drag", (5, 10, 150, 350, 0.5))]


@pytest.mark.parametrize("duration", [0, -1, _MAX_DRAG_DURATION_S + 1, math.nan, True])
def test_drag_duration_out_of_bounds_rejected(duration):
    transport = FakeTransport()
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(
            executor,
            [Drag(start_x=0, start_y=0, end_x=100, end_y=100, duration=duration)],
        )
    expect_no_effect(err, ErrorCode.INVALID_REQUEST)
    assert transport.calls == []


def test_swipe_composes_directional_drag_in_logical_points():
    transport = FakeTransport()
    executor = make_executor(transport)
    run(executor, [Swipe(direction="up", distance=0.5)])
    # center (200, 400) px; half-extent 200px -> start (200, 600), end (200, 200) px
    assert transport.calls == [("drag", (100, 300, 100, 100, _SWIPE_DURATION_S))]


def test_swipe_full_distance_clamped_inside_logical_screen():
    transport = FakeTransport()
    executor = make_executor(transport)
    run(executor, [Swipe(direction="up", distance=1.0)])
    # start (200, 800) px clamps to logical y=399; end (200, 0) px -> (100, 0)
    assert transport.calls == [("drag", (100, 399, 100, 0, _SWIPE_DURATION_S))]


@pytest.mark.parametrize(
    ("direction", "distance"),
    [("inward", 0.5), ("UP", 0.5), ("up", 0.0), ("up", 1.5), ("up", math.nan), ("up", True)],
)
def test_invalid_swipe_direction_or_distance_rejected(direction, distance):
    transport = FakeTransport()
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [Swipe(direction=direction, distance=distance)])
    expect_no_effect(err, ErrorCode.INVALID_REQUEST)
    assert transport.calls == []


# --- attempted-effect semantics (R2-A06) -----------------------------------------


def test_r2_a06_timeout_after_send_is_effect_unknown_and_never_replayed():
    transport = FakeTransport(faults={1: TimeoutError()})
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapPoint(x=100, y=200), TapPoint(x=300, y=400)])
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
    # Two calls were sent (the second timed out after send); execution stopped
    # there and the executor never replayed the ambiguous action.
    assert transport.calls == [
        ("tap_at_point", (50, 100)),
        ("tap_at_point", (150, 200)),
    ]


def test_upstream_connection_terminated_after_send_is_effect_unknown():
    transport = FakeTransport(faults={0: ConnectionTerminatedError()})
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapPoint(x=100, y=200)])
    error = err.value
    assert (error.code, error.phase, error.effect) == (
        ErrorCode.EFFECT_UNKNOWN,
        ErrorPhase.EXECUTION,
        ErrorEffect.UNKNOWN,
    )
    assert error.completed_actions == 0
    assert error.failed_action_index == 0
    assert error.retry_safe is False
    assert error.revision_invalidated is True
    assert transport.calls == [("tap_at_point", (50, 100))]


@pytest.mark.parametrize(
    "fault",
    [
        StreamClosedError(),
        WdaError("WDA response did not contain headers terminator"),
    ],
)
def test_upstream_after_send_eof_variants_are_effect_unknown(fault):
    transport = FakeTransport(faults={0: fault})
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapPoint(x=100, y=200)])
    error = err.value
    assert (error.code, error.phase, error.effect) == (
        ErrorCode.EFFECT_UNKNOWN,
        ErrorPhase.EXECUTION,
        ErrorEffect.UNKNOWN,
    )
    assert error.retry_safe is False
    assert error.revision_invalidated is True
    assert transport.calls == [("tap_at_point", (50, 100))]


def test_ordinary_wda_error_remains_definitive():
    transport = FakeTransport(faults={0: WdaError("element not interactable", status_code=400)})
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapPoint(x=100, y=200)])
    assert (err.value.code, err.value.effect) == (
        ErrorCode.ACTION_FAILED,
        ErrorEffect.PARTIAL,
    )


def test_definitive_rejection_is_action_failed_partial():
    transport = FakeTransport(faults={1: WdaRejection()})
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [TapPoint(x=100, y=200), TapPoint(x=300, y=400)])
    error = err.value
    assert (error.code, error.phase, error.effect) == (
        ErrorCode.ACTION_FAILED,
        ErrorPhase.EXECUTION,
        ErrorEffect.PARTIAL,
    )
    assert error.completed_actions == 1
    assert error.failed_action_index == 1
    assert error.retry_safe is False
    assert error.revision_invalidated is True
    # The rejected request was sent and answered; execution stopped there.
    assert transport.calls == [
        ("tap_at_point", (50, 100)),
        ("tap_at_point", (150, 200)),
    ]


def test_plumbing_failure_before_first_action_is_not_ready_with_no_effect():
    transport = FakeTransport(connect_error=WdaUnreachableError("probe failed"))
    executor = make_executor(transport)
    with pytest.raises(RuntimeOperationError) as err:
        run(executor, [Home()])
    error = err.value
    assert (error.code, error.phase, error.effect, error.retry_safe) == (
        ErrorCode.NOT_READY,
        ErrorPhase.LIFECYCLE,
        ErrorEffect.NONE,
        True,
    )
    assert transport.calls == []
    assert transport.connect_count == 1


# --- launch_app has no display-name heuristic -------------------------------------


def test_launch_app_passes_bundle_id_verbatim_with_no_heuristic_surface():
    transport = FakeTransport()
    executor = make_executor(transport)
    result = run(executor, [LaunchApp(bundle_id="Settings")])  # human name, not a bundle id
    assert transport.calls == [("launch_app", ("Settings",))]
    assert result.completed_actions == 1
    # No display-name-to-bundle resolution surface exists on the module.
    public = [name for name in vars(executor_module) if not name.startswith("_")]
    assert not any(
        marker in name.lower()
        for name in public
        for marker in ("display", "app_name", "resolve", "heuristic", "alias")
    )
