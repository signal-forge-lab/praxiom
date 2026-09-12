"""R6 A/E/F/G lane conformance (freeze 20260906): authority + execution lane.

Deterministic, fake-Runtime only, temp-store ledgers (tempfile, never
committed). Covers: revision binding, batch preflight, owned-resource close,
single-lane mutation, no blind replay after ambiguous effect,
recovery-loop suppression, deterministic success + failure coverage,
restart/crash inspection.
"""
import contextlib
import itertools
import sqlite3
from pathlib import Path

import pytest

import praxiom.agent.coordinator as coordinator_mod
from praxiom.agent.arbiter import InterruptEvent, arbitrate
from praxiom.agent.coordinator import (
    ATTEMPT_TERMINAL,
    EXECUTION_TERMINAL,
    LEDGER_SCHEMA_VERSION,
    CancelledError,
    DeadlineError,
    DeviceLeaseManager,
    ExecutionCoordinator,
    ExecutionSpec,
    LeaseBusyError,
    SpecValidationError,
    preflight_specs,
)
from tests.fakes import FakeRuntime
from praxiom.agent.reasoning import ReasoningSignals, escalation_chain, route
from praxiom.agent.recovery import RecoveryPlanner, RecoveryTransition, WorldState

# Temp stores are isolated per-test scratch dirs under a workspace-local root
# (plain mkdir/unlink only: the sandbox denies chmod-based platform-temp and
# tmp_path cleanup). Each ledger is still an uncommitted temp store that
# proves restart/crash inspection; nothing under .pytest-tmp is committed.
_SCRATCH_ROOT = Path(__file__).resolve().parents[1] / ".pytest-tmp" / "r6-lane"
_lane_counter = itertools.count(1)


@contextlib.contextmanager
def _tempdir():
    _SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    d = _SCRATCH_ROOT / f"t{next(_lane_counter):04d}"
    d.mkdir(parents=True, exist_ok=True)
    for p in d.glob("*.db*"):
        try:
            p.unlink()
        except OSError:
            pass
    try:
        yield d
    finally:
        for p in d.glob("*.db*"):
            try:
                p.unlink()
            except OSError:
                pass


def _spec(**kw):
    base = dict(namespace="ns", owner="op", task_type="t.safe",
                task_version=1, payload={"op": "home"}, revision="rev-1")
    base.update(kw)
    return ExecutionSpec(**base)


def _coord(tmpdir: Path, rt=None, now=None, device_id="device-0"):
    rt = rt if rt is not None else FakeRuntime()
    now_fn = now if now is not None else (lambda: 1000)
    coord = ExecutionCoordinator(rt, DeviceLeaseManager(),
                                 ledger_path=tmpdir / "ledger.db",
                                 now_ms=now_fn, device_id=device_id)
    return coord, rt


# --- revision binding -------------------------------------------------------

def test_lane_revision_binding_stale_rejected_no_phantom_success():
    with _tempdir() as td:
        coord, rt = _coord(Path(td))
        rev = rt.observe()
        att = coord.run(_spec(revision=rev), owner="o")
        assert att.state == "succeeded"
        # Stale revision fails closed through the Runtime seam.
        stale = coord.run(_spec(revision=rev), owner="o")
        assert stale.state in ("failed", "unknown")
        assert coord.inspect(stale.execution_id)[0].attempt_id == stale.attempt_id
        coord.close()


def test_lane_raw_envelope_rejected_before_mutation():
    with _tempdir() as td:
        coord, rt = _coord(Path(td))
        before = rt.device_calls
        with pytest.raises((SpecValidationError, ValueError)):
            coord.run(_spec(payload={"op": "raw_tap"}), owner="o")
        with pytest.raises((SpecValidationError, ValueError)):
            coord.run(_spec(payload={"op": "tap_element"}), owner="o")
        with pytest.raises((SpecValidationError, ValueError)):
            coord.run(_spec(task_version=0), owner="o")
        assert rt.device_calls == before
        coord.close()


# --- batch preflight --------------------------------------------------------

