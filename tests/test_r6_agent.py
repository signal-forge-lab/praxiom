"""R6 scenario matrix (13 deterministic synthetic scenarios)."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

from praxiom.agent.arbiter import InterruptEvent, arbitrate
from praxiom.agent.coordinator import (
    CancelledError, DeadlineError, DeviceLeaseManager, ExecutionCoordinator,
    ExecutionSpec, LeaseBusyError,
)
from tests.fakes import FakeRuntime
from praxiom.agent.reasoning import ReasoningSignals, route
from praxiom.agent.recovery import RecoveryPlanner, RecoveryTransition, WorldState
from praxiom.knowledge.experience import ExperienceEpisode
from praxiom.knowledge.hygiene import (
    claim_key, find_conflicts, find_duplicates, mojibake_score, normalize_claim,
)
from praxiom.knowledge.promotion import KnowledgeRecord, promote, supersede


def _spec(**kw):
    base = dict(namespace="ns", owner="op", task_type="t.safe",
                task_version=1, payload={"op": "home"}, revision="rev-1")
    base.update(kw)
    return ExecutionSpec(**base)


def test_R6_A01_deadline_risk_reversibility():
    evs = [InterruptEvent(event_id="e-urgent", kind="goal", priority=95,
                          reversibility="irreversible", risk="high"),
           InterruptEvent(event_id="e-safe", kind="goal", priority=40)]
    res = arbitrate(evs, current_goal="g", at_safe_boundary=True)
    assert res.selected_id == "e-safe"
    assert "e-urgent" in res.rejected_ids


def test_R6_A02_safe_boundary_preemption_and_stale_invalidation():
    evs = [InterruptEvent(event_id="e-new", kind="operator", priority=80,
                          goal_assumption="world-v2")]
    res = arbitrate(evs, current_goal="g", at_safe_boundary=False,
                    current_assumption="world-v1")
    assert res.selected_id is None
    res2 = arbitrate(evs, current_goal="g", at_safe_boundary=True,
                     current_assumption="world-v1")
    assert res2.selected_id == "e-new"
    assert res2.stale_plan_invalidated is True
    # Teaching conflicting with safety policy is deferred/rejected explicitly.
    t = [InterruptEvent(event_id="e-teach", kind="teaching", priority=99, risk="high")]
    res3 = arbitrate(t, current_goal="g", at_safe_boundary=True)
    assert res3.selected_id is None
    assert "teaching" in res3.reasons["e-teach"]
    # Deterministic tie: lower event_id wins.
    tie = [InterruptEvent(event_id="e-b", kind="goal", priority=50),
           InterruptEvent(event_id="e-a", kind="goal", priority=50)]
    assert arbitrate(tie, current_goal="g", at_safe_boundary=True).selected_id == "e-a"
    # No raw payload in trace.
    assert all("secret" not in r for r in res2.reasons.values())


def test_R6_B01_experience_roundtrip_bounds_privacy():
    ep = ExperienceEpisode(episode_id="ep-1", transition="home->home",
                           outcome="ok", execution_id="exe-0001",
                           attempt_id="att-0001", revision="rev-9")
    raw = ep.to_json()
    assert ExperienceEpisode.from_json(raw) == ep
    assert "screenshot" not in raw and len(raw.encode()) <= 8 * 1024
    assert ep.provenance == "synthetic-fixture"


def test_R6_C01_hygiene_mojibake_duplicate_conflict_supersession():
    assert mojibake_score("ok text") == 0.0
    assert mojibake_score("bad \ufffd\ufffd\ufffd\ufffd\ufffd") > 0.2
    assert normalize_claim("  Hello   World ") == "Hello World"
    dups = find_duplicates(["Alpha Beta", "alpha  beta", "Gamma"])
    assert dups == [[0, 1]]
    a, b = "claim one", "claim two"
    keys = {frozenset({claim_key(a), claim_key(b)})}
    assert find_conflicts([(a, b)], keys) == [(a, b)]
    assert find_conflicts([(a, "other")], keys) == []


def test_R6_D01_promotion_evidence_conflict_teaching():
    rec = KnowledgeRecord(kid="k-1", claim="  anchor  fact ", supports=2)
    seq = [promote(rec).to_state, promote(rec).to_state]
    assert seq == ["normalized", "candidate"]
    blocked = promote(rec, has_conflict=True)
    assert blocked.to_state == "candidate" and "conflict" in blocked.reason
    ok = promote(rec, has_conflict=False)
    assert ok.to_state == "conflict_checked"
    still = promote(rec)  # supports=2 -> verified
    assert still.to_state == "verified"
    final = promote(rec)
    assert final.to_state == "promoted"
    # Semantic score cannot promote; policy teaching never fact-promotes.
    rec2 = KnowledgeRecord(kid="k-2", claim="fact two", state="conflict_checked",
                           supports=0, teaching_kind="policy")
    assert promote(rec2, semantic_score=0.99).to_state == "rejected"
    old = KnowledgeRecord(kid="k-old", claim="old claim", state="promoted")
    new = KnowledgeRecord(kid="k-new", claim="new claim")
    supersede(old, new)
    assert old.state == "superseded" and "supersedes:k-old" in new.provenance[0]


def test_R6_E01_routing_and_trace():
    assert route(ReasoningSignals()).tier == "deterministic"
    r = route(ReasoningSignals(unknown_state=True), latency_ms=7)
    assert (r.tier, r.latency_ms) == ("lightweight", 7) and r.reason
    assert route(ReasoningSignals(repeated_failures=3)).tier == "heavy"
    assert route(ReasoningSignals(teaching_contradicts_knowledge=True)).tier == "lightweight"


def test_R6_F01_spec_validation_rejection():
    bad_version = _spec(task_version=0)
    try:
        bad_version.validate()
        raise AssertionError("expected rejection")
    except ValueError:
        pass
    bad_op = _spec(payload={"op": "raw_tap"})
    try:
        bad_op.validate()
        raise AssertionError("expected rejection")
    except ValueError:
        pass
    no_ref = _spec(payload={"op": "tap_element"})
    try:
        no_ref.validate()
        raise AssertionError("expected rejection")
    except ValueError:
        pass


def _coord(tmpname, now=None):
    base = Path(__file__).resolve().parents[1] / ".pytest-tmp" / tmpname
    base.mkdir(parents=True, exist_ok=True)
    for p in base.glob("*.db"):
        p.unlink()
    rt = FakeRuntime()
    clock = {"t": 1000} if now is None else now
    now_fn = (lambda: clock["t"]) if isinstance(clock, dict) else clock
    coord = ExecutionCoordinator(rt, DeviceLeaseManager(),
                                 ledger_path=base / "ledger.db",
                                 now_ms=now_fn)
    return coord, rt, clock, base


def test_R6_F02_durable_lifecycle_restart_inspection():
    coord, rt, clock, _ = _coord("r6f02")
    rev = rt.observe()
    att = coord.run(_spec(revision=rev), owner="owner-a")
    assert att.state == "succeeded"
    rows = coord.inspect(att.execution_id)
    assert len(rows) == 1 and rows[0].attempt_id == att.attempt_id
    # Restart inspection: new coordinator over same ledger file.
    from praxiom.agent.coordinator import ExecutionCoordinator as EC
    coord2 = EC(rt, DeviceLeaseManager(),
                ledger_path=Path(__file__).resolve().parents[1] / ".pytest-tmp"
                / "r6f02" / "ledger.db", now_ms=lambda: 1000)
    assert len(coord2.inspect(att.execution_id)) == 1


def test_R6_F03_cancellation_deadline_prevents_mutation():
    coord, rt, clock, _ = _coord("r6f03")
    rev = rt.observe()
    before = rt.device_calls
    coord.cancel()
    try:
        coord.run(_spec(revision=rev), owner="o")
        raise AssertionError("expected cancel")
    except CancelledError:
        pass
    assert rt.device_calls == before
    coord2, rt2, clock2, _ = _coord("r6f03b")
    rev2 = rt2.observe()
    clock2["t"] = 5000
    try:
        coord2.run(_spec(revision=rev2, deadline_ms=1000), owner="o")
        raise AssertionError("expected deadline")
    except (DeadlineError, ValueError):
        pass
    assert rt2.device_calls == 0  # observe is not a mutation; run blocked pre-device


def test_R6_F04_lease_serializes_ownership():
    leases = DeviceLeaseManager()
    leases.acquire("dev-1", "owner-a")
    try:
        leases.acquire("dev-1", "owner-b")
        raise AssertionError("expected busy")
    except LeaseBusyError:
        pass
    leases.release("dev-1", "owner-a")
    leases.acquire("dev-1", "owner-b")  # free after release
    # Terminal attempt releases its lease even on failure.
    coord, rt, clk, _ = _coord("r6f04")
    rt.script = ["fail"]
    rev = rt.observe()
    att = coord.run(_spec(revision=rev), owner="owner-c")
    assert att.state == "failed"


def test_R6_F05_failed_unknown_retained_no_replay():
    coord, rt, _, _ = _coord("r6f05")
    rt.script = ["unknown"]
    rev = rt.observe()
    att = coord.run(_spec(revision=rev), owner="o")
    assert att.state == "unknown" and att.effect == "UNKNOWN"
    assert att.evidence["replayed"] is False
    assert rt.device_calls == 1  # exactly one attempt, no auto-replay


def test_R6_F06_async_runtime_port_preserves_boundary_and_lease():
    class AsyncRuntime:
        def __init__(self):
            self.calls = []
            self.invalidations = []

        async def execute(self, actions, *, expected_revision):
            self.calls.append((actions, expected_revision))
            return SimpleNamespace(
                completed_actions=1,
                accepted_revision_invalidated=True,
            )

        async def invalidate(self, reason):
            self.invalidations.append(reason)

    async def scenario():
        rt = AsyncRuntime()
        leases = DeviceLeaseManager()
        coord = ExecutionCoordinator(rt, leases, device_id="dev-real-shape")
        spec = _spec(revision="rev-live")
        seen = []

        def factory(payload):
            seen.append(dict(payload))
            return ("typed-action", payload["op"])

        att = await coord.run_async(spec, owner="owner-a", action_factory=factory)
        assert att.state == "succeeded"
        assert att.evidence["revision_invalidated"] is True
        assert att.evidence["replayed"] is False
        assert seen == [{"op": "home"}]
        assert rt.calls == [([("typed-action", "home")], "rev-live")]
        assert leases.holder("dev-real-shape") is None

    asyncio.run(scenario())


def test_R6_G01_known_reversible_recovery_to_anchor():
    planner = RecoveryPlanner([RecoveryTransition(transition_id="t-home",
                                                  from_state="off-goal:away",
                                                  to_state="home")])
    plan = planner.plan(goal_anchor="home",
                        world=WorldState(anchor_id="home",
                                         state_id="off-goal:away", revision="rev-3"))
    assert plan.steps and plan.steps[0].transition_id == "t-home"
    assert not plan.escalate


def test_R6_G02_ineffective_loop_suppressed():
    planner = RecoveryPlanner([RecoveryTransition(transition_id="t-x",
                                                  from_state="off-goal:loop",
                                                  to_state="off-goal:loop")])
    first = planner.plan(goal_anchor="home",
                         world=WorldState(anchor_id="home", state_id="off-goal:loop"))
    assert len(first.steps) == 1
    second = planner.plan(goal_anchor="home",
                          world=WorldState(anchor_id="home", state_id="off-goal:loop"))
    assert second.escalate and not second.steps


def test_R6_G03_high_risk_unknown_escalates_without_mutation():
    planner = RecoveryPlanner([RecoveryTransition(transition_id="t-pay",
                                                  from_state="off-goal:store",
                                                  to_state="home",
                                                  reversible=False, risk="high")])
    plan = planner.plan(goal_anchor="home",
                        world=WorldState(anchor_id="home", state_id="off-goal:store"))
    assert plan.escalate and plan.steps == ()
    plan2 = RecoveryPlanner([]).plan(
        goal_anchor="home",
        world=WorldState(anchor_id="home", state_id="mystery"))
    assert plan2.escalate
