"""R9 action-dependency DAG + bounded parallel planning (fail-closed)."""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["DagNode", "DagPlan", "plan_dag"]


@dataclass(frozen=True, kw_only=True)
class DagNode:
    idx: int
    deps: frozenset[int]
    state_sensitive: bool = True
    revision: str | None = None


@dataclass(frozen=True, kw_only=True)
class DagPlan:
    waves: tuple[tuple[int, ...], ...]
    max_width: int
    reason: str
    revision: str


def plan_dag(nodes: list[DagNode], *, max_width: int = 2) -> DagPlan:
    if max_width < 1:
        raise ValueError("max_width must be >= 1")
    if len({n.idx for n in nodes}) != len(nodes):
        raise ValueError("duplicate-node-id-rejected")
    revisions = {n.revision for n in nodes}
    if nodes and (None in revisions or "" in revisions or len(revisions) != 1):
        raise ValueError("revision-binding-required")
    ids = {n.idx for n in nodes}
    for n in nodes:
        if n.idx in n.deps:
            raise ValueError("self-dependency-rejected")
        if not set(n.deps) <= ids:
            raise ValueError("unknown-dependency-rejected")
    # cycle check (Kahn)
    indeg = {n.idx: len(n.deps) for n in nodes}
    children: dict[int, list[int]] = {n.idx: [] for n in nodes}
    for n in nodes:
        for d in n.deps:
            children[d].append(n.idx)
    queue = sorted([i for i, d in indeg.items() if d == 0])
    order: list[int] = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for ch in sorted(children[cur]):
            indeg[ch] -= 1
            if indeg[ch] == 0:
                queue.append(ch)
        queue.sort()
    if len(order) != len(nodes):
        raise ValueError("cycle-rejected")
    by_id = {n.idx: n for n in nodes}
    # waves: state-sensitive nodes never share a wave with their deps
    done: set[int] = set()
    waves: list[tuple[int, ...]] = []
    remaining = list(order)
    while remaining:
        wave: list[int] = []
        for idx in list(remaining):
            n = by_id[idx]
            if not set(n.deps) <= done:
                continue
            if n.state_sensitive and wave:
                continue
            if any(by_id[w].state_sensitive for w in wave):
                continue
            if len(wave) >= max_width:
                continue
            wave.append(idx)
        if not wave:
            # serialize remainder one at a time (still valid order)
            nxt = next(i for i in remaining if set(by_id[i].deps) <= done)
            wave = [nxt]
        for idx in wave:
            remaining.remove(idx)
            done.add(idx)
        waves.append(tuple(wave))
    revision = next(iter(revisions)) if revisions else "no-actions"
    return DagPlan(waves=tuple(waves), max_width=max_width,
                   reason="bounded-parallel-safe", revision=revision)
