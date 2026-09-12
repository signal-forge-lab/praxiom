"""R6 review-blocker repairs (freeze 20260906): regression guards.

Strengthen-only: each test fails on the pre-repair implementation and passes
after. No existing test is modified or weakened here. Workspace-local scratch
only (never tmp_path) to stay green under the sandbox file policy.
"""
import pytest

import praxiom.agent.coordinator as coordinator_mod
from praxiom.agent.coordinator import (
    CancelledError,
    DeviceLeaseManager,
    ExecutionCoordinator,
    ExecutionSpec,
)
from praxiom.knowledge.promotion import KnowledgeRecord, promote
from tests.fakes import FakeRuntime


def _spec(**kw):
    base = dict(namespace="ns", owner="op", task_type="t.safe",
                task_version=1, payload={"op": "home"}, revision="rev-1")
    base.update(kw)
    return ExecutionSpec(**base)


# --- repair 1: FakeRuntime lives in tests/, not src/ --------------------------


def test_review_fake_runtime_not_in_production_surface():
    assert not hasattr(coordinator_mod, "FakeRuntime")
    assert "FakeRuntime" not in coordinator_mod.__all__
    rt = FakeRuntime()
    rev = rt.observe()
    assert rt.execute([{"op": "home"}], expected_revision=rev)["effect"] == "NONE"
    assert rt.revision != rev  # attempted mutation invalidates the revision


# --- repair 2: contradicting evidence blocks promotion ------------------------


def test_review_contradicts_blocks_verification_and_promotion():
    rec = KnowledgeRecord(kid="k-contra", claim="anchor fact",
                          state="conflict_checked", supports=5, contradicts=1)
    blocked = promote(rec)
    assert blocked.to_state == "conflict_checked"
    assert "contradict" in blocked.reason
    # Clearing the contradiction resumes the lifecycle without data loss.
    rec.contradicts = 0
    assert promote(rec).to_state == "verified"
    rec.contradicts = 2
    held = promote(rec)
    assert held.to_state == "verified" and "contradict" in held.reason
    rec.contradicts = 0
    assert promote(rec).to_state == "promoted"


# --- repair 3: unexpected Runtime-port errors are recorded, never lost --------


class _FlakyPort(FakeRuntime):
    def __init__(self, failure: BaseException):
        super().__init__()
        self._failure = failure

    def execute(self, actions, *, expected_revision: str):
        raise self._failure


def test_review_unexpected_port_error_recorded_no_replay_no_orphan_lease():
    leases = DeviceLeaseManager()
    coord = ExecutionCoordinator(_FlakyPort(OSError("transport reset")),
                                 leases, device_id="dev-r")
    att = coord.run(_spec(revision="rev-1"), owner="o")
    assert att.state == "unknown"
    assert att.effect == "UNKNOWN"
    assert att.retry_safe is False
    assert att.evidence["replayed"] is False
    assert att.evidence["retry_safe"] is False
    assert att.evidence["revision_invalidated"] is True
    assert leases.holder("dev-r") is None  # terminal/no-orphan release
    assert coord.inspect(att.execution_id)[0].attempt_id == att.attempt_id
    coord.close()


def test_review_batch_stops_after_unexpected_port_error_until_reconciliation():
    leases = DeviceLeaseManager()
    coord = ExecutionCoordinator(_FlakyPort(OSError("transport reset")),
                                 leases, device_id="dev-b")
    attempts = coord.run_batch([_spec(revision="r1"), _spec(revision="r2")],
                               owner="o")
    assert len(attempts) == 1
    assert attempts[0].state == "unknown"
    assert attempts[0].effect == "UNKNOWN"
    assert attempts[0].retry_safe is False
    assert leases.holder("dev-b") is None
    coord.close()


def test_review_coordinator_cancel_still_propagates_from_port():
    leases = DeviceLeaseManager()
    coord = ExecutionCoordinator(_FlakyPort(CancelledError("cancelled")),
                                 leases, device_id="dev-c")
    with pytest.raises(CancelledError):
        coord.run(_spec(revision="rev-1"), owner="o")
    assert leases.holder("dev-c") is None
    coord.close()


# --- repair 4: ledger-less coordinators retain inspectable history ------------


def test_review_ledgerless_inspect_returns_recorded_attempts():
    coord = ExecutionCoordinator(FakeRuntime(), DeviceLeaseManager())
    rt = coord._rt
    att = coord.run(_spec(revision=rt.observe()), owner="o")
    rows = coord.inspect(att.execution_id)
    assert len(rows) == 1
    assert rows[0].attempt_id == att.attempt_id
    assert rows[0].state == "succeeded"
    assert coord.inspect("exe-missing") == []
    coord.close()
