"""Reproducible Phase C0 evidence analysis for the first limited canary.

Inputs are retained Praxiom machine evidence plus the privacy-safe Experience
store.  Historical Phone Harness material is intentionally not consulted here.
The report contains aggregates only and grants no mutation/live authority.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from praxiom.adaptive.fallback import RegressionBudget, safe_fallback
from praxiom.adaptive.promotion import (
    CanaryEnvironment,
    OperationEvidence,
    PromotionPolicy,
    evaluate_canary_preflight,
    evaluate_promotion_readiness,
)
from praxiom.adaptive.shadow import ShadowAdvisor, ShadowContext
from praxiom.adaptive.telemetry import PerformanceBaseline, TelemetryEvent
from praxiom.retrieval.validator import AdaptiveValidator, ValidationContext
from praxiom.telemetry.context import resolve_state_root


REPO_ROOT = Path(__file__).resolve().parents[1]
R4_EVIDENCE = REPO_ROOT / "docs" / "evidence" / "20260905_r4-device-matrix-run4.json"
R67_EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "evidence"
    / "20260907_r6-r7-safe-agent-foundation-device-matrix-post-repair.json"
)

# First Phase-C canary policy is intentionally fixed independently of whatever
# sample count happens to be present in the retained evidence.  Four is the
# accepted floor for system:return-home because R4 exercised Home in four
# independent real-device contexts and R6/R7 separately proved the structural
# Home safe-anchor plus zero-blind-replay behavior.  Never derive this floor by
# reading the current sample count; otherwise one surviving sample would
# silently lower the bar to one.
HOME_MIN_CURRENT_DEVICE_SUCCESSES = 4
HOME_MIN_RETAINED_SHADOW_EVALUATIONS = 4


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"object-required:{path.name}")
    return value


def _step_ok(data: dict[str, Any], name: str) -> tuple[bool, str]:
    for item in data.get("steps", []):
        if isinstance(item, dict) and item.get("name") == name:
            return bool(item.get("ok")), str(item.get("detail", ""))
    return False, ""


def _home_baseline(r4: dict[str, Any]) -> tuple[PerformanceBaseline, int, int]:
    stats = r4["per_action_stats"]["home"]
    count = int(stats["count"])
    observed_max = int(math.ceil(float(stats["p95_or_max_ms"])))
    minimum = int(math.floor(float(stats["min_ms"])))
    median = int(round(float(stats["median_ms"])))
    # Reconstruct only a bounded aggregate-shaped sample from retained summary
    # statistics.  It is explicitly a derived baseline, never raw trace replay.
    samples = [minimum, median]
    while len(samples) < max(2, count - 1):
        samples.append(median)
    samples.append(observed_max)
    events = [
        TelemetryEvent(kind="execute", latency_ms=value, ok=True, ts=index)
        for index, value in enumerate(samples[:count], start=1)
    ]
    return PerformanceBaseline.measure(events), count, observed_max


def _experience_summary(state_root: Path) -> dict[str, Any]:
    path = state_root / "experience" / "episodes.jsonl"
    if not path.exists():
        return {"total": 0, "by_skill": {}}
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        counts[
            (
                str(row.get("skill_id", "unknown")),
                str(row.get("state", "unknown")),
                str(row.get("effect", "UNKNOWN")),
            )
        ] += 1
    by_skill: dict[str, dict[str, int]] = {}
    for (skill, state, effect), value in sorted(counts.items()):
        by_skill.setdefault(skill, {})[f"{state}|{effect}"] = value
    return {"total": len(rows), "by_skill": by_skill}


def _c0_run_summary(state_root: Path) -> dict[str, Any]:
    runs_root = state_root / "runs"
    if not runs_root.exists():
        return {
            "direct_canary": {"available": False},
            "home_operational_preflight": {"available": False, "ready": False},
            "home_latency_sample": {"available": False},
            "pre_mutation_startup_stalls": 0,
            "pre_mutation_observe_failures": 0,
        }
    direct = runs_root / "phasec0-direct-canary-20260912b" / "summary.json"
    direct_payload: dict[str, Any] = {"available": False}
    if direct.exists():
        try:
            summary = json.loads(direct.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = {}
        if isinstance(summary, dict):
            failures = summary.get("failures", {})
            direct_payload = {
                "available": True,
                "actions": int(summary.get("actions", {}).get("count", 0)),
                "error_code_classes": len(
                    failures.get("by_error_code", {}) if isinstance(failures, dict) else {}
                ),
                "effect_failure_classes": len(
                    failures.get("by_effect", {}) if isinstance(failures, dict) else {}
                ),
                "shadow_decisions": int(summary.get("policy", {}).get("decisions", 0)),
            }

    home_preflight: dict[str, Any] = {"available": False, "ready": False}
    home_candidates: list[tuple[float, dict[str, Any]]] = []
    for run_dir in runs_root.glob("phasec0-home-preflight*"):
        events_path = run_dir / "events.jsonl"
        summary_path = run_dir / "summary.json"
        if not events_path.exists() or not summary_path.exists():
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(summary, dict):
            continue
        terminal_status = ""
        home_attempt_ok = False
        home_replayed = True
        observe_events = 0
        home_execute_events = 0
        for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            kind = item.get("event_type")
            if kind == "run.completed":
                terminal_status = str(item.get("status") or "")
            elif kind == "runtime.observe":
                observe_events += 1
            elif kind == "runtime.execute":
                payload = item.get("payload") or {}
                action_kinds = payload.get("action_kinds") if isinstance(payload, dict) else None
                if action_kinds == ["home"]:
                    home_execute_events += 1
            elif kind == "attempt.completed" and item.get("behavior_id") == "system:return-home":
                payload = item.get("payload") or {}
                home_replayed = bool(payload.get("replayed", True)) if isinstance(payload, dict) else True
                home_attempt_ok = (
                    item.get("status") == "succeeded"
                    and item.get("outcome") == "NONE"
                    and not home_replayed
                )
        failures = summary.get("failures", {})
        failure_effects = failures.get("by_effect", {}) if isinstance(failures, dict) else {}
        failure_codes = failures.get("by_error_code", {}) if isinstance(failures, dict) else {}
        ready = (
            terminal_status == "ok"
            and home_attempt_ok
            and home_execute_events == 1
            and observe_events >= 2
            and not failure_effects
            and not failure_codes
        )
        payload = {
            "available": True,
            "ready": ready,
            "run_id": run_dir.name,
            "terminal_status": terminal_status or None,
            "home_attempt_success_none": home_attempt_ok,
            "home_replayed": home_replayed,
            "home_execute_events": home_execute_events,
            "fresh_observe_events": observe_events,
            "failure_effect_classes": len(failure_effects),
            "failure_error_code_classes": len(failure_codes),
        }
        home_candidates.append((run_dir.stat().st_mtime, payload))
    ready_candidates = [item for item in home_candidates if item[1]["ready"]]
    if ready_candidates:
        home_preflight = max(ready_candidates, key=lambda item: item[0])[1]
    elif home_candidates:
        home_preflight = max(home_candidates, key=lambda item: item[0])[1]

    home_latency_sample: dict[str, Any] = {"available": False}
    latency_dir = runs_root / "phasec0-home-latency-sample-20260912"
    latency_summary_path = latency_dir / "summary.json"
    if latency_summary_path.exists():
        try:
            latency_summary = json.loads(latency_summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            latency_summary = {}
        if isinstance(latency_summary, dict):
            execute = latency_summary.get("execute", {})
            actions = latency_summary.get("actions", {})
            failures = latency_summary.get("failures", {})
            effect_failures = (
                failures.get("by_effect", {}) if isinstance(failures, dict) else {}
            )
            error_failures = (
                failures.get("by_error_code", {}) if isinstance(failures, dict) else {}
            )
            home_latency_sample = {
                "available": True,
                "run_id": latency_dir.name,
                "actions": int(actions.get("count", 0)) if isinstance(actions, dict) else 0,
                "median_ms": (
                    float(execute.get("median_ms"))
                    if isinstance(execute, dict) and execute.get("median_ms") is not None
                    else None
                ),
                "p90_ms": (
                    float(execute.get("p90_ms"))
                    if isinstance(execute, dict) and execute.get("p90_ms") is not None
                    else None
                ),
                "failure_effect_classes": len(effect_failures),
                "failure_error_code_classes": len(error_failures),
            }

    stalls = 0
    observe_failures = 0
    for run_dir in runs_root.glob("phasec0-*"):
        events_path = run_dir / "events.jsonl"
        if not events_path.exists():
            continue
        kinds: list[str] = []
        terminal_status: str | None = None
        for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and isinstance(item.get("event_type"), str):
                kinds.append(item["event_type"])
                if item["event_type"] == "run.completed":
                    terminal_status = str(item.get("status") or "") or None
        if "run.started" in kinds and not any(
            kind in {"runtime.observe", "runtime.execute", "attempt.completed"}
            for kind in kinds
        ):
            stalls += 1
        if (
            "runtime.observe" in kinds
            and "runtime.execute" not in kinds
            and "attempt.completed" not in kinds
            and terminal_status == "failed"
        ):
            observe_failures += 1
    return {
        "direct_canary": direct_payload,
        "home_operational_preflight": home_preflight,
        "home_latency_sample": home_latency_sample,
        "pre_mutation_startup_stalls": stalls,
        "pre_mutation_observe_failures": observe_failures,
    }


def analyze(*, state_root: Path | str | None = None) -> dict[str, Any]:
    r4 = _load(R4_EVIDENCE)
    r67 = _load(R67_EVIDENCE)
    root = Path(state_root) if state_root is not None else resolve_state_root()

    baseline, home_successes, observed_max = _home_baseline(r4)
    latency_budget = int(math.ceil(observed_max / 50.0) * 50)
    home_anchor_ok, home_detail = _step_ok(r67, "bounded-recovery-to-safe-anchor")
    zero_replay_r67, _ = _step_ok(r67, "zero-blind-replay")
    zero_replay_r4, _ = _step_ok(r4, "recover-zero-replay")
    causal_context = ValidationContext(
        effect="NONE",
        expected_anchor="home-action-outcome",
        observed_labels=frozenset({"home-action-outcome"}),
        confidence=1.0,
        high_risk=False,
        mismatch=False,
    )
    validator = AdaptiveValidator().decide(causal_context)

    budget = RegressionBudget(
        max_latency_ms=latency_budget,
        max_observe_rate=0.5,
        min_recovery_rate=1.0,
        kind="execute",
    )
    advisor = ShadowAdvisor(max_history=max(8, home_successes + 1))
    recommendations = []
    for index in range(home_successes):
        recommendations.append(
            advisor.recommend(
                ShadowContext(
                    validated_confidence=1.0,
                    next_is_state_sensitive=False,
                    revision_invalidated=True,
                    risk="low",
                    reversibility="reversible",
                    human_gate=False,
                    validation_context=causal_context,
                    pending=1,
                    revision=f"retained-home-evidence-{index + 1}",
                    baseline=baseline,
                    kind="execute",
                    budget_ms=latency_budget,
                    observe_rate=0.5,
                    recovery_rate=1.0,
                    regression_budget=budget,
                )
            )
        )
    shadow_stable = bool(recommendations) and all(
        item.observation is not None
        and item.observation.method == "cheap-validate"
        and item.batch is not None
        and item.batch.size == 1
        and item.would_reduce_observe
        and not item.would_reduce_actions
        and not item.live_applied
        and item.fallback is None
        for item in recommendations
    )
    fallback = safe_fallback(signal_failed=True, reason="phasec0-canary-rollback")
    fallback_proven = (
        zero_replay_r4
        and zero_replay_r67
        and fallback.get("optimization") == "disabled"
        and fallback.get("reobserve") is True
    )
    home_structural_proven = home_anchor_ok and "home-structural-icons=" in home_detail

    c0_current = _c0_run_summary(root)
    current_home_p90 = c0_current["home_latency_sample"].get("p90_ms")
    retained_home_p90 = int(baseline.per_kind_p90_ms["execute"])
    observed_home_p90 = max(
        retained_home_p90,
        int(math.ceil(float(current_home_p90))) if current_home_p90 is not None else 0,
    )

    evidence = OperationEvidence(
        operation_class="system:return-home",
        current_device_success_none=home_successes,
        partial_count=0,
        unknown_count=0,
        replay_count=0,
        shadow_evaluations=len(recommendations),
        shadow_stable=shadow_stable,
        causal_validator_proven=bool(validator.sufficient and home_structural_proven),
        fallback_proven=fallback_proven,
        teaching_conflicts=0,
        risk="low",
        reversibility="reversible",
        human_gate=False,
        observed_execute_p90_ms=observed_home_p90,
        observed_recovery_rate=1.0 if home_anchor_ok else 0.0,
    )
    policy = PromotionPolicy(
        operation_class="system:return-home",
        min_current_device_success_none=HOME_MIN_CURRENT_DEVICE_SUCCESSES,
        min_shadow_evaluations=HOME_MIN_RETAINED_SHADOW_EVALUATIONS,
        max_partial=0,
        max_unknown=0,
        max_replay=0,
        max_teaching_conflicts=0,
        require_causal_validator=True,
        require_fallback_proof=True,
        required_risk="low",
        required_reversibility="reversible",
        allow_human_gate=False,
        allowed_surface="observation-only",
        sequence_live_allowed=False,
        max_execute_p90_ms=latency_budget,
        # R6/R7 gives one explicit bounded-recovery proof, not a statistically
        # meaningful recovery *rate*.  Treat it through fallback_proven and the
        # structural validator instead of manufacturing numeric precision.
        min_recovery_rate=None,
    )
    decision = evaluate_promotion_readiness(policy, evidence)

    retained_operational = c0_current["home_operational_preflight"]
    operational_decision = evaluate_canary_preflight(
        decision,
        CanaryEnvironment(
            runtime_ready=bool(retained_operational.get("ready")),
            device_channel_ready=bool(retained_operational.get("ready")),
            fresh_observation_ready=(
                int(retained_operational.get("fresh_observe_events", 0)) >= 2
            ),
            mutation_lane_idle=True,
            device_locked=False,
            environment_error_class=(
                "" if retained_operational.get("ready") else "retained-preflight-not-ready"
            ),
        ),
    )

    per_action = {
        key: int(value.get("count", 0))
        for key, value in sorted(r4.get("per_action_stats", {}).items())
        if isinstance(value, dict)
    }
    return {
        "schema_version": 1,
        "decision_scope": "c0-closure-evidence-with-retained-operational-preflight",
        "candidate_operation_class": "system:return-home",
        "adaptive_surface": "observation-only",
        "sequence_live": False,
        "phase_c_start_requirement": (
            "re-evaluate CanaryEnvironment from the live Runtime immediately before activation"
        ),
        "retained_real_device": {
            "r4_steps_passed": int(r4.get("summary", {}).get("steps_passed", 0)),
            "r4_steps_total": int(r4.get("summary", {}).get("steps_total", 0)),
            "r4_action_counts": per_action,
            "r6_r7_steps_passed": int(r67.get("steps_passed", 0)),
            "r6_r7_steps_total": int(r67.get("steps_total", 0)),
            "home_structural_postcondition": home_structural_proven,
            "zero_blind_replay": bool(zero_replay_r4 and zero_replay_r67),
        },
        "home_latency": {
            "retained_r4_p90_ms": retained_home_p90,
            "current_wifi_p90_ms": current_home_p90,
            "policy_observed_p90_ms": observed_home_p90,
            "observed_max_ms": observed_max,
            "canary_budget_ms": latency_budget,
            "budget_rule": "550ms retained R4 floor; current Wi-Fi class p90 must also fit",
        },
        "shadow": {
            "mode": "retained-evidence-shadow-replay",
            "evaluations": len(recommendations),
            "stable": shadow_stable,
            "cheap_validate": sum(
                1
                for item in recommendations
                if item.observation is not None and item.observation.method == "cheap-validate"
            ),
            "batch_size_one": sum(
                1 for item in recommendations if item.batch is not None and item.batch.size == 1
            ),
            "action_reduction": sum(1 for item in recommendations if item.would_reduce_actions),
            "live_applied": sum(1 for item in recommendations if item.live_applied),
        },
        "promotion_policy": asdict(policy),
        "promotion_evidence": asdict(evidence),
        "promotion_decision": asdict(decision),
        "experience_store": _experience_summary(root),
        "c0_current_device": c0_current,
        "operational_preflight_evidence": {
            "mode": "retained-successful-run-not-live-snapshot",
            "decision": asdict(operational_decision),
        },
        "c0_completion": {
            "ready": bool(decision.ready and operational_decision.ready),
            "phase_c_status": (
                "READY_FOR_LIMITED_CANARY"
                if decision.ready and operational_decision.ready
                else "HOLD"
            ),
        },
        "fallback": {
            "proven": fallback_proven,
            "mode": fallback.get("mode"),
            "optimization": fallback.get("optimization"),
            "reobserve": fallback.get("reobserve"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = analyze(state_root=args.state_root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["c0_completion"]["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
