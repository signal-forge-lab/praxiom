"""R8-E Successful-procedure reuse (never blind replay)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["Procedure", "ReuseDecision", "reuse_decision"]

VALID_KNOWLEDGE = frozenset({"verified", "promoted"})


@dataclass(frozen=True, kw_only=True)
class Procedure:
    procedure_id: str
    effect: str  # NONE | PARTIAL | UNKNOWN (+ unrecognized fails closed)
    revision: str
    preconditions: tuple[str, ...]
    execution_id: str | None = None
    attempt_id: str | None = None
    experience_id: str | None = None
    superseded: bool = False
    revoked: bool = False
    expires_at: int | None = None


@dataclass(frozen=True)
class ReuseDecision:
    action: str  # reuse | reobserve | reject
    reason: str
    linkage: dict[str, Any]


def reuse_decision(
    proc: Procedure,
    *,
    current_revision: str,
    current_facts: frozenset[str],
    knowledge_state: str,
    now_ms: int = 0,
) -> ReuseDecision:
    link = {"execution_id": proc.execution_id, "attempt_id": proc.attempt_id,
            "experience_id": proc.experience_id, "procedure_id": proc.procedure_id}
    if proc.effect != "NONE":
        return ReuseDecision("reobserve", "unknown-partial-effect-requires-reobserve", link)
    if proc.revoked or proc.superseded:
        return ReuseDecision("reject", "lifecycle-invalid", link)
    if knowledge_state not in VALID_KNOWLEDGE:
        return ReuseDecision("reject", "knowledge-lifecycle-invalid", link)
    if proc.expires_at is not None and now_ms >= proc.expires_at:
        return ReuseDecision("reject", "procedure-expired", link)
    if proc.revision != current_revision:
        return ReuseDecision("reobserve", "stale-revision-requires-reobserve", link)
    if not set(proc.preconditions) <= set(current_facts):
        return ReuseDecision("reobserve", "preconditions-unproven-reobserve", link)
    return ReuseDecision("reuse", "preconditions-revision-lifecycle-valid", link)
