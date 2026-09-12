"""Passive, cross-process projection for the read-only Praxiom Monitor.

The Monitor never calls Runtime ``observe``. Execution paths may opt in by
passing :meth:`LatestFrameStore.publish` as ``NativeIosRuntime(frame_sink=...)``;
the already-captured screenshot is then mirrored as one replace-in-place
latest frame. No image history is retained here (Visual Flight Recorder owns
that future concern).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from praxiom.ios_runtime.models import Observation
from praxiom.knowledge.teaching import HumanTeachingStore
from praxiom.telemetry.context import resolve_state_root
from praxiom.telemetry.journal import fingerprint_revision

__all__ = [
    "FRAME_PROJECTION_ENV",
    "LatestFrameStore",
    "MonitorSnapshotBuilder",
    "frame_sink_from_env",
]

_MONITOR_DIR = "monitor"
_FRAME_FILE = "latest-frame.png"
_META_FILE = "latest-frame.json"
_MAX_FRAME_BYTES = 32 * 1024 * 1024
_MAX_META_BYTES = 4096
_MAX_JOURNAL_TAIL_BYTES = 2 * 1024 * 1024
FRAME_PROJECTION_ENV = "PRAXIOM_MONITOR_FRAME_PROJECTION"
_ACTIVITY_FIELDS = (
    "event_type",
    "seq",
    "timestamp_utc",
    "phase",
    "status",
    "duration_ms",
    "effect",
    "outcome",
    "error_code",
    "fallback_reason",
    "policy_recommendation",
    "actual_policy",
    "behavior_id",
    "skill_id",
    "visual_hint",
)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class LatestFrameStore:
    """Best-effort latest-frame store; retains exactly one frame + metadata."""

    def __init__(self, state_root: Path | str | None = None) -> None:
        root = Path(state_root) if state_root is not None else resolve_state_root()
        self.root = root / _MONITOR_DIR
        self.frame_path = self.root / _FRAME_FILE
        self.metadata_path = self.root / _META_FILE

    def publish(self, png: bytes, observation: Observation) -> None:
        if not isinstance(png, bytes) or not png or len(png) > _MAX_FRAME_BYTES:
            raise ValueError("monitor frame must be non-empty bounded bytes")
        if observation.frame.format != "png":
            raise ValueError("monitor frame projection supports png only")
        digest = hashlib.sha256(png).hexdigest()
        metadata = {
            "captured_at": observation.captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "width": observation.frame.width,
            "height": observation.frame.height,
            "format": "png",
            "revision": fingerprint_revision(observation.revision),
            "sha256": digest,
            "byte_length": len(png),
        }
        _atomic_write(self.frame_path, png)
        _atomic_write(
            self.metadata_path,
            (json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
        )

    def read_metadata(self) -> dict[str, Any] | None:
        try:
            if self.metadata_path.stat().st_size > _MAX_META_BYTES:
                return None
            value = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        return value

    def read_frame(self) -> bytes | None:
        metadata = self.read_metadata()
        if metadata is None:
            return None
        try:
            data = self.frame_path.read_bytes()
        except OSError:
            return None
        if not data or len(data) > _MAX_FRAME_BYTES:
            return None
        expected = metadata.get("sha256")
        if not isinstance(expected, str) or hashlib.sha256(data).hexdigest() != expected:
            return None
        return data


def frame_sink_from_env(
    state_root: Path | str | None = None,
    *,
    environ: dict[str, str] | None = None,
):
    """Return an opt-in passive frame sink, otherwise ``None``.

    Screenshot persistence is sensitive and therefore never enabled merely by
    starting the Monitor UI. The execution process must explicitly set
    ``PRAXIOM_MONITOR_FRAME_PROJECTION=1``.
    """
    source = environ if environ is not None else os.environ
    if source.get(FRAME_PROJECTION_ENV, "").strip() != "1":
        return None
    return LatestFrameStore(state_root).publish


def _latest_run_dir(state_root: Path) -> Path | None:
    runs = state_root / "runs"
    if not runs.is_dir():
        return None
    candidates: list[tuple[int, Path]] = []
    for entry in runs.iterdir():
        events = entry / "events.jsonl"
        if not entry.is_dir() or not events.is_file():
            continue
        try:
            candidates.append((events.stat().st_mtime_ns, entry))
        except OSError:
            continue
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def _read_recent_events(path: Path, limit: int) -> tuple[list[dict[str, Any]], int]:
    events: deque[dict[str, Any]] = deque(maxlen=limit)
    malformed = 0
    try:
        size = path.stat().st_size
        start = max(0, size - _MAX_JOURNAL_TAIL_BYTES)
        handle = path.open("rb")
    except OSError:
        return [], 0
    with handle:
        handle.seek(start)
        data = handle.read(_MAX_JOURNAL_TAIL_BYTES)
    lines = data.splitlines()
    if start and lines:
        # The first tail chunk entry may start mid-record.
        lines = lines[1:]
    for raw in lines[-limit:]:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(value, dict):
            events.append(value)
        else:
            malformed += 1
    return list(events), malformed


def _activity(event: dict[str, Any]) -> dict[str, Any]:
    return {key: event[key] for key in _ACTIVITY_FIELDS if key in event}


class MonitorSnapshotBuilder:
    """Build one bounded read-only projection from existing durable evidence."""

    def __init__(
        self,
        *,
        state_root: Path | str | None = None,
        frame_store: LatestFrameStore | None = None,
        event_limit: int = 120,
    ) -> None:
        if isinstance(event_limit, bool) or not isinstance(event_limit, int) or event_limit < 1:
            raise ValueError("event_limit must be a positive integer")
        self.state_root = Path(state_root) if state_root is not None else resolve_state_root()
        self.frame_store = frame_store or LatestFrameStore(self.state_root)
        self.human_store = HumanTeachingStore(self.state_root)
        self.event_limit = event_limit

    def build(self) -> dict[str, Any]:
        run_dir = _latest_run_dir(self.state_root)
        events: list[dict[str, Any]] = []
        malformed = 0
        if run_dir is not None:
            events, malformed = _read_recent_events(run_dir / "events.jsonl", self.event_limit)

        frame = self.frame_store.read_metadata()
        if frame is not None and self.frame_store.read_frame() is None:
            frame = None

        last_runtime = next(
            (event for event in reversed(events) if str(event.get("event_type", "")).startswith("runtime.")),
            None,
        )
        last_policy = next(
            (event for event in reversed(events) if event.get("event_type") == "policy.decision"),
            None,
        )
        error_counts: Counter[str] = Counter()
        effects: Counter[str] = Counter()
        learning = 0
        for event in events:
            code = event.get("error_code")
            if isinstance(code, str) and code:
                error_counts[code] += 1
            effect = event.get("effect") or event.get("outcome")
            if isinstance(effect, str) and effect:
                effects[effect] += 1
            if event.get("event_type") == "learning.recorded":
                learning += 1

        completed = any(event.get("event_type") == "run.completed" for event in events)
        return {
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "mode": "read-only-passive",
            "run": {
                "available": run_dir is not None,
                "run_id": run_dir.name if run_dir is not None else None,
                "completed": completed,
                "event_count_window": len(events),
            },
            "frame": {"available": frame is not None, **(frame or {})},
            "runtime": {
                "available": last_runtime is not None,
                **(_activity(last_runtime) if last_runtime is not None else {}),
            },
            "ai_state": {
                "available": last_policy is not None,
                "policy_recommendation": last_policy.get("policy_recommendation") if last_policy else None,
                "actual_policy": last_policy.get("actual_policy") if last_policy else None,
                "learning_records_window": learning,
            },
            "human_channel": self.human_store.snapshot(recent=20),
            "diagnostics": {
                "malformed_records": malformed,
                "errors": dict(sorted(error_counts.items())),
                "effects": dict(sorted(effects.items())),
            },
            "activity": [_activity(event) for event in events],
        }
