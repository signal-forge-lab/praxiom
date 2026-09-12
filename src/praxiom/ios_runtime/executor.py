"""Whole-batch preflight and ordered execution for Native iOS Runtime v0 (R3-04).

Implements the ``execute()`` semantics of the R2 contract sections 4.3 / 5 for
exactly the v0 action set (tap_point, tap_element, drag, swipe, type_text,
home, launch_app):

- ``expected_revision`` is mandatory for every batch — no bypass for
  home/launch_app;
- the whole batch is validated before the first device side effect: empty
  batch, over-limit batch (against the runtime-owned ``max_batch_actions``),
  stale revision, coordinate bounds against the observation screen, swipe
  direction/distance, drag duration bounds, required strings, and
  element-ref revision binding all reject with a no-effect error and zero
  transport calls;
- public coordinates are full-screen screenshot pixels of the accepted
  revision; the conversion to WDA logical points is internal and linear
  (per-revision pixel/logical screen dimensions from the registry);
- validated actions execute in order through the primitive surface documented
  in ``transport.py`` — one ``connect()`` per batch, then every action reuses
  the transport's single owned WDA session;
- after the first attempted mutation the accepted revision is invalidated:
  the executor never mutates the registry itself, it reports the
  invalidation to the caller via
  ``ExecutionResult.accepted_revision_invalidated`` (success) or
  ``RuntimeOperationError.revision_invalidated`` (failure), and the caller
  must invalidate its registry accordingly;
- execution stops at the first failed action. A connection-class failure or
  timeout after the request reached the device is ``EFFECT_UNKNOWN`` — the
  effect cannot be proven and the action is never automatically replayed;
  a definitive WDA rejection or plumbing failure is ``ACTION_FAILED`` with
  ``effect=PARTIAL`` (this action provably did not apply). Both are
  attempted-effect errors: ``phase=execution``, ``retry_safe=False``,
  ``revision_invalidated=True``, with completed count and failed index.

The registry is runtime-owned revision state (R3-03/R3-05); this module only
defines the read-only shape the executor consumes.

Privacy: errors are built exclusively from structured fields — raw action
payloads, screen text, and device identifiers can never enter a message.
"""

import math
import time
from collections.abc import Sequence
from typing import Protocol

from praxiom.ios_runtime.models import (
    Action,
    ActionOutcome,
    Drag,
    Element,
    ErrorEffect,
    ErrorCode,
    ErrorPhase,
    ExecutionResult,
    Home,
    LaunchApp,
    RuntimeOperationError,
    ScreenSize,
    Swipe,
    TapElement,
    TapPoint,
    TypeText,
)
from praxiom.ios_runtime.transport import IosTransport, TransportError

__all__ = ["ActionExecutor", "RevisionRegistry"]

# Drag duration is positive and bounded by implementation safety limits
# (contract 4.3).
_MAX_DRAG_DURATION_S = 10.0
# Internal finger-travel time for a composed directional swipe.
_SWIPE_DURATION_S = 0.3
_SWIPE_DIRECTIONS = frozenset({"up", "down", "left", "right"})

# Prepared device call: (public action kind, transport method name, args).
_Prepared = tuple[str, str, tuple[object, ...]]
_Point = tuple[int, int]


def _is_ambiguous_execution_failure(exc: Exception) -> bool:
    """Return whether an after-send failure leaves the device effect unknown.

    ``pymobiledevice3.exceptions.ConnectionTerminatedError`` and its subclasses
    are intentionally matched by MRO identity rather than imported here. That
    keeps this module importable in static-analysis/tooling environments that
    do not install the pinned device dependency while still recognizing the
    pinned upstream abrupt/incomplete-read failures at runtime. The pinned WDA
    client also converts one after-send EOF case into a ``WdaError`` with the
    exact headers-terminator message below; that specific case is ambiguous,
    while ordinary WDA rejections remain definitive.
    """
    if isinstance(exc, (ConnectionError, OSError, TimeoutError)):
        return True
    mro = type(exc).__mro__
    if any(
        cls.__module__ == "pymobiledevice3.exceptions"
        and cls.__name__ == "ConnectionTerminatedError"
        for cls in mro
    ):
        return True
    exc_type = type(exc)
    return (
        exc_type.__module__ == "pymobiledevice3.exceptions"
        and exc_type.__name__ == "WdaError"
        and getattr(exc, "status_code", None) is None
        and str(exc) == "WDA response did not contain headers terminator"
    )


