"""R6-D Knowledge Promotion Pipeline (explicit lifecycle + evidence)."""
from __future__ import annotations

from dataclasses import dataclass, field

from praxiom.knowledge.hygiene import claim_key, mojibake_score, normalize_claim

__all__ = ["KnowledgeRecord", "PromotionDecision", "promote"]

STATES = ("raw", "normalized", "candidate", "conflict_checked", "verified",
          "promoted", "superseded", "disproved", "rejected")
EVIDENCE_THRESHOLD = 2


@dataclass(kw_only=True)
class KnowledgeRecord:
    kid: str
    claim: str
    state: str = "raw"
    provenance: list[str] = field(default_factory=list)
    supports: int = 0
    contradicts: int = 0
    teaching_kind: str = "none"  # policy | fact | none
    supersedes: str | None = None
    reason: str = ""


@dataclass(frozen=True, kw_only=True)
class PromotionDecision:
    kid: str
    from_state: str
    to_state: str
    reason: str


def promote(rec: KnowledgeRecord, *,
            has_conflict: bool = False,
            semantic_score: float | None = None) -> PromotionDecision:
    """Advance one lifecycle step. Conflicts block; semantic score never promotes."""
    _ = semantic_score  # explicitly ignored: no score-driven truth promotion
    src = rec.state
    if mojibake_score(rec.claim) > 0.2:
        rec.state = "rejected"
        rec.reason = "rejected:encoding-unreliable"
        return PromotionDecision(kid=rec.kid, from_state=src, to_state=rec.state,
                                 reason=rec.reason)
    if src == "raw":
        rec.claim = normalize_claim(rec.claim)
        rec.provenance = [*rec.provenance, "normalized"]
        rec.state = "normalized"
        return PromotionDecision(kid=rec.kid, from_state=src, to_state="normalized",
                                 reason="normalized")
    if src == "normalized":
        rec.state = "candidate"
        return PromotionDecision(kid=rec.kid, from_state=src, to_state="candidate",
                                 reason="candidate")
    if src == "candidate":
        if has_conflict:
            rec.reason = "blocked:conflict-requires-branch"
            return PromotionDecision(kid=rec.kid, from_state=src, to_state=src,
                                     reason=rec.reason)
        rec.state = "conflict_checked"
        return PromotionDecision(kid=rec.kid, from_state=src,
                                 to_state="conflict_checked", reason="no-conflict")
    if src == "conflict_checked":
        if rec.teaching_kind == "policy":
            rec.state = "rejected"
            rec.reason = "policy-teaching-not-fact"
            return PromotionDecision(kid=rec.kid, from_state=src, to_state="rejected",
                                     reason=rec.reason)
        if rec.contradicts > 0:
            # Contradicting evidence blocks verification: conflicts branch,
            # never silent overwrite.
            rec.reason = "blocked:contradicting-evidence-requires-branch"
            return PromotionDecision(kid=rec.kid, from_state=src, to_state=src,
                                     reason=rec.reason)
        if rec.supports >= EVIDENCE_THRESHOLD:
            rec.state = "verified"
            return PromotionDecision(kid=rec.kid, from_state=src, to_state="verified",
                                     reason=f"evidence:{rec.supports}")
        rec.reason = "insufficient-evidence"
        return PromotionDecision(kid=rec.kid, from_state=src, to_state=src,
                                 reason=rec.reason)
    if src == "verified":
        if has_conflict:
            rec.reason = "blocked:conflict-requires-branch"
            return PromotionDecision(kid=rec.kid, from_state=src, to_state=src,
                                     reason=rec.reason)
        if rec.contradicts > 0:
            rec.reason = "blocked:contradicting-evidence-requires-branch"
            return PromotionDecision(kid=rec.kid, from_state=src, to_state=src,
                                     reason=rec.reason)
        rec.state = "promoted"
        return PromotionDecision(kid=rec.kid, from_state=src, to_state="promoted",
                                 reason="promoted")
    return PromotionDecision(kid=rec.kid, from_state=src, to_state=src,
                             reason="terminal-state")


def supersede(old: KnowledgeRecord, new: KnowledgeRecord) -> None:
    """Explicit supersession keeps history/provenance on both records."""
    old.state = "superseded"
    old.supersedes = new.kid
    new.provenance = [*new.provenance, f"supersedes:{old.kid}:{claim_key(old.claim)}"]
