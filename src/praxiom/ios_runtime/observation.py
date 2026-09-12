"""Observation + revision layer for Native iOS Runtime v0 (R3-03).

Builds one immutable :class:`Observation` per capture from the downstream
primitive surface documented in ``transport.py`` — ``screenshot() -> bytes``,
``accessibility_source() -> str``, ``screen_size() -> (width, height)`` — and
owns the revision lifecycle of R2 contract sections 4.2/6/7:

- the revision token and every element ref are opaque random tokens; callers
  compare and pass them, nothing here parses them;
- exactly one revision is logically current. A new capture, ``invalidate()``,
  or the runtime's recover/close makes every earlier ref unresolvable
  (fail closed): a stale revision never becomes valid again;
- every public point/rect is in full-screen screenshot pixels. The pixel space
  of a revision is the captured PNG's own dimensions; upstream WDA
  logical-point geometry is scaled into that space here (reading the PNG
  header, stdlib only — no image dependency). Without a captured frame the
  pixel space degenerates to the WDA logical-point space (1:1);
- ``resolve(ref, revision)`` is the executor's preflight helper: a ref from
  another revision — or any ref not bound to the still-current revision —
  raises the no-effect ``STALE_REVISION`` error, so R2-A09-style batches are
  rejected with zero device calls;
- ``logical_screen(revision)`` exposes the WDA logical-point screen size pinned
  to the revision so the executor can convert screenshot pixels back to the
  device coordinate representation internally (contract 4.3).

Error mapping (all no-effect, R2 contract 5.1): malformed request sources ->
``INVALID_REQUEST`` (preflight); unusable capture plumbing/data ->
``OBSERVATION_FAILED`` (lifecycle); foreign/unknown/stale ref or revision ->
``STALE_REVISION`` (preflight). Capture primitives are read-only, so retrying
an observe can never duplicate a device effect (``retry_safe=True``).

When a requested source cannot be retrieved it is degraded to absent and the
returned ``sources`` tuple reports exactly what was captured; only a capture
with no usable source at all (or an unusable screen space) fails. This is the
"accessibility/source retrieval when available" rule of the task scope.

No OCR and no domain logic: the accessibility XML is projected structurally
(role, label/name/value, rect, enabled/visible) exactly as the source supplies
it. Errors carry structured fields only — never device identifiers, screen
text, or raw payloads.
"""

import struct
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

from praxiom.ios_runtime.models import (
    Element,
    FrameInfo,
    ObserveRequest,
    Observation,
    Rect,
    RuntimeOperationError,
    ScreenSize,
)

__all__ = ["ObservationEngine"]

_KNOWN_SOURCES = frozenset({"screenshot", "accessibility"})
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_size(png: bytes) -> tuple[int, int]:
    """Dimensions from the PNG IHDR header (the only frame metadata needed)."""
    if not png.startswith(_PNG_SIGNATURE) or len(png) < 24:
        raise ValueError("screenshot is not a png frame")
    return struct.unpack(">II", png[16:24])


def _logical_rect(attrs: dict[str, str]) -> tuple[int, int, int, int] | None:
    """WDA source geometry: separate ``x``/``y``/``width``/``height`` attributes,
    or a ``rect="x, y, width, height"`` attribute."""
    try:
        return int(attrs["x"]), int(attrs["y"]), int(attrs["width"]), int(attrs["height"])
    except (KeyError, TypeError, ValueError):
        pass
    parts = attrs.get("rect", "").strip(" {}").replace(",", " ").split()
    if len(parts) != 4:
        return None
    try:
        x, y, width, height = (int(part) for part in parts)
    except ValueError:
        return None
    return x, y, width, height


def _scaled_rect(
    logical: tuple[int, int, int, int], scale_x: float, scale_y: float
) -> Rect:
    x, y, width, height = logical
    return Rect(
        x=round(x * scale_x),
        y=round(y * scale_y),
        width=round(width * scale_x),
        height=round(height * scale_y),
    )


def _optional_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    return {"true": True, "false": False}.get(raw.strip().lower())


def _elements_from_source(
    source: str, scale_x: float, scale_y: float
) -> tuple[Element, ...]:
    """Project the accessibility XML structurally; document order is kept."""
    elements = []
    for node in ElementTree.fromstring(source).iter():
        attrs = node.attrib
        logical = _logical_rect(attrs)
        elements.append(
            Element(
                ref=uuid.uuid4().hex,
                role=node.tag.rsplit("}", 1)[-1],
                source="accessibility",
                label=attrs.get("label"),
                text=attrs.get("name"),
                value=attrs.get("value"),
                rect=(
                    _scaled_rect(logical, scale_x, scale_y)
                    if logical is not None
                    else None
                ),
                enabled=_optional_bool(attrs.get("enabled")),
                visible=_optional_bool(attrs.get("visible")),
            )
        )
    return tuple(elements)


