"""Trusted Skill registry: gates + lifecycle + revocation-bound execution authority."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from uuid import uuid4

from praxiom.skill.candidate import ActiveSkill, SkillCandidate
from praxiom.skill.gates import GATE_ORDER, run_gates
from praxiom.skill.lifecycle import LifecycleState, record_success, transition

__all__ = [
    "SkillRegistry", "SkillRegistryError", "SkillTrustToken", "HumanGateApproval",
    "LifecycleSnapshot",
]


class SkillRegistryError(RuntimeError):
    pass


@dataclass(frozen=True, kw_only=True)
class SkillTrustToken:
    skill_id: str
    version: int
    token_id: str


@dataclass(frozen=True, kw_only=True)
class HumanGateApproval:
    skill_id: str
    version: int
    revision: str
    payload_digest: str
    approval_id: str
    evidence_id: str


@dataclass(frozen=True, kw_only=True)
class HumanApprovalEvidence:
    """Opaque attestation issued only by the trusted human-approval boundary."""

    skill_id: str
    version: int
    revision: str
    payload_digest: str
    evidence_id: str
    evidence_nonce: str


def _payload_digest(payload: dict[str, Any]) -> str:
    try:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SkillRegistryError("human-gate-payload-not-canonical") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class HumanApprovalAuthority:
    """Capability held by the trusted human-interaction boundary, not Skill code.

    Possession of this object is the authority to attest one exact human-reviewed
    mutation.  SkillRegistry receives only the evidence object and verifies it
    against the configured authority by object identity before minting a one-shot
    execution approval.
    """

    def __init__(self) -> None:
        self.__issued: dict[int, tuple[HumanApprovalEvidence, tuple[str, int, str, str, str]]] = {}
        self.__evidence_ids: set[str] = set()
        self.__lock = Lock()

    def approve(
        self,
        *,
        skill_id: str,
        version: int,
        revision: str,
        payload: dict[str, Any],
        evidence_id: str,
    ) -> HumanApprovalEvidence:
        if not skill_id or not isinstance(version, int) or version < 1 or not revision:
            raise SkillRegistryError("human-evidence-target-invalid")
        if not evidence_id:
            raise SkillRegistryError("human-gate-evidence-required")
        digest = _payload_digest(payload)
        evidence = HumanApprovalEvidence(
            skill_id=skill_id,
            version=version,
            revision=revision,
            payload_digest=digest,
            evidence_id=evidence_id,
            evidence_nonce=uuid4().hex,
        )
        with self.__lock:
            if evidence_id in self.__evidence_ids:
                raise SkillRegistryError("human-gate-evidence-replay")
            self.__evidence_ids.add(evidence_id)
            self.__issued[id(evidence)] = (
                evidence,
                (skill_id, version, revision, digest, evidence_id),
            )
        return evidence

    def _consume(
        self,
        evidence: HumanApprovalEvidence,
        *,
        skill_id: str,
        version: int,
        revision: str,
        payload_digest: str,
    ) -> str | None:
        with self.__lock:
            stored = self.__issued.get(id(evidence))
            if stored is None or stored[0] is not evidence:
                return None
            claims = stored[1]
            if claims[:4] != (skill_id, version, revision, payload_digest):
                return None
            self.__issued.pop(id(evidence), None)
            return claims[4]


@dataclass(frozen=True, kw_only=True)
class LifecycleSnapshot:
    skill_id: str
    version: int
    state: str
    confidence: float
    provenance: tuple[str, ...]
    success_revisions: frozenset[str]


@dataclass
class _Entry:
    candidate: SkillCandidate
    lifecycle: LifecycleState
    active: ActiveSkill | None = None
    token: SkillTrustToken | None = None
    active_policy: tuple[frozenset[str], bool] | None = None
    validation_evidence_ids: frozenset[str] = frozenset()
    success_evidence: dict[str, str] = field(default_factory=dict)


class SkillRegistry:
    """Own the mutable lifecycle trust root; callers receive snapshots only."""

    def __init__(self, *, human_approval_authority: HumanApprovalAuthority | None = None) -> None:
        self.__entries: dict[tuple[str, int], _Entry] = {}
        self.__tokens: dict[str, SkillTrustToken] = {}
        self.__human_approvals: dict[
            int,
            tuple[HumanGateApproval, tuple[str, int, str, str, str]],
        ] = {}
        self.__human_approval_lock = Lock()
        self.__human_approval_authority = human_approval_authority

    def register(self, candidate: SkillCandidate) -> LifecycleSnapshot:
        gates = run_gates(candidate)
        if not gates.passed or gates.evaluated != GATE_ORDER:
            raise SkillRegistryError("gates-not-passed")
        key = (candidate.skill_id, candidate.version)
        if key in self.__entries:
            raise SkillRegistryError("skill-version-already-registered")
        self.__entries[key] = _Entry(
            candidate=candidate,
            lifecycle=LifecycleState(skill_id=candidate.skill_id, version=candidate.version),
        )
        return self.snapshot(*key)

    def validate(
        self,
        skill_id: str,
        version: int,
        *,
        evidence_ids: tuple[str, ...],
        reason: str = "registry-gates-pass",
    ) -> LifecycleSnapshot:
        entry = self._entry(skill_id, version)
        distinct_evidence = frozenset(x for x in evidence_ids if x)
        if len(distinct_evidence) < 2:
            raise SkillRegistryError("validation-evidence-insufficient")
        if not run_gates(entry.candidate).passed:
            raise SkillRegistryError("gates-no-longer-pass")
        if not transition(
            entry.lifecycle,
            "validated",
            gate_passed=True,
            evidence_ids=evidence_ids,
            reason=reason,
        ):
            raise SkillRegistryError("validation-transition-rejected")
        entry.validation_evidence_ids = distinct_evidence
        return self.snapshot(skill_id, version)

    def record_success(
        self,
        skill_id: str,
        version: int,
        *,
        revision: str,
        evidence_id: str,
    ) -> LifecycleSnapshot:
        entry = self._entry(skill_id, version)
        if not record_success(entry.lifecycle, revision=revision, evidence_id=evidence_id):
            raise SkillRegistryError("success-evidence-rejected")
        entry.success_evidence[revision] = evidence_id
        return self.snapshot(skill_id, version)

    def activate(
        self,
        skill_id: str,
        version: int,
        *,
        confidence: float,
        evidence_id: str,
        reason: str = "registry-activation",
    ) -> ActiveSkill:
        entry = self._entry(skill_id, version)
        gates = run_gates(entry.candidate)
        if not gates.passed or gates.evaluated != GATE_ORDER:
            raise SkillRegistryError("gates-not-passed")
        if not (0.0 <= confidence <= 1.0):
            raise SkillRegistryError("confidence-out-of-range")
        if entry.active is not None:
            raise SkillRegistryError("skill-version-already-active")
        if any(
            other_id == skill_id
            and other_version > version
            and other.active is not None
            and other.lifecycle.state == "active"
            for (other_id, other_version), other in self.__entries.items()
        ):
            raise SkillRegistryError("older-version-cannot-activate")
        if len(entry.validation_evidence_ids) < 2:
            raise SkillRegistryError("validation-evidence-insufficient")
        if len(entry.success_evidence) < 2 or len(set(entry.success_evidence.values())) < 2:
            raise SkillRegistryError("distinct-success-evidence-required")
        if frozenset(entry.success_evidence) != frozenset(entry.lifecycle.success_revisions):
            raise SkillRegistryError("success-revision-evidence-mismatch")
        if not transition(entry.lifecycle, "active", evidence_id=evidence_id, reason=reason):
            raise SkillRegistryError("lifecycle-not-accepted")

        # Activating a newer version atomically retires any older active version.
        for (other_id, other_version), other in list(self.__entries.items()):
            if other_id != skill_id or other_version >= version or other.active is None:
                continue
            if other.lifecycle.state == "active":
                transition(
                    other.lifecycle,
                    "superseded",
                    new_version=version,
                    evidence_id=evidence_id,
                    reason=f"registry-superseded-by-v{version}",
                )
            self._invalidate(other)

        candidate = entry.candidate
        skill = ActiveSkill(
            skill_id=candidate.skill_id,
            version=candidate.version,
            inputs=candidate.inputs,
            outputs=candidate.outputs,
            preconditions=candidate.preconditions,
            postconditions=candidate.postconditions,
            risk=candidate.risk,
            reversibility=candidate.reversibility,
            authority=candidate.authority,
            provenance=tuple(candidate.provenance) + tuple(entry.lifecycle.provenance),
            gated_by=GATE_ORDER,
            confidence=confidence,
            human_gate=candidate.human_gate,
        )
        token = SkillTrustToken(skill_id=skill.skill_id, version=skill.version,
                                token_id=uuid4().hex)
        entry.active = skill
        entry.active_policy = (frozenset(candidate.authority), bool(candidate.human_gate))
        entry.token = token
        self.__tokens[token.token_id] = token
        return skill

    def degrade(self, skill_id: str, version: int, *, evidence_id: str, reason: str = "") -> None:
        entry = self._entry(skill_id, version)
        if not transition(entry.lifecycle, "degraded", evidence_id=evidence_id, reason=reason):
            raise SkillRegistryError("degrade-transition-rejected")
        self._invalidate(entry)

    def revoke(self, skill_id: str, version: int, *, evidence_id: str, reason: str = "") -> None:
        entry = self._entry(skill_id, version)
        if not transition(entry.lifecycle, "revoked", evidence_id=evidence_id, reason=reason):
            raise SkillRegistryError("revoke-transition-rejected")
        self._invalidate(entry)

    def supersede(
        self,
        skill_id: str,
        version: int,
        *,
        new_version: int,
        evidence_id: str,
        reason: str = "",
    ) -> None:
        entry = self._entry(skill_id, version)
        if not transition(
            entry.lifecycle,
            "superseded",
            new_version=new_version,
            evidence_id=evidence_id,
            reason=reason,
        ):
            raise SkillRegistryError("supersede-transition-rejected")
        self._invalidate(entry)

    def is_executable(self, skill: ActiveSkill) -> bool:
        entry = self.__entries.get((skill.skill_id, skill.version))
        return bool(
            entry
            and entry.lifecycle.state == "active"
            and entry.active is skill
            and entry.active_policy is not None
            and entry.token is not None
            and self.__tokens.get(entry.token.token_id) is entry.token
        )

    def execution_policy(self, skill: ActiveSkill) -> tuple[frozenset[str], bool]:
        """Return registry-owned execution authority, never caller-mutated fields."""
        if not self.is_executable(skill):
            raise SkillRegistryError("skill-not-executable")
        entry = self._entry(skill.skill_id, skill.version)
        assert entry.active_policy is not None
        return entry.active_policy

    def trust_token(self, skill: ActiveSkill) -> SkillTrustToken:
        if not self.is_executable(skill):
            raise SkillRegistryError("skill-not-executable")
        entry = self._entry(skill.skill_id, skill.version)
        assert entry.token is not None
        return entry.token

    def is_token_active(self, token: SkillTrustToken) -> bool:
        stored = self.__tokens.get(token.token_id)
        if stored is not token:
            return False
        entry = self.__entries.get((token.skill_id, token.version))
        return bool(entry and entry.token is token and entry.lifecycle.state == "active")

    def issue_human_gate_approval(
        self,
        skill: ActiveSkill,
        *,
        revision: str,
        payload: dict[str, Any],
        evidence: HumanApprovalEvidence,
    ) -> HumanGateApproval:
        """Mint one registry approval from a trusted external human attestation."""
        if not self.is_executable(skill):
            raise SkillRegistryError("skill-not-executable")
        authority_ops, human_gate = self.execution_policy(skill)
        if not human_gate:
            raise SkillRegistryError("skill-not-human-gated")
        op = payload.get("op")
        if op not in authority_ops:
            raise SkillRegistryError("human-gate-op-not-authorized")
        if not revision:
            raise SkillRegistryError("human-gate-revision-required")
        authority = self.__human_approval_authority
        if authority is None:
            raise SkillRegistryError("human-approval-authority-required")
        digest = _payload_digest(payload)
        human_evidence_id = authority._consume(
            evidence,
            skill_id=skill.skill_id,
            version=skill.version,
            revision=revision,
            payload_digest=digest,
        )
        if human_evidence_id is None:
            raise SkillRegistryError("human-gate-evidence-invalid")
        approval = HumanGateApproval(
            skill_id=skill.skill_id,
            version=skill.version,
            revision=revision,
            payload_digest=digest,
            approval_id=uuid4().hex,
            evidence_id=human_evidence_id,
        )
        with self.__human_approval_lock:
            self.__human_approvals[id(approval)] = (
                approval,
                (
                    skill.skill_id,
                    skill.version,
                    revision,
                    digest,
                    human_evidence_id,
                ),
            )
        return approval

    def consume_human_gate_approval(
        self,
        skill: ActiveSkill,
        approval: HumanGateApproval | None,
        *,
        revision: str,
        payload: dict[str, Any],
    ) -> bool:
        """Consume exactly one approval bound to Skill/revision/full payload."""
        if approval is None or not self.is_executable(skill):
            return False
        try:
            digest = _payload_digest(payload)
        except SkillRegistryError:
            return False
        with self.__human_approval_lock:
            stored = self.__human_approvals.get(id(approval))
            if stored is None or stored[0] is not approval:
                return False
            claims = stored[1]
            if claims[:4] != (skill.skill_id, skill.version, revision, digest):
                return False
            self.__human_approvals.pop(id(approval), None)
            return True

    def snapshot(self, skill_id: str, version: int) -> LifecycleSnapshot:
        st = self._entry(skill_id, version).lifecycle
        return LifecycleSnapshot(
            skill_id=st.skill_id,
            version=st.version,
            state=st.state,
            confidence=st.confidence,
            provenance=tuple(st.provenance),
            success_revisions=frozenset(st.success_revisions),
        )

    def _entry(self, skill_id: str, version: int) -> _Entry:
        try:
            return self.__entries[(skill_id, version)]
        except KeyError as exc:
            raise SkillRegistryError("skill-version-not-registered") from exc

    def _invalidate(self, entry: _Entry) -> None:
        if entry.active is not None:
            target = (entry.lifecycle.skill_id, entry.lifecycle.version)
            with self.__human_approval_lock:
                for approval_key, stored in list(self.__human_approvals.items()):
                    if stored[1][:2] == target:
                        self.__human_approvals.pop(approval_key, None)
        if entry.token is not None:
            self.__tokens.pop(entry.token.token_id, None)
        entry.active = None
        entry.active_policy = None
        entry.token = None
