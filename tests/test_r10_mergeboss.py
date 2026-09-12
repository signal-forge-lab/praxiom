"""R10-B MergeBoss domain behavior migration — deterministic acceptance suite.

Covers all 6 rubric points for MergeBoss migration:
- B1: Explicit behavior/contract mapping and provenance
- B2: Deterministic fixtures and test scenarios (synthesized, no device capture)
- B3: Precondition/postcondition/revision binding fail-closed execution
- B4: Risk/reversibility/human-gate classification per behavior and negatives
- B5: Greenfield boundary, no copied legacy dependency, no hidden execution path
- B6: No blind replay after partial/unknown/stale effect
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from praxiom.domain.adapter import DomainBehavior, behavior_to_candidate
from praxiom.domain.mergeboss import (
    BEHAVIORS,
    BEHAVIORS_BY_ID,
    MIGRATION_RECORDS,
    get_behavior,
    get_all_candidates,
)
from praxiom.skill.candidate import RUNTIME_OPS, SkillCandidate
from praxiom.skill.executor import SkillExecutionError, SkillExecutor
from praxiom.skill.gates import GATE_ORDER, run_gates
from praxiom.skill.registry import HumanApprovalAuthority, SkillRegistry
from praxiom.agent.coordinator import DeviceLeaseManager, ExecutionCoordinator
from tests.fakes import FakeRuntime

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "r10" / "mergeboss"
GUARD_SCRIPT = REPO_ROOT / "scripts" / "check_agent_boundaries.py"
PROVENANCE_SCRIPT = REPO_ROOT / "scripts" / "check_provenance.py"
MERGEBOSS_MODULE = REPO_ROOT / "src" / "praxiom" / "domain" / "mergeboss.py"

DOMAIN_IMPORT_ALLOWLIST = {"dataclasses", "typing", "praxiom.skill.candidate"}


def _run_script(script_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _activate_skill(candidate: SkillCandidate, *, registry: SkillRegistry):
    """Drive candidate through full R8 registry lifecycle to activate it."""
    gates = run_gates(candidate)
    assert gates.passed and gates.evaluated == GATE_ORDER, f"Gates failed: {gates}"
    registry.register(candidate)
    registry.validate(candidate.skill_id, candidate.version, evidence_ids=("ev-1", "ev-2"))
    registry.record_success(candidate.skill_id, candidate.version, revision="rev-1", evidence_id="s-1")
    registry.record_success(candidate.skill_id, candidate.version, revision="rev-2", evidence_id="s-2")
    return registry.activate(candidate.skill_id, candidate.version, confidence=0.95, evidence_id="act-1")


# ==============================================================================
# B1: Explicit behavior/contract mapping and provenance
# ==============================================================================

def test_r10_b1_behaviors_defined_with_valid_contract_and_provenance():
    """Every MergeBoss behavior is an immutable DomainBehavior with valid provenance."""
    assert {b.behavior_id for b in BEHAVIORS} == {
        "mergeboss:launch",
        "mergeboss:open-level-board",
        "mergeboss:spawn-generator-item",
        "mergeboss:merge-board-items",
        "mergeboss:deliver-customer-order",
    }
    seen_ids = set()

    for behavior in BEHAVIORS:
        assert isinstance(behavior, DomainBehavior)
        assert behavior.domain == "mergeboss"
        assert behavior.behavior_id.startswith("mergeboss:")
        assert behavior.behavior_id not in seen_ids
        seen_ids.add(behavior.behavior_id)

        # Summary bounded and non-empty
        assert isinstance(behavior.summary, str) and behavior.summary.strip()
        assert len(behavior.summary) <= 280

        # Source evidence citations must exist on disk
        assert isinstance(behavior.source_evidence, tuple) and len(behavior.source_evidence) >= 1
        for ref in behavior.source_evidence:
            ref_path = REPO_ROOT / ref
            assert ref_path.is_file(), f"Source evidence citation not found: {ref}"

        # Inputs and outputs/postconditions non-empty
        assert isinstance(behavior.inputs, tuple) and len(behavior.inputs) >= 1
        assert isinstance(behavior.postconditions, tuple) and len(behavior.postconditions) >= 1

        # Operations must be non-empty subset of RUNTIME_OPS
        assert isinstance(behavior.ops, frozenset) and len(behavior.ops) >= 1
        assert behavior.ops <= RUNTIME_OPS

        # Converts cleanly to SkillCandidate via frozen seam
        candidate = behavior_to_candidate(behavior)
        assert isinstance(candidate, SkillCandidate)
        assert candidate.skill_id == behavior.behavior_id
        assert candidate.authority == behavior.ops
        assert candidate.provenance == behavior.source_evidence


def test_r10_b1_behavior_lookup_and_batch_helpers():
    """BEHAVIORS_BY_ID and helpers provide deterministic lookups."""
    for b in BEHAVIORS:
        assert BEHAVIORS_BY_ID[b.behavior_id] == b
        assert get_behavior(b.behavior_id) == b

    with pytest.raises(KeyError):
        get_behavior("mergeboss:non-existent-behavior")

    candidates = get_all_candidates(version=2)
    assert len(candidates) == len(BEHAVIORS)
    assert all(c.version == 2 for c in candidates)


def test_r10_b1_migration_records_distinguish_migrated_excluded_and_deferred():
    """Migration provenance records explicitly distinguish decisions with reasons."""
    assert len(MIGRATION_RECORDS) >= 10

    decisions = {r["decision"] for r in MIGRATION_RECORDS}
    assert "migrated" in decisions
    assert "excluded-legacy-only" in decisions
    assert "deferred" in decisions

    migrated_ids = set()
    for record in MIGRATION_RECORDS:
        assert "legacy_name" in record and record["legacy_name"]
        assert "decision" in record
        assert "reason" in record and record["reason"]
        assert "source_evidence" in record and len(record["source_evidence"]) >= 1

        if record["decision"] == "migrated":
            b_id = record["behavior_id"]
            assert b_id in BEHAVIORS_BY_ID, f"Migrated behavior id {b_id} not in BEHAVIORS"
            migrated_ids.add(b_id)
        else:
            assert record["behavior_id"] is None

    # Every implemented behavior must be covered by a migration record
    for b in BEHAVIORS:
        assert b.behavior_id in migrated_ids, f"{b.behavior_id} missing in MIGRATION_RECORDS"


# ==============================================================================
# B2: Deterministic fixtures/tests
# ==============================================================================

def test_r10_b2_fixtures_exist_and_contain_synthesized_data():
    """Fixtures under tests/fixtures/r10/mergeboss/ are valid JSON and synthesized."""
    assert FIXTURES_DIR.is_dir()

    board_file = FIXTURES_DIR / "board_fixture.json"
    scenarios_file = FIXTURES_DIR / "scenarios.json"
    migration_file = FIXTURES_DIR / "migration_spec.json"

    assert board_file.is_file()
    assert scenarios_file.is_file()
    assert migration_file.is_file()

    # Load and validate board fixture
    with board_file.open(encoding="utf-8") as f:
        board_data = json.load(f)
    assert board_data["domain"] == "mergeboss"
    assert board_data["grid"]["rows"] == 9
    assert board_data["grid"]["cols"] == 7
    assert board_data["provenance"] == "synthesized-contract-fixture-no-device-capture"
    assert len(board_data["sample_slots"]) >= 4

    # Load and validate scenarios fixture
    with scenarios_file.open(encoding="utf-8") as f:
        scenarios_data = json.load(f)
    assert scenarios_data["domain"] == "mergeboss"
    assert len(scenarios_data["scenarios"]) == 5

    for scen in scenarios_data["scenarios"]:
        b_id = scen["behavior_id"]
        assert b_id in BEHAVIORS_BY_ID
        behavior = BEHAVIORS_BY_ID[b_id]
        assert scen["risk"] == behavior.risk
        assert scen["reversibility"] == behavior.reversibility
        assert scen["human_gate"] == behavior.human_gate
        assert scen["op"] in behavior.ops

    # Load and validate migration spec fixture
    with migration_file.open(encoding="utf-8") as f:
        mig_data = json.load(f)
    assert mig_data["domain"] == "mergeboss"
    assert len(mig_data["decisions"]) >= 10


def test_r10_b2_scenarios_execute_deterministically_via_fixtures():
    """Every scenario in scenarios.json executes deterministically against FakeRuntime."""
    scenarios_file = FIXTURES_DIR / "scenarios.json"
    with scenarios_file.open(encoding="utf-8") as f:
        scenarios_data = json.load(f)

    authority = HumanApprovalAuthority()
    registry = SkillRegistry(human_approval_authority=authority)
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    executor = SkillExecutor(coordinator=coordinator, registry=registry)

    active_skills = {}
    for candidate in get_all_candidates():
        active_skills[candidate.skill_id] = _activate_skill(candidate, registry=registry)

    for scen in scenarios_data["scenarios"]:
        b_id = scen["behavior_id"]
        skill = active_skills[b_id]
        assert skill is not None
        rev = rt.observe()
        op = scen["op"]

        approval = None
        if scen["human_gate"]:
            payload = {"op": op}
            evidence = authority.approve(
                skill_id=skill.skill_id,
                version=skill.version,
                revision=rev,
                payload=payload,
                evidence_id=f"ev-scen-{scen['scenario_id']}",
            )
            approval = registry.issue_human_gate_approval(
                skill, revision=rev, payload=payload, evidence=evidence,
            )

        res = executor.execute(
            skill, revision=rev, op=op, human_gate_approval=approval,
        )
        assert res.state == scen["expected_outcome"], f"Scenario {scen['scenario_id']} failed: {res}"


# ==============================================================================
# B3: Precondition/postcondition/revision binding
# ==============================================================================

def test_r10_b3_all_behaviors_have_revision_bound_precondition():
    """Every behavior mandates the revision-bound token in preconditions."""
    for behavior in BEHAVIORS:
        assert any(
            "revision-bound" in p.lower() for p in behavior.preconditions
        ), f"{behavior.behavior_id} missing 'revision-bound' token in preconditions"


def test_r10_b3_gate_level_validation_passes_for_all_candidates():
    """All candidates pass all ordered R8 skill gates."""
    for behavior in BEHAVIORS:
        candidate = behavior_to_candidate(behavior)
        gate_res = run_gates(candidate)
        assert gate_res.passed, f"Gate failed for {behavior.behavior_id}: {gate_res}"
        assert gate_res.evaluated == GATE_ORDER


def test_r10_b3_execution_requires_fresh_revision_and_rejects_stale_revision():
    """Mutation only proceeds on fresh observation; stale revision fails closed with zero device calls."""
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coordinator, registry=registry)

    behavior = get_behavior("mergeboss:spawn-generator-item")
    candidate = behavior_to_candidate(behavior)
    skill = _activate_skill(candidate, registry=registry)

    fresh_rev = rt.observe()
    initial_calls = rt.device_calls

    # First attempt with fresh revision succeeds
    result = executor.execute(skill, revision=fresh_rev, op="tap_point")
    assert result.state == "succeeded"
    assert rt.device_calls == initial_calls + 1

    # Attempting to mutate again with the SAME revision must fail closed
    stale_result = executor.execute(skill, revision=fresh_rev, op="tap_point")
    assert stale_result.state == "failed"
    assert stale_result.evidence["error_code"] == "STALE_REVISION"
    assert stale_result.retry_safe is False
    # Stale attempt makes ZERO device calls
    assert rt.device_calls == initial_calls + 1

    # Attempting with a bogus/foreign revision fails closed
    bogus_result = executor.execute(skill, revision="invalid-foreign-rev", op="tap_point")
    assert bogus_result.state == "failed"
    assert bogus_result.evidence["error_code"] == "STALE_REVISION"
    assert bogus_result.retry_safe is False
    assert rt.device_calls == initial_calls + 1

    # With a new fresh revision, execution succeeds again
    new_rev = rt.observe()
    new_result = executor.execute(skill, revision=new_rev, op="tap_point")
    assert new_result.state == "succeeded"
    assert rt.device_calls == initial_calls + 2


# ==============================================================================
# B4: Risk/reversibility/human-gate classification per behavior
# ==============================================================================

def test_r10_b4_classification_table_integrity():
    """Behaviors adhere to exact risk/reversibility/human-gate policy."""
    expected_classifications = {
        "mergeboss:launch": ("low", "reversible", False),
        "mergeboss:open-level-board": ("low", "reversible", False),
        "mergeboss:spawn-generator-item": ("medium", "compensable", False),
        "mergeboss:merge-board-items": ("medium", "compensable", False),
        "mergeboss:deliver-customer-order": ("medium", "compensable", False),
    }

    for b_id, (risk, reversibility, human_gate) in expected_classifications.items():
        b = get_behavior(b_id)
        assert b.risk == risk, f"{b_id} risk mismatch"
        assert b.reversibility == reversibility, f"{b_id} reversibility mismatch"
        assert b.human_gate == human_gate, f"{b_id} human_gate mismatch"


def test_r10_b4_unproven_purchase_and_speedup_contracts_stay_deferred():
    """Historical evidence does not authorize purchase/speedup as runnable R10 behaviors."""
    for behavior_id in (
        "mergeboss:purchase-generator-part",
        "mergeboss:speedup-generator-cooldown",
    ):
        with pytest.raises(KeyError):
            get_behavior(behavior_id)

    deferred = {
        r["legacy_name"]
        for r in MIGRATION_RECORDS
        if r["decision"] == "deferred"
    }
    assert {"buy_generator_part", "speedup_cooldown"} <= deferred


def test_r10_b4_human_gate_execution_enforcement_and_one_shot_approval():
    """Generic seam human-gate enforcement remains covered without inventing domain authority."""
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    authority = HumanApprovalAuthority()
    registry = SkillRegistry(human_approval_authority=authority)
    executor = SkillExecutor(coordinator=coordinator, registry=registry)
    behavior = DomainBehavior(
        behavior_id="mergeboss:test-human-gate",
        domain="mergeboss",
        summary="synthetic high-risk gate contract",
        source_evidence=("docs/evidence/20260909_r10-domain-provenance-repair.md",),
        inputs=("target",),
        preconditions=("revision-bound: synthetic test",),
        postconditions=("synthetic postcondition",),
        risk="high",
        reversibility="irreversible",
        ops=frozenset({"tap_point"}),
        human_gate=True,
    )
    candidate = behavior_to_candidate(behavior)
    skill = _activate_skill(candidate, registry=registry)
    rev = rt.observe()
    with pytest.raises(SkillExecutionError, match="human-gate-approval-required"):
        executor.execute(skill, revision=rev, op="tap_point")
    payload = {"op": "tap_point"}
    evidence = authority.approve(
        skill_id=skill.skill_id, version=skill.version, revision=rev,
        payload=payload, evidence_id="hg-mb-1",
    )
    approval = registry.issue_human_gate_approval(
        skill, revision=rev, payload=payload, evidence=evidence,
    )

    # 3. Execution with valid approval succeeds
    attempt = executor.execute(
        skill, revision=rev, op="tap_point", human_gate_approval=approval,
    )
    assert attempt.state == "succeeded"

    # 4. Approval cannot be replayed (one-shot per execution)
    next_rev = rt.observe()
    with pytest.raises(SkillExecutionError):
        executor.execute(
            skill, revision=next_rev, op="tap_point", human_gate_approval=approval,
        )

    # 5. Approval bound to wrong revision is rejected
    evidence_wrong = authority.approve(
        skill_id=skill.skill_id,
        version=skill.version,
        revision=next_rev,
        payload=payload,
        evidence_id="hg-mb-2",
    )
    approval_wrong = registry.issue_human_gate_approval(
        skill, revision=next_rev, payload=payload, evidence=evidence_wrong,
    )
    with pytest.raises(SkillExecutionError):
        executor.execute(
            skill, revision=next_rev + "-stale", op="tap_point", human_gate_approval=approval_wrong,
        )


# ==============================================================================
# B5: Greenfield boundary, no copied legacy dependency, no hidden execution path
# ==============================================================================

def test_r10_b5_mergeboss_module_import_allowlist():
    """mergeboss.py imports only from praxiom.domain.*, praxiom.skill.candidate, dataclasses, typing."""
    assert MERGEBOSS_MODULE.is_file()
    tree = ast.parse(MERGEBOSS_MODULE.read_text(encoding="utf-8"), filename=str(MERGEBOSS_MODULE))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in DOMAIN_IMPORT_ALLOWLIST, (
                    f"Forbidden import in mergeboss.py: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            in_package = (node.module or "").startswith("praxiom.domain.")
            assert in_package or node.module in DOMAIN_IMPORT_ALLOWLIST, (
                f"Forbidden import-from in mergeboss.py: {node.module}"
            )


def test_r10_b5_mergeboss_makes_no_runtime_operation_calls():
    """mergeboss.py is purely declarative and contains no Runtime calls."""
    tree = ast.parse(MERGEBOSS_MODULE.read_text(encoding="utf-8"), filename=str(MERGEBOSS_MODULE))
    banned_calls = {"execute", "observe", "invalidate", "recover", "status", "close"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in banned_calls:
                pytest.fail(f"mergeboss.py line {node.lineno}: direct Runtime operation call: {func.attr}")


def test_r10_b5_architecture_and_provenance_guards_pass():
    """Boundary and provenance guard scripts pass cleanly."""
    res_b = _run_script(GUARD_SCRIPT)
    assert res_b.returncode == 0, f"Boundary guard failed:\n{res_b.stdout}\n{res_b.stderr}"

    res_p = _run_script(PROVENANCE_SCRIPT)
    assert res_p.returncode == 0, f"Provenance guard failed:\n{res_p.stdout}\n{res_p.stderr}"


def test_r10_b5_no_leak_tokens_in_mergeboss_module():
    """mergeboss.py contains no leak tokens that would trip boundary guards."""
    content = MERGEBOSS_MODULE.read_text(encoding="utf-8").lower()
    for token in ("gogomatch", "merge boss", "visual flight", "domain_adapter"):
        assert token not in content, f"Domain leak token '{token}' detected in mergeboss.py"


# ==============================================================================
# B6: No blind replay after partial/unknown/stale effect
# ==============================================================================

def test_r10_b6_no_blind_replay_after_effect_unknown_or_failure():
    """After a failure or unknown effect, coordinator/executor halts and marks retry_safe=False."""
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coordinator, registry=registry)

    behavior = get_behavior("mergeboss:merge-board-items")
    candidate = behavior_to_candidate(behavior)
    skill = _activate_skill(candidate, registry=registry)

    rev = rt.observe()

    # Configure fake runtime to fail execute with connection error (UNKNOWN effect class)
    rt.script = ["unknown"]

    attempt = executor.execute(skill, revision=rev, op="drag")
    assert attempt.state == "unknown"
    assert attempt.effect == "UNKNOWN"
    assert attempt.retry_safe is False

    # Attempting to replay with the same revision fails closed (stale revision)
    replay_attempt = executor.execute(skill, revision=rev, op="drag")
    assert replay_attempt.state == "failed"
    assert replay_attempt.evidence["error_code"] == "STALE_REVISION"
    assert replay_attempt.retry_safe is False

    # Blind replay without re-observation is impossible;
    # A fresh observation and state reconciliation are mandatory.
    rt.fail_next_execute = False
    fresh_rev = rt.observe()
    recovery_attempt = executor.execute(skill, revision=fresh_rev, op="drag")
    assert recovery_attempt.state == "succeeded"

    # Test PARTIAL effect mode
    rt.script = ["fail"]
    rev_partial = rt.observe()
    attempt_partial = executor.execute(skill, revision=rev_partial, op="drag")
    assert attempt_partial.state == "failed"
    assert attempt_partial.effect == "PARTIAL"
    assert attempt_partial.retry_safe is False

    # Attempting to replay with the same revision fails closed (stale revision)
    attempt_stale_partial = executor.execute(skill, revision=rev_partial, op="drag")
    assert attempt_stale_partial.state == "failed"
    assert attempt_stale_partial.evidence["error_code"] == "STALE_REVISION"
    assert attempt_stale_partial.retry_safe is False

    # Fresh observation permits recovery
    fresh_rev_2 = rt.observe()
    recovery_partial = executor.execute(skill, revision=fresh_rev_2, op="drag")
    assert recovery_partial.state == "succeeded"


# ==============================================================================
# Domain independence: zero dependency on or taxonomy leakage to/from GoGoMatch
# ==============================================================================

def test_r10_b_disjoint_from_gogomatch():
    """mergeboss.py, fixtures, and tests are strictly disjoint from GoGoMatch."""
    text = MERGEBOSS_MODULE.read_text(encoding="utf-8")
    assert "gogomatch" not in text.lower()
    for fixture_file in FIXTURES_DIR.glob("*.json"):
        fixture_text = fixture_file.read_text(encoding="utf-8")
        assert "gogomatch" not in fixture_text.lower()
