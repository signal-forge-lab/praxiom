"""Non-device contract tests for the R6/R7 real-device gate runner."""
from __future__ import annotations

import json
import subprocess
import sys
import asyncio
from pathlib import Path

from datetime import UTC, datetime

from praxiom.ios_runtime.models import Element, FrameInfo, Home, LaunchApp, Observation, ScreenSize
from scripts.r6_r7_device_matrix import (
    CELLS,
    EVIDENCE_NAME,
    _action_from_payload,
    _privacy_safe_home_anchor,
    _privacy_safe_source_head,
    _source_state,
    preprobe,
)
import scripts.r6_r7_device_matrix as device_matrix
from scripts.r4_device_matrix import scan_for_identifiers

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "r6_r7_device_matrix.py"


def test_device_runner_has_exact_ten_required_cells():
    assert len(CELLS) == 10
    assert len(set(CELLS)) == 10


def test_post_repair_device_runner_preserves_historical_evidence_filename():
    assert EVIDENCE_NAME == "20260907_r6-r7-safe-agent-foundation-device-matrix-post-repair.json"
    assert EVIDENCE_NAME != "20260905_r6-r7-safe-agent-foundation-device-matrix.json"


def test_preprobe_short_circuits_runner_lookup_when_device_count_is_not_one(monkeypatch):
    monkeypatch.setattr(
        device_matrix,
        "_source_state",
        lambda: ("a" * 40, True),
    )

    async def no_devices():
        return 0

    async def runner_lookup_must_not_run():
        raise AssertionError("runner lookup must not run without exactly one device")

    monkeypatch.setattr(device_matrix, "_device_count", no_devices)
    monkeypatch.setattr(device_matrix, "_find_runner_bundle_id", runner_lookup_must_not_run)

    assert asyncio.run(preprobe()) == {
        "device_count": 0,
        "runner_present": False,
        "source_head": "a" * 40,
        "source_tree_clean": True,
    }


def test_source_state_binds_head_and_cleanliness(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        stdout = "b" * 40 + "\n" if argv[1:3] == ["rev-parse", "HEAD"] else ""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(device_matrix.subprocess, "run", fake_run)

    assert _source_state() == ("b" * 40, True)
    assert [call[0] for call in calls] == [
        ["git", "rev-parse", "HEAD"],
        ["git", "status", "--porcelain"],
    ]


def test_physical_evidence_source_head_is_exact_and_privacy_safe():
    head = "c" * 40
    parts = _privacy_safe_source_head(head)

    assert "".join(parts) == head
    assert [len(part) for part in parts] == [20, 20]
    assert scan_for_identifiers(json.dumps({"source_head_parts": parts})) == []


def test_device_runner_action_conversion_stays_at_integration_edge():
    assert isinstance(_action_from_payload({"op": "home"}), Home)
    launch = _action_from_payload(
        {"op": "launch_app", "bundle_id": "com.apple.Preferences"}
    )
    assert isinstance(launch, LaunchApp)
    assert launch.bundle_id == "com.apple.Preferences"


def test_device_runner_refuses_mutation_without_confirmation():
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "matrix"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "requires --confirm-device-run" in proc.stdout


def test_device_runner_home_anchor_requires_observed_structural_icon_without_text_leak():
    base = dict(
        revision="rev-home",
        captured_at=datetime.now(UTC),
        screen=ScreenSize(width=1179, height=2556),
        frame=FrameInfo(width=1179, height=2556, format="png"),
        sources=("accessibility",),
    )
    home = Observation(
        **base,
        elements=(Element(ref="r1", role="XCUIElementTypeIcon",
                          source="accessibility", label="SENSITIVE APP NAME"),),
    )
    ok, detail = _privacy_safe_home_anchor(home)
    assert ok is True
    assert detail == "home-structural-icons=1"
    assert "SENSITIVE" not in detail

    settings_like = Observation(
        **base,
        elements=(Element(ref="r2", role="XCUIElementTypeButton",
                          source="accessibility", label="Settings"),),
    )
    ok2, detail2 = _privacy_safe_home_anchor(settings_like)
    assert ok2 is False and detail2 == "home-structural-icons=0"
