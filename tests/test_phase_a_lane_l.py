"""Post-R10 Phase A lane L deterministic tests (A3 + A4 only).

A3: execution -> Experience -> learning evidence bridge (automatic
extraction from real outcomes, durable privacy-safe persistence, cross-run
rebinding that can never persist or replay SkillTrustToken authority).
A4: shadow-first adaptive recommendations (observation, batching, latency
routing, strategy, macro/path reuse eligibility, fallback) with live
optimization feature-gated OFF.

All tests are deterministic fakes with workspace-local scratch state.
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from praxiom.agent.coordinator import DeviceLeaseManager, ExecutionCoordinator
from praxiom.adaptive.experience_bridge import (
    ExtractionContext,
    build_episode,
    rebind_history,
)
from praxiom.adaptive.fallback import RegressionBudget
from praxiom.adaptive.learning import learn_macros, macro_reusable, score_path
from praxiom.adaptive.shadow import (
    LIVE_OPTIMIZATION_ENABLED,
    LiveOptimizationDisabledError,
    LiveOptimizationGate,
    LiveOptimizationRefusedError,
    ShadowAdvisor,
    ShadowContext,
    shadow_recommend,
)
from praxiom.adaptive.telemetry import PerformanceBaseline, TelemetryEvent
from praxiom.knowledge.experience import (
    FORBIDDEN_AUTHORITY_KEYS,
    ExperienceEpisode,
)
from praxiom.knowledge.experience_store import ExperienceStore
from praxiom.retrieval.validator import ValidationContext, ValidationDecision
from praxiom.skill.candidate import SkillCandidate
from praxiom.skill.executor import SkillExecutor
from praxiom.skill.registry import SkillRegistry
from tests.fakes import FakeRuntime

SCRATCH = Path(__file__).resolve().parents[1] / ".pytest-tmp" / "lane-l"


def _cand(**kw):
    base = dict(skill_id="sk-l", version=1, inputs=("x",), outputs=("y",),
                preconditions=("revision-bound: rev-1", "fact-a"),
                postconditions=("done",), risk="low", reversibility="reversible",
                authority=frozenset({"tap_point"}), provenance=("prov-a", "prov-b"))
    base.update(kw)
    return SkillCandidate(**base)


def _registry(skill_id="sk-l", provenance=("prov-a", "prov-b")):
    registry = SkillRegistry()
    registry.register(_cand(skill_id=skill_id, provenance=provenance))
    registry.validate(skill_id, 1, evidence_ids=provenance)
    registry.record_success(skill_id, 1, revision="r1", evidence_id="s1")
    registry.record_success(skill_id, 1, revision="r2", evidence_id="s2")
    return registry


def _ctx(**kw):
    base = dict(skill_id="sk-l", skill_version=1, provenance="prov-a:prov-b",
                captured_at=1000)
    base.update(kw)
    return ExtractionContext(**base)


def _run_attempt(rt, revision, script="ok"):
    """Run one real coordinator attempt and return (spec, attempt)."""
    rt.script = [script]
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    spec = _spec(revision)
    return spec, coord.run(spec, owner="test-owner")


def _spec(revision, op="tap_point"):
    from praxiom.agent.coordinator import ExecutionSpec
    return ExecutionSpec(namespace="skill", owner="owner-x", task_type="sk-l",
                         task_version=1, payload={"op": op}, revision=revision)


# ---------------------------------------------------------------------------
# A3 — extraction from real outcomes
# ---------------------------------------------------------------------------

def test_a3_episode_from_success_part_unknown_stale():
    rt = FakeRuntime()
    rev = rt.observe()
    spec_ok, att_ok = _run_attempt(rt, rev, "ok")
    ep_ok = build_episode(spec_ok, att_ok, _ctx(macro_id="m1"))
    assert ep_ok.outcome == "succeeded" and ep_ok.effect == "NONE"
    assert ep_ok.skill_id == "sk-l" and ep_ok.skill_version == 1
    assert ep_ok.episode_id == att_ok.attempt_id

    rev2 = rt.observe()
    spec_fail, att_fail = _run_attempt(rt, rev2, "fail")
    ep_fail = build_episode(spec_fail, att_fail, _ctx())
    assert ep_fail.outcome == "failed" and ep_fail.effect == "PARTIAL"

    rev3 = rt.observe()
    spec_unk, att_unk = _run_attempt(rt, rev3, "unknown")
    ep_unk = build_episode(spec_unk, att_unk, _ctx())
    assert ep_unk.outcome == "unknown" and ep_unk.effect == "UNKNOWN"

    # Stale revision: retained with the error code, never upgraded.
    rev4 = rt.observe()
    rt.script = ["ok"]
    spec_stale = _spec("rev-forged-stale")
    att_stale = ExecutionCoordinator(rt, DeviceLeaseManager()).run(
        spec_stale, owner="test-owner")
    ep_stale = build_episode(spec_stale, att_stale, _ctx())
    assert ep_stale.outcome == "failed"
    assert ep_stale.error_code == "STALE_REVISION"
    # Failure evidence is never filtered into success.
    assert all(ep.outcome != "succeeded"
               for ep in (ep_fail, ep_unk, ep_stale))


def test_a3_episode_serialization_never_carries_authority():
    rt = FakeRuntime()
    rev = rt.observe()
    spec, att = _run_attempt(rt, rev, "ok")
    episode = build_episode(spec, att, _ctx())
    raw = episode.to_json()
    assert "trust_token" not in raw
    assert not FORBIDDEN_AUTHORITY_KEYS.intersection(json.loads(raw))
    assert ExperienceEpisode.from_json(raw) == episode
    # Legacy R6 episode JSON (without the new fields) still loads.
    legacy = {
        "episode_id": "ep-legacy", "transition": "a->b", "outcome": "ok",
        "provenance": "synthetic-fixture", "execution_id": "exe-1",
        "attempt_id": "att-1", "revision": "rev-1", "captured_at": 5,
        "schema_version": 1,
    }
    loaded = ExperienceEpisode.from_json(json.dumps(legacy))
    assert loaded.episode_id == "ep-legacy" and loaded.effect == "NONE"


def test_a3_store_roundtrip_crash_tail_and_authority_rejection():
    path = SCRATCH / f"store-a-{uuid4().hex}" / "episodes.jsonl"
    store = ExperienceStore(path)
    rt = FakeRuntime()
    rev = rt.observe()
    spec, att = _run_attempt(rt, rev, "ok")
    ep1 = build_episode(spec, att, _ctx(macro_id="m1"))
    ep2 = ExperienceEpisode(episode_id="ep-x", transition="t", outcome="ok")
    store.record(ep1)
    store.record(ep2)
    report = store.load()
    assert [e.episode_id for e in report.episodes] == [ep1.episode_id, "ep-x"]
    assert report.rejected == 0

    # Crash-torn trailing line stays inspectable as rejected evidence.
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"episode_id": "torn"')
    report = store.load()
    assert [e.episode_id for e in report.episodes] == [ep1.episode_id, "ep-x"]
    assert report.rejected == 1
    assert "malformed-episode" in report.rejected_reasons[0]

    # Persisted authority-smuggling keys are rejected, never reused.
    smuggled = json.loads(ep1.to_json())
    smuggled["trust_token"] = {"token_id": "forged"}
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n" + json.dumps(smuggled) + "\n")
    report = store.load()
    assert report.rejected == 2
    assert "persisted-authority-key-rejected" in report.rejected_reasons[1]
    assert [e.episode_id for e in report.episodes] == [ep1.episode_id, "ep-x"]


def test_a3_rebind_requires_fresh_live_token_and_matching_identity():
    registry = _registry()
    skill = registry.activate("sk-l", 1, confidence=0.9, evidence_id="activate")
    token = registry.trust_token(skill)

    rt = FakeRuntime()
    episodes = []
    for _ in ("a", "b", "c"):
        revision = rt.observe()
        spec, att = _run_attempt(rt, revision, "ok")
        episodes.append(build_episode(spec, att, _ctx(macro_id="m1", path_id="p1")))

    result = rebind_history(episodes, registry=registry, skill_id="sk-l",
                            version=1, trust_token=token,
                            provenance="prov-a:prov-b")
    assert [status for _, status in result.statuses] == ["rebound"] * 3
    assert result.macro_reuse_eligible and result.path_reuse_eligible
    assert all(t["trust_token"] is token for t in result.transitions)
    assert learn_macros(list(result.transitions), registry=registry)[0].trusted
    path_stats = score_path(**result.path_inputs[0])
    assert path_stats.reusable

    # A fresh but foreign token (different registry) fails closed.
    other = _registry()
    other_skill = other.activate("sk-l", 1, confidence=0.9, evidence_id="activate")
    foreign = other.trust_token(other_skill)
    blocked = rebind_history(episodes, registry=registry, skill_id="sk-l",
                             version=1, trust_token=foreign,
                             provenance="prov-a:prov-b")
    assert all(s == "rejected:trust-not-live" for _, s in blocked.statuses)
    assert not blocked.macro_reuse_eligible and not blocked.path_reuse_eligible

    # Version mismatch fails closed to non-reusable history.
    stale_version = episodes[0]
    object.__setattr__(stale_version, "skill_version", 2)
    mismatched = rebind_history([stale_version], registry=registry,
                                skill_id="sk-l", version=1, trust_token=token,
                                provenance="prov-a:prov-b")
    assert mismatched.statuses[0][1] == "rejected:version-mismatch"

    # Provenance mismatch fails closed.
    other_prov = episodes[1]
    object.__setattr__(other_prov, "provenance", "somewhere-else")
    mismatch = rebind_history([other_prov], registry=registry, skill_id="sk-l",
                              version=1, trust_token=token,
                              provenance="prov-a:prov-b")
    assert mismatch.statuses[0][1] == "rejected:provenance-mismatch"


def test_a3_failure_evidence_is_retained_and_poisons_reuse():
    registry = _registry()
    skill = registry.activate("sk-l", 1, confidence=0.9, evidence_id="activate")
    token = registry.trust_token(skill)

    rt = FakeRuntime()
    rev = rt.observe()
    spec_ok, att_ok = _run_attempt(rt, rev, "ok")
    rev2 = rt.observe()
    spec_bad, att_bad = _run_attempt(rt, rev2, "fail")
    episodes = [
        build_episode(spec_ok, att_ok, _ctx(macro_id="m1")),
        build_episode(spec_bad, att_bad, _ctx(macro_id="m1")),
    ]
    result = rebind_history(episodes, registry=registry, skill_id="sk-l",
                            version=1, trust_token=token,
                            provenance="prov-a:prov-b")
    assert dict(result.statuses)[episodes[0].episode_id] == "rebound"
    assert dict(result.statuses)[episodes[1].episode_id] == "retained-failure"
    # The retained PARTIAL evidence poisons macro trust (existing certified
    # semantic): it is passed through, not filtered into success.
    stats = learn_macros(list(result.transitions), registry=registry)[0]
    assert stats.reason == "non-none-effect-poisons-trust"
    assert not macro_reusable(stats, registry=registry)
    # Inactive token (revoked skill) fails closed even with matching identity.
    registry.revoke("sk-l", 1, evidence_id="safety")
    blocked = rebind_history(episodes, registry=registry, skill_id="sk-l",
                             version=1, trust_token=token,
                             provenance="prov-a:prov-b")
    assert all(s == "rejected:trust-not-live" for _, s in blocked.statuses)


# ---------------------------------------------------------------------------
# A4 — shadow-first recommendations
# ---------------------------------------------------------------------------

def _validator_ok():
    return ValidationDecision(method="cheap-causal", sufficient=True,
                              confidence=0.9, reason="sufficient-postcondition",
                              cost="cheap")


def _baseline(lat_ms=100):
    return PerformanceBaseline.measure([
        TelemetryEvent(kind="execute", latency_ms=lat_ms, ok=True, ts=i)
        for i in range(10)
    ])


def _rich_ctx(**kw):
    base = dict(
        validated_confidence=0.9,
        validator_decision=_validator_ok(),
        risk="low", reversibility="reversible", human_gate=False,
        pending=3, revision="rev-1", budget_ms=1000,
        baseline=_baseline(100),
    )
    base.update(kw)
    return ShadowContext(**base)


def test_a4_shadow_recommends_without_applying():
    rec = shadow_recommend(_rich_ctx())
    assert rec.actual_decision == "certified-safe-behavior"
    assert rec.live_applied is False
    assert rec.observation is not None and rec.observation.method == "cheap-validate"
    assert rec.would_reduce_observe is True
    assert rec.batch is not None and rec.batch.size == 3
    assert rec.would_reduce_actions is True
    assert rec.route is not None and rec.route.route == "fast-path"
    assert rec.strategy is not None and rec.strategy.tier == "deterministic"
    assert rec.fallback is None and rec.fallback_reason == ""
    assert rec.confidence == pytest.approx(0.9)


@pytest.mark.parametrize("floor", ["human_gate", "high_risk", "irreversible",
                                   "state_sensitive"])
def test_a4_safety_floors_fail_closed(floor):
    kw = {
        "human_gate": dict(human_gate=True),
        "high_risk": dict(risk="high"),
        "irreversible": dict(reversibility="irreversible"),
        "state_sensitive": dict(next_is_state_sensitive=True),
    }[floor]
    rec = shadow_recommend(_rich_ctx(**kw))
    assert rec.observation is not None
    assert rec.observation.method == "full-observe"
    assert rec.would_reduce_observe is False
    assert rec.batch is not None and rec.batch.size == 1
    assert rec.would_reduce_actions is False
    if floor != "state_sensitive":
        # Non-low-risk / human-gated classes never route fast.
        assert rec.route is not None and rec.route.route == "careful"


def test_a4_untrusted_confidence_fails_closed():
    rec = shadow_recommend(_rich_ctx(validated_confidence=float("nan")))
    assert rec.observation is not None
    assert rec.observation.method == "full-observe"
    assert rec.observation.reason == "malformed-optimization-signal"
    assert rec.confidence == 0.0


def test_a4_budget_breach_yields_fallback_recommendation():
    budget = RegressionBudget(max_latency_ms=50)
    rec = shadow_recommend(_rich_ctx(baseline=_baseline(500), regression_budget=budget))
    assert rec.fallback is not None
    assert rec.fallback["optimization"] == "disabled"
    assert rec.fallback_reason == "latency-budget-exceeded"

    within = shadow_recommend(_rich_ctx(regression_budget=RegressionBudget(max_latency_ms=1000),
                                        recovery_rate=1.0))
    assert within.fallback is None


def test_a4_missing_baseline_and_advisor_history_bounds():
    rec = shadow_recommend(_rich_ctx(baseline=None))
    assert rec.route is None
    assert "no-baseline" in rec.reason
    assert rec.live_applied is False

    advisor = ShadowAdvisor(max_history=3)
    for _ in range(5):
        advisor.recommend(_rich_ctx())
    assert len(advisor.history) == 3
    assert advisor.last_recommendation is advisor.history[-1]


def test_a4_live_optimization_feature_gated_off():
    assert LIVE_OPTIMIZATION_ENABLED is False
    rec = shadow_recommend(_rich_ctx())
    gate = LiveOptimizationGate()  # default OFF
    with pytest.raises(LiveOptimizationDisabledError):
        gate.authorize(rec, risk="low", reversibility="reversible",
                       human_gate=False)
    # Even an explicitly enabled gate refuses non-low-risk classes.
    enabled = LiveOptimizationGate(enabled=True)
    with pytest.raises(LiveOptimizationRefusedError):
        enabled.authorize(rec, risk="high", reversibility="reversible",
                          human_gate=False)
    with pytest.raises(LiveOptimizationRefusedError):
        enabled.authorize(rec, risk="low", reversibility="reversible",
                          human_gate=True)
    assert enabled.authorize(rec, risk="low", reversibility="reversible",
                             human_gate=False) == "live-apply-authorized"
    # No shadow recommendation ever reports applied state.
    assert rec.live_applied is False


# ---------------------------------------------------------------------------
# A3 + A4 production wiring through SkillExecutor
# ---------------------------------------------------------------------------

def _wired_executor(tmp_name):
    rt = FakeRuntime()
    rev = rt.observe()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = _registry()
    skill = registry.activate("sk-l", 1, confidence=0.9, evidence_id="activate")
    store = ExperienceStore(SCRATCH / f"exec-{uuid4().hex}" / "episodes.jsonl")
    advisor = ShadowAdvisor()
    ex = SkillExecutor(coordinator=coord, registry=registry,
                       experience_recorder=store, shadow_advisor=advisor)
    return rt, rev, ex, skill, registry, store, advisor


def test_a3_a4_executor_records_evidence_and_shadow():
    rt, rev, ex, skill, registry, store, advisor = _wired_executor("exec-ok")
    att = ex.execute(skill, revision=rev, op="tap_point", shadow_pending=3)
    assert att.state == "succeeded"
    assert ex.hook_errors == []
    report = store.load()
    assert len(report.episodes) == 1
    ep = report.episodes[0]
    assert ep.skill_id == "sk-l" and ep.effect == "NONE"
    assert ep.outcome == "succeeded" and ep.revision == rev
    assert "trust_token" not in ep.to_json()
    rec = advisor.last_recommendation
    assert rec is not None and rec.live_applied is False
    assert rec.actual_decision == "certified-safe-behavior"
    assert rec.observation is not None and rec.observation.method == "full-observe"
    assert rec.batch is not None and rec.batch.size == 3


def test_a3_a4_hook_failure_never_alters_attempt():
    rt = FakeRuntime()
    rev = rt.observe()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = _registry()
    skill = registry.activate("sk-l", 1, confidence=0.9, evidence_id="activate")

    class BrokenSink:
        def record(self, episode):
            raise ValueError("sink-down")

    class BrokenAdvisor:
        def recommend(self, ctx):
            raise RuntimeError("advisor-down")

    ex = SkillExecutor(coordinator=coord, registry=registry,
                       experience_recorder=BrokenSink(),
                       shadow_advisor=BrokenAdvisor())
    att = ex.execute(skill, revision=rev, op="tap_point")
    assert att.state == "succeeded"
    assert ex.hook_errors == ["experience:ValueError", "shadow:RuntimeError"]

    # Without hooks the certified behavior is bit-for-bit unchanged.
    ex_plain = SkillExecutor(coordinator=coord, registry=registry)
    rev2 = rt.observe()
    att2 = ex_plain.execute(skill, revision=rev2, op="tap_point")
    assert att2.state == "succeeded" and ex_plain.hook_errors == []
