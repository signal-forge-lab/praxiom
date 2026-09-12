"""Phase A integration pass: one shared closed loop, end to end.

Deterministic acceptance for the single integration owner's wiring across
the landed lanes (frozen decisions D1=A..D5=A):

- ``ExecutionCoordinator.run_sequence``: whole-sequence preflight with zero
  device calls on rejection, one lease, exactly one Runtime
  ``execute([...], expected_revision=R)`` call, fail-closed stale /
  PARTIAL / UNKNOWN (no continuation, no retry, no replay), durable ledger
  rows, unchanged ``run_batch`` semantics;
- ``RunSession``: durable run journal + run-scoped Coordinator ledger in
  normal live-run construction, automatic Experience extraction persisted
  under the state root, actual-versus-shadow policy decisions journaled
  (live control stays OFF), bounded-sequence decision evidence, metadata-
  only visual hints, Runtime trace draining, fail-loud journal semantics;
- transport-neutral discovery + in-process Wi-Fi RSD wiring guards (D5=A)
  and the untouched six-operation Runtime public surface;
- privacy: no raw secrets, device identifiers, IPs, bundle ids, screen
  text, action payloads, or trust-token authority anywhere on disk; raw
  revision tokens appear only as fingerprints;
- cross-run Experience rebinding requires a fresh live registry token.

Environment note (documented precedent, retained R10 evidence): this
sandbox denies pytest's ``tmp_path`` factory, so every test derives a
disposable workspace-local state root under ``.tmp-phasea-integration/``
(pid-scoped, never inside ``src/``). No real device, network, or home
directory is touched.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
from pathlib import Path

import pytest

from praxiom.agent.coordinator import (
    CancelledError,
    DeviceLeaseManager,
    ExecutionCoordinator,
    ExecutionSpec,
    SpecValidationError,
)
from praxiom.adaptive.experience_bridge import rebind_history
from praxiom.knowledge.experience_store import ExperienceStore
from praxiom.skill.candidate import SkillCandidate
from praxiom.skill.executor import SkillExecutionError, SequenceStep
from praxiom.skill.registry import SkillRegistry
from praxiom.session import RunSession
from praxiom.telemetry.journal import JournalClosedError
from fakes import FakeRuntime

_SCRATCH_ROOT = Path(__file__).resolve().parents[1] / ".tmp-phasea-integration"


@pytest.fixture(scope="module", autouse=True)
def _cleanup_workspace_scratch():
    """Keep the repository clean after normal Phase A test execution."""
    shutil.rmtree(_SCRATCH_ROOT, ignore_errors=True)
    yield
    shutil.rmtree(_SCRATCH_ROOT, ignore_errors=True)


def _state_root(request: pytest.FixtureRequest) -> Path:
    """Disposable, pid-scoped scratch state root for one test."""
    root = _SCRATCH_ROOT / f"{request.node.name}-{os.getpid()}"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cand(**kw) -> SkillCandidate:
    base = dict(skill_id="int-1", version=1, inputs=("x",), outputs=("y",),
                preconditions=("revision-bound: rev-1", "fact-a"),
                postconditions=("done",), risk="low", reversibility="reversible",
                authority=frozenset({"tap_point", "swipe", "home"}),
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


class RecordingRuntime(FakeRuntime):
    """FakeRuntime plus exact dispatch recording (tests only)."""

    def __init__(self) -> None:
        super().__init__()
        self.execute_calls: list[tuple[list[dict], str]] = []

    def execute(self, actions, *, expected_revision):
        self.execute_calls.append(
            ([dict(a) for a in actions], expected_revision))
        return super().execute(actions, expected_revision=expected_revision)


def _events(journal) -> list[dict]:
    return [dict(e) for e in journal.events()]


def _types(events: list[dict]) -> list[str]:
    return [e["event_type"] for e in events]


# --- coordinator.run_sequence: the one Runtime call -----------------------------


def test_run_sequence_one_lease_one_runtime_call_for_n_actions():
    rt = RecordingRuntime()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    revision = rt.observe()
    specs = [
        ExecutionSpec(namespace="skill", owner="skill-executor",
                      task_type="int-1", task_version=1,
                      payload={"op": "tap_point", "x": 1}, revision=revision),
        ExecutionSpec(namespace="skill", owner="skill-executor",
                      task_type="int-1", task_version=1,
                      payload={"op": "swipe"}, revision=revision),
        ExecutionSpec(namespace="skill", owner="skill-executor",
                      task_type="int-1", task_version=1,
                      payload={"op": "tap_point"}, revision=revision),
    ]
    attempt = coord.run_sequence(specs, owner="skill-executor")
    # Exactly one Runtime execute call carrying ALL payloads + one revision.
    assert len(rt.execute_calls) == 1
    actions, bound = rt.execute_calls[0]
    assert [a["op"] for a in actions] == ["tap_point", "swipe", "tap_point"]
    assert bound == revision
    assert rt.device_calls == 1
    assert attempt.state == "succeeded" and attempt.effect == "NONE"
    assert attempt.evidence["action_count"] == 3
    assert attempt.evidence["completed"] == 3
    assert attempt.evidence["replayed"] is False
    assert attempt.evidence["retry_safe"] is False
    assert attempt.evidence["revision_invalidated"] is True
    # One parent execution, correlated, inspectable; lease fully released.
    rows = coord.inspect(attempt.execution_id)
    assert [a.attempt_id for a in rows] == [attempt.attempt_id]
    assert coord._leases.holder(coord._device) is None


def test_run_sequence_whole_preflight_rejects_with_zero_calls_zero_rows():
    rt = FakeRuntime()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    revision = rt.observe()
    good = dict(namespace="skill", owner="o", task_type="int-1",
                task_version=1, revision=revision)
    rejections = [
        [],
        [ExecutionSpec(**good, payload={"op": "tap_point"}),
         ExecutionSpec(**good, payload={"op": "wipe"})],
        [ExecutionSpec(**good, payload={"op": "tap_point"}),
         ExecutionSpec(**{**good, "revision": rt.observe()},
                       payload={"op": "swipe"})],
    ]
    for specs in rejections:
        with pytest.raises(SpecValidationError):
            coord.run_sequence(specs, owner="o")
    assert rt.device_calls == 0
    assert coord.ledger_executions() == []


def test_run_sequence_stale_fails_closed_zero_device_calls_no_retry():
    rt = RecordingRuntime()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    stale = rt.observe()
    rt.observe()  # supersede: stale is now old
    specs = [ExecutionSpec(namespace="skill", owner="o", task_type="int-1",
                           task_version=1, payload={"op": op}, revision=stale)
             for op in ("tap_point", "swipe")]
    attempt = coord.run_sequence(specs, owner="o")
    assert attempt.state == "failed"
    assert attempt.evidence["error_code"] == "STALE_REVISION"
    assert attempt.retry_safe is False
    # One delegation, zero device effects (Runtime stale preflight), and the
    # coordinator never re-attempted the sequence: there is no retry path.
    assert len(rt.execute_calls) == 1
    assert rt.device_calls == 0
    assert coord.inspect(attempt.execution_id)[-1].state == "failed"


def test_run_sequence_partial_and_unknown_stop_without_replay():
    for mode, state in (("fail", "failed"), ("unknown", "unknown")):
        rt = RecordingRuntime()
        rt.script = [mode]
        coord = ExecutionCoordinator(rt, DeviceLeaseManager())
        revision = rt.observe()
        specs = [ExecutionSpec(namespace="skill", owner="o", task_type="t",
                               task_version=1, payload={"op": "tap_point"},
                               revision=revision)
                 for _ in range(2)]
        attempt = coord.run_sequence(specs, owner="o")
        assert attempt.state == state and attempt.effect != "NONE"
        assert len(rt.execute_calls) == 1 and rt.device_calls == 1
        assert rt.revision != revision  # accepted revision invalidated
        assert attempt.evidence["replayed"] is False


def test_run_sequence_durable_ledger_row_and_restart_safe_inspection():
    root = Path(_SCRATCH_ROOT) / f"ledger-{os.getpid()}"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    ledger = root / "coordinator-ledger.db"
    rt = FakeRuntime()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager(), ledger_path=ledger)
    assert coord.ledger_schema_version is not None
    revision = rt.observe()
    attempt = coord.run_sequence(
        [ExecutionSpec(namespace="skill", owner="o", task_type="int-1",
                       task_version=1, payload={"op": "home"},
                       revision=revision)],
        owner="o")
    assert attempt.state == "succeeded"
    assert ledger.exists()
    rows = coord.inspect(attempt.execution_id)
    assert rows[-1].state == "succeeded"
    coord.close()


def test_run_sequence_cancelled_or_closed_fail_closed():
    rt = FakeRuntime()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    spec = ExecutionSpec(namespace="skill", owner="o", task_type="t",
                         task_version=1, payload={"op": "home"},
                         revision=rt.observe())
    coord.cancel()
    with pytest.raises(CancelledError):
        coord.run_sequence([spec], owner="o")
    assert rt.device_calls == 0
    coord2 = ExecutionCoordinator(FakeRuntime(), DeviceLeaseManager())
    coord2.close()
    with pytest.raises(RuntimeError, match="COORDINATOR_CLOSED"):
        coord2.run_sequence([spec], owner="o")


def test_run_batch_semantics_unchanged_by_integration():
    rt = FakeRuntime()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    skill = _active(registry, _cand())
    revision = rt.observe()
    batch = coord.run_batch(
        [ExecutionSpec(namespace="skill", owner="skill-executor",
                       task_type=skill.skill_id, task_version=1,
                       payload={"op": "tap_point"}, revision=revision),
         ExecutionSpec(namespace="skill", owner="skill-executor",
                       task_type=skill.skill_id, task_version=1,
                       payload={"op": "swipe"}, revision=revision)],
        owner="skill-executor")
    assert [a.state for a in batch] == ["succeeded", "failed"]
    assert batch[1].evidence["error_code"] == "STALE_REVISION"
    assert rt.device_calls == 1  # per-spec Runtime calls, unchanged


# --- RunSession: durable closed loop --------------------------------------------


def test_session_full_closed_loop_single_action(request):
    root = _state_root(request)
    rt = FakeRuntime()
    session = RunSession.start(runtime=rt, state_root=root)
    skill = _active(session.registry, _cand())
    revision = rt.observe()
    attempt = session.execute_skill(
        skill, revision=revision, op="home", shadow_pending=3)
    assert attempt.state == "succeeded"
    types = _types(_events(session.journal))
    assert types[0] == "run.started"
    assert "attempt.completed" in types
    assert "policy.decision" in types
    assert "learning.recorded" in types
    completed = next(e for e in _events(session.journal)
                     if e["event_type"] == "attempt.completed")
    assert completed["visual_hint"] == "post-action"
    assert completed["skill_id"] == "int-1"
    assert completed["status"] == "succeeded"
    learning = next(e for e in _events(session.journal)
                    if e["event_type"] == "learning.recorded")
    assert learning["visual_hint"] == "learning-change"
    policy = next(e for e in _events(session.journal)
                  if e["event_type"] == "policy.decision")
    assert policy["actual_policy"] == "certified-safe-behavior"
    assert policy["payload"]["actual_batch_size"] == 1
    assert policy["payload"]["recommended_batch_size"] == 3
    # A2: durable run-scoped safety ledger is ON in live-run construction.
    assert session.ledger_path.exists()
    summary = session.close()
    assert summary["learning"]["records"] == 1
    assert summary["policy"]["decisions"] >= 1
    assert summary["policy"]["shadow_divergences"] >= 1
    assert summary["events"]["by_type"].get("run.completed", 0) == 1
    assert summary["run"]["duration_ms"] is not None
    snapshot = (root / "runs" / session.run_id / "learning_snapshot.json")
    assert snapshot.exists()
    assert (root / "runs" / session.run_id / "summary.json").exists()
    # Idempotent close.
    assert session.close()["already_closed"] is True
    # Cross-run Experience evidence persisted under the state root.
    store = ExperienceStore(root / "experience" / "episodes.jsonl")
    report = store.load()
    assert report.rejected == 0
    assert len(report.episodes) == 1
    episode = report.episodes[0]
    assert episode.skill_id == "int-1" and episode.effect == "NONE"
    assert episode.state == "succeeded"


def test_session_sequence_closed_loop_and_state_sensitive_fallback(request):
    root = _state_root(request)
    rt = RecordingRuntime()
    session = RunSession.start(runtime=rt, state_root=root,
                               sequence_enabled=True)
    skill = _active(session.registry, _cand())
    revision = rt.observe()
    result = session.execute_sequence(
        skill,
        [SequenceStep(op="tap_point"), SequenceStep(op="swipe"),
         SequenceStep(op="tap_point")],
        revision=revision)
    assert result.executed_steps == 3 and result.fallback_reason is None
    assert len(rt.execute_calls) == 1 and rt.device_calls == 1
    events = _events(session.journal)
    decision = next(e for e in events if e["event_type"] == "sequence.decision")
    assert decision["payload"]["actual_batch_size"] == 3
    assert decision["payload"]["counters"]["requested_steps"] == 3
    assert "execution.completed" in _types(events)
    assert "attempt.completed" in _types(events)
    # State-sensitive steps collapse to size 1 with a retained reason.
    revision = rt.observe()
    result = session.execute_sequence(
        skill,
        [SequenceStep(op="tap_point"),
         SequenceStep(op="swipe", state_sensitive=True)],
        revision=revision)
    assert result.executed_steps == 1
    assert result.fallback_reason == "state-sensitive-fallback-single"
    summary = session.close()
    assert summary["sequences"]["actual_sizes"] == {"3": 1, "1": 1}
    assert summary["fallbacks"]["reasons"][
        "state-sensitive-fallback-single"] == 1


def test_session_sequence_preflight_rejection_journaled_fail_closed(request):
    root = _state_root(request)
    rt = FakeRuntime()
    session = RunSession.start(runtime=rt, state_root=root,
                               sequence_enabled=True)
    skill = _active(session.registry, _cand())
    with pytest.raises(SkillExecutionError) as err:
        session.execute_sequence(skill, [SequenceStep(op="wipe")],
                                 revision="rev-1")
    assert "op-not-authorized" in str(err.value)
    assert rt.device_calls == 0
    decision = next(e for e in _events(session.journal)
                    if e["event_type"] == "sequence.decision")
    assert decision["fallback_reason"]
    session.journal.close()  # stop projections; close() must stay idempotent


def test_session_journal_failure_fails_loud_but_keeps_safety_record(request):
    root = _state_root(request)
    rt = FakeRuntime()
    session = RunSession.start(runtime=rt, state_root=root)
    skill = _active(session.registry, _cand())
    session.journal.close()  # simulate a dead journal mid-run
    with pytest.raises(JournalClosedError):
        session.execute_skill(skill, revision=rt.observe(), op="home")
    # The certified safety record is intact: the attempt was durably made
    # through the Coordinator; only the observational surface failed loud.
    assert session.coordinator.ledger_executions()
    assert any(h.startswith("experience:") for h in session.executor.hook_errors)


def test_session_close_failure_is_retryable_without_duplicate_completion(request):
    root = _state_root(request)
    session = RunSession.start(state_root=root)
    original_emit = session.journal.emit
    failed = False

    def _fail_once(event_type, **kwargs):
        nonlocal failed
        if event_type == "run.completed" and not failed:
            failed = True
            raise JournalClosedError("forced-close-failure")
        return original_emit(event_type, **kwargs)

    session.journal.emit = _fail_once
    with pytest.raises(JournalClosedError):
        session.close()
    assert session._closed is False
    assert session._completion_emitted is False
    assert session.journal._closed is False

    summary = session.close()
    assert summary["events"]["by_type"]["run.completed"] == 1
    assert session._closed is True
    assert session._completion_emitted is True
    assert session.journal._closed is True


def test_session_trace_draining_is_watermarked_and_hinted(request):
    from praxiom.ios_runtime.trace import Trace

    root = _state_root(request)
    session = RunSession.start(state_root=root)
    source = type("TracedPort", (), {})()
    source.trace = Trace()
    source.trace.record("observe", started=source.trace.start())
    first = session.drain_trace(source)
    assert [e["event_type"] for e in first] == ["runtime.observe"]
    assert session.drain_trace(source) == []  # watermarked: nothing new
    source.trace.record("recover", started=source.trace.start())
    second = session.drain_trace(source)
    assert [e["event_type"] for e in second] == ["runtime.recover"]
    assert second[0]["visual_hint"] == "recovery"  # D4=A metadata-only hint
    session.close()


def test_session_failed_close_retains_failed_terminal_status(request):
    root = _state_root(request)
    session = RunSession.start(state_root=root, run_id="run-failed-close")
    summary = session.close(status="failed", reason_code="workload-exception")
    assert summary["events"]["by_type"]["run.completed"] == 1
    events = [
        json.loads(line)
        for line in session.context.events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    terminal = [event for event in events if event["event_type"] == "run.completed"][-1]
    assert terminal["status"] == "failed"
    assert terminal["payload"]["reason_code"] == "workload-exception"


# --- privacy + authority guards ---------------------------------------------------


_PRIVACY_PROBES = (
    "p4ssw0rd!",
    "com.example.secretapp",
    "Welcome to the secret screen",
    "0123456789abcdef0123456789abcdef01234567",
)


def test_session_durable_record_is_privacy_safe(request):
    root = _state_root(request)
    rt = FakeRuntime()
    session = RunSession.start(runtime=rt, state_root=root)
    skill = _active(session.registry, _cand())
    revision = rt.observe()
    session.execute_skill(
        skill, revision=revision, op="home",
        extra={"secret_screen_text": "p4ssw0rd!"})
    raw = (root / "runs" / session.run_id / "events.jsonl").read_bytes()
    text = raw.decode("utf-8")
    for probe in _PRIVACY_PROBES:
        assert probe not in text
    assert "trust_token" not in text
    # The raw opaque revision token never lands on disk; only its
    # deterministic fingerprint does.
    assert revision not in text
    assert "fp:" in text
    for event in _events(session.journal):
        payload_text = str(event.get("payload", {}))
        for probe in _PRIVACY_PROBES:
            assert probe not in payload_text
    session.close()


def test_cross_run_experience_rebind_requires_fresh_live_token(request):
    root = _state_root(request)
    rt = FakeRuntime()
    run_one = RunSession.start(runtime=rt, state_root=root)
    skill = _active(run_one.registry, _cand())
    run_one.execute_skill(skill, revision=rt.observe(), op="home")
    run_one.close()
    # Run two: same state root, fresh registry, fresh live token.
    store = ExperienceStore(root / "experience" / "episodes.jsonl")
    episodes = store.load().episodes
    fresh_registry = SkillRegistry()
    fresh_skill = _active(fresh_registry, _cand())
    fresh_token = fresh_registry.trust_token(fresh_skill)
    fresh_provenance = ":".join(fresh_skill.provenance)[:128]
    result = rebind_history(
        episodes, registry=fresh_registry, skill_id="int-1", version=1,
        trust_token=fresh_token, provenance=fresh_provenance)
    assert result.statuses[0][1] == "rebound"
    # Provenance mismatch fails closed to non-reusable.
    mismatch = rebind_history(
        episodes, registry=fresh_registry, skill_id="int-1", version=1,
        trust_token=fresh_token, provenance="need-1")
    assert mismatch.statuses[0][1] == "rejected:provenance-mismatch"
    # Version/provenance mismatch fails closed to non-reusable.
    stale_registry = SkillRegistry()
    stale_skill = _active(stale_registry, _cand(version=2))
    stale_token = stale_registry.trust_token(stale_skill)
    result = rebind_history(
        episodes, registry=stale_registry, skill_id="int-1", version=2,
        trust_token=stale_token, provenance="need-1")
    assert result.statuses[0][1] == "rejected:version-mismatch"
    assert result.macro_reuse_eligible is False


# --- transport / discovery / surface guards (D5=A, six ops) ----------------------


def test_transport_wiring_uses_discovery_and_inprocess_wifi_rsd():
    src = Path(__file__).resolve().parents[1] / "src" / "praxiom" / "ios_runtime"
    transport_text = (src / "transport.py").read_text(encoding="utf-8")
    assert "DeviceDiscovery" in transport_text  # transport-neutral selection
    assert "wifi_tunnel_factory" in transport_text  # in-process D5=A adapter
    from praxiom.ios_runtime import wifi_tunnel as wt

    from pymobiledevice3.remote.userspace_tunnel import (
        UserspaceRsdTunnel as UpstreamTunnel,
    )
    assert issubclass(wt.RemotePairingUserspaceRsdTunnel, UpstreamTunnel)
    for name in ("discovery.py", "wifi_tunnel.py"):
        text = (src / name).read_text(encoding="utf-8")
        tree = ast.parse(text)  # library-level seam: no subprocess imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] != "subprocess" for a in node.names)
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "subprocess"
        assert re.search(r"phone[\s_-]*harness", text, re.IGNORECASE) is None


def test_runtime_public_surface_still_exactly_six_operations():
    src = Path(__file__).resolve().parents[1] / "src" / "praxiom" / "ios_runtime"
    tree = ast.parse((src / "runtime.py").read_text(encoding="utf-8"))
    public = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "NativeIosRuntime":
            public = {
                item.name for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not item.name.startswith("_")
            }
    assert public == {"status", "observe", "execute", "invalidate",
                      "recover", "close"}


# --- integration-module boundary guard --------------------------------------------

_BANNED_TOKENS = (
    "pymobiledevice3", "usbmux", "coredevice", "appservice", "tunneld",
)
_RUNTIME_OPS = frozenset({"status", "observe", "execute", "invalidate",
                          "recover", "close"})


def test_session_module_boundary_guard():
    src = Path(__file__).resolve().parents[1] / "src" / "praxiom" / "session.py"
    text = src.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in _BANNED_TOKENS:
        assert token not in lowered, f"session.py mentions {token}"
    assert re.search(r"phone[\s_-]*harness", lowered) is None
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            names = [a.name for a in node.names]
            assert not module.startswith("praxiom.ios_runtime")
            assert all(not n.startswith("praxiom.ios_runtime") for n in names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _RUNTIME_OPS:
                receiver = ast.dump(node.func.value)
                # Only coordinator/journal lifecycle closes are legitimate;
                # no direct Runtime operation call may appear.
                assert "runtime" not in receiver.lower(), ast.dump(node)
