"""Metadata-only Visual Flight Recorder V0-V3 compatibility hooks (A7, D4=A).

Phase A adds correlation/artifact hooks only. This module deliberately
implements **no** recorder, no video capture, no frame differencing, no AI
retrieval, and carries no media bytes: Visual V0-V3 remains a separate
read-only track that will later subscribe to the run journal's monotonic
timeline and attach retained artifacts through ids.

What Phase A provides here so later Visual work is purely additive:

- the frozen ``visual_hint`` vocabulary (design freeze 2026-09-09, D4=A):
  ``post-action``, ``validation-mismatch``, ``recovery``, ``learning-change``;
- :func:`suggest_visual_hint` for the A7 timeline marker event types
  (action sent/completed, observe, validation, recovery, learning/policy);
- metadata-only :func:`artifact_ref` construction: identifiers and small
  vocabularies only. There is intentionally no key or value shape able to
  carry image/video bytes, paths, URLs, device identifiers, bundle ids,
  screen text, or any raw payload. Phase A mints ``status="reserved"``
  refs only — capture and retention belong to future V0/V2;
- :func:`hook`: emit-ready ``visual_hint`` / ``artifact_refs`` keyword
  arguments for the run journal envelope;
- :class:`VisualTimeline`: a read-only, deep-copied monotonic-timeline
  projection over journal event dicts — markers, hint filters, inclusive
  monotonic windows, marker-centered clip windows (V2 shape), artifact-id
  correlation (V3 shape), and parent/execution/attempt correlation (V1
  shape). Visual artifacts correlate through event ids and monotonic time,
  never through hidden device-stack calls.

Authority: nothing here can mutate a device. This module imports no other
``praxiom`` module at all (the lane V test suite proves the import graph)
and performs no I/O; it is and remains advisory/read-only relative to the
Runtime / Coordinator / Skill mutation authorities. A visual failure can
therefore never grant or widen mutation authority.

The vocabularies mirror the run journal envelope allowlists exactly
(``praxiom.telemetry.journal``: ``ALLOWED_VISUAL_HINTS``,
``ALLOWED_ARTIFACT_KEYS``, ``MAX_ARTIFACT_REFS``, ``MAX_TOKEN_LENGTH``);
the conformance test in ``tests/test_phase_a_lane_v.py`` arms as soon as
that package is importable and fails loudly if the two ever drift apart.
"""
from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Callable, Iterable, Mapping

__all__ = [
    "ARTIFACT_FORMATS",
    "ARTIFACT_ID_PATTERN",
    "ARTIFACT_KINDS",
    "ARTIFACT_REF_KEYS",
    "ARTIFACT_STATUSES",
    "DEFAULT_CLIP_WINDOW_NS",
    "MARKER_EVENT_TYPES",
    "MAX_ARTIFACT_REFS",
    "MAX_TOKEN_LENGTH",
    "VISUAL_HINTS",
    "VisualTimeline",
    "artifact_ref",
    "artifact_refs",
    "assert_metadata_only",
    "check_visual_hint",
    "hook",
    "is_metadata_only",
    "new_artifact_id",
    "suggest_visual_hint",
]

# --- frozen vocabularies (design freeze 2026-09-09, D4=A) ------------------

#: The only visual hints Phase A may emit on journal events.
VISUAL_HINTS = frozenset({
    "post-action", "validation-mismatch", "recovery", "learning-change",
})

#: Marker event types of the A7 monotonic timeline a future V0 recorder
#: subscribes to (action sent/completed, observe, validation, recovery,
#: learning/policy change).
MARKER_EVENT_TYPES = frozenset({
    "attempt.sent", "attempt.completed", "runtime.observe",
    "validation.performed", "runtime.recover",
    "learning.recorded", "policy.decision",
})

#: Artifact reference keys: identifiers/metadata only. There is deliberately
#: no path, URL, content, or bytes key.
ARTIFACT_REF_KEYS = frozenset({"artifact_id", "kind", "status", "format"})

