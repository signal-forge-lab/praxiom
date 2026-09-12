"""Execution -> Experience -> learning evidence bridge (shadow-safe).

Frozen Phase A rules implemented here:

- successful/failed attempts generate bounded, privacy-safe evidence
  automatically (identity: skill id/version, macro/path provenance,
  execution/attempt ids, opaque revision reference, timestamps);
- PARTIAL/UNKNOWN/failed/stale/validator-failed outcomes are retained,
  never filtered into success;
- persisted evidence never contains SkillTrustToken authority; historical
  evidence may only be rebound at the start of a later run after the
  current registry has independently activated the matching skill/version
  and issued a fresh live token;
- version or provenance mismatch fails closed to non-reusable history;
- macro/path/performance summaries derived here are evidence projections,
  never mutation authority; the adaptive layer never calls the Runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from praxiom.adaptive.learning import (
    MacroStats,
    PathStats,
    learn_macros,
    macro_reusable,
    path_reusable,
    score_path,
)
from praxiom.knowledge.experience import ExperienceEpisode
from praxiom.skill.candidate import RUNTIME_OPS
from praxiom.skill.registry import SkillRegistry, SkillTrustToken

__all__ = [
    "ExtractionContext", "build_episode", "RebindResult", "rebind_history",
]

_MAX_ID_CHARS = 128
_MAX_TRANSITION_CHARS = 128
_MAX_ERROR_CODE_CHARS = 64
_MAX_PROVENANCE_CHARS = 128


@dataclass(frozen=True, kw_only=True)
class ExtractionContext:
    """Bounded identity evidence bound to one real execution outcome."""

    skill_id: str
    skill_version: int
    provenance: str
    captured_at: int = 0
    macro_id: str = ""
    path_id: str = ""


def _bounded(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    return text[:limit]


def build_episode(spec: Any, attempt: Any, ctx: ExtractionContext) -> ExperienceEpisode:
    """Project one Coordinator attempt into a bounded ExperienceEpisode.

    ``spec``/``attempt`` are the production ``ExecutionSpec``/``Attempt``
    objects (duck-typed so this module stays decoupled from the Agent
    package). Only allowlisted identity fields are persisted; the raw
    action payload is never read beyond the op name, and any unknown op
    collapses to the bounded ``unknown-op`` marker.
    """
    if not isinstance(ctx, ExtractionContext):
        raise TypeError("extraction-context-required")
    if not ctx.skill_id or not isinstance(ctx.skill_version, int) or ctx.skill_version < 1:
        raise ValueError("extraction-context-identity-invalid")
    if not ctx.provenance:
        raise ValueError("extraction-context-provenance-required")
    if spec is None or attempt is None:
        raise ValueError("extraction-inputs-required")

    try:
        payload = spec.payload
    except AttributeError:
        payload = None
    op = payload.get("op") if isinstance(payload, dict) else None
    op = op if op in RUNTIME_OPS else "unknown-op"

    effect = str(attempt.effect or "NONE")
    if effect not in ("NONE", "PARTIAL", "UNKNOWN"):
        effect = "UNKNOWN"
    state = _bounded(attempt.state, 32)
    error_code = ""
    evidence = attempt.evidence
    if isinstance(evidence, dict):
        error_code = _bounded(evidence.get("error_code", ""), _MAX_ERROR_CODE_CHARS)

    return ExperienceEpisode(
        episode_id=_bounded(attempt.attempt_id, _MAX_ID_CHARS),
        transition=_bounded(f"{spec.task_type}/{op}", _MAX_TRANSITION_CHARS),
        outcome=state,
        provenance=_bounded(ctx.provenance, _MAX_PROVENANCE_CHARS),
        execution_id=_bounded(attempt.execution_id, _MAX_ID_CHARS),
        attempt_id=_bounded(attempt.attempt_id, _MAX_ID_CHARS),
        revision=_bounded(spec.revision, _MAX_ID_CHARS),
        captured_at=int(ctx.captured_at),
        skill_id=_bounded(ctx.skill_id, _MAX_ID_CHARS),
        skill_version=int(ctx.skill_version),
        effect=effect,
        state=state,
        error_code=error_code,
        macro_id=_bounded(ctx.macro_id, _MAX_ID_CHARS),
        path_id=_bounded(ctx.path_id, _MAX_ID_CHARS),
    )


@dataclass(frozen=True, kw_only=True)
class RebindResult:
    """Cross-run history rebound to one fresh live trust token.

    ``transitions``/``path_inputs`` carry the *fresh* live token object for
    the existing certified macro/path learning functions. Failure evidence
    is retained and passed through so it poisons reuse trust instead of
    being filtered into success.
    """

    transitions: tuple[dict, ...]
    path_inputs: tuple[dict, ...]
    statuses: tuple[tuple[str, str], ...]
    macro_stats: tuple[MacroStats, ...]
    path_stats: tuple[PathStats, ...]
    macro_reuse_eligible: bool
    path_reuse_eligible: bool


def rebind_history(
    episodes,
    *,
    registry: SkillRegistry,
    skill_id: str,
    version: int,
    trust_token: SkillTrustToken,
    provenance: str,
) -> RebindResult:
    """Rebind persisted episodes to a fresh live token, failing closed.

    Requirements enforced per episode: exact skill id/version match, exact
    provenance match, non-empty revision evidence, and a token that the
    current registry independently issued and still considers active for
    the matching skill/version. Any mismatch marks that episode
    non-reusable; it is never silently dropped or upgraded to success.
    """
    if not isinstance(registry, SkillRegistry):
        raise TypeError("registry-required")
    if not skill_id or not isinstance(version, int) or version < 1:
        raise ValueError("rebind-identity-invalid")
    if not provenance:
        raise ValueError("rebind-provenance-required")

    fresh = (
        isinstance(trust_token, SkillTrustToken)
        and trust_token.skill_id == skill_id
        and trust_token.version == version
        and registry.is_token_active(trust_token)
    )

    transitions: list[dict] = []
    path_episodes: list[ExperienceEpisode] = []
    statuses: list[tuple[str, str]] = []
    for ep in episodes:
        if not isinstance(ep, ExperienceEpisode):
            statuses.append(("<untyped>", "rejected:malformed-episode"))
            continue
        if not fresh:
            statuses.append((ep.episode_id, "rejected:trust-not-live"))
            continue
        if ep.skill_id != skill_id or ep.skill_version != version:
            statuses.append((ep.episode_id, "rejected:version-mismatch"))
            continue
        if ep.provenance != provenance:
            statuses.append((ep.episode_id, "rejected:provenance-mismatch"))
            continue
        if not ep.revision:
            statuses.append((ep.episode_id, "rejected:revision-evidence-missing"))
            continue
        if ep.effect == "NONE" and ep.outcome == "succeeded":
            statuses.append((ep.episode_id, "rebound"))
        else:
            # Retained failure/partial/unknown evidence: passed through so
            # it poisons reuse trust, never filtered into success.
            statuses.append((ep.episode_id, "retained-failure"))
        if ep.macro_id:
            transitions.append({
                "macro_id": ep.macro_id,
                "effect": ep.effect,
                "revision": ep.revision,
                "trust_token": trust_token,
            })
        if ep.path_id:
            path_episodes.append(ep)

    grouped: dict[str, list[ExperienceEpisode]] = {}
    for ep in path_episodes:
        grouped.setdefault(ep.path_id, []).append(ep)
    path_inputs: list[dict] = [
        {
            "path_id": path_id,
            "outcomes": [ep.effect for ep in grouped[path_id]],
            "revisions": [ep.revision for ep in grouped[path_id]],
            "trust_token": trust_token,
            "registry": registry,
        }
        for path_id in sorted(grouped)
    ]

    macro_stats = tuple(
        learn_macros(transitions, registry=registry)) if transitions else ()
    path_stats = tuple(
        score_path(**kwargs) for kwargs in path_inputs) if path_inputs else ()
    macro_ok = any(
        macro_reusable(stats, registry=registry) for stats in macro_stats)
    path_ok = any(path_reusable(stats, registry=registry) for stats in path_stats)
    return RebindResult(
        transitions=tuple(transitions),
        path_inputs=tuple(path_inputs),
        statuses=tuple(statuses),
        macro_stats=macro_stats,
        path_stats=path_stats,
        macro_reuse_eligible=bool(macro_ok),
        path_reuse_eligible=bool(path_ok),
    )
