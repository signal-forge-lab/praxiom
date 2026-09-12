"""Domain-neutral bridge from learned Human Teaching to Shadow context."""
from __future__ import annotations

from dataclasses import dataclass, replace

from praxiom.adaptive.shadow import ShadowContext

__all__ = ["TeachingInfluence", "apply_teaching_influence"]


@dataclass(frozen=True, kw_only=True)
class TeachingInfluence:
    teaching_ids: tuple[str, ...]
    confidence_cap: float | None = None
    force_full_observe: bool = False
    max_batch: int | None = None
    disable_reuse: bool = False


def apply_teaching_influence(
    ctx: ShadowContext,
    influence: TeachingInfluence,
    *,
    learned_ids: frozenset[str] | set[str],
) -> ShadowContext:
    """Apply only already-learned Teaching as generic Shadow constraints."""
    if not influence.teaching_ids:
        raise ValueError("teaching-influence-requires-evidence")
    if any(item not in learned_ids for item in influence.teaching_ids):
        raise ValueError("unlearned-teaching-cannot-influence-shadow")
    confidence = ctx.validated_confidence
    if influence.confidence_cap is not None:
        cap = float(influence.confidence_cap)
        if not 0.0 <= cap <= 1.0:
            raise ValueError("confidence-cap-out-of-range")
        confidence = min(confidence, cap)
    max_batch = ctx.max_batch
    if influence.max_batch is not None:
        if isinstance(influence.max_batch, bool) or influence.max_batch < 1:
            raise ValueError("max-batch-positive")
        max_batch = min(max_batch, int(influence.max_batch))
    return replace(
        ctx,
        validated_confidence=confidence,
        next_is_state_sensitive=(ctx.next_is_state_sensitive or influence.force_full_observe),
        max_batch=max_batch,
        macro_reuse_eligible=(False if influence.disable_reuse else ctx.macro_reuse_eligible),
        path_reuse_eligible=(False if influence.disable_reuse else ctx.path_reuse_eligible),
    )
