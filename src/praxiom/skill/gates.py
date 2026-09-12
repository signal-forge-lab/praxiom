"""R8-C Skill Gates (ordered, fail-closed, untrusted-until-pass)."""
from __future__ import annotations

from dataclasses import dataclass

from praxiom.skill.candidate import BANNED_TOKENS, RUNTIME_OPS, SkillCandidate

__all__ = ["GateResult", "run_gates", "GATE_ORDER"]

GATE_ORDER = (
    "schema", "authority", "privacy", "dependency", "revision", "safety",
    "sandbox-readiness",
)

PRIVACY_TOKENS = frozenset({
    "password", "token", "secret", "credential", "label:", "screen-text",
})


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failed_gate: str | None
    reason: str
    evaluated: tuple[str, ...]


def _contains_banned(text: str) -> str | None:
    low = text.lower()
    for tok in sorted(BANNED_TOKENS):
        if tok in low:
            return tok
    return None


def run_gates(candidate: SkillCandidate) -> GateResult:
    evaluated: list[str] = []
    # schema
    evaluated.append("schema")
    if not isinstance(candidate.version, int) or candidate.version < 1:
        return GateResult(False, "schema", "version-must-be-positive-int", tuple(evaluated))
    if not candidate.inputs or not candidate.preconditions or not candidate.postconditions:
        return GateResult(False, "schema", "inputs-pre-post-required", tuple(evaluated))
    if candidate.risk not in ("low", "medium", "high"):
        return GateResult(False, "schema", "unknown-risk", tuple(evaluated))
    if candidate.reversibility not in ("reversible", "compensable", "irreversible"):
        return GateResult(False, "schema", "unknown-reversibility", tuple(evaluated))
    if candidate.lifecycle != "candidate":
        return GateResult(False, "schema", "lifecycle-must-be-candidate", tuple(evaluated))
    # authority
    evaluated.append("authority")
    if not candidate.authority or not set(candidate.authority) <= set(RUNTIME_OPS):
        return GateResult(False, "authority", "authority-exceeds-runtime-ops", tuple(evaluated))
    if candidate.risk == "high" and candidate.reversibility == "irreversible" and not candidate.human_gate:
        return GateResult(False, "authority", "high-irreversible-requires-human-gate", tuple(evaluated))
    # privacy
    evaluated.append("privacy")
    blob = " ".join([*candidate.inputs, *candidate.outputs, *candidate.preconditions,
                     *candidate.postconditions, candidate.code_ref or ""]).lower()
    for tok in sorted(PRIVACY_TOKENS):
        if tok in blob:
            return GateResult(False, "privacy", f"privacy-token:{tok}", tuple(evaluated))
    # dependency
    evaluated.append("dependency")
    hit = _contains_banned(blob)
    if hit:
        return GateResult(False, "dependency", f"banned-edge:{hit}", tuple(evaluated))
    # revision
    evaluated.append("revision")
    if not any("revision-bound" in p.lower() for p in candidate.preconditions):
        return GateResult(False, "revision", "preconditions-must-bind-revision", tuple(evaluated))
    # safety
    evaluated.append("safety")
    if any("stale-assume" in p.lower() or "assume-stale" in p.lower() for p in candidate.preconditions):
        return GateResult(False, "safety", "stale-revision-assumption-rejected", tuple(evaluated))
    # sandbox-readiness
    evaluated.append("sandbox-readiness")
    if candidate.code_ref is not None:
        hit = _contains_banned(candidate.code_ref)
        if hit:
            return GateResult(False, "sandbox-readiness", f"code-ref-banned:{hit}", tuple(evaluated))
    return GateResult(True, None, "all-gates-pass", tuple(evaluated))
