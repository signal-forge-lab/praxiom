"""Phase A lane-T deterministic tests: run journal, correlation, reporting.

Covers the Phase A handoff categories owned by the telemetry lane (T):

- A1 journal ordering / schema / privacy / crash tolerance / determinism;
- A2 privacy-safe correlation fields (revision fingerprints, Runtime trace
  and Coordinator attempt/execution primitives, run-scoped ledger path);
- A8 rough improvement summary + learning snapshot projections.

Everything runs on deterministic injected clocks and on disposable
workspace-local state roots; no real device, network, or home-directory
access is performed. The telemetry package is additionally AST-scoped to
prove it stays purely observational (no Runtime/Agent imports, no
mutation-shaped calls).

Note: this execution sandbox denies pytest's ``tmp_path`` factory (same
environment denial documented in the retained R10 bounded-workflow
evidence), so each test derives an isolated state root under
``.tmp-phasea-telemetry/`` (pid-scoped, never inside ``src/``) instead.
The directory is disposable scratch and is not part of the change set.
"""

import ast
import json
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from praxiom.agent.coordinator import (
    Attempt,
    DeviceLeaseManager,
    ExecutionCoordinator,
    ExecutionSpec,
)
from praxiom.ios_runtime.models import ActionOutcome, ErrorCode
from praxiom.ios_runtime.trace import Trace
from praxiom.telemetry import (
    ALLOWED_EVENT_TYPES,
    JournalClosedError,
    JournalStats,
    JournalWriteError,
    RunContext,
    build_learning_snapshot,
    build_summary,
    fingerprint_revision,
    record_attempt,
    record_execution,
    record_runtime_trace,
    record_trace_record,
    resolve_state_root,
    sanitize_payload,
)
from fakes import FakeRuntime

# UDID-shaped / secret / screen-text probes that must never reach the disk.
_UDID_40 = "0123456789abcdef0123456789abcdef01234567"
_SECRET = "p4ssw0rd!"
_BUNDLE_ID = "com.example.secretapp"
_SCREEN_TEXT = "Welcome to the secret screen"
_SCRATCH_ROOT = Path(__file__).resolve().parents[1] / ".tmp-phasea-telemetry"


@pytest.fixture(scope="module", autouse=True)
def _cleanup_workspace_scratch():
    """Keep the repository clean after normal Phase A test execution."""
    shutil.rmtree(_SCRATCH_ROOT, ignore_errors=True)
    yield
    shutil.rmtree(_SCRATCH_ROOT, ignore_errors=True)


def _state_root(request: pytest.FixtureRequest, *parts: str) -> Path:
    """Disposable, pid-scoped scratch state root for one test."""
    root = (
        _SCRATCH_ROOT
        / f"{request.node.name}-{os.getpid()}"
    )
    for part in parts:
        root = root / part
    root.mkdir(parents=True, exist_ok=True)
    return root


class StepClock:
    """Deterministic ts/mono pair: event k gets base ts + (k-1) * 1000 ms."""

    def __init__(self, start: str = "2026-09-09T12:00:00.000Z") -> None:
        self._t = datetime.fromisoformat(start.replace("Z", "+00:00"))
        self._mono = 1_000_000

    def ts(self) -> str:
        value = self._t.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        self._t += timedelta(milliseconds=1000)
        return value

    def mono(self) -> int:
        self._mono += 5_000_000
        return self._mono


def _make_journal(root: Path, run_id: str = "run-test", clock: StepClock | None = None):
    ctx = RunContext.create(state_root=root, run_id=run_id)
    clock = clock or StepClock()
    return ctx.open_journal(ts_fn=clock.ts, mono_fn=clock.mono), ctx, clock


def _read_lines(path: Path) -> list[dict]:
    events = []
    for line in path.read_bytes().split(b"\n"):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue  # torn fragment: preserved on disk, skipped here
    return events


# --- A1: schema, ordering, determinism ---------------------------------------


