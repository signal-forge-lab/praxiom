"""R7-05 Generic rollback / state-revision reconciliation.

Stale revision invalidates continuation; EFFECT_UNKNOWN / partial outcomes
require re-observe/retrieve/replan/escalate. Rollback only with a known
allowed reversible compensation; never blind replay. Cancellation and
deadline respected throughout. Device contact only via observe() and
execute(expected_revision) on the injected Runtime port.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ReconcileDecision", "reconcile"]


@dataclass(frozen=True, kw_only=True)
class ReconcileDecision:
    action: str  # reobserve | rollback | replan | escalate
    reason: str
    replay: bool = False  # always False: no blind replay


def reconcile(*, effect: str, revision_valid: bool, has_compensation: bool,
              cancelled: bool = False, expired: bool = False,
              compensation_allowed_reversible: bool = False) -> ReconcileDecision:
    if cancelled:
        return ReconcileDecision(action="escalate", reason="cancelled-during-reconcile")
    if expired:
        return ReconcileDecision(action="escalate", reason="deadline-during-reconcile")
    # NONE is the only definitive no-error effect in the Runtime contract.
    # Any unrecognized effect is ambiguous and must fail closed like UNKNOWN.
    if not revision_valid:
        return ReconcileDecision(action="reobserve",
                                 reason="stale-revision-requires-fresh-observe")
    if effect != "NONE":
        if has_compensation and compensation_allowed_reversible:
            return ReconcileDecision(action="rollback",
                                     reason="known-reversible-compensation")
        return ReconcileDecision(action="reobserve",
                                 reason="stale-or-unknown-requires-fresh-observe")
    return ReconcileDecision(action="replan", reason="definitive-replan")
