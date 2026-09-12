from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from praxiom.adaptive.shadow import ShadowAdvisor, ShadowContext
from praxiom.learning.cycle import (
    CycleValidation,
    LearningCycleStore,
    LearningCycleV1,
)


@dataclass
class _Observation:
    revision: str
    state: str


@dataclass
class _Attempt:
    state: str = "succeeded"
    effect: str = "NONE"
    evidence: dict | None = None


def test_learning_cycle_records_one_action_and_fresh_post_observation(tmp_path: Path):
    observations = iter([_Observation("r1", "before"), _Observation("r2", "after")])
    calls = {"observe": 0, "execute": 0}
    shadow = ShadowAdvisor()
    shadow.recommend(ShadowContext(validated_confidence=0.95, pending=3, revision="r1"))

    def observe():
        calls["observe"] += 1
        return next(observations)

    def execute(revision: str):
        calls["execute"] += 1
        assert revision == "r1"
        return _Attempt(evidence={"replayed": False})

    cycle = LearningCycleV1(LearningCycleStore(tmp_path))
    item = cycle.run_single(
        operation_class="synthetic:single-action",
        skill_id="synthetic:skill",
        skill_version=1,
        observe=observe,
        execute=execute,
        classify_state=lambda obs: obs.state,
        validate=lambda _pre, _attempt, post: CycleValidation(
            accepted=post.state == "after",
            method="fresh-observe",
            post_state_class=post.state,
        ),
        teaching_ids=("teaching-1",),
        bootstrap_candidate_ids=("legacy-1",),
        shadow_snapshot=lambda: shadow.last_recommendation,
    )
    assert calls == {"observe": 2, "execute": 1}
    assert item.validation_accepted is True
    assert item.negative_evidence is False
    assert item.replayed is False
    assert item.teaching_ids == ("teaching-1",)
    assert item.bootstrap_candidate_ids == ("legacy-1",)
    assert item.shadow_recommended_batch_size == 3
    assert LearningCycleStore(tmp_path).load() == (item,)


def test_learning_cycle_keeps_failed_validation_as_negative_evidence(tmp_path: Path):
    observations = iter([_Observation("r1", "before"), _Observation("r2", "unchanged")])
    cycle = LearningCycleV1(LearningCycleStore(tmp_path))
    item = cycle.run_single(
        operation_class="synthetic:no-op",
        skill_id="synthetic:skill",
        skill_version=1,
        observe=lambda: next(observations),
        execute=lambda _revision: _Attempt(evidence={"replayed": False}),
        classify_state=lambda obs: obs.state,
        validate=lambda _pre, _attempt, post: CycleValidation(
            accepted=False,
            method="fresh-observe",
            post_state_class=post.state,
            reason="postcondition-not-met",
        ),
    )
    assert item.negative_evidence is True
    assert item.failure_reason == "postcondition-not-met"


def test_learning_cycle_does_not_retry_execute_on_exception(tmp_path: Path):
    calls = 0

    def execute(_revision: str):
        nonlocal calls
        calls += 1
        raise RuntimeError("ambiguous-mutation")

    cycle = LearningCycleV1(LearningCycleStore(tmp_path))
    with pytest.raises(RuntimeError, match="ambiguous-mutation"):
        cycle.run_single(
            operation_class="synthetic:ambiguous",
            skill_id="synthetic:skill",
            skill_version=1,
            observe=lambda: _Observation("r1", "before"),
            execute=execute,
            classify_state=lambda obs: obs.state,
            validate=lambda *_args: CycleValidation(
                accepted=False, method="none", post_state_class="unknown"
            ),
        )
    assert calls == 1
    assert LearningCycleStore(tmp_path).load() == ()


def test_learning_cycle_marks_nonfresh_post_revision_negative(tmp_path: Path):
    observations = iter([_Observation("r1", "before"), _Observation("r1", "after")])
    cycle = LearningCycleV1(LearningCycleStore(tmp_path))
    item = cycle.run_single(
        operation_class="synthetic:stale-post",
        skill_id="synthetic:skill",
        skill_version=1,
        observe=lambda: next(observations),
        execute=lambda _revision: _Attempt(evidence={"replayed": False}),
        classify_state=lambda obs: obs.state,
        validate=lambda *_args: pytest.fail("validator must not accept stale revision"),
    )
    assert item.negative_evidence is True
    assert item.validation_accepted is False
    assert item.failure_reason == "fresh-post-revision-required"
