"""Shared Phase-B synthetic fixtures (privacy-safe, deterministic).

Factory vocabulary for the frozen record families. Every factory builds
the production dataclass from ``src/praxiom/...`` (single writer) with
synthetic, machine-readable values only:

- no raw screenshots, screen text, action payloads, credentials,
  identifiers, or conversation text — opaque refs/counters/hashes only;
- deterministic IDs via per-family counters (stable ordering, no clock);
- provenance always ``"synthetic-fixture"`` or an explicit synthetic tag.
"""

from __future__ import annotations

import itertools

from praxiom.agent.arbiter import ArbitrationResult, InterruptEvent
from praxiom.agent.coordinator import ExecutionSpec
from praxiom.agent.reasoning import ReasoningRoute
from praxiom.agent.recovery import RecoveryTransition, WorldState
from praxiom.knowledge.experience import ExperienceEpisode
from praxiom.knowledge.promotion import KnowledgeRecord
from praxiom.retrieval.store import KnowledgeItem
from praxiom.retrieval.validator import ValidationContext

__all__ = [
    "SYNTHETIC_PROVENANCE",
    "make_spec",
    "make_episode",
    "make_knowledge_record",
    "make_knowledge_item",
    "make_interrupt",
    "make_arbitration",
    "make_route",
    "make_world",
    "make_transition",
    "make_validation_context",
]

SYNTHETIC_PROVENANCE = "synthetic-fixture"

_counters = {name: itertools.count(1) for name in (
    "spec", "episode", "knowledge", "interrupt", "world", "transition")}


def _next(prefix: str) -> str:
    return f"{prefix}-{next(_counters[prefix]):04d}"


def make_spec(**overrides) -> ExecutionSpec:
    """Versioned ExecutionSpec bound to an explicit revision.

    Rejects raw non-revision-bound envelopes at ``validate()`` time;
    callers must supply a current ``revision`` from ``observe()``.
    """
    base = {
        "namespace": "synthetic",
        "owner": "fixture-owner",
        "task_type": "t.safe",
        "task_version": 1,
        "payload": {"op": "home"},
        "revision": "rev-synth-1",
    }
    base.update(overrides)
    return ExecutionSpec(**base)


def make_episode(**overrides) -> ExperienceEpisode:
    base = {
        "episode_id": _next("episode"),
        "transition": "synthetic-state->synthetic-anchor",
        "outcome": "ok",
        "provenance": SYNTHETIC_PROVENANCE,
        "execution_id": "exe-0001",
        "attempt_id": "att-0001",
        "revision": "rev-synth-1",
        "captured_at": 1_000,
    }
    base.update(overrides)
    return ExperienceEpisode(**base)


def make_knowledge_record(**overrides) -> KnowledgeRecord:
    base = {
        "kid": _next("knowledge"),
        "claim": "synthetic anchor claim",
        "supports": 0,
    }
    base.update(overrides)
    return KnowledgeRecord(**base)


def make_knowledge_item(**overrides) -> KnowledgeItem:
    base = {
        "kid": _next("knowledge"),
        "claim": "synthetic anchor claim",
        "state": "promoted",
        "reliability": 0.5,
    }
    base.update(overrides)
    return KnowledgeItem(**base)


def make_interrupt(**overrides) -> InterruptEvent:
    base = {
        "event_id": _next("interrupt"),
        "kind": "goal",
        "priority": 50,
    }
    base.update(overrides)
    return InterruptEvent(**base)


def make_arbitration(**overrides) -> ArbitrationResult:
    base: dict = {
        "selected_id": None,
        "deferred_ids": (),
        "rejected_ids": (),
        "reasons": {},
    }
    base.update(overrides)
    return ArbitrationResult(**base)


def make_route(**overrides) -> ReasoningRoute:
    base = {
        "tier": "deterministic",
        "reason": "deterministic:known-confident",
        "latency_ms": 0,
    }
    base.update(overrides)
    return ReasoningRoute(**base)


def make_world(**overrides) -> WorldState:
    base = {
        "anchor_id": "synthetic-anchor",
        "state_id": "synthetic-anchor",
        "revision": "rev-synth-1",
    }
    base.update(overrides)
    return WorldState(**base)


def make_transition(**overrides) -> RecoveryTransition:
    base = {
        "transition_id": _next("transition"),
        "from_state": "synthetic-off-goal",
        "to_state": "synthetic-anchor",
    }
    base.update(overrides)
    return RecoveryTransition(**base)


def make_validation_context(**overrides) -> ValidationContext:
    base = {
        "effect": "NONE",
        "expected_anchor": "synthetic-anchor",
        "observed_labels": frozenset({"synthetic-anchor"}),
        "confidence": 0.9,
    }
    base.update(overrides)
    return ValidationContext(**base)
