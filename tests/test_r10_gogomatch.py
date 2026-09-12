"""R10-C GoGoMatch migration — deterministic acceptance matrix (Points C1–C6).

Proves GoGoMatch behavior migration through the frozen domain adapter seam:
- C1: Explicit behavior/contract mapping and provenance
- C2: Deterministic fixtures and tests
- C3: Precondition/postcondition/revision binding
- C4: Risk/reversibility/human-gate classification
- C5: No copied legacy production dependency or hidden execution path
- C6: No blind replay after partial/unknown/stale effect

Operates independently from Merge Boss with disjoint file ownership.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from praxiom.domain import DomainBehavior, behavior_to_candidate
from praxiom.domain.gogomatch import (
    BEHAVIORS,
    BEHAVIORS_BY_ID,
    DOMAIN_NAME,
    MIGRATION_DECISIONS,
    get_behavior,
    get_migration_decisions,
    list_behaviors,
)
from praxiom.skill.candidate import RUNTIME_OPS
from praxiom.skill.executor import SkillExecutionError, SkillExecutor
from praxiom.skill.gates import GATE_ORDER, run_gates
from praxiom.skill.registry import HumanApprovalAuthority, SkillRegistry
from praxiom.agent.coordinator import DeviceLeaseManager, ExecutionCoordinator
from tests.fakes import FakeRuntime

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "check_agent_boundaries.py"
PROVENANCE_GUARD = REPO_ROOT / "scripts" / "check_provenance.py"
GOGOMATCH_SRC = REPO_ROOT / "src" / "praxiom" / "domain" / "gogomatch.py"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "r10" / "gogomatch"

DOMAIN_IMPORT_ALLOWLIST = {"dataclasses", "typing", "praxiom.skill.candidate"}


def _run(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _activate_behavior(behavior: DomainBehavior, registry: SkillRegistry):
    candidate = behavior_to_candidate(behavior)
    gates = run_gates(candidate)
    assert gates.passed and gates.evaluated == GATE_ORDER, gates
    registry.register(candidate)
    registry.validate(
        behavior.behavior_id, 1, evidence_ids=("val-gg-01", "val-gg-02")
    )
    registry.record_success(
        behavior.behavior_id, 1, revision="val-rev-1", evidence_id="suc-gg-01"
    )
    registry.record_success(
        behavior.behavior_id, 1, revision="val-rev-2", evidence_id="suc-gg-02"
    )
    return registry.activate(
        behavior.behavior_id, 1, confidence=0.95, evidence_id="activate-gg"
    )


# ==============================================================================
# C1: Explicit behavior/contract mapping and provenance
# ==============================================================================

def test_r10_c1_explicit_behavior_contract_mapping_and_provenance():
    assert DOMAIN_NAME == "gogomatch"
    behaviors = list_behaviors()
    assert {b.behavior_id for b in behaviors} == {
        "gogomatch:launch-game",
        "gogomatch:swap-tiles",
    }
    assert len(BEHAVIORS_BY_ID) == 2

    for behavior in behaviors:
        assert isinstance(behavior, DomainBehavior)
        assert behavior.domain == "gogomatch"
        assert behavior.behavior_id.startswith("gogomatch:")
        assert 0 < len(behavior.summary) <= 280
        assert len(behavior.source_evidence) >= 1
        assert len(behavior.inputs) >= 1
        assert len(behavior.preconditions) >= 1
        assert len(behavior.postconditions) >= 1
        assert behavior.ops <= RUNTIME_OPS
        assert behavior.risk in ("low", "medium", "high")
        assert behavior.reversibility in ("reversible", "compensable", "irreversible")

        # Map to SkillCandidate through frozen seam
        candidate = behavior_to_candidate(behavior)
        assert candidate.skill_id == behavior.behavior_id
        assert candidate.authority == behavior.ops
        assert candidate.provenance == behavior.source_evidence

        # Must pass all R8 skill gates
        gate_result = run_gates(candidate)
        assert gate_result.passed
        assert gate_result.evaluated == GATE_ORDER

    # Prove behavior lookup helper
    lookup = get_behavior("gogomatch:swap-tiles")
    assert lookup.behavior_id == "gogomatch:swap-tiles"
    with pytest.raises(KeyError, match="Unknown GoGoMatch behavior"):
        get_behavior("gogomatch:non-existent")

    # Prove migration decision table distinguishes migrated vs excluded vs deferred
    decisions = get_migration_decisions()
    assert len(decisions) >= 8
    statuses = {d["decision"] for d in decisions}
    assert "migrated" in statuses
    assert "excluded-legacy-only" in statuses
    assert "deferred" in statuses

    for d in decisions:
        assert "legacy_behavior" in d and d["legacy_behavior"]
        assert "decision" in d
        assert "reason" in d and d["reason"]
        assert "evidence_ref" in d and d["evidence_ref"]
        if d["decision"] == "migrated":
            assert d["behavior_id"] in BEHAVIORS_BY_ID
        else:
            assert d["behavior_id"] == "none" or d["behavior_id"] is None


# ==============================================================================
# C2: Deterministic fixtures and tests
# ==============================================================================

def test_r10_c2_deterministic_fixtures_derived_from_contracts():
    assert FIXTURES_DIR.is_dir()
    contracts_file = FIXTURES_DIR / "behavior_contracts.json"
    board_file = FIXTURES_DIR / "mock_board_states.json"
    evidence_file = FIXTURES_DIR / "mock_validation_evidence.json"
    closure_file = FIXTURES_DIR / "migration_closure.json"

    assert contracts_file.is_file()
    assert board_file.is_file()
    assert evidence_file.is_file()
    assert closure_file.is_file()

    # Fixture content verification: behavior contracts
    with open(contracts_file, "r", encoding="utf-8") as f:
        contracts_data = json.load(f)
    assert contracts_data["domain"] == "gogomatch"
    fixture_ids = {b["behavior_id"] for b in contracts_data["behaviors"]}
    assert fixture_ids == set(BEHAVIORS_BY_ID.keys())

    # Board states fixture: synthesized, never captured device payloads
    with open(board_file, "r", encoding="utf-8") as f:
        board_data = json.load(f)
    assert len(board_data["synthesized_states"]) >= 2
    raw_board_text = board_file.read_text(encoding="utf-8")
    for forbidden in ("udid", "serial", "wda", "device_id", "screenshot", "png"):
        assert forbidden not in raw_board_text.lower()

    # Validation evidence fixture can drive full registry activation
    with open(evidence_file, "r", encoding="utf-8") as f:
        evidence_data = json.load(f)
    registry = SkillRegistry()
    profiles = evidence_data["validation_profiles"]
    for behavior in BEHAVIORS:
        assert behavior.behavior_id in profiles
        prof = profiles[behavior.behavior_id]
        cand = behavior_to_candidate(behavior)
        registry.register(cand)
        registry.validate(
            cand.skill_id, cand.version, evidence_ids=tuple(prof["evidence_ids"])
        )
        for s in prof["success_revisions"]:
            registry.record_success(
                cand.skill_id, cand.version, revision=s["revision"], evidence_id=s["evidence_id"]
            )
        active = registry.activate(
            cand.skill_id, cand.version, confidence=prof["activation_confidence"], evidence_id="act"
        )
        assert active.skill_id == behavior.behavior_id

    # Closure decisions fixture
    with open(closure_file, "r", encoding="utf-8") as f:
        closure_data = json.load(f)
    assert closure_data["domain"] == "gogomatch"
    closure_legacy = {d["legacy_behavior"] for d in closure_data["decisions"]}
    code_legacy = {d["legacy_behavior"] for d in MIGRATION_DECISIONS}
    assert closure_legacy == code_legacy


# ==============================================================================
# C3: Precondition/postcondition/revision binding
# ==============================================================================

def test_r10_c3_precondition_postcondition_revision_binding():
    # Every GoGoMatch behavior must enforce revision binding at gate level
    for b in BEHAVIORS:
        has_revision_token = any(
            "revision-bound" in p.lower() for p in b.preconditions
        )
        assert has_revision_token, f"{b.behavior_id} lacks revision-bound precondition"

    # Execution requires fresh revision; stale revision fails closed
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coordinator, registry=registry)

    # Use launch-game behavior (low risk, ungated)
    launch_behavior = get_behavior("gogomatch:launch-game")
    active_launch = _activate_behavior(launch_behavior, registry)

    revision_0 = rt.observe()
    assert rt.device_calls == 0

    # 1. Successful execution with fresh revision
    attempt = executor.execute(active_launch, revision=revision_0, op="launch_app")
    assert attempt.state == "succeeded"
    assert rt.device_calls == 1

    # 2. Invariant: mutation invalidates the revision. Replay with same revision is STALE
    stale_attempt = executor.execute(active_launch, revision=revision_0, op="launch_app")
    assert stale_attempt.state == "failed"
    assert stale_attempt.evidence["error_code"] == "STALE_REVISION"
    assert stale_attempt.retry_safe is False
    # Device calls did not increase on stale revision rejection (fail-closed)
    assert rt.device_calls == 1

    # 3. New execution requires a fresh observation
    revision_1 = rt.observe()
    attempt_2 = executor.execute(active_launch, revision=revision_1, op="launch_app")
    assert attempt_2.state == "succeeded"
    assert rt.device_calls == 2


# ==============================================================================
# C4: Risk/reversibility/human-gate classification per behavior
# ==============================================================================

def test_r10_c4_risk_reversibility_human_gate_classification():
    # Classification table assertions
    assert get_behavior("gogomatch:launch-game").risk == "low"
    assert get_behavior("gogomatch:launch-game").reversibility == "reversible"
    assert get_behavior("gogomatch:launch-game").human_gate is False

    assert get_behavior("gogomatch:swap-tiles").risk == "medium"
    assert get_behavior("gogomatch:swap-tiles").reversibility == "compensable"
    assert get_behavior("gogomatch:swap-tiles").human_gate is False
    for behavior_id in (
        "gogomatch:open-level",
        "gogomatch:start-level",
        "gogomatch:use-hammer-booster",
        "gogomatch:claim-level-reward",
        "gogomatch:purchase-extra-moves",
    ):
        with pytest.raises(KeyError):
            get_behavior(behavior_id)
    deferred = {
        d["legacy_behavior"]
        for d in MIGRATION_DECISIONS
        if d["decision"] == "deferred"
    }
    assert {
        "select_level", "start_level", "use_booster", "claim_rewards",
        "buy_extra_moves",
    } <= deferred


# ==============================================================================
# C5: No copied legacy production dependency or hidden execution path
# ==============================================================================

def test_r10_c5_no_copied_legacy_production_dependency_or_hidden_execution_path():
    # Provenance guard must pass
    assert _run(PROVENANCE_GUARD).returncode == 0

    # Boundary guard must pass
    assert _run(GUARD).returncode == 0

    # AST check on gogomatch.py: verify strict allowlist compliance
    tree = ast.parse(GOGOMATCH_SRC.read_text(encoding="utf-8"), filename=str(GOGOMATCH_SRC))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in DOMAIN_IMPORT_ALLOWLIST, f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            in_domain = (node.module or "").startswith("praxiom.domain")
            assert in_domain or node.module in DOMAIN_IMPORT_ALLOWLIST, (
                f"Forbidden import: {node.module}"
            )
        elif isinstance(node, ast.Call):
            # No runtime operation calls directly from domain code
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            assert func_name not in {
                "execute", "observe", "invalidate", "recover", "status", "close"
            }, f"Direct runtime operation call in domain module: {func_name}"


# ==============================================================================
# C6: No blind replay after partial/unknown/stale effect
# ==============================================================================

def test_r10_c6_no_blind_replay_after_partial_unknown_or_stale_effect():
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coordinator, registry=registry)

    swap_behavior = get_behavior("gogomatch:swap-tiles")
    active_swap = _activate_behavior(swap_behavior, registry)

    # Case 1: EFFECT_UNKNOWN
    # Injected unknown effect simulates communication loss
    rt.script.append("unknown")
    rev = rt.observe()

    attempt = executor.execute(active_swap, revision=rev, op="drag")
    assert attempt.state == "unknown"
    assert attempt.retry_safe is False  # Must not auto-retry blind
    assert attempt.evidence.get("effect") == "UNKNOWN"

    # Attempting to re-execute with old revision fails closed with STALE_REVISION
    attempt_blind = executor.execute(active_swap, revision=rev, op="drag")
    assert attempt_blind.state == "failed"
    assert attempt_blind.retry_safe is False
    assert attempt_blind.evidence["error_code"] == "STALE_REVISION"

    # Case 2: PARTIAL effect
    rt.script.append("fail")
    rev_2 = rt.observe()
    attempt_partial = executor.execute(active_swap, revision=rev_2, op="drag")
    assert attempt_partial.state == "failed"
    assert attempt_partial.retry_safe is False
    assert attempt_partial.evidence.get("effect") == "PARTIAL"

    # Only fresh observation and reconciliation can continue
    rev_reconciled = rt.observe()
    attempt_reconciled = executor.execute(active_swap, revision=rev_reconciled, op="drag")
    assert attempt_reconciled.state == "succeeded"


# ==============================================================================
# Domain independence: zero dependency on Merge Boss
# ==============================================================================

def test_r10_c_disjoint_from_mergeboss():
    # gogomatch.py must not reference mergeboss in any way
    text = GOGOMATCH_SRC.read_text(encoding="utf-8")
    assert "mergeboss" not in text.lower()
    assert "merge boss" not in text.lower()
