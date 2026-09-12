"""R10-D compatibility, provenance, rollback, and supersession acceptance tests.

Deterministic tests for:
- D1: Explicit legacy/domain behavior mapping, distinguishing required vs legacy-only
      exclusions and deferred behaviors.
- D2: Greenfield source provenance, absence of Phone Harness / legacy copy,
      pinned upstream dependency integrity.
- D3: Instant execution-level rollback via SkillRegistry.revoke and supersession via
      SkillRegistry.supersede, with complete provenance audit tuples; physical removal safety.
- D4: Generalized boundary and provenance guard coverage over the domain adapter seam.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from praxiom.agent.coordinator import DeviceLeaseManager, ExecutionCoordinator
from praxiom.domain.adapter import DomainBehavior, behavior_to_candidate
from praxiom.domain.gogomatch import (
    BEHAVIORS as GOGOMATCH_BEHAVIORS,
    MIGRATION_DECISIONS as GOGOMATCH_MIGRATION_DECISIONS,
)
from praxiom.domain.mergeboss import (
    BEHAVIORS as MERGEBOSS_BEHAVIORS,
    MIGRATION_RECORDS as MERGEBOSS_MIGRATION_RECORDS,
)
from praxiom.skill.candidate import RUNTIME_OPS, SkillCandidate
from praxiom.skill.executor import SkillExecutionError, SkillExecutor
from praxiom.skill.gates import GATE_ORDER, run_gates
from praxiom.skill.lifecycle import transition
from praxiom.skill.registry import SkillRegistry, SkillRegistryError
from tests.fakes import FakeRuntime

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_SCRIPT = REPO_ROOT / "scripts" / "check_agent_boundaries.py"
PROVENANCE_SCRIPT = REPO_ROOT / "scripts" / "check_provenance.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
DOMAIN_DIR = REPO_ROOT / "src" / "praxiom" / "domain"

PINNED_PYMOBILEDEVICE3_COMMIT = "ec4ac06a850a6a884ca778350621f354faf347c6"


def _run_script(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def _activate_candidate(candidate: SkillCandidate, registry: SkillRegistry):
    gates = run_gates(candidate)
    assert gates.passed and gates.evaluated == GATE_ORDER
    registry.register(candidate)
    registry.validate(candidate.skill_id, candidate.version, evidence_ids=("ev-1", "ev-2"))
    registry.record_success(candidate.skill_id, candidate.version, revision="rev-1", evidence_id="ev-1")
    registry.record_success(candidate.skill_id, candidate.version, revision="rev-2", evidence_id="ev-2")
    active = registry.activate(
        candidate.skill_id,
        candidate.version,
        confidence=0.9,
        evidence_id="ev-activate",
    )
    assert active is not None
    return active


# ==============================================================================
# R10-D1: Retained legacy/domain behavior mapped; required vs legacy-only distinguished
# ==============================================================================

def test_r10_d1_mergeboss_mapping_and_legacy_exclusions():
    assert len(MERGEBOSS_BEHAVIORS) == 5
    migrated_ids = {b.behavior_id for b in MERGEBOSS_BEHAVIORS}

    # Verify all migrated behaviors satisfy frozen seam invariants
    for b in MERGEBOSS_BEHAVIORS:
        assert b.domain == "mergeboss"
        assert b.behavior_id.startswith("mergeboss:")
        assert any("revision-bound" in p for p in b.preconditions)
        assert b.ops.issubset(RUNTIME_OPS)
        assert len(b.ops) >= 1
        assert len(b.inputs) >= 1
        assert len(b.postconditions) >= 1
        assert len(b.source_evidence) >= 1
        assert b.risk in ("low", "medium", "high")
        assert b.reversibility in ("reversible", "compensable", "irreversible")
        if b.risk == "high" or b.reversibility == "irreversible":
            assert b.human_gate is True

        cand = behavior_to_candidate(b)
        assert cand.skill_id == b.behavior_id
        assert cand.authority == b.ops

    # Verify migration records explicitly distinguish migrated vs excluded-legacy-only vs deferred
    migrated_records = [r for r in MERGEBOSS_MIGRATION_RECORDS if r["decision"] == "migrated"]
    excluded_records = [r for r in MERGEBOSS_MIGRATION_RECORDS if r["decision"] == "excluded-legacy-only"]
    deferred_records = [r for r in MERGEBOSS_MIGRATION_RECORDS if r["decision"] == "deferred"]

    assert len(migrated_records) == 5
    assert len(excluded_records) == 4
    assert len(deferred_records) == 3

    # Every migrated record maps to a real behavior
    for r in migrated_records:
        assert r["behavior_id"] in migrated_ids
        assert len(str(r["reason"])) > 0

    # Every excluded record has no runnable behavior_id and documents a concrete safety/architecture rationale
    excluded_names = {r["legacy_name"] for r in excluded_records}
    assert excluded_names == {
        "direct_memory_hack",
        "cloud_sync_override",
        "auto_purchase_real_money",
        "batch_board_wipe",
    }
    for r in excluded_records:
        assert r["behavior_id"] is None
        assert len(str(r["reason"])) > 0

    # Deferred record has no runnable behavior_id and documents rationale
    deferred_names = {r["legacy_name"] for r in deferred_records}
    assert deferred_names == {
        "buy_generator_part",
        "speedup_cooldown",
        "cross_game_inventory_exchange",
    }
    assert all(r["behavior_id"] is None for r in deferred_records)


def test_r10_d1_gogomatch_mapping_and_legacy_exclusions():
    assert len(GOGOMATCH_BEHAVIORS) == 2
    migrated_ids = {b.behavior_id for b in GOGOMATCH_BEHAVIORS}

    # Verify all migrated behaviors satisfy frozen seam invariants
    for b in GOGOMATCH_BEHAVIORS:
        assert b.domain == "gogomatch"
        assert b.behavior_id.startswith("gogomatch:")
        assert any("revision-bound" in p for p in b.preconditions)
        assert b.ops.issubset(RUNTIME_OPS)
        assert len(b.ops) >= 1
        assert len(b.inputs) >= 1
        assert len(b.postconditions) >= 1
        assert len(b.source_evidence) >= 1
        assert b.risk in ("low", "medium", "high")
        assert b.reversibility in ("reversible", "compensable", "irreversible")
        if b.risk == "high" or b.reversibility == "irreversible":
            assert b.human_gate is True

        cand = behavior_to_candidate(b)
        assert cand.skill_id == b.behavior_id
        assert cand.authority == b.ops

    # Verify migration decisions explicitly distinguish migrated vs excluded-legacy-only vs deferred
    migrated_decisions = [d for d in GOGOMATCH_MIGRATION_DECISIONS if d["decision"] == "migrated"]
    excluded_decisions = [d for d in GOGOMATCH_MIGRATION_DECISIONS if d["decision"] == "excluded-legacy-only"]
    deferred_decisions = [d for d in GOGOMATCH_MIGRATION_DECISIONS if d["decision"] == "deferred"]

    assert len(migrated_decisions) == 2
    assert len(excluded_decisions) == 3
    assert len(deferred_decisions) == 6

    for d in migrated_decisions:
        assert d["behavior_id"] in migrated_ids
        assert len(d["reason"]) > 0

    excluded_names = {d["legacy_behavior"] for d in excluded_decisions}
    assert excluded_names == {
        "direct_device_service_bypass",
        "auto_retry_blindly",
        "background_daemon_injection",
    }
    for d in excluded_decisions:
        assert d["behavior_id"] in (None, "none")
        assert len(d["reason"]) > 0

    deferred_names = {d["legacy_behavior"] for d in deferred_decisions}
    assert deferred_names == {
        "select_level",
        "start_level",
        "use_booster",
        "claim_rewards",
        "buy_extra_moves",
        "multi_touch_cascade_gesture",
    }


def test_r10_d1_no_untracked_legacy_behaviors_and_fixture_alignment():
    # Verify fixtures align with Python module records
    mb_fixture_path = REPO_ROOT / "tests" / "fixtures" / "r10" / "mergeboss" / "migration_spec.json"
    assert mb_fixture_path.is_file()
    with mb_fixture_path.open("r", encoding="utf-8") as f:
        mb_fixture = json.load(f)
    assert len(mb_fixture["decisions"]) == len(MERGEBOSS_MIGRATION_RECORDS)

    gg_fixture_path = REPO_ROOT / "tests" / "fixtures" / "r10" / "gogomatch" / "migration_closure.json"
    assert gg_fixture_path.is_file()
    with gg_fixture_path.open("r", encoding="utf-8") as f:
        gg_fixture = json.load(f)
    assert len(gg_fixture["decisions"]) == len(GOGOMATCH_MIGRATION_DECISIONS)


# ==============================================================================
# R10-D2: Greenfield source provenance and dependency pin integrity
# ==============================================================================

def test_r10_d2_provenance_guard_passes_clean_on_production_tree():
    proc = _run_script(PROVENANCE_SCRIPT)
    assert proc.returncode == 0
    assert "OK: no Phone Harness import/name/dependency in production paths" in proc.stdout


def test_r10_d2_upstream_pymobiledevice3_pin_is_unmodified():
    text = PYPROJECT_PATH.read_text(encoding="utf-8")
    assert PINNED_PYMOBILEDEVICE3_COMMIT in text
    expected_dep = f"pymobiledevice3 @ git+https://github.com/doronz88/pymobiledevice3@{PINNED_PYMOBILEDEVICE3_COMMIT}"
    assert expected_dep in text


def test_r10_d2_no_prohibited_imports_in_domain_modules():
    domain_files = sorted(DOMAIN_DIR.glob("*.py"))
    assert len(domain_files) >= 4  # __init__.py, adapter.py, mergeboss.py, gogomatch.py
    allowed_modules = {
        "dataclasses",
        "typing",
        "praxiom.domain.adapter",
        "praxiom.skill.candidate",
    }
    for file_path in domain_files:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name in allowed_modules, (
                        f"{file_path}: unexpected import {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                in_domain = (node.module or "").startswith("praxiom.domain.")
                assert in_domain or node.module in allowed_modules, (
                    f"{file_path}: unexpected import from {node.module}"
                )


# ==============================================================================
# R10-D3: Migration notes, supersession/rollback information, compatibility evidence
# ==============================================================================

def test_r10_d3_execution_level_rollback_via_registry_revoke():
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coordinator, registry=registry)

    # Use first MergeBoss behavior as candidate
    behavior = MERGEBOSS_BEHAVIORS[0]
    candidate = behavior_to_candidate(behavior, version=1)
    active = _activate_candidate(candidate, registry)

    # Prove execution succeeds when active
    rev = rt.observe()
    attempt = executor.execute(active, revision=rev, op="launch_app")
    assert attempt.state == "succeeded"
    assert rt.device_calls == 1

    # Execute rollback: revoke the skill in the registry
    registry.revoke(
        candidate.skill_id,
        candidate.version,
        evidence_id="ev-rollback-drill",
        reason="defect-mitigation-test",
    )

    # Verification 1: Registry immediately marks skill non-executable
    assert registry.is_executable(active) is False

    # Verification 2: Execution through Executor fails closed immediately
    rev2 = rt.observe()
    with pytest.raises(SkillExecutionError) as exc_info:
        executor.execute(active, revision=rev2, op="launch_app")
    assert "skill-not-registry-active" in str(exc_info.value)
    # Zero additional device mutation calls occurred on rejected attempt
    assert rt.device_calls == 1

    # Verification 3: Lifecycle state is terminal 'revoked'
    entry = registry._entry(candidate.skill_id, candidate.version)
    assert entry.lifecycle.state == "revoked"

    # Verification 4: Cannot transition out of revoked (terminal state invariant)
    assert transition(entry.lifecycle, "active", reason="bypass-attempt") is False
    assert transition(entry.lifecycle, "candidate", reason="bypass-attempt") is False
    assert transition(entry.lifecycle, "validated", reason="bypass-attempt") is False

    # Verification 5: Provenance tuple records full transition history
    provenance = entry.lifecycle.provenance
    assert any("active->revoked:defect-mitigation-test:ev-rollback-drill" in p for p in provenance)


def test_r10_d3_supersession_via_registry_supersede():
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coordinator, registry=registry)

    behavior = GOGOMATCH_BEHAVIORS[0]
    cand_v1 = behavior_to_candidate(behavior, version=1)
    active_v1 = _activate_candidate(cand_v1, registry)
    assert registry.is_executable(active_v1) is True

    # Test explicit manual supersession of v1 by registry.supersede
    registry.supersede(
        behavior.behavior_id,
        1,
        new_version=2,
        evidence_id="ev-upgrade-v2",
        reason="behavior-logic-refinement",
    )

    # Verification 1: v1 is immediately no longer executable
    assert registry.is_executable(active_v1) is False
    rev = rt.observe()
    with pytest.raises(SkillExecutionError) as exc_info:
        executor.execute(active_v1, revision=rev, op="launch_app")
    assert "skill-not-registry-active" in str(exc_info.value)

    # Verification 2: v1 lifecycle is terminal 'superseded' with provenance tuple
    entry_v1 = registry._entry(behavior.behavior_id, 1)
    assert entry_v1.lifecycle.state == "superseded"
    assert any("active->superseded:behavior-logic-refinement:ev-upgrade-v2" in p for p in entry_v1.lifecycle.provenance)

    # Verification 3: Activating v2 operates cleanly
    cand_v2 = behavior_to_candidate(behavior, version=2)
    active_v2 = _activate_candidate(cand_v2, registry)
    assert registry.is_executable(active_v2) is True
    attempt_v2 = executor.execute(active_v2, revision=rev, op="launch_app")
    assert attempt_v2.state == "succeeded"

    # Verification 4: Test atomic supersession when activating v3 while v2 is active
    cand_v3 = behavior_to_candidate(behavior, version=3)
    active_v3 = _activate_candidate(cand_v3, registry)
    # v2 was atomically superseded by activation of v3
    entry_v2 = registry._entry(behavior.behavior_id, 2)
    assert entry_v2.lifecycle.state == "superseded"
    assert registry.is_executable(active_v2) is False
    assert registry.is_executable(active_v3) is True


def test_r10_d3_physical_removal_rollback_safety_of_boundary_guard():
    # Prove that check_agent_boundaries.py handles absent domain directory safely
    import importlib.util
    spec = importlib.util.spec_from_file_location("boundary_guard_check", str(GUARD_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # If _DOMAIN_SCAN_DIR did not exist, SCAN_DIRS equals _CORE_SCAN_DIRS
    core_dirs = mod._CORE_SCAN_DIRS
    assert all(d.is_dir() for d in core_dirs)
    assert not any(d.as_posix().endswith("src/praxiom/domain") for d in core_dirs)


# ==============================================================================
# R10-D4: Generalized guard updates where warranted
# ==============================================================================

def test_r10_d4_boundary_guard_covers_domain_and_rejects_generic_core_imports():
    import importlib.util
    spec = importlib.util.spec_from_file_location("guard_domain_gen", str(GUARD_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Confirm domain directory is covered in SCAN_DIRS
    assert any(p.as_posix().endswith("src/praxiom/domain") for p in mod.SCAN_DIRS)

    probe_path = REPO_ROOT / "src" / "praxiom" / "domain" / "_synthetic_probe.py"

    # Test rejection of generic core imports from domain files
    for core_mod in ("agent", "ios_runtime", "adaptive", "knowledge", "retrieval"):
        source = f"from praxiom.{core_mod} import something\n"
        hits = mod._ast_violations(probe_path, source)
        assert any("[prohibited domain import of generic core]" in h for h in hits), (core_mod, hits)

    # Test rejection of unsafe standard library modules
    for unsafe_lib in ("os", "sys", "pathlib", "subprocess", "mcp"):
        source = f"import {unsafe_lib}\n"
        hits = mod._ast_violations(probe_path, source)
        assert any(("[unsafe domain import]" in h or "[prohibited import]" in h) for h in hits), (unsafe_lib, hits)

    # Test rejection of bare dynamic calls
    for bare_call in ("open('file.txt')", "eval('1+1')", "exec('pass')"):
        source = f"{bare_call}\n"
        hits = mod._ast_violations(probe_path, source)
        assert any("[dynamic authority/builtin bypass]" in h for h in hits), (bare_call, hits)


def test_r10_d4_clean_production_tree_passes_all_guards():
    assert _run_script(GUARD_SCRIPT).returncode == 0
    assert _run_script(PROVENANCE_SCRIPT).returncode == 0