def test_phasea_journal_schema_ordering_append_only(request):
    journal, ctx, _ = _make_journal(_state_root(request))
    first = journal.emit("run.started", phase="run")
    second = journal.emit(
        "runtime.observe", phase="observe", duration_ms=10.0,
        execution_id="exe-abc", correlation_id="corr-1",
    )

    assert first["seq"] == 1 and second["seq"] == 2
    assert first["event_id"] == "evt-000001"
    assert "parent_event_id" not in second
    for event in (first, second):
        assert event["schema_version"] == 1
        assert event["run_id"] == "run-test"
        for core in ("seq", "ts_utc", "monotonic_ns", "event_type", "payload"):
            assert core in event
    assert second.get("duration_ms") == 10.0

    raw_before = ctx.events_path.read_bytes()
    journal.emit("run.completed", phase="run")
    raw_after = ctx.events_path.read_bytes()
    # Append-only: prior bytes are a byte-exact prefix of the grown file.
    assert raw_after.startswith(raw_before)

    lines = _read_lines(ctx.events_path)
    assert [e["seq"] for e in lines] == [1, 2, 3]
    # Canonical serialization: re-dumping any parsed line is byte-identical.
    for line in ctx.events_path.read_bytes().split(b"\n"):
        if not line.strip():
            continue
        parsed = json.loads(line.decode("utf-8"))
        redumped = json.dumps(
            parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        assert redumped.encode("utf-8") == line


def test_phasea_journal_bytes_are_deterministic(request):
    emits = [
        ("run.started", dict(phase="run")),
        ("runtime.execute", dict(
            phase="execute", duration_ms=100.0, revision="rev-token-1",
            payload={"action_count": 2, "action_kinds": ["tap_point", "home"]},
        )),
        ("run.completed", dict(phase="run")),
    ]
    root = _state_root(request)
    digests = []
    for part in ("a", "b"):
        journal, ctx, _ = _make_journal(
            root / part, run_id="run-det", clock=StepClock())
        for event_type, fields in emits:
            journal.emit(event_type, **fields)
        digests.append(ctx.events_path.read_bytes())
    assert digests[0] == digests[1]
    assert digests[0] != b""


# --- A1: fail-safe privacy allowlist -----------------------------------------


def test_phasea_privacy_allowlist_fail_safe(request):
    journal, ctx, _ = _make_journal(_state_root(request))
    event = journal.emit(
        "runtime.execute",
        phase="execute",
        skill_id="demo.skill",
        revision="raw-revision-token-4f3a",
        payload={
            "error_code": "ACTION_FAILED",          # allowlisted machine field
            "bundle_id": _BUNDLE_ID,                # forbidden key
            "device_udid": _UDID_40,                # forbidden key
            "screen_text": _SCREEN_TEXT,            # forbidden key
            "action_payload": {"op": "tap", "x": 1},  # forbidden key
            "skilltrust_token": "stt-never-persist-me",  # forbidden key
        },
    )

    assert event["payload"] == {
        "error_code": "ACTION_FAILED",
        "redacted_keys": 5,
    }
    assert event["revision_ref"].startswith("fp:")
    assert "raw-revision-token-4f3a" not in json.dumps(event)

    raw = ctx.events_path.read_text(encoding="utf-8")
    for forbidden in (
        _UDID_40, _SECRET, _BUNDLE_ID, _SCREEN_TEXT, "stt-never-persist-me",
        "bundle_id", "device_udid", "screen_text", "action_payload",
        "skilltrust_token", "raw-revision-token-4f3a",
    ):
        assert forbidden not in raw


def test_phasea_payload_bounds_enforced():
    assert sanitize_payload(None) == {}
    assert sanitize_payload("not-a-dict") == {"redacted_keys": 1}

    long_list = sanitize_payload({"action_kinds": [f"kind{i}" for i in range(20)]})
    assert len(long_list["action_kinds"]) == 16
    assert long_list["truncated_items"] == 4

    huge_int = sanitize_payload({"action_count": 10**16})
    assert "action_count" not in huge_int and huge_int["redacted_keys"] == 1

    nonfinite = sanitize_payload({"confidence": float("nan")})
    assert "confidence" not in nonfinite and nonfinite["redacted_keys"] == 1

    counters = sanitize_payload({"counters": {f"k{i}": i for i in range(12)}})
    assert len(counters["counters"]) == 8 and counters["redacted_keys"] == 4

    oversize_token = "x" * 200
    token = sanitize_payload({"detail": oversize_token})
    assert token["detail"].startswith("fp:") and oversize_token not in str(token)

    from praxiom.telemetry.journal import build_event

    event = build_event(
        run_id="run-x",
        seq=1,
        ts_utc="2026-09-09T12:00:00.000Z",
        monotonic_ns=1,
        event_type="runtime.execute",
        phase="execute",
        duration_ms=float("nan"),
        payload={"confidence": float("inf")},
    )
    assert "duration_ms" not in event
    assert event["payload"]["redacted_keys"] == 2  # nan duration + inf payload


def test_phasea_payload_byte_cap_collapses(monkeypatch):
    import praxiom.telemetry.journal as journal_module

    monkeypatch.setattr(journal_module, "MAX_PAYLOAD_BYTES", 64)
    collapsed = sanitize_payload({
        "error_code": "ACTION_FAILED",
        "detail": "d" * 96,
    })
    assert set(collapsed) <= {"redacted_keys", "truncated_items"}
    assert collapsed["redacted_keys"] >= 2


def test_phasea_structural_fields_fail_closed():
    from praxiom.telemetry.journal import build_event

    with pytest.raises(ValueError):
        build_event(
            run_id="run-x", seq=0, ts_utc="t", monotonic_ns=0,
            event_type="run.started",
        )
    with pytest.raises(ValueError):
        build_event(
            run_id="run-x", seq=1, ts_utc="t", monotonic_ns=0,
            event_type="not-an-allowed-type",
        )
    with pytest.raises(ValueError):
        build_event(
            run_id="run-x", seq=1, ts_utc="t", monotonic_ns=0,
            event_type="run.started", phase="not-a-phase",
        )
    with pytest.raises(ValueError):
        build_event(
            run_id="run-x", seq=1, ts_utc="t", monotonic_ns=0,
            event_type="run.started",
            revision="tok", revision_ref="fp:0123456789abcdef",
        )
    # Fail-safe content fields: unknown status/outcome/visual_hint dropped.
    event = build_event(
        run_id="run-x", seq=1, ts_utc="2026-09-09T12:00:00.000Z",
        monotonic_ns=1, event_type="runtime.observe", phase="observe",
        status="mega-secret-status", outcome="SORT-OF", visual_hint="raw-bytes",
    )
    assert "status" not in event and "outcome" not in event
    assert "visual_hint" not in event
    assert event["payload"]["redacted_keys"] == 3
    assert len(ALLOWED_EVENT_TYPES) >= 20  # bounded, explicit allowlist


# --- A1: crash / restart tolerance --------------------------------------------


def test_phasea_crash_torn_tail_is_preserved_and_skipped(request):
    journal, ctx, clock = _make_journal(_state_root(request), run_id="run-torn")
    journal.emit("run.started", phase="run")
    journal.emit("runtime.observe", phase="observe", duration_ms=5.0)
    journal.abandon()  # crash: no projections, no clean close

    with open(ctx.events_path, "ab") as handle:  # torn mid-line append
        handle.write(b'{"seq":3,"event_type":"run.comp')

    recovered = ctx.open_journal(ts_fn=clock.ts, mono_fn=clock.mono)
    stats = recovered.stats
    assert stats.torn_records == 1 and stats.malformed_records == 0
    # 2 valid pre-crash events + the journal.recovered marker.
    assert stats.records == 3
    recovered_event = recovered.events()[-1]
    assert recovered_event["event_type"] == "journal.recovered"
    assert recovered_event["payload"]["torn_records"] == 1
    assert recovered_event["seq"] == 3

    follow_up = recovered.emit("run.completed", phase="run")
    assert follow_up["seq"] == 4

    raw = ctx.events_path.read_bytes()
    assert b'"event_type":"run.comp' in raw  # torn bytes preserved on disk
    parsed = _read_lines(ctx.events_path)
    assert [e["seq"] for e in parsed] == [1, 2, 3, 4]
    assert [e["event_type"] for e in parsed] == [
        "run.started", "runtime.observe", "journal.recovered", "run.completed",
    ]


def test_phasea_restart_summary_covers_full_history(request):
    journal, ctx, clock = _make_journal(
        _state_root(request), run_id="run-restart")
    journal.emit("run.started", phase="run")
    journal.emit("runtime.observe", phase="observe", duration_ms=25.0)
    journal.abandon()

    reopened = ctx.open_journal(ts_fn=clock.ts, mono_fn=clock.mono)
    reopened.emit("run.completed", phase="run")
    summary = reopened.close()

    stored = json.loads(ctx.summary_path.read_text(encoding="utf-8"))
    assert stored == summary
    assert stored["events"]["total"] == 3
    assert stored["observe"]["count"] == 1
    assert stored["run"]["duration_ms"] == 2000.0  # 3 emits * 1000ms spacing
    assert ctx.learning_snapshot_path.exists()


def test_phasea_emit_failures_never_invent_success(request):
    journal, ctx, _ = _make_journal(_state_root(request), run_id="run-fail")
    ok = journal.emit("run.started", phase="run")
    assert ok["seq"] == 1

    def _boom(_data: bytes) -> None:
        raise OSError("simulated disk failure")

    journal._append = _boom
    with pytest.raises(JournalWriteError):
        journal.emit("runtime.observe", phase="observe", duration_ms=1.0)
    # Sequence did not advance; no partial line reached the file.
    assert journal.stats.records == 1
    lines = _read_lines(ctx.events_path)
    assert [e["seq"] for e in lines] == [1]

    journal.close()
    with pytest.raises(JournalClosedError):
        journal.emit("run.completed", phase="run")


def test_phasea_projection_failure_is_retryable(request, monkeypatch):
    import praxiom.telemetry.journal as journal_module

    journal, ctx, _ = _make_journal(
        _state_root(request), run_id="run-projection-retry")
    journal.emit("run.started", phase="run")
    journal.emit("run.completed", phase="run")
    original_write = journal_module._atomic_write_json
    failed = False

    def _fail_snapshot_once(path, payload):
        nonlocal failed
        if path == ctx.learning_snapshot_path and not failed:
            failed = True
            raise OSError("forced projection failure")
        return original_write(path, payload)

    monkeypatch.setattr(journal_module, "_atomic_write_json", _fail_snapshot_once)
    with pytest.raises(JournalWriteError):
        journal.close()
    assert journal._closed is True
    assert ctx.summary_path.exists()
    assert not ctx.learning_snapshot_path.exists()

    summary = journal.close()
    assert summary["events"]["by_type"]["run.completed"] == 1
    assert ctx.learning_snapshot_path.exists()


def test_phasea_revision_ref_is_stable_opaque_fingerprint(request):
    journal, ctx, _ = _make_journal(_state_root(request), run_id="run-fp")
    token = "revision-opaque-9f8e7d6c"
    first = journal.emit("runtime.observe", phase="observe", revision=token)
    second = journal.emit("runtime.observe", phase="observe", revision=token)
    other = journal.emit(
        "runtime.observe", phase="observe", revision="different-token")

    assert first["revision_ref"] == second["revision_ref"]
    assert first["revision_ref"] != other["revision_ref"]
    assert first["revision_ref"] == fingerprint_revision(token)
    assert first["revision_ref"].startswith("fp:")
    assert len(first["revision_ref"]) == len("fp:") + 16
    assert token not in ctx.events_path.read_text(encoding="utf-8")
    # Already-fingerprinted refs pass through unchanged.
    assert fingerprint_revision(first["revision_ref"]) == first["revision_ref"]


# --- A2: correlation primitives ------------------------------------------------


def test_phasea_trace_bridge_correlates_runtime_trace(request):
    journal, ctx, _ = _make_journal(_state_root(request), run_id="run-trace")
    trace = Trace()
    trace.record(
        "execute",
        started=Trace.start(),
        outcomes=(
            ActionOutcome(index=0, kind="tap_point", duration_ms=12.0),
            ActionOutcome(index=1, kind="home", duration_ms=3.0),
        ),
        error_code=ErrorCode.ACTION_FAILED,
        failed_action_index=1,
    )
    trace.record(
        "invalidate", started=Trace.start(), detail="fp:0123456789abcdef")

    events = record_runtime_trace(
        journal, trace, execution_id="exe-777", correlation_id="corr-9")
    assert [e["event_type"] for e in events] == [
        "runtime.execute", "runtime.invalidate"]
    execute_event = events[0]
    assert execute_event["phase"] == "execute"
    assert execute_event["execution_id"] == "exe-777"
    assert execute_event["correlation_id"] == "corr-9"
    assert execute_event["payload"]["action_count"] == 2
    assert execute_event["payload"]["action_kinds"] == ["tap_point", "home"]
    assert execute_event["payload"]["error_code"] == "ACTION_FAILED"
    assert execute_event["payload"]["failed_action_index"] == 1
    assert isinstance(execute_event["duration_ms"], float)
    assert events[1]["phase"] == "invalidate"
    assert "runtime.execute" in ctx.events_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError):
        record_trace_record(journal, type("R", (), {"operation": "observe_all"})())


