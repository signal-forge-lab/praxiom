"""Privacy-safe operation trace for Native iOS Runtime v0 (R3-06).

Minimal observability for R4, wired into the runtime's observe/execute/recover
paths without touching their effect semantics:

- one latency record per observe call, one per execute batch (batch duration
  plus the executor's per-action ``ActionOutcome`` durations on success), one
  per recover call, and one per invalidate call carrying only a Runtime-local
  keyed reason fingerprint — enough to compare observe/action/batch/recovery
  latency later and correlate why a revision was discarded without retaining
  the raw reason;
- machine-readable counters: operation invocation counts and error-code
  counts;
- a bounded history of records exposed through ``records`` / ``render()``.

Privacy (R2 contract 4.1 / fixture R2-A01): records are built exclusively
from allowlisted structured fields — operation name, durations, action kinds,
machine error codes, action indexes, counts, and keyed invalidate-reason
fingerprints. The bounded raw reason is validated by the runtime and then
discarded before trace recording. Raw action payloads, screen
text, revision/element tokens, device identifiers, pair records, secrets,
and exception messages have no path into a record, so a scan of the trace
output can never surface them. Status-like output of the runtime stays
privacy-safe for the same reason.
"""

import time
from collections import Counter, deque
from dataclasses import asdict, dataclass

from praxiom.ios_runtime.models import ActionOutcome, ErrorCode

__all__ = ["Trace", "TraceRecord"]

# ponytail: bounded history drops the oldest records; raise _MAX_RECORDS or
# stream to disk only if R4 proves it needs full fidelity.
_MAX_RECORDS = 256


@dataclass(frozen=True)
class TraceRecord:
    """One privacy-safe operation record: timing plus structured outcome only."""

    operation: str  # "observe" | "execute" | "recover" | "invalidate"
    duration_ms: float
    error_code: ErrorCode | None = None
    failed_action_index: int | None = None
    outcomes: tuple[ActionOutcome, ...] = ()
    # Runtime-local keyed fingerprint of the validated invalidate reason
    # (contract 4.4); set only on "invalidate" records. The raw reason is never
    # stored in TraceRecord and therefore cannot surface through render().
    detail: str | None = None


class Trace:
    """Operation latency records and lifecycle/error counters of one runtime.

    Exposed as ``runtime.trace`` — state projection, not an operation; the
    public surface stays exactly the six async operations. Records survive
    ``close()`` so post-close inspection (R3-08) still sees the whole run.
    """

    def __init__(self) -> None:
        self._records: deque[TraceRecord] = deque(maxlen=_MAX_RECORDS)
        self.operations: Counter[str] = Counter()
        self.errors: Counter[ErrorCode] = Counter()

    @staticmethod
    def start() -> float:
        """Capture a monotonic start stamp for one operation call."""
        return time.perf_counter()

    def record(
        self,
        operation: str,
        *,
        started: float,
        error_code: ErrorCode | None = None,
        failed_action_index: int | None = None,
        outcomes: tuple[ActionOutcome, ...] = (),
        detail: str | None = None,
    ) -> None:
        """Record one finished operation call (success or machine error)."""
        self.operations[operation] += 1
        if error_code is not None:
            self.errors[error_code] += 1
        self._records.append(
            TraceRecord(
                operation=operation,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error_code=error_code,
                failed_action_index=failed_action_index,
                outcomes=tuple(outcomes),
                detail=detail,
            )
        )

    @property
    def records(self) -> tuple[TraceRecord, ...]:
        """The bounded record history, oldest first."""
        return tuple(self._records)

    def render(self) -> dict:
        """Privacy-safe machine-readable projection (JSON-serializable)."""
        return {
            "counters": {
                "operations": dict(self.operations),
                "errors": {code.value: count for code, count in self.errors.items()},
            },
            "records": [asdict(record) for record in self._records],
        }
