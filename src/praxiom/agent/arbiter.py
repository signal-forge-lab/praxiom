"""R6-A Priority Arbiter (domain-neutral, deterministic).

Arbitrates interrupt/goal events at safe boundaries with stale-plan
invalidation. Teaching is one event type, never unconditional priority.
Trusted device mutation enters only through the accepted Runtime seam via
observe() + execute(..., expected_revision=...) in the coordinator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["InterruptEvent", "ArbitrationResult", "arbitrate"]


@dataclass(frozen=True, kw_only=True)
class InterruptEvent:
    event_id: str
    kind: str  # goal | teaching | operator | deadline | risk
    priority: int  # 0..100 effective priority
    reversibility: str = "reversible"  # reversible | irreversible
    risk: str = "low"  # low | high
    safe_boundary_only: bool = True
    deadline_ms: int | None = None
    goal_assumption: str = ""
    payload_summary: str = ""  # machine summary only, never raw payload


@dataclass(frozen=True, kw_only=True)
class ArbitrationResult:
    selected_id: str | None
    deferred_ids: tuple[str, ...] = ()
    rejected_ids: tuple[str, ...] = ()
    reasons: dict[str, str] = field(default_factory=dict)
    stale_plan_invalidated: bool = False
    trace_version: int = 1


def _effective(ev: InterruptEvent, safety_policy: str) -> tuple[int, str] | None:
    """Return (priority, decision) or None when rejected outright."""
    if ev.risk == "high" and ev.reversibility == "irreversible":
        if ev.kind != "risk" and "safety-gate" in safety_policy:
            return None
    return (ev.priority, "ok")


def arbitrate(
    events: list[InterruptEvent],
    *,
    current_goal: str,
    at_safe_boundary: bool,
    safety_policy: str = "safety-gate:v1",
    current_assumption: str = "",
    now_ms: int | None = None,
) -> ArbitrationResult:
    """Deterministic arbitration. Ties break by (priority desc, event_id asc)."""
    reasons: dict[str, str] = {}
    rejected: list[str] = []
    candidates: list[tuple[int, str, InterruptEvent]] = []
    for ev in events:
        if (ev.deadline_ms is not None and now_ms is not None
                and now_ms >= ev.deadline_ms):
            rejected.append(ev.event_id)
            reasons[ev.event_id] = "rejected:deadline-expired"
            continue
        eff = _effective(ev, safety_policy)
        if eff is None:
            rejected.append(ev.event_id)
            reasons[ev.event_id] = "rejected:unsafe-irreversible-blocked-by-safety-gate"
            continue
        if ev.kind == "teaching" and ev.priority >= 90 and ev.risk == "high":
            # Teaching never bypasses safety policy by origin alone.
            rejected.append(ev.event_id)
            reasons[ev.event_id] = "rejected:teaching-not-absolute-priority"
            continue
        if ev.safe_boundary_only and not at_safe_boundary:
            candidates.append((eff[0], ev.event_id, ev))
            reasons.setdefault(ev.event_id, "deferred:not-at-safe-boundary")
        else:
            candidates.append((eff[0], ev.event_id, ev))
    if not candidates:
        return ArbitrationResult(
            selected_id=None, deferred_ids=(), rejected_ids=tuple(rejected),
            reasons=reasons, stale_plan_invalidated=False,
        )
    candidates.sort(key=lambda t: (-t[0], t[1]))
    # If not at a safe boundary, nothing preempts now.
    if not at_safe_boundary:
        deferred = tuple(eid for _, eid, _ in candidates)
        for _, eid, _ in candidates:
            reasons[eid] = "deferred:not-at-safe-boundary"
        return ArbitrationResult(
            selected_id=None, deferred_ids=deferred,
            rejected_ids=tuple(rejected), reasons=reasons,
            stale_plan_invalidated=False,
        )
    top_prio, top_id, top_ev = candidates[0]
    deferred = tuple(eid for _, eid, _ in candidates[1:])
    for _, eid, _ in candidates[1:]:
        reasons[eid] = "deferred:lower-effective-priority"
    reasons[top_id] = f"selected:priority={top_prio}"
    invalidated = bool(
        current_assumption
        and top_ev.goal_assumption
        and top_ev.goal_assumption != current_assumption
    )
    # A stale plan tied to a superseded assumption cannot continue.
    _ = current_goal
    return ArbitrationResult(
        selected_id=top_id, deferred_ids=deferred,
        rejected_ids=tuple(rejected), reasons=reasons,
        stale_plan_invalidated=invalidated,
    )
