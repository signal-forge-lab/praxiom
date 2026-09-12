import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from praxiom.ios_runtime.models import TapElement, TapPoint


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phasec_mergeboss_route_probe.py"
SPEC = importlib.util.spec_from_file_location("phasec_mergeboss_route_probe", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _element(*, role, rect, ref):
    return SimpleNamespace(
        label="My Account",
        text=None,
        value=None,
        role=role,
        rect=rect,
        ref=ref,
        enabled=True,
        visible=True,
    )


def test_selects_one_button_from_one_nested_semantic_cluster():
    button = _element(
        role="XCUIElementTypeButton",
        rect=SimpleNamespace(x=10, y=10, width=100, height=80),
        ref="button",
    )
    image = _element(
        role="XCUIElementTypeImage",
        rect=SimpleNamespace(x=20, y=20, width=60, height=40),
        ref="image",
    )
    selected = MODULE._select_single_cluster_button(
        SimpleNamespace(elements=(button, image)),
        MODULE.ACCOUNT_KEYWORDS,
        contains=True,
    )
    assert selected is button


def test_refuses_multiple_visual_clusters():
    first = _element(
        role="XCUIElementTypeButton",
        rect=SimpleNamespace(x=10, y=10, width=100, height=80),
        ref="one",
    )
    second = _element(
        role="XCUIElementTypeImage",
        rect=SimpleNamespace(x=500, y=500, width=50, height=50),
        ref="two",
    )
    assert MODULE._select_single_cluster_button(
        SimpleNamespace(elements=(first, second)),
        MODULE.ACCOUNT_KEYWORDS,
        contains=True,
    ) is None


def test_refuses_two_buttons_even_when_nested():
    first = _element(
        role="XCUIElementTypeButton",
        rect=SimpleNamespace(x=10, y=10, width=100, height=80),
        ref="one",
    )
    second = _element(
        role="XCUIElementTypeButton",
        rect=SimpleNamespace(x=20, y=20, width=60, height=40),
        ref="two",
    )
    assert MODULE._select_single_cluster_button(
        SimpleNamespace(elements=(first, second)),
        MODULE.ACCOUNT_KEYWORDS,
        contains=True,
    ) is None


def test_phasec_route_action_mapper_adds_only_revision_bound_tap_element():
    action = MODULE._action_from_payload_phasec_route(
        {"op": "tap_element", "ref": "ref-1"}
    )
    assert isinstance(action, TapElement)
    assert action.ref == "ref-1"
    with pytest.raises(ValueError, match="tap_element requires ref"):
        MODULE._action_from_payload_phasec_route({"op": "tap_element"})


def test_phasec_route_action_mapper_allows_revision_bound_visual_tap_point():
    action = MODULE._action_from_payload_phasec_route(
        {"op": "tap_point", "x": 400, "y": 1800}
    )
    assert isinstance(action, TapPoint)
    assert action.x == 400
    assert action.y == 1800
    with pytest.raises(ValueError, match="tap_point requires integer x/y"):
        MODULE._action_from_payload_phasec_route(
            {"op": "tap_point", "x": 1.5, "y": 1800}
        )


def test_unique_exact_bindable_accepts_other_role_but_refuses_ambiguity():
    only = SimpleNamespace(
        label="Merge Boss",
        text=None,
        value=None,
        role="XCUIElementTypeOther",
        rect=SimpleNamespace(x=10, y=10, width=100, height=50),
        ref="entry",
        enabled=True,
        visible=True,
    )
    observation = SimpleNamespace(elements=(only,))
    assert MODULE._select_unique_exact_bindable(
        observation,
        MODULE.MERGE_BOSS_LABELS,
    ) is only
    duplicate = SimpleNamespace(**vars(only))
    duplicate.ref = "entry-2"
    assert MODULE._select_unique_exact_bindable(
        SimpleNamespace(elements=(only, duplicate)),
        MODULE.MERGE_BOSS_LABELS,
    ) is None
