"""R3-03 deterministic observation/revision tests (R2 contract 4.2/6/7).

The fake transport is duck-typed to the downstream primitive surface
documented in ``transport.py`` (``screenshot`` / ``accessibility_source`` /
``screen_size`` — read-only primitives only, so no mutation can even be
attempted here). Covers R2-A02 semantics (opaque revision, positive screen,
revision-bound refs), one logical revision shared by screenshot and
accessibility, invalidation, and the R2-A09-style cross-revision ref
rejection helper. No device, usbmux, tunnel, or WDA is involved.
"""

import asyncio
import struct

import pytest

from praxiom.ios_runtime.models import ObserveRequest
from praxiom.ios_runtime.observation import ObservationEngine


def run(coro):
    return asyncio.run(coro)


def png_bytes(width, height):
    """Minimal PNG header (signature + IHDR dims) — all the engine reads."""
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
    )


LOGICAL = (390, 844)
PIXELS = (780, 1688)  # exactly 2x the logical points

# WDA-shaped source using the separate x/y/width/height attribute form.
DEFAULT_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<XCUIElementTypeApplication type="XCUIElementTypeApplication" name="App"'
    ' label="App" enabled="true" visible="true" x="0" y="0" width="390" height="844">\n'
    '  <XCUIElementTypeWindow type="XCUIElementTypeWindow" x="0" y="0" width="390" height="844">\n'
    '    <XCUIElementTypeButton type="XCUIElementTypeButton" name="Buy" label="Buy"'
    ' value="Buy now" enabled="true" visible="true" x="100" y="200" width="50" height="24"/>\n'
    '    <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="Title"'
    ' label="Title" enabled="true" visible="false" x="10" y="20" width="30" height="40"/>\n'
    '  </XCUIElementTypeWindow>\n'
    "</XCUIElementTypeApplication>"
)

# Same geometry expressed with the rect-attribute form, scaled 2x expectations.
RECT_ATTR_XML = (
    '<XCUIElementTypeApplication x="0" y="0" width="390" height="844">'
    '<XCUIElementTypeSlider rect="{12, 34, 56, 78}"/>'
    "</XCUIElementTypeApplication>"
)


class FakeTransport:
    """Duck-typed to the documented read-only observation primitives."""

    def __init__(self, logical=LOGICAL, pixels=PIXELS, xml=DEFAULT_XML, fail=()):
        self.logical = logical
        self.png = png_bytes(*pixels)
        self.xml = xml
        self.fail = set(fail)
        self.calls = []

    async def screenshot(self):
        self.calls.append("screenshot")
        if "screenshot" in self.fail:
            raise ConnectionError("in-flight screenshot request timed out")
        return self.png

    async def screen_size(self):
        self.calls.append("screen_size")
        if "screen_size" in self.fail:
            raise TimeoutError("window size request timed out")
        return self.logical

    async def accessibility_source(self):
        self.calls.append("accessibility_source")
        if "accessibility" in self.fail:
            raise RuntimeError("source retrieval failed")
        return self.xml


def make_engine(**fake_kwargs):
    transport = FakeTransport(**fake_kwargs)
    return ObservationEngine(transport), transport


def capture(request=None, **fake_kwargs):
    engine, transport = make_engine(**fake_kwargs)
    observation = run(engine.capture(request))
    return engine, transport, observation


# --- R2-A02: opaque revision, positive screen, revision-bound refs ------------


def test_a02_observation_creates_opaque_revision_and_positive_screen():
    engine, _, obs = capture()
    assert isinstance(obs.revision, str) and obs.revision
    assert obs.revision == engine.current_revision
    assert obs.screen.width == 780 and obs.screen.height == 1688
    assert obs.screen.width > 0 and obs.screen.height > 0
    assert obs.captured_at.tzinfo is not None


def test_a02_ref_resolution_returns_element_rect_from_same_engine():
    engine, _, obs = capture()
    for element in obs.elements:
        assert engine.resolve(element.ref, obs.revision) == element.rect
    with pytest.raises(Exception) as excinfo:
        engine.resolve("ref-from-elsewhere", obs.revision)
    assert excinfo.value.code == "STALE_REVISION"


