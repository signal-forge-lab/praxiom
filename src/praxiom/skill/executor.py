"""R8 Skill execution: ActiveSkill -> Coordinator -> Runtime (only path).

Phase A (frozen design decision D3=A) adds an explicit bounded multi-action
sequence path beside the certified single-action path:
``SkillExecutor.execute_sequence`` -> ``ExecutionCoordinator.run_sequence``
-> one Runtime ``execute([...], expected_revision=R)`` call. The sequence
path is feature-gated off by default, whole-sequence-preflighted before the
first effect, limited to low-risk reversible non-human-gated skills, bound
to exactly one accepted revision, and fails closed (no continuation, no
retry, no replay). The existing ``execute`` / coordinator ``run`` /
``run_batch`` semantics and the six-operation Runtime public surface are
unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from praxiom.skill.candidate import ActiveSkill, RUNTIME_OPS
from praxiom.skill.registry import HumanGateApproval, SkillRegistry

__all__ = [
    "SkillExecutor", "SkillExecutionError", "SequenceStep", "SequenceExecution",
    "MAX_HOOK_ERRORS",
]

# Bounded-sequence limits (frozen D3=A). The default soft bound mirrors the
# adaptive batching default; the hard bound mirrors the Runtime max-batch
# contract so the skill layer never admits a longer sequence than the
# mutation authority accepts.
DEFAULT_SEQUENCE_LIMIT = 8
MAX_SEQUENCE_LIMIT = 32

# Bounded retained count for observational hook failures (A3/A4): hook
# errors never alter the attempt, the lifecycle, or execution semantics.
MAX_HOOK_ERRORS = 32

STATE_SENSITIVE_FALLBACK_REASON = "state-sensitive-fallback-single"


class SkillExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class SequenceStep:
    """One planned mutation inside a bounded sequence.

    ``state_sensitive`` marks a step that must be planned against a fresh
    observation of the post-effect world. Any such step collapses the whole
    sequence to size 1: only the first (already revision-bound) step may
    run under the single accepted revision.
    """

    op: str
    extra: dict[str, Any] | None = None
    state_sensitive: bool = False


@dataclass(frozen=True, kw_only=True)
class SequenceExecution:
    """Skill-side sequence result: sizes/fallback plus coordinator evidence.

    ``outcome`` is the coordinator-owned ``run_sequence`` result (one parent
    execution plus correlated per-action evidence); it is carried through,
    never re-derived or replayed here. This wrapper retains only counts,
    the bound revision reference, and a machine fallback reason — no
    payloads, element refs, or trust material.
    """

    requested_steps: int
    executed_steps: int
    fallback_reason: str | None
    revision: str
    outcome: Any


@dataclass(kw_only=True)
class SkillExecutor:
    coordinator: Any
    registry: SkillRegistry
    owner: str = "skill-executor"
    # Phase A baseline rule: bounded-sequence live application stays OFF
    # until separately accepted (frozen D2/D3). Default False so existing
    # constructions never mutate sequence behavior.
    sequence_enabled: bool = False
    # Optional A3/A4 observational seams (lane L). Telemetry/learning are
    # advisory only: they never mutate device state and never bypass the
    # certified lifecycle -> Coordinator -> Runtime path. Hook failures are
    # retained in ``hook_errors`` and never change the returned attempt.
    experience_recorder: Any | None = None  # A3: .record(ExperienceEpisode)
    shadow_advisor: Any | None = None  # A4: .recommend(ShadowContext)
    hook_errors: list[str] = field(default_factory=list)

    def execute(self, skill: ActiveSkill, *, revision: str, op: str,
                human_gate_approval: HumanGateApproval | None = None,
                extra: dict[str, Any] | None = None,
                shadow_pending: int = 1):
        from praxiom.agent.coordinator import ExecutionSpec
        if not self.registry.is_executable(skill):
            raise SkillExecutionError("skill-not-registry-active")
        try:
            authority_ops, human_gate = self.registry.execution_policy(skill)
        except Exception as exc:
            raise SkillExecutionError("skill-policy-unavailable") from exc
        if op not in RUNTIME_OPS or op not in authority_ops:
            raise SkillExecutionError("op-not-authorized")
        if not revision:
            raise SkillExecutionError("revision-required")
        payload: dict[str, Any] = {"op": op}
        if extra:
            reserved = {"op", "revision", "expected_revision", "namespace",
                        "owner", "task_type", "task_version", "human_gate_approval"}
            hit = reserved.intersection(extra)
            if hit:
                raise SkillExecutionError(f"reserved-payload-key:{sorted(hit)[0]}")
            payload.update(extra)
        if payload.get("op") != op or payload["op"] not in authority_ops:
            raise SkillExecutionError("op-not-authorized-after-merge")
        # Consume the human capability only after all local validation has passed,
        # and bind it to the exact mutation + revision it approved.
        if human_gate:
            if not self.registry.consume_human_gate_approval(
                skill,
                human_gate_approval,
                revision=revision,
                payload=payload,
            ):
                raise SkillExecutionError("human-gate-approval-required")
        elif human_gate_approval is not None:
            raise SkillExecutionError("unexpected-human-gate-approval")
        spec = ExecutionSpec(namespace="skill", owner=self.owner, task_type=skill.skill_id,
                             task_version=int(skill.version),
                             payload=payload, revision=revision)
        attempt = self.coordinator.run(spec, owner=self.owner)
        self._post_run_evidence(skill, spec, attempt, shadow_pending=shadow_pending)
        return attempt

    def _post_run_evidence(
        self, skill: ActiveSkill, spec, attempt, *, shadow_pending: int = 1
    ) -> None:
        """A3/A4 observational hooks over the real execution outcome.

        Extracts one bounded ExperienceEpisode (A3) and one shadow
        recommendation (A4) from the completed attempt. These hooks are
        purely observational: any failure is retained in ``hook_errors`` and
        never raises, never alters the attempt, and never grants authority.
        """
        if self.experience_recorder is None and self.shadow_advisor is None:
            return
        import time
        from praxiom.adaptive.experience_bridge import (
            ExtractionContext, build_episode,
        )
        from praxiom.adaptive.shadow import ShadowContext
        captured_at = int(time.time() * 1000)
        if self.experience_recorder is not None:
            try:
                ctx = ExtractionContext(
                    skill_id=skill.skill_id,
                    skill_version=int(skill.version),
                    provenance=":".join(skill.provenance)[:128],
                    captured_at=captured_at,
                )
                self.experience_recorder.record(build_episode(spec, attempt, ctx))
            except Exception as exc:
                self._note_hook_error("experience", exc)
        if self.shadow_advisor is not None:
            try:
                evidence = attempt.evidence if isinstance(attempt.evidence, dict) else {}
                self.shadow_advisor.recommend(ShadowContext(
                    validated_confidence=float(skill.confidence),
                    revision_invalidated=bool(evidence.get("revision_invalidated", True)),
                    risk=str(skill.risk),
                    reversibility=str(skill.reversibility),
                    human_gate=bool(skill.human_gate),
                    pending=shadow_pending,
                    revision=spec.revision,
                    validator_failed=attempt.effect != "NONE",
                    macro_reuse_eligible=False,
                    path_reuse_eligible=False,
                ))
            except Exception as exc:
                self._note_hook_error("shadow", exc)

    def _note_hook_error(self, hook: str, exc: BaseException) -> None:
        self.hook_errors.append(f"{hook}:{type(exc).__name__}")
        if len(self.hook_errors) > MAX_HOOK_ERRORS:
            del self.hook_errors[: len(self.hook_errors) - MAX_HOOK_ERRORS]

    def execute_sequence(
        self,
        skill: ActiveSkill,
        steps: list[SequenceStep],
        *,
        revision: str,
        max_steps: int = DEFAULT_SEQUENCE_LIMIT,
    ) -> SequenceExecution:
        """Execute one bounded multi-action sequence under one revision.

        Frozen Phase A semantics (design decision D3=A):

        - whole-sequence preflight: registry authority, op authorization,
          payload merge, and spec shape are checked for *every* step before
          the single delegation, so any rejection makes zero device calls;
        - one accepted starting revision: every spec carries the same
          revision and exactly one ``coordinator.run_sequence`` call is
          made (one device lease, one Runtime ``execute`` call with one
          ``expected_revision`` for the whole sequence);
        - low-risk + reversible + non-human-gated skills only; anything
          else fails closed here and keeps using the certified
          single-action ``execute`` (human-gated skills keep their
          one-payload approval binding there);
        - any ``state_sensitive`` step collapses the sequence to size 1
          with a retained fallback reason;
        - fail-closed effects: a stale/PARTIAL/UNKNOWN coordinator error or
          outcome propagates unchanged. This method never continues the
          remainder, never retries, and never replays; callers must
          reconcile with a fresh observation before any further mutation.

        Refuses with ``sequence-not-enabled`` unless the executor was
        constructed with ``sequence_enabled=True`` (Phase A baseline gate).
        """
        from praxiom.agent.coordinator import ExecutionSpec, SpecValidationError
        if not self.sequence_enabled:
            raise SkillExecutionError("sequence-not-enabled")
        if not self.registry.is_executable(skill):
            raise SkillExecutionError("skill-not-registry-active")
        try:
            authority_ops, human_gate = self.registry.execution_policy(skill)
        except Exception as exc:
            raise SkillExecutionError("skill-policy-unavailable") from exc
        if not revision:
            raise SkillExecutionError("revision-required")
        if not steps:
            raise SkillExecutionError("sequence-empty")
        if not 1 <= max_steps <= MAX_SEQUENCE_LIMIT:
            raise SkillExecutionError("sequence-limit-invalid")
        if len(steps) > max_steps:
            raise SkillExecutionError("sequence-over-limit")
        # Registry-owned limits: sequences carry only low-risk, reversible,
        # non-human-gated mutations. Registry policy is authoritative even
        # if the caller-tampered skill snapshot disagrees.
        if human_gate or skill.human_gate:
            raise SkillExecutionError("sequence-human-gate-unsupported")
        if skill.risk != "low":
            raise SkillExecutionError("sequence-risk-not-low")
        if skill.reversibility != "reversible":
            raise SkillExecutionError("sequence-not-reversible")
        if not hasattr(self.coordinator, "run_sequence"):
            raise SkillExecutionError("sequence-coordinator-unavailable")
        specs: list[ExecutionSpec] = []
        for index, step in enumerate(steps):
            if not isinstance(step, SequenceStep):
                raise SkillExecutionError(f"sequence-step-invalid:{index}")
            if step.op not in RUNTIME_OPS or step.op not in authority_ops:
                raise SkillExecutionError("op-not-authorized")
            payload: dict[str, Any] = {"op": step.op}
            if step.extra:
                reserved = {"op", "revision", "expected_revision", "namespace",
                            "owner", "task_type", "task_version", "human_gate_approval"}
                hit = reserved.intersection(step.extra)
                if hit:
                    raise SkillExecutionError(f"reserved-payload-key:{sorted(hit)[0]}")
                payload.update(step.extra)
            if payload.get("op") != step.op or payload["op"] not in authority_ops:
                raise SkillExecutionError("op-not-authorized-after-merge")
            spec = ExecutionSpec(namespace="skill", owner=self.owner,
                                 task_type=skill.skill_id,
                                 task_version=int(skill.version),
                                 payload=payload, revision=revision)
            try:
                spec.validate()
            except SpecValidationError as exc:
                raise SkillExecutionError(f"sequence-step-invalid:{index}") from exc
            specs.append(spec)
        # Size-one fallback: a state-sensitive step must be replanned against
        # a fresh post-effect observation, so it can never share the single
        # accepted revision with earlier effects. Only the first step, which
        # the caller already planned against this revision, may run.
        fallback_reason: str | None = None
        if any(step.state_sensitive for step in steps):
            specs = specs[:1]
            fallback_reason = STATE_SENSITIVE_FALLBACK_REASON
        outcome = self.coordinator.run_sequence(specs, owner=self.owner)
        return SequenceExecution(
            requested_steps=len(steps),
            executed_steps=len(specs),
            fallback_reason=fallback_reason,
            revision=revision,
            outcome=outcome,
        )
