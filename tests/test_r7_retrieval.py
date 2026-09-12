"""R7 scenario matrix (12 deterministic synthetic scenarios)."""
from praxiom.agent.coordinator import (
    DeviceLeaseManager, ExecutionCoordinator, ExecutionSpec,
)
from tests.fakes import FakeRuntime
from praxiom.retrieval.feedback import apply_decay, record_outcome
from praxiom.retrieval.graph import KnowledgeGraph, TypedEdge
from praxiom.retrieval.reconcile import reconcile
from praxiom.retrieval.semantic import SemanticAdapter, rerank
from praxiom.retrieval.store import KnowledgeItem, KnowledgeStore
from praxiom.retrieval.validator import AdaptiveValidator, ValidationContext


def _store() -> KnowledgeStore:
    s = KnowledgeStore()
    s.put(KnowledgeItem(kid="k-home", claim="home anchor observed",
                        state="promoted", reliability=0.8))
    s.put(KnowledgeItem(kid="k-old", claim="home anchor observed",
                        state="superseded", reliability=0.9))
    s.put(KnowledgeItem(kid="k-draft", claim="home anchor guess",
                        state="candidate", reliability=0.9))
    s.put(KnowledgeItem(kid="k-verified", claim="settings anchor verified",
                        state="verified", reliability=0.5))
    return s


def test_R7_01_active_filter_exact_deterministic_stability():
    s = _store()
    hits = s.retrieve("k-home", mode="action")
    assert hits and hits[0].kid == "k-home" and hits[0].source == "exact"
    # Action mode excludes superseded/candidate; audit reveals them.
    ids = {h.kid for h in s.retrieve("home anchor", mode="action")}
    assert "k-home" in ids and "k-old" not in ids and "k-draft" not in ids
    audit_ids = {h.kid for h in s.retrieve("home anchor", mode="audit")}
    assert {"k-home", "k-old", "k-draft"} <= audit_ids
    # Stable ties: same query twice -> identical order.
    assert [h.kid for h in s.retrieve("anchor", mode="action")] == \
           [h.kid for h in s.retrieve("anchor", mode="action")]
    assert len(s.retrieve("anchor", mode="action", top_k=2)) <= 2


def test_R7_02_bounded_cycle_safe_typed_expansion():
    s = _store()
    s.put(KnowledgeItem(kid="k-b", claim="b node", state="promoted"))
    s.put(KnowledgeItem(kid="k-c", claim="c node", state="promoted"))
    g = KnowledgeGraph(s)
    g.add_edge(TypedEdge(src="k-home", dst="k-b", edge_type="relates"))
    g.add_edge(TypedEdge(src="k-b", dst="k-c", edge_type="relates"))
    g.add_edge(TypedEdge(src="k-c", dst="k-home", edge_type="relates"))  # cycle
    g.add_edge(TypedEdge(src="k-b", dst="k-old", edge_type="relates"))  # filtered
    out = g.expand("k-home", depth=5, budget=50)
    assert "k-b" in out and "k-c" in out and "k-old" not in out
    assert len(out) == len(set(out))  # cycle-safe
    assert g.expand("k-home", depth=1) == ["k-b"]  # bounded depth
    assert g.expand("k-old", depth=5, mode="action") == []  # hidden root has no authority


def test_R7_03_semantic_seam_canonical_ids_safe_fallback():
    s = _store()
    disabled = SemanticAdapter(enabled=False, mapping={"q": ["k-home"]})
    assert all(h.source != "semantic" for h in rerank("q", s, disabled))
    adapter = SemanticAdapter(enabled=True, mapping={"anchor": ["k-home", "k-ghost"]})
    hits = rerank("anchor", s, adapter)
    assert hits[0].source in ("exact", "lexical")  # deterministic first
    assert "k-ghost" not in {h.kid for h in hits}  # canonical only
    failing = SemanticAdapter(enabled=True, mapping={})
    assert rerank("__fail__", s, failing) is not None  # safe fallback
    assert rerank("anchor", s, adapter, top_k=-1) == []


def test_R7_03_semantic_rerank_preserves_exact_and_deterministic_order():
    s = KnowledgeStore()
    s.put(KnowledgeItem(kid="z-exact", claim="alpha", state="promoted",
                        reliability=0.9))
    s.put(KnowledgeItem(kid="a-lex", claim="z-exact alpha", state="promoted",
                        reliability=0.1))
    baseline = s.retrieve("z-exact", mode="action")
    reranked = rerank("z-exact", s, SemanticAdapter(enabled=False))
    assert [h.kid for h in baseline] == ["z-exact", "a-lex"]
    assert [h.kid for h in reranked] == ["z-exact", "a-lex"]
    assert reranked[0].source == "exact"


