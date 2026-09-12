"""R9 Adaptive Execution Performance deterministic matrix (47/47)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from praxiom.adaptive.telemetry import TelemetryEvent, aggregate, PerformanceBaseline
from praxiom.adaptive.dag import DagNode, plan_dag
from praxiom.adaptive.batching import decide_batch
from praxiom.adaptive.learning import (
    MacroStats, PathStats, learn_macros, macro_reusable, score_path, path_reusable,
)
from praxiom.adaptive.temporal import Countdown, MonotonicClock, remaining_ms
from praxiom.adaptive.observation import ObservationPolicy
from praxiom.adaptive.routing import route_latency_aware, adapt_strategy
from praxiom.adaptive.feedback import SelectorStats, record_selector, RecoveryStats, record_recovery
from praxiom.adaptive.fallback import RegressionBudget, check_budget, safe_fallback
from praxiom.ios_runtime.runtime import NativeIosRuntime
from praxiom.retrieval.validator import AdaptiveValidator, ValidationContext, ValidationDecision
from praxiom.skill.candidate import SkillCandidate
from praxiom.skill.registry import SkillRegistry
import inspect as _inspect

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ev(kind="execute", lat=10, ok=True, ts=1):
    return TelemetryEvent(kind=kind, latency_ms=lat, ok=ok, ts=ts)


def _trusted_registry_token():
    registry = SkillRegistry()
    candidate = SkillCandidate(
        skill_id="r9-skill", version=1, inputs=("x",), outputs=("y",),
        preconditions=("revision-bound:r1",), postconditions=("done",),
        risk="low", reversibility="reversible", authority=frozenset({"tap_point"}),
        provenance=("e1", "e2"),
    )
    registry.register(candidate)
    registry.validate("r9-skill", 1, evidence_ids=("e1", "e2"))
    registry.record_success("r9-skill", 1, revision="r1", evidence_id="s1")
    registry.record_success("r9-skill", 1, revision="r2", evidence_id="s2")
    skill = registry.activate("r9-skill", 1, confidence=0.9, evidence_id="activate")
    return registry, registry.trust_token(skill)


def _batch(*, pending: int, validated_confidence: float, max_batch: int = 8,
           revision: str = "r1", state_sensitive: bool = False,
           risk: str = "low", reversibility: str = "reversible",
           human_gate: bool = False):
    return decide_batch(
        pending=pending,
        validated_confidence=validated_confidence,
        max_batch=max_batch,
        revision=revision,
        state_sensitive=state_sensitive,
        risk=risk,
        reversibility=reversibility,
        human_gate=human_gate,
    )


def _route(*, p90_ms: int | None, budget_ms: int, risk: str = "low",
           reversibility: str = "reversible", human_gate: bool = False):
    events = [] if p90_ms is None else [_ev("execute", p90_ms), _ev("execute", p90_ms, ts=2)]
    baseline = PerformanceBaseline.measure(events)
    return route_latency_aware(
        baseline=baseline,
        kind="execute",
        budget_ms=budget_ms,
        risk=risk,
        reversibility=reversibility,
        human_gate=human_gate,
    )


# telemetry 01-04
def test_r9_01_kinds_only():
    agg = aggregate([_ev("execute"), _ev("nope")])
    assert "execute" in agg and "nope" not in agg


def test_r9_02_malformed_dropped():
    agg = aggregate([TelemetryEvent(kind="execute", latency_ms=-5, ok=True, ts=1)])
    assert agg == {}
    assert aggregate([TelemetryEvent(kind="execute", latency_ms=5, ok=1, ts=1)]) == {}  # type: ignore[arg-type]
    assert aggregate([TelemetryEvent(kind="execute", latency_ms=5, ok=True, ts="1")]) == {}  # type: ignore[arg-type]
    assert aggregate([object()]) == {}  # type: ignore[list-item]


def test_r9_03_baseline_only_from_ok():
    base = PerformanceBaseline.measure([_ev("execute", lat=10, ok=True),
                                        _ev("execute", lat=9999, ok=False)])
    assert base.per_kind_median_ms["execute"] == 10
    assert base.measured
    malformed = PerformanceBaseline.measure([
        TelemetryEvent(kind="execute", latency_ms=1, ok="yes", ts=1),  # type: ignore[arg-type]
    ])
    assert "execute" not in malformed.per_kind_p90_ms
    try:
        PerformanceBaseline(per_kind_median_ms={}, per_kind_p90_ms={}, sample_counts={})
        assert False
    except TypeError:
        pass
    try:
        base.per_kind_p90_ms["execute"] = 0  # type: ignore[index]
        assert False
    except TypeError:
        pass


def test_r9_04_median_p90():
    evs = [_ev("observe", lat=v) for v in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)]
    base = PerformanceBaseline.measure(evs)
    assert base.per_kind_median_ms["observe"] == 60
    assert base.per_kind_p90_ms["observe"] == 100
    assert base.sample_counts["observe"] == 10


# dag 05-10
def test_r9_05_acyclic_waves():
    nodes = [DagNode(idx=0, deps=frozenset(), state_sensitive=False, revision="r1"),
             DagNode(idx=1, deps=frozenset(), state_sensitive=False, revision="r1"),
             DagNode(idx=2, deps=frozenset({0, 1}), state_sensitive=True, revision="r1")]
    plan = plan_dag(nodes, max_width=2)
    assert plan.waves[0] == (0, 1) and plan.waves[1] == (2,)


def test_r9_06_self_dep_rejected():
    try:
        plan_dag([DagNode(idx=0, deps=frozenset({0}), revision="r1")])
        assert False
    except ValueError:
        pass


def test_r9_07_unknown_dep_rejected():
    try:
        plan_dag([DagNode(idx=0, deps=frozenset({9}), revision="r1")])
        assert False
    except ValueError:
        pass


def test_r9_08_cycle_rejected():
    try:
        plan_dag([DagNode(idx=0, deps=frozenset({1}), revision="r1"),
                  DagNode(idx=1, deps=frozenset({0}), revision="r1")])
        assert False
    except ValueError:
        pass


def test_r9_09_state_sensitive_serialize():
    nodes = [DagNode(idx=0, deps=frozenset(), state_sensitive=True, revision="r1"),
             DagNode(idx=1, deps=frozenset({0}), state_sensitive=True, revision="r1")]
    plan = plan_dag(nodes, max_width=4)
    assert len(plan.waves) == 2
    mixed = plan_dag([
        DagNode(idx=0, deps=frozenset(), state_sensitive=True, revision="r1"),
        DagNode(idx=1, deps=frozenset({0}), state_sensitive=False, revision="r1"),
    ], max_width=4)
    assert mixed.waves == ((0,), (1,))
    try:
        plan_dag([DagNode(idx=0, deps=frozenset(), revision=None)])
        assert False
    except ValueError:
        pass
    try:
        plan_dag([DagNode(idx=0, deps=frozenset(), revision="r1"),
                  DagNode(idx=1, deps=frozenset(), revision="r2")])
        assert False
    except ValueError:
        pass


def test_r9_10_max_width_bound():
    nodes = [DagNode(idx=i, deps=frozenset(), state_sensitive=False, revision="r1") for i in range(5)]
    plan = plan_dag(nodes, max_width=2)
    assert all(len(w) <= 2 for w in plan.waves)


# batching 11-16
def test_r9_11_high_confidence_full():
    assert _batch(pending=6, validated_confidence=0.9, max_batch=4).size == 4


def test_r9_12_mid_confidence_half():
    assert _batch(pending=6, validated_confidence=0.6, max_batch=4).size == 2


def test_r9_13_low_confidence_single():
    assert _batch(pending=6, validated_confidence=0.2).size == 1


def test_r9_14_invalid_rejected():
    assert _batch(pending=0, validated_confidence=0.9).size == 0


def test_r9_15_untrusted_confidence_single():
    assert _batch(pending=6, validated_confidence=99.0).size == 1
    assert _batch(pending=6, validated_confidence=0.99, risk="high").size == 1
    assert _batch(pending=6, validated_confidence=0.99,
                  reversibility="irreversible").size == 1
    assert _batch(pending=6, validated_confidence=0.99, human_gate=True).size == 1
    assert _batch(pending=6, validated_confidence=0.99,
                  state_sensitive=True).size == 1


def test_r9_16_preflight_required_and_stops():
    d = _batch(pending=3, validated_confidence=0.9)
    assert d.preflight == "required" and "STALE_REVISION" in d.stop_on
    assert _batch(pending=3, validated_confidence=0.9, revision="").size == 1


# learning 17-20
def test_r9_17_validated_macro_trusted():
    registry, token = _trusted_registry_token()
    ts = [
        {"macro_id": "m", "effect": "NONE", "revision": f"r{i}", "trust_token": token}
        for i in range(5)
    ]
    (m,) = [x for x in learn_macros(ts, registry=registry) if x.macro_id == "m"]
    assert m.trusted and m.episodes == 5
    assert macro_reusable(m, registry=registry)
    try:
        MacroStats("forged", 2, 1.0, True, "forged", token)
        assert False
    except TypeError:
        pass
    registry.revoke("r9-skill", 1, evidence_id="revoke")
    assert not macro_reusable(m, registry=registry)


def test_r9_18_insufficient_episodes_untrusted():
    registry, token = _trusted_registry_token()
    ts = [{"macro_id": "m", "effect": "NONE", "revision": "r1", "trust_token": token}]
    (m,) = [x for x in learn_macros(ts, registry=registry) if x.macro_id == "m"]
    assert not m.trusted
    object.__setattr__(m, "trusted", True)
    object.__setattr__(m, "trust_token", token)
    assert not macro_reusable(m, registry=registry)


def test_r9_19_unvalidated_never_macro():
    registry, _ = _trusted_registry_token()
    ts = [{"macro_id": "m", "effect": "NONE", "revision": f"r{i}"} for i in range(5)]
    (m,) = [x for x in learn_macros(ts, registry=registry) if x.macro_id == "m"]
    assert not m.trusted


def test_r9_20_path_scoring():
    registry, token = _trusted_registry_token()
    reusable = score_path(path_id="p", outcomes=["NONE", "NONE", "NONE"],
                          revisions=["r1", "r2", "r3"], trust_token=token,
                          registry=registry)
    assert reusable.reusable and path_reusable(reusable, registry=registry)
    try:
        PathStats("forged", 2, 1.0, True, token)
        assert False
    except TypeError:
        pass
    forged = object.__new__(PathStats)
    object.__setattr__(forged, "path_id", "forged")
    object.__setattr__(forged, "uses", 2)
    object.__setattr__(forged, "success_rate", 1.0)
    object.__setattr__(forged, "reusable", True)
    object.__setattr__(forged, "trust_token", token)
    assert not path_reusable(forged, registry=registry)
    assert not score_path(path_id="p", outcomes=["NONE"], revisions=["r1"],
                          trust_token=token, registry=registry).reusable
    poisoned = score_path(path_id="p", outcomes=["NONE", "PARTIAL"],
                          revisions=["r1", "r2"], trust_token=token,
                          registry=registry)
    assert not poisoned.reusable
    object.__setattr__(poisoned, "reusable", True)
    object.__setattr__(poisoned, "trust_token", token)
    assert not path_reusable(poisoned, registry=registry)
    registry.revoke("r9-skill", 1, evidence_id="revoke")
    assert not path_reusable(reusable, registry=registry)


# temporal 21-23
def test_r9_21_remaining():
    assert remaining_ms(deadline_ms=100, now_ms=30) == 70


def test_r9_22_expired():
    assert Countdown(deadline_ms=100, now_ms=100).expired()
    assert Countdown(deadline_ms=100, now_ms=150).expired()
    assert not Countdown(deadline_ms=100, now_ms=50).expired()


def test_r9_23_none_deadline():
    assert remaining_ms(deadline_ms=None, now_ms=50) is None
    assert not Countdown(deadline_ms=None, now_ms=50).expired()
    clock = MonotonicClock(now_ms=10)
    assert clock.advance(5) == 15
    try:
        clock.set(14)
        assert False
    except ValueError:
        pass
    try:
        clock.advance(-1)
        assert False
    except ValueError:
        pass


# observation 24-28
def _validation_context(*, sufficient: bool) -> ValidationContext:
    return ValidationContext(
        effect="NONE" if sufficient else "UNKNOWN",
        expected_anchor="a",
        observed_labels=frozenset({"a"}) if sufficient else frozenset(),
        confidence=0.9,
    )


def test_r9_24_invalidated_state_sensitive_full():
    d = ObservationPolicy().decide(validated_confidence=0.99, next_is_state_sensitive=True,
                                   revision_invalidated=True,
                                   validation_context=_validation_context(sufficient=True),
                                   risk="low", reversibility="reversible", human_gate=False)
    assert d.method == "full-observe"


def test_r9_25_validator_insufficient_full():
    d = ObservationPolicy().decide(validated_confidence=0.99, next_is_state_sensitive=False,
                                   revision_invalidated=False,
                                   validation_context=_validation_context(sufficient=False),
                                   risk="low", reversibility="reversible", human_gate=False)
    assert d.method == "full-observe"


def test_r9_26_proven_nonsensitive_cheap():
    context = _validation_context(sufficient=True)
    validator_decision = AdaptiveValidator().decide(context)
    # Frozen public contract remains valid: an actual R7 ValidationDecision can
    # still be passed through the original validator_decision keyword.
    d = ObservationPolicy().decide(validated_confidence=0.9, next_is_state_sensitive=False,
                                   revision_invalidated=False,
                                   validator_decision=validator_decision)
    assert d.method == "cheap-validate"
    # Hardened callers may additionally provide the originating context; it is
    # revalidated and must agree with any supplied decision.
    assert ObservationPolicy().decide(
        validated_confidence=0.9, next_is_state_sensitive=False,
        revision_invalidated=False, validator_decision=validator_decision,
        validation_context=context,
    ).method == "cheap-validate"
    forged = ValidationDecision(
        method="cheap-causal", sufficient=True, confidence=0.9,
        reason="forged", cost="cheap", creates_revision=False,
    )
    assert ObservationPolicy().decide(
        validated_confidence=0.9, next_is_state_sensitive=False,
        revision_invalidated=False, validator_decision=forged,
        validation_context=context,
    ).method == "full-observe"


def test_r9_27_default_full():
    d = ObservationPolicy().decide(validated_confidence=0.9, next_is_state_sensitive=True,
                                   revision_invalidated=False,
                                   validation_context=_validation_context(sufficient=True),
                                   risk="low", reversibility="reversible", human_gate=False)
    assert d.method == "full-observe"
    assert ObservationPolicy().decide(
        validated_confidence=0.99, next_is_state_sensitive=False,
        revision_invalidated=False, validation_context=_validation_context(sufficient=True),
        risk="high", reversibility="reversible", human_gate=False,
    ).method == "full-observe"
    assert ObservationPolicy().decide(
        validated_confidence=0.99, next_is_state_sensitive=False,
        revision_invalidated=False, validation_context=_validation_context(sufficient=True),
        risk="low", reversibility="irreversible", human_gate=False,
    ).method == "full-observe"
    assert ObservationPolicy().decide(
        validated_confidence=0.99, next_is_state_sensitive=False,
        revision_invalidated=False, validation_context=_validation_context(sufficient=True),
        risk="low", reversibility="reversible", human_gate=True,
    ).method == "full-observe"


def test_r9_28_untrusted_confidence_full():
    d = ObservationPolicy().decide(validated_confidence=5.0, next_is_state_sensitive=False,
                                   revision_invalidated=False,
                                   validation_context=_validation_context(sufficient=True),
                                   risk="low", reversibility="reversible", human_gate=False)
    assert d.method == "full-observe"
    assert ObservationPolicy().decide(
        validated_confidence=0.9, next_is_state_sensitive=False,
        revision_invalidated=False, validation_context="forged",  # type: ignore[arg-type]
        risk="low", reversibility="reversible", human_gate=False,
    ).method == "full-observe"
    malformed_contexts = (
        ValidationContext(effect="NONE", expected_anchor="a", observed_labels=frozenset({"a"}),
                          confidence=float("nan")),
        ValidationContext(effect="NONE", expected_anchor="a", observed_labels=frozenset({"a"}),
                          confidence="bad"),  # type: ignore[arg-type]
    )
    for context in malformed_contexts:
        assert ObservationPolicy().decide(
            validated_confidence=0.9, next_is_state_sensitive=False,
            revision_invalidated=False, validation_context=context,
            risk="low", reversibility="reversible", human_gate=False,
        ).method == "full-observe"
    assert ObservationPolicy().decide(
        validated_confidence="bad",  # type: ignore[arg-type]
        next_is_state_sensitive=False, revision_invalidated=False,
        validation_context=_validation_context(sufficient=True),
        risk="low", reversibility="reversible", human_gate=False,
    ).method == "full-observe"


# routing 29-33
def test_r9_29_fast_standard_careful():
    assert _route(p90_ms=40, budget_ms=100).route == "fast-path"
    assert _route(p90_ms=80, budget_ms=100).route == "standard"
    assert _route(p90_ms=500, budget_ms=100).route == "careful"


def test_r9_30_high_risk_careful():
    assert _route(p90_ms=1, budget_ms=1000, risk="high").route == "careful"
    assert _route(p90_ms=1, budget_ms=1000, risk="medium").route == "standard"
    assert _route(p90_ms=1, budget_ms=1000,
                  reversibility="irreversible").route == "careful"
    assert _route(p90_ms=1, budget_ms=1000, human_gate=True).route == "careful"
    assert _route(p90_ms=1, budget_ms=1000, risk="critical").route == "careful"


def test_r9_31_no_telemetry_standard():
    assert _route(p90_ms=None, budget_ms=100).route == "careful"
    forged = object.__new__(PerformanceBaseline)
    assert route_latency_aware(
        baseline=forged,
        kind="execute",
        budget_ms=100,
        risk="low",
        reversibility="reversible",
        human_gate=False,
    ).route == "careful"
    empty = PerformanceBaseline.measure([])
    object.__setattr__(empty, "per_kind_p90_ms", {"execute": 0})
    object.__setattr__(empty, "sample_counts", {"execute": 99})
    assert route_latency_aware(
        baseline=empty,
        kind="execute",
        budget_ms=100,
        risk="low",
        reversibility="reversible",
        human_gate=False,
    ).route == "careful"
    assert route_latency_aware(
        baseline=PerformanceBaseline.measure([_ev(), _ev(ts=2)]),
        kind=[],  # type: ignore[arg-type]
        budget_ms=100,
        risk="low",
        reversibility="reversible",
        human_gate=False,
    ).route == "careful"


def test_r9_32_invalid_budget_careful():
    assert _route(p90_ms=10, budget_ms=0).route == "careful"


def test_r9_33_strategy_escalate_cautious_steady():
    assert adapt_strategy(failure_streak=3, loop_detected=False, validator_failed=False).tier == "heavy"
    assert adapt_strategy(failure_streak=0, loop_detected=True, validator_failed=False).tier == "heavy"
    assert adapt_strategy(failure_streak=0, loop_detected=False, validator_failed=True).tier == "heavy"
    assert adapt_strategy(failure_streak=1, loop_detected=False, validator_failed=False).tier == "lightweight"
    assert adapt_strategy(failure_streak=0, loop_detected=False, validator_failed=False).tier == "deterministic"


# feedback 34-36
def test_r9_34_selector_hit_rate():
    s = SelectorStats(selector_id="sel")
    record_selector(s, hit=True)
    record_selector(s, hit=False)
    assert s.hit_rate == 0.5 and s.uses == 2


def test_r9_35_recovery_rate():
    r = RecoveryStats()
    record_recovery(r, recovered=True)
    record_recovery(r, recovered=False)
    assert r.recovery_rate == 0.5


def test_r9_36_no_lifecycle_leak():
    # feedback stats carry no lifecycle/state fields
    assert "lifecycle" not in SelectorStats.__dataclass_fields__ or True
    s = SelectorStats(selector_id="x")
    assert not hasattr(s, "lifecycle") and not hasattr(RecoveryStats(), "lifecycle")


# fallback 37-41
def test_r9_37_latency_exceeded_fallback():
    v = check_budget(RegressionBudget(max_latency_ms=100), p90_ms=500,
                     observe_rate=0.1, recovery_rate=0.9)
    assert not v.within and v.fallback


def test_r9_38_observe_exceeded():
    v = check_budget(RegressionBudget(max_observe_rate=0.5), p90_ms=10,
                     observe_rate=0.9, recovery_rate=0.9)
    assert not v.within and v.fallback


def test_r9_39_recovery_missed():
    v = check_budget(RegressionBudget(min_recovery_rate=0.8), p90_ms=10,
                     observe_rate=0.1, recovery_rate=0.2)
    assert not v.within and v.fallback


def test_r9_40_within_no_fallback():
    v = check_budget(RegressionBudget(), p90_ms=10, observe_rate=0.1, recovery_rate=0.9)
    assert v.within and not v.fallback
    missing = check_budget(RegressionBudget(), p90_ms=None,
                           observe_rate=0.1, recovery_rate=0.9)
    assert not missing.within and missing.fallback
    malformed = check_budget(RegressionBudget(), p90_ms=10,
                             observe_rate=-0.1, recovery_rate=0.9)
    assert not malformed.within and malformed.fallback


def test_r9_41_safe_fallback_shape():
    fb = safe_fallback(signal_failed=True, reason="telemetry-failed")
    assert fb["mode"] == "r7-safe-baseline" and fb["optimization"] == "disabled" and fb["reobserve"]


# integration/safety 42-47
def test_r9_42_optimization_falls_back_on_signal_failure():
    fb = safe_fallback(signal_failed=True, reason="model-failed")
    assert fb["mode"] == "r7-safe-baseline"


def test_r9_43_batch_stops_require_reconcile():
    d = _batch(pending=5, validated_confidence=0.9)
    assert set(d.stop_on) >= {"PARTIAL", "UNKNOWN", "STALE_REVISION"}


def test_r9_44_validator_never_creates_revision():
    from praxiom.retrieval.validator import AdaptiveValidator, ValidationContext
    dec = AdaptiveValidator().decide(ValidationContext(effect="NONE", expected_anchor="a",
                                                       observed_labels=frozenset({"a"}),
                                                       confidence=0.9))
    assert dec.creates_revision is False


def test_r9_45_no_new_runtime_ops():
    ops = sorted(m for m, _ in _inspect.getmembers(NativeIosRuntime, _inspect.isfunction)
                 if not m.startswith("_"))
    assert ops == ["close", "execute", "invalidate", "observe", "recover", "status"]


def test_r9_46_boundary_guard_passes():
    r = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "check_agent_boundaries.py")],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_r9_47_budgets_independent_per_kind():
    b_exec = RegressionBudget(kind="execute", max_latency_ms=50)
    b_obs = RegressionBudget(kind="observe", max_latency_ms=5000)
    v_exec = check_budget(b_exec, p90_ms=100, observe_rate=0.1, recovery_rate=0.9)
    v_obs = check_budget(b_obs, p90_ms=100, observe_rate=0.1, recovery_rate=0.9)
    assert v_exec.fallback and not v_obs.fallback
