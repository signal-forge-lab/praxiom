"""Correlation primitives: Runtime Trace / Coordinator -> journal (A2).

Duck-typed readers only. This module intentionally imports neither
``praxiom.ios_runtime`` nor ``praxiom.agent``: it reads the already
privacy-safe Runtime ``Trace`` records and Coordinator attempts/executions
by attribute and maps them onto the journal envelope. It therefore

- never changes the Runtime public operation surface (six operations stay
  untouched; ``runtime.trace`` is a state projection, not an operation);
- never duplicates lifecycle authority (these are observational records of
  boundaries that already happened);
- correlates Runtime trace -> execution -> attempt -> domain behavior with
  ids, timestamps, and fingerprinted revision references instead of raw
  payload capture.

Production wiring (who calls these, when) is owned by the single
integration owner; this module only provides the primitives.
"""
from __future__ import annotations

from typing import Any

from praxiom.telemetry.journal import (
    ALLOWED_OUTCOMES,
    RunJournal,
)

__all__ = [
    "RUNTIME_TRACE_OPERATIONS",
    "record_attempt",
    "record_execution",
    "record_runtime_trace",
    "record_trace_record",
]

RUNTIME_TRACE_OPERATIONS = frozenset({
    "status", "observe", "execute", "invalidate", "recover", "close",
})

_TRACE_PHASES = {
    "status": "status",
    "observe": "observe",
    "execute": "execute",
    "invalidate": "invalidate",
    "recover": "recovery",
    "close": "run",
}

_ATTEMPT_EVENT_TYPES = {
    "planned": "attempt.planned",
    "sent": "attempt.sent",
    "succeeded": "attempt.completed",
    "failed": "attempt.completed",
    "unknown": "attempt.completed",
    "cancelled": "attempt.completed",
    "expired": "attempt.completed",
}

_ATTEMPT_STATES = frozenset(_ATTEMPT_EVENT_TYPES)

_ATTEMPT_EVIDENCE_KEYS = (
    "error_code", "completed", "replayed", "retry_safe",
    "revision_invalidated", "effect",
)


def _field(obj: Any, name: str) -> Any:
    """Read one attribute or mapping key without importing producer types."""
    if obj is None:
        return None
    value = getattr(obj, name, None)
    if value is None and isinstance(obj, dict):
        value = obj.get(name)
    return value


def record_trace_record(
    journal: RunJournal,
    record: Any,
    *,
    parent_event_id: str | None = None,
    correlation_id: str | None = None,
    revision: str | None = None,
    **identity: Any,
) -> dict[str, Any]:
    """Journal one Runtime ``TraceRecord`` as a ``runtime.<operation>`` event.

    ``record`` is duck-typed against the Runtime trace projection fields
    (``operation``, ``duration_ms``, ``error_code``, ``failed_action_index``,
    ``outcomes``, ``detail``); only machine fields survive the journal
    allowlist. ``identity`` kwargs (execution_id, attempt_id, skill_id, ...)
    pass through to the envelope for correlation.
    """
    operation = _field(record, "operation")
    if operation not in RUNTIME_TRACE_OPERATIONS:
        raise ValueError(f"unsupported trace operation: {operation!r}")
    phase = _TRACE_PHASES[operation]
    outcomes = _field(record, "outcomes") or ()
    kinds: list[str] = []
    for outcome in outcomes:
        kind = _field(outcome, "kind")
        if isinstance(kind, str):
            kinds.append(kind)
    payload: dict[str, Any] = {}
    error_code = _field(record, "error_code")
    if error_code is not None:
        payload["error_code"] = str(getattr(error_code, "value", error_code))
    failed_index = _field(record, "failed_action_index")
    if isinstance(failed_index, int):
        payload["failed_action_index"] = failed_index
    if outcomes:
        payload["action_count"] = len(outcomes)
        payload["action_kinds"] = kinds
        payload["completed"] = len(outcomes)
    detail = _field(record, "detail")
    if detail is not None:
        payload["detail"] = str(detail)
    return journal.emit(
        f"runtime.{operation}",
        phase=phase,
        parent_event_id=parent_event_id,
        correlation_id=correlation_id,
        revision=revision,
        duration_ms=_field(record, "duration_ms"),
        payload=payload,
        **identity,
    )