#: Retention shapes of the envisioned future track: single pre/post-action
#: frames, rolling/auto-clip video, representative multi-frame sets, and AI
#: retrieval references.
ARTIFACT_KINDS = frozenset({"frame", "clip", "frameset", "retrieval-ref"})

#: Lifecycle of an artifact reference. Phase A only ever mints "reserved".
ARTIFACT_STATUSES = frozenset({"reserved", "retained", "referenced", "dropped"})

#: Token-safe container labels (no "/" — the journal token charset excludes
#: it, so MIME-looking strings would be fingerprinted and lose identity).
ARTIFACT_FORMATS = frozenset({
    "png", "jpeg", "webp", "mp4", "manifest-json", "frameset-json",
})

# Bounds mirrored from the journal envelope; the conformance test enforces
# the match once the telemetry package is importable.
MAX_ARTIFACT_REFS = 8
MAX_TOKEN_LENGTH = 96

#: Default marker-centered clip radius (each side, nanoseconds). A bounded
#: placeholder only — real retention thresholds are a V2 decision that
#: requires real-device evidence (Phase A must not invent them).
DEFAULT_CLIP_WINDOW_NS = 250_000_000

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_.:@+-]{1,%d}\Z" % MAX_TOKEN_LENGTH)
_ARTIFACT_ID_BODY = 64
ARTIFACT_ID_PATTERN = re.compile(r"art-[0-9A-Za-z]{1,%d}\Z" % _ARTIFACT_ID_BODY)


# --- validation helpers -----------------------------------------------------

def _require_token(name: str, value: Any) -> str:
    """Fail loudly unless ``value`` is a bounded token-shaped string."""
    if not isinstance(value, str):
        raise ValueError(
            f"{name} must be a string; media bytes, containers, and raw "
            f"payloads have no path into artifact metadata"
        )
    if not value or len(value) > MAX_TOKEN_LENGTH \
            or _TOKEN_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{name} must match {_TOKEN_PATTERN.pattern!r} with length "
            f"1..{MAX_TOKEN_LENGTH}: {value!r}"
        )
    return value


def _require_vocab(name: str, value: Any, allowed: frozenset[str]) -> str:
    token = _require_token(name, value)
    if token not in allowed:
        raise ValueError(
            f"{name} {token!r} not allowed (allowed: {sorted(allowed)})"
        )
    return token


def _check_ref(ref: Any) -> None:
    """Raise ``ValueError`` unless ``ref`` is metadata-only by construction."""
    if not isinstance(ref, Mapping):
        raise ValueError("artifact ref must be a mapping")
    for key, value in ref.items():
        if key not in ARTIFACT_REF_KEYS:
            raise ValueError(
                f"artifact ref key {key!r} not allowed — identifiers and "
                f"vocabularies only, never paths/URLs/content"
            )
        _require_token(f"artifact ref {key!r}", value)


# --- artifact references ----------------------------------------------------

def new_artifact_id(entropy: Callable[[], str] | None = None) -> str:
    """Mint one opaque artifact id ``art-<16 hex>``.

    ``entropy`` is injectable for deterministic tests; it must return
    exactly 16 lowercase hex characters.
    """
    raw = entropy() if entropy is not None else uuid.uuid4().hex[:16]
    if not isinstance(raw, str) or re.fullmatch(r"[0-9a-f]{16}", raw) is None:
        raise ValueError("artifact entropy must be 16 lowercase hex characters")
    return f"art-{raw}"


def artifact_ref(
    *,
    artifact_id: str,
    kind: str,
    format: str,  # noqa: A002 - mirrors the journal envelope key
    status: str = "reserved",
) -> dict[str, str]:
    """Build one metadata-only artifact reference.

    Every value is validated against a bounded vocabulary or id pattern, so
    the result always survives the journal sanitizer losslessly and can
    never carry media bytes, paths, URLs, or raw payloads. Phase A callers
    keep the ``reserved`` default — retention is future V0/V2 work.
    """
    _require_token("artifact_id", artifact_id)
    if ARTIFACT_ID_PATTERN.fullmatch(artifact_id) is None:
        raise ValueError(
            f"artifact_id must match {ARTIFACT_ID_PATTERN.pattern!r}"
        )
    _require_vocab("kind", kind, ARTIFACT_KINDS)
    _require_vocab("status", status, ARTIFACT_STATUSES)
    _require_vocab("format", format, ARTIFACT_FORMATS)
    return {
        "artifact_id": artifact_id,
        "kind": kind,
        "status": status,
        "format": format,
    }


