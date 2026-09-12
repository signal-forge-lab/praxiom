"""Generic system-navigation behavior contracts.

This domain contains only OS-level user-visible navigation semantics.  It is
pure declarative data: no Runtime import, no device I/O, and no authority
bypass.  Execution still flows through the normal Skill lifecycle,
Coordinator, and revision-bound Runtime surface.
"""
from typing import Final

from praxiom.domain.adapter import DomainBehavior

__all__ = [
    "DOMAIN_NAME",
    "RETURN_HOME",
    "LAUNCH_APPLICATION",
    "BEHAVIORS",
    "get_behavior",
]

DOMAIN_NAME: Final[str] = "system"
_SOURCE_EVIDENCE: Final[tuple[str, ...]] = (
    "docs/evidence/PHASE_C_READINESS_PROGRESS.md",
)

RETURN_HOME: Final[DomainBehavior] = DomainBehavior(
    behavior_id="system:return-home",
    domain=DOMAIN_NAME,
    summary="return to the user-visible system Home surface",
    source_evidence=_SOURCE_EVIDENCE,
    inputs=("navigation-intent",),
    preconditions=("revision-bound: fresh observation required",),
    postconditions=("system Home surface visible in a fresh observation",),
    risk="low",
    reversibility="reversible",
    ops=frozenset({"home"}),
    human_gate=False,
)

LAUNCH_APPLICATION: Final[DomainBehavior] = DomainBehavior(
    behavior_id="system:launch-application",
    domain=DOMAIN_NAME,
    summary="launch a requested installed application and make it foreground",
    source_evidence=(
        "docs/evidence/PHASE_C_PROGRESS.md",
    ),
    inputs=("bundle-id", "expected-application-identity"),
    preconditions=(
        "revision-bound: fresh observation required",
        "application installed",
    ),
    postconditions=(
        "requested application is foreground in causal read-only validation",
    ),
    risk="low",
    reversibility="reversible",
    ops=frozenset({"launch_app"}),
    human_gate=False,
)

BEHAVIORS: Final[tuple[DomainBehavior, ...]] = (RETURN_HOME, LAUNCH_APPLICATION)
_BY_ID: Final[dict[str, DomainBehavior]] = {item.behavior_id: item for item in BEHAVIORS}


def get_behavior(behavior_id: str) -> DomainBehavior:
    if behavior_id not in _BY_ID:
        raise KeyError(f"Unknown system behavior: {behavior_id}")
    return _BY_ID[behavior_id]
