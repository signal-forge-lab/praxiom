"""Phase A lane S (A5, skill-side): bounded multi-action sequence path.

Deterministic acceptance for ``SkillExecutor.execute_sequence`` (frozen
design decision D3=A) while the coordinator-side ``run_sequence`` wiring
lands in its own lane:

- whole-sequence preflight before the first effect (zero device calls on
  any rejection);
- one accepted revision, one ``run_sequence`` delegation (one lease, one
  Runtime execute call) for the whole sequence;
- low-risk / reversible / non-human-gated limits fail closed;
- any state-sensitive step collapses the sequence to size 1 with a
  retained fallback reason;
- stale / PARTIAL / UNKNOWN outcomes stop, invalidate the revision, and
  are never continued or replayed;
- the certified single-action ``execute`` and coordinator ``run_batch``
  semantics are unchanged, and the path is feature-gated off by default
  (Phase A baseline rule).
"""
from __future__ import annotations

import pytest
from praxiom.agent.coordinator import (
    DeviceLeaseManager,
    ExecutionCoordinator,
    ExecutionSpec,
    preflight_specs,
)
from praxiom.ios_runtime.models import ErrorCode, RuntimeOperationError
from praxiom.skill.candidate import SkillCandidate
from praxiom.skill.executor import (
    DEFAULT_SEQUENCE_LIMIT,
    SkillExecutionError,
    SkillExecutor,
    SequenceStep,
)
from praxiom.skill.registry import SkillRegistry
from tests.fakes import FakeRuntime


def _cand(**kw):
    base = dict(skill_id="seq-1", version=1, inputs=("x",), outputs=("y",),
                preconditions=("revision-bound: rev-1", "fact-a"),
                postconditions=("done",), risk="low", reversibility="reversible",
                authority=frozenset({"tap_point", "swipe", "tap_element"}),
                provenance=("need-1",))
    base.update(kw)
    return SkillCandidate(**base)


def _active(registry: SkillRegistry, candidate: SkillCandidate):
    registry.register(candidate)
    registry.validate(candidate.skill_id, candidate.version,
                      evidence_ids=("e1", "e2"))
    registry.record_success(candidate.skill_id, candidate.version,
                            revision="r1", evidence_id="s1")
    registry.record_success(candidate.skill_id, candidate.version,
                            revision="r2", evidence_id="s2")
    return registry.activate(candidate.skill_id, candidate.version,
                             confidence=0.9, evidence_id="activate")


class _UnknownEffectError(RuntimeError):
    """Stand-in for a Runtime-port UNKNOWN-effect dispatch exception."""

    effect = "UNKNOWN"
    code = "EFFECT_UNKNOWN"


class FakeSequenceCoordinator:
    """Test double for the coordinator lane's run_sequence seam.

    Records every delegation (so zero-call preflight assertions are exact)
    and either returns a scripted outcome or raises a scripted error. It
    never touches a Runtime itself; device-level contract coverage uses
    ContractSequenceCoordinator below.
    """

    def __init__(self, outcome=None, error: Exception | None = None):
        self.calls: list[tuple[list[ExecutionSpec], str]] = []
        self.outcome = outcome
        self.error = error

    def run_sequence(self, specs, *, owner):
        self.calls.append((list(specs), owner))
        if self.error is not None:
            raise self.error
        return self.outcome


class ContractSequenceCoordinator:
    """Minimal stand-in honoring the frozen run_sequence contract:

    whole-sequence preflight, one device lease, and exactly one Runtime
    ``execute([...], expected_revision=R)`` call for all payloads.
    """

    def __init__(self, rt, leases: DeviceLeaseManager, device_id: str = "device-0"):
        self._rt = rt
        self._leases = leases
        self._device = device_id
        self.calls: list[list[ExecutionSpec]] = []

    def run_sequence(self, specs, *, owner):
        specs = list(specs)
        preflight_specs(specs)
        self.calls.append(specs)
        self._leases.acquire(self._device, owner)
        try:
            revisions = {spec.revision for spec in specs}
            assert len(revisions) == 1, "sequence must carry one revision"
            return self._rt.execute([spec.payload for spec in specs],
                                    expected_revision=specs[0].revision)
        finally:
            self._leases.release(self._device, owner)


def _steps(*ops) -> list[SequenceStep]:
    return [SequenceStep(op=op) for op in ops]


