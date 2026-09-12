from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phasec_launch_application_canary.py"
SPEC = importlib.util.spec_from_file_location("phasec_launch_application_canary", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write_report(root: Path, *, samples: list[dict], status: str = "completed") -> str:
    run_id = "validator-run"
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / MODULE.VALIDATOR_REPORT_NAME).write_text(
        json.dumps({"status": status, "samples": samples}), encoding="utf-8"
    )
    return run_id


def _good_sample() -> dict:
    return {
        "launch_success_none": True,
        "launch_replayed": False,
        "active_app_bundle_id_present": True,
        "active_app_pid_present": True,
        "cheap_foreground_match": True,
        "cheap_validator_fallback_full_observe": False,
        "full_observe_foreground_match": True,
    }


def test_validator_report_promotes_generic_launch_observation_only(tmp_path: Path):
    run_id = _write_report(tmp_path, samples=[_good_sample() for _ in range(5)])
    readiness, analysis = MODULE._promotion_readiness(
        state_root=tmp_path, validator_run_id=run_id, fallback_proven=True
    )
    assert readiness.ready is True
    assert readiness.operation_class == "system:launch-application"
    assert readiness.allowed_surface == "observation-only"
    assert readiness.sequence_live_allowed is False
    assert analysis["clean_success_none"] == 5
    assert analysis["causal_matches"] == 5
    assert analysis["shadow_evaluations"] == 5


def test_promotion_fails_closed_when_sample_is_not_corroborated(tmp_path: Path):
    samples = [_good_sample() for _ in range(5)]
    samples[-1]["full_observe_foreground_match"] = False
    run_id = _write_report(tmp_path, samples=samples)
    readiness, analysis = MODULE._promotion_readiness(
        state_root=tmp_path, validator_run_id=run_id, fallback_proven=True
    )
    assert readiness.ready is False
    assert "causal-validator-not-proven" in readiness.reasons
    assert analysis["causal_matches"] == 4


def test_promotion_requires_fallback_proof(tmp_path: Path):
    run_id = _write_report(tmp_path, samples=[_good_sample() for _ in range(5)])
    readiness, _analysis = MODULE._promotion_readiness(
        state_root=tmp_path, validator_run_id=run_id, fallback_proven=False
    )
    assert readiness.ready is False
    assert "fallback-not-proven" in readiness.reasons


def test_promotion_requires_five_clean_current_device_samples(tmp_path: Path):
    run_id = _write_report(tmp_path, samples=[_good_sample() for _ in range(4)])
    readiness, analysis = MODULE._promotion_readiness(
        state_root=tmp_path, validator_run_id=run_id, fallback_proven=True
    )
    assert readiness.ready is False
    assert "insufficient-current-device-success-none" in readiness.reasons
    assert analysis["samples"] == 4


def test_canary_close_failure_still_persists_report(tmp_path: Path):
    run_dir = tmp_path / "runs" / "close-failed"
    run_dir.mkdir(parents=True)

    class _Session:
        context = type("Context", (), {"run_dir": run_dir})()

        def close(self, **_kwargs):
            raise RuntimeError("close-failed")

    report = {
        "run_id": "close-failed",
        "status": "completed",
        "promotion": {},
    }
    try:
        MODULE._close_and_persist_canary_report(
            _Session(),
            report,
            close_status="ok",
            close_reason=None,
            suppress_close_error=False,
        )
    except RuntimeError as exc:
        assert str(exc) == "close-failed"
    else:
        raise AssertionError("close failure must be surfaced")
    saved = json.loads((run_dir / MODULE.CANARY_REPORT_NAME).read_text(encoding="utf-8"))
    assert saved["status"] == "failed"
    assert saved["close_error_class"] == "RuntimeError"
