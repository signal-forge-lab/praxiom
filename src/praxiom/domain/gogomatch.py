"""GoGoMatch migrated domain behavior definitions (declarative only).

Provides accepted GoGoMatch behavior contracts mapped to R10 DomainBehavior
records. Every behavior is reimplemented as pure declarative data with explicit
source evidence, revision-bound preconditions, and fail-closed risk/human-gate
classification.

Imports are strictly restricted to the frozen seam allowlist. Zero device calls,
zero I/O, zero generic core taxonomy leakage.
"""
from typing import Final

from praxiom.domain.adapter import DomainBehavior
from praxiom.skill.candidate import RUNTIME_OPS

__all__ = [
    "DOMAIN_NAME",
    "BEHAVIORS",
    "BEHAVIORS_BY_ID",
    "MIGRATION_DECISIONS",
    "get_behavior",
    "list_behaviors",
    "get_migration_decisions",
]

DOMAIN_NAME: Final[str] = "gogomatch"

_SOURCE_EVIDENCE: Final[tuple[str, ...]] = (
    "docs/evidence/20260909_r10-domain-provenance-repair.md",
)

LAUNCH_GAME: Final[DomainBehavior] = DomainBehavior(
    behavior_id="gogomatch:launch-game",
    domain=DOMAIN_NAME,
    summary="launch GoGoMatch application to level map or home surface",
    source_evidence=_SOURCE_EVIDENCE,
    inputs=("bundle-id",),
    preconditions=("revision-bound: runtime status verified",),
    postconditions=("game application launched and active in observation",),
    risk="low",
    reversibility="reversible",
    ops=frozenset({"launch_app"}),
    human_gate=False,
)

SWAP_TILES: Final[DomainBehavior] = DomainBehavior(
    behavior_id="gogomatch:swap-tiles",
    domain=DOMAIN_NAME,
    summary="drag tile from origin to adjacent cell to execute match-3 swap",
    source_evidence=_SOURCE_EVIDENCE,
    inputs=("source-cell-point", "target-cell-point"),
    preconditions=("revision-bound: interactive match grid confirmed",),
    postconditions=("tiles swapped, match resolved, gravity applied",),
    risk="medium",
    reversibility="compensable",
    ops=frozenset({"drag", "tap_point"}),
    human_gate=False,
)

BEHAVIORS: Final[tuple[DomainBehavior, ...]] = (
    LAUNCH_GAME,
    SWAP_TILES,
)

BEHAVIORS_BY_ID: Final[dict[str, DomainBehavior]] = {
    b.behavior_id: b for b in BEHAVIORS
}

MIGRATION_DECISIONS: Final[tuple[dict[str, str], ...]] = (
    {
        "legacy_behavior": "launch_app",
        "behavior_id": "gogomatch:launch-game",
        "decision": "migrated",
        "reason": "Core entry behavior re-implemented using standard launch_app op.",
        "evidence_ref": "docs/evidence/20260909_r10-domain-provenance-repair.md",
    },
    {
        "legacy_behavior": "select_level",
        "behavior_id": "none",
        "decision": "deferred",
        "reason": "The retained GoGoMatch evidence does not establish the level-selection contract or its postcondition.",
        "evidence_ref": "docs/evidence/20260909_r10-domain-provenance-repair.md",
    },
    {
        "legacy_behavior": "start_level",
        "behavior_id": "none",
        "decision": "deferred",
        "reason": "The retained GoGoMatch evidence begins after level entry and does not establish a start-level contract.",
        "evidence_ref": "docs/evidence/20260909_r10-domain-provenance-repair.md",
    },
    {
        "legacy_behavior": "swipe_match",
        "behavior_id": "gogomatch:swap-tiles",
        "decision": "migrated",
        "reason": "Primary match-3 mechanic re-implemented with drag and tap_point ops.",
        "evidence_ref": "docs/evidence/20260909_r10-domain-provenance-repair.md",
    },
    {
        "legacy_behavior": "use_booster",
        "behavior_id": "none",
        "decision": "deferred",
        "reason": "Historical evidence explicitly records that no booster was intentionally selected; no booster execution contract is accepted.",
        "evidence_ref": "docs/evidence/20260909_r10-domain-provenance-repair.md",
    },
    {
        "legacy_behavior": "claim_rewards",
        "behavior_id": "none",
        "decision": "deferred",
        "reason": "The retained run did not clear the level and therefore cannot establish victory reward-claim semantics.",
        "evidence_ref": "docs/evidence/20260909_r10-domain-provenance-repair.md",
    },
    {
        "legacy_behavior": "buy_extra_moves",
        "behavior_id": "none",
        "decision": "deferred",
        "reason": "Historical evidence proves a paid/resource-consuming continuation offer exists but no purchase was executed, so transaction semantics remain unestablished.",
        "evidence_ref": "docs/evidence/20260909_r10-domain-provenance-repair.md",
    },
    {
        "legacy_behavior": "direct_device_service_bypass",
        "behavior_id": "none",
        "decision": "excluded-legacy-only",
        "reason": "Direct device-service manipulation violates Praxiom Runtime six-operation boundary.",
        "evidence_ref": "docs/evidence/r10-design-freeze.md#2-dependency-direction",
    },
    {
        "legacy_behavior": "auto_retry_blindly",
        "behavior_id": "none",
        "decision": "excluded-legacy-only",
        "reason": "Blind retry without observation reconciliation violates R7/R8 safety invariant.",
        "evidence_ref": "docs/evidence/r10-design-freeze.md#4-revision-semantics",
    },
    {
        "legacy_behavior": "background_daemon_injection",
        "behavior_id": "none",
        "decision": "excluded-legacy-only",
        "reason": "Out-of-band daemon manipulation prohibited by greenfield security model.",
        "evidence_ref": "docs/PROVENANCE.md",
    },
    {
        "legacy_behavior": "multi_touch_cascade_gesture",
        "behavior_id": "none",
        "decision": "deferred",
        "reason": "Multi-touch gesture execution deferred to future multi-point track.",
        "evidence_ref": "docs/design/20260907_r8plus_execution_plan.md",
    },
)


def get_behavior(behavior_id: str) -> DomainBehavior:
    """Lookup a GoGoMatch behavior by its unique behavior_id."""
    if behavior_id not in BEHAVIORS_BY_ID:
        raise KeyError(f"Unknown GoGoMatch behavior: {behavior_id}")
    return BEHAVIORS_BY_ID[behavior_id]


def list_behaviors() -> tuple[DomainBehavior, ...]:
    """Return all migrated GoGoMatch behaviors."""
    return BEHAVIORS


def get_migration_decisions() -> tuple[dict[str, str], ...]:
    """Return explicit provenance decision records for GoGoMatch behaviors."""
    return MIGRATION_DECISIONS
