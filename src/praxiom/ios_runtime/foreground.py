"""Generic read-only foreground-application evidence helpers.

The helpers intentionally retain only bounded structural evidence.  Callers
may provide an expected application identity in-process, but the returned
objects never contain that identity, raw accessibility XML, user-visible text,
bundle identifiers, coordinates, or device identifiers.

This module has no mutation authority and does not author Runtime revisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

__all__ = [
    "ActiveApplicationEvidence",
    "ForegroundEvidence",
    "inspect_active_application_info",
    "inspect_foreground_source",
    "observation_matches_foreground",
]


@dataclass(frozen=True, kw_only=True)
class ForegroundEvidence:
    application_node_count: int
    expected_match: bool
    matched_attribute_keys: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ActiveApplicationEvidence:
    expected_match: bool
    bundle_id_present: bool
    pid_present: bool


def _expected_identity(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("expected-application-identity-must-be-string")
    if not value or len(value) > 512:
        raise ValueError("expected-application-identity-invalid")
    return value


def inspect_foreground_source(xml: str, expected_identity: str) -> ForegroundEvidence:
    """Inspect raw accessibility XML without returning any raw attribute value."""
    expected = _expected_identity(expected_identity)
    if not isinstance(xml, str) or not xml:
        return ForegroundEvidence(application_node_count=0, expected_match=False)
    root = ElementTree.fromstring(xml)
    count = 0
    matched_keys: set[str] = set()
    for node in root.iter():
        role = node.tag.rsplit("}", 1)[-1].lower()
        if "application" not in role:
            continue
        count += 1
        for key in ("name", "label"):
            value = node.attrib.get(key)
            if isinstance(value, str) and value == expected:
                matched_keys.add(key)
    return ForegroundEvidence(
        application_node_count=count,
        expected_match=bool(matched_keys),
        matched_attribute_keys=tuple(sorted(matched_keys)),
    )


def inspect_active_application_info(
    info: Any, expected_bundle_id: str
) -> ActiveApplicationEvidence:
    """Project active-app metadata into identity-free foreground evidence."""
    expected = _expected_identity(expected_bundle_id)
    if not isinstance(info, dict):
        return ActiveApplicationEvidence(
            expected_match=False,
            bundle_id_present=False,
            pid_present=False,
        )
    bundle_id = info.get("bundleId")
    pid = info.get("pid")
    return ActiveApplicationEvidence(
        expected_match=isinstance(bundle_id, str) and bundle_id == expected,
        bundle_id_present=isinstance(bundle_id, str) and bool(bundle_id),
        pid_present=isinstance(pid, int) and not isinstance(pid, bool) and pid > 0,
    )


def observation_matches_foreground(observation: Any, expected_identity: str) -> bool:
    """Check a normal Runtime observation for the same application identity."""
    expected = _expected_identity(expected_identity)
    for element in tuple(getattr(observation, "elements", ()) or ()):
        role = str(getattr(element, "role", "") or "").lower()
        if "application" not in role:
            continue
        if (
            getattr(element, "label", None) == expected
            or getattr(element, "text", None) == expected
        ):
            return True
    return False