def _enabled_executor(coordinator) -> SkillExecutor:
    return SkillExecutor(coordinator=coordinator, registry=SkillRegistry(),
                         sequence_enabled=True)


# --- feature gate + single-action/run_batch preservation -----------------------


def test_a5_gate_off_by_default_and_single_action_unchanged():
    rt = FakeRuntime()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coord, registry=registry)
    skill = _active(registry, _cand())
    revision = rt.observe()

    # Default construction keeps the certified single-action path and never
    # exposes live sequence application (Phase A baseline rule).
    attempt = executor.execute(skill, revision=revision, op="tap_point")
    assert attempt.state == "succeeded"
    assert rt.device_calls == 1
    with pytest.raises(SkillExecutionError) as err:
        executor.execute_sequence(skill, _steps("tap_point", "swipe"),
                                  revision=rt.observe())
    assert "sequence-not-enabled" in str(err.value)
    assert rt.device_calls == 1


def test_a5_enabled_gate_leaves_single_action_and_run_batch_untouched():
    rt = FakeRuntime()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coord, registry=registry,
                             sequence_enabled=True)
    skill = _active(registry, _cand())

    attempt = executor.execute(skill, revision=rt.observe(), op="tap_point")
    assert attempt.state == "succeeded" and rt.device_calls == 1
    # Stale single-action replay still fails closed exactly as certified.
    stale = executor.execute(skill, revision="bogus-stale", op="tap_point")
    assert stale.state == "failed"
    assert stale.evidence["error_code"] == "STALE_REVISION"
    assert rt.device_calls == 1
    # run_batch keeps its certified per-spec Runtime-call semantics: the
    # first mutation invalidates the shared revision, so the second spec
    # stops the batch with a stale failure instead of continuing.
    revision = rt.observe()
    batch = coord.run_batch(
        [ExecutionSpec(namespace="skill", owner="skill-executor",
                       task_type=skill.skill_id, task_version=1,
                       payload={"op": "tap_point"}, revision=revision),
         ExecutionSpec(namespace="skill", owner="skill-executor",
                       task_type=skill.skill_id, task_version=1,
                       payload={"op": "swipe"}, revision=revision)],
        owner="skill-executor")
    assert len(batch) == 2
    assert [a.state for a in batch] == ["succeeded", "failed"]
    # 1 single-action call + 1 first-spec batch call; the stale second spec
    # is rejected by the Runtime revision check and makes zero device calls.
    assert rt.device_calls == 2


# --- whole-sequence preflight: zero delegations on any rejection ---------------


def test_a5_whole_sequence_preflight_rejects_before_any_dispatch():
    coord = FakeSequenceCoordinator(outcome=[])
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand())

    rejections = [
        (lambda: executor.execute_sequence(skill, [], revision="rev-1"),
         "sequence-empty"),
        (lambda: executor.execute_sequence(
            skill, _steps("tap_point") * (DEFAULT_SEQUENCE_LIMIT + 1),
            revision="rev-1"), "sequence-over-limit"),
        (lambda: executor.execute_sequence(skill, _steps("tap_point"),
                                           revision="rev-1", max_steps=0),
         "sequence-limit-invalid"),
        (lambda: executor.execute_sequence(skill, _steps("tap_point"),
                                           revision="rev-1", max_steps=33),
         "sequence-limit-invalid"),
        (lambda: executor.execute_sequence(skill, _steps("wipe"),
                                           revision="rev-1"),
         "op-not-authorized"),
        (lambda: executor.execute_sequence(skill, _steps("tap_point", "launch_app"),
                                           revision="rev-1"),
         "op-not-authorized"),
        (lambda: executor.execute_sequence(
            skill, [SequenceStep(op="tap_point", extra={"owner": "x"})],
            revision="rev-1"), "reserved-payload-key:owner"),
        (lambda: executor.execute_sequence(
            skill, [SequenceStep(op="tap_element")], revision="rev-1"),
         "sequence-step-invalid:0"),
        (lambda: executor.execute_sequence(
            skill, [SequenceStep(op="tap_point"),
                    SequenceStep(op="tap_element")], revision="rev-1"),
         "sequence-step-invalid:1"),
        (lambda: executor.execute_sequence(
            skill, [SequenceStep(op="tap_point"), ("swipe",)], revision="rev-1"),
         "sequence-step-invalid:1"),
        (lambda: executor.execute_sequence(skill, _steps("tap_point"),
                                           revision=""),
         "revision-required"),
    ]
    for action, code in rejections:
        with pytest.raises(SkillExecutionError) as err:
            action()
        assert code in str(err.value), (code, str(err.value))
    # Every rejection happened before the single delegation: zero calls.
    assert coord.calls == []


