"""Shared Phase-B contract smoke test (helpers only, no lane logic).

Proves the shared seam imports cleanly and honors its invariants:
fake Runtime revision binding, deterministic clock monotonicity, and
privacy-safe synthetic factories. Lane behavior stays in R6/R7 matrices.
"""
import pytest

from praxiom.ios_runtime.models import ErrorCode, ErrorEffect, RuntimeOperationError
from tests.fakes import FakeRuntime, ManualClock
from tests.synthetic_fixtures import (
    SYNTHETIC_PROVENANCE,
    make_episode,
    make_knowledge_item,
    make_knowledge_record,
    make_spec,
    make_validation_context,
    make_world,
)


def test_fake_runtime_revision_binding_and_invalidation():
    rt = FakeRuntime()
    rev = rt.observe()
    res = rt.execute([{"op": "home"}], expected_revision=rev)
    assert res["effect"] == "NONE"
    assert rt.revision != rev  # mutation invalidates the accepted revision
    with pytest.raises(RuntimeOperationError) as excinfo:
        rt.execute([{"op": "home"}], expected_revision=rev)  # stale rejected
    assert excinfo.value.code == ErrorCode.STALE_REVISION
    assert excinfo.value.effect == ErrorEffect.NONE


def test_manual_clock_monotonic_and_callable():
    clock = ManualClock(start_ms=1_000)
    assert clock.now_ms() == 1_000
    assert clock.advance(50) == 1_050
    with pytest.raises(ValueError):
        clock.advance(-1)  # no time travel
    assert clock.as_fn()() == 1_050


def test_synthetic_factories_privacy_safe_and_deterministic():
    spec = make_spec()
    spec.validate(now_ms=500)  # revision-bound, positive version
    assert spec.namespace and spec.task_version >= 1 and spec.revision
    ep = make_episode()
    assert ep.provenance == SYNTHETIC_PROVENANCE
    raw = ep.to_json()
    for token in ("screenshot", "password", "credential"):
        assert token not in raw
    rec = make_knowledge_record()
    assert rec.kid and rec.state == "raw"
    item = make_knowledge_item()
    assert item.state == "promoted"
    world = make_world()
    assert world.revision
    ctx = make_validation_context()
    assert ctx.effect == "NONE"
    # Deterministic IDs: two fresh episodes differ but order stably.
    assert make_episode().episode_id != ep.episode_id
