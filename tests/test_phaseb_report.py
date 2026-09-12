from __future__ import annotations

from pathlib import Path

from praxiom.telemetry.context import RunContext
from praxiom.telemetry.phaseb_report import build_phaseb_report


def _journal(root: Path, run_id: str):
    return RunContext.create(state_root=root, run_id=run_id).open_journal(durable=False)


def test_phaseb_report_holds_when_only_transport_baseline_exists(tmp_path):
    journal = _journal(tmp_path, "baseline")
    journal.emit("run.started", phase="run", status="running")
    journal.emit("runtime.observe", phase="observe", duration_ms=10.0)
    journal.emit("attempt.completed", phase="attempt", status="succeeded",
                 outcome="NONE", behavior_id="home-baseline", skill_id="home-baseline")
    journal.emit("run.completed", phase="run", status="succeeded")
    journal.close()

    report = build_phaseb_report(state_root=tmp_path, run_ids=["baseline"])
    aggregate = report["aggregate"]
    assert aggregate["attempts"] == 1
    assert aggregate["successful_none_attempts"] == 1
    assert aggregate["representative_domain_attempts"] == 0
    assert aggregate["policy_decisions"] == 0
    assert report["promotion"]["decision"] == "HOLD"
    assert report["promotion"]["automatic_promotion"] is False
    assert "representative-domain-attempts-missing" in report["evidence_gaps"]
    assert "shadow-policy-decisions-missing" in report["evidence_gaps"]


def test_phaseb_report_aggregates_domain_shadow_learning_without_auto_promoting(tmp_path):
    journal = _journal(tmp_path, "domain-run")
    journal.emit("run.started", phase="run", status="running")
    journal.emit("runtime.observe", phase="observe", duration_ms=12.0)
    journal.emit("runtime.observe", phase="observe", duration_ms=30.0)
    journal.emit("runtime.execute", phase="execute", duration_ms=100.0,
                 payload={"action_count": 1})
    journal.emit("attempt.completed", phase="attempt", status="succeeded",
                 outcome="NONE", behavior_id="mergeboss:launch",
                 skill_id="mergeboss:launch", skill_version="1")
    journal.emit("policy.decision", phase="policy",
                 policy_recommendation="cheap-validate",
                 actual_policy="certified-safe-behavior",
                 payload={"recommended": True, "recommended_batch_size": 2,
                          "actual_batch_size": 1})
    journal.emit("learning.recorded", phase="learning", status="succeeded",
                 outcome="NONE", behavior_id="mergeboss:launch",
                 skill_id="mergeboss:launch", skill_version="1",
                 payload={"candidate_kind": "episode", "recommended": False})
    journal.emit("run.completed", phase="run", status="succeeded")
    journal.close()

    report = build_phaseb_report(state_root=tmp_path)
    aggregate = report["aggregate"]
    assert aggregate["representative_domain_attempts"] == 1
    assert aggregate["domains"] == {"mergeboss": 1}
    assert aggregate["policy_decisions"] == 1
    assert aggregate["shadow_optimizations_recommended"] == 1
    assert aggregate["shadow_divergences"] == 1
    assert aggregate["learning_records"] == 1
    assert aggregate["learning_candidates"] == {"episode": 1}
    assert aggregate["observe"] == {"count": 2, "median_ms": 30.0, "p90_ms": 30.0}
    assert aggregate["execute"] == {"count": 1, "median_ms": 100.0, "p90_ms": 100.0}
    assert report["evidence_gaps"] == []
    assert report["safety_blockers"] == []
    assert report["promotion"]["decision"] == "MANUAL_REVIEW_REQUIRED"
    assert report["promotion"]["automatic_promotion"] is False


def test_phaseb_report_fails_closed_on_partial_unknown_or_malformed_journal(tmp_path):
    journal = _journal(tmp_path, "unsafe-run")
    journal.emit("run.started", phase="run", status="running")
    journal.emit("attempt.completed", phase="attempt", status="failed",
                 outcome="PARTIAL", behavior_id="gogomatch:swap-tiles",
                 skill_id="gogomatch:swap-tiles")
    journal.emit("attempt.completed", phase="attempt", status="unknown",
                 outcome="UNKNOWN", behavior_id="gogomatch:swap-tiles",
                 skill_id="gogomatch:swap-tiles")
    journal.emit("policy.decision", phase="policy",
                 actual_policy="certified-safe-behavior",
                 payload={"recommended": False})
    journal.emit("learning.recorded", phase="learning",
                 payload={"candidate_kind": "episode", "recommended": False})
    journal.emit("run.completed", phase="run", status="failed")
    journal.close()
    with (tmp_path / "runs" / "unsafe-run" / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{malformed\n")

    report = build_phaseb_report(state_root=tmp_path, run_ids=["unsafe-run"])
    assert report["aggregate"]["rejected_records"] == 1
    assert report["aggregate"]["effects"] == {"PARTIAL": 1, "UNKNOWN": 1}
    assert "journal-records-rejected" in report["safety_blockers"]
    assert "partial-effect-observed" in report["safety_blockers"]
    assert "unknown-effect-observed" in report["safety_blockers"]
    assert "failed-or-unknown-events-observed" in report["safety_blockers"]
    assert report["promotion"]["decision"] == "HOLD"