def test_phasea_attempt_bridge_maps_identity_and_effect(request):
    journal, ctx, _ = _make_journal(_state_root(request), run_id="run-att")
    spec = ExecutionSpec(
        namespace="demo-ns",
        owner="demo-owner",
        task_type="demo.skill",
        task_version=3,
        payload={"op": "home"},
        revision="raw-spec-revision-token",
    )
    planned = Attempt(attempt_id="att-1", execution_id="exe-1", state="planned")
    sent = Attempt(attempt_id="att-1", execution_id="exe-1", state="sent")
    failed = Attempt(
        attempt_id="att-1", execution_id="exe-1", state="failed",
        effect="PARTIAL",
        evidence={
            "effect": "PARTIAL", "error_code": "ACTION_FAILED",
            "completed": 1, "replayed": False, "retry_safe": False,
            "revision_invalidated": True,
        },
    )

    e1 = record_attempt(journal, planned, spec)
    e2 = record_attempt(journal, sent, spec, parent_event_id=e1["event_id"])
    e3 = record_attempt(journal, failed, spec, parent_event_id=e2["event_id"])

    assert [e["event_type"] for e in (e1, e2, e3)] == [
        "attempt.planned", "attempt.sent", "attempt.completed"]
    assert e3["status"] == "failed" and e3["outcome"] == "PARTIAL"
    assert e3["domain"] == "demo-ns"
    assert e3["skill_id"] == "demo.skill"
    assert e3["skill_version"] == "3"
    assert e3["attempt_id"] == "att-1" and e3["execution_id"] == "exe-1"
    assert e3["parent_event_id"] == "evt-000002"
    assert e3["revision_ref"] == fingerprint_revision("raw-spec-revision-token")
    assert e3["payload"]["error_code"] == "ACTION_FAILED"
    assert e3["payload"]["revision_invalidated"] is True
    raw = ctx.events_path.read_text(encoding="utf-8")
    assert "raw-spec-revision-token" not in raw
    assert '"op"' not in raw  # spec payload is never read by the bridge

    execution = type("E", (), {"execution_id": "exe-1", "state": "created"})()
    parent = record_execution(journal, execution, spec)
    assert parent["event_type"] == "execution.created"
    assert parent["phase"] == "sequence"
    assert parent["skill_id"] == "demo.skill"


