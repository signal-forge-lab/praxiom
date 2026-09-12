import importlib.util
import base64
import io
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phasec_mergeboss_board_probe.py"
SPEC = importlib.util.spec_from_file_location("phasec_mergeboss_board_probe", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _png(fill):
    image = Image.new("RGB", MODULE.REFERENCE_SCREEN, fill)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_reference_colored_candidate_revalidates_geometry():
    metrics = MODULE._board_visual_metrics(_png(MODULE.REFERENCE_EMPTY_RGB))
    assert metrics["screen_size_match"] is True
    assert metrics["candidate_cells"] == MODULE.GRID_COLS * MODULE.GRID_ROWS
    assert metrics["reference_geometry_revalidated"] is True


def test_unrelated_screen_fails_board_candidate():
    metrics = MODULE._board_visual_metrics(_png((0, 0, 0)))
    assert metrics["candidate_cells"] == 0
    assert metrics["reference_geometry_revalidated"] is False


def test_entry_cta_shape_requires_one_large_horizontal_visible_control():
    screen = SimpleNamespace(width=1206, height=2622)
    candidate = SimpleNamespace(
        ref="cta",
        role="XCUIElementTypeOther",
        enabled=True,
        visible=True,
        rect=SimpleNamespace(x=200, y=1600, width=806, height=160),
    )
    tiny = SimpleNamespace(
        ref="tiny",
        role="XCUIElementTypeButton",
        enabled=True,
        visible=True,
        rect=SimpleNamespace(x=10, y=10, width=50, height=50),
    )
    metrics = MODULE._entry_cta_shape_metrics(
        SimpleNamespace(screen=screen, elements=(candidate, tiny))
    )
    assert metrics["candidate_count"] == 1
    assert metrics["single_candidate"] is True
    assert metrics["roles"] == ["XCUIElementTypeOther"]


def test_entry_cta_shape_excludes_purchase_semantics():
    screen = SimpleNamespace(width=1206, height=2622)
    safe = SimpleNamespace(
        ref="safe",
        role="XCUIElementTypeOther",
        enabled=True,
        visible=True,
        label="Play",
        text=None,
        value=None,
        rect=SimpleNamespace(x=200, y=1600, width=806, height=160),
    )
    purchase = SimpleNamespace(
        ref="purchase",
        role="XCUIElementTypeButton",
        enabled=True,
        visible=True,
        label="Buy now",
        text=None,
        value=None,
        rect=SimpleNamespace(x=200, y=1900, width=806, height=160),
    )
    observation = SimpleNamespace(screen=screen, elements=(safe, purchase))
    candidates = MODULE._entry_cta_candidates(observation)
    metrics = MODULE._entry_cta_shape_metrics(observation)
    assert tuple(item.ref for item in candidates) == ("safe",)
    assert metrics["candidate_count"] == 1
    assert metrics["single_candidate"] is True


def test_visual_cta_detector_finds_one_large_saturated_button():
    image = Image.new("RGB", (1206, 2622), (230, 230, 230))
    for x in range(300, 906):
        for y in range(1700, 1900):
            image.putpixel((x, y), (230, 130, 20))
    output = io.BytesIO()
    image.save(output, format="PNG")
    metrics = MODULE._visual_cta_metrics(output.getvalue())
    assert metrics["candidate_count"] == 1
    assert metrics["single_candidate"] is True
    assert metrics["candidates"][0]["vertical_band"] == "middle"
    assert metrics["candidates"][0]["mean_saturation"] > 0.5


def test_visual_cta_detector_rejects_thin_saturated_bar():
    image = Image.new("RGB", (1206, 2622), (230, 230, 230))
    for x in range(250, 956):
        for y in range(1800, 1910):
            image.putpixel((x, y), (180, 90, 20))
    output = io.BytesIO()
    image.save(output, format="PNG")
    metrics = MODULE._visual_cta_metrics(output.getvalue())
    assert metrics["candidate_count"] == 0
    assert metrics["single_candidate"] is False


def test_visual_cta_detector_rejects_unsaturated_background_band():
    image = Image.new("RGB", (1206, 2622), (230, 230, 230))
    for x in range(150, 1050):
        for y in range(1700, 1870):
            image.putpixel((x, y), (170, 170, 170))
    output = io.BytesIO()
    image.save(output, format="PNG")
    metrics = MODULE._visual_cta_metrics(output.getvalue())
    assert metrics["candidate_count"] == 0
    assert metrics["single_candidate"] is False


def test_visual_cta_center_is_not_exposed_by_metrics():
    image = Image.new("RGB", (1206, 2622), (230, 230, 230))
    for x in range(300, 906):
        for y in range(1700, 1900):
            image.putpixel((x, y), (230, 130, 20))
    output = io.BytesIO()
    image.save(output, format="PNG")
    metrics = MODULE._visual_cta_metrics(output.getvalue())
    assert metrics["single_candidate"] is True
    assert "x" not in metrics["candidates"][0]
    assert "y" not in metrics["candidates"][0]


def test_play_template_similarity_is_exact_for_identical_descriptor():
    descriptor = base64.b64decode(MODULE.PLAY_TEMPLATE_RGB4_B64)
    assert MODULE._rgb4_similarity(descriptor, descriptor) == 1.0
    assert MODULE._rgb4_similarity(descriptor, bytes(len(descriptor))) < 1.0


def test_play_visual_binding_fails_closed_on_other_screen_size():
    image = Image.new("RGB", (800, 1200), (255, 255, 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    metrics = MODULE._play_visual_binding_metrics(output.getvalue())
    assert metrics["screen_size_match"] is False
    assert metrics["matched"] is False


def test_play_visual_binding_fails_closed_on_wrong_current_screen_content():
    metrics = MODULE._play_visual_binding_metrics(_png((0, 0, 0)))
    assert metrics["screen_size_match"] is True
    assert metrics["matched"] is False
    assert metrics["similarity"] < metrics["threshold"]