def test_lane_batch_preflight_zero_effect_on_reject():
    with _tempdir() as td:
        coord, rt = _coord(Path(td))
        rev = rt.observe()
        good = _spec(revision=rev)
        bad = _spec(revision=rev, payload={"op": "raw_tap"})
        with pytest.raises((SpecValidationError, ValueError)):
            coord.run_batch([good, bad], owner="o")
        assert rt.device_calls == 0  # whole batch rejected before first effect
        # All-valid batch executes in single-lane order.
        rev2 = rt.observe()
        attempts = coord.run_batch(
            [_spec(revision=rev2), _spec(revision="stale-rev")], owner="o")
        assert [a.state for a in attempts] == ["succeeded", "failed"]
        assert rt.device_calls == 1
        with pytest.raises(SpecValidationError):
            preflight_specs([])
        coord.close()


# --- owned-resource close ---------------------------------------------------

def test_lane_owned_close_releases_lease_keeps_runtime_authority():
    with _tempdir() as td:
        leases = DeviceLeaseManager()
        rt = FakeRuntime()
        coord = ExecutionCoordinator(rt, leases, ledger_path=Path(td) / "l.db",
                                     now_ms=lambda: 1000)
        leases.acquire("device-9", "other-owner-hold")  # not ours
        coord._acquire_owned("lane-owner")
        coord.close()
        assert leases.holder("device-9") == "other-owner-hold"  # only owned out
        assert leases.holder("device-0") is None
        assert rt.closed is False  # Runtime never closed by coordinator
        coord.close()  # idempotent
        with pytest.raises(RuntimeError):
            coord.run(_spec(revision="rev-x"), owner="lane-owner")


# --- single-lane mutation ---------------------------------------------------

def test_lane_single_lane_second_owner_fails_closed():
    leases = DeviceLeaseManager()
    leases.acquire("dev-1", "owner-a")
    with pytest.raises(LeaseBusyError):
        leases.acquire("dev-1", "owner-b")
    leases.release("dev-1", "owner-a")
    leases.acquire("dev-1", "owner-b")
    assert leases.holder("dev-1") == "owner-b"

    with _tempdir() as td:
        shared = DeviceLeaseManager()
        rt = FakeRuntime()
        c1 = ExecutionCoordinator(rt, shared, ledger_path=Path(td) / "a.db",
                                  now_ms=lambda: 1000)
        c2 = ExecutionCoordinator(rt, shared, ledger_path=Path(td) / "b.db",
                                  now_ms=lambda: 1000)
        shared.acquire("device-0", "c1-owner")  # lane occupied
        with pytest.raises(LeaseBusyError):
            c2.run(_spec(revision=rt.observe()), owner="c2-owner")
        c1.close()
        c2.close()


# --- no blind replay after ambiguous effect ---------------------------------

def test_lane_unknown_effect_retained_single_attempt_reconcile_needs_observe():
    with _tempdir() as td:
        coord, rt = _coord(Path(td))
        rt.script = ["unknown"]
        rev = rt.observe()
        att = coord.run(_spec(revision=rev), owner="o")
        assert att.state == "unknown" and att.effect == "UNKNOWN"
        assert att.retry_safe is False
        assert att.evidence["replayed"] is False
        assert att.evidence["retry_safe"] is False
        assert rt.device_calls == 1  # zero auto-replay
        # Continuation requires reconciliation: fresh observe for next binding.
        fresh = rt.observe()
        rt.script = ["ok"]
        nxt = coord.run(_spec(revision=fresh), owner="o")
        assert nxt.state == "succeeded"
        assert rt.device_calls == 2
        coord.close()


def test_lane_failed_effect_terminal_releases_lease():
    with _tempdir() as td:
        leases = DeviceLeaseManager()
        rt = FakeRuntime()
        rt.script = ["fail"]
        coord = ExecutionCoordinator(rt, leases, ledger_path=Path(td) / "l.db",
                                     now_ms=lambda: 1000)
        att = coord.run(_spec(revision=rt.observe()), owner="o")
        assert att.state == "failed" and att.retry_safe is False
        assert leases.holder("device-0") is None  # terminal releases lease
        coord.close()