class ObservationEngine:
    """Captures observations and owns the single logically current revision.

    ``transport`` is duck-typed to the documented ``IosTransport`` operation
    primitives; lifecycle (connect/recover/close) stays with the runtime.
    """

    def __init__(
        self,
        transport: Any,
        *,
        frame_sink: Callable[[bytes, Observation], None] | None = None,
    ) -> None:
        self._transport = transport
        self._frame_sink = frame_sink
        self._revision: str | None = None
        self._refs: dict[str, Rect | None] = {}
        self._logical: tuple[int, int] | None = None

    @property
    def current_revision(self) -> str | None:
        """The one logically current revision token, or None."""
        return self._revision

    async def capture(self, request: ObserveRequest | None = None) -> Observation:
        """Capture one observation and install it as the current revision.

        Any prior revision is dropped: its refs become unresolvable and its
        token can never validate again.
        """
        sources = (request or ObserveRequest()).sources
        if not sources or set(sources) - _KNOWN_SOURCES:
            raise RuntimeOperationError(
                "INVALID_REQUEST", "preflight", "NONE", retry_safe=True
            )
        try:
            png: bytes | None = None
            if "screenshot" in sources:
                try:
                    png = await self._transport.screenshot()
                except Exception:
                    png = None  # degraded; the returned sources tuple reports it
            logical_w, logical_h = await self._transport.screen_size()
            if logical_w <= 0 or logical_h <= 0:
                raise ValueError("transport reported a non-positive screen size")
            xml: str | None = None
            if "accessibility" in sources:
                try:
                    xml = await self._transport.accessibility_source()
                except Exception:
                    xml = None  # degraded; the returned sources tuple reports it
        except Exception as exc:
            raise RuntimeOperationError(
                "OBSERVATION_FAILED", "lifecycle", "NONE", retry_safe=True
            ) from exc
        if png is None and xml is None:
            raise RuntimeOperationError(
                "OBSERVATION_FAILED", "lifecycle", "NONE", retry_safe=True
            )
        try:
            pixel_w, pixel_h = (
                _png_size(png) if png is not None else (logical_w, logical_h)
            )
            scale_x = pixel_w / logical_w
            scale_y = pixel_h / logical_h
            elements = (
                _elements_from_source(xml, scale_x, scale_y) if xml is not None else ()
            )
        except Exception as exc:
            raise RuntimeOperationError(
                "OBSERVATION_FAILED", "lifecycle", "NONE", retry_safe=True
            ) from exc

        revision = uuid.uuid4().hex
        self._revision = revision
        self._refs = {element.ref: element.rect for element in elements}
        self._logical = (logical_w, logical_h)
        captured: list[str] = []
        if png is not None:
            captured.append("screenshot")
        if xml is not None:
            captured.append("accessibility")
        observation = Observation(
            revision=revision,
            captured_at=datetime.now(UTC),
            screen=ScreenSize(width=pixel_w, height=pixel_h),
            frame=FrameInfo(
                width=pixel_w,
                height=pixel_h,
                format="png" if png is not None else "none",
            ),
            sources=tuple(captured),
            elements=elements,
        )
        if png is not None and self._frame_sink is not None:
            # Monitor/diagnostic projections are observational only. Their
            # failure must never change observe() success or revision state.
            try:
                self._frame_sink(png, observation)
            except Exception:
                pass
        return observation

    def invalidate(self) -> None:
        """Invalidate the current revision; every prior ref becomes unusable."""
        self._revision = None
        self._refs = {}
        self._logical = None

    def resolve(self, ref: str, revision: str) -> Rect | None:
        """Resolve a revision-bound element ref (executor preflight helper).

        Raises the no-effect ``STALE_REVISION`` error when the ref was not
        created by the still-current revision: foreign-revision (R2-A09),
        invalidated, unknown, and superseded refs all fail closed identically.
        This is synchronous and device-free, so a rejection costs zero device
        calls.
        """
        if revision != self._revision or ref not in self._refs:
            raise RuntimeOperationError(
                "STALE_REVISION", "preflight", "NONE", retry_safe=True
            )
        return self._refs[ref]

    def logical_screen(self, revision: str) -> tuple[int, int]:
        """WDA logical-point screen size pinned to the still-current revision.

        The executor uses it with ``Observation.screen`` to convert accepted
        screenshot-pixel coordinates into the device representation.
        """
        if revision != self._revision or self._logical is None:
            raise RuntimeOperationError(
                "STALE_REVISION", "preflight", "NONE", retry_safe=True
            )
        return self._logical
