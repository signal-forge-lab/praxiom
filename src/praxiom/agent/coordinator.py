"""R6-F Execution Coordinator v1.

Versioned ExecutionSpec -> Execution -> Attempt over an injected Runtime
port mirroring the six operations. Trusted mutation flows only through
observe() then execute(..., expected_revision=...). Deterministic tests
use the FakeRuntime seam in tests/fakes.py (never defined here: production
modules must not ship a test double).
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "ExecutionSpec", "Execution", "Attempt", "DeviceLeaseManager",
    "ExecutionCoordinator", "CancelledError", "DeadlineError",
    "LeaseBusyError", "SpecValidationError",
    "LEDGER_SCHEMA_VERSION", "EXECUTION_TERMINAL", "ATTEMPT_TERMINAL",
    "preflight_specs",
]

LEDGER_SCHEMA_VERSION = 1

# Freeze lifecycle mapping (T4): Execution pending -> running ->
# (succeeded | failed | cancelled | expired); Attempt planned -> sent ->
# (ok | failed | unknown-effect | cancelled | expired). The state strings
# below keep the Phase-B vocabulary ("succeeded"/"failed"/"unknown") which
# the deterministic matrix asserts; the terminal sets are the conformance
# surface for restart/cleanup/lease decisions.
EXECUTION_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "expired"})
ATTEMPT_TERMINAL = frozenset(
    {"succeeded", "failed", "unknown", "cancelled", "expired"})

ALLOWED_OPS = frozenset({"tap_point", "tap_element", "drag", "swipe",
                         "type_text", "home", "launch_app"})


class SpecValidationError(ValueError):
    pass


class LeaseBusyError(RuntimeError):
    pass


class CancelledError(RuntimeError):
    pass


class DeadlineError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class ExecutionSpec:
    namespace: str
    owner: str
    task_type: str
    task_version: int
    payload: dict[str, Any]
    revision: str
    deadline_ms: int | None = None
    spec_version: int = 1

    def validate(self, now_ms: int | None = None) -> None:
        if not self.namespace or not self.owner or not self.task_type:
            raise SpecValidationError("namespace/owner/task_type required")
        if not isinstance(self.task_version, int) or self.task_version < 1:
            raise SpecValidationError("task_version must be positive int")
        if not isinstance(self.revision, str) or not self.revision:
            raise SpecValidationError("revision required")
        op = self.payload.get("op")
        if op not in ALLOWED_OPS:
            raise SpecValidationError(f"unsupported op: {op!r}")
        if op == "tap_element" and not self.payload.get("ref"):
            raise SpecValidationError("tap_element requires revision-bound ref")
        if "raw_tap" in self.payload or "raw_swipe" in self.payload:
            raise SpecValidationError("raw non-revision-bound envelope rejected")
        if self.deadline_ms is not None and now_ms is not None:
            if now_ms >= self.deadline_ms:
                raise DeadlineError("spec already expired")


def preflight_specs(
    specs: list[ExecutionSpec], *, now_ms: int | None = None
) -> None:
    """Batch preflight: validate every spec before the first device effect.

    Whole-batch rejection makes zero device calls; callers (run_batch) invoke
    this before acquiring the mutation lease or sending any attempt.
    """
    if not specs:
        raise SpecValidationError("empty batch rejected")
    for spec in specs:
        spec.validate(now_ms=now_ms)


@dataclass(kw_only=True)
class Execution:
    execution_id: str
    spec: ExecutionSpec
    state: str = "created"
    attempt_ids: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class Attempt:
    attempt_id: str
    execution_id: str
    state: str  # running | succeeded | failed | unknown | cancelled | expired
    effect: str = "NONE"  # NONE | PARTIAL | UNKNOWN (mirrors ErrorEffect)
    evidence: dict[str, Any] = field(default_factory=dict)
    retry_safe: bool = False  # attempted effects are never retry_safe


class DeviceLeaseManager:
    """One trusted mutation owner per device (single-lane mutation)."""

    def __init__(self) -> None:
        self._held: dict[str, str] = {}

    def acquire(self, device_id: str, owner: str) -> None:
        if device_id in self._held:
            raise LeaseBusyError(f"lease busy: {device_id}")
        self._held[device_id] = owner

    def release(self, device_id: str, owner: str) -> None:
        if self._held.get(device_id) == owner:
            del self._held[device_id]

    def holder(self, device_id: str) -> str | None:
        return self._held.get(device_id)

    def release_all(self, owner: str) -> list[str]:
        """Release every lease held by *owner*; returns released device ids."""
        released = [d for d, o in self._held.items() if o == owner]
        for d in released:
            del self._held[d]
        return released


class ExecutionCoordinator:
    """Coordinates versioned specs over one Runtime port with lease."""

    def __init__(
        self,
        runtime: Any,
        leases: DeviceLeaseManager,
        *,
        ledger_path: Path | None = None,
        now_ms: Callable[[], int] | None = None,
        device_id: str = "device-0",
    ) -> None:
        self._rt = runtime
        self._leases = leases
        self._now = now_ms or (lambda: int(time.time() * 1000))
        self._device = device_id
        self._executions: dict[str, Execution] = {}
        self._attempts: dict[str, list[Attempt]] = {}
        self.cancelled = False
        self._closed = False
        self._held: list[tuple[str, str]] = []  # (device_id, owner) owned by us
        self._ledger_path = ledger_path
        self._db: sqlite3.Connection | None = None
        if ledger_path is not None:
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(ledger_path))
            # WAL-safe usage: torn write never invents a phantom success;
            # each attempt append commits atomically.
            try:
                self._db.execute("PRAGMA journal_mode=WAL")
            except sqlite3.Error:
                pass
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS attempts "
                "(attempt_id TEXT PRIMARY KEY, execution_id TEXT, spec_hash TEXT,"
                " state TEXT, effect TEXT, evidence_json TEXT, ts INTEGER,"
                " schema_version INTEGER, spec_version INTEGER, task_version INTEGER)"
            )
            self._db.commit()
            self._recover_incomplete_attempts()
            # Backfill columns when reopening a Phase-B ledger without them.
            cols = {r[1] for r in
                    self._db.execute("PRAGMA table_info(attempts)").fetchall()}
            for col, default in (("schema_version", LEDGER_SCHEMA_VERSION),
                                 ("spec_version", 1), ("task_version", 1)):
                if col not in cols:
                    self._db.execute(
                        f"ALTER TABLE attempts ADD COLUMN {col} INTEGER"
                    )
                    self._db.execute(
                        f"UPDATE attempts SET {col}=? WHERE {col} IS NULL",
                        (default,),
                    )
            self._db.commit()

    @property
    def ledger_schema_version(self) -> int | None:
        return LEDGER_SCHEMA_VERSION if self._db is not None else None

    def _record(self, att: Attempt, spec: ExecutionSpec) -> None:
        if self._db is None:
            return
        identity = self._db.execute(
            "SELECT execution_id,spec_hash FROM attempts WHERE attempt_id=?",
            (att.attempt_id,),
        ).fetchone()
        if identity is None:
            try:
                self._db.execute(
                    "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (att.attempt_id, att.execution_id, spec.task_type, att.state,
                     att.effect, json.dumps(att.evidence)[:4000], self._now(),
                     LEDGER_SCHEMA_VERSION, spec.spec_version, spec.task_version),
                )
            except sqlite3.IntegrityError:
                # Another writer may have won the primary-key race. Re-read
                # and validate identity instead of ever overwriting history.
                identity = self._db.execute(
                    "SELECT execution_id,spec_hash FROM attempts WHERE attempt_id=?",
                    (att.attempt_id,),
                ).fetchone()
        if identity is not None:
            if identity != (att.execution_id, spec.task_type):
                raise RuntimeError("ATTEMPT_ID_COLLISION")
            self._db.execute(
                "UPDATE attempts SET state=?,effect=?,evidence_json=?,ts=?,"
                "schema_version=?,spec_version=?,task_version=? WHERE attempt_id=?",
                (att.state, att.effect, json.dumps(att.evidence)[:4000], self._now(),
                 LEDGER_SCHEMA_VERSION, spec.spec_version, spec.task_version,
                 att.attempt_id),
            )
        self._db.commit()
        # Bounded cleanup: only terminal rows are eligible; non-terminal
        # history is never deleted silently.
        count = self._db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        if count > 1000:
            terminal = "', '".join(sorted(EXECUTION_TERMINAL | ATTEMPT_TERMINAL))
            self._db.execute(
                "DELETE FROM attempts WHERE state IN ('" + terminal + "')"
                " AND attempt_id NOT IN "
                "(SELECT attempt_id FROM attempts WHERE state IN ('" + terminal
                + "') ORDER BY ts DESC, rowid DESC LIMIT 1000)"
            )
            self._db.commit()

    def _recover_incomplete_attempts(self) -> None:
        """Fail closed after restart for work whose dispatch outcome is unknown.

        A durable ``planned``/``sent`` row proves that work was admitted but did
        not reach a terminal ledger state before the previous coordinator died.
        We cannot safely infer whether the device observed the mutation, so the
        attempt is recovered as UNKNOWN and is never replayable.
        """
        if self._db is None:
            return
        rows = self._db.execute(
            "SELECT attempt_id,evidence_json FROM attempts "
            "WHERE state IN ('planned','sent','running')"
        ).fetchall()
        for attempt_id, evj in rows:
            evidence = json.loads(evj) if evj else {}
            evidence.update({
                "effect": "UNKNOWN",
                "replayed": False,
                "retry_safe": False,
                "revision_invalidated": True,
                "crash_recovered": True,
            })
            self._db.execute(
                "UPDATE attempts SET state='unknown',effect='UNKNOWN',"
                "evidence_json=?,ts=? WHERE attempt_id=?",
                (json.dumps(evidence)[:4000], self._now(), attempt_id),
            )
        if rows:
            self._db.commit()

    def inspect(self, execution_id: str) -> list[Attempt]:
        if self._db is None:
            # Ledger-less coordinators still retain inspectable history in
            # memory; attempts are never silently dropped.
            return list(self._attempts.get(execution_id, []))
        rows = self._db.execute(
            "SELECT attempt_id,execution_id,state,effect,evidence_json FROM attempts"
            " WHERE execution_id=? ORDER BY ts, rowid",
            (execution_id,)).fetchall()
        out = []
        for aid, eid, state, effect, evj in rows:
            ev = json.loads(evj) if evj else {}
            out.append(Attempt(attempt_id=aid, execution_id=eid, state=state,
                               effect=effect, evidence=ev,
                               retry_safe=bool(ev.get("retry_safe", False))))
        return out

    def ledger_executions(self) -> list[str]:
        """Restart inspection: execution ids visible in the durable ledger."""
        if self._db is None:
            return sorted(self._executions)
        rows = self._db.execute(
            "SELECT DISTINCT execution_id FROM attempts ORDER BY execution_id"
        ).fetchall()
        return [r[0] for r in rows]

    def cancel(self) -> None:
        self.cancelled = True

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("COORDINATOR_CLOSED")

    def _guard(self, spec: ExecutionSpec) -> None:
        if self.cancelled:
            raise CancelledError("cancelled before mutation")
        if spec.deadline_ms is not None and self._now() >= spec.deadline_ms:
            raise DeadlineError("deadline expired before mutation")

    @staticmethod
    def _value(value: Any, default: str = "") -> str:
        raw = getattr(value, "value", value)
        if raw is None:
            return default
        return str(raw)

    def _new_attempt(self, spec: ExecutionSpec) -> tuple[Execution, Attempt]:
        eid = self._new_unique_id("exe")
        exe = Execution(execution_id=eid, spec=spec, state="running")
        self._executions[eid] = exe
        aid = self._new_unique_id("att")
        att = Attempt(attempt_id=aid, execution_id=eid, state="planned")
        exe.attempt_ids.append(aid)
        self._attempts.setdefault(eid, []).append(att)
        att.evidence = {
            "effect": "UNKNOWN",
            "replayed": False,
            "retry_safe": False,
            "revision_invalidated": True,
            "dispatch_state": "planned",
        }
        self._record(att, spec)
        return exe, att

    def _new_unique_id(self, prefix: str) -> str:
        """Generate an ID that is collision-free against memory and ledger.

        UUID4 provides the normal uniqueness mechanism, but correctness does
        not depend on probability: an observed collision is retried and a
        pathological/repeated collision fails closed before dispatch.
        """
        for _ in range(16):
            value = f"{prefix}-{uuid.uuid4().hex}"
            if prefix == "exe":
                exists = value in self._executions
                if not exists and self._db is not None:
                    exists = self._db.execute(
                        "SELECT 1 FROM attempts WHERE execution_id=? LIMIT 1",
                        (value,),
                    ).fetchone() is not None
            else:
                exists = any(
                    attempt.attempt_id == value
                    for attempts in self._attempts.values()
                    for attempt in attempts
                )
                if not exists and self._db is not None:
                    exists = self._db.execute(
                        "SELECT 1 FROM attempts WHERE attempt_id=? LIMIT 1",
                        (value,),
                    ).fetchone() is not None
            if not exists:
                return value
        kind = "EXECUTION" if prefix == "exe" else "ATTEMPT"
        raise RuntimeError(f"{kind}_ID_COLLISION")

    def _mark_sent(self, att: Attempt, spec: ExecutionSpec) -> None:
        """Durably record intent immediately before crossing Runtime dispatch."""
        att.state = "sent"
        att.effect = "UNKNOWN"
        att.retry_safe = False
        att.evidence = {
            "effect": "UNKNOWN",
            "replayed": False,
            "retry_safe": False,
            "revision_invalidated": True,
            "dispatch_state": "sent",
        }
        self._record(att, spec)

    def _finish_runtime_error(
        self,
        exe: Execution,
        att: Attempt,
        spec: ExecutionSpec,
        exc: BaseException,
    ) -> Attempt:
        # Only an explicit Runtime no-effect classification may be treated as
        # NONE. An unexpected port/transport exception can occur after a
        # mutation reached the device, so fail closed as UNKNOWN.
        effect = self._value(getattr(exc, "effect", None), "UNKNOWN")
        if effect not in {"NONE", "PARTIAL", "UNKNOWN"}:
            effect = "UNKNOWN"
        att.state = "unknown" if effect == "UNKNOWN" else "failed"
        att.effect = effect
        att.retry_safe = False  # attempted effects are never replayable
        code = getattr(exc, "code", None)
        evidence: dict[str, Any] = {
            "effect": effect,
            "replayed": False,
            "retry_safe": False,
            "revision_invalidated": bool(
                getattr(exc, "revision_invalidated", effect != "NONE")
            ),
        }
        if code is not None:
            evidence["error_code"] = self._value(code)
        completed = getattr(exc, "completed_actions", None)
        if isinstance(completed, int):
            evidence["completed"] = completed
        att.evidence = evidence
        exe.state = att.state
        self._record(att, spec)
        return att

    def _acquire_owned(self, owner: str) -> None:
        self._leases.acquire(self._device, owner)
        self._held.append((self._device, owner))

    def _release_owned(self, owner: str) -> None:
        self._leases.release(self._device, owner)
        try:
            self._held.remove((self._device, owner))
        except ValueError:
            pass

    def run(self, spec: ExecutionSpec, *, owner: str) -> Attempt:
        self._require_open()
        now = self._now()
        spec.validate(now_ms=now)
        self._guard(spec)
        self._acquire_owned(owner)
        try:
            exe, att = self._new_attempt(spec)
            self._guard(spec)  # re-check after wait/lease
            self._mark_sent(att, spec)
            try:
                res = self._rt.execute([spec.payload],
                                       expected_revision=spec.revision)
            except (CancelledError, DeadlineError):
                raise
            except Exception as exc:
                # Any Runtime-port failure is retained as a recorded attempt
                # (failed/unknown, never replayed); only coordinator-level
                # cancel/deadline propagate without an attempt record.
                return self._finish_runtime_error(exe, att, spec, exc)
            effect = res.get("effect", "NONE")
            if effect == "NONE":
                att.state = "succeeded"
            elif effect == "PARTIAL":
                att.state = "failed"
            else:
                att.state = "unknown"
            att.effect = effect
            # Failed/unknown effects are retained, never auto-replayed.
            att.retry_safe = False
            att.evidence = {"effect": effect, "completed": res.get("completed", 0),
                            "replayed": False, "retry_safe": False,
                            "revision_invalidated": True}
            exe.state = att.state
            self._record(att, spec)
            return att
        finally:
            self._release_owned(owner)

    def run_batch(self, specs: list[ExecutionSpec], *, owner: str) -> list[Attempt]:
        """Execute a batch with whole-batch preflight (zero-effect on reject).

        Every spec is validated and deadline/cancel-checked before the lease
        is acquired or the first mutation is sent. Single-lane: one lease is
        held for the whole batch; each attempt still releases/consumes its own
        revision binding via the Runtime seam.
        """
        self._require_open()
        now = self._now()
        preflight_specs(specs, now_ms=now)
        for spec in specs:
            self._guard(spec)
        self._acquire_owned(owner)
        attempts: list[Attempt] = []
        try:
            for spec in specs:
                self._guard(spec)  # expiry checked before every next mutation
                exe, att = self._new_attempt(spec)
                self._mark_sent(att, spec)
                try:
                    res = self._rt.execute([spec.payload],
                                           expected_revision=spec.revision)
                except (CancelledError, DeadlineError):
                    raise
                except Exception as exc:
                    finished = self._finish_runtime_error(exe, att, spec, exc)
                    attempts.append(finished)
                    # R7-05: an attempted/unknown effect invalidates the
                    # continuation path. Never send the next mutation before
                    # reconciliation/fresh observation.
                    if (finished.effect != "NONE"
                            or finished.evidence.get("error_code") == "STALE_REVISION"
                            or finished.evidence.get("revision_invalidated", False)):
                        break
                    continue
                effect = res.get("effect", "NONE")
                if effect == "NONE":
                    att.state = "succeeded"
                elif effect == "PARTIAL":
                    att.state = "failed"
                else:
                    att.state = "unknown"
                att.effect = effect
                att.retry_safe = False
                att.evidence = {
                    "effect": effect, "completed": res.get("completed", 0),
                    "replayed": False, "retry_safe": False,
                    "revision_invalidated": True}
                exe.state = att.state
                self._record(att, spec)
                attempts.append(att)
                if effect != "NONE":
                    # PARTIAL/UNKNOWN cannot be followed by another mutation
                    # in the same batch without reconciliation.
                    break
            return attempts
        finally:
            self._release_owned(owner)

    def run_sequence(self, specs: list[ExecutionSpec], *, owner: str) -> Attempt:
        """Execute one bounded multi-action sequence as ONE Runtime call (D3=A).

        Frozen Phase A sequence contract (design decision D3=A):

        - whole-sequence preflight: every spec is validated (shape, op,
          revision binding, deadline) before the lease is acquired and before
          any device effect is possible; any rejection raises
          ``SpecValidationError`` with zero device calls and zero ledger rows;
        - one accepted starting revision: all specs must carry exactly the
          same revision (``SpecValidationError`` otherwise), and exactly one
          Runtime ``execute([payload1, payload2, ...], expected_revision=R)``
          call is made for the whole sequence under one device lease;
        - the Runtime ``ActionExecutor`` remains the sole mutation authority
          and owns per-action ordered outcomes; this method never retries,
          continues, or replays anything;
        - outcome mapping mirrors ``run()``: effect ``NONE`` -> succeeded,
          ``PARTIAL`` -> failed, anything else -> unknown; a Runtime-port
          error (e.g. a stale revision rejected in Runtime preflight with
          zero device calls) is retained via the fail-closed error path and
          is never replayed;
        - one parent ``Execution`` plus one correlated ``Attempt`` carry the
          sequence evidence (``action_count`` and per-action kinds when the
          port reports them); certified per-spec ``run_batch()`` semantics
          are unchanged.

        Returns the sequence ``Attempt``; ``attempt.execution_id`` links the
        parent execution and ``inspect(execution_id)`` stays the
        restart-safe inspection path.
        """
        self._require_open()
        now = self._now()
        preflight_specs(specs, now_ms=now)
        lead = specs[0]
        if len({spec.revision for spec in specs}) != 1:
            raise SpecValidationError(
                "sequence requires exactly one shared revision")
        for spec in specs:
            self._guard(spec)
        self._acquire_owned(owner)
        try:
            exe, att = self._new_attempt(lead)
            for spec in specs:
                self._guard(spec)  # expiry re-checked before the single send
            self._mark_sent(att, lead)
            try:
                res = self._rt.execute([spec.payload for spec in specs],
                                       expected_revision=lead.revision)
            except (CancelledError, DeadlineError):
                raise
            except Exception as exc:
                # Stale/PARTIAL/UNKNOWN port errors are retained fail-closed:
                # no continuation, no retry, no replay (frozen D3=A).
                return self._finish_runtime_error(exe, att, lead, exc)
            if isinstance(res, dict):
                effect = res.get("effect", "NONE")
                completed = res.get("completed", 0)
                outcomes = res.get("outcomes") or ()
            else:
                effect = getattr(res, "effect", "NONE")
                completed = getattr(res, "completed_actions", 0)
                outcomes = getattr(res, "outcomes", None) or ()
            if effect == "NONE":
                att.state = "succeeded"
            elif effect == "PARTIAL":
                att.state = "failed"
            else:
                att.state = "unknown"
            att.effect = effect
            # Failed/unknown sequence effects are retained, never replayed;
            # the accepted revision is invalidated by the attempted mutation.
            att.retry_safe = False
            kinds = [
                (oc.get("kind") if isinstance(oc, dict)
                 else getattr(oc, "kind", None))
                for oc in outcomes
            ]
            att.evidence = {
                "effect": effect,
                "completed": completed if isinstance(completed, int) else 0,
                "action_count": len(specs),
                "action_kinds": [k for k in kinds if isinstance(k, str)][:16],
                "replayed": False,
                "retry_safe": False,
                "revision_invalidated": True,
            }
            exe.state = att.state
            self._record(att, lead)
            return att
        finally:
            self._release_owned(owner)

    def close(self) -> None:
        """Idempotent owned-resource close: release owned leases, close ledger.

        The Runtime remains the sole device authority and is never closed
        here; only resources this coordinator owns are released.
        """
        if self._closed:
            return
        self._closed = True
        for device_id, owner in list(self._held):
            self._leases.release(device_id, owner)
        self._held.clear()
        if self._db is not None:
            try:
                self._db.commit()
                self._db.close()
            finally:
                self._db = None

    async def run_async(
        self,
        spec: ExecutionSpec,
        *,
        owner: str,
        action_factory: Callable[[dict[str, Any]], Any],
    ) -> Attempt:
        """Run one spec against an async Runtime implementation.

        ``action_factory`` is supplied at the integration edge so this generic
        Agent module never imports device/runtime implementation types. The
        Runtime remains the sole mutation authority. A cancellation or
        deadline that fires after dispatch is conservatively retained as
        ``UNKNOWN`` and the Runtime revision is invalidated before the lease is
        released; no automatic replay is attempted.
        """
        now = self._now()
        self._require_open()
        spec.validate(now_ms=now)
        self._guard(spec)
        self._acquire_owned(owner)
        try:
            exe, att = self._new_attempt(spec)
            self._guard(spec)
            action = action_factory(dict(spec.payload))
            self._mark_sent(att, spec)
            try:
                call = self._rt.execute(
                    [action], expected_revision=spec.revision
                )
                if spec.deadline_ms is None:
                    result = await call
                else:
                    remaining_ms = spec.deadline_ms - self._now()
                    if remaining_ms <= 0:
                        raise DeadlineError("deadline expired before mutation")
                    result = await asyncio.wait_for(
                        call, timeout=max(0.001, remaining_ms / 1000.0)
                    )
            except asyncio.TimeoutError:
                try:
                    await asyncio.shield(
                        self._rt.invalidate("execution-deadline-after-dispatch")
                    )
                except Exception:
                    pass
                att.state = "unknown"
                att.effect = "UNKNOWN"
                att.retry_safe = False
                att.evidence = {
                    "effect": "UNKNOWN",
                    "error_code": "DEADLINE_DURING_EXECUTE",
                    "replayed": False,
                    "retry_safe": False,
                    "revision_invalidated": True,
                }
                exe.state = att.state
                self._record(att, spec)
                return att
            except asyncio.CancelledError:
                try:
                    await asyncio.shield(
                        self._rt.invalidate("execution-cancelled-after-dispatch")
                    )
                except Exception:
                    pass
                att.state = "unknown"
                att.effect = "UNKNOWN"
                att.retry_safe = False
                att.evidence = {
                    "effect": "UNKNOWN",
                    "error_code": "CANCELLED_DURING_EXECUTE",
                    "replayed": False,
                    "retry_safe": False,
                    "revision_invalidated": True,
                }
                exe.state = att.state
                self._record(att, spec)
                raise
            except Exception as exc:
                return self._finish_runtime_error(exe, att, spec, exc)

            completed = getattr(result, "completed_actions", None)
            invalidated = getattr(
                result, "accepted_revision_invalidated", True
            )
            att.state = "succeeded"
            att.effect = "NONE"
            att.retry_safe = False
            att.evidence = {
                "effect": "NONE",
                "completed": completed if isinstance(completed, int) else 1,
                "replayed": False,
                "retry_safe": False,
                "revision_invalidated": bool(invalidated),
            }
            exe.state = att.state
            self._record(att, spec)
            return att
        finally:
            self._release_owned(owner)
