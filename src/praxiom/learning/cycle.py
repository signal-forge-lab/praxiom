"""Generic real-device Learning Cycle v1 evidence orchestration.

The cycle owns no device authority.  Callers supply a certified single-unit
execute callback (normally RunSession -> SkillExecutor -> Coordinator ->
Runtime) plus fresh observation callbacks.  This layer records the causal
pre/action/post episode and never retries or replays a mutation.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from praxiom.telemetry.context import resolve_state_root, utc_now_iso

__all__ = [
    "LEARNING_CYCLE_RELATIVE_PATH",
    "CycleValidation",
    "LearningCycleRecord",
    "LearningCycleStore",
    "LearningCycleV1",
]

LEARNING_CYCLE_RELATIVE_PATH = Path("learning") / "cycle-v1.jsonl"
_MAX_IDS = 64


def _bounded_ids(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    out = tuple(str(item) for item in values if str(item))
    if len(out) > _MAX_IDS:
        raise ValueError("evidence-id-list-too-large")
    return out


@dataclass(frozen=True, kw_only=True)
class CycleValidation:
    accepted: bool
    method: str
    post_state_class: str
    reason: str = ""


@dataclass(frozen=True, kw_only=True)
class LearningCycleRecord:
    cycle_id: str
    timestamp_utc: str
    operation_class: str
    skill_id: str
    skill_version: int
    pre_revision: str
    post_revision: str | None
    pre_state_class: str
    post_state_class: str
    attempt_state: str
    effect: str
    validation_method: str
    validation_accepted: bool
    failure_reason: str
    negative_evidence: bool
    replayed: bool
    teaching_ids: tuple[str, ...]
    bootstrap_candidate_ids: tuple[str, ...]
    shadow_actual_decision: str | None = None
    shadow_reason: str | None = None
    shadow_confidence: float | None = None
    shadow_recommended_batch_size: int | None = None


class LearningCycleStore:
    def __init__(self, state_root: Path | str | None = None) -> None:
        root = Path(state_root) if state_root is not None else resolve_state_root()
        self.path = root / LEARNING_CYCLE_RELATIVE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def record(self, item: LearningCycleRecord) -> None:
        raw = json.dumps(asdict(item), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(raw + "\n")
                handle.flush()

    def load(self) -> tuple[LearningCycleRecord, ...]:
        if not self.path.exists():
            return ()
        records: list[LearningCycleRecord] = []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                data["teaching_ids"] = tuple(data.get("teaching_ids") or ())
                data["bootstrap_candidate_ids"] = tuple(data.get("bootstrap_candidate_ids") or ())
                records.append(LearningCycleRecord(**data))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return tuple(records)


class LearningCycleV1:
    """One-action causal learning loop over caller-owned certified execution."""

    def __init__(self, store: LearningCycleStore) -> None:
        self.store = store

    def run_single(
        self,
        *,
        operation_class: str,
        skill_id: str,
        skill_version: int,
        observe: Callable[[], Any],
        execute: Callable[[str], Any],
        classify_state: Callable[[Any], str],
        validate: Callable[[Any, Any, Any], CycleValidation],
        teaching_ids: tuple[str, ...] = (),
        bootstrap_candidate_ids: tuple[str, ...] = (),
        shadow_snapshot: Callable[[], Any | None] | None = None,
    ) -> LearningCycleRecord:
        if not operation_class or not skill_id:
            raise ValueError("operation-class-and-skill-required")
        pre = observe()
        pre_revision = str(getattr(pre, "revision", "") or "")
        if not pre_revision:
            raise RuntimeError("fresh-pre-observation-required")
        pre_state = str(classify_state(pre) or "unknown")

        # Exactly one caller-certified mutation attempt.  No retry/replay path
        # exists in this orchestration layer.
        attempt = execute(pre_revision)
        attempt_state = str(getattr(attempt, "state", "unknown") or "unknown")
        effect = str(getattr(attempt, "effect", "UNKNOWN") or "UNKNOWN")
        evidence = getattr(attempt, "evidence", None)
        replayed = bool(evidence.get("replayed", False)) if isinstance(evidence, dict) else False

        post = observe()
        post_revision = str(getattr(post, "revision", "") or "")
        if not post_revision or post_revision == pre_revision:
            validation = CycleValidation(
                accepted=False,
                method="fresh-observe",
                post_state_class="unknown",
                reason="fresh-post-revision-required",
            )
            post_revision_value: str | None = post_revision or None
        else:
            validation = validate(pre, attempt, post)
            if not isinstance(validation, CycleValidation):
                raise TypeError("cycle-validation-required")
            post_revision_value = post_revision

        failure_reason = validation.reason
        negative = (
            attempt_state != "succeeded"
            or effect != "NONE"
            or not validation.accepted
            or replayed
        )
        shadow = shadow_snapshot() if shadow_snapshot is not None else None
        batch = None
        if shadow is not None:
            batch_obj = getattr(shadow, "batch", None)
            size = getattr(batch_obj, "size", None)
            if isinstance(size, int) and not isinstance(size, bool):
                batch = size
        item = LearningCycleRecord(
            cycle_id=f"cycle-{uuid.uuid4().hex}",
            timestamp_utc=utc_now_iso(),
            operation_class=operation_class,
            skill_id=skill_id,
            skill_version=int(skill_version),
            pre_revision=pre_revision,
            post_revision=post_revision_value,
            pre_state_class=pre_state,
            post_state_class=validation.post_state_class,
            attempt_state=attempt_state,
            effect=effect,
            validation_method=validation.method,
            validation_accepted=bool(validation.accepted),
            failure_reason=failure_reason,
            negative_evidence=negative,
            replayed=replayed,
            teaching_ids=_bounded_ids(teaching_ids),
            bootstrap_candidate_ids=_bounded_ids(bootstrap_candidate_ids),
            shadow_actual_decision=(
                str(getattr(shadow, "actual_decision", "")) or None if shadow is not None else None
            ),
            shadow_reason=(
                str(getattr(shadow, "reason", "")) or None if shadow is not None else None
            ),
            shadow_confidence=(
                float(getattr(shadow, "confidence"))
                if shadow is not None and getattr(shadow, "confidence", None) is not None
                else None
            ),
            shadow_recommended_batch_size=batch,
        )
        self.store.record(item)
        return item