# --- restart / crash consistency (temp stores) ------------------------------

def test_lane_restart_inspects_history_crash_mid_batch():
    with _tempdir() as td:
        ledger = Path(td) / "ledger.db"
        rt = FakeRuntime()
        coord = ExecutionCoordinator(rt, DeviceLeaseManager(),
                                     ledger_path=ledger, now_ms=lambda: 1000)
        rev = rt.observe()
        first = coord.run(_spec(revision=rev), owner="o")
        assert first.state == "succeeded"
        first_eid = first.execution_id
        # Simulate crash: drop coordinator without close, reopen same file.
        del coord
        rt2 = FakeRuntime()
        coord2 = ExecutionCoordinator(rt2, DeviceLeaseManager(),
                                      ledger_path=ledger, now_ms=lambda: 1000)
        assert coord2.ledger_schema_version == LEDGER_SCHEMA_VERSION
        rows = coord2.inspect(first_eid)
        assert len(rows) == 1 and rows[0].state == "succeeded"
        assert coord2.ledger_executions() == [first_eid]
        # Spec version binds restart interpretation: stored versions survive.
        con = sqlite3.connect(str(ledger))
        try:
            got = con.execute(
                "SELECT schema_version, spec_version, task_version FROM attempts"
            ).fetchall()
        finally:
            con.close()
        assert got == [(LEDGER_SCHEMA_VERSION, 1, 1)]
        # New work after restart gets fresh collision-free ids, old rows intact.
        rt2.script = ["ok"]
        rev2 = rt2.observe()
        again = coord2.run(_spec(revision=rev2), owner="o")
        assert again.execution_id != first_eid
        assert again.attempt_id != first.attempt_id
        assert len(coord2.inspect(first_eid)) == 1  # untouched
        coord2.close()


def test_lane_forced_id_collision_fails_closed_without_overwriting_history(monkeypatch):
    with _tempdir() as td:
        ledger = Path(td) / "ledger.db"
        rt = FakeRuntime()
        coord = ExecutionCoordinator(rt, DeviceLeaseManager(),
                                     ledger_path=ledger, now_ms=lambda: 1000)
        first = coord.run(_spec(revision=rt.observe()), owner="o")
        before_calls = rt.device_calls
        first_execution_hex = first.execution_id.removeprefix("exe-")

        class FixedUuid:
            hex = first_execution_hex

        monkeypatch.setattr(coordinator_mod.uuid, "uuid4", lambda: FixedUuid())
        with pytest.raises(RuntimeError, match="EXECUTION_ID_COLLISION"):
            coord.run(_spec(revision=rt.observe()), owner="o")
        assert rt.device_calls == before_calls
        rows = coord.inspect(first.execution_id)
        assert len(rows) == 1
        assert rows[0].attempt_id == first.attempt_id
        assert rows[0].state == "succeeded"
        coord.close()


def test_lane_forced_attempt_id_collision_fails_closed_without_dispatch(monkeypatch):
    with _tempdir() as td:
        ledger = Path(td) / "ledger.db"
        rt = FakeRuntime()
        coord = ExecutionCoordinator(rt, DeviceLeaseManager(),
                                     ledger_path=ledger, now_ms=lambda: 1000)
        first = coord.run(_spec(revision=rt.observe()), owner="o")
        before_calls = rt.device_calls
        attempt_hex = first.attempt_id.removeprefix("att-")

        class ValueUuid:
            def __init__(self, value):
                self.hex = value

        values = iter([ValueUuid("f" * 32)] + [ValueUuid(attempt_hex)] * 16)
        monkeypatch.setattr(coordinator_mod.uuid, "uuid4", lambda: next(values))
        with pytest.raises(RuntimeError, match="ATTEMPT_ID_COLLISION"):
            coord.run(_spec(revision=rt.observe()), owner="o")
        assert rt.device_calls == before_calls
        rows = coord.inspect(first.execution_id)
        assert len(rows) == 1 and rows[0].attempt_id == first.attempt_id
        coord.close()


