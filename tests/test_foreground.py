from __future__ import annotations

from types import SimpleNamespace

import pytest

from praxiom.ios_runtime.foreground import (
    ActiveApplicationEvidence,
    ForegroundEvidence,
    inspect_active_application_info,
    inspect_foreground_source,
    observation_matches_foreground,
)


def test_source_projection_is_privacy_bounded():
    xml = """<Root><XCUIElementTypeApplication name='Expected' label='Expected'>
    <XCUIElementTypeButton label='private-value'/></XCUIElementTypeApplication></Root>"""
    evidence = inspect_foreground_source(xml, "Expected")
    assert evidence == ForegroundEvidence(
        application_node_count=1,
        expected_match=True,
        matched_attribute_keys=("label", "name"),
    )
    assert "Expected" not in repr(evidence)
    assert "private-value" not in repr(evidence)


def test_source_projection_fails_closed_for_other_application():
    evidence = inspect_foreground_source(
        "<Root><XCUIElementTypeApplication name='Other'/></Root>",
        "Expected",
    )
    assert evidence.application_node_count == 1
    assert evidence.expected_match is False
    assert evidence.matched_attribute_keys == ()


def test_observation_match_is_application_scoped():
    observation = SimpleNamespace(
        elements=(
            SimpleNamespace(role="XCUIElementTypeButton", label="Expected", text=None),
            SimpleNamespace(role="XCUIElementTypeApplication", label=None, text="Expected"),
        )
    )
    assert observation_matches_foreground(observation, "Expected") is True
    assert observation_matches_foreground(observation, "Other") is False


def test_expected_identity_is_bounded_and_required():
    with pytest.raises(ValueError, match="expected-application-identity-invalid"):
        inspect_foreground_source("<Root/>", "")
    with pytest.raises(TypeError, match="expected-application-identity-must-be-string"):
        inspect_foreground_source("<Root/>", 1)  # type: ignore[arg-type]


def test_active_application_info_projects_only_bounded_identity_evidence():
    evidence = inspect_active_application_info(
        {"bundleId": "private.bundle", "name": "Private App", "pid": 1234},
        "private.bundle",
    )
    assert evidence == ActiveApplicationEvidence(
        expected_match=True,
        bundle_id_present=True,
        pid_present=True,
    )
    assert "private.bundle" not in repr(evidence)
    assert "Private App" not in repr(evidence)


def test_active_application_info_fails_closed_for_wrong_or_malformed_identity():
    wrong = inspect_active_application_info(
        {"bundleId": "other.bundle", "pid": 10}, "expected.bundle"
    )
    assert wrong.expected_match is False
    malformed = inspect_active_application_info(None, "expected.bundle")
    assert malformed == ActiveApplicationEvidence(
        expected_match=False,
        bundle_id_present=False,
        pid_present=False,
    )