def test_a5_registry_authority_required_before_sequence():
    coord = FakeSequenceCoordinator(outcome=[])
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand())
    executor.registry.revoke(skill.skill_id, 1, evidence_id="rollback")
    with pytest.raises(SkillExecutionError) as err:
        executor.execute_sequence(skill, _steps("tap_point"), revision="rev-1")
    assert "skill-not-registry-active" in str(err.value)
    assert coord.calls == []


# --- low-risk / reversible / non-human-gated limits -----------------------------


@pytest.mark.parametrize("candidate,code", [
    (_cand(skill_id="hg", risk="high", reversibility="irreversible",
           human_gate=True), "sequence-human-gate-unsupported"),
    (_cand(skill_id="risky", risk="medium"), "sequence-risk-not-low"),
    (_cand(skill_id="irrev", reversibility="compensable"),
     "sequence-not-reversible"),
])
def test_a5_sequence_limits_fail_closed(candidate, code):
    coord = FakeSequenceCoordinator(outcome=[])
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, candidate)
    with pytest.raises(SkillExecutionError) as err:
        executor.execute_sequence(skill, _steps("tap_point"), revision="rev-1")
    assert code in str(err.value)
    assert coord.calls == []


def test_a5_registry_owned_human_gate_beats_tampered_snapshot():
    coord = FakeSequenceCoordinator(outcome=[])
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand(skill_id="hg2", risk="high",
                                             reversibility="irreversible",
                                             human_gate=True))
    object.__setattr__(skill, "human_gate", False)
    with pytest.raises(SkillExecutionError) as err:
        executor.execute_sequence(skill, _steps("tap_point"), revision="rev-1")
    assert "sequence-human-gate-unsupported" in str(err.value)
    assert coord.calls == []


def test_a5_tampered_human_gate_snapshot_also_refused():
    coord = FakeSequenceCoordinator(outcome=[])
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand(skill_id="tampered"))
    object.__setattr__(skill, "human_gate", True)
    with pytest.raises(SkillExecutionError) as err:
        executor.execute_sequence(skill, _steps("tap_point"), revision="rev-1")
    assert "sequence-human-gate-unsupported" in str(err.value)
    assert coord.calls == []


# --- one revision, one delegation (one lease, one Runtime execute call) ---------


def test_a5_one_delegation_one_revision_for_whole_sequence():
    outcome = {"effect": "NONE", "completed": 3}
    coord = FakeSequenceCoordinator(outcome=outcome)
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand())
    steps = [SequenceStep(op="tap_point", extra={"x": 1}),
             SequenceStep(op="swipe"),
             SequenceStep(op="tap_point")]
    result = executor.execute_sequence(skill, steps, revision="rev-7")
    assert len(coord.calls) == 1
    specs, owner = coord.calls[0]
    assert owner == "skill-executor"
    assert [s.payload["op"] for s in specs] == ["tap_point", "swipe", "tap_point"]
    assert {s.revision for s in specs} == {"rev-7"}
    assert all(s.namespace == "skill" and s.task_type == skill.skill_id
               and s.task_version == 1 for s in specs)
    assert result.requested_steps == 3 and result.executed_steps == 3
    assert result.fallback_reason is None
    assert result.revision == "rev-7" and result.outcome is outcome


def test_a5_contract_one_lease_one_runtime_call_for_n_actions():
    rt = FakeRuntime()
    leases = DeviceLeaseManager()
    coord = ContractSequenceCoordinator(rt, leases)
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand())
    revision = rt.observe()
    result = executor.execute_sequence(
        skill, _steps("tap_point", "swipe", "tap_point"), revision=revision)
    assert rt.device_calls == 1
    assert result.outcome == {"completed": 3, "effect": "NONE"}
    assert result.executed_steps == 3
    assert leases.holder("device-0") is None  # lease released after sequence
    assert len(coord.calls) == 1


# --- size-one state-sensitive fallback ------------------------------------------