class RevisionRegistry(Protocol):
    """Read-only revision state the executor consumes (runtime-owned).

    Every method is an in-memory lookup — never device I/O — so preflight
    performs zero device calls. Unknown revisions and refs must answer
    ``None`` so preflight fails closed.
    """

    def current_revision(self) -> str | None: ...

    def screen_size(self, revision: str) -> ScreenSize | None:
        """Full-screen screenshot-pixel dimensions of the revision."""

    def logical_screen_size(self, revision: str) -> tuple[int, int] | None:
        """WDA logical-point screen dimensions captured with the revision."""

    def element(self, revision: str, ref: str) -> Element | None:
        """Element bound to ``ref`` within exactly ``revision``, else ``None``."""


def _no_effect(code: ErrorCode) -> RuntimeOperationError:
    """No-effect preflight rejection: nothing was sent to the device."""
    return RuntimeOperationError(
        code, ErrorPhase.PREFLIGHT, ErrorEffect.NONE, retry_safe=True
    )


def _to_logical(
    point_px: tuple[float, float], px: ScreenSize, logical: tuple[int, int]
) -> _Point:
    """Screenshot pixels -> WDA logical points (internal linear conversion).

    Truncates to integer points and clamps into the logical screen so a
    boundary pixel maps inside the touchable area.
    """
    lx = int(point_px[0] * logical[0] / px.width)
    ly = int(point_px[1] * logical[1] / px.height)
    return min(max(lx, 0), logical[0] - 1), min(max(ly, 0), logical[1] - 1)


