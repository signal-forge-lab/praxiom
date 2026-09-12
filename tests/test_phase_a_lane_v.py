"""Post-R10 Phase A lane V deterministic tests (A7 only, D4=A).

Metadata-only Visual Flight Recorder V0-V3 compatibility hooks: the frozen
visual-hint vocabulary, timeline marker suggestion, metadata-only
artifact-ref construction/reservation, emit-ready hook kwargs, and the
read-only monotonic timeline/correlation projection future V0-V3 will
subscribe to. No recorder, no video, no AI retrieval, no media bytes, no
device mutation, and no import of any mutation-authority stack.

The journal conformance test arms automatically once the lane T
``praxiom.telemetry`` package becomes importable; until then it skips with
an explicit reason so this lane stays independently green while the five
lanes run in parallel.
"""
from __future__ import annotations

import copy
import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

from praxiom.visual_hooks import (
    ARTIFACT_FORMATS,
    ARTIFACT_KINDS,
    ARTIFACT_REF_KEYS,
    ARTIFACT_STATUSES,
    DEFAULT_CLIP_WINDOW_NS,
    MAX_ARTIFACT_REFS,
    MAX_TOKEN_LENGTH,
    MARKER_EVENT_TYPES,
    VISUAL_HINTS,
    VisualTimeline,
    artifact_ref,
    artifact_refs,
    assert_metadata_only,
    check_visual_hint,
    hook,
    is_metadata_only,
    new_artifact_id,
    suggest_visual_hint,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "src" / "praxiom" / "visual_hooks.py"
RUN = "run-v-0001"
AUTHORITY_PREFIXES = (
    "praxiom.ios_runtime",
    "praxiom.agent",
    "praxiom.skill",
    "praxiom.adaptive",
    "praxiom.telemetry",
)


def _ref(n: int = 1, **kw) -> dict:
    base = dict(
        artifact_id=new_artifact_id(entropy=lambda: f"{n:016x}"),
        kind="frame",
        status="reserved",
        format="png",
    )
    base.update(kw)
    return artifact_ref(**base)


def _event(seq: int, event_type: str = "attempt.completed", **fields) -> dict:
    base = {
        "schema_version": 1,
        "run_id": RUN,
        "event_id": f"evt-{seq:06d}",
        "seq": seq,
        "ts_utc": "2026-09-09T12:00:00.000Z",
        "monotonic_ns": seq * 1_000_000_000,
        "event_type": event_type,
        "payload": {},
    }
    base.update(fields)
    return base


def _sample_events() -> list[dict]:
    return [
        _event(1, "run.started"),
        _event(2, "runtime.observe"),
        _event(3, "attempt.sent", execution_id="exec-1", attempt_id="att-1"),
        _event(
            4,
            "attempt.completed",
            execution_id="exec-1",
            attempt_id="att-1",
            visual_hint="post-action",
            artifact_refs=[_ref(1)],
        ),
        _event(
            5,
            "validation.performed",
            parent_event_id="evt-000004",
            execution_id="exec-1",
            visual_hint="validation-mismatch",
        ),
        _event(6, "runtime.recover", visual_hint="recovery"),
        _event(7, "learning.recorded", visual_hint="learning-change",
               execution_id="exec-1"),
    ]


# ---------------------------------------------------------------------------
# A7 vocabularies (frozen by the 2026-09-09 design freeze, D4=A)
# ---------------------------------------------------------------------------

def test_visual_hint_vocabulary_is_the_frozen_d4_set():
    assert VISUAL_HINTS == frozenset({
        "post-action", "validation-mismatch", "recovery", "learning-change",
    })


def test_marker_event_types_are_the_a7_timeline_markers():
    assert MARKER_EVENT_TYPES == frozenset({
        "attempt.sent", "attempt.completed", "runtime.observe",
        "validation.performed", "runtime.recover",
        "learning.recorded", "policy.decision",
    })


def test_artifact_vocabularies_cover_the_v0_v3_retention_shapes():
    # frame=pre/post-action capture, clip=rolling/auto-clip video,
    # frameset=representative multi-frame set, retrieval-ref=AI retrieval.
    assert ARTIFACT_KINDS == frozenset(
        {"frame", "clip", "frameset", "retrieval-ref"})
    assert ARTIFACT_STATUSES == frozenset(
        {"reserved", "retained", "referenced", "dropped"})
    assert ARTIFACT_FORMATS == frozenset(
        {"png", "jpeg", "webp", "mp4", "manifest-json", "frameset-json"})
    assert ARTIFACT_REF_KEYS == frozenset(
        {"artifact_id", "kind", "status", "format"})


def test_suggest_visual_hint_maps_markers_with_gates():
    assert suggest_visual_hint("attempt.completed") == "post-action"
    assert suggest_visual_hint("attempt.sent") is None
    assert suggest_visual_hint("runtime.observe") is None
    assert suggest_visual_hint("runtime.recover") == "recovery"
    assert suggest_visual_hint("validation.performed") is None
    assert suggest_visual_hint("validation.performed", mismatch=True) \
        == "validation-mismatch"
    assert suggest_visual_hint("learning.recorded") == "learning-change"
    assert suggest_visual_hint("policy.decision") is None
    assert suggest_visual_hint("policy.decision", learned=True) \
        == "learning-change"
    assert suggest_visual_hint("runtime.status") is None
    with pytest.raises(ValueError):
        check_visual_hint("pre-action")
    check_visual_hint("post-action")  # allowlisted hint passes


# ---------------------------------------------------------------------------
# A7 artifact refs: identifiers/metadata only, never media bytes
# ---------------------------------------------------------------------------

def test_artifact_ref_is_metadata_only_with_reserved_default():
    ref = artifact_ref(artifact_id="art-0000000000000001", kind="clip",
                       format="mp4")
    assert set(ref) == set(ARTIFACT_REF_KEYS)
    assert ref["status"] == "reserved"  # Phase A reserves; it never captures
    assert is_metadata_only(ref)
    assert_metadata_only(ref)  # no-op on a clean ref


def test_new_artifact_id_shape_and_injected_entropy():
    assert new_artifact_id(entropy=lambda: "abc123def4567890") \
        == "art-abc123def4567890"
    assert re.fullmatch(r"art-[0-9a-f]{16}", new_artifact_id())
    with pytest.raises(ValueError):
        new_artifact_id(entropy=lambda: "not-hex-zzzzzzzz")


def test_artifact_ref_rejects_every_non_metadata_shape():
    good = dict(artifact_id="art-0000000000000001", kind="frame",
                status="reserved", format="png")
    with pytest.raises(ValueError):  # media bytes can never enter
        artifact_ref(**{**good, "status": b"reserved"})
    with pytest.raises(ValueError):  # nested containers can never enter
        artifact_ref(**{**good, "kind": ["frame"]})
    with pytest.raises(ValueError):  # unknown vocabulary fails loudly
        artifact_ref(**{**good, "kind": "video"})
    with pytest.raises(ValueError):  # unknown vocabulary fails loudly
        artifact_ref(**{**good, "status": "captured"})
    with pytest.raises(ValueError):  # token-unsafe + unknown vocabulary
        artifact_ref(**{**good, "format": "image/png"})
    with pytest.raises(ValueError):  # token-unsafe free text
        artifact_ref(**{**good, "artifact_id": "art-a b"})
    with pytest.raises(ValueError):  # wrong id namespace
        artifact_ref(**{**good, "artifact_id": "evt-000001"})
    for bad_key in ("path", "url", "uri", "data", "content", "bytes",
                    "udid", "ip", "bundle_id", "screen_text"):
        with pytest.raises(TypeError):  # no such parameter exists at all
            artifact_ref(**good, **{bad_key: "x"})


def test_is_metadata_only_rejects_foreign_and_oversized_values():
    ok = _ref()
    assert is_metadata_only(ok)
    assert not is_metadata_only({**ok, "path": "C:/x.png"})
    assert not is_metadata_only({**ok, "bytes": b"\x89PNG"})
    assert not is_metadata_only({**ok, "kind": 7})
    assert not is_metadata_only({**ok, "kind": "a b"})
    assert not is_metadata_only({**ok, "artifact_id": "art-" + "x" * 200})
    assert not is_metadata_only(["not", "a", "mapping"])
    with pytest.raises(ValueError):
        assert_metadata_only({**ok, "url": "http://device"})


def test_artifact_refs_respects_journal_bound_and_uniqueness():
    eight = [_ref(i + 1) for i in range(MAX_ARTIFACT_REFS)]
    assert artifact_refs(*eight) == eight
    with pytest.raises(ValueError):  # the journal would silently drop #9
        artifact_refs(*eight, _ref(9))
    with pytest.raises(ValueError):  # one event cannot list an id twice
        artifact_refs(_ref(1), _ref(1))
    with pytest.raises(ValueError):  # foreign entries never pass through
        artifact_refs(_ref(1), {**_ref(2), "path": "C:/x.png"})


# ---------------------------------------------------------------------------
# A7 hook: emit-ready kwargs for the lane T journal envelope
# ---------------------------------------------------------------------------

def test_hook_builds_emit_ready_kwargs():
    ref = _ref(3)
    assert hook("attempt.completed", refs=(ref,)) == {
        "visual_hint": "post-action",
        "artifact_refs": [ref],
    }
    assert hook("validation.performed") == {}  # no mismatch -> nothing to say
    assert hook("validation.performed", mismatch=True) == {
        "visual_hint": "validation-mismatch"}
    assert hook(hint="recovery") == {"visual_hint": "recovery"}
    assert hook("runtime.observe", hint="post-action") == {
        "visual_hint": "post-action"}  # explicit hint beats suggestion
    assert hook(refs=(ref,)) == {"artifact_refs": [ref]}
    with pytest.raises(ValueError):
        hook(hint="pre-action")
    out = hook("attempt.completed", refs=(ref,))
    out["artifact_refs"].append(_ref(4))  # mutating output must not stick
    assert hook("attempt.completed", refs=(ref,))["artifact_refs"] == [ref]


# ---------------------------------------------------------------------------
# A7 read-only monotonic timeline / correlation projection
# ---------------------------------------------------------------------------

def test_timeline_construction_enforces_stable_ids_and_sequence():
    events = _sample_events()
    timeline = VisualTimeline(events)
    assert timeline.run_id == RUN
    assert len(timeline.events) == 7
    with pytest.raises(ValueError):  # seq must strictly increase
        VisualTimeline([_event(1), _event(2), _event(2)])
    with pytest.raises(ValueError):
        VisualTimeline([_event(1), _event(3), _event(2)])
    with pytest.raises(ValueError):  # one timeline spans exactly one run
        VisualTimeline([_event(1), _event(2, run_id="run-other")])
    with pytest.raises(ValueError):  # event ids are stable and unique
        VisualTimeline([_event(1), _event(2, event_id="evt-000001")])
    with pytest.raises(ValueError):
        VisualTimeline([_event(1), {"seq": 2}])
    with pytest.raises(ValueError):
        VisualTimeline([_event(1), object()])
    with pytest.raises(ValueError):  # explicit run_id must match
        VisualTimeline(events, run_id="run-not-mine")
    empty = VisualTimeline([], run_id="run-empty")
    assert empty.run_id == "run-empty" and empty.events == ()


def test_timeline_is_an_isolated_read_only_snapshot():
    events = _sample_events()
    timeline = VisualTimeline(events)
    before = copy.deepcopy(events)
    events.append(_event(8, "policy.decision"))  # caller mutates after handoff
    events[3]["visual_hint"] = "learning-change"
    assert [e["event_id"] for e in timeline.events] \
        == [f"evt-{i:06d}" for i in range(1, 8)]
    for got, want in zip(timeline.events, before):
        assert got == want
    # queries never mutate the projection either
    snapshot = copy.deepcopy(timeline.events)
    timeline.markers
    timeline.by_hint("recovery")
    timeline.window(0, 10**12)
    timeline.artifact_index
    timeline.problems()
    assert timeline.events == snapshot == tuple(
        copy.deepcopy(e) for e in before)


def test_timeline_markers_hints_and_monotonic_windows():
    timeline = VisualTimeline(_sample_events())
    assert [e["event_id"] for e in timeline.markers] == [
        "evt-000004", "evt-000005", "evt-000006", "evt-000007"]
    assert [e["event_id"] for e in timeline.by_hint("post-action")] \
        == ["evt-000004"]
    assert [e["event_id"] for e in timeline.by_hint("recovery")] \
        == ["evt-000006"]
    with pytest.raises(ValueError):
        timeline.by_hint("pre-action")

    # inclusive monotonic window: the V2 frame-diff/auto-clip query surface
    got = timeline.window(4 * 10**9, 6 * 10**9)
    assert [e["event_id"] for e in got] == ["evt-000004", "evt-000005",
                                            "evt-000006"]
    with pytest.raises(ValueError):
        timeline.window(6, 5)

    # marker-centered clip window with explicit radii
    around = timeline.around("evt-000005", before_ns=1_500_000_000,
                             after_ns=500_000_000)
    assert [e["event_id"] for e in around] == ["evt-000004", "evt-000005"]
    with pytest.raises(ValueError):
        timeline.around("evt-999999")
    with pytest.raises(ValueError):
        timeline.around("evt-000005", before_ns=-1)
    # default window is a bounded placeholder radius, not evidence-tuned
    assert 0 < DEFAULT_CLIP_WINDOW_NS <= 1_000_000_000


def test_timeline_correlates_artifacts_and_execution_attempt_parents():
    timeline = VisualTimeline(_sample_events())
    index = timeline.artifact_index
    assert set(index) == {"art-0000000000000001"}
    assert [e["event_id"] for e in index["art-0000000000000001"]] \
        == ["evt-000004"]
    assert timeline.parent_of("evt-000005") == "evt-000004"
    assert [e["event_id"] for e in timeline.children("evt-000004")] \
        == ["evt-000005"]
    assert [e["event_id"] for e in timeline.by_execution("exec-1")] == [
        "evt-000003", "evt-000004", "evt-000005", "evt-000007"]
    assert [e["event_id"] for e in timeline.by_attempt("att-1")] == [
        "evt-000003", "evt-000004"]
    with pytest.raises(ValueError):
        timeline.children("evt-999999")
    with pytest.raises(ValueError):
        timeline.by_execution("")


def test_timeline_problems_report_foreign_damage_without_raising():
    damaged = [
        _event(1, "run.started"),
        _event(2, "attempt.completed", visual_hint="post-action"),
        _event(3, "attempt.completed", visual_hint="mystery-hint"),
        _event(4, "attempt.completed",
               artifact_refs=[{"artifact_id": "art-x", "path": "C:/a.png"}]),
        _event(5, "attempt.completed", parent_event_id="evt-000099"),
        _event(6, "attempt.completed", monotonic_ns=1),  # went backwards
    ]
    problems = VisualTimeline(damaged).problems()
    assert any("mystery-hint" in p and "seq 3" in p for p in problems)
    assert any("seq 4" in p and "metadata-only" in p for p in problems)
    assert any("seq 5" in p and "parent" in p for p in problems)
    assert any("seq 6" in p and "monotonic" in p for p in problems)
    assert VisualTimeline(_sample_events()).problems() == ()


# ---------------------------------------------------------------------------
# A7 authority boundaries: no mutation stack, no I/O, no media bytes
# ---------------------------------------------------------------------------

def test_module_imports_no_authority_stack():
    probe = (
        "import sys, praxiom.visual_hooks as vh; "
        "bad = [m for m in sys.modules if m.startswith(%r)]; "
        "assert not bad, bad; assert vh.VISUAL_HINTS; print('pure')"
        % (AUTHORITY_PREFIXES,)
    )
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                          text=True, cwd=REPO_ROOT)
    assert done.returncode == 0, done.stderr
    assert "pure" in done.stdout