@pytest.mark.parametrize("steps,expected_ops", [
    ([SequenceStep(op="tap_point", state_sensitive=True),
      SequenceStep(op="swipe")], ["tap_point"]),
    ([SequenceStep(op="tap_point"),
      SequenceStep(op="swipe", state_sensitive=True)], ["tap_point"]),
])
def test_a5_state_sensitive_falls_back_to_size_one(steps, expected_ops):
    coord = FakeSequenceCoordinator(outcome={"effect": "NONE", "completed": 1})
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand())
    result = executor.execute_sequence(skill, steps, revision="rev-1")
    assert result.requested_steps == 2 and result.executed_steps == 1
    assert result.fallback_reason == "state-sensitive-fallback-single"
    specs, _ = coord.calls[0]
    assert [s.payload["op"] for s in specs] == expected_ops


def test_a5_state_sensitive_fallback_executes_one_device_call():
    rt = FakeRuntime()
    coord = ContractSequenceCoordinator(rt, DeviceLeaseManager())
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand())
    revision = rt.observe()
    result = executor.execute_sequence(
        skill, [SequenceStep(op="tap_point"),
                SequenceStep(op="swipe", state_sensitive=True)],
        revision=revision)
    assert rt.device_calls == 1
    assert result.outcome == {"completed": 1, "effect": "NONE"}
    assert result.fallback_reason == "state-sensitive-fallback-single"


# --- fail-closed stale / PARTIAL / UNKNOWN: stop, no continuation, no replay ----


def test_a5_stale_revision_fails_closed_with_zero_device_calls():
    rt = FakeRuntime()
    stale_revision = rt.observe()  # accepted once...
    rt.observe()  # ...then immediately superseded: stale_revision is old now
    coord = ContractSequenceCoordinator(rt, DeviceLeaseManager())
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand())
    with pytest.raises(RuntimeOperationError) as err:
        executor.execute_sequence(skill, _steps("tap_point", "swipe"),
                                  revision=stale_revision)
    assert err.value.code == ErrorCode.STALE_REVISION
    assert rt.device_calls == 0  # stale preflight rejection: zero device calls
    assert len(coord.calls) == 1  # single delegation, never re-attempted


def test_a5_partial_outcome_stops_and_never_replays():
    rt = FakeRuntime()
    rt.script = ["fail"]  # PARTIAL on the single sequence call
    coord = ContractSequenceCoordinator(rt, DeviceLeaseManager())
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand())
    revision = rt.observe()
    result = executor.execute_sequence(skill, _steps("tap_point", "swipe"),
                                       revision=revision)
    assert result.outcome["effect"] == "PARTIAL"
    assert rt.device_calls == 1 and len(coord.calls) == 1  # no continuation/replay
    assert rt.revision != revision  # accepted revision invalidated by the effect


def test_a5_unknown_error_propagates_without_retry():
    error = _UnknownEffectError()
    coord = FakeSequenceCoordinator(error=error)
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand())
    with pytest.raises(RuntimeError) as err:
        executor.execute_sequence(skill, _steps("tap_point", "swipe"),
                                  revision="rev-1")
    assert err.value is error
    assert len(coord.calls) == 1  # exactly one delegation, never retried


def test_a5_unknown_effect_outcome_retained_not_continued():
    rt = FakeRuntime()
    rt.script = ["unknown"]
    coord = ContractSequenceCoordinator(rt, DeviceLeaseManager())
    executor = _enabled_executor(coord)
    skill = _active(executor.registry, _cand())
    revision = rt.observe()
    result = executor.execute_sequence(skill, _steps("tap_point", "swipe"),
                                       revision=revision)
    assert result.outcome["effect"] == "UNKNOWN"
    assert rt.device_calls == 1 and len(coord.calls) == 1
    assert rt.revision != revision


def test_a5_coordinator_without_sequence_seam_fails_closed():
    # A coordinator without the run_sequence seam must be refused explicitly
    # (no AttributeError, no silent fallback to run_batch). Integration note:
    # the shared ExecutionCoordinator now ships run_sequence (integration
    # pass, frozen D3=A), so the seam-less case is exercised with a minimal
    # seam-less double while the real coordinator contract is covered by
    # tests/test_phasea_integration.py.
    rt = FakeRuntime()
    executor = SkillExecutor(coordinator=object(), registry=SkillRegistry(),
                             sequence_enabled=True)
    skill = _active(executor.registry, _cand())
    with pytest.raises(SkillExecutionError) as err:
        executor.execute_sequence(skill, _steps("tap_point"), revision="rev-1")
    assert "sequence-coordinator-unavailable" in str(err.value)
    assert rt.device_calls == 0