def test_phasea_run_scoped_ledger_primitive(request):
    """A2 primitive: the run-scoped ledger path keeps Coordinator durability
    inside the run directory without touching shared coordinator wiring."""
    ctx = RunContext.create(state_root=_state_root(request), run_id="run-ledger")
    assert ctx.ledger_path == ctx.run_dir / "coordinator-ledger.db"
    assert not ctx.ledger_path.exists()  # created by Coordinator, not here

    runtime = FakeRuntime()
    revision = runtime.observe()
    coordinator = ExecutionCoordinator(
        runtime, DeviceLeaseManager(), ledger_path=ctx.ledger_path)
    assert coordinator.ledger_schema_version == 1

    spec = ExecutionSpec(
        namespace="ns", owner="owner", task_type="ledger.skill",
        task_version=1, payload={"op": "home"}, revision=revision,
    )
    attempt = coordinator.run(spec, owner="tester")
    assert attempt.state == "succeeded"
    coordinator.close()
    assert ctx.ledger_path.exists()

    # Restart inspection: the durable ledger reopens from the run directory.
    reopened = ExecutionCoordinator(
        runtime, DeviceLeaseManager(), ledger_path=ctx.ledger_path)
    rows = reopened.inspect(attempt.execution_id)
    assert [row.state for row in rows] == ["succeeded"]
    reopened.close()

    clock = StepClock()
    journal = RunContext.create(
        state_root=Path(ctx.state_root), run_id="run-ledger-j"
    ).open_journal(ts_fn=clock.ts, mono_fn=clock.mono)
    event = record_attempt(journal, attempt, spec)
    assert event["event_type"] == "attempt.completed"
    assert event["skill_id"] == "ledger.skill"
    assert event["status"] == "succeeded" and event["outcome"] == "NONE"
    # The ledger stays the safety record; the journal stays observational.
    assert ctx.events_path.name == "events.jsonl"
    assert not ctx.events_path.exists() or "coordinator" not in (
        ctx.events_path.read_text(encoding="utf-8"))


