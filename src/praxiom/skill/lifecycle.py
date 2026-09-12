"""R8-F Skill lifecycle + confidence/provenance (auditable, rollback-explicit)."""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["LifecycleState", "record_success", "transition", "STATES", "TERMINAL"]

STATES = ("candidate", "validated", "active", "degraded", "superseded", "revoked")
TERMINAL = frozenset({"superseded", "revoked"})


@dataclass(kw_only=True)
class LifecycleState:
    skill_id: str
    version: int
    state: str = "candidate"
    confidence: float = 0.0
    provenance: list[str] = field(default_factory=list)
    successes: int = 0
    failures: int = 0
    success_revisions: set[str] = field(default_factory=set)


def _append(st: LifecycleState, frm: str, to: str, reason: str, evidence: str) -> None:
    st.provenance.append(f"{frm}->{to}:{reason}:{evidence}")


def record_success(st: LifecycleState, *, revision: str, evidence_id: str) -> bool:
    """Record one validated sandbox success, de-duplicated by revision."""
    if st.state not in ("validated", "active") or not revision or not evidence_id:
        return False
    st.success_revisions.add(revision)
    st.successes = len(st.success_revisions)
    st.provenance.append(f"success:{revision}:{evidence_id}")
    return True


def transition(
    st: LifecycleState,
    to: str,
    *,
    reason: str = "",
    evidence_id: str = "",
    evidence_ids: tuple[str, ...] = (),
    gate_passed: bool = False,
    new_version: int | None = None,
) -> bool:
    """Apply one lifecycle transition. Returns True when applied.

    Fail-closed: illegal edges, confidence-driven bypass, single-success
    promotion, and revoked reactivation are rejected.
    """
    frm = st.state
    if to not in STATES or frm in TERMINAL:
        return False
    if to == "validated":
        evidence = {x for x in (*evidence_ids, evidence_id) if x}
        if frm != "candidate" or not gate_passed or len(evidence) < 2:
            return False
        # confidence never substitutes for gates/evidence
        st.state = "validated"
        _append(st, frm, to, reason or "gates-pass", ",".join(sorted(evidence)))
        return True
    if to == "active":
        if frm != "validated":
            return False
        if len(st.success_revisions) < 2:  # must be distinct revisions
            return False
        if not evidence_id:
            return False
        st.state = "active"
        _append(st, frm, to, reason or "two-episodes-distinct-revisions", evidence_id)
        return True
    if to == "degraded":
        if frm != "active":
            return False
        st.state = "degraded"
        _append(st, frm, to, reason or "contradiction-or-failure", evidence_id or "signal")
        return True
    if to == "superseded":
        if frm not in ("active", "degraded"):
            return False
        if new_version is None or new_version <= st.version:
            return False
        st.state = "superseded"
        _append(st, frm, to, reason or f"superseded-by-v{new_version}", evidence_id or "supersede")
        return True
    if to == "revoked":
        if frm not in ("active", "degraded", "validated", "candidate"):
            return False
        st.state = "revoked"
        _append(st, frm, to, reason or "safety-revocation", evidence_id or "revoke")
        return True
    return False
