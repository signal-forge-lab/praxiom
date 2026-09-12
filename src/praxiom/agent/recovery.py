"""R6-G Goal-directed State Recovery v1 (Agent task-state recovery).

Distinct from device-plumbing recover(): plans bounded reversible steps
from Current World / Revision toward a goal anchor, validates every step,
suppresses repeat loops, and escalates fail-closed.
Trusted steps run through observe() + execute(expected_revision) only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["WorldState", "RecoveryTransition", "RecoveryPlan", "RecoveryPlanner"]


@dataclass(frozen=True, kw_only=True)
class WorldState:
    anchor_id: str
    state_id: str
    revision: str | None = None
    labels: frozenset[str] = frozenset()


@dataclass(frozen=True, kw_only=True)
class RecoveryTransition:
    transition_id: str
    from_state: str
    to_state: str
    reversible: bool = True
    allowed: bool = True
    risk: str = "low"  # low | high
    uses_runtime: bool = True


@dataclass(frozen=True, kw_only=True)
class RecoveryPlan:
    steps: tuple[RecoveryTransition, ...]
    escalate: bool = False
    reason: str = ""


class RecoveryPlanner:
    """Bounded planner: retrieve by current state, choose safe transition."""

    # Recovery-loop suppression bound (T11): an ineffective (state,
    # transition) pair is usable at most this many times before escalation.
    MAX_VISITS_PER_PAIR = 1

    def __init__(
        self,
        transitions: list[RecoveryTransition],
        *,
        max_visits_per_pair: int = MAX_VISITS_PER_PAIR,
    ) -> None:
        if max_visits_per_pair < 1:
            raise ValueError("max_visits_per_pair must be positive")
        self._t = transitions
        self._max_visits = max_visits_per_pair
        self._seen: set[tuple[str, str]] = set()
        self._visits: dict[tuple[str, str], int] = {}

    def _record_visit(self, state_id: str, transition_id: str) -> None:
        key = (state_id, transition_id)
        self._seen.add(key)
        self._visits[key] = self._visits.get(key, 0) + 1

    def _exhausted(self, state_id: str, transition_id: str) -> bool:
        return self._visits.get((state_id, transition_id), 0) >= self._max_visits

    def reset(self) -> None:
        """Clear loop-suppression history (e.g. after a fresh observation)."""
        self._seen.clear()
        self._visits.clear()

    def plan(self, *, goal_anchor: str, world: WorldState) -> RecoveryPlan:
        if world.anchor_id == goal_anchor and world.state_id == goal_anchor:
            return RecoveryPlan(steps=(), reason="already-at-anchor")
        cands = [t for t in self._t if t.from_state == world.state_id]
        # Failed-transition evidence stays scoped: drop already-tried pairs.
        fresh = [t for t in cands
                 if (world.state_id, t.transition_id) not in self._seen
                 and not self._exhausted(world.state_id, t.transition_id)]
        safe = [t for t in fresh if t.allowed and t.reversible and t.risk == "low"]
        if safe:
            chosen = sorted(safe, key=lambda t: t.transition_id)[0]
            self._record_visit(world.state_id, chosen.transition_id)
            return RecoveryPlan(steps=(chosen,), reason="bounded-reversible-step")
        if fresh:
            # Only unsafe options remain -> escalate without mutation.
            return RecoveryPlan(steps=(), escalate=True,
                                reason="no-safe-transition-escalate")
        if cands:
            return RecoveryPlan(steps=(), escalate=True,
                                reason="loop-suppressed-escalate")
        return RecoveryPlan(steps=(), escalate=True, reason="unknown-state-escalate")

    def note_failed(self, state_id: str, transition_id: str) -> None:
        self._record_visit(state_id, transition_id)