def test_refs_are_unique_across_observations():
    _, _, obs1 = capture()
    _, _, obs2 = capture()
    refs1 = {element.ref for element in obs1.elements}
    refs2 = {element.ref for element in obs2.elements}
    assert obs1.revision != obs2.revision
    assert not refs1 & refs2  # a stale ref string can never match a live one


# --- one logical revision shared by screenshot + accessibility -----------------


def test_screenshot_and_accessibility_share_one_logical_revision():
    engine, transport, obs = capture()
    assert obs.sources == ("screenshot", "accessibility")
    assert engine.current_revision == obs.revision
    # One capture = one of each read primitive, single shared revision.
    assert transport.calls == ["screenshot", "screen_size", "accessibility_source"]
    assert obs.frame.width == 780 and obs.frame.height == 1688
    assert obs.frame.format == "png"


# --- coordinate space: full-screen screenshot pixels ---------------------------


def test_accessibility_rects_are_scaled_into_screenshot_pixels():
    _, _, obs = capture()
    button = next(e for e in obs.elements if e.role == "XCUIElementTypeButton")
    assert button.rect is not None
    # Logical (100, 200, 50, 24) at exactly 2x screenshot scale.
    assert (button.rect.x, button.rect.y, button.rect.width, button.rect.height) == (
        200,
        400,
        100,
        48,
    )


def test_non_integer_scale_rounds_to_pixels():
    engine, _, obs = capture(pixels=(585, 1266))  # 1.5x
    button = next(e for e in obs.elements if e.role == "XCUIElementTypeButton")
    assert (button.rect.x, button.rect.y, button.rect.width, button.rect.height) == (
        150,
        300,
        75,
        36,
    )
    assert engine.logical_screen(obs.revision) == LOGICAL


def test_rect_attribute_shape_is_supported():
    _, _, obs = capture(xml=RECT_ATTR_XML)
    slider = next(e for e in obs.elements if e.role == "XCUIElementTypeSlider")
    assert slider.rect is not None
    # Logical (12, 34, 56, 78) at 2x.
    assert (slider.rect.x, slider.rect.y, slider.rect.width, slider.rect.height) == (
        24,
        68,
        112,
        156,
    )


def test_element_attributes_are_projected_from_the_source():
    _, _, obs = capture()
    button = next(e for e in obs.elements if e.role == "XCUIElementTypeButton")
    text = next(e for e in obs.elements if e.role == "XCUIElementTypeStaticText")
    assert button.label == "Buy" and button.text == "Buy" and button.value == "Buy now"
    assert button.enabled is True and button.visible is True
    assert button.source == "accessibility"
    assert text.visible is False
    window = next(e for e in obs.elements if e.role == "XCUIElementTypeWindow")
    assert window.label is None and window.value is None
    assert window.enabled is None and window.visible is None


# --- source-filtered and degraded captures -------------------------------------


def test_accessibility_only_request_uses_logical_pixel_space():
    engine, transport, obs = capture(
        request=ObserveRequest(sources=frozenset({"accessibility"}))
    )
    assert transport.calls == ["screen_size", "accessibility_source"]
    assert obs.sources == ("accessibility",)
    assert (obs.screen.width, obs.screen.height) == LOGICAL  # 1:1 pixel space
    assert obs.frame.format == "none" and obs.frame.width == 390
    button = next(e for e in obs.elements if e.role == "XCUIElementTypeButton")
    assert (button.rect.x, button.rect.y, button.rect.width, button.rect.height) == (
        100,
        200,
        50,
        24,
    )
    assert engine.resolve(button.ref, obs.revision) == button.rect


def test_screenshot_only_request_has_no_elements():
    _, transport, obs = capture(request=ObserveRequest(sources=frozenset({"screenshot"})))
    assert transport.calls == ["screenshot", "screen_size"]
    assert obs.sources == ("screenshot",)
    assert obs.elements == ()
    assert (obs.screen.width, obs.screen.height) == PIXELS