def is_metadata_only(ref: Any) -> bool:
    """True iff ``ref`` could pass the journal ref sanitizer unredacted."""
    try:
        _check_ref(ref)
    except ValueError:
        return False
    return True


def assert_metadata_only(ref: Any) -> None:
    """Raise ``ValueError`` unless ``ref`` is metadata-only (privacy guard)."""
    _check_ref(ref)


def artifact_refs(*refs: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Validate a bounded, duplicate-free artifact-ref list for one event.

    Mirrors the journal bound (``MAX_ARTIFACT_REFS``) so a compliant list
    is never silently truncated, and rejects duplicate artifact ids within
    one event.
    """
    if len(refs) > MAX_ARTIFACT_REFS:
        raise ValueError(
            f"at most {MAX_ARTIFACT_REFS} artifact refs per event "
            f"(journal bound); got {len(refs)}"
        )
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        _check_ref(ref)
        artifact_id = ref.get("artifact_id")
        if artifact_id in seen:
            raise ValueError(
                f"duplicate artifact_id {artifact_id!r} in one event"
            )
        seen.add(artifact_id)
        clean.append(dict(ref))
    return clean


# --- visual hints ------------------------------------------------------------

def check_visual_hint(hint: Any) -> None:
    """Raise ``ValueError`` unless ``hint`` is in the frozen vocabulary."""
    if hint not in VISUAL_HINTS:
        raise ValueError(
            f"visual_hint not allowed: {hint!r} "
            f"(allowed: {sorted(VISUAL_HINTS)})"
        )


def suggest_visual_hint(
    event_type: str | None,
    *,
    mismatch: bool = False,
    learned: bool = False,
) -> str | None:
    """Suggest the frozen visual hint for one timeline marker, if any.

    ``attempt.completed`` -> ``post-action``; ``validation.performed`` ->
    ``validation-mismatch`` only on mismatch; ``runtime.recover`` ->
    ``recovery``; ``learning.recorded`` -> ``learning-change``;
    ``policy.decision`` -> ``learning-change`` only when a decision actually
    changed. Everything else (including observe and action-sent markers)
    carries no hint in Phase A.
    """
    if event_type == "attempt.completed":
        return "post-action"
    if event_type == "validation.performed":
        return "validation-mismatch" if mismatch else None
    if event_type == "runtime.recover":
        return "recovery"
    if event_type == "learning.recorded":
        return "learning-change"
    if event_type == "policy.decision":
        return "learning-change" if learned else None
    return None


def hook(
    event_type: str | None = None,
    *,
    hint: str | None = None,
    refs: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = (),
    mismatch: bool = False,
    learned: bool = False,
) -> dict[str, Any]:
    """Build emit-ready ``visual_hint``/``artifact_refs`` journal kwargs.

    An explicit ``hint`` (validated) beats the suggestion for
    ``event_type``. Empty input yields ``{}`` so callers can splat the
    result unconditionally.
    """
    if hint is not None:
        check_visual_hint(hint)
    resolved = hint
    if resolved is None and event_type is not None:
        resolved = suggest_visual_hint(
            event_type, mismatch=mismatch, learned=learned
        )
    out: dict[str, Any] = {}
    if resolved is not None:
        out["visual_hint"] = resolved
    if refs:
        out["artifact_refs"] = artifact_refs(*refs)
    return out


# --- read-only timeline projection -------------------------------------------

def _valid_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _mono_ns(event: Mapping[str, Any]) -> int | None:
    value = event.get("monotonic_ns")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _check_ns(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative int (monotonic ns)")
    return value


class VisualTimeline:
    """Read-only monotonic-timeline view over one run's journal events.

    Future Visual V0-V3 subscribes here: V0 marks/retains around
    :attr:`markers`, V1 correlates through event ids / parents /
    executions / attempts, V2 clips via :meth:`window`/:meth:`around`, V3
    retrieves via :attr:`artifact_index`. Construction deep-copies the
    input, so the projection is isolated from later caller mutation, and no
    query ever mutates it.

    Structural violations that would corrupt correlation (non-mappings,
    missing/duplicate ``event_id``, missing/non-positive or non-increasing
    ``seq``, mixed ``run_id``) fail loudly at construction; per-event
    damage that a future subscriber should *report* rather than crash on
    (unknown hints, non-metadata refs, orphan parents, monotonic
    regressions — the latter are legal across process restarts) is
    surfaced through :meth:`problems`.
    """

    def __init__(
        self,
        events: Iterable[Mapping[str, Any]],
        *,
        run_id: str | None = None,
    ) -> None:
        checked: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        resolved_run = run_id
        last_seq = 0
        for raw in events:
            if not isinstance(raw, Mapping):
                raise ValueError("timeline events must be mappings")
            event = copy.deepcopy(dict(raw))
            event_id = _valid_id(event.get("event_id"), "event_id")
            if event_id in seen_ids:
                raise ValueError(f"duplicate event_id {event_id!r}")
            seq = event.get("seq")
            if not isinstance(seq, int) or isinstance(seq, bool) or seq <= 0:
                raise ValueError(
                    f"event {event_id!r} needs a positive int seq"
                )
            if seq <= last_seq:
                raise ValueError(
                    f"seq must strictly increase: {seq} after {last_seq}"
                )
            event_run = _valid_id(event.get("run_id"), f"event {event_id!r} run_id")
            if resolved_run is None:
                resolved_run = event_run
            elif event_run != resolved_run:
                raise ValueError(
                    f"timeline spans multiple runs: {event_run!r} vs "
                    f"{resolved_run!r}"
                )
            seen_ids.add(event_id)
            last_seq = seq
            checked.append(event)
        self._events: tuple[dict[str, Any], ...] = tuple(checked)
        self._run_id = resolved_run
        self._ids = frozenset(seen_ids)

    @property
    def run_id(self) -> str | None:
        return self._run_id

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        """The isolated event snapshot, seq order (shared — do not mutate)."""
        return self._events

    @property
    def markers(self) -> tuple[dict[str, Any], ...]:
        """Events carrying a visual hint or artifact refs, seq order."""
        return tuple(
            e for e in self._events
            if "visual_hint" in e or e.get("artifact_refs")
        )

    def by_hint(self, hint: str) -> tuple[dict[str, Any], ...]:
        """Events carrying exactly ``hint`` (validated), seq order."""
        check_visual_hint(hint)
        return tuple(e for e in self._events if e.get("visual_hint") == hint)

    def window(self, start_ns: int, end_ns: int) -> tuple[dict[str, Any], ...]:
        """Events with ``monotonic_ns`` in the inclusive ``[start, end]``."""
        start = _check_ns(start_ns, "start_ns")
        end = _check_ns(end_ns, "end_ns")
        if start > end:
            raise ValueError("start_ns must not exceed end_ns")
        return tuple(
            e for e in self._events
            if (mono := _mono_ns(e)) is not None and start <= mono <= end
        )

    def around(
        self,
        event_id: str,
        *,
        before_ns: int = DEFAULT_CLIP_WINDOW_NS,
        after_ns: int = DEFAULT_CLIP_WINDOW_NS,
    ) -> tuple[dict[str, Any], ...]:
        """Events within ``[t-before_ns, t+after_ns]`` around one event.

        The marker-centered clip window a future V2 auto-clip pass will
        ask for; radii default to the bounded placeholder, never to a
        physically-tuned threshold.
        """
        _valid_id(event_id, "event_id")
        if event_id not in self._ids:
            raise ValueError(f"unknown event_id {event_id!r}")
        before = _check_ns(before_ns, "before_ns")
        after = _check_ns(after_ns, "after_ns")
        center: int | None = None
        for event in self._events:
            if event["event_id"] == event_id:
                center = _mono_ns(event)
                break
        if center is None:
            raise ValueError(
                f"event {event_id!r} has no valid monotonic_ns to center on"
            )
        return self.window(center - before, center + after)

    @property
    def artifact_index(self) -> dict[str, tuple[dict[str, Any], ...]]:
        """artifact_id -> events referencing it (V3 retrieval correlation)."""
        index: dict[str, list[dict[str, Any]]] = {}
        for event in self._events:
            refs = event.get("artifact_refs")
            if not isinstance(refs, (list, tuple)):
                continue
            for ref in refs:
                if isinstance(ref, Mapping) \
                        and isinstance(ref.get("artifact_id"), str):
                    index.setdefault(ref["artifact_id"], []).append(event)
        return {aid: tuple(events) for aid, events in index.items()}

    def parent_of(self, event_id: str) -> str | None:
        """The ``parent_event_id`` of one event, if set."""
        _valid_id(event_id, "event_id")
        for event in self._events:
            if event["event_id"] == event_id:
                parent = event.get("parent_event_id")
                return parent if isinstance(parent, str) else None
        raise ValueError(f"unknown event_id {event_id!r}")

    def children(self, event_id: str) -> tuple[dict[str, Any], ...]:
        """Events whose ``parent_event_id`` is ``event_id``, seq order."""
        _valid_id(event_id, "event_id")
        if event_id not in self._ids:
            raise ValueError(f"unknown event_id {event_id!r}")
        return tuple(
            e for e in self._events if e.get("parent_event_id") == event_id
        )

    def by_execution(self, execution_id: str) -> tuple[dict[str, Any], ...]:
        """Events correlated to one execution id, seq order."""
        _valid_id(execution_id, "execution_id")
        return tuple(
            e for e in self._events if e.get("execution_id") == execution_id
        )

    def by_attempt(self, attempt_id: str) -> tuple[dict[str, Any], ...]:
        """Events correlated to one attempt id, seq order."""
        _valid_id(attempt_id, "attempt_id")
        return tuple(
            e for e in self._events if e.get("attempt_id") == attempt_id
        )

    def problems(self) -> tuple[str, ...]:
        """Report per-event visual/correlation damage instead of raising.

        Unknown visual hints, non-metadata-only or over-long artifact ref
        lists, orphan parents, missing/invalid monotonic stamps, and
        monotonic regressions (legal across process restarts, suspicious
        within one session) are returned as human-readable ``seq``-anchored
        findings. An empty tuple means the timeline is visually sound.
        """
        findings: list[str] = []
        last_mono: int | None = None
        for event in self._events:
            seq = event["seq"]
            hint = event.get("visual_hint")
            if hint is not None and hint not in VISUAL_HINTS:
                findings.append(
                    f"seq {seq}: unknown visual_hint {hint!r}"
                )
            refs = event.get("artifact_refs")
            if refs is not None:
                if not isinstance(refs, (list, tuple)):
                    findings.append(
                        f"seq {seq}: artifact_refs must be a list"
                    )
                else:
                    if len(refs) > MAX_ARTIFACT_REFS:
                        findings.append(
                            f"seq {seq}: {len(refs)} artifact refs exceed "
                            f"the journal bound {MAX_ARTIFACT_REFS}"
                        )
                    for ref in refs:
                        if not is_metadata_only(ref):
                            findings.append(
                                f"seq {seq}: artifact ref is not "
                                f"metadata-only"
                            )
            parent = event.get("parent_event_id")
            if parent is not None and parent not in self._ids:
                findings.append(
                    f"seq {seq}: parent_event_id {parent!r} not in timeline"
                )
            mono = _mono_ns(event)
            if "monotonic_ns" in event and mono is None:
                findings.append(
                    f"seq {seq}: monotonic_ns is not a non-negative int"
                )
            elif mono is not None and last_mono is not None \
                    and mono < last_mono:
                findings.append(
                    f"seq {seq}: monotonic_ns decreased below seq-earlier "
                    f"{last_mono} (process restart or unsynchronized writer?)"
                )
            if mono is not None:
                last_mono = mono
        return tuple(findings)
