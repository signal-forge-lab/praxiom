"""R9 temporal/countdown modeling (injectable clock, fail-closed)."""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Countdown", "MonotonicClock", "remaining_ms"]


@dataclass
class MonotonicClock:
    now_ms: int = 0

    def set(self, value: int) -> int:
        if value < self.now_ms:
            raise ValueError("clock-must-not-move-backwards")
        self.now_ms = value
        return self.now_ms

    def advance(self, delta_ms: int) -> int:
        if delta_ms < 0:
            raise ValueError("clock-must-not-move-backwards")
        self.now_ms += delta_ms
        return self.now_ms


@dataclass(frozen=True, kw_only=True)
class Countdown:
    deadline_ms: int | None
    now_ms: int

    def remaining(self) -> int | None:
        if self.now_ms < 0 or (self.deadline_ms is not None and self.deadline_ms < 0):
            return 0
        if self.deadline_ms is None:
            return None
        return self.deadline_ms - self.now_ms

    def expired(self) -> bool:
        r = self.remaining()
        return r is not None and r <= 0


def remaining_ms(*, deadline_ms: int | None, now_ms: int) -> int | None:
    return Countdown(deadline_ms=deadline_ms, now_ms=now_ms).remaining()