# --- A8: rough summary + learning snapshot -------------------------------------


def _emit_a8_scenario(journal):
    journal.emit("run.started", phase="run")
    for duration in (10.0, 20.0, 30.0, 40.0, 50.0):
        journal.emit("runtime.observe", phase="observe", duration_ms=duration)
    journal.emit("runtime.execute", phase="execute", duration_ms=100.0,
                 payload={"action_count": 2})
    journal.emit("runtime.execute", phase="execute", duration_ms=200.0,
                 payload={"action_count": 3})
    for mode in ("full", "full", "cheap_validate"):
        journal.emit("validation.performed", phase="validation",
                     payload={"observe_mode": mode})
    journal.emit("policy.decision", phase="policy",
                 policy_recommendation="full-observe",
                 actual_policy="certified-safe-behavior",
                 payload={"recommended": True, "recommended_batch_size": 3,
                          "actual_batch_size": 1})
    journal.emit("policy.decision", phase="policy",
                 policy_recommendation="full-observe",
                 actual_policy="certified-safe-behavior",
                 payload={"recommended": False, "recommended_batch_size": 1,
                          "actual_batch_size": 1})
    journal.emit("sequence.decision", phase="sequence",
                 payload={"actual_batch_size": 3})
    journal.emit("sequence.decision", phase="sequence",
                 payload={"actual_batch_size": 1})
    journal.emit("runtime.recover", phase="recovery", payload={"repaired": True})
    journal.emit("runtime.recover", phase="recovery", payload={"repaired": False})
    journal.emit("attempt.completed", phase="attempt", status="failed",
                 outcome="PARTIAL", payload={"error_code": "ACTION_FAILED"})
    journal.emit("attempt.completed", phase="attempt", status="unknown",
                 outcome="UNKNOWN", payload={"error_code": "EFFECT_UNKNOWN"})
    journal.emit("policy.decision", phase="policy",
                 policy_recommendation="batch-2", actual_policy="batch-1",
                 fallback_reason="state-sensitive")
    journal.emit("policy.decision", phase="policy",
                 policy_recommendation="batch-1", actual_policy="batch-1")
    journal.emit("policy.decision", phase="policy",
                 policy_recommendation="observe-cheap",
                 actual_policy="observe-cheap", fallback_reason="state-sensitive")
    journal.emit("policy.decision", phase="policy",
                 policy_recommendation="observe-cheap",
                 actual_policy="observe-cheap", fallback_reason="human-gated")
    journal.emit("learning.recorded", phase="learning",
                 payload={"candidate_kind": "macro", "recommended": True})
    journal.emit("learning.recorded", phase="learning",
                 payload={"candidate_kind": "macro", "recommended": False})
    journal.emit("learning.recorded", phase="learning",
                 payload={"candidate_kind": "path", "recommended": True})
    journal.emit("artifacts.reserved", phase="artifacts",
                 visual_hint="post-action",
                 artifact_refs=[{"artifact_id": "a1", "kind": "clip",
                                 "status": "reserved", "format": "h264"}])
    journal.emit("run.completed", phase="run")


