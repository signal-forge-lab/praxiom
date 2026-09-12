"""Rough per-run reporting: summary + learning snapshot (A8, Phase A).

Both builders are pure functions of the validated journal events, so they
are deterministic, recomputable at any time, and safe to treat as caches:
``summary.json`` / ``learning_snapshot.json`` are projections written on
clean close, never safety authority and never mutation authority.

The summary answers the handoff A8 questions manually (durations, observe /
execute counts and percentiles, action counts, full-observe vs
cheap-validation, shadow recommended vs actual sequence sizes, recovery
attempts/successes, failures by class/effect, fallback reasons, learning
candidates, and policy/shadow divergences) without building any cross-system
analytics product.

The learning snapshot projects only evidence facts (skill id/version,
behavior/domain identity, outcome/effect counts, execution references,
timestamps). It never contains a ``SkillTrustToken`` or any token-shaped
authority material; ``token_authority_persisted`` is a constant ``false``
marker so this privacy property stays machine-checkable.

Percentile convention mirrors the certified R9 adaptive telemetry exactly:
``median = sorted[n // 2]``, ``p90 = sorted[min(n - 1, int(n * 0.9))]``.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Iterable

__all__ = ["SUMMARY_SCHEMA_VERSION", "build_learning_snapshot", "build_summary"]

SUMMARY_SCHEMA_VERSION = 1
MAX_SNAPSHOT_EPISODES = 256
MAX_EPISODE_EXECUTION_REFS = 8


def _parse_ts(ts: str | None) -> datetime | None:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _percentile_stats(values: list[float]) -> dict[str, Any]:
    """count/total/median/p90 over ascending values (R9 percentile rule)."""
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "total_ms": 0.0, "median_ms": None, "p90_ms": None}
    return {
        "count": len(ordered),
        "total_ms": round(sum(ordered), 3),
        "median_ms": ordered[len(ordered) // 2],
        "p90_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))],
    }


def _duration_values(events: Iterable[dict[str, Any]], event_type: str) -> list[float]:
    out: list[float] = []
    for event in events:
        if event.get("event_type") != event_type:
            continue
        value = event.get("duration_ms")
        if isinstance(value, (int, float)) and value >= 0:
            out.append(float(value))
    return out


def _counted(counter: Counter) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def build_summary(
    events: Iterable[dict[str, Any]],
    *,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    """Build the rough improvement-judgment summary for one run (A8)."""
    events = [e for e in events if isinstance(e, dict)]
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "kind": "run-summary",
        "generated_utc": generated_utc,
    }

    started = next((e for e in events if e.get("event_type") == "run.started"), None)
    completed = next(
        (e for e in reversed(events) if e.get("event_type") == "run.completed"),
        None,
    )
    run_id = None
    for event in events:
        if isinstance(event.get("run_id"), str):
            run_id = event["run_id"]
            break
    duration_ms = None
    started_ts = _parse_ts((started or {}).get("ts_utc"))
    completed_ts = _parse_ts((completed or {}).get("ts_utc"))
    if started_ts is not None and completed_ts is not None:
        duration_ms = round((completed_ts - started_ts).total_seconds() * 1000.0, 3)
    summary["run"] = {
        "run_id": run_id,
        "started_utc": (started or {}).get("ts_utc"),
        "completed_utc": (completed or {}).get("ts_utc"),
        "duration_ms": duration_ms,
    }

    summary["observe"] = _percentile_stats(
        _duration_values(events, "runtime.observe"))
    summary["execute"] = _percentile_stats(
        _duration_values(events, "runtime.execute"))

    action_count = 0
    execute_batch_sizes: Counter = Counter()
    for event in events:
        if event.get("event_type") != "runtime.execute":
            continue
        count = event.get("payload", {}).get("action_count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            action_count += count
            execute_batch_sizes[str(count)] += 1
    summary["actions"] = {
        "count": action_count,
        "execute_batch_sizes": _counted(execute_batch_sizes),
    }

    observe_modes: Counter = Counter()
    for event in events:
        if event.get("event_type") not in {"validation.performed", "runtime.observe"}:
            continue
        mode = event.get("payload", {}).get("observe_mode")
        if mode in {"full", "cheap_validate"}:
            observe_modes[mode] += 1
    summary["validation"] = {
        "full_observe": observe_modes.get("full", 0),
        "cheap_validate": observe_modes.get("cheap_validate", 0),
    }

    policy_recommended: Counter = Counter()
    legacy_sequence_recommended: Counter = Counter()
    actual_sizes: Counter = Counter()
    for event in events:
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        if event_type == "policy.decision":
            size = payload.get("recommended_batch_size")
            if isinstance(size, int) and not isinstance(size, bool) and size >= 0:
                policy_recommended[str(size)] += 1
        elif event_type == "sequence.decision":
            size = payload.get("recommended_batch_size")
            if isinstance(size, int) and not isinstance(size, bool) and size >= 0:
                legacy_sequence_recommended[str(size)] += 1
            size = payload.get("actual_batch_size")
            if isinstance(size, int) and not isinstance(size, bool) and size >= 0:
                actual_sizes[str(size)] += 1
    recommended = policy_recommended or legacy_sequence_recommended
    summary["sequences"] = {
        "shadow_recommended_sizes": _counted(recommended),
        "actual_sizes": _counted(actual_sizes),
    }

    recovery_attempts = 0
    recovery_successes = 0
    for event in events:
        if event.get("event_type") != "runtime.recover":
            continue
        recovery_attempts += 1
        if event.get("payload", {}).get("repaired") is True:
            recovery_successes += 1
    summary["recovery"] = {
        "attempts": recovery_attempts,
        "successes": recovery_successes,
    }

    effects: Counter = Counter()
    error_codes: Counter = Counter()
    for event in events:
        if event.get("status") not in {"failed", "unknown"}:
            continue
        outcome = event.get("outcome")
        effects[outcome if isinstance(outcome, str) else event["status"]] += 1
        code = event.get("payload", {}).get("error_code")
        if isinstance(code, str):
            error_codes[code] += 1
    summary["failures"] = {
        "by_effect": _counted(effects),
        "by_error_code": _counted(error_codes),
    }

    fallbacks: Counter = Counter()
    for event in events:
        reason = event.get("fallback_reason")
        if isinstance(reason, str):
            fallbacks[reason] += 1
    summary["fallbacks"] = {"reasons": _counted(fallbacks)}

    decisions = 0
    divergences = 0
    divergence_pairs: Counter = Counter()
    for event in events:
        if event.get("event_type") != "policy.decision":
            continue
        decisions += 1
        recommendation = event.get("policy_recommendation")
        actual = event.get("actual_policy")
        if recommendation is not None and actual is not None \
                and recommendation != actual:
            divergences += 1
            divergence_pairs[
                f"{recommendation}|{actual}|{event.get('fallback_reason') or ''}"
            ] += 1
    summary["policy"] = {
        "decisions": decisions,
        "shadow_divergences": divergences,
        "divergence_pairs": _counted(divergence_pairs),
    }

    learning_records = 0
    candidates_by_kind: Counter = Counter()
    reuse_recommended = 0
    for event in events:
        if event.get("event_type") != "learning.recorded":
            continue
        learning_records += 1
        payload = event.get("payload", {})
        kind = payload.get("candidate_kind")
        if isinstance(kind, str):
            candidates_by_kind[kind] += 1
        if payload.get("recommended") is True:
            reuse_recommended += 1
    summary["learning"] = {
        "records": learning_records,
        "candidates_by_kind": _counted(candidates_by_kind),
        "reuse_recommended": reuse_recommended,
    }

    artifacts_reserved = sum(
        1 for e in events if e.get("event_type") == "artifacts.reserved")
    by_type: Counter = Counter(
        e.get("event_type", "<missing>") for e in events)
    torn = 0
    malformed = 0
    for event in events:
        if event.get("event_type") != "journal.recovered":
            continue
        payload = event.get("payload", {})
        torn += payload.get("torn_records", 0)
        malformed += payload.get("malformed_records", 0)
    summary["artifacts"] = {"reserved_refs": artifacts_reserved}
    summary["events"] = {
        "total": len(events),
        "by_type": _counted(by_type),
        "torn_records": torn,
        "malformed_records": malformed,
    }
    return summary


def build_learning_snapshot(
    events: Iterable[dict[str, Any]],
    *,
    run_id: str | None = None,
    generated_utc: str | None = None,
) -> dict[str, Any]:
    """Project bounded cross-run learning evidence facts (no authority).

    Episodes group completed attempts by (domain, skill_id, skill_version)
    and retain only counts, effect classifications, and execution id
    references — the evidence facts the design freeze allows. Historical
    evidence never contains or implies a live trust token; rebinding to a
    fresh live token is the registry's decision in a later run, never this
    snapshot's.
    """
    events = [e for e in events if isinstance(e, dict)]
    episodes: dict[tuple[str, str, str], dict[str, Any]] = {}
    totals: Counter = Counter()
    for event in events:
        if event.get("event_type") != "attempt.completed":
            continue
        key = (
            event.get("domain") if isinstance(event.get("domain"), str) else "",
            event.get("skill_id") if isinstance(event.get("skill_id"), str) else "",
            event.get("skill_version")
            if isinstance(event.get("skill_version"), str) else "",
        )
        episode = episodes.get(key)
        if episode is None:
            episode = {
                "domain": key[0],
                "skill_id": key[1],
                "skill_version": key[2],
                "attempts": 0,
                "effects": {},
                "execution_ids": [],
                "last_status": None,
                "last_seq": 0,
            }
            episodes[key] = episode
        episode["attempts"] += 1
        totals["attempts"] += 1
        outcome = event.get("outcome")
        effect = outcome if outcome in {"NONE", "PARTIAL", "UNKNOWN"} \
            else "UNSPECIFIED"
        episode["effects"][effect] = episode["effects"].get(effect, 0) + 1
        totals[effect] += 1
        execution_id = event.get("execution_id")
        if isinstance(execution_id, str) \
                and execution_id not in episode["execution_ids"] \
                and len(episode["execution_ids"]) < MAX_EPISODE_EXECUTION_REFS:
            episode["execution_ids"].append(execution_id)
        seq = event.get("seq")
        if isinstance(seq, int) and seq >= episode["last_seq"]:
            episode["last_seq"] = seq
            status = event.get("status")
            episode["last_status"] = status if isinstance(status, str) else None

    ordered_keys = sorted(episodes)
    truncated = max(0, len(ordered_keys) - MAX_SNAPSHOT_EPISODES)
    projected = []
    for key in ordered_keys[:MAX_SNAPSHOT_EPISODES]:
        episode = episodes[key]
        projected.append({
            "domain": episode["domain"],
            "skill_id": episode["skill_id"],
            "skill_version": episode["skill_version"],
            "attempts": episode["attempts"],
            "effects": {
                effect: episode["effects"][effect]
                for effect in sorted(episode["effects"])
            },
            "execution_ids": list(episode["execution_ids"]),
            "last_status": episode["last_status"],
            "last_seq": episode["last_seq"],
        })
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "kind": "learning-snapshot",
        "run_id": run_id,
        "generated_utc": generated_utc,
        # Constant privacy marker: this snapshot never stores trust-token
        # authority; rebinding requires a fresh live registry token later.
        "token_authority_persisted": False,
        "episode_count": len(projected),
        "truncated_episodes": truncated,
        "episodes": projected,
        "totals": {
            "attempts": totals["attempts"],
            "effects": {
                effect: totals[effect]
                for effect in sorted(totals) if effect != "attempts"
            },
        },
    }