def test_module_source_declares_no_praxiom_dependency_and_no_io():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "import praxiom" not in source  # stdlib-only, zero coupling
    assert "open(" not in source  # no file/device I/O exists to misuse


# ---------------------------------------------------------------------------
# Conformance with the lane T journal envelope (arms once importable)
# ---------------------------------------------------------------------------

def test_journal_envelope_conformance_when_lane_t_lands():
    try:
        journal = importlib.import_module("praxiom.telemetry.journal")
    except Exception as exc:  # noqa: BLE001 - lane T may be mid-authoring
        pytest.skip(
            f"lane T praxiom.telemetry not importable yet "
            f"({exc.__class__.__name__}); this conformance check arms "
            f"automatically once it lands"
        )
    assert VISUAL_HINTS == journal.ALLOWED_VISUAL_HINTS
    assert ARTIFACT_REF_KEYS == journal.ALLOWED_ARTIFACT_KEYS
    assert MAX_ARTIFACT_REFS == journal.MAX_ARTIFACT_REFS
    assert MAX_TOKEN_LENGTH == journal.MAX_TOKEN_LENGTH
    assert MARKER_EVENT_TYPES <= journal.ALLOWED_EVENT_TYPES

    # A ref minted here survives the journal sanitizer losslessly: no
    # silent drops, no fingerprinting, no redaction counters.
    ref = _ref(7, kind="clip", format="mp4")
    event = journal.build_event(
        run_id=RUN, seq=1, ts_utc="2026-09-09T12:00:00.000Z",
        monotonic_ns=42, event_type="attempt.completed", phase="attempt",
        visual_hint="post-action", artifact_refs=[ref],
    )
    assert event["visual_hint"] == "post-action"
    assert event["artifact_refs"] == [ref]
    assert event["payload"].get("redacted_keys", 0) == 0

    for hint in VISUAL_HINTS:  # every frozen hint round-trips
        ev = journal.build_event(
            run_id=RUN, seq=2, ts_utc="2026-09-09T12:00:00.000Z",
            monotonic_ns=43, event_type="learning.recorded", phase="learning",
            visual_hint=hint,
        )
        assert ev["visual_hint"] == hint
