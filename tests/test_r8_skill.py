"""R8 Skill Foundry deterministic acceptance matrix (47/47)."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from threading import Barrier, Thread

from praxiom.agent.coordinator import DeviceLeaseManager, ExecutionCoordinator
from praxiom.skill.need import detect_need
from praxiom.skill.candidate import SkillCandidate
from praxiom.skill.gates import GATE_ORDER, run_gates
from praxiom.skill.sandbox import SandboxPolicy, run_sandboxed
from praxiom.skill.reuse import Procedure, reuse_decision
from praxiom.skill.lifecycle import LifecycleState, record_success, transition
from praxiom.skill.executor import SkillExecutor, SkillExecutionError
from praxiom.skill.registry import (
    HumanApprovalAuthority, HumanApprovalEvidence, SkillRegistry, SkillRegistryError,
)
from tests.fakes import FakeRuntime


def _cand(**kw):
    base = dict(skill_id="sk-1", version=1, inputs=("x",), outputs=("y",),
                preconditions=("revision-bound: rev-1", "fact-a"),
                postconditions=("done",), risk="low", reversibility="reversible",
                authority=frozenset({"tap_point"}), provenance=("need-1",))
    base.update(kw)
    return SkillCandidate(**base)


# R8-A
def test_r8_01_repeated_gap_yields_need():
    n = detect_need(summary="missing tap", evidence_ids=["e1", "e2"],
                    failure_signatures=["tap missing"] * 3,
                    failure_revisions=["r1", "r2"], now_ms=5)
    assert n is not None and n.gap_kind == "missing-capability" and n.observed_failures == 3


def test_r8_02_one_off_no_need():
    assert detect_need(summary="x", evidence_ids=["e1", "e2"],
                        failure_signatures=["one-off: flake"],
                        failure_revisions=["r1", "r2"]) is None


def test_r8_03_stale_state_no_need():
    assert detect_need(summary="x", evidence_ids=["e1", "e2"],
                        failure_signatures=["stale-state: old"] * 3,
                        failure_revisions=["r1", "r2"]) is None


def test_r8_04_distinct_signatures_no_need():
    assert detect_need(summary="x", evidence_ids=["e1", "e2"],
                        failure_signatures=["a", "b", "c"],
                        failure_revisions=["r1", "r2"]) is None


def test_r8_05_single_revision_no_need():
    assert detect_need(summary="x", evidence_ids=["e1", "e2"],
                        failure_signatures=["same"] * 3,
                        failure_revisions=["r1"]) is None


def test_r8_06_insufficient_evidence_no_need():
    assert detect_need(summary="x", evidence_ids=["e1"],
                        failure_signatures=["same"] * 3,
                        failure_revisions=["r1", "r2"]) is None


def test_r8_07_confidence_frequency_never_sufficient():
    assert detect_need(summary="x", evidence_ids=["only-one"],
                        failure_signatures=["same"],
                        failure_revisions=["r1"],
                        model_confidence=0.99, frequency=999) is None


def test_r8_08_empty_summary_no_need():
    assert detect_need(summary="  ", evidence_ids=["e1", "e2"],
                        failure_signatures=["same"] * 3,
                        failure_revisions=["r1", "r2"]) is None


# R8-B
def test_r8_09_candidate_shape():
    c = _cand()
    assert c.lifecycle == "candidate" and c.version == 1


def test_r8_10_authority_subset_runtime_ops():
    c = _cand(authority=frozenset({"tap_point", "observe"}))
    assert run_gates(c).failed_gate == "authority"


def test_r8_11_no_domain_taxonomy():
    c = _cand(inputs=("gogomatch tap",))
    assert run_gates(c).failed_gate == "dependency"


def test_r8_12_no_raw_bypass():
    c = _cand(preconditions=("revision-bound: r", "raw_tap fast"))
    assert run_gates(c).failed_gate == "dependency"


def test_r8_13_version_positive():
    assert run_gates(_cand(version=0)).failed_gate == "schema"


def test_r8_14_pre_post_required():
    assert run_gates(_cand(preconditions=())).failed_gate == "schema"
    assert run_gates(_cand(postconditions=())).failed_gate == "schema"


# R8-C
def test_r8_15_schema_gate_unknown_risk():
    assert run_gates(_cand(risk="extreme")).failed_gate == "schema"


def test_r8_16_authority_excess_ops():
    assert run_gates(_cand(authority=frozenset({"tap_point", "wipe"}))).failed_gate == "authority"


def test_r8_17_high_irreversible_requires_human_gate():
    c = _cand(risk="high", reversibility="irreversible", human_gate=False)
    assert run_gates(c).failed_gate == "authority"
    assert run_gates(_cand(risk="high", reversibility="irreversible", human_gate=True)).passed


def test_r8_18_privacy_gate():
    assert run_gates(_cand(inputs=("password field",))).failed_gate == "privacy"


def test_r8_19_dependency_banned_edge():
    assert run_gates(_cand(code_ref="import subprocess // run")).failed_gate in ("dependency", "sandbox-readiness")


def test_r8_20_revision_binding_required():
    assert run_gates(_cand(preconditions=("fact-a",))).failed_gate == "revision"


def test_r8_21_stale_assumption_rejected():
    assert run_gates(_cand(preconditions=("revision-bound: r", "stale-assume ok"))).failed_gate == "safety"


def test_r8_22_code_ref_banned():
    assert run_gates(_cand(code_ref="use wda session")).failed_gate in ("dependency", "sandbox-readiness")


def test_r8_23_all_pass_and_order():
    r = run_gates(_cand())
    assert r.passed and r.evaluated == GATE_ORDER


# R8-D
def test_r8_24_minimal_policy_ok():
    res = run_sandboxed(lambda s, b: ("done", s), initial_state={},
                        policy=SandboxPolicy(), now_ms=lambda: 0)
    assert res.ok and res.steps_used == 1


def test_r8_25_network_policy_rejected():
    res = run_sandboxed(lambda s, b: ("done", s), initial_state={},
                        policy=SandboxPolicy(allow_network=True), now_ms=lambda: 0)
    assert not res.ok


def test_r8_26_filesystem_rejected():
    res = run_sandboxed(lambda s, b: ("done", s), initial_state={},
                        policy=SandboxPolicy(allow_filesystem=True), now_ms=lambda: 0)
    assert not res.ok


def test_r8_27_credentials_rejected():
    res = run_sandboxed(lambda s, b: ("done", s), initial_state={},
                        policy=SandboxPolicy(allow_credentials=True), now_ms=lambda: 0)
    assert not res.ok


def test_r8_28_device_rejected():
    res = run_sandboxed(lambda s, b: ("done", s), initial_state={},
                        policy=SandboxPolicy(allow_device=True), now_ms=lambda: 0)
    assert not res.ok


def test_r8_29_deadline_enforced():
    ticks = iter((0, 0, 50, 50, 50))

    def clock() -> int:
        return next(ticks, 50)

    def step(s, b):
        return ("continue", s)

    res = run_sandboxed(step, initial_state={},
                        policy=SandboxPolicy(max_steps=8, deadline_ms=10),
                        now_ms=clock)
    assert not res.ok and res.timed_out

    # R8-D requires preemption while a generated step is executing, not only
    # checks between cooperative step returns.
    def never_returns(s, b):
        while True:
            pass

    hard = run_sandboxed(never_returns, initial_state={},
                         policy=SandboxPolicy(max_steps=1, deadline_ms=10),
                         now_ms=lambda: 0)
    assert not hard.ok and hard.timed_out and hard.steps_used == 0

    # Exercise ordinary generated code in a fresh interpreter, outside
    # pytest's tracing/instrumentation. It must return on the wall deadline.
    probe = (
        "from praxiom.skill.sandbox import run_sandboxed,SandboxPolicy;"
        "ns={};"
        "exec(compile('def step(s,b):\\n    while True:\\n        pass\\n',"
        "'generated_skill.py','exec'),ns);"
        "r=run_sandboxed(ns['step'],initial_state={},"
        "policy=SandboxPolicy(max_steps=1,deadline_ms=10),now_ms=lambda:0);"
        "print(r.timed_out,r.detail)"
    )
    outside_pytest = subprocess.run(
        [sys.executable, "-c", probe], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=2,
    )
    assert outside_pytest.returncode == 0, outside_pytest.stdout + outside_pytest.stderr
    assert "True deadline-exceeded-during-step" in outside_pytest.stdout


def test_r8_30_cancel_enforced():
    res = run_sandboxed(lambda s, b: ("done", s), initial_state={},
                        policy=SandboxPolicy(), now_ms=lambda: 0,
                        is_cancelled=lambda: True)
    assert not res.ok and res.cancelled
    disabled = run_sandboxed(lambda s, b: ("done", s), initial_state={},
                             policy=SandboxPolicy(cancellable=False), now_ms=lambda: 0)
    assert not disabled.ok and disabled.detail == "cancellation-required"

    checks = {"n": 0}

    def cancel_after_trace_checks() -> bool:
        checks["n"] += 1
        return checks["n"] >= 8

    def never_returns(s, b):
        while True:
            pass

    during = run_sandboxed(never_returns, initial_state={},
                           policy=SandboxPolicy(max_steps=1, deadline_ms=1000),
                           now_ms=lambda: 0,
                           is_cancelled=cancel_after_trace_checks)
    assert not during.ok and during.cancelled and during.steps_used == 0


def test_r8_31_step_budget_enforced():
    res = run_sandboxed(lambda s, b: ("continue", s), initial_state={},
                        policy=SandboxPolicy(max_steps=2, deadline_ms=1000),
                        now_ms=lambda: 0)
    assert not res.ok and res.detail == "step-budget-exhausted"


def test_r8_32_unrecognized_effect_fails_closed():
    res = run_sandboxed(lambda s, b: ("weird", s), initial_state={},
                        policy=SandboxPolicy(), now_ms=lambda: 0)
    assert not res.ok and "unrecognized-effect" in res.detail
    def boom_step(s, b):
        raise ValueError("boom")

    boom = run_sandboxed(boom_step, initial_state={}, policy=SandboxPolicy(), now_ms=lambda: 0)
    assert not boom.ok and boom.detail == "step-error:ValueError"


def test_r8_33_sandbox_zero_device_calls():
    res = run_sandboxed(lambda s, b: ("done", s), initial_state={},
                        policy=SandboxPolicy(), now_ms=lambda: 0)
    assert res.device_calls == 0
    dangerous = run_sandboxed(lambda s, b: (__import__("sub" + "process"), s),
                              initial_state={}, policy=SandboxPolicy(), now_ms=lambda: 0)
    assert not dangerous.ok and dangerous.steps_used == 0
    def local_import(s, b):
        import pathlib
        return ("done", s)
    local = run_sandboxed(local_import, initial_state={}, policy=SandboxPolicy(),
                          now_ms=lambda: 0)
    assert not local.ok and local.steps_used == 0 and local.detail == "unsafe-step-import"
    def local_os(s, b):
        import os
        return ("done", {"cwd": os.getcwd()})
    def local_importlib(s, b):
        import importlib
        return ("done", {"name": importlib.import_module("o" + "s").name})
    for step in (local_os, local_importlib):
        blocked = run_sandboxed(step, initial_state={}, policy=SandboxPolicy(), now_ms=lambda: 0)
        assert not blocked.ok and blocked.steps_used == 0 and blocked.detail == "unsafe-step-import"
    class Unsafe:
        pass
    state = run_sandboxed(lambda s, b: ("done", s), initial_state={"x": Unsafe()},
                          policy=SandboxPolicy(), now_ms=lambda: 0)
    assert not state.ok and state.detail == "unsafe-initial-state"

    # Resource amplification and trace-signal swallowing are excluded from the
    # admitted procedural subset before execution.
    huge = run_sandboxed(lambda s, b: ("done", {"x": 1 << 300}), initial_state={},
                         policy=SandboxPolicy(), now_ms=lambda: 0)
    assert not huge.ok and huge.steps_used == 0

    def catches_everything(s, b):
        try:
            while True:
                pass
        except BaseException:
            return ("done", s)

    catches = run_sandboxed(catches_everything, initial_state={},
                            policy=SandboxPolicy(), now_ms=lambda: 0)
    assert not catches.ok and catches.steps_used == 0
    assert catches.detail == "unsafe-step-exception-handler"

    def amplifies_local_data(s, b):
        value = s["value"]
        while True:
            value = value + value

    amplified = run_sandboxed(amplifies_local_data, initial_state={"value": "x" * 4096},
                              policy=SandboxPolicy(deadline_ms=1000), now_ms=lambda: 0)
    assert not amplified.ok and amplified.steps_used == 0
    assert amplified.detail == "instruction-budget-exhausted"

    def format_amplification(s, b):
        discarded = f"{1:1000000000}"
        return ("done", s)

    formatted = run_sandboxed(format_amplification, initial_state={},
                              policy=SandboxPolicy(), now_ms=lambda: 0)
    assert not formatted.ok and formatted.steps_used == 0
    assert formatted.detail.startswith("unsafe-step-opcode:format_")

    nonfinite = run_sandboxed(lambda s, b: ("done", s), initial_state={"x": float("inf")},
                              policy=SandboxPolicy(), now_ms=lambda: 0)
    assert not nonfinite.ok and nonfinite.detail == "unsafe-initial-state"

    escaped = Path(".tmp-r8-evil-int")

    class EvilInt(int):
        def bit_length(self):
            escaped.write_text("escaped", encoding="utf-8")
            return 1

    try:
        subclassed = run_sandboxed(
            lambda s, b: ("done", s),
            initial_state={"x": EvilInt(1)},
            policy=SandboxPolicy(),
            now_ms=lambda: 0,
        )
        assert not subclassed.ok and subclassed.detail == "unsafe-initial-state"
        assert not escaped.exists()
    finally:
        escaped.unlink(missing_ok=True)

    # Names that normally resolve to allowed builtin exception constructors
    # must resolve to those exact trusted objects; a function-global shadow
    # cannot run arbitrary host code during a generated step.
    shadow_escape = Path(".tmp-r8-shadowed-global")

    def shadow_template(s, b):
        raise ValueError("boom")

    def evil_value_error(message):
        shadow_escape.write_text(str(message), encoding="utf-8")
        return RuntimeError(message)

    import types
    shadowed = types.FunctionType(
        shadow_template.__code__,
        {"ValueError": evil_value_error, "__builtins__": shadow_template.__builtins__},
    )
    try:
        shadow_result = run_sandboxed(shadowed, initial_state={},
                                      policy=SandboxPolicy(), now_ms=lambda: 0)
        assert not shadow_result.ok and shadow_result.steps_used == 0
        assert shadow_result.detail == "unsafe-step-global:ValueError"
        assert not shadow_escape.exists()
    finally:
        shadow_escape.unlink(missing_ok=True)

    captured = {"outside": 0}

    def mutates_capture(s, b):
        captured["outside"] = 1
        return ("done", s)

    capture_result = run_sandboxed(mutates_capture, initial_state={},
                                   policy=SandboxPolicy(), now_ms=lambda: 0)
    assert not capture_result.ok and capture_result.steps_used == 0
    assert capture_result.detail == "unsafe-step-closure"
    assert captured == {"outside": 0}

    initial = {"nested": {"outside": 0}}

    def mutates_isolated_state(s, b):
        s["nested"]["outside"] = 1
        return ("done", s)

    isolated = run_sandboxed(mutates_isolated_state, initial_state=initial,
                             policy=SandboxPolicy(), now_ms=lambda: 0)
    assert isolated.ok
    assert initial == {"nested": {"outside": 0}}


# R8-E
def _proc(**kw):
    base = dict(procedure_id="p1", effect="NONE", revision="rev-1",
                preconditions=("fact-a",), execution_id="e", attempt_id="a",
                experience_id="x")
    base.update(kw)
    return Procedure(**base)


def test_r8_34_valid_reuse():
    d = reuse_decision(_proc(), current_revision="rev-1",
                       current_facts=frozenset({"fact-a", "other"}),
                       knowledge_state="verified")
    assert d.action == "reuse" and d.linkage["procedure_id"] == "p1"


def test_r8_35_partial_reobserve():
    assert reuse_decision(_proc(effect="PARTIAL"), current_revision="rev-1",
                          current_facts=frozenset({"fact-a"}),
                          knowledge_state="verified").action == "reobserve"


def test_r8_36_unknown_reobserve():
    assert reuse_decision(_proc(effect="UNKNOWN"), current_revision="rev-1",
                          current_facts=frozenset({"fact-a"}),
                          knowledge_state="verified").action == "reobserve"


def test_r8_37_unrecognized_reobserve():
    assert reuse_decision(_proc(effect="SOMETHING-NEW"), current_revision="rev-1",
                          current_facts=frozenset({"fact-a"}),
                          knowledge_state="verified").action == "reobserve"


def test_r8_38_stale_revision_reobserve():
    assert reuse_decision(_proc(), current_revision="rev-2",
                          current_facts=frozenset({"fact-a"}),
                          knowledge_state="verified").action == "reobserve"


def test_r8_39_preconditions_unproven_reobserve():
    assert reuse_decision(_proc(), current_revision="rev-1",
                          current_facts=frozenset({"other"}),
                          knowledge_state="verified").action == "reobserve"


def test_r8_40_revoked_superseded_reject():
    assert reuse_decision(_proc(revoked=True), current_revision="rev-1",
                          current_facts=frozenset({"fact-a"}),
                          knowledge_state="verified").action == "reject"
    assert reuse_decision(_proc(superseded=True), current_revision="rev-1",
                          current_facts=frozenset({"fact-a"}),
                          knowledge_state="verified").action == "reject"


def test_r8_41_knowledge_lifecycle_invalid_reject():
    assert reuse_decision(_proc(), current_revision="rev-1",
                          current_facts=frozenset({"fact-a"}),
                          knowledge_state="candidate").action == "reject"
    assert reuse_decision(_proc(), current_revision="rev-1",
                          current_facts=frozenset({"fact-a"}),
                          knowledge_state="active").action == "reject"


def test_r8_42_linkage_retained():
    d = reuse_decision(_proc(), current_revision="rev-1",
                       current_facts=frozenset({"fact-a"}), knowledge_state="verified")
    assert d.linkage == {"execution_id": "e", "attempt_id": "a",
                         "experience_id": "x", "procedure_id": "p1"}


# R8-F + executor
def test_r8_43_validated_requires_gates_and_evidence():
    st = LifecycleState(skill_id="s", version=1)
    assert not transition(st, "validated", gate_passed=False, evidence_id="e1")
    assert not transition(st, "validated", gate_passed=True, evidence_id="e1")
    assert transition(st, "validated", gate_passed=True,
                      evidence_ids=("e1", "e2"), reason="reviewed-gates")
    assert st.state == "validated"
    assert "reviewed-gates" in st.provenance[-1]


def test_r8_44_one_success_never_active():
    st = LifecycleState(skill_id="s", version=1, state="validated")
    assert record_success(st, revision="r1", evidence_id="e1")
    assert not transition(st, "active", evidence_id="e2")


def test_r8_45_two_successes_active():
    st = LifecycleState(skill_id="s", version=1, state="validated")
    assert record_success(st, revision="r1", evidence_id="e1")
    assert record_success(st, revision="r1", evidence_id="e1b")
    assert not transition(st, "active", evidence_id="e2")
    assert record_success(st, revision="r2", evidence_id="e2")
    assert transition(st, "active", evidence_id="e2")
    assert st.state == "active"


def test_r8_46_degraded_superseded_revoked_no_reactivation():
    st = LifecycleState(skill_id="s", version=1, state="active",
                        success_revisions={"r1", "r2"}, successes=2)
    assert transition(st, "degraded", evidence_id="sig")
    assert transition(st, "superseded", evidence_id="sup", new_version=2)
    assert st.state == "superseded"
    assert not transition(st, "active", evidence_id="x")
    st2 = LifecycleState(skill_id="t", version=1, state="active",
                         success_revisions={"r1", "r2"}, successes=2)
    assert transition(st2, "revoked", evidence_id="safe")
    assert not transition(st2, "active", evidence_id="x")


def test_r8_47_executor_only_via_coordinator_active_revision_authority():
    rt = FakeRuntime()
    rev = rt.observe()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    ex = SkillExecutor(coordinator=coord, registry=registry)
    candidate = _cand(skill_id="s", provenance=("p1", "p2"))
    registry.register(candidate)
    registry.validate("s", 1, evidence_ids=("p1", "p2"))
    registry.record_success("s", 1, revision="r1", evidence_id="s1")
    registry.record_success("s", 1, revision="r2", evidence_id="s2")
    skill = registry.activate("s", 1, confidence=0.9, evidence_id="activate")
    att = ex.execute(skill, revision=rev, op="tap_point")
    assert att.state == "succeeded"
    try:
        ex.execute(skill, revision=rev, op="tap_point", extra={"op": "swipe"})
        assert False
    except SkillExecutionError:
        pass
    registry2 = SkillRegistry()
    candidate2 = _cand(skill_id="t", provenance=("q1", "q2"))
    registry2.register(candidate2)
    registry2.validate("t", 1, evidence_ids=("q1", "q2"))
    registry2.record_success("t", 1, revision="r1", evidence_id="same")
    registry2.record_success("t", 1, revision="r2", evidence_id="same")
    try:
        registry2.activate("t", 1, confidence=1.0, evidence_id="activate")
        assert False
    except SkillRegistryError:
        pass
    try:
        ex.execute(skill, revision=rev, op="tap_point", extra={"revision": "foreign"})
        assert False
    except SkillExecutionError:
        pass
    try:
        ex.execute(skill, revision=rev, op="wipe")
        assert False
    except SkillExecutionError:
        pass
    try:
        ex.execute(skill, revision="", op="tap_point")
        assert False
    except SkillExecutionError:
        pass
    from praxiom.skill.candidate import ActiveSkill
    cand_skill = ActiveSkill(skill_id="s", version=1, inputs=("x",), outputs=("y",),
                             preconditions=("revision-bound",), postconditions=("d",),
                             risk="low", reversibility="reversible",
                             authority=frozenset({"tap_point"}), provenance=("p",),
                             lifecycle="active", gated_by=("all-gates-pass",), confidence=1.0)
    try:
        ex.execute(cand_skill, revision=rev, op="tap_point")
        assert False
    except SkillExecutionError:
        pass
    # Post-activation lifecycle invalidation removes execution authority.
    registry.revoke("s", 1, evidence_id="safety")
    try:
        ex.execute(skill, revision=rev, op="tap_point")
        assert False
    except SkillExecutionError:
        pass

    # Activating a newer version atomically retires the older active version.
    reg2 = SkillRegistry()
    c1 = _cand(skill_id="upgrade", version=1, provenance=("a", "b"))
    c2 = _cand(skill_id="upgrade", version=2, provenance=("c", "d"))
    for c, prefix in ((c1, "one"), (c2, "two")):
        reg2.register(c)
        reg2.validate(c.skill_id, c.version,
                      evidence_ids=(f"{prefix}-e1", f"{prefix}-e2"))
        reg2.record_success(c.skill_id, c.version, revision=f"{prefix}-r1",
                            evidence_id=f"{prefix}-s1")
        reg2.record_success(c.skill_id, c.version, revision=f"{prefix}-r2",
                            evidence_id=f"{prefix}-s2")
    old = reg2.activate("upgrade", 1, confidence=0.8, evidence_id="old-active")
    new = reg2.activate("upgrade", 2, confidence=0.9, evidence_id="new-active")
    assert not reg2.is_executable(old) and reg2.is_executable(new)

    # A lower version cannot be activated after a newer version is live.
    reg3 = SkillRegistry()
    for version in (1, 2):
        c = _cand(skill_id="no-downgrade", version=version,
                  provenance=(f"v{version}-a", f"v{version}-b"))
        reg3.register(c)
        reg3.validate("no-downgrade", version,
                      evidence_ids=(f"v{version}-e1", f"v{version}-e2"))
        reg3.record_success("no-downgrade", version, revision=f"v{version}-r1",
                            evidence_id=f"v{version}-s1")
        reg3.record_success("no-downgrade", version, revision=f"v{version}-r2",
                            evidence_id=f"v{version}-s2")
    newer = reg3.activate("no-downgrade", 2, confidence=0.9, evidence_id="v2-active")
    assert reg3.is_executable(newer)
    try:
        reg3.activate("no-downgrade", 1, confidence=0.9, evidence_id="v1-late")
        assert False
    except SkillRegistryError:
        pass

    # Human-gated skills retain that requirement through registry -> executor.
    approval_authority = HumanApprovalAuthority()
    gated_registry = SkillRegistry(human_approval_authority=approval_authority)
    gated_candidate = _cand(skill_id="human-gated", risk="high",
                            reversibility="irreversible", human_gate=True,
                            provenance=("hg-a", "hg-b"))
    gated_registry.register(gated_candidate)
    gated_registry.validate("human-gated", 1, evidence_ids=("hg-e1", "hg-e2"))
    gated_registry.record_success("human-gated", 1, revision="hg-r1", evidence_id="hg-s1")
    gated_registry.record_success("human-gated", 1, revision="hg-r2", evidence_id="hg-s2")
    gated_skill = gated_registry.activate("human-gated", 1, confidence=0.9,
                                          evidence_id="hg-active")
    gated_exec = SkillExecutor(coordinator=coord, registry=gated_registry)
    assert gated_skill.human_gate is True
    object.__setattr__(gated_skill, "human_gate", False)
    try:
        gated_exec.execute(gated_skill, revision=rt.observe(), op="tap_point")
        assert False
    except SkillExecutionError:
        pass
    object.__setattr__(gated_skill, "human_gate", True)
    try:
        gated_exec.execute(gated_skill, revision=rt.observe(), op="tap_point")
        assert False
    except SkillExecutionError:
        pass
    approval_rev1 = rt.observe()
    payload = {"op": "tap_point"}
    evidence = approval_authority.approve(
        skill_id=gated_skill.skill_id,
        version=gated_skill.version,
        revision=approval_rev1,
        payload=payload,
        evidence_id="human-approved-1",
    )
    approval = gated_registry.issue_human_gate_approval(
        gated_skill,
        revision=approval_rev1,
        payload=payload,
        evidence=evidence,
    )
    gated_att = gated_exec.execute(
        gated_skill,
        revision=approval_rev1,
        op="tap_point",
        human_gate_approval=approval,
    )
    assert gated_att.state == "succeeded"

    # Approval is one-shot and cannot be replayed.
    try:
        gated_exec.execute(
            gated_skill,
            revision=rt.observe(),
            op="tap_point",
            human_gate_approval=approval,
        )
        assert False
    except SkillExecutionError:
        pass

    # A copied/forged approval object is not registry authority.
    from praxiom.skill.registry import HumanGateApproval
    approval_rev2 = rt.observe()
    payload2 = {"op": "tap_point"}
    evidence2 = approval_authority.approve(
        skill_id=gated_skill.skill_id,
        version=gated_skill.version,
        revision=approval_rev2,
        payload=payload2,
        evidence_id="human-approved-2",
    )
    approval2 = gated_registry.issue_human_gate_approval(
        gated_skill,
        revision=approval_rev2,
        payload=payload2,
        evidence=evidence2,
    )
    forged = HumanGateApproval(
        skill_id=approval2.skill_id,
        version=approval2.version,
        revision=approval2.revision,
        payload_digest=approval2.payload_digest,
        approval_id=approval2.approval_id,
        evidence_id=approval2.evidence_id,
    )
    try:
        gated_exec.execute(
            gated_skill,
            revision=approval_rev2,
            op="tap_point",
            human_gate_approval=forged,
        )
        assert False
    except SkillExecutionError:
        pass
    assert gated_exec.execute(
        gated_skill,
        revision=approval_rev2,
        op="tap_point",
        human_gate_approval=approval2,
    ).state == "succeeded"

    # Approval cannot cross revisions. A mismatch does not consume it, so the
    # exact approved mutation can still use it once.
    approval_revision_value = rt.observe()
    payload3 = {"op": "tap_point"}
    evidence3 = approval_authority.approve(
        skill_id=gated_skill.skill_id,
        version=gated_skill.version,
        revision=approval_revision_value,
        payload=payload3,
        evidence_id="human-approved-r3",
    )
    approval_revision = gated_registry.issue_human_gate_approval(
        gated_skill,
        revision=approval_revision_value,
        payload=payload3,
        evidence=evidence3,
    )
    try:
        gated_exec.execute(
            gated_skill,
            revision=approval_revision_value + "-other",
            op="tap_point",
            human_gate_approval=approval_revision,
        )
        assert False
    except SkillExecutionError:
        pass
    assert gated_exec.execute(
        gated_skill,
        revision=approval_revision_value,
        op="tap_point",
        human_gate_approval=approval_revision,
    ).state == "succeeded"

    # The same external human evidence cannot mint a second attestation.
    replay_revision = rt.observe()
    try:
        approval_authority.approve(
            skill_id=gated_skill.skill_id,
            version=gated_skill.version,
            revision=replay_revision,
            payload={"op": "tap_point"},
            evidence_id="human-approved-r3",
        )
        assert False
    except SkillRegistryError:
        pass

    # A registry without the configured human-boundary capability cannot
    # self-mint an approval from caller-provided data.
    untrusted_registry = SkillRegistry()
    rogue_authority = HumanApprovalAuthority()
    rogue_evidence = rogue_authority.approve(
        skill_id=gated_skill.skill_id,
        version=gated_skill.version,
        revision=replay_revision,
        payload={"op": "tap_point"},
        evidence_id="rogue-human-evidence",
    )
    try:
        untrusted_registry.issue_human_gate_approval(
            gated_skill,
            revision=replay_revision,
            payload={"op": "tap_point"},
            evidence=rogue_evidence,
        )
        assert False
    except SkillRegistryError:
        pass

    # A copied human attestation is not authority, even with matching fields.
    copy_revision = rt.observe()
    authentic = approval_authority.approve(
        skill_id=gated_skill.skill_id,
        version=gated_skill.version,
        revision=copy_revision,
        payload={"op": "tap_point"},
        evidence_id="human-approved-copy-test",
    )
    copied = HumanApprovalEvidence(
        skill_id=authentic.skill_id,
        version=authentic.version,
        revision=authentic.revision,
        payload_digest=authentic.payload_digest,
        evidence_id=authentic.evidence_id,
        evidence_nonce=authentic.evidence_nonce,
    )
    try:
        gated_registry.issue_human_gate_approval(
            gated_skill,
            revision=copy_revision,
            payload={"op": "tap_point"},
            evidence=copied,
        )
        assert False
    except SkillRegistryError:
        pass
    approval_copy = gated_registry.issue_human_gate_approval(
        gated_skill,
        revision=copy_revision,
        payload={"op": "tap_point"},
        evidence=authentic,
    )
    assert gated_exec.execute(
        gated_skill, revision=copy_revision, op="tap_point",
        human_gate_approval=approval_copy,
    ).state == "succeeded"

    # Human approval covers the exact canonical mutation payload, not just op.
    payload_revision = rt.observe()
    exact_extra = {"x": 10, "y": 20}
    payload_evidence = approval_authority.approve(
        skill_id=gated_skill.skill_id,
        version=gated_skill.version,
        revision=payload_revision,
        payload={"op": "tap_point", **exact_extra},
        evidence_id="human-approved-exact-payload",
    )
    payload_approval = gated_registry.issue_human_gate_approval(
        gated_skill,
        revision=payload_revision,
        payload={"op": "tap_point", **exact_extra},
        evidence=payload_evidence,
    )
    try:
        gated_exec.execute(
            gated_skill,
            revision=payload_revision,
            op="tap_point",
            extra={"x": 10, "y": 21},
            human_gate_approval=payload_approval,
        )
        assert False
    except SkillExecutionError:
        pass
    assert gated_exec.execute(
        gated_skill,
        revision=payload_revision,
        op="tap_point",
        extra=exact_extra,
        human_gate_approval=payload_approval,
    ).state == "succeeded"

    # Caller-visible evidence/approval fields are not authority.  Mutating the
    # frozen objects cannot rebind the independently stored claims.
    tamper_revision = rt.observe()
    original_payload = {"op": "tap_point", "x": 1, "y": 2}
    tamper_evidence = approval_authority.approve(
        skill_id=gated_skill.skill_id,
        version=gated_skill.version,
        revision=tamper_revision,
        payload=original_payload,
        evidence_id="human-approved-tamper-evidence",
    )
    object.__setattr__(tamper_evidence, "revision", tamper_revision + "-forged")
    object.__setattr__(tamper_evidence, "payload_digest", "0" * 64)
    try:
        gated_registry.issue_human_gate_approval(
            gated_skill,
            revision=tamper_revision + "-forged",
            payload={"op": "tap_point", "x": 9, "y": 9},
            evidence=tamper_evidence,
        )
        assert False
    except SkillRegistryError:
        pass
    tamper_approval = gated_registry.issue_human_gate_approval(
        gated_skill,
        revision=tamper_revision,
        payload=original_payload,
        evidence=tamper_evidence,
    )
    object.__setattr__(tamper_approval, "revision", tamper_revision + "-forged")
    object.__setattr__(tamper_approval, "payload_digest", "f" * 64)
    try:
        gated_exec.execute(
            gated_skill,
            revision=tamper_revision + "-forged",
            op="tap_point",
            extra={"x": 9, "y": 9},
            human_gate_approval=tamper_approval,
        )
        assert False
    except SkillExecutionError:
        pass
    assert gated_exec.execute(
        gated_skill,
        revision=tamper_revision,
        op="tap_point",
        extra={"x": 1, "y": 2},
        human_gate_approval=tamper_approval,
    ).state == "succeeded"

    # A one-shot approval remains one-shot under concurrent consumers.
    race_revision = rt.observe()
    race_payload = {"op": "tap_point", "x": 3, "y": 4}
    race_evidence = approval_authority.approve(
        skill_id=gated_skill.skill_id,
        version=gated_skill.version,
        revision=race_revision,
        payload=race_payload,
        evidence_id="human-approved-race",
    )
    race_approval = gated_registry.issue_human_gate_approval(
        gated_skill,
        revision=race_revision,
        payload=race_payload,
        evidence=race_evidence,
    )
    barrier = Barrier(3)
    race_results: list[bool] = []

    def consume_once() -> None:
        barrier.wait()
        race_results.append(gated_registry.consume_human_gate_approval(
            gated_skill,
            race_approval,
            revision=race_revision,
            payload=race_payload,
        ))

    workers = [Thread(target=consume_once) for _ in range(2)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join()
    assert sorted(race_results) == [False, True]

    # Degrading a live skill also invalidates its registry token immediately.
    approval_rev4 = rt.observe()
    payload4 = {"op": "tap_point"}
    evidence4 = approval_authority.approve(
        skill_id=gated_skill.skill_id,
        version=gated_skill.version,
        revision=approval_rev4,
        payload=payload4,
        evidence_id="human-approved-3",
    )
    approval3 = gated_registry.issue_human_gate_approval(
        gated_skill,
        revision=approval_rev4,
        payload=payload4,
        evidence=evidence4,
    )
    gated_registry.degrade("human-gated", 1, evidence_id="quality-drop")
    assert not gated_registry.is_executable(gated_skill)
    assert not gated_registry.consume_human_gate_approval(
        gated_skill,
        approval3,
        revision=approval_rev4,
        payload=payload4,
    )
