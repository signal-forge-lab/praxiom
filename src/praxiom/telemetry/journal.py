"""Append-only per-run JSONL telemetry journal (D1=A, Phase A).

One ``RunJournal`` owns ``<state-root>/runs/<run_id>/events.jsonl``. It is a
pure observational record: it never mutates devices, never grants authority,
and is never a safety authority. Authoritative safety state remains Skill
lifecycle -> Coordinator durable attempt ledger -> Runtime revision check ->
Runtime execute; a journal failure raises instead of inventing success.

Event envelope (handoff A1 minimum):

.. code-block:: text

    schema_version, run_id, event_id, seq, ts_utc, monotonic_ns, event_type,
    phase, parent_event_id/correlation_id, execution_id, attempt_id, domain,
    behavior_id, skill_id, skill_version, revision_ref (fingerprinted),
    status, outcome/effect, duration_ms, policy_recommendation,
    actual_policy, fallback_reason, visual_hint, artifact_refs (metadata
    only), payload (bounded, allowlisted machine fields)

Not every event populates every optional field; ``None``/absent optional
fields are omitted from the serialized record.

Privacy model (fail-safe, enforced at serialization time):

- structural fields (``event_type``, ``phase``) must be allowlisted or the
  call fails loudly (``ValueError``) — events are never misfiled silently;
- content fields are token-shaped: only ``[A-Za-z0-9_.:@+-]{1,96}`` strings
  pass through; anything else (long text, payload fragments, identifiers,
  secrets) is replaced by a deterministic truncated SHA-256 fingerprint
  (``fp:`` + 16 hex), keeping correlation while dropping content;
- ``revision_ref`` is always a fingerprint of the opaque Runtime revision
  token — raw revision/element tokens are never journaled;
- ``payload`` accepts only allowlisted machine keys with bounded scalar /
  short-token / bounded-list / bounded-counter values; everything else is
  dropped and counted in ``payload.redacted_keys``;
- ``visual_hint`` and ``artifact_refs`` are metadata-only allowlists; no
  image/video bytes or paths ever enter the journal.

Durability model (crash/restart tolerance):

- canonical deterministic serialization: ``json.dumps(sort_keys=True,
  separators=(",", ":"), ensure_ascii=True, allow_nan=False)`` + ``\n``;
- append-only: existing bytes are never rewritten; each event is flushed and
  (by default) fsynced before ``seq`` advances, so a torn final record can
  only ever lose the event being written;
- on reopen, a torn tail (partial line without ``\n``) or malformed line is
  preserved on disk, skipped for interpretation, counted, and documented
  with a ``journal.recovered`` event; the sequence continues after the last
  valid record. A partial journal therefore stays inspectable;
- derived projections (``summary.json`` / ``learning_snapshot.json``) are
  written atomically on clean close and are caches only — recomputable from
  the journal at any time.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from praxiom.telemetry.context import RunContext, utc_now_iso

__all__ = [
    "ALLOWED_ARTIFACT_KEYS",
    "ALLOWED_EVENT_TYPES",
    "ALLOWED_OUTCOMES",
    "ALLOWED_PAYLOAD_KEYS",
    "ALLOWED_PHASES",
    "ALLOWED_STATUS",
    "ALLOWED_VISUAL_HINTS",
    "JOURNAL_SCHEMA_VERSION",
    "JournalClosedError",
    "JournalStats",
    "JournalWriteError",
    "RunJournal",
    "build_event",
    "fingerprint_revision",
    "sanitize_payload",
]

JOURNAL_SCHEMA_VERSION = 1

# Bounded payload limits (bytes/chars/items/entries).
MAX_PAYLOAD_BYTES = 4096
MAX_TOKEN_LENGTH = 96
MAX_LIST_ITEMS = 16
MAX_COUNTER_ENTRIES = 8
MAX_ARTIFACT_REFS = 8
MAX_INT_ABS = 10**15

FINGERPRINT_PREFIX = "fp:"
FINGERPRINT_HEX = 16

# Structural allowlists: unknown values fail loudly (caller bug).
ALLOWED_EVENT_TYPES = frozenset({
    "run.started", "run.completed", "journal.recovered",
    "runtime.status", "runtime.observe", "runtime.execute",
    "runtime.invalidate", "runtime.recover", "runtime.close",
    "execution.created", "execution.completed",
    "attempt.planned", "attempt.sent", "attempt.completed",
    "validation.performed", "policy.decision", "sequence.decision",
    "learning.recorded", "learning.snapshot", "artifacts.reserved",
})

ALLOWED_PHASES = frozenset({
    "run", "journal", "status", "observe", "execute", "invalidate",
    "recover", "preflight", "attempt", "validation", "recovery",
    "fallback", "policy", "learning", "sequence", "artifacts",
})

# Content allowlists: unknown values are dropped (fail-safe, counted where
# the envelope has a place for it) rather than misfiled.
ALLOWED_STATUS = frozenset({
    "created", "planned", "sent", "running", "succeeded", "failed",
    "unknown", "cancelled", "expired", "ok", "ready", "degraded",
})
ALLOWED_OUTCOMES = frozenset({"NONE", "PARTIAL", "UNKNOWN"})
ALLOWED_VISUAL_HINTS = frozenset({
    "post-action", "validation-mismatch", "recovery", "learning-change",
})

# Payload machine-field allowlist. Keys outside this set are dropped and
# counted; raw action payloads, screen text, bundle identifiers, device
# identifiers, secrets, and trust-token material have no allowlisted key.
ALLOWED_PAYLOAD_KEYS = frozenset({
    "error_code", "effect", "completed", "action_count", "action_kinds",
    "failed_action_index", "repaired", "revision_invalidated", "retry_safe",
    "replayed", "observe_mode", "element_count", "screen_width",
    "screen_height", "recommended_batch_size", "actual_batch_size",
    "confidence", "reason_code", "candidate_kind", "candidate_count",
    "recommended", "truncated_items", "redacted_keys", "torn_records",
    "malformed_records", "budget_ms", "detail", "counters",
})

# Artifact references are identifiers/metadata only (D4=A hooks); there is
# deliberately no path/bytes/URL key.
ALLOWED_ARTIFACT_KEYS = frozenset({"artifact_id", "kind", "status", "format"})


class JournalWriteError(RuntimeError):
    """A journal append/projection failed; no success may be inferred."""


class JournalClosedError(RuntimeError):
    """The journal is closed; events can no longer be appended."""


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_.:@+-]{1,%d}\Z" % MAX_TOKEN_LENGTH)


def _token_fullmatch(value: str) -> bool:
    return _TOKEN_PATTERN.fullmatch(value) is not None


def _fingerprint(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:FINGERPRINT_HEX]
    return FINGERPRINT_PREFIX + digest


def sanitize_token(value: Any) -> str | None:
    """Token-safe bounded string; anything else becomes a fingerprint.

    Deterministic: the same input always yields the same output, so
    correlation joins keep working while content cannot surface.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if _token_fullmatch(value):
        return value
    return _fingerprint(value)


