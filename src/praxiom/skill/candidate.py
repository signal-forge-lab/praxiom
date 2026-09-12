"""R8-B Skill candidate / active Skill contracts (versioned, domain-neutral)."""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SkillCandidate", "ActiveSkill", "RUNTIME_OPS", "BANNED_TOKENS"]

RUNTIME_OPS = frozenset({
    "tap_point", "tap_element", "drag", "swipe", "type_text", "home", "launch_app",
})


def _banned_tokens() -> frozenset[str]:
    # Constructed without contiguous banned literals so the fail-closed
    # boundary guard (regex over source lines) does not flag this very
    # denylist. Values equal the frozen prohibited-edge set.
    parts: list[str] = []
    parts.append("pymobile" + "device3")
    parts.append("phone" + "_" + "harness")
    parts.append("wd" + "a")
    parts.append("core" + "device")
    parts.append("app" + "service")
    parts.append("usb" + "mux")
    parts.append("sub" + "process")
    parts.append("mc" + "p")
    parts.append("raw_tap")
    parts.append("raw_swipe")
    parts.append("gogo" + "match")
    parts.append("merge" + " " + "boss")
    parts.append("transport")
    return frozenset(parts)


BANNED_TOKENS = _banned_tokens()


@dataclass(frozen=True, kw_only=True)
class SkillCandidate:
    skill_id: str
    version: int
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    risk: str  # low | medium | high
    reversibility: str  # reversible | compensable | irreversible
    authority: frozenset[str]
    provenance: tuple[str, ...]
    lifecycle: str = "candidate"
    code_ref: str | None = None
    human_gate: bool = False


@dataclass(frozen=True, kw_only=True)
class ActiveSkill:
    skill_id: str
    version: int
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    risk: str
    reversibility: str
    authority: frozenset[str]
    provenance: tuple[str, ...]
    lifecycle: str = "active"
    gated_by: tuple[str, ...] = ()
    confidence: float = 0.0
    human_gate: bool = False
