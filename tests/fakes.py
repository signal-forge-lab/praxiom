"""Shared Phase-B test seam: fake Runtime + deterministic clock (tests only).

Single-writer rule: production schemas live in ``src/praxiom/...`` and are
never redefined here. This module only re-exports the Runtime test double
and provides a deterministic clock helper so deadline/lease/retry tests
never depend on wall time.

All Agent effects flow via the coordinator to the Native Runtime; this
``FakeRuntime`` mirrors only the six-operation seam surface
(``observe`` / ``execute(expected_revision=...)`` / ``invalidate`` /
``recover`` / ``status`` / ``close``) with injected observations,
revisions, effects (including ``UNKNOWN``), latency-free steps, and
failure modes. It never exposes transport/WDA internals.
"""

from __future__ import annotations

from typing import Callable

from praxiom.agent.coordinator import DeviceLeaseManager
from praxiom.ios_runtime.models import (
    ErrorCode,
    ErrorEffect,
    ErrorPhase,
    RuntimeOperationError,
)

__all__ = ["DeviceLeaseManager", "FakeRuntime", "ManualClock"]


class FakeRuntime:
    """Deterministic in-memory Runtime port for tests.

    Mirrors observe() / execute(expected_revision) / invalidate() /
    recover() / status() / close() semantics: every attempted mutation
    invalidates the accepted revision; scripted outcomes drive failure tests.
    Lives here (tests only) per the R6/R7 plan freeze: production modules
    must not ship a test double. Never exposes transport/WDA internals.
    """

    def __init__(self) -> None:
        self.revision = "rev-0"
        self._counter = 0
        self.closed = False
        self.device_calls = 0
        self.script: list[str] = []  # "ok" | "fail" | "unknown"

    def observe(self) -> str:
        if self.closed:
            raise RuntimeError("RUNTIME_CLOSED")
        self._counter += 1
        self.revision = f"rev-{self._counter}"
        return self.revision

    def execute(self, actions: list[dict], *, expected_revision: str) -> dict:
        if self.closed:
            raise RuntimeError("RUNTIME_CLOSED")
        if expected_revision != self.revision:
            raise RuntimeOperationError(
                ErrorCode.STALE_REVISION,
                ErrorPhase.PREFLIGHT,
                ErrorEffect.NONE,
                retry_safe=True,
                revision_invalidated=False,
            )
        self.device_calls += 1
        mode = self.script.pop(0) if self.script else "ok"
        # Any attempted mutation invalidates the accepted revision.
        self._counter += 1
        self.revision = f"rev-{self._counter}-invalidated"
        if mode == "ok":
            return {"completed": len(actions), "effect": "NONE"}
        if mode == "fail":
            return {"completed": 0, "effect": "PARTIAL"}
        return {"completed": 0, "effect": "UNKNOWN"}

    def invalidate(self, reason: str) -> None:
        if not reason or not reason.strip():
            raise ValueError("INVALID_REQUEST")
        self._counter += 1
        self.revision = f"rev-{self._counter}-invalidated"

    def recover(self) -> bool:
        self._counter += 1
        self.revision = f"rev-{self._counter}-invalidated"
        return True

    def status(self) -> dict:
        return {"closed": self.closed, "revision": self.revision}

    def close(self) -> None:
        self.closed = True


class ManualClock:
    """Deterministic millisecond clock for deadline/lease tests.

    Starts at ``start_ms``; ``advance(ms)`` moves time forward only
    (fail-closed against time travel). ``as_fn()`` returns a zero-arg
    callable suitable for ``ExecutionCoordinator(now_ms=...)``.
    """

    def __init__(self, start_ms: int = 1_000) -> None:
        if start_ms < 0:
            raise ValueError("start_ms must be non-negative")
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    def advance(self, delta_ms: int) -> int:
        if delta_ms < 0:
            raise ValueError("clock cannot move backwards")
        self._now += delta_ms
        return self._now

    def as_fn(self) -> Callable[[], int]:
        return self.now_ms
