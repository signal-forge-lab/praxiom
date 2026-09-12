"""R9 transition/macro + action-path learning bound to live R8 trust tokens."""
from __future__ import annotations

from dataclasses import dataclass
from weakref import ref

from praxiom.skill.registry import SkillRegistry, SkillTrustToken

__all__ = [
    "MacroStats", "learn_macros", "macro_reusable", "PathStats", "score_path",
    "path_reusable",
]

MIN_EPISODES = 2
_MACRO_ISSUED: dict[int, tuple[ref["MacroStats"], bool, SkillTrustToken | None]] = {}
_PATH_ISSUED: dict[int, tuple[ref["PathStats"], bool, SkillTrustToken | None]] = {}


@dataclass(frozen=True, init=False)
class MacroStats:
    macro_id: str
    episodes: int
    success_rate: float
    trusted: bool
    reason: str
    trust_token: SkillTrustToken | None = None

    def __init__(self, *args, **kwargs) -> None:
        raise TypeError("MacroStats must be created by learn_macros()")


def _macro_stats(
    macro_id: str,
    episodes: int,
    success_rate: float,
    trusted: bool,
    reason: str,
    trust_token: SkillTrustToken | None,
) -> MacroStats:
    stats = object.__new__(MacroStats)
    for name, value in (
        ("macro_id", macro_id), ("episodes", episodes), ("success_rate", success_rate),
        ("trusted", trusted), ("reason", reason), ("trust_token", trust_token),
    ):
        object.__setattr__(stats, name, value)
    oid = id(stats)
    _MACRO_ISSUED[oid] = (
        ref(stats, lambda _ref, key=oid: _MACRO_ISSUED.pop(key, None)),
        trusted,
        trust_token,
    )
    return stats


def learn_macros(transitions: list[dict], *, registry: SkillRegistry) -> list[MacroStats]:
    """Produce evidence-only macro stats from live registry-bound NONE episodes.

    Each transition must provide ``macro_id``, ``effect``, ``revision`` and a
    live ``SkillTrustToken`` issued by the registry. Any unbound episode or any
    non-NONE effect poisons trust for that macro instead of being filtered out.
    """
    by_id: dict[str, list[dict]] = {}
    for transition in transitions:
        by_id.setdefault(str(transition.get("macro_id", "")), []).append(transition)
    out: list[MacroStats] = []
    for macro_id, episodes in sorted(by_id.items()):
        if not macro_id:
            continue
        tokens = [e.get("trust_token") for e in episodes]
        revisions = [str(e.get("revision", "")) for e in episodes]
        all_bound = all(
            isinstance(token, SkillTrustToken) and registry.is_token_active(token)
            for token in tokens
        )
        same_token = bool(tokens) and all(token is tokens[0] for token in tokens)
        all_revision_bound = all(revisions) and len(set(revisions)) >= MIN_EPISODES
        all_none = all(e.get("effect") == "NONE" for e in episodes)
        ok_count = sum(1 for e in episodes if e.get("effect") == "NONE")
        rate = ok_count / len(episodes) if episodes else 0.0
        trusted = (
            len(episodes) >= MIN_EPISODES
            and all_bound
            and same_token
            and all_revision_bound
            and all_none
        )
        if len(episodes) < MIN_EPISODES:
            reason = "insufficient-episodes"
        elif not all_bound or not same_token:
            reason = "registry-trust-not-live"
        elif not all_revision_bound:
            reason = "revision-evidence-insufficient"
        elif not all_none:
            reason = "non-none-effect-poisons-trust"
        else:
            reason = "trusted-registry-bound-macro"
        out.append(_macro_stats(
            macro_id,
            len(episodes),
            rate,
            trusted,
            reason,
            tokens[0] if trusted else None,
        ))
    return out


def macro_reusable(stats: MacroStats, *, registry: SkillRegistry) -> bool:
    """Consumption gate: learned statistics never outlive their R8 authority."""
    issued = _MACRO_ISSUED.get(id(stats))
    if issued is None or issued[0]() is not stats:
        return False
    trusted, token = issued[1], issued[2]
    return bool(
        isinstance(stats, MacroStats)
        and trusted
        and token is not None
        and registry.is_token_active(token)
    )


@dataclass(frozen=True, init=False)
class PathStats:
    path_id: str
    uses: int
    success_rate: float
    reusable: bool
    trust_token: SkillTrustToken | None = None

    def __init__(self, *args, **kwargs) -> None:
        raise TypeError("PathStats must be created by score_path()")


def _path_stats(
    path_id: str,
    uses: int,
    success_rate: float,
    reusable: bool,
    trust_token: SkillTrustToken | None,
) -> PathStats:
    stats = object.__new__(PathStats)
    for name, value in (
        ("path_id", path_id), ("uses", uses), ("success_rate", success_rate),
        ("reusable", reusable), ("trust_token", trust_token),
    ):
        object.__setattr__(stats, name, value)
    oid = id(stats)
    _PATH_ISSUED[oid] = (
        ref(stats, lambda _ref, key=oid: _PATH_ISSUED.pop(key, None)),
        reusable,
        trust_token,
    )
    return stats


def score_path(
    *,
    path_id: str,
    outcomes: list[str],
    revisions: list[str],
    trust_token: SkillTrustToken,
    registry: SkillRegistry,
) -> PathStats:
    bound = registry.is_token_active(trust_token)
    revisions_ok = (
        len(revisions) == len(outcomes)
        and len(set(revisions)) >= MIN_EPISODES
        and all(revisions)
    )
    all_none = bool(outcomes) and all(outcome == "NONE" for outcome in outcomes)
    reusable = (
        bound
        and len(outcomes) >= MIN_EPISODES
        and revisions_ok
        and all_none
    )
    rate = sum(1 for outcome in outcomes if outcome == "NONE") / len(outcomes) if outcomes else 0.0
    return _path_stats(
        path_id,
        len(outcomes),
        rate,
        reusable,
        trust_token if reusable else None,
    )


def path_reusable(stats: PathStats, *, registry: SkillRegistry) -> bool:
    """Consumption gate: path reuse authority expires with its R8 trust token."""
    issued = _PATH_ISSUED.get(id(stats))
    if issued is None or issued[0]() is not stats:
        return False
    reusable, token = issued[1], issued[2]
    return bool(
        isinstance(stats, PathStats)
        and reusable
        and token is not None
        and registry.is_token_active(token)
    )