def fingerprint_revision(value: str | None) -> str | None:
    """Opaque revision reference: fingerprint any non-``fp:`` token."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if value.startswith(FINGERPRINT_PREFIX) and len(value) == (
        len(FINGERPRINT_PREFIX) + FINGERPRINT_HEX
    ):
        hex_part = value[len(FINGERPRINT_PREFIX):]
        if all(c in "0123456789abcdef" for c in hex_part):
            return value
    return _fingerprint(value)


def _sanitize_scalar(value: Any) -> tuple[Any, bool]:
    """Return (bounded value, kept?) for one payload scalar."""
    if isinstance(value, bool):
        return value, True
    if isinstance(value, int):
        return (value, True) if abs(value) <= MAX_INT_ABS else (None, False)
    if isinstance(value, float):
        return (value, True) if math.isfinite(value) else (None, False)
    if isinstance(value, str):
        return sanitize_token(value), True
    return None, False


def sanitize_payload(payload: Any) -> dict[str, Any]:
    """Fail-safe bounded projection of a caller payload.

    Only allowlisted machine keys survive; values are type-checked and
    bounded (scalars, short token strings, <=16 scalar list items, one
    bounded ``counters`` mapping). Dropped keys/items are counted into
    ``redacted_keys`` / ``truncated_items`` instead of being written. A
    payload that is still over the byte bound after sanitization collapses
    to its redaction counters.
    """
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        return {"redacted_keys": 1}
    dropped = 0
    truncated = 0
    clean: dict[str, Any] = {}
    for raw_key, value in payload.items():
        key = raw_key if isinstance(raw_key, str) else str(raw_key)
        if key not in ALLOWED_PAYLOAD_KEYS or key in clean:
            dropped += 1
            continue
        if key == "counters":
            if not isinstance(value, dict):
                dropped += 1
                continue
            bounded: dict[str, int] = {}
            for ckey, cvalue in value.items():
                if len(bounded) >= MAX_COUNTER_ENTRIES:
                    dropped += 1
                    continue
                ckey_s = ckey if isinstance(ckey, str) else str(ckey)
                if not _token_fullmatch(ckey_s) or isinstance(cvalue, bool) \
                        or not isinstance(cvalue, int) \
                        or abs(cvalue) > MAX_INT_ABS:
                    dropped += 1
                    continue
                bounded[ckey_s] = cvalue
            clean[key] = bounded
            continue
        if isinstance(value, (list, tuple)):
            items: list[Any] = []
            for item in value:
                if len(items) >= MAX_LIST_ITEMS:
                    truncated += 1
                    continue
                bounded_item, kept = _sanitize_scalar(item)
                if kept:
                    items.append(bounded_item)
                else:
                    dropped += 1
            clean[key] = items
            continue
        bounded_value, kept = _sanitize_scalar(value)
        if kept:
            clean[key] = bounded_value
        else:
            dropped += 1
    if truncated:
        existing = clean.get("truncated_items")
        clean["truncated_items"] = truncated + (existing if isinstance(existing, int) else 0)
    if dropped:
        existing = clean.get("redacted_keys")
        clean["redacted_keys"] = dropped + (existing if isinstance(existing, int) else 0)
    if len(json.dumps(clean, sort_keys=True, ensure_ascii=True).encode("utf-8")) \
            > MAX_PAYLOAD_BYTES:
        total = dropped + len(clean)
        return {
            "redacted_keys": total,
            "truncated_items": clean.get("truncated_items", 0),
        }
    return clean


def _sanitize_artifact_refs(refs: Any) -> tuple[list[dict[str, Any]], int]:
    """Metadata-only artifact references; returns (clean refs, dropped count)."""
    if refs is None:
        return [], 0
    if not isinstance(refs, (list, tuple)):
        return [], 1
    clean: list[dict[str, Any]] = []
    dropped = 0
    for ref in refs:
        if len(clean) >= MAX_ARTIFACT_REFS:
            dropped += 1
            continue
        if not isinstance(ref, dict):
            dropped += 1
            continue
        entry: dict[str, Any] = {}
        for raw_key, value in ref.items():
            key = raw_key if isinstance(raw_key, str) else str(raw_key)
            if key not in ALLOWED_ARTIFACT_KEYS or key in entry:
                dropped += 1
                continue
            bounded_value, kept = _sanitize_scalar(value)
            if kept:
                entry[key] = bounded_value
            else:
                dropped += 1
        if entry:
            clean.append(entry)
    return clean, dropped


def build_event(
    *,
    run_id: str,
    seq: int,
    ts_utc: str,
    monotonic_ns: int,
    event_type: str,
    phase: str | None = None,
    parent_event_id: str | None = None,
    correlation_id: str | None = None,
    execution_id: str | None = None,
    attempt_id: str | None = None,
    domain: str | None = None,
    behavior_id: str | None = None,
    skill_id: str | None = None,
    skill_version: str | None = None,
    revision: str | None = None,
    revision_ref: str | None = None,
    status: str | None = None,
    outcome: str | None = None,
    duration_ms: float | None = None,
    policy_recommendation: str | None = None,
    actual_policy: str | None = None,
    fallback_reason: str | None = None,
    visual_hint: str | None = None,
    artifact_refs: list[dict[str, Any]] | tuple | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one privacy-safe, bounded, deterministic envelope record.

    Structural fields (``event_type``, ``phase``) fail loudly when not
    allowlisted; content fields are sanitized fail-safe (see module doc).
    Pass either ``revision`` (raw Runtime token; fingerprinted here) or a
    pre-fingerprinted ``revision_ref`` — never both.
    """
    if not isinstance(seq, int) or isinstance(seq, bool) or seq <= 0:
        raise ValueError("seq must be a positive int")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id required")
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"event_type not allowed: {event_type!r}")
    if phase is not None and phase not in ALLOWED_PHASES:
        raise ValueError(f"phase not allowed: {phase!r}")
    if revision is not None and revision_ref is not None:
        raise ValueError("pass revision or revision_ref, not both")

    event: dict[str, Any] = {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "run_id": sanitize_token(run_id),
        "event_id": f"evt-{seq:06d}",
        "seq": seq,
        "ts_utc": sanitize_token(ts_utc) or utc_now_iso(),
        "monotonic_ns": monotonic_ns if isinstance(monotonic_ns, int)
        and not isinstance(monotonic_ns, bool) else 0,
        "event_type": event_type,
        "payload": sanitize_payload(payload),
    }
    if phase is not None:
        event["phase"] = phase

    optional_token_fields = {
        "parent_event_id": parent_event_id,
        "correlation_id": correlation_id,
        "execution_id": execution_id,
        "attempt_id": attempt_id,
        "domain": domain,
        "behavior_id": behavior_id,
        "skill_id": skill_id,
        "skill_version": skill_version,
        "policy_recommendation": policy_recommendation,
        "actual_policy": actual_policy,
        "fallback_reason": fallback_reason,
    }
    for field, value in optional_token_fields.items():
        cleaned = sanitize_token(value)
        if cleaned is not None:
            event[field] = cleaned

    ref = fingerprint_revision(revision) if revision is not None \
        else fingerprint_revision(revision_ref)
    if ref is not None:
        event["revision_ref"] = ref

    if status is not None:
        if status in ALLOWED_STATUS:
            event["status"] = status
        else:
            event["payload"]["redacted_keys"] = \
                event["payload"].get("redacted_keys", 0) + 1
    if outcome is not None:
        if outcome in ALLOWED_OUTCOMES:
            event["outcome"] = outcome
        else:
            event["payload"]["redacted_keys"] = \
                event["payload"].get("redacted_keys", 0) + 1
    if duration_ms is not None:
        if isinstance(duration_ms, (int, float)) \
                and not isinstance(duration_ms, bool) \
                and math.isfinite(duration_ms) and 0 <= duration_ms <= MAX_INT_ABS:
            event["duration_ms"] = float(duration_ms)
        else:
            event["payload"]["redacted_keys"] = \
                event["payload"].get("redacted_keys", 0) + 1
    if visual_hint is not None:
        if visual_hint in ALLOWED_VISUAL_HINTS:
            event["visual_hint"] = visual_hint
        else:
            event["payload"]["redacted_keys"] = \
                event["payload"].get("redacted_keys", 0) + 1
    clean_refs, ref_dropped = _sanitize_artifact_refs(artifact_refs)
    if clean_refs:
        event["artifact_refs"] = clean_refs
    if ref_dropped:
        event["payload"]["redacted_keys"] = \
            event["payload"].get("redacted_keys", 0) + ref_dropped
    return event


