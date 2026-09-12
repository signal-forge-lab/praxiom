"""R9 adaptive bounded batching (whole-batch preflight + reconcile stops)."""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["BatchDecision", "decide_batch"]

MAX_BATCH_HARD = 32


@dataclass(frozen=True, kw_only=True)
class BatchDecision:
    size: int
    reason: str
    preflight: str  # "required"
    revision: str | None = None
    stop_on: tuple[str, ...] = ("PARTIAL", "UNKNOWN", "STALE_REVISION")


def decide_batch(*, pending: int, validated_confidence: float, revision: str,
                 state_sensitive: bool, risk: str, reversibility: str,
                 human_gate: bool, max_batch: int = 8) -> BatchDecision:
    if pending <= 0 or max_batch < 1 or max_batch > MAX_BATCH_HARD:
        return BatchDecision(size=0, reason="invalid-batch-rejected", preflight="required",
                             revision=revision)
    if not revision:
        return BatchDecision(size=1, reason="revision-unbound-fallback-single",
                             preflight="required", revision=None)
    if risk not in ("low", "medium", "high") or reversibility not in (
            "reversible", "compensable", "irreversible"):
        return BatchDecision(size=1, reason="malformed-risk-fallback-single",
                             preflight="required", revision=revision)
    if human_gate or risk != "low" or reversibility != "reversible" or state_sensitive:
        return BatchDecision(size=1, reason="risk-or-state-sensitive-fallback-single",
                             preflight="required", revision=revision)
    if not (0.0 <= validated_confidence <= 1.0):
        return BatchDecision(size=1, reason="untrusted-confidence-fallback-single",
                             preflight="required", revision=revision)
    if validated_confidence >= 0.8:
        size = min(pending, max_batch)
    elif validated_confidence >= 0.5:
        size = min(pending, max(1, max_batch // 2))
    else:
        size = 1
    return BatchDecision(size=size, reason="confidence-bounded-batch", preflight="required",
                         revision=revision)
