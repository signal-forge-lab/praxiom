"""R9 telemetry (privacy-safe aggregation) + performance baseline."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping
from weakref import ref

__all__ = ["TelemetryEvent", "aggregate", "Aggregates", "PerformanceBaseline"]

ALLOWED_KINDS = frozenset({
    "execute", "observe", "validate", "retrieve", "reason", "recover", "skill",
})

_BASELINE_RECORDS: dict[
    int,
    tuple[ref["PerformanceBaseline"], Mapping[str, int], Mapping[str, int], Mapping[str, int]],
] = {}


@dataclass(frozen=True, kw_only=True)
class TelemetryEvent:
    kind: str
    latency_ms: int
    ok: bool
    ts: int
    skill_id: str | None = None
    revision_invalidated: bool = False


@dataclass(frozen=True, kw_only=True)
class Aggregates:
    count: int
    failures: int
    total_latency_ms: int
    buckets: tuple[int, ...]  # per-kind counts in latency buckets


def _bucket(lat: int) -> int:
    if lat < 50:
        return 0
    if lat < 200:
        return 1
    return 2


def _valid_event(ev: object) -> bool:
    """Validate runtime telemetry types before it can influence optimization."""
    return bool(
        isinstance(ev, TelemetryEvent)
        and ev.kind in ALLOWED_KINDS
        and type(ev.latency_ms) is int
        and ev.latency_ms >= 0
        and type(ev.ok) is bool
        and type(ev.ts) is int
        and type(ev.revision_invalidated) is bool
        and (ev.skill_id is None or (isinstance(ev.skill_id, str) and bool(ev.skill_id)))
    )


def aggregate(events: list[TelemetryEvent]) -> dict[str, Aggregates]:
    out: dict[str, Aggregates] = {}
    by_kind: dict[str, list[TelemetryEvent]] = {}
    for ev in events:
        if not _valid_event(ev):
            continue  # fail-closed: drop malformed, never invent
        assert isinstance(ev, TelemetryEvent)
        by_kind.setdefault(ev.kind, []).append(ev)
    for kind, evs in by_kind.items():
        buckets = [0, 0, 0]
        for ev in evs:
            buckets[_bucket(ev.latency_ms)] += 1
        out[kind] = Aggregates(count=len(evs),
                               failures=sum(1 for e in evs if not e.ok),
                               total_latency_ms=sum(e.latency_ms for e in evs),
                               buckets=tuple(buckets))
    return out


@dataclass(frozen=True, kw_only=True, init=False)
class PerformanceBaseline:
    per_kind_median_ms: Mapping[str, int]
    per_kind_p90_ms: Mapping[str, int]
    sample_counts: Mapping[str, int]

    def __init__(self, *args, **kwargs) -> None:
        raise TypeError("PerformanceBaseline must be created by measure()")

    @property
    def measured(self) -> bool:
        stored = _BASELINE_RECORDS.get(id(self))
        return stored is not None and stored[0]() is self

    @staticmethod
    def measure(events: list[TelemetryEvent]) -> "PerformanceBaseline":
        by_kind: dict[str, list[int]] = {}
        for ev in events:
            if not _valid_event(ev) or not ev.ok:
                continue  # baseline only from successful safe-path events
            assert isinstance(ev, TelemetryEvent)
            by_kind.setdefault(ev.kind, []).append(ev.latency_ms)
        med: dict[str, int] = {}
        p90: dict[str, int] = {}
        counts: dict[str, int] = {}
        for kind, lats in by_kind.items():
            s = sorted(lats)
            med[kind] = s[len(s) // 2]
            p90[kind] = s[min(len(s) - 1, int(len(s) * 0.9))]
            counts[kind] = len(s)
        baseline = object.__new__(PerformanceBaseline)
        object.__setattr__(baseline, "per_kind_median_ms", MappingProxyType(dict(med)))
        object.__setattr__(baseline, "per_kind_p90_ms", MappingProxyType(dict(p90)))
        object.__setattr__(baseline, "sample_counts", MappingProxyType(dict(counts)))
        oid = id(baseline)
        _BASELINE_RECORDS[oid] = (
            ref(baseline, lambda _ref, key=oid: _BASELINE_RECORDS.pop(key, None)),
            MappingProxyType(dict(med)),
            MappingProxyType(dict(p90)),
            MappingProxyType(dict(counts)),
        )
        return baseline


def _baseline_sample(baseline: PerformanceBaseline, kind: str) -> tuple[int | None, int] | None:
    stored = _BASELINE_RECORDS.get(id(baseline))
    if stored is None or stored[0]() is not baseline:
        return None
    return stored[2].get(kind), stored[3].get(kind, 0)