def test_accessibility_failure_degrades_to_screenshot_only():
    engine, _, obs = capture(fail=("accessibility",))
    assert obs.sources == ("screenshot",)
    assert obs.elements == ()
    assert engine.current_revision == obs.revision  # still a valid revision


def test_capture_with_no_usable_source_fails_as_observation_failed():
    engine, transport = make_engine(fail=("screenshot", "accessibility"))
    with pytest.raises(Exception) as excinfo:
        run(engine.capture())
    err = excinfo.value
    assert err.code == "OBSERVATION_FAILED"
    assert err.phase == "lifecycle"
    assert err.effect == "NONE"
    assert err.retry_safe is True
    assert "Buy" not in str(err)  # structured message only, never source content
    assert len(transport.calls) == 3  # every read was attempted, nothing more


def test_screen_size_failure_fails_capture():
    engine, _ = make_engine(fail=("screen_size",))
    with pytest.raises(Exception) as excinfo:
        run(engine.capture())
    assert excinfo.value.code == "OBSERVATION_FAILED"
    assert excinfo.value.phase == "lifecycle"


def test_malformed_sources_rejected_with_zero_device_calls():
    engine, transport = make_engine()
    for request in (
        ObserveRequest(sources=frozenset({"ocr"})),
        ObserveRequest(sources=frozenset()),
    ):
        with pytest.raises(Exception) as excinfo:
            run(engine.capture(request))
        assert excinfo.value.code == "INVALID_REQUEST"
        assert excinfo.value.phase == "preflight"
        assert excinfo.value.effect == "NONE"
        assert excinfo.value.retry_safe is True
    assert transport.calls == []  # rejected before any device I/O


# --- invalidation + R2-A09 cross-revision rejection -----------------------------


def test_invalidate_makes_all_prior_refs_unusable():
    engine, _, obs = capture()
    refs = [element.ref for element in obs.elements]
    engine.invalidate()
    assert engine.current_revision is None
    for ref in refs:
        with pytest.raises(Exception) as excinfo:
            engine.resolve(ref, obs.revision)
        assert excinfo.value.code == "STALE_REVISION"
        assert excinfo.value.phase == "preflight"
        assert excinfo.value.effect == "NONE"
    with pytest.raises(Exception):
        engine.logical_screen(obs.revision)


def test_a09_cross_revision_ref_rejected_before_device_calls():
    engine, transport, obs1 = capture()
    stale_ref = next(
        e for e in obs1.elements if e.role == "XCUIElementTypeButton"
    ).ref
    obs2 = run(engine.capture())
    calls_after_second_capture = list(transport.calls)

    # The ref from rev-1 used against rev-2: rejected preflight, no device call.
    with pytest.raises(Exception) as excinfo:
        engine.resolve(stale_ref, obs2.revision)
    err = excinfo.value
    assert err.code == "STALE_REVISION"
    assert err.phase == "preflight"
    assert err.effect == "NONE"
    assert err.retry_safe is True
    # The old revision itself is superseded: fail closed both ways.
    with pytest.raises(Exception):
        engine.resolve(stale_ref, obs1.revision)
    assert transport.calls == calls_after_second_capture  # resolve is device-free


def test_superseded_revision_refs_fail_closed_after_new_capture():
    engine, _, obs1 = capture()
    ref = obs1.elements[0].ref
    run(engine.capture())  # a fresh observation supersedes rev-1
    with pytest.raises(Exception) as excinfo:
        engine.resolve(ref, obs1.revision)
    assert excinfo.value.code == "STALE_REVISION"
    assert engine.current_revision != obs1.revision


def test_logical_screen_is_pinned_to_current_revision():
    engine, _, obs = capture()
    assert engine.logical_screen(obs.revision) == LOGICAL
    with pytest.raises(Exception) as excinfo:
        engine.logical_screen("some-other-revision")
    assert excinfo.value.code == "STALE_REVISION"
