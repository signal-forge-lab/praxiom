"""R7-02 Typed graph expansion (bounded, cycle-safe, lifecycle-filtered)."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from praxiom.retrieval.store import ACTION_VISIBLE, KnowledgeStore

__all__ = ["TypedEdge", "KnowledgeGraph"]


@dataclass(frozen=True, kw_only=True)
class TypedEdge:
    src: str
    dst: str
    edge_type: str  # data-provided type value; core freezes no taxonomy


class KnowledgeGraph:
    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store
        self._edges: dict[str, list[TypedEdge]] = {}

    def add_edge(self, edge: TypedEdge) -> None:
        self._edges.setdefault(edge.src, []).append(edge)

    def expand(self, start: str, *, depth: int = 2, budget: int = 50,
               mode: str = "action") -> list[str]:
        """BFS with visited set (cycle-safe), deterministic neighbor order."""
        if mode != "audit":
            start_item = self._store.get(start)
            if start_item is None or start_item.state not in ACTION_VISIBLE:
                # A superseded/candidate/disproved node must not regain action
                # authority merely by serving as the graph root.
                return []
        seen = {start}
        order: list[str] = []
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        while queue and len(order) < budget:
            node, d = queue.popleft()
            if d >= depth:
                continue
            for e in sorted(self._edges.get(node, []), key=lambda x: x.dst):
                if e.dst in seen:
                    continue
                seen.add(e.dst)
                item = self._store.get(e.dst)
                if item is None:
                    continue
                if mode != "audit" and item.state not in ACTION_VISIBLE:
                    continue
                order.append(e.dst)
                queue.append((e.dst, d + 1))
                if len(order) >= budget:
                    break
        return order
