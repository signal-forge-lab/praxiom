"""R7-03 Optional semantic retrieval seam (disabled by default).

No vector store, no embedding dependency. Deterministic evidence outranks
semantic candidates; lifecycle filters stay authoritative; provider failure
degrades to deterministic retrieval. Consumes the Runtime seam only via
observe()/execute(expected_revision) at the coordinator layer.
"""
from __future__ import annotations

from dataclasses import dataclass

from praxiom.retrieval.store import KnowledgeStore, RetrievalHit

__all__ = ["SemanticAdapter", "rerank"]


@dataclass(kw_only=True)
class SemanticAdapter:
    enabled: bool = False
    mapping: dict[str, list[str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.mapping is None:
            self.mapping = {}

    def candidates(self, query: str) -> list[str]:
        if not self.enabled:
            return []
        if query == "__fail__":
            raise RuntimeError("semantic-provider-failed")
        return list(self.mapping.get(query, []))


def rerank(query: str, store: KnowledgeStore, adapter: SemanticAdapter,
           *, top_k: int = 5) -> list[RetrievalHit]:
    """Deterministic-first rerank; semantic resolves to canonical IDs only."""
    limit = max(0, top_k)
    if limit == 0:
        return []
    try:
        cands = adapter.candidates(query)
    except RuntimeError:
        cands = []  # safe fallback to deterministic
    deterministic = store.retrieve(query, mode="action", top_k=limit)
    det_ids = {h.kid for h in deterministic}
    # Preserve the exact/lexical ordering produced by deterministic retrieval.
    # A semantic seam may append candidates but must never reshuffle stronger
    # canonical evidence.
    out: list[RetrievalHit] = list(deterministic)
    for kid in cands:
        item = store.get(kid)
        if item is None or kid in det_ids:
            continue
        if item.state not in ("promoted", "verified"):
            continue  # lifecycle filter authoritative
        out.append(RetrievalHit(kid=kid, score=0.1, source="semantic",
                                snippet_hash="h-sem"))
    return out[:limit]
