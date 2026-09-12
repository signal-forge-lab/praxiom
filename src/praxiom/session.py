"""Phase A run session: the single integration composition layer.

This module is the one place where the already-landed Phase A lanes are
wired into a live run (the "one shared integration pass"):

- **D1=A durable run ledger + trace events (A1/A2):** every session owns a
  ``RunContext`` (external, configurable state root) with an append-only
  ``RunJournal``, and — when a Runtime port is supplied — constructs the
  ``ExecutionCoordinator`` with the run-scoped ``ledger_path`` so the
  durable safety attempt ledger is ON in normal live-run construction.
  Privacy-safe Runtime ``Trace`` records are drained into the journal via
  the telemetry bridges (watermarked, oldest first), never re-read from
  device state.
- **A3 automatic Experience extraction:** the session builds an
  ``ExperienceStore`` under the state root (cross-run, outside the per-run
  directory) and a recorder adapter that persists each episode extracted by
  ``SkillExecutor`` and journals one ``learning.recorded`` event.
- **A4 actual-versus-shadow adaptive decisions, live control OFF:** the
  session wraps a default-refusing ``ShadowAdvisor`` and journals one
  ``policy.decision`` event per recommendation carrying the actual
  decision, the shadow recommendation, reason, confidence, and fallback
  reason. Nothing here applies a recommendation; ``LiveOptimizationGate``
  stays default-OFF and the session never constructs an enabled one.
- **D3=A bounded sequences:** the session exposes ``execute_sequence``
  over ``SkillExecutor.execute_sequence`` -> ``ExecutionCoordinator.run_sequence``
  -> exactly one Runtime ``execute([...], expected_revision=R)`` call, and
  journals the ``sequence.decision`` (shadow recommended vs actual size)
  plus the parent execution/attempt evidence. Feature gate stays
  default-OFF (``sequence_enabled=False``) per the Phase A baseline rule.
- **D4=A metadata-only visual hooks:** timeline markers carry
  ``visual_hint`` values from the frozen vocabulary via
  ``praxiom.visual_hooks``; artifact references stay ``reserved``
  identifiers. No capture, no bytes, no paths.

Authority rules (unchanged by this wiring):

- mutation flows only Skill lifecycle -> Coordinator -> Runtime revision
  check -> Runtime execute; the session, journal, experience store, shadow
  advisor, and visual hints are observational and can never mutate device
  state, never bypass a gate, and never gain authority;
- journal/store failures raise (fail-loud): they can never invent success,
  never silently drop an attempt, and never widen authority;
- no SkillTrustToken, secret, device identifier, IP address, bundle id,
  screen text, or action payload is ever persisted here: the journal
  allowlist, the episode store's authority-key rejection, and the token
  fingerprint fallback enforce that by construction.

This module deliberately imports only public seams (no
``praxiom.ios_runtime`` import at all): the Runtime port arrives fully
constructed from the caller, and trace draining duck-types the documented
``runtime.trace.records`` projection.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from praxiom.adaptive.shadow import ShadowAdvisor
from praxiom.knowledge.experience_store import ExperienceStore
from praxiom.skill.executor import DEFAULT_SEQUENCE_LIMIT, SkillExecutor
from praxiom.skill.registry import SkillRegistry
from praxiom.telemetry.bridges import record_attempt, record_execution
from praxiom.telemetry.bridges import record_trace_record
from praxiom.telemetry.context import RunContext
from praxiom.telemetry.journal import ALLOWED_OUTCOMES, ALLOWED_STATUS, RunJournal
from praxiom.visual_hooks import hook as visual_hook

__all__ = [
    "EXPERIENCE_STORE_RELATIVE_PATH",
    "JournalExperienceRecorder",
    "JournalShadowAdvisor",
    "RunSession",
    "SEQUENCE_TERMINAL_HINTS",
]

# Cross-run Experience evidence lives under the state root (outside the
# per-run D1=A directory layout, which stays exactly as frozen): episodes
# must survive and be rebindable across runs, so they cannot be run-scoped.
EXPERIENCE_STORE_RELATIVE_PATH = Path("experience") / "episodes.jsonl"

# Attempt terminal states whose completed timeline marker carries the D4=A
# ``post-action`` visual hint (cancelled/expired never reached an effect).
SEQUENCE_TERMINAL_HINTS = frozenset({"succeeded", "failed", "unknown"})

_MAX_TRACE_WATERMARK = 1024


class JournalExperienceRecorder:
    """A3 sink for ``SkillExecutor.experience_recorder`` (durable + journaled).

    ``record`` persists the episode the executor extracted from a real
    outcome and journals one ``learning.recorded`` event. Persistence and
    journal failures raise: a lost evidence record is never silently
    accepted as recorded.
    """

    def __init__(self, store: ExperienceStore, journal: RunJournal) -> None:
        self._store = store
        self._journal = journal

    @property
    def store(self) -> ExperienceStore:
        return self._store

    def record(self, episode: Any) -> None:
        self._store.record(episode)  # authority-key/size rejection raises here
        effect = episode.effect if episode.effect in ALLOWED_OUTCOMES else None
        state = episode.state if episode.state in ALLOWED_STATUS else None
        self._journal.emit(
            "learning.recorded",
            phase="learning",
            execution_id=getattr(episode, "execution_id", None),
            attempt_id=getattr(episode, "attempt_id", None),
            domain="skill",
            behavior_id=episode.skill_id,
            skill_id=episode.skill_id,
            skill_version=str(episode.skill_version),
            revision=getattr(episode, "revision", None),
            status=state,
            outcome=effect,
            payload={
                "effect": effect or "UNKNOWN",
                # Phase A extracts evidence only; reuse eligibility is the
                # registry's fresh-token decision in a later run (A3), so
                # extraction never recommends reuse by itself.
                "candidate_kind": episode.macro_id or episode.path_id
                or "episode",
                "recommended": False,
            },
            **visual_hook("learning.recorded"),
        )


class JournalShadowAdvisor:
    """A4 sink for ``SkillExecutor.shadow_advisor`` (recorded, never applied).

    Delegates to the default-refusing ``ShadowAdvisor`` and journals one
    ``policy.decision`` event per recommendation with the actual decision,
    the shadow recommendation, reason, confidence, batch sizes, and the
    fallback reason when a shadow optimization would have been refused.
    """

    def __init__(self, inner: ShadowAdvisor, journal: RunJournal) -> None:
        self._inner = inner
        self._journal = journal

    def recommend(self, ctx: Any) -> Any:
        rec = self._inner.recommend(ctx)
        observation = rec.observation
        recommended_policy = (
            observation.method if observation is not None else None)
        batch_size = rec.batch.size if rec.batch is not None else None
        reduce = bool(rec.would_reduce_observe or rec.would_reduce_actions)
        payload: dict[str, Any] = {
            # Certified single-action actual: one action per Runtime call.
            "actual_batch_size": 1,
            "confidence": rec.confidence,
            "reason_code": rec.reason if isinstance(rec.reason, str) else "",
            "recommended": reduce,
        }
        if isinstance(batch_size, int) and not isinstance(batch_size, bool):
            payload["recommended_batch_size"] = batch_size
        self._journal.emit(
            "policy.decision",
            phase="policy",
            revision=ctx.revision or None,
            policy_recommendation=recommended_policy,
            actual_policy=rec.actual_decision,
            fallback_reason=rec.fallback_reason or None,
            payload=payload,
            **visual_hook("policy.decision", learned=reduce),
        )
        return rec

    @property
    def history(self) -> tuple[Any, ...]:
        return self._inner.history

    @property
    def last_recommendation(self) -> Any | None:
        return self._inner.last_recommendation


class RunSession:
    """One durable, observable, closed-loop run over the certified stack."""

    def __init__(
        self,
        *,
        context: RunContext,
        journal: RunJournal,
        coordinator: Any | None = None,
    ) -> None:
        self.context = context
        self.journal = journal
        self.coordinator = coordinator
        self.registry: SkillRegistry | None = None
        self.executor: SkillExecutor | None = None
        self.experience_store: ExperienceStore | None = None
        self.experience_recorder: JournalExperienceRecorder | None = None
        self.shadow_advisor: JournalShadowAdvisor | None = None
        self._trace_source: Any | None = None
        self._trace_seen: dict[int, Any] = {}
        self._last_event_id: str | None = None
        self._completion_emitted = False
        self._closed = False

    # --- construction -------------------------------------------------------

    @classmethod
    def start(
        cls,
        *,
        runtime: Any | None = None,
        registry: SkillRegistry | None = None,
        state_root: Path | str | None = None,
        run_id: str | None = None,
        now: Any | None = None,
        ts_fn: Any | None = None,
        mono_fn: Any | None = None,
        durable_journal: bool = True,
        sequence_enabled: bool = False,
        shadow_history_cap: int = 256,
        device_id: str = "device-0",
    ) -> "RunSession":
        """Open one run: journal, durable ledger, experience + shadow hooks.

        ``runtime`` is a fully constructed Runtime port (the caller keeps
        Runtime construction below the Runtime boundary). When supplied, the
        session constructs the ``ExecutionCoordinator`` with the run-scoped
        durable ``ledger_path`` (A2: the normal live-run construction
        enables the safety ledger) and a ``SkillExecutor`` wired with the
        A3 experience recorder and the A4 shadow advisor. The bounded
        sequence path is feature-gated OFF by default (frozen D2/D3 baseline
        rule); pass ``sequence_enabled=True`` only where separately
        accepted.
        """
        from praxiom.agent.coordinator import DeviceLeaseManager
        from praxiom.agent.coordinator import ExecutionCoordinator

        context = RunContext.create(
            state_root=state_root, run_id=run_id, now=now)
        journal = context.open_journal(
            durable=durable_journal, ts_fn=ts_fn, mono_fn=mono_fn)
        session = cls(context=context, journal=journal)
        session._note(journal.emit(
            "run.started",
            phase="run",
            status="running",
            payload={"detail": "phase-a-closed-loop"},
        ))
        coordinator = None
        if runtime is not None:
            # A2: durable safety/restart ledger is ON for the run, scoped to
            # the run directory; the journal stays observational only.
            coordinator = ExecutionCoordinator(
                runtime,
                DeviceLeaseManager(),
                ledger_path=context.ledger_path,
                device_id=device_id,
            )
            session.coordinator = coordinator
        session.registry = registry if registry is not None else SkillRegistry()
        store = ExperienceStore(
            context.state_root / EXPERIENCE_STORE_RELATIVE_PATH)
        session.experience_store = store
        session.experience_recorder = JournalExperienceRecorder(store, journal)
        session.shadow_advisor = JournalShadowAdvisor(
            ShadowAdvisor(max_history=shadow_history_cap), journal)
        if coordinator is not None:
            session.executor = SkillExecutor(
                coordinator=coordinator,
                registry=session.registry,
                # Frozen Phase A baseline: bounded-sequence live application
                # stays OFF unless separately accepted by the caller.
                sequence_enabled=bool(sequence_enabled),
                experience_recorder=session.experience_recorder,
                shadow_advisor=session.shadow_advisor,
            )
        return session

    # --- wiring helpers -------------------------------------------------------

    @property
    def ledger_path(self) -> Path:
        """Run-scoped Coordinator durable attempt-ledger path (A2)."""
        return self.context.ledger_path

    @property
    def run_id(self) -> str:
        return self.context.run_id

    def attach_executor(self, executor: Any) -> None:
        """Install the A3/A4 observational hooks on a caller-built executor."""
        executor.experience_recorder = self.experience_recorder
        executor.shadow_advisor = self.shadow_advisor
        self.executor = executor

    def attach_trace_source(self, runtime: Any) -> None:
        """Register the Runtime whose ``trace`` projection gets drained.

        Read-only: the projection attribute is state, not one of the six
        Runtime operations, and draining never calls the Runtime.
        """
        self._trace_source = runtime

    # --- closed-loop execution --------------------------------------------------

    def execute_skill(
        self,
        skill: Any,
        *,
        revision: str,
        op: str,
        human_gate_approval: Any | None = None,
        extra: dict[str, Any] | None = None,
        shadow_pending: int = 1,
    ) -> Any:
        """One certified single-action execution with full closed-loop evidence."""
        executor = self._require_executor()
        attempt = executor.execute(
            skill,
            revision=revision,
            op=op,
            human_gate_approval=human_gate_approval,
            extra=extra,
            shadow_pending=shadow_pending,
        )
        self.note_attempt(attempt, skill=skill, revision=revision)
        self.drain_trace()
        return attempt

    def note_attempt(
        self,
        attempt: Any,
        *,
        skill: Any | None = None,
        revision: str | None = None,
        spec: Any | None = None,
    ) -> dict[str, Any]:
        """Journal one completed attempt with skill/revision correlation."""
        spec_view = spec
        if spec_view is None and skill is not None:
            spec_view = SimpleNamespace(
                namespace="skill",
                task_type=getattr(skill, "skill_id", ""),
                task_version=int(getattr(skill, "version", 0) or 0),
                revision=revision or "",
            )
        hint = (
            "post-action"
            if getattr(attempt, "state", None) in SEQUENCE_TERMINAL_HINTS
            else None
        )
        event = record_attempt(
            self.journal,
            attempt,
            spec_view,
            parent_event_id=self._last_event_id,
            domain="skill",
            behavior_id=getattr(spec_view, "task_type", None)
            if spec_view is not None else None,
            visual_hint=hint,
        )
        return self._note(event)

    def execute_sequence(
        self,
        skill: Any,
        steps: list,
        *,
        revision: str,
        max_steps: int = DEFAULT_SEQUENCE_LIMIT,
    ):
        """Bounded sequence (D3=A) with shadow-vs-actual decision evidence.

        Delegates entirely to ``SkillExecutor.execute_sequence`` (whole
        preflight, gate, limits, size-one fallback, fail-closed effects) and
        journals the ``sequence.decision`` plus the parent execution and
        attempt evidence. The last shadow batch recommendation — when one
        was recorded earlier in the run — is retained as the recommended
        size; Phase A never applies it.
        """
        executor = self._require_executor()
        recommendation = (
            self.shadow_advisor.last_recommendation
            if self.shadow_advisor is not None else None)
        recommended = (
            recommendation.batch.size
            if recommendation is not None and recommendation.batch is not None
            else None
        )
        try:
            result = executor.execute_sequence(
                skill, steps, revision=revision, max_steps=max_steps)
        except Exception as exc:
            # Preflight/gate rejection or propagated port error: zero or
            # already-retained effects; journal the fail-closed reason and
            # re-raise unchanged. No continuation, no retry, no replay.
            self._note(self.journal.emit(
                "sequence.decision",
                phase="sequence",
                parent_event_id=self._last_event_id,
                skill_id=getattr(skill, "skill_id", None),
                skill_version=str(getattr(skill, "version", "") or ""),
                revision=revision,
                fallback_reason=str(exc),
                payload={"actual_batch_size": 0},
            ))
            raise
        payload: dict[str, Any] = {
            "actual_batch_size": int(result.executed_steps),
            "action_count": int(result.executed_steps),
            "counters": {"requested_steps": int(result.requested_steps)},
        }
        if isinstance(recommended, int) and not isinstance(recommended, bool):
            payload["recommended_batch_size"] = recommended
        self._note(self.journal.emit(
            "sequence.decision",
            phase="sequence",
            parent_event_id=self._last_event_id,
            skill_id=getattr(skill, "skill_id", None),
            skill_version=str(getattr(skill, "version", "") or ""),
            revision=revision,
            fallback_reason=result.fallback_reason,
            payload=payload,
        ))
        outcome = result.outcome
        state = getattr(outcome, "state", None)
        if isinstance(state, str) and state:  # coordinator-owned Attempt
            spec_view = SimpleNamespace(
                namespace="skill",
                task_type=getattr(skill, "skill_id", ""),
                task_version=int(getattr(skill, "version", 0) or 0),
                revision=revision,
            )
            self._note(record_execution(
                self.journal,
                SimpleNamespace(
                    execution_id=getattr(outcome, "execution_id", None),
                    state=state,
                ),
                spec_view,
                event_type="execution.completed",
                parent_event_id=self._last_event_id,
                domain="skill",
            ))
            self.note_attempt(outcome, spec=spec_view)
        self.drain_trace()
        return result

    # --- runtime trace draining (A2) ----------------------------------------

    def drain_trace(self, runtime: Any | None = None, **identity: Any) -> list:
        """Journal unseen privacy-safe Runtime trace records, oldest first."""
        source = runtime if runtime is not None else self._trace_source
        if source is None:
            return []
        trace = getattr(source, "trace", None)
        records = getattr(trace, "records", None) or ()
        emitted: list[dict[str, Any]] = []
        for record in records:
            key = id(record)
            if key in self._trace_seen:
                continue
            # Strong reference keeps ids unique for the lifetime of the run;
            # the Runtime trace history is bounded (<=256 records), so this
            # watermark stays bounded for any Phase A run.
            self._trace_seen[key] = record
            if len(self._trace_seen) > _MAX_TRACE_WATERMARK:
                self._trace_seen.clear()
            kwargs = dict(identity)
            if kwargs.get("visual_hint") is None and \
                    getattr(record, "operation", None) == "recover":
                kwargs["visual_hint"] = "recovery"
            emitted.append(self._note(
                record_trace_record(
                    self.journal, record,
                    parent_event_id=self._last_event_id,
                    **kwargs,
                )))
        return emitted

    # --- lifecycle -----------------------------------------------------------

    def close(self, *, status: str = "ok", reason_code: str | None = None) -> dict[str, Any]:
        """Finish the run: final trace sweep, run.completed, projections.

        The journal writes ``summary.json`` / ``learning_snapshot.json``
        (derived caches) on clean close; the coordinator releases only its
        own resources (leases + ledger handle), never the Runtime. A failed
        final journal/projection write remains retryable without duplicating
        ``run.completed``. Idempotent after a fully successful close.
        """
        if status not in {"ok", "failed", "cancelled"}:
            raise ValueError("run-close-status-invalid")
        if self._closed:
            return {"run_id": self.context.run_id, "already_closed": True}
        if not self._completion_emitted:
            self.drain_trace()
            payload = {"reason_code": reason_code} if reason_code else None
            self._note(self.journal.emit(
                "run.completed", phase="run", status=status, payload=payload))
            self._completion_emitted = True
        summary = self.journal.close()
        if self.coordinator is not None:
            self.coordinator.close()
        self._closed = True
        return summary

    # --- internals ------------------------------------------------------------

    def _require_executor(self) -> Any:
        if self.executor is None:
            raise RuntimeError(
                "session-has-no-executor (start() with a runtime port or "
                "attach_executor() first)")
        return self.executor

    def _note(self, event: dict[str, Any]) -> dict[str, Any]:
        self._last_event_id = event.get("event_id", self._last_event_id)
        return event