def record_runtime_trace(
    journal: RunJournal,
    trace: Any,
    **identity: Any,
) -> list[dict[str, Any]]:
    """Journal every record of a Runtime ``Trace`` projection, oldest first."""
    return [
        record_trace_record(journal, record, **identity)
        for record in (_field(trace, "records") or ())
    ]


def record_attempt(
    journal: RunJournal,
    attempt: Any,
    spec: Any | None = None,
    *,
    parent_event_id: str | None = None,
    correlation_id: str | None = None,
    domain: str | None = None,
    behavior_id: str | None = None,
    visual_hint: str | None = None,
) -> dict[str, Any]:
    """Journal one Coordinator ``Attempt`` with its identity correlation.

    ``attempt`` is duck-typed (``attempt_id``, ``execution_id``, ``state``,
    ``effect``, ``evidence``); ``spec`` optionally supplies the versioned
    identity (``namespace``, ``task_type``, ``task_version``, ``revision``).
    The attempt state maps onto the bounded ``attempt.*`` event types; the
    raw spec payload is never read. ``visual_hint`` is an optional
    metadata-only D4 marker (validated against the journal allowlist).
    """
    state = _field(attempt, "state")
    event_type = _ATTEMPT_EVENT_TYPES.get(state) if isinstance(state, str) else None
    if event_type is None:
        raise ValueError(f"unsupported attempt state: {state!r}")
    effect = _field(attempt, "effect")
    payload: dict[str, Any] = {}
    evidence = _field(attempt, "evidence")
    if isinstance(evidence, dict):
        for key in _ATTEMPT_EVIDENCE_KEYS:
            if key == "effect":
                continue  # envelope outcome field, not payload
            value = evidence.get(key)
            if value is not None:
                payload[key] = value
    spec_revision = _field(spec, "revision") if spec is not None else None
    return journal.emit(
        event_type,
        phase="attempt",
        parent_event_id=parent_event_id,
        correlation_id=correlation_id,
        execution_id=_field(attempt, "execution_id"),
        attempt_id=_field(attempt, "attempt_id"),
        domain=domain if domain is not None else (
            _field(spec, "namespace") if spec is not None else None),
        behavior_id=behavior_id,
        skill_id=_field(spec, "task_type") if spec is not None else None,
        skill_version=(
            str(_field(spec, "task_version")) if spec is not None else None),
        revision=spec_revision,
        status=state if isinstance(state, str) else None,
        outcome=effect if effect in ALLOWED_OUTCOMES else None,
        visual_hint=visual_hint,
        payload=payload,
    )


def record_execution(
    journal: RunJournal,
    execution: Any,
    spec: Any | None = None,
    *,
    event_type: str = "execution.created",
    parent_event_id: str | None = None,
    correlation_id: str | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    """Journal a parent execution boundary (e.g. one sequence execution)."""
    if event_type not in {"execution.created", "execution.completed"}:
        raise ValueError(f"unsupported execution event type: {event_type!r}")
    state = _field(execution, "state")
    return journal.emit(
        event_type,
        phase="sequence" if event_type == "execution.created" else "attempt",
        parent_event_id=parent_event_id,
        correlation_id=correlation_id,
        execution_id=_field(execution, "execution_id"),
        domain=domain if domain is not None else (
            _field(spec, "namespace") if spec is not None else None),
        skill_id=_field(spec, "task_type") if spec is not None else None,
        skill_version=(
            str(_field(spec, "task_version")) if spec is not None else None),
        revision=_field(spec, "revision") if spec is not None else None,
        status=state if isinstance(state, str) and state in {
            "created", "planned", "sent", "running", "succeeded", "failed",
            "unknown", "cancelled", "expired",
        } else None,
    )
