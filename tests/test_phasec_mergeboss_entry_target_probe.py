from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phasec_mergeboss_entry_target_probe.py"
SPEC = importlib.util.spec_from_file_location("phasec_mergeboss_entry_target_probe", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _element(*, label=None, text=None, value=None, role="XCUIElementTypeButton", ref="r1", rect=True, enabled=True, visible=True):
    return SimpleNamespace(
        label=label,
        text=text,
        value=value,
        role=role,
        ref=ref,
        rect=(object() if rect else None),
        enabled=enabled,
        visible=visible,
    )


def test_merge_boss_target_requires_exact_predeclared_semantic_match():
    observation = SimpleNamespace(
        elements=(
            _element(label="マージボス"),
            _element(label="マージボス セール"),
        )
    )
    result = MODULE._project_target(
        observation,
        target_kind="merge-boss-entry",
        labels=MODULE.MERGE_BOSS_LABELS,
    )
    assert result.count == 1
    assert result.bindable_count == 1
    assert result.unique_bindable is True


def test_keyword_hint_probe_can_find_bounded_partial_match_without_changing_exact_match():
    observation = SimpleNamespace(
        elements=(
            _element(label="Play Merge Boss now"),
            _element(label="Unrelated"),
        )
    )
    exact = MODULE._project_target(
        observation,
        target_kind="merge-boss-entry",
        labels=MODULE.MERGE_BOSS_LABELS,
    )
    hints = MODULE._project_target(
        observation,
        target_kind="merge-boss-keyword-hints",
        labels=MODULE.MERGE_BOSS_KEYWORDS,
        contains=True,
    )
    assert exact.count == 0
    assert hints.count == 1
    assert hints.bindable_count == 1
    assert hints.matched_fields == ("label",)


def test_nested_button_and_image_are_one_semantic_cluster():
    button = _element(label="My Account")
    image = _element(label="Account")
    button.role = "XCUIElementTypeButton"
    image.role = "XCUIElementTypeImage"
    button.rect = SimpleNamespace(x=10, y=20, width=100, height=80)
    image.rect = SimpleNamespace(x=20, y=30, width=60, height=50)
    observation = SimpleNamespace(elements=(button, image))
    result = MODULE._project_target(
        observation,
        target_kind="account-keyword-hints",
        labels=MODULE.ACCOUNT_KEYWORDS,
        contains=True,
    )
    assert result.bindable_count == 2
    assert result.semantic_cluster_count == 1
    assert result.single_semantic_cluster is True
    assert result.bindable_button_count == 1


def test_target_is_not_bindable_when_hidden_disabled_or_geometry_missing():
    observation = SimpleNamespace(
        elements=(
            _element(label="Merge Boss", visible=False),
            _element(label="Merge Boss", enabled=False),
            _element(label="Merge Boss", rect=False),
        )
    )
    result = MODULE._project_target(
        observation,
        target_kind="merge-boss-entry",
        labels=MODULE.MERGE_BOSS_LABELS,
    )
    assert result.count == 3
    assert result.bindable_count == 0
    assert result.unique_bindable is False


def test_account_anchor_accepts_known_localized_exact_label():
    observation = SimpleNamespace(elements=(_element(text="アカウント"),))
    result = MODULE._project_target(
        observation,
        target_kind="account-anchor",
        labels=MODULE.ACCOUNT_LABELS,
    )
    assert result.unique_bindable is True
    assert result.matched_fields == ("text",)