def test_lane_stale_first_batch_stops_before_later_mutation():
    with _tempdir() as td:
        coord, rt = _coord(Path(td))
        live = rt.observe()
        attempts = coord.run_batch(
            [_spec(revision="stale-revision"), _spec(revision=live)], owner="o")
        assert len(attempts) == 1
        assert attempts[0].state == "failed"
        assert attempts[0].evidence["error_code"] == "STALE_REVISION"
        assert rt.device_calls == 0
        coord.close()


def test_lane_restart_recovers_incomplete_dispatch_as_unknown_no_replay():
    class CrashAfterDispatchRuntime(FakeRuntime):
        def execute(self, actions, *, expected_revision: str):
            self.device_calls += 1
            raise SystemExit("simulated-process-crash-after-dispatch")

    with _tempdir() as td:
        ledger = Path(td) / "ledger.db"
        rt = CrashAfterDispatchRuntime()
        coord = ExecutionCoordinator(rt, DeviceLeaseManager(),
                                     ledger_path=ledger, now_ms=lambda: 1000)
        rev = rt.observe()
        with pytest.raises(SystemExit):
            coord.run(_spec(revision=rev), owner="o")
        con = sqlite3.connect(str(ledger))
        try:
            before = con.execute(
                "SELECT attempt_id,execution_id,state FROM attempts"
            ).fetchone()
        finally:
            con.close()
        assert before is not None and before[2] == "sent"

        coord2 = ExecutionCoordinator(FakeRuntime(), DeviceLeaseManager(),
                                      ledger_path=ledger, now_ms=lambda: 1001)
        recovered = coord2.inspect(before[1])
        assert len(recovered) == 1
        assert recovered[0].attempt_id == before[0]
        assert recovered[0].state == "unknown"
        assert recovered[0].effect == "UNKNOWN"
        assert recovered[0].retry_safe is False
        assert recovered[0].evidence["replayed"] is False
        assert recovered[0].evidence["crash_recovered"] is True
        coord2.close()


def test_lane_ledger_cleanup_never_drops_nonterminal():
    with _tempdir() as td:
        coord, rt = _coord(Path(td))
        rev = rt.observe()
        att = coord.run(_spec(revision=rev), owner="o")
        assert att.state in EXECUTION_TERMINAL | ATTEMPT_TERMINAL
        coord.close()


# --- cancellation / deadline -------------------------------------------------

def test_lane_cancel_and_deadline_prevent_next_mutation_no_orphan_lease():
    with _tempdir() as td:
        leases = DeviceLeaseManager()
        rt = FakeRuntime()
        coord = ExecutionCoordinator(rt, leases, ledger_path=Path(td) / "l.db",
                                     now_ms=lambda: 1000)
        coord.cancel()
        with pytest.raises(CancelledError):
            coord.run(_spec(revision=rt.observe()), owner="o")
        assert rt.device_calls == 0
        assert leases.holder("device-0") is None
        coord.close()

    with _tempdir() as td:
        clock = {"t": 5000}
        rt = FakeRuntime()
        coord = ExecutionCoordinator(rt, DeviceLeaseManager(),
                                     ledger_path=Path(td) / "l.db",
                                     now_ms=lambda: clock["t"])
        with pytest.raises((DeadlineError, ValueError)):
            coord.run(_spec(revision=rt.observe(), deadline_ms=1000), owner="o")
        assert rt.device_calls == 0
        coord.close()


# --- arbiter (A) --------------------------------------------------------------

