"""Durable append-only Experience evidence store (privacy-safe, bounded).

A3 production bridge persistence: episodes extracted from real Coordinator
outcomes are appended one JSON line each under a configurable state root.
The store is observational evidence only — never lifecycle authority, never
mutation authority, and never a SkillTrustToken carrier. Persisted records
that smuggle authority-shaped keys, oversized records, and torn crash-tail
lines are rejected on load as non-reusable evidence; they are never
silently converted into success or replayed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from praxiom.knowledge.experience import (
    FORBIDDEN_AUTHORITY_KEYS,
    ExperienceEpisode,
)

__all__ = ["ExperienceStore", "ExperienceLoadReport"]

_MAX_REJECTED_REASONS = 64


@dataclass(frozen=True, kw_only=True)
class ExperienceLoadReport:
    episodes: tuple[ExperienceEpisode, ...]
    rejected: int
    rejected_reasons: tuple[str, ...]


class ExperienceStore:
    """Append-only JSONL store of ExperienceEpisode evidence."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def record(self, episode: ExperienceEpisode) -> None:
        """Append one bounded, authority-free episode as a single JSON line."""
        if not isinstance(episode, ExperienceEpisode):
            raise TypeError("experience-store-episode-required")
        raw = episode.to_json()  # canonical (sorted keys) + size-bounded
        for key in FORBIDDEN_AUTHORITY_KEYS:
            if f'"{key}"' in raw:
                raise ValueError("persisted-authority-key-rejected")
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(raw + "\n")
            handle.flush()

    def load(self) -> ExperienceLoadReport:
        """Read back all reusable episodes; reject malformed/torn/authority.

        A crash-torn trailing line is tolerated as rejected evidence: the
        store stays inspectable and never invents a clean success from it.
        """
        if not self._path.exists():
            return ExperienceLoadReport(episodes=(), rejected=0,
                                        rejected_reasons=())
        episodes: list[ExperienceEpisode] = []
        rejected: list[str] = []
        with self._path.open("r", encoding="utf-8", errors="replace") as handle:
            for lineno, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                if any(f'"{key}"' in text for key in FORBIDDEN_AUTHORITY_KEYS):
                    rejected.append(
                        f"line-{lineno}:persisted-authority-key-rejected")
                    continue
                try:
                    episodes.append(ExperienceEpisode.from_json(text))
                except Exception:
                    rejected.append(f"line-{lineno}:malformed-episode")
        return ExperienceLoadReport(
            episodes=tuple(episodes),
            rejected=len(rejected),
            rejected_reasons=tuple(rejected[:_MAX_REJECTED_REASONS]),
        )
