"""Shared domain adapter seam: one frozen declarative contract.

Pure data plus one pure mapping function. Domain behaviors are immutable
declarative records; the only route toward device mutation is
``behavior_to_candidate`` -> all ordered Skill gates -> registry-owned
activation -> SkillExecutor -> ExecutionCoordinator ->
``Runtime.execute(actions, expected_revision=...)``. No bypass lane exists.

This module performs zero device calls and zero I/O, and imports nothing
outside ``dataclasses`` and ``praxiom.skill.candidate`` (the frozen seam
allowlist; see the dated shared-seam freeze in ``docs/evidence/``). The
mapping result is untrusted until the Skill gates and
``SkillRegistry.activate`` re-run them.
"""
import dataclasses

from praxiom.skill.candidate import RUNTIME_OPS, SkillCandidate

__all__ = ["DomainBehavior", "behavior_to_candidate"]

_RISKS = ("low", "medium", "high")
_REVERSIBILITIES = ("reversible", "compensable", "irreversible")
_SUMMARY_MAX_LENGTH = 280
_REVISION_BINDING_TOKEN = "revision-bound"


def _fail(reason: str) -> None:
    """Fail closed with a machine-oriented, bounded reason."""
    raise ValueError(reason)


def _is_kebab(value: str) -> bool:
    """True for non-empty lowercase ASCII kebab tokens (``kebab-behavior``)."""
    parts = value.split("-")
    return bool(parts) and all(
        part and part.isascii() and part.isalnum() for part in parts
    )


def _valid_strings(values: object, reason: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        _fail(reason)
    if any(not isinstance(item, str) or not item for item in values):
        _fail(reason)
    return values


@dataclasses.dataclass(frozen=True)
class DomainBehavior:
    """Declarative per-domain behavior contract (no code, no device access).

    ``behavior_id`` is ``"<domain>:<kebab-behavior>"`` and unique per domain;
    ``preconditions`` must carry the ``revision-bound`` token; ``ops`` is a
    non-empty subset of the frozen runtime operation set (never redefined
    here); ``human_gate`` must be true whenever the classification is
    high-risk or irreversible.
    """

    behavior_id: str
    domain: str
    summary: str  # machine-oriented, bounded, non-empty
    source_evidence: tuple[str, ...]  # >=1 accepted evidence/design refs
    inputs: tuple[str, ...]
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    risk: str
    reversibility: str
    ops: frozenset[str]
    human_gate: bool


def behavior_to_candidate(behavior: DomainBehavior, *, version: int = 1) -> SkillCandidate:
    """Pure mapping to a SkillCandidate; fail-closed on contract violations.

    The result is untrusted until it passes all ordered Skill gates and
    ``SkillRegistry.activate`` re-runs them. ``outputs`` carry the behavior's
    observation-verifiable postconditions; execution authority is exactly the
    behavior's frozen ``ops`` subset — an unsupported operation is rejected
    here and can never widen the runtime surface.
    """
    if not isinstance(behavior, DomainBehavior):
        _fail("behavior-type-required")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        _fail("version-must-be-positive-int")
    if not isinstance(behavior.domain, str) or not _is_kebab(behavior.domain):
        _fail("domain-format")
    if not isinstance(behavior.behavior_id, str):
        _fail("behavior-id-format")
    domain_part, separator, kebab = behavior.behavior_id.partition(":")
    if (
        not separator
        or not kebab
        or ":" in kebab
        or domain_part != behavior.domain
        or not _is_kebab(kebab)
    ):
        _fail("behavior-id-format")
    if (
        not isinstance(behavior.summary, str)
        or not behavior.summary.strip()
        or len(behavior.summary) > _SUMMARY_MAX_LENGTH
    ):
        _fail("summary-blank-or-over-limit")
    _valid_strings(behavior.source_evidence, "source-evidence-required")
    _valid_strings(behavior.inputs, "inputs-required")
    preconditions = _valid_strings(behavior.preconditions, "preconditions-required")
    _valid_strings(behavior.postconditions, "postconditions-required")
    if not any(
        _REVISION_BINDING_TOKEN in precondition.lower()
        for precondition in preconditions
    ):
        _fail("precondition-revision-binding-required")
    if behavior.risk not in _RISKS:
        _fail("unknown-risk")
    if behavior.reversibility not in _REVERSIBILITIES:
        _fail("unknown-reversibility")
    if not isinstance(behavior.ops, frozenset) or not behavior.ops:
        _fail("ops-required")
    if not all(isinstance(op, str) for op in behavior.ops):
        _fail("ops-required")
    if not set(behavior.ops) <= set(RUNTIME_OPS):
        _fail("ops-exceed-runtime-ops")
    if behavior.human_gate not in (True, False):
        _fail("human-gate-must-be-bool")
    if (behavior.risk == "high" or behavior.reversibility == "irreversible") \
            and behavior.human_gate is not True:
        _fail("human-gate-required")
    return SkillCandidate(
        skill_id=behavior.behavior_id,
        version=version,
        inputs=behavior.inputs,
        outputs=behavior.postconditions,
        preconditions=behavior.preconditions,
        postconditions=behavior.postconditions,
        risk=behavior.risk,
        reversibility=behavior.reversibility,
        authority=frozenset(behavior.ops),
        provenance=behavior.source_evidence,
        human_gate=behavior.human_gate,
    )
