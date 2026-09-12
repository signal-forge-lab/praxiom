"""R9 selector/reliability + recovery feedback (evidence-only, no lifecycle leak)."""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SelectorStats", "record_selector", "RecoveryStats", "record_recovery"]


@dataclass(kw_only=True)
class SelectorStats:
    selector_id: str
    uses: int = 0
    hits: int = 0

    @property
    def hit_rate(self) -> float:
        return (self.hits / self.uses) if self.uses else 0.0


def record_selector(stats: SelectorStats, *, hit: bool) -> None:
    stats.uses += 1
    if hit:
        stats.hits += 1
    # reliability evidence only; lifecycle truth never leaks through feedback


@dataclass(kw_only=True)
class RecoveryStats:
    attempts: int = 0
    recovered: int = 0

    @property
    def recovery_rate(self) -> float:
        return (self.recovered / self.attempts) if self.attempts else 0.0


def record_recovery(stats: RecoveryStats, *, recovered: bool) -> None:
    stats.attempts += 1
    if recovered:
        stats.recovered += 1