def _swipe_points(
    direction: str, distance: float, px: ScreenSize
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Center-anchored finger path in screenshot pixels.

    ``direction`` names the finger travel direction; ``distance`` 1.0 spans
    the full screen dimension edge to edge.
    """
    cx, cy = px.width / 2.0, px.height / 2.0
    hx, hy = distance * px.width / 2.0, distance * px.height / 2.0
    if direction == "up":
        return (cx, cy + hy), (cx, cy - hy)
    if direction == "down":
        return (cx, cy - hy), (cx, cy + hy)
    if direction == "left":
        return (cx + hx, cy), (cx - hx, cy)
    return (cx - hx, cy), (cx + hx, cy)  # right


def _require_point(x: object, y: object, px: ScreenSize) -> _Point:
    for value in (x, y):
        if not isinstance(value, int) or isinstance(value, bool):
            raise _no_effect(ErrorCode.INVALID_REQUEST)
    if not (0 <= x < px.width and 0 <= y < px.height):
        raise _no_effect(ErrorCode.INVALID_REQUEST)
    return x, y


def _require_finite(value: object) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise _no_effect(ErrorCode.INVALID_REQUEST)
    return float(value)


def _require_non_empty_str(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise _no_effect(ErrorCode.INVALID_REQUEST)
    return value


class ActionExecutor:
    """Preflights and executes one ordered action batch per ``execute()`` call."""

    def __init__(
        self,
        transport: IosTransport,
        registry: RevisionRegistry,
        *,
        max_batch_actions: int,
    ) -> None:
        self._transport = transport
        self._registry = registry
        self._max_batch_actions = max_batch_actions
        # Bound once: every prepared action dispatches to one of these five
        # primitives, all sharing the transport's single owned WDA session.
        self._primitives = {
            "tap_at_point": transport.tap_at_point,
            "drag": transport.drag,
            "send_keys": transport.send_keys,
            "press_home": transport.press_home,
            "launch_app": transport.launch_app,
        }

    async def execute(
        self, actions: Sequence[Action], *, expected_revision: str
    ) -> ExecutionResult:
        """Validate the whole batch, then execute it in order.

        Raises ``RuntimeOperationError``: no-effect codes for a rejected
        preflight (zero device calls), ``EFFECT_UNKNOWN``/``ACTION_FAILED``
        for attempted-effect failures after the first mutation was sent.
        """
        plan = self._preflight(actions, expected_revision)

        # Plumbing before the first action; no-op fast path when READY.
        try:
            await self._transport.connect()
        except TransportError:
            raise RuntimeOperationError(
                ErrorCode.NOT_READY,
                ErrorPhase.LIFECYCLE,
                ErrorEffect.NONE,
                retry_safe=True,
            ) from None

        outcomes: list[ActionOutcome] = []
        for index, (kind, method, args) in enumerate(plan):
            started = time.perf_counter()
            try:
                await self._primitives[method](*args)
            except Exception as exc:
                if _is_ambiguous_execution_failure(exc):
                    # The request reached the device; its effect is unprovable
                    # and must never be automatically replayed.
                    raise RuntimeOperationError(
                        ErrorCode.EFFECT_UNKNOWN,
                        ErrorPhase.EXECUTION,
                        ErrorEffect.UNKNOWN,
                        retry_safe=False,
                        completed_actions=index,
                        failed_action_index=index,
                        revision_invalidated=True,
                    ) from None
                # Definitive failure (WDA rejection or plumbing): this action
                # provably did not apply; the earlier ones did.
                raise RuntimeOperationError(
                    ErrorCode.ACTION_FAILED,
                    ErrorPhase.EXECUTION,
                    ErrorEffect.PARTIAL,
                    retry_safe=False,
                    completed_actions=index,
                    failed_action_index=index,
                    revision_invalidated=True,
                ) from None
            outcomes.append(
                ActionOutcome(
                    index=index,
                    kind=kind,
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                )
            )

        return ExecutionResult(
            completed_actions=len(outcomes),
            accepted_revision_invalidated=True,
            outcomes=tuple(outcomes),
        )

    # --- preflight (zero device I/O) ----------------------------------------

    def _preflight(
        self, actions: Sequence[Action], expected_revision: str
    ) -> list[_Prepared]:
        if isinstance(actions, (str, bytes)) or not isinstance(actions, Sequence):
            raise _no_effect(ErrorCode.INVALID_REQUEST)
        if len(actions) == 0:
            raise _no_effect(ErrorCode.INVALID_REQUEST)
        if len(actions) > self._max_batch_actions:
            raise _no_effect(ErrorCode.INVALID_REQUEST)
        if not isinstance(expected_revision, str) or not expected_revision:
            raise _no_effect(ErrorCode.INVALID_REQUEST)
        current = self._registry.current_revision()
        if current is None or expected_revision != current:
            raise _no_effect(ErrorCode.STALE_REVISION)
        px = self._registry.screen_size(expected_revision)
        logical = self._registry.logical_screen_size(expected_revision)
        if (
            px is None
            or logical is None
            or px.width <= 0
            or px.height <= 0
            or logical[0] <= 0
            or logical[1] <= 0
        ):
            # Accepted revision without usable geometry: fail closed.
            raise _no_effect(ErrorCode.STALE_REVISION)
        return [
            self._prepare(action, px, logical, expected_revision) for action in actions
        ]

    def _prepare(
        self,
        action: object,
        px: ScreenSize,
        logical: tuple[int, int],
        revision: str,
    ) -> _Prepared:
        if isinstance(action, TapPoint):
            x, y = _require_point(action.x, action.y, px)
            return action.kind, "tap_at_point", _to_logical((x, y), px, logical)

        if isinstance(action, TapElement):
            ref = _require_non_empty_str(action.ref)
            element = self._registry.element(revision, ref)
            if element is None:
                # Ref from another/unknown revision (R2-A09): fail closed.
                raise _no_effect(ErrorCode.STALE_REVISION)
            rect = element.rect
            if rect is None or rect.width <= 0 or rect.height <= 0:
                raise _no_effect(ErrorCode.INVALID_REQUEST)
            center = (rect.x + rect.width / 2.0, rect.y + rect.height / 2.0)
            return action.kind, "tap_at_point", _to_logical(center, px, logical)

        if isinstance(action, Drag):
            x1, y1 = _require_point(action.start_x, action.start_y, px)
            x2, y2 = _require_point(action.end_x, action.end_y, px)
            duration = _require_finite(action.duration)
            if not 0 < duration <= _MAX_DRAG_DURATION_S:
                raise _no_effect(ErrorCode.INVALID_REQUEST)
            return (
                action.kind,
                "drag",
                (
                    *_to_logical((x1, y1), px, logical),
                    *_to_logical((x2, y2), px, logical),
                    duration,
                ),
            )

        if isinstance(action, Swipe):
            if action.direction not in _SWIPE_DIRECTIONS:
                raise _no_effect(ErrorCode.INVALID_REQUEST)
            distance = _require_finite(action.distance)
            if not 0 < distance <= 1:
                raise _no_effect(ErrorCode.INVALID_REQUEST)
            start, end = _swipe_points(action.direction, distance, px)
            return (
                action.kind,
                "drag",
                (
                    *_to_logical(start, px, logical),
                    *_to_logical(end, px, logical),
                    _SWIPE_DURATION_S,
                ),
            )

        if isinstance(action, TypeText):
            return action.kind, "send_keys", (_require_non_empty_str(action.text),)

        if isinstance(action, Home):
            return action.kind, "press_home", ()

        if isinstance(action, LaunchApp):
            return action.kind, "launch_app", (_require_non_empty_str(action.bundle_id),)

        raise _no_effect(ErrorCode.UNSUPPORTED_ACTION)