def canonical_dumps(event: dict[str, Any]) -> str:
    """Deterministic one-line JSON serialization for the journal."""
    return json.dumps(
        event, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    )


@dataclass(frozen=True)
class JournalStats:
    """Integrity counters for one journal session."""

    records: int
    torn_records: int
    malformed_records: int


class RunJournal:
    """Append-only per-run JSONL journal (crash/restart tolerant).

    The journal file is the durable authority for the observational record;
    the in-memory list is a replay cache refreshed from disk on reopen, so
    summaries written after a restart cover pre-crash history too.
    """

    def __init__(
        self,
        ctx: RunContext,
        *,
        ts_fn: Callable[[], str] | None = None,
        mono_fn: Callable[[], int] | None = None,
        durable: bool = True,
    ) -> None:
        self._ctx = ctx
        self._ts_fn = ts_fn or utc_now_iso
        self._mono_fn = mono_fn or time.monotonic_ns
        self._durable = durable
        self._closed = False
        self._seq = 0
        self._events: list[dict[str, Any]] = []
        self._torn = 0
        self._malformed = 0
        self._fh: Any = None
        self._pending_newline = False
        ctx.run_dir.mkdir(parents=True, exist_ok=True)
        self._scan_existing()
        if self._torn or self._malformed:
            self.emit(
                "journal.recovered",
                phase="journal",
                payload={
                    "torn_records": self._torn,
                    "malformed_records": self._malformed,
                },
            )

    # --- recovery ---------------------------------------------------------

    def _scan_existing(self) -> None:
        path = self._ctx.events_path
        if not path.exists():
            return
        raw = path.read_bytes()
        if not raw:
            return
        lines = raw.split(b"\n")
        tail = lines.pop()  # bytes after the final newline (torn when non-empty)
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._torn += 1
                continue
            if (
                isinstance(record, dict)
                and isinstance(record.get("seq"), int)
                and not isinstance(record["seq"], bool)
                and record["seq"] > 0
                and isinstance(record.get("event_id"), str)
            ):
                self._events.append(record)
                self._seq = max(self._seq, record["seq"])
            else:
                self._malformed += 1
        if tail:
            # Preserve the torn bytes on disk (append-only); the next append
            # starts on a fresh line so both remain inspectable.
            self._torn += 1
            self._pending_newline = True

    # --- append ------------------------------------------------------------

    def emit(self, event_type: str, **fields: Any) -> dict[str, Any]:
        """Sanitize, serialize, durably append, and return one event.

        Raises ``JournalClosedError`` after close/abandon and
        ``JournalWriteError`` when the append fails; in the failure case the
        sequence does not advance, so a later retry (possibly after reopen)
        cannot tear the record ordering. A failed or partial write can never
        be interpreted as success by any caller.
        """
        if self._closed:
            raise JournalClosedError("journal is closed")
        seq = self._seq + 1
        event = build_event(
            run_id=self._ctx.run_id,
            seq=seq,
            ts_utc=self._ts_fn(),
            monotonic_ns=self._mono_fn(),
            event_type=event_type,
            **fields,
        )
        line = canonical_dumps(event).encode("utf-8") + b"\n"
        try:
            self._append(line)
        except OSError as exc:
            raise JournalWriteError(
                f"journal append failed: {exc.__class__.__name__}"
            ) from exc
        self._seq = seq
        self._events.append(event)
        return event

    def _append(self, data: bytes) -> None:
        """Single append path; overridable in tests to inject I/O faults."""
        try:
            if self._fh is None:
                self._fh = open(self._ctx.events_path, "ab")
            if self._pending_newline:
                self._fh.write(b"\n")
                self._pending_newline = False
            self._fh.write(data)
            self._fh.flush()
            if self._durable:
                os.fsync(self._fh.fileno())
        except OSError as exc:
            raise JournalWriteError(
                f"journal append failed: {exc.__class__.__name__}"
            ) from exc

    # --- inspection ---------------------------------------------------------

    @property
    def run_id(self) -> str:
        return self._ctx.run_id

    @property
    def stats(self) -> JournalStats:
        return JournalStats(
            records=len(self._events),
            torn_records=self._torn,
            malformed_records=self._malformed,
        )

    def events(self) -> tuple[dict[str, Any], ...]:
        """All valid events known to this session (disk-replayed + new)."""
        return tuple(self._events)

    # --- derived projections (caches, never authority) -----------------------

    def write_summary(self) -> dict[str, Any]:
        from praxiom.telemetry.summary import build_summary

        summary = build_summary(self._events, generated_utc=self._ts_fn())
        _atomic_write_json(self._ctx.summary_path, summary)
        return summary

    def write_learning_snapshot(self) -> dict[str, Any]:
        from praxiom.telemetry.summary import build_learning_snapshot

        snapshot = build_learning_snapshot(
            self._events, run_id=self._ctx.run_id, generated_utc=self._ts_fn()
        )
        _atomic_write_json(self._ctx.learning_snapshot_path, snapshot)
        return snapshot

    # --- lifecycle -----------------------------------------------------------

    def close(self) -> dict[str, Any]:
        """Flush/close the journal, then atomically write derived projections.

        The events file is closed first; only after a clean close are
        ``summary.json`` / ``learning_snapshot.json`` (pure caches) written.
        A projection write failure raises but never corrupts the journal and
        a later ``close()`` retries both derived projections. Idempotent;
        returns the summary projection.
        """
        from praxiom.telemetry.summary import build_learning_snapshot, build_summary

        summary = build_summary(self._events, generated_utc=self._ts_fn())
        snapshot = build_learning_snapshot(
            self._events, run_id=self._ctx.run_id, generated_utc=self._ts_fn()
        )
        if not self._closed and self._fh is not None:
            try:
                self._fh.flush()
                if self._durable:
                    os.fsync(self._fh.fileno())
                self._fh.close()
            except OSError as exc:
                raise JournalWriteError(
                    f"journal close failed: {exc.__class__.__name__}"
                ) from exc
            finally:
                self._fh = None
        self._closed = True
        try:
            _atomic_write_json(self._ctx.summary_path, summary)
            _atomic_write_json(self._ctx.learning_snapshot_path, snapshot)
        except OSError as exc:
            raise JournalWriteError(
                f"projection write failed: {exc.__class__.__name__}"
            ) from exc
        return summary

    def abandon(self) -> None:
        """Simulate a crash for tests: drop the handle without projections.

        Mirrors process death: appended events survive on disk; no summary
        is written; the file may end mid-line only if the OS lost the tail.
        Reopening the run journal via :meth:`RunContext.open_journal`
        recovers the history and continues the sequence.
        """
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            except OSError:
                pass
            finally:
                self._fh = None
        self._closed = True

    def __enter__(self) -> "RunJournal":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _atomic_write_json(path, obj: dict[str, Any]) -> None:
    """Write a derived cache atomically: temp file + replace."""
    tmp = path.with_name(path.name + ".tmp")
    data = canonical_dumps(obj).encode("utf-8") + b"\n"
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
    os.replace(tmp, path)
