from __future__ import annotations

from pathlib import Path

import pytest

from praxiom.adaptive.shadow import ShadowAdvisor, ShadowContext
from praxiom.adaptive.teaching import TeachingInfluence, apply_teaching_influence
from praxiom.knowledge.teaching import HumanTeachingStore, promote_fact_teaching


def test_answered_is_not_learned_until_review_and_acceptance(tmp_path: Path):
    store = HumanTeachingStore(tmp_path)
    question = store.ask("Which generic policy should apply?", context={"revision": "rev-1"})
    teaching = store.answer(question.question_id, "Prefer the safer path", teaching_kind="policy")
    questions, teachings = store.load()
    assert questions[question.question_id].state == "answered"
    assert teachings[teaching.teaching_id].state == "received"
    assert teaching.teaching_id not in store.learned_ids()

    store.review(teaching.teaching_id, conflict=False, decision="policy-reviewed")
    learned = store.mark_learned(teaching.teaching_id, decision="policy-accepted")
    assert learned.state == "learned"
    assert store.load()[0][question.question_id].state == "learned"


def test_conflict_blocks_learning(tmp_path: Path):
    store = HumanTeachingStore(tmp_path)
    teaching = store.submit("A reusable fact", teaching_kind="fact")
    store.review(teaching.teaching_id, conflict=True, decision="conflicting-knowledge")
    with pytest.raises(ValueError, match="conflict-blocks"):
        store.mark_learned(teaching.teaching_id, decision="fact-promoted")


def test_fact_teaching_uses_existing_promotion_evidence_floor(tmp_path: Path):
    store = HumanTeachingStore(tmp_path)
    teaching = store.submit("Synthetic fact for promotion", teaching_kind="fact")
    insufficient = promote_fact_teaching(store, teaching.teaching_id, supports=1)
    assert insufficient.state == "conflict_checked"
    assert teaching.teaching_id not in store.learned_ids()

    other = store.submit("Synthetic corroborated fact", teaching_kind="fact")
    promoted = promote_fact_teaching(
        store, other.teaching_id, supports=2, evidence_ids=("ev-a", "ev-b")
    )
    assert promoted.state == "promoted"
    assert other.teaching_id in store.learned_ids()


def test_only_learned_teaching_can_influence_shadow(tmp_path: Path):
    store = HumanTeachingStore(tmp_path)
    teaching = store.submit("Bound this operation", teaching_kind="policy")
    influence = TeachingInfluence(
        teaching_ids=(teaching.teaching_id,),
        confidence_cap=0.80,
        force_full_observe=True,
        max_batch=1,
        disable_reuse=True,
    )
    ctx = ShadowContext(
        validated_confidence=0.99,
        pending=4,
        revision="r-1",
        max_batch=8,
        macro_reuse_eligible=True,
        path_reuse_eligible=True,
    )
    with pytest.raises(ValueError, match="unlearned"):
        apply_teaching_influence(ctx, influence, learned_ids=store.learned_ids())

    store.review(teaching.teaching_id, conflict=False, decision="policy-reviewed")
    store.mark_learned(teaching.teaching_id, decision="policy-accepted")
    influenced = apply_teaching_influence(ctx, influence, learned_ids=store.learned_ids())
    rec = ShadowAdvisor().recommend(influenced)
    assert influenced.validated_confidence == 0.80
    assert influenced.max_batch == 1
    assert influenced.macro_reuse_eligible is False
    assert rec.batch is not None and rec.batch.size == 1
    assert rec.observation is not None and rec.observation.method == "full-observe"
