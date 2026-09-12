"""R8-A Capability-need discovery (domain-neutral, traceable)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

__all__ = ["CapabilityNeed", "detect_need", "normalize_signature"]

EVIDENCE_MIN = 2
FAILURES_MIN = 3
SUMMARY_MAX = 280


@dataclass(frozen=True, kw_only=True)
class CapabilityNeed:
    need_id: str
    summary: str
    evidence_ids: tuple[str, ...]
    gap_kind: str  # "missing-capability"
    observed_failures: int
    created_at: int


def normalize_signature(raw: str) -> str:
    return " ".join(raw.strip().lower().split())


def detect_need(
    *,
    summary: str,
    evidence_ids: list[str],
    failure_signatures: list[str],
    failure_revisions: list[str],
    model_confidence: float | None = None,
    frequency: int | None = None,
    now_ms: int = 0,
) -> CapabilityNeed | None:
    """Detect a repeated capability gap. Returns None when not proven.

    Fail-closed rules: needs >=EVIDENCE_MIN distinct evidence ids, >=FAILURES_MIN
    failures with one normalized signature across >=2 revisions; one-off/stale
    never yields a need; confidence/frequency alone never yields a need.
    """
    _ = (model_confidence, frequency)  # explicitly never sufficient alone
    if not summary or not summary.strip() or len(summary) > SUMMARY_MAX:
        return None
    distinct_ev = tuple(dict.fromkeys(evidence_ids))
    if len(distinct_ev) < EVIDENCE_MIN:
        return None
    if len(failure_signatures) < FAILURES_MIN:
        return None
    sigs = [normalize_signature(s) for s in failure_signatures]
    if any(not s for s in sigs):
        return None
    if len(set(sigs)) != 1:
        return None  # distinct failures, not one repeated gap
    if len(set(failure_revisions)) < 2:
        return None  # one-off / single-revision stale state
    if sigs[0].startswith("stale-state:") or sigs[0].startswith("one-off:"):
        return None
    return CapabilityNeed(
        need_id=f"need-{uuid.uuid4().hex}",
        summary=" ".join(summary.strip().split()),
        evidence_ids=distinct_ev,
        gap_kind="missing-capability",
        observed_failures=len(failure_signatures),
        created_at=now_ms,
    )
