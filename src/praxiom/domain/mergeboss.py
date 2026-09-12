"""MergeBoss domain behavior contracts and migration provenance.

Declarative domain behaviors for the MergeBoss puzzle mechanics.
Enters device execution exclusively via the frozen seam:
behavior_to_candidate -> ordered Skill gates -> SkillRegistry activation ->
SkillExecutor -> ExecutionCoordinator -> Runtime.execute(actions, expected_revision).

Pure data with zero device I/O. Adheres strictly to the frozen domain import
allowlist and preserves greenfield boundary isolation.
"""
from praxiom.domain.adapter import DomainBehavior, behavior_to_candidate
from praxiom.skill.candidate import RUNTIME_OPS, SkillCandidate

__all__ = [
    "BEHAVIORS",
    "BEHAVIORS_BY_ID",
    "MIGRATION_RECORDS",
    "get_behavior",
    "get_all_candidates",
]

_ACCEPTED_EVIDENCE = (
    "docs/evidence/20260909_r10-domain-provenance-repair.md",
)

BEHAVIORS: tuple[DomainBehavior, ...] = (
    DomainBehavior(
        behavior_id="mergeboss:launch",
        domain="mergeboss",
        summary="Launch the MergeBoss application and verify initial interactive surface",
        source_evidence=_ACCEPTED_EVIDENCE,
        inputs=("bundle-id",),
        preconditions=(
            "revision-bound: fresh observation required",
            "device unlocked",
            "app installed",
        ),
        postconditions=("app window active", "top-level view rendered"),
        risk="low",
        reversibility="reversible",
        ops=frozenset({"launch_app"}),
        human_gate=False,
    ),
    DomainBehavior(
        behavior_id="mergeboss:open-level-board",
        domain="mergeboss",
        summary="Open the level board surface for tile manipulation and state observation",
        source_evidence=_ACCEPTED_EVIDENCE,
        inputs=("board-target",),
        preconditions=(
            "revision-bound: fresh observation required",
            "app active",
        ),
        postconditions=(
            "board surface visible in observation",
            "grid coordinates resolved",
        ),
        risk="low",
        reversibility="reversible",
        ops=frozenset({"tap_point", "tap_element"}),
        human_gate=False,
    ),
    DomainBehavior(
        behavior_id="mergeboss:spawn-generator-item",
        domain="mergeboss",
        summary="Tap an active generator tile to produce a new item on an adjacent open board slot",
        source_evidence=_ACCEPTED_EVIDENCE,
        inputs=("generator-slot", "energy-budget"),
        preconditions=(
            "revision-bound: fresh observation required",
            "generator tile ready",
            "energy available",
            "open board slot available",
        ),
        postconditions=(
            "item spawned on open slot",
            "energy decremented",
        ),
        risk="medium",
        reversibility="compensable",
        ops=frozenset({"tap_point", "tap_element"}),
        human_gate=False,
    ),
    DomainBehavior(
        behavior_id="mergeboss:merge-board-items",
        domain="mergeboss",
        summary="Drag one board item onto an identical item on another slot to merge into higher tier item",
        source_evidence=_ACCEPTED_EVIDENCE,
        inputs=("source-slot", "target-slot", "item-type", "item-tier"),
        preconditions=(
            "revision-bound: fresh observation required",
            "matching items present on source and target slots",
        ),
        postconditions=(
            "merged higher tier item on target slot",
            "source slot cleared",
        ),
        risk="medium",
        reversibility="compensable",
        ops=frozenset({"drag"}),
        human_gate=False,
    ),
    DomainBehavior(
        behavior_id="mergeboss:deliver-customer-order",
        domain="mergeboss",
        summary="Deliver completed item to satisfy customer order and receive coins or bill rewards",
        source_evidence=_ACCEPTED_EVIDENCE,
        inputs=("order-id", "item-type", "item-tier"),
        preconditions=(
            "revision-bound: fresh observation required",
            "customer order active",
            "matching item on board",
        ),
        postconditions=(
            "order marked completed",
            "coins rewarded",
            "board item consumed",
        ),
        risk="medium",
        reversibility="compensable",
        ops=frozenset({"tap_point", "tap_element"}),
        human_gate=False,
    ),
)

BEHAVIORS_BY_ID: dict[str, DomainBehavior] = {
    behavior.behavior_id: behavior for behavior in BEHAVIORS
}


def get_behavior(behavior_id: str) -> DomainBehavior:
    """Retrieve an immutable behavior contract by its unique identifier."""
    if behavior_id not in BEHAVIORS_BY_ID:
        raise KeyError(f"Unknown behavior id: {behavior_id}")
    return BEHAVIORS_BY_ID[behavior_id]


def get_all_candidates(*, version: int = 1) -> tuple[SkillCandidate, ...]:
    """Map all MergeBoss behaviors to SkillCandidates via the frozen seam."""
    return tuple(
        behavior_to_candidate(behavior, version=version)
        for behavior in BEHAVIORS
    )


# Explicit migration provenance records distinguishing migrated vs legacy-only excluded vs deferred
MIGRATION_RECORDS: tuple[dict[str, object], ...] = (
    {
        "legacy_name": "launch",
        "behavior_id": "mergeboss:launch",
        "decision": "migrated",
        "reason": "Entrypoint for game launch and foreground setup via native runtime",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "open_board",
        "behavior_id": "mergeboss:open-level-board",
        "decision": "migrated",
        "reason": "Navigation to board screen to enable tile observation and manipulation",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "tap_generator",
        "behavior_id": "mergeboss:spawn-generator-item",
        "decision": "migrated",
        "reason": "Core item generation action consuming renewable energy",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "merge_items",
        "behavior_id": "mergeboss:merge-board-items",
        "decision": "migrated",
        "reason": "Primary merge puzzle progression mechanic upgrading tile tier",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "complete_order",
        "behavior_id": "mergeboss:deliver-customer-order",
        "decision": "migrated",
        "reason": "Order fulfillment to earn coins and queue new customer requests",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "buy_generator_part",
        "behavior_id": None,
        "decision": "deferred",
        "reason": "No retained per-behavior evidence establishes this purchase contract; purchase-like paths remain non-runnable until separately evidenced and approved",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "speedup_cooldown",
        "behavior_id": None,
        "decision": "deferred",
        "reason": "Historical evidence does not establish premium cooldown-spend semantics as an accepted contract; premium-spend behavior remains non-runnable",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "direct_memory_hack",
        "behavior_id": None,
        "decision": "excluded-legacy-only",
        "reason": "Violates greenfield native runtime boundary and execution model",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "cloud_sync_override",
        "behavior_id": None,
        "decision": "excluded-legacy-only",
        "reason": "Modifying external account/cloud state is prohibited by real-workflow safety envelope",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "auto_purchase_real_money",
        "behavior_id": None,
        "decision": "excluded-legacy-only",
        "reason": "Real-money payment/purchase is strictly prohibited by safety envelope",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "batch_board_wipe",
        "behavior_id": None,
        "decision": "excluded-legacy-only",
        "reason": "Unsafe destructive deletion of user inventory prohibited",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
    {
        "legacy_name": "cross_game_inventory_exchange",
        "behavior_id": None,
        "decision": "deferred",
        "reason": "Requires cross-domain persistent storage outside current scope",
        "source_evidence": _ACCEPTED_EVIDENCE,
    },
)