def test_phasea_summary_reports_a8_fields(request):
    journal, ctx, _ = _make_journal(_state_root(request), run_id="run-a8")
    _emit_a8_scenario(journal)
    summary = journal.close()

    assert summary["kind"] == "run-summary"
    assert summary["run"]["run_id"] == "run-a8"
    assert summary["run"]["duration_ms"] == 27000.0  # 28 emits, 1000ms apart

    assert summary["observe"] == {
        "count": 5, "total_ms": 150.0, "median_ms": 30.0, "p90_ms": 50.0}
    assert summary["execute"] == {
        "count": 2, "total_ms": 300.0, "median_ms": 200.0, "p90_ms": 200.0}
    assert summary["actions"] == {
        "count": 5, "execute_batch_sizes": {"2": 1, "3": 1}}
    assert summary["validation"] == {"full_observe": 2, "cheap_validate": 1}
    assert summary["sequences"] == {
        "shadow_recommended_sizes": {"1": 1, "3": 1},
        "actual_sizes": {"1": 1, "3": 1},
    }
    assert summary["recovery"] == {"attempts": 2, "successes": 1}
    assert summary["failures"]["by_effect"] == {"PARTIAL": 1, "UNKNOWN": 1}
    assert summary["failures"]["by_error_code"] == {
        "ACTION_FAILED": 1, "EFFECT_UNKNOWN": 1}
    assert summary["fallbacks"]["reasons"] == {
        "human-gated": 1, "state-sensitive": 2}
    assert summary["policy"]["decisions"] == 6
    assert summary["policy"]["shadow_divergences"] == 3
    assert summary["policy"]["divergence_pairs"] == {
        "batch-2|batch-1|state-sensitive": 1,
        "full-observe|certified-safe-behavior|": 2,
    }
    assert summary["learning"] == {
        "records": 3,
        "candidates_by_kind": {"macro": 2, "path": 1},
        "reuse_recommended": 2,
    }
    assert summary["artifacts"] == {"reserved_refs": 1}
    assert summary["events"]["total"] == 28
    assert summary["events"]["torn_records"] == 0

    stored = json.loads(ctx.summary_path.read_text(encoding="utf-8"))
    assert stored == summary
    snapshot = json.loads(ctx.learning_snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["kind"] == "learning-snapshot"
    # Summary is a derived cache: empty projection for an empty journal.
    assert build_summary([])["observe"]["count"] == 0


def test_phasea_summary_is_deterministic(request):
    root = _state_root(request)
    summaries = []
    for part in ("x", "y"):
        journal, _, _ = _make_journal(
            root / part, run_id="run-sumdet", clock=StepClock())
        _emit_a8_scenario(journal)
        summaries.append(journal.close())
    assert summaries[0] == summaries[1]


def test_phasea_learning_snapshot_evidence_facts_only(request):
    journal, _, _ = _make_journal(_state_root(request), run_id="run-snap")
    for index in range(10):
        journal.emit(
            "attempt.completed", phase="attempt",
            execution_id=f"exe-{index:02d}", attempt_id=f"att-{index:02d}",
            domain="ns", skill_id="snap.skill", skill_version="2",
            status="succeeded", outcome="NONE",
        )
    journal.emit(
        "attempt.completed", phase="attempt",
        execution_id="exe-other", domain="ns", skill_id="snap.skill",
        skill_version="2", status="unknown", outcome="UNKNOWN",
        payload={"error_code": "EFFECT_UNKNOWN"},
    )
    snapshot = build_learning_snapshot(
        journal.events(), run_id="run-snap",
        generated_utc="2026-09-09T12:00:00.000Z")

    assert snapshot["token_authority_persisted"] is False
    assert snapshot["episode_count"] == 1
    assert snapshot["truncated_episodes"] == 0
    episode = snapshot["episodes"][0]
    assert episode["domain"] == "ns"
    assert episode["skill_id"] == "snap.skill"
    assert episode["skill_version"] == "2"
    assert episode["attempts"] == 11
    assert episode["effects"] == {"NONE": 10, "UNKNOWN": 1}
    assert len(episode["execution_ids"]) == 8  # bounded unique references
    assert snapshot["totals"]["attempts"] == 11
    assert snapshot["totals"]["effects"] == {"NONE": 10, "UNKNOWN": 1}

    text = json.dumps(snapshot)
    assert "EFFECT_UNKNOWN" not in text  # failure classes are counts only
    assert "stt-" not in text  # no token-shaped authority material

    oversize = build_learning_snapshot(
        [
            {"event_type": "attempt.completed", "domain": f"d{i}",
             "skill_id": "s", "skill_version": "1", "seq": i}
            for i in range(300)
        ],
        run_id="run-snap",
    )
    assert oversize["episode_count"] == 256
    assert oversize["truncated_episodes"] == 44


# --- A1/D4 hooks: artifacts and visual hints are metadata only ------------------


def test_phasea_artifacts_and_visual_hints_are_metadata_only(request):
    journal, ctx, _ = _make_journal(_state_root(request), run_id="run-art")
    event = journal.emit(
        "artifacts.reserved",
        phase="artifacts",
        visual_hint="post-action",
        artifact_refs=[
            {"artifact_id": "art-1", "kind": "clip", "status": "reserved",
             "format": "h264"},
            {"artifact_id": "art-2", "kind": "frameset", "bytes": "ff"},
            "not-a-mapping",
        ],
    )
    assert event["visual_hint"] == "post-action"
    assert event["artifact_refs"] == [
        {"artifact_id": "art-1", "kind": "clip", "status": "reserved",
         "format": "h264"},
        {"artifact_id": "art-2", "kind": "frameset"},  # "bytes" key dropped
    ]
    assert event["payload"]["redacted_keys"] == 2  # bytes key + non-mapping ref

    hintless = journal.emit(
        "artifacts.reserved", phase="artifacts", visual_hint="raw-screenshot")
    assert "visual_hint" not in hintless

    raw = ctx.events_path.read_text(encoding="utf-8")
    for forbidden in ("bytes", "raw-screenshot", "screenshot"):
        assert forbidden not in raw
    assert ctx.artifacts_dir.is_dir()  # reserved layout, nothing written


# --- state root configuration ----------------------------------------------------


def test_phasea_state_root_configurable_and_external_by_default(request):
    assert resolve_state_root({}) == Path.home() / ".praxiom"
    external = _state_root(request, "env-root")
    assert resolve_state_root(
        {"PRAXIOM_STATE_ROOT": str(external)}) == external

    root = _state_root(request, "layout")
    ctx = RunContext.create(state_root=root, run_id="run-layout")
    assert ctx.run_dir == root / "runs" / "run-layout"
    assert ctx.events_path.name == "events.jsonl"
    assert ctx.summary_path.name == "summary.json"
    assert ctx.learning_snapshot_path.name == "learning_snapshot.json"
    assert ctx.artifacts_dir.is_dir()
    assert ctx.ledger_path.name == "coordinator-ledger.db"
    assert ctx.created_utc.startswith("20")
    # The configured root is scratch, never the repository source tree.
    assert "src" not in root.parts


# --- observational isolation of the telemetry package ----------------------------


def test_phasea_telemetry_package_is_observational_only():
    """AST proof: telemetry imports no Runtime/Agent/Skill/Domain module and
    makes no mutation-shaped calls. (``close`` is excluded: the journal
    closes its own file handle; with imports banned, no Runtime receiver
    even exists in this package.)"""
    package_dir = Path(__file__).resolve().parents[1] / "src" / "praxiom" / "telemetry"
    banned_import_roots = (
        "praxiom.ios_runtime", "praxiom.agent", "praxiom.skill",
        "praxiom.domain", "praxiom.adaptive",
    )
    banned_ops = {"status", "observe", "execute", "invalidate", "recover"}
    violations: list[str] = []
    for path in sorted(package_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for root in banned_import_roots:
                    if node.module == root or node.module.startswith(root + "."):
                        violations.append(
                            f"{path.name}:{node.lineno}: import {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for root in banned_import_roots:
                        if alias.name == root or alias.name.startswith(root + "."):
                            violations.append(
                                f"{path.name}:{node.lineno}: import {alias.name}")
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in banned_ops:
                    violations.append(f"{path.name}:{node.lineno}: call .{func.attr}()")
                if isinstance(func, ast.Name) and func.id in banned_ops:
                    violations.append(f"{path.name}:{node.lineno}: call {func.id}()")
    assert violations == []