def test_lane_arbiter_deadline_reversible_teaching_deterministic():
    urgent_unsafe = InterruptEvent(event_id="e-urgent", kind="goal", priority=95,
                                   reversibility="irreversible", risk="high")
    safe = InterruptEvent(event_id="e-safe", kind="goal", priority=40)
    res = arbitrate([urgent_unsafe, safe], current_goal="g", at_safe_boundary=True)
    assert res.selected_id == "e-safe" and "e-urgent" in res.rejected_ids

    rev_deadline = InterruptEvent(event_id="e-dl", kind="goal", priority=90,
                                  deadline_ms=100)
    normal = InterruptEvent(event_id="e-n", kind="goal", priority=10)
    preempt = arbitrate([rev_deadline, normal], current_goal="g",
                        at_safe_boundary=True, now_ms=50)
    assert preempt.selected_id == "e-dl"  # reversible deadline preempts
    expired = arbitrate([rev_deadline, normal], current_goal="g",
                        at_safe_boundary=True, now_ms=200)
    assert "e-dl" in expired.rejected_ids and expired.selected_id == "e-n"

    teach = [InterruptEvent(event_id="e-teach", kind="teaching", priority=99,
                            risk="high")]
    assert arbitrate(teach, current_goal="g",
                     at_safe_boundary=True).selected_id is None

    tie = [InterruptEvent(event_id="e-b", kind="goal", priority=50),
           InterruptEvent(event_id="e-a", kind="goal", priority=50)]
    assert arbitrate(tie, current_goal="g",
                     at_safe_boundary=True).selected_id == "e-a"


# --- reasoning (E) ------------------------------------------------------------

def test_lane_reasoning_tiers_triggers_and_chain():
    assert route(ReasoningSignals()).tier == "deterministic"
    assert route(ReasoningSignals(unknown_state=True)).tier == "lightweight"
    assert route(ReasoningSignals(conflicts_knowledge=True)).tier == "lightweight"
    assert route(ReasoningSignals(
        low_confidence_near_side_effect=True)).tier == "lightweight"
    assert route(ReasoningSignals(unexplained_transition=True)).tier == "lightweight"
    assert route(ReasoningSignals(
        teaching_contradicts_knowledge=True)).tier == "lightweight"
    assert route(ReasoningSignals(repeated_failures=2)).tier == "lightweight"
    assert route(ReasoningSignals(repeated_failures=3)).tier == "heavy"
    assert route(ReasoningSignals(security_boundary=True)).tier == "heavy"
    r = route(ReasoningSignals(unknown_state=True), latency_ms=7)
    assert (r.tier, r.latency_ms, bool(r.reason)) == ("lightweight", 7, True)
    assert escalation_chain("heavy") == ("deterministic", "lightweight", "heavy")
    with pytest.raises(ValueError):
        escalation_chain("llm-x")


# --- recovery (G) ---------------------------------------------------------------

def test_lane_recovery_bounded_reversible_escalate_scoped():
    planner = RecoveryPlanner([RecoveryTransition(transition_id="t-home",
                                                  from_state="off-goal:away",
                                                  to_state="home")])
    plan = planner.plan(goal_anchor="home",
                        world=WorldState(anchor_id="home",
                                         state_id="off-goal:away",
                                         revision="rev-3"))
    assert plan.steps and not plan.escalate

    loop = RecoveryPlanner([RecoveryTransition(transition_id="t-x",
                                                from_state="off-goal:loop",
                                                to_state="off-goal:loop")])
    assert len(loop.plan(goal_anchor="home",
                         world=WorldState(anchor_id="home",
                                          state_id="off-goal:loop")).steps) == 1
    second = loop.plan(goal_anchor="home",
                       world=WorldState(anchor_id="home",
                                        state_id="off-goal:loop"))
    assert second.escalate and not second.steps  # loop suppressed
    # note_failed keeps evidence scoped: other states unaffected.
    other = RecoveryPlanner(
        [RecoveryTransition(transition_id="t-x", from_state="s-a", to_state="s-b"),
         RecoveryTransition(transition_id="t-y", from_state="s-c", to_state="s-b")])
    other.note_failed("s-a", "t-x")
    assert other.plan(goal_anchor="s-b",
                      world=WorldState(anchor_id="s-b",
                                       state_id="s-c")).steps

    risky = RecoveryPlanner([RecoveryTransition(
        transition_id="t-pay", from_state="off-goal:store", to_state="home",
        reversible=False, risk="high")])
    bad = risky.plan(goal_anchor="home",
                     world=WorldState(anchor_id="home",
                                      state_id="off-goal:store"))
    assert bad.escalate and bad.steps == ()
    assert RecoveryPlanner([]).plan(
        goal_anchor="home",
        world=WorldState(anchor_id="home", state_id="mystery")).escalate