def test_R7_04_feedback_decay_without_lifecycle_corruption():
    s = _store()
    before = s.get("k-home").reliability
    record_outcome(s, "k-home", success=True, now_ts=200)
    assert s.get("k-home").reliability > before
    record_outcome(s, "k-home", success=False, now_ts=201)
    assert s.get("k-home").state == "promoted"  # feedback never flips lifecycle
    for _ in range(5):
        record_outcome(s, "k-home", success=False, now_ts=202)
    assert s.get("k-home").state == "promoted"  # one storm never disproves
    apply_decay(s, now_ts=1000, half_life_ticks=10)
    decayed = s.get("k-home").reliability
    assert decayed < 1.0
    apply_decay(s, now_ts=1000, half_life_ticks=10)
    assert s.get("k-home").reliability == decayed  # same-time re-evaluation is idempotent


def test_R7_05_stale_revision_reconciliation():
    d = reconcile(effect="NONE", revision_valid=False, has_compensation=False)
    assert d.action == "reobserve" and d.replay is False


def test_R7_06_unknown_reconciliation_no_replay():
    d = reconcile(effect="UNKNOWN", revision_valid=True, has_compensation=False)
    assert d.action == "reobserve" and d.replay is False
    d2 = reconcile(effect="UNKNOWN", revision_valid=True, has_compensation=True,
                   compensation_allowed_reversible=False)
    assert d2.action == "reobserve" and d2.replay is False
    d3 = reconcile(effect="UNRECOGNIZED", revision_valid=True,
                   has_compensation=False)
    assert d3.action == "reobserve" and d3.replay is False


def test_R7_07_rollback_vs_no_safe_rollback_escalation():
    d = reconcile(effect="PARTIAL", revision_valid=True, has_compensation=True,
                  compensation_allowed_reversible=True)
    assert d.action == "rollback"
    d2 = reconcile(effect="PARTIAL", revision_valid=True, has_compensation=False)
    assert d2.action == "reobserve"
    stale = reconcile(effect="PARTIAL", revision_valid=False, has_compensation=True,
                      compensation_allowed_reversible=True)
    assert stale.action == "reobserve" and stale.replay is False


def test_R7_08_cheap_postcheck_accepted_for_sufficient_postcondition():
    v = AdaptiveValidator()
    d = v.decide(ValidationContext(effect="NONE", expected_anchor="home",
                                   observed_labels=frozenset({"home"}),
                                   confidence=0.9))
    assert d.method == "cheap-causal" and d.sufficient
    assert d.creates_revision is False


def test_R7_09_cheap_mismatch_requires_full_observe():
    v = AdaptiveValidator()
    d = v.decide(ValidationContext(effect="NONE", expected_anchor="home",
                                   observed_labels=frozenset({"away"}),
                                   confidence=0.9))
    assert d.method == "full-observe"
    d2 = v.decide(ValidationContext(effect="UNKNOWN", expected_anchor="home",
                                    observed_labels=frozenset({"home"}),
                                    confidence=0.9))
    assert d2.method == "full-observe"
    d3 = v.decide(ValidationContext(effect="UNRECOGNIZED", expected_anchor="home",
                                    observed_labels=frozenset({"home"}),
                                    confidence=0.9))
    assert d3.method == "full-observe"


def test_R7_10_mutation_invalidates_next_requires_observe():
    v = AdaptiveValidator()
    assert v.next_requires_observe(mutation_invalidated_revision=True,
                                   next_is_state_sensitive=True) is True
    assert v.next_requires_observe(mutation_invalidated_revision=False,
                                   next_is_state_sensitive=True) is False
    # End-to-end with FakeRuntime: revision changes after mutation.
    rt = FakeRuntime()
    rev = rt.observe()
    rt.execute([{"op": "home"}], expected_revision=rev)
    assert rt.revision != rev


def test_R7_11_cancellation_deadline_during_retrieval_validation():
    d = reconcile(effect="NONE", revision_valid=True, has_compensation=True,
                  compensation_allowed_reversible=True, cancelled=True)
    assert d.action == "escalate"
    d2 = reconcile(effect="NONE", revision_valid=True, has_compensation=False,
                   expired=True)
    assert d2.action == "escalate"


def test_R7_12_end_to_end_goal_retrieve_execute_validate_experience():
    from praxiom.knowledge.experience import ExperienceEpisode
    s = _store()
    hits = s.retrieve("home anchor", mode="action")
    assert hits and hits[0].kid == "k-home"
    rt = FakeRuntime()
    coord = ExecutionCoordinator(rt, DeviceLeaseManager())
    rev = rt.observe()
    spec = ExecutionSpec(namespace="ns", owner="op", task_type="t.e2e",
                         task_version=1, payload={"op": "home"}, revision=rev)
    att = coord.run(spec, owner="op")
    assert att.state == "succeeded"
    v = AdaptiveValidator()
    dec = v.decide(ValidationContext(effect="NONE", expected_anchor="home",
                                     observed_labels=frozenset({"home"}),
                                     confidence=0.95))
    assert dec.sufficient
    record_outcome(s, hits[0].kid, success=True, now_ts=300)
    ep = ExperienceEpisode(episode_id="ep-e2e", transition="goal->home",
                           outcome="succeeded", execution_id="exe-0001",
                           attempt_id=att.attempt_id, revision=rev)
    assert ExperienceEpisode.from_json(ep.to_json()).episode_id == "ep-e2e"
