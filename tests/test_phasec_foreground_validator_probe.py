from __future__ import annotations

import importlib.util
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phasec_foreground_validator_probe.py"
SPEC = importlib.util.spec_from_file_location("phasec_foreground_validator_probe", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_active_application_match_retains_no_identity_values():
    evidence = MODULE.inspect_active_application_info(
        {"bundleId": "Expected", "name": "private", "pid": 123},
        "Expected",
    )
    assert evidence.expected_match is True
    assert evidence.bundle_id_present is True
    assert evidence.pid_present is True
    assert "Expected" not in repr(evidence)
    assert "private" not in repr(evidence)


def test_active_application_match_fails_closed_on_wrong_app():
    evidence = MODULE.inspect_active_application_info(
        {"bundleId": "Other", "pid": 123}, "Expected"
    )
    assert evidence.expected_match is False
    assert evidence.bundle_id_present is True


def test_full_observation_match_is_application_scoped():
    observation = SimpleNamespace(
        elements=(
            SimpleNamespace(role="XCUIElementTypeButton", label="Expected", text=None),
            SimpleNamespace(role="XCUIElementTypeApplication", label=None, text="Expected"),
        )
    )
    assert MODULE.observation_matches_foreground(observation, "Expected") is True


def test_probe_blocks_before_mutation_when_remote_pairing_is_unavailable(monkeypatch, tmp_path: Path):
    async def no_endpoint():
        raise RuntimeError("exactly-one-remote-paired-device-required")

    monkeypatch.setattr(MODULE, "_discover_endpoint", no_endpoint)
    result = asyncio.run(
        MODULE._run_probe(state_root=tmp_path, run_id="blocked-probe", iterations=1)
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "remote-pairing-unavailable"
    assert result["mutation_count"] == 0


def test_probe_report_projection_excludes_sensitive_identity_values():
    report = {
        "run_id": "r1",
        "status": "completed",
        "iterations": 1,
        "samples": [
            {
                "iteration": 1,
                "launch_success_none": True,
                "launch_replayed": False,
                "application_node_count": 1,
                "active_app_bundle_id_present": True,
                "active_app_pid_present": True,
                "cheap_foreground_match": True,
                "matched_attribute_keys": ["label", "name"],
                "cheap_validator_latency_ms": 123.4,
                "cheap_validator_error_class": None,
                "cheap_validator_fallback_full_observe": False,
                "full_observe_foreground_match": True,
                "home_restore_success_none": True,
                "home_restore_icon_count": 42,
                "raw_xml": "<private/>",
                "bundle_id": "private.bundle",
                "expected_application_identity": "Private App",
            }
        ],
        "summary": {"actions": {"count": 2}, "failures": {"by_effect": {}}},
    }
    projected = MODULE._project_probe_report(report)
    encoded = json.dumps(projected, sort_keys=True)
    assert projected["candidate_operation_class"] == "system:launch-application"
    assert projected["privacy"] == {
        "raw_xml_persisted": False,
        "app_identity_persisted": False,
        "bundle_id_persisted": False,
    }
    assert "<private/>" not in encoded
    assert "private.bundle" not in encoded
    assert "Private App" not in encoded


def test_probe_report_persists_under_run_directory(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    session = SimpleNamespace(context=SimpleNamespace(run_dir=run_dir))
    path = MODULE._persist_probe_report(
        session,
        {"run_id": "r1", "status": "completed", "iterations": 0, "samples": []},
    )
    assert path == run_dir / MODULE.REPORT_NAME
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["run_id"] == "r1"
    assert loaded["privacy"]["raw_xml_persisted"] is False


def test_close_failure_still_persists_probe_report(tmp_path: Path):
    run_dir = tmp_path / "runs" / "close-failed"
    run_dir.mkdir(parents=True)

    class _Session:
        context = SimpleNamespace(run_dir=run_dir)

        def close(self, **_kwargs):
            raise RuntimeError("coordinator-close-failed")

    report = {
        "run_id": "close-failed",
        "status": "completed",
        "iterations": 0,
        "samples": [],
    }
    with pytest.raises(RuntimeError, match="coordinator-close-failed"):
        MODULE._close_and_persist_probe_report(
            _Session(),
            report,
            close_status="ok",
            close_reason=None,
            suppress_close_error=False,
        )
    loaded = json.loads((run_dir / MODULE.REPORT_NAME).read_text(encoding="utf-8"))
    assert loaded["status"] == "failed"
    assert loaded["close_error_class"] == "RuntimeError"


def test_primary_error_keeps_close_failure_as_evidence_without_masking(tmp_path: Path):
    run_dir = tmp_path / "runs" / "primary-failed"
    run_dir.mkdir(parents=True)

    class _Session:
        context = SimpleNamespace(run_dir=run_dir)

        def close(self, **_kwargs):
            raise RuntimeError("coordinator-close-failed")

    report = {
        "run_id": "primary-failed",
        "status": "failed",
        "error_type": "ValueError",
        "iterations": 0,
        "samples": [],
    }
    MODULE._close_and_persist_probe_report(
        _Session(),
        report,
        close_status="failed",
        close_reason="probe-exception",
        suppress_close_error=True,
    )
    loaded = json.loads((run_dir / MODULE.REPORT_NAME).read_text(encoding="utf-8"))
    assert loaded["error_type"] == "ValueError"
    assert loaded["close_error_class"] == "RuntimeError"


def test_explicit_run_id_reuse_is_refused_before_device_work(tmp_path: Path):
    run_dir = tmp_path / "runs" / "duplicate"
    run_dir.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="run-id-already-exists"):
        MODULE._assert_unused_run_id(tmp_path, "duplicate")


def test_cheap_validator_failure_recovers_plumbing_and_full_observes(monkeypatch):
    calls = {"recover": 0, "observe": 0}

    class _Transport:
        async def active_application_info(self):
            raise RuntimeError("stale-session")

    class _Runtime:
        async def recover(self):
            calls["recover"] += 1

    audit = SimpleNamespace(revision="fresh-r2", elements=())

    async def fake_observe(_runtime):
        calls["observe"] += 1
        return audit

    monkeypatch.setattr(MODULE, "_observe_bounded", fake_observe)
    foreground, _latency, error_class, returned_audit, fallback = asyncio.run(
        MODULE._foreground_validation_with_safe_fallback(
            _Runtime(), _Transport(), "expected.bundle"
        )
    )
    assert foreground is None
    assert error_class == "RuntimeError"
    assert returned_audit is audit
    assert fallback is True
    assert calls == {"recover": 1, "observe": 1}
