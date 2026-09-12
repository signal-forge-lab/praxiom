"""R7-04 Retrieval outcome feedback / stale decay (deterministic clock)."""
from __future__ import annotations

from praxiom.retrieval.store import KnowledgeStore

__all__ = ["record_outcome", "apply_decay"]

DECAY_PER_TICK = 0.01


def record_outcome(store: KnowledgeStore, kid: str, *, success: bool,
                   now_ts: int) -> None:
    """Update bounded reliability/recency evidence; never changes lifecycle."""
    item = store.get(kid)
    if item is None:
        return
    delta = 0.05 if success else -0.05
    # One event never disproves: clamp, lifecycle untouched.
    item.reliability = min(1.0, max(0.0, item.reliability + delta))
    item.last_used_ts = now_ts
    item.last_decay_ts = now_ts


def apply_decay(store: KnowledgeStore, *, now_ts: int, half_life_ticks: int = 100) -> None:
    for item in list(store._items.values()):
        interval = max(1, half_life_ticks)
        baseline = max(item.last_used_ts, item.last_decay_ts)
        age = max(0, now_ts - baseline)
        steps = age // interval
        if steps:
            item.reliability = max(0.0, item.reliability - steps * DECAY_PER_TICK)
            # Advance only by consumed whole intervals so repeated evaluation
            # at the same timestamp is idempotent while fractional age carries.
            item.last_decay_ts = baseline + steps * interval
