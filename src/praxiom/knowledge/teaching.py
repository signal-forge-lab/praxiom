"""Generic durable Human Teaching / question channel.

The channel persists human-originated learning evidence only. It never owns
device mutation authority, Skill trust, or Runtime calls. ``answered`` and
``learned`` are deliberately distinct lifecycle states.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from praxiom.knowledge.promotion import KnowledgeRecord, promote
from praxiom.telemetry.context import resolve_state_root, utc_now_iso

__all__ = [
    "HUMAN_CHANNEL_RELATIVE_PATH",
    "HumanQuestion",
    "TeachingRecord",
    "HumanTeachingStore",
    "promote_fact_teaching",
]

HUMAN_CHANNEL_RELATIVE_PATH = Path("human_channel") / "events.jsonl"
_KINDS = frozenset({"policy", "fact", "other"})
_SOURCES = frozenset({"operator", "question-answer"})
_MAX_TEXT = 8192
_MAX_CONTEXT_ITEMS = 16
_MAX_CONTEXT_VALUE = 512


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _bounded_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name}-must-be-string")
    value = " ".join(value.split())
    if not value:
        raise ValueError(f"{field_name}-required")
    if len(value) > _MAX_TEXT:
        raise ValueError(f"{field_name}-too-long")
    return value


def _bounded_context(value: dict[str, Any] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError("context-must-be-object")
    if len(value) > _MAX_CONTEXT_ITEMS:
        raise ValueError("context-too-large")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or len(key) > 64:
            raise ValueError("context-key-invalid")
        rendered = str(item)
        if len(rendered) > _MAX_CONTEXT_VALUE:
            raise ValueError("context-value-too-long")
        result[key] = rendered
    return dict(sorted(result.items()))


@dataclass(frozen=True, kw_only=True)
class HumanQuestion:
    question_id: str
    prompt: str
    created_at: str
    context: dict[str, str] = field(default_factory=dict)
    state: str = "open"  # open | answered | learned
    teaching_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class TeachingRecord:
    teaching_id: str
    text: str
    teaching_kind: str  # policy | fact | other
    source: str
    created_at: str
    context: dict[str, str] = field(default_factory=dict)
    question_id: str | None = None
    state: str = "received"  # received | reviewed | conflict | learned
    conflict_checked: bool = False
    conflict: bool = False
    learning_decision: str | None = None
    evidence_ids: tuple[str, ...] = ()


class HumanTeachingStore:
    """Append-only Human Teaching event store with deterministic projection."""

    def __init__(self, state_root: Path | str | None = None) -> None:
        root = Path(state_root) if state_root is not None else resolve_state_root()
        self.path = root / HUMAN_CHANNEL_RELATIVE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _append(self, event: dict[str, Any]) -> None:
        raw = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(raw + "\n")
                handle.flush()

    def ask(self, prompt: str, *, context: dict[str, Any] | None = None) -> HumanQuestion:
        question = HumanQuestion(
            question_id=_new_id("question"),
            prompt=_bounded_text(prompt, field_name="prompt"),
            created_at=utc_now_iso(),
            context=_bounded_context(context),
        )
        self._append({"event": "question.created", **asdict(question)})
        return question

    def submit(
        self,
        text: str,
        *,
        teaching_kind: str,
        source: str = "operator",
        context: dict[str, Any] | None = None,
        question_id: str | None = None,
    ) -> TeachingRecord:
        if teaching_kind not in _KINDS:
            raise ValueError("teaching-kind-invalid")
        if source not in _SOURCES:
            raise ValueError("teaching-source-invalid")
        if question_id is not None:
            questions, _ = self.load()
            question = questions.get(question_id)
            if question is None:
                raise KeyError("question-not-found")
            if question.state != "open":
                raise ValueError("question-not-open")
        record = TeachingRecord(
            teaching_id=_new_id("teaching"),
            text=_bounded_text(text, field_name="teaching"),
            teaching_kind=teaching_kind,
            source=source,
            created_at=utc_now_iso(),
            context=_bounded_context(context),
            question_id=question_id,
        )
        self._append({"event": "teaching.submitted", **asdict(record)})
        if question_id is not None:
            self._append(
                {
                    "event": "question.answered",
                    "question_id": question_id,
                    "teaching_id": record.teaching_id,
                    "timestamp": utc_now_iso(),
                }
            )
        return record

    def answer(
        self,
        question_id: str,
        text: str,
        *,
        teaching_kind: str,
        context: dict[str, Any] | None = None,
    ) -> TeachingRecord:
        return self.submit(
            text,
            teaching_kind=teaching_kind,
            source="question-answer",
            context=context,
            question_id=question_id,
        )

    def review(
        self,
        teaching_id: str,
        *,
        conflict: bool,
        decision: str,
        evidence_ids: tuple[str, ...] = (),
    ) -> TeachingRecord:
        _, teachings = self.load()
        current = teachings.get(teaching_id)
        if current is None:
            raise KeyError("teaching-not-found")
        if current.state == "learned":
            raise ValueError("teaching-terminal")
        if not isinstance(decision, str) or not decision.strip():
            raise ValueError("review-decision-required")
        ids = tuple(str(item) for item in evidence_ids if str(item))
        self._append(
            {
                "event": "teaching.reviewed",
                "teaching_id": teaching_id,
                "conflict": bool(conflict),
                "decision": decision.strip(),
                "evidence_ids": ids,
                "timestamp": utc_now_iso(),
            }
        )
        return self.load()[1][teaching_id]

    def mark_learned(
        self,
        teaching_id: str,
        *,
        decision: str,
        evidence_ids: tuple[str, ...] = (),
    ) -> TeachingRecord:
        _, teachings = self.load()
        current = teachings.get(teaching_id)
        if current is None:
            raise KeyError("teaching-not-found")
        if not current.conflict_checked:
            raise ValueError("teaching-conflict-check-required")
        if current.conflict:
            raise ValueError("teaching-conflict-blocks-learning")
        allowed = {
            "policy": "policy-accepted",
            "fact": "fact-promoted",
            "other": "other-accepted",
        }
        if decision != allowed[current.teaching_kind]:
            raise ValueError("teaching-learning-decision-invalid")
        ids = tuple(str(item) for item in evidence_ids if str(item))
        self._append(
            {
                "event": "teaching.learned",
                "teaching_id": teaching_id,
                "decision": decision,
                "evidence_ids": ids,
                "timestamp": utc_now_iso(),
            }
        )
        if current.question_id:
            self._append(
                {
                    "event": "question.learned",
                    "question_id": current.question_id,
                    "teaching_id": teaching_id,
                    "timestamp": utc_now_iso(),
                }
            )
        return self.load()[1][teaching_id]

    def load(self) -> tuple[dict[str, HumanQuestion], dict[str, TeachingRecord]]:
        questions: dict[str, HumanQuestion] = {}
        teachings: dict[str, TeachingRecord] = {}
        if not self.path.exists():
            return questions, teachings
        with self._lock:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = event.get("event")
            if kind == "question.created":
                questions[event["question_id"]] = HumanQuestion(
                    question_id=event["question_id"],
                    prompt=event["prompt"],
                    created_at=event["created_at"],
                    context=dict(event.get("context") or {}),
                )
            elif kind == "teaching.submitted":
                teachings[event["teaching_id"]] = TeachingRecord(
                    teaching_id=event["teaching_id"],
                    text=event["text"],
                    teaching_kind=event["teaching_kind"],
                    source=event["source"],
                    created_at=event["created_at"],
                    context=dict(event.get("context") or {}),
                    question_id=event.get("question_id"),
                )
            elif kind == "question.answered" and event.get("question_id") in questions:
                old = questions[event["question_id"]]
                questions[old.question_id] = HumanQuestion(
                    **{**asdict(old), "state": "answered", "teaching_id": event.get("teaching_id")}
                )
            elif kind == "teaching.reviewed" and event.get("teaching_id") in teachings:
                old = teachings[event["teaching_id"]]
                teachings[old.teaching_id] = TeachingRecord(
                    **{
                        **asdict(old),
                        "state": "conflict" if event.get("conflict") else "reviewed",
                        "conflict_checked": True,
                        "conflict": bool(event.get("conflict")),
                        "learning_decision": event.get("decision"),
                        "evidence_ids": tuple(event.get("evidence_ids") or ()),
                    }
                )
            elif kind == "teaching.learned" and event.get("teaching_id") in teachings:
                old = teachings[event["teaching_id"]]
                teachings[old.teaching_id] = TeachingRecord(
                    **{
                        **asdict(old),
                        "state": "learned",
                        "learning_decision": event.get("decision"),
                        "evidence_ids": tuple(event.get("evidence_ids") or old.evidence_ids),
                    }
                )
            elif kind == "question.learned" and event.get("question_id") in questions:
                old = questions[event["question_id"]]
                questions[old.question_id] = HumanQuestion(
                    **{**asdict(old), "state": "learned", "teaching_id": event.get("teaching_id")}
                )
        return questions, teachings

    def snapshot(self, *, recent: int = 20) -> dict[str, Any]:
        questions, teachings = self.load()
        q_values = list(questions.values())
        t_values = list(teachings.values())
        return {
            "available": True,
            "state": "READY",
            "counts": {
                "questions": len(q_values),
                "open_questions": sum(item.state == "open" for item in q_values),
                "answered_questions": sum(item.state == "answered" for item in q_values),
                "learned_questions": sum(item.state == "learned" for item in q_values),
                "teachings": len(t_values),
                "learned_teachings": sum(item.state == "learned" for item in t_values),
                "conflicts": sum(item.state == "conflict" for item in t_values),
            },
            "questions": [asdict(item) for item in q_values[-max(1, recent):]],
            "teachings": [asdict(item) for item in t_values[-max(1, recent):]],
        }

    def learned_ids(self) -> frozenset[str]:
        return frozenset(
            key for key, value in self.load()[1].items() if value.state == "learned"
        )


def promote_fact_teaching(
    store: HumanTeachingStore,
    teaching_id: str,
    *,
    supports: int,
    contradicts: int = 0,
    has_conflict: bool = False,
    evidence_ids: tuple[str, ...] = (),
) -> KnowledgeRecord:
    """Run factual Teaching through the existing generic Knowledge lifecycle."""
    _, teachings = store.load()
    teaching = teachings.get(teaching_id)
    if teaching is None:
        raise KeyError("teaching-not-found")
    if teaching.teaching_kind != "fact":
        raise ValueError("fact-teaching-required")
    rec = KnowledgeRecord(
        kid=f"teaching:{teaching_id}",
        claim=teaching.text,
        provenance=[f"human-teaching:{teaching_id}", *evidence_ids],
        supports=int(supports),
        contradicts=int(contradicts),
        teaching_kind="fact",
    )
    for _ in range(6):
        before = rec.state
        decision = promote(rec, has_conflict=has_conflict)
        if rec.state in {"promoted", "rejected"} or decision.to_state == before:
            break
    store.review(
        teaching_id,
        conflict=has_conflict or rec.contradicts > 0,
        decision=f"knowledge:{rec.state}",
        evidence_ids=evidence_ids,
    )
    if rec.state == "promoted":
        store.mark_learned(
            teaching_id,
            decision="fact-promoted",
            evidence_ids=evidence_ids,
        )
    return rec
