"""R7-01 Deterministic retrieval + active-state filtering."""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["KnowledgeItem", "KnowledgeStore", "RetrievalHit"]

ACTION_VISIBLE = frozenset({"promoted", "verified"})
ALL_STATES = frozenset({"promoted", "verified", "candidate", "superseded",
                        "disproved", "rejected", "raw", "normalized",
                        "conflict_checked"})


@dataclass(kw_only=True)
class KnowledgeItem:
    kid: str
    claim: str
    state: str = "promoted"
    provenance: list[str] = field(default_factory=list)
    reliability: float = 0.5
    last_used_ts: int = 0
    last_decay_ts: int = 0


@dataclass(frozen=True, kw_only=True)
class RetrievalHit:
    kid: str
    score: float
    source: str
    snippet_hash: str  # hash only; raw claim never in traces


def _tokens(text: str) -> set[str]:
    return {t for t in text.lower().split() if t}


class KnowledgeStore:
    def __init__(self) -> None:
        self._items: dict[str, KnowledgeItem] = {}

    def put(self, item: KnowledgeItem) -> None:
        self._items[item.kid] = item

    def get(self, kid: str) -> KnowledgeItem | None:
        return self._items.get(kid)

    def retrieve(self, query: str, *, mode: str = "action",
                 top_k: int = 5) -> list[RetrievalHit]:
        """Exact canonical ID first; then lexical overlap; stable ties.

        Action mode excludes non-active lifecycle states; audit mode returns
        history. Trusted mutation consumes action mode only, via the Runtime
        seam observe()/execute(expected_revision).
        """
        hits: list[RetrievalHit] = []
        if query in self._items:
            item = self._items[query]
            if mode == "audit" or item.state in ACTION_VISIBLE:
                hits.append(RetrievalHit(kid=item.kid, score=100.0,
                                         source="exact", snippet_hash="h-exact"))
        qt = _tokens(query)
        scored: list[tuple[float, str]] = []
        for kid, item in self._items.items():
            if kid == query:
                continue
            if mode != "audit" and item.state not in ACTION_VISIBLE:
                continue
            overlap = len(qt & _tokens(item.claim))
            if overlap:
                scored.append((float(overlap) + item.reliability * 0.01, kid))
        scored.sort(key=lambda t: (-t[0], t[1]))
        for score, kid in scored[:max(0, top_k)]:
            hits.append(RetrievalHit(kid=kid, score=score, source="lexical",
                                     snippet_hash="h-lex"))
        # De-duplicate exact hit preserved first.
        seen: set[str] = set()
        out: list[RetrievalHit] = []
        for h in hits:
            if h.kid not in seen:
                seen.add(h.kid)
                out.append(h)
        return out[:max(0, top_k)]
