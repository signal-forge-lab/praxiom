from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "phasec0_readiness_analysis.py"


def _load():
    spec = importlib.util.spec_from_file_location("phasec0_readiness_analysis", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_retained_real_device_evidence_yields_narrow_ready_canary(tmp_path: Path):
    module = _load()
    report = module.analyze(state_root=tmp_path)

    assert report["promotion_decision"]["ready"] is True
    assert report["decision_scope"] == "c0-closure-evidence-with-retained-operational-preflight"
    assert report["candidate_operation_class"] == "system:return-home"
    assert report["adaptive_surface"] == "observation-only"
    assert report["sequence_live"] is False
    assert report["retained_real_device"]["r4_action_counts"]["home"] >= 4
    assert report["retained_real_device"]["home_structural_postcondition"] is True
    assert report["retained_real_device"]["zero_blind_replay"] is True
    assert report["shadow"]["stable"] is True
    assert report["shadow"]["mode"] == "retained-evidence-shadow-replay"
    assert report["shadow"]["action_reduction"] == 0
    assert report["shadow"]["live_applied"] == 0
    assert report["fallback"]["proven"] is True
    assert report["c0_current_device"]["direct_canary"]["available"] is False
    assert report["c0_current_device"]["home_operational_preflight"]["available"] is False
    assert report["c0_current_device"]["home_latency_sample"]["available"] is False
    assert report["c0_current_device"]["pre_mutation_startup_stalls"] == 0
    assert report["c0_current_device"]["pre_mutation_observe_failures"] == 0
    assert report["operational_preflight_evidence"]["decision"]["ready"] is False
    assert report["c0_completion"]["ready"] is False


def test_home_promotion_floor_is_not_derived_from_observed_sample_count(tmp_path: Path):
    module = _load()
    assert module.HOME_MIN_CURRENT_DEVICE_SUCCESSES == 4
    assert module.HOME_MIN_RETAINED_SHADOW_EVALUATIONS == 4

    # The accepted policy remains a fixed four-sample floor; changing the
    # current evidence count must not silently lower the policy threshold.
    report = module.analyze(state_root=tmp_path)
    policy = report["promotion_policy"]
    assert policy["min_current_device_success_none"] == 4
    assert policy["min_shadow_evaluations"] == 4
    assert policy["min_recovery_rate"] is None


def test_successful_home_operational_run_closes_c0_but_live_start_still_rechecks(tmp_path: Path):
    module = _load()
    run = tmp_path / "runs" / "phasec0-home-preflight-test"
    run.mkdir(parents=True)
    events = [
        {"event_type": "run.started", "status": "running"},
        {"event_type": "runtime.observe"},
        {
            "event_type": "attempt.completed",
            "behavior_id": "system:return-home",
            "status": "succeeded",
            "outcome": "NONE",
            "payload": {"replayed": False},
        },
        {"event_type": "runtime.execute", "payload": {"action_kinds": ["home"]}},
        {"event_type": "runtime.observe"},
        {"event_type": "run.completed", "status": "ok"},
    ]
    (run / "events.jsonl").write_text(
        "\n".join(__import__("json").dumps(item) for item in events) + "\n",
        encoding="utf-8",
    )
    (run / "summary.json").write_text(
        __import__("json").dumps(
            {"failures": {"by_effect": {}, "by_error_code": {}}}
        ),
        encoding="utf-8",
    )

    report = module.analyze(state_root=tmp_path)

    assert report["promotion_decision"]["ready"] is True
    assert report["c0_current_device"]["home_operational_preflight"]["ready"] is True
    assert report["operational_preflight_evidence"]["decision"]["ready"] is True
    assert report["c0_completion"] == {
        "ready": True,
        "phase_c_status": "READY_FOR_LIMITED_CANARY",
    }
    assert "re-evaluate CanaryEnvironment" in report["phase_c_start_requirement"]


def test_current_wifi_latency_sample_participates_in_class_p90_gate(tmp_path: Path):
    module = _load()
    run = tmp_path / "runs" / "phasec0-home-latency-sample-20260912"
    run.mkdir(parents=True)
    (run / "summary.json").write_text(
        __import__("json").dumps(
            {
                "actions": {"count": 6},
                "execute": {"median_ms": 117.7, "p90_ms": 159.2},
                "failures": {"by_effect": {}, "by_error_code": {}},
            }
        ),
        encoding="utf-8",
    )

    report = module.analyze(state_root=tmp_path)

    sample = report["c0_current_device"]["home_latency_sample"]
    assert sample["available"] is True
    assert sample["actions"] == 6
    assert sample["p90_ms"] == 159.2
    assert report["home_latency"]["current_wifi_p90_ms"] == 159.2
    # The accepted policy uses the stricter retained R4 p90 (502ms here), not
    # the smaller current Wi-Fi sample and never lowers its threshold to fit.
    assert report["home_latency"]["policy_observed_p90_ms"] == 502
    assert report["promotion_decision"]["ready"] is True
