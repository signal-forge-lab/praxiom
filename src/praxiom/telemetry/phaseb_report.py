"""Offline Phase B evidence aggregation for shadow-first promotion review.

This module reads Praxiom's existing privacy-safe run journals only. It never
imports the Runtime, Coordinator, SkillExecutor, or device plumbing and can
therefore be used while the iPhone is disconnected.

The report is descriptive by design. It identifies missing evidence and hard
safety blockers, but it never auto-promotes Phase C: confidence thresholds,
minimum episode counts, and sequence/cheap-validation activation limits remain
an explicit review decision after representative real-device workload exists.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from praxiom.telemetry.context import resolve_state_root

__all__ = ["PHASEB_REPORT_SCHEMA_VERSION", "build_phaseb_report"]

PHASEB_REPORT_SCHEMA_VERSION = 1
_DOMAIN_PREFIXES = ("mergeboss:", "gogomatch:")


def _percentiles(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "median_ms": None, "p90_ms": None}
    return {
        "count": len(ordered),
        "median_ms": ordered[len(ordered) // 2],
        "p90_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))],
    }


def _read_events(path: Path) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    rejected = 0
    if not path.exists():
        return events, rejected
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                rejected += 1
                continue
            if not isinstance(value, dict):
                rejected += 1
                continue
            events.append(value)
    return events, rejected


def _safe_duration(event: dict[str, Any]) -> float | None:
    value = event.get("duration_ms")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def _is_domain_attempt(event: dict[str, Any]) -> bool:
    behavior = event.get("behavior_id")
    if isinstance(behavior, str) and behavior.startswith(_DOMAIN_PREFIXES):
        return True
    skill = event.get("skill_id")
    return isinstance(skill, str) and skill.startswith(_DOMAIN_PREFIXES)


def _count_map(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def build_phaseb_report(
    *,
    state_root: Path | str | None = None,
    run_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Aggregate existing Phase B journals without touching a device.

    ``run_ids`` limits the report to named runs. When omitted, every run
    directory under the configured state root is inspected. Missing journals
    are represented as evidence gaps rather than inferred as success.
    """
    root = Path(state_root) if state_root is not None else resolve_state_root()
    runs_root = root / "runs"
    if run_ids is None:
        selected = sorted(
            (entry.name for entry in runs_root.iterdir() if entry.is_dir()),
        ) if runs_root.exists() else []
    else:
        selected = sorted({str(run_id) for run_id in run_ids if str(run_id)})

    observe_ms: list[float] = []
    execute_ms: list[float] = []
    effects: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    fallbacks: Counter[str] = Counter()
    candidates: Counter[str] = Counter()
    domains: Counter[str] = Counter()

    total_events = 0
    rejected_records = 0
    attempts = 0
    succeeded_none = 0
    domain_attempts = 0
    policy_decisions = 0
    shadow_optimizations = 0
    shadow_divergences = 0
    learning_records = 0
    recoveries = 0
    actual_multi_action_sequences = 0
    completed_runs = 0
    run_rows: list[dict[str, Any]] = []

    for run_id in selected:
        events, rejected = _read_events(runs_root / run_id / "events.jsonl")
        rejected_records += rejected
        total_events += len(events)
        row = {
            "run_id": run_id,
            "events": len(events),
            "rejected_records": rejected,
            "attempts": 0,
            "domain_attempts": 0,
            "policy_decisions": 0,
            "learning_records": 0,
            "completed": False,
        }

        for event in events:
            event_type = event.get("event_type")
            if event_type == "run.completed":
                row["completed"] = True
            elif event_type == "runtime.observe":
                value = _safe_duration(event)
                if value is not None:
                    observe_ms.append(value)
            elif event_type == "runtime.execute":
                value = _safe_duration(event)
                if value is not None:
                    execute_ms.append(value)
            elif event_type == "attempt.completed":
                attempts += 1
                row["attempts"] += 1
                outcome = event.get("outcome")
                if isinstance(outcome, str):
                    effects[outcome] += 1
                if event.get("status") == "succeeded" and outcome == "NONE":
                    succeeded_none += 1
                if _is_domain_attempt(event):
                    domain_attempts += 1
                    row["domain_attempts"] += 1
                    behavior = event.get("behavior_id") or event.get("skill_id")
                    if isinstance(behavior, str):
                        domains[behavior.split(":", 1)[0]] += 1
            elif event_type == "policy.decision":
                policy_decisions += 1
                row["policy_decisions"] += 1
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                if payload.get("recommended") is True:
                    shadow_optimizations += 1
                recommendation = event.get("policy_recommendation")
                actual = event.get("actual_policy")
                if recommendation is not None and actual is not None and recommendation != actual:
                    shadow_divergences += 1
            elif event_type == "learning.recorded":
                learning_records += 1
                row["learning_records"] += 1
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                kind = payload.get("candidate_kind")
                if isinstance(kind, str):
                    candidates[kind] += 1
            elif event_type == "runtime.recover":
                recoveries += 1
            elif event_type == "sequence.decision":
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                size = payload.get("actual_batch_size")
                if isinstance(size, int) and not isinstance(size, bool) and size > 1:
                    actual_multi_action_sequences += 1

            status = event.get("status")
            if status in {"failed", "unknown"}:
                failures[str(status)] += 1
            reason = event.get("fallback_reason")
            if isinstance(reason, str) and reason:
                fallbacks[reason] += 1

        if row["completed"]:
            completed_runs += 1
        run_rows.append(row)

    evidence_gaps: list[str] = []
    if not selected:
        evidence_gaps.append("no-runs")
    if domain_attempts == 0:
        evidence_gaps.append("representative-domain-attempts-missing")
    if policy_decisions == 0:
        evidence_gaps.append("shadow-policy-decisions-missing")
    if learning_records == 0:
        evidence_gaps.append("learning-records-missing")

    safety_blockers: list[str] = []
    if rejected_records:
        safety_blockers.append("journal-records-rejected")
    if effects.get("PARTIAL", 0):
        safety_blockers.append("partial-effect-observed")
    if effects.get("UNKNOWN", 0):
        safety_blockers.append("unknown-effect-observed")
    if failures:
        safety_blockers.append("failed-or-unknown-events-observed")

    return {
        "schema_version": PHASEB_REPORT_SCHEMA_VERSION,
        "kind": "phase-b-shadow-evidence-report",
        "source": "privacy-safe-journals-only",
        "runs": run_rows,
        "aggregate": {
            "run_count": len(selected),
            "completed_runs": completed_runs,
            "events": total_events,
            "rejected_records": rejected_records,
            "attempts": attempts,
            "successful_none_attempts": succeeded_none,
            "representative_domain_attempts": domain_attempts,
            "domains": _count_map(domains),
            "observe": _percentiles(observe_ms),
            "execute": _percentiles(execute_ms),
            "effects": _count_map(effects),
            "policy_decisions": policy_decisions,
            "shadow_optimizations_recommended": shadow_optimizations,
            "shadow_divergences": shadow_divergences,
            "learning_records": learning_records,
            "learning_candidates": _count_map(candidates),
            "recoveries": recoveries,
            "actual_multi_action_sequences": actual_multi_action_sequences,
            "fallbacks": _count_map(fallbacks),
        },
        "evidence_gaps": evidence_gaps,
        "safety_blockers": safety_blockers,
        "promotion": {
            "automatic_promotion": False,
            "decision": "HOLD" if evidence_gaps or safety_blockers else "MANUAL_REVIEW_REQUIRED",
            "thresholds": "intentionally-unset-until-representative-real-device-data",
        },
    }
