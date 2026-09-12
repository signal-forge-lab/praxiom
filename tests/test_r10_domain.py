"""R10-A shared domain adapter seam — deterministic Lane-S matrix.

Proves the frozen seam contract: pure declarative data + one pure mapping,
import-allowlisted, fail-closed on unsupported operations, and reachable
toward device mutation only as a registry-active skill through
SkillExecutor -> ExecutionCoordinator -> Runtime.execute(expected_revision).

Fixtures here are repo-local synthesized contract data (inline, deterministic,
no recorded device captures). Per-domain fixture directories under
``tests/fixtures/r10/`` belong to the per-domain lanes, not this file.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from praxiom.domain import DomainBehavior, behavior_to_candidate
from praxiom.skill.candidate import RUNTIME_OPS
from praxiom.skill.executor import SkillExecutionError, SkillExecutor
from praxiom.skill.gates import GATE_ORDER, run_gates
from praxiom.skill.registry import HumanApprovalAuthority, SkillRegistry
from praxiom.agent.coordinator import DeviceLeaseManager, ExecutionCoordinator
from tests.fakes import FakeRuntime

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "check_agent_boundaries.py"
PROVENANCE_GUARD = REPO_ROOT / "scripts" / "check_provenance.py"
DOMAIN_DIR = REPO_ROOT / "src" / "praxiom" / "domain"
SCRATCH = REPO_ROOT / ".pytest-tmp" / "r10-domain-guard"
RUNTIME_SOURCE = REPO_ROOT / "src" / "praxiom" / "ios_runtime" / "runtime.py"
SIX_OPERATIONS = {"status", "observe", "execute", "invalidate", "recover", "close"}
# Frozen seam allowlist: the only modules domain code may import.
DOMAIN_IMPORT_ALLOWLIST = {"dataclasses", "typing", "praxiom.skill.candidate"}


def _load_guard():
    import importlib.util
    spec = importlib.util.spec_from_file_location("boundary_guard_r10", str(GUARD))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, cwd=REPO_ROOT,
    )


def _fixture_behavior(**overrides) -> DomainBehavior:
    """Deterministic synthesized contract fixture (never device-captured)."""
    base = dict(
        behavior_id="mergeboss:open-level-board",
        domain="mergeboss",
        summary="open the level board surface for observation",
        source_evidence=("docs/design/20260907_r8plus_execution_plan.md",),
        inputs=("level-id",),
        preconditions=("revision-bound: fresh observation",),
        postconditions=("board surface visible in observation",),
        risk="low",
        reversibility="reversible",
        ops=frozenset({"launch_app"}),
        human_gate=False,
    )
    base.update(overrides)
    return DomainBehavior(**base)


def _activated_skill(behavior: DomainBehavior, *, registry: SkillRegistry):
    """Drive a seam candidate through the full registry-owned lifecycle."""
    candidate = behavior_to_candidate(behavior)
    gates = run_gates(candidate)
    assert gates.passed and gates.evaluated == GATE_ORDER, gates
    registry.register(candidate)
    registry.validate(behavior.behavior_id, 1, evidence_ids=("ev-alpha", "ev-beta"))
    registry.record_success(behavior.behavior_id, 1, revision="val-rev-1",
                            evidence_id="suc-alpha")
    registry.record_success(behavior.behavior_id, 1, revision="val-rev-2",
                            evidence_id="suc-beta")
    return registry.activate(behavior.behavior_id, 1, confidence=0.9,
                             evidence_id="activate")


# --- A1: generic core stays domain-neutral; the guard scans the domain pkg ---

def test_r10_a1_guard_green_with_domain_scan_scope_active():
    assert DOMAIN_DIR.is_dir()
    guard = _load_guard()
    assert any(p.as_posix().endswith("src/praxiom/domain") for p in guard.SCAN_DIRS)
    # The generic-core domain-token tripwire is retained (R8 freeze §3).
    guard_text = GUARD.read_text(encoding="utf-8")
    assert '"gogomatch"' in guard_text and '"merge boss"' in guard_text
    assert _run(GUARD).returncode == 0


# --- A2: adapters cannot reach transport/device edges ------------------------

def test_r10_a2_banned_edge_imports_fail_guard_for_domain_files():
    guard = _load_guard()
    # Regex-level banned edges in a domain-shaped tree fail the file scan.
    domain_scratch = SCRATCH / "domain"
    domain_scratch.mkdir(parents=True, exist_ok=True)
    planted = domain_scratch / "_planted_banned_edge.py"
    planted.write_text(
        "from praxiom.ios_runtime.transport import IosTransport\n"
        "import pymobiledevice3\n",
        encoding="utf-8",
    )
    try:
        hits = guard.check_tree(SCRATCH)
        assert any("transport-internals" in hit for hit in hits)
        assert any("upstream" in hit for hit in hits)
    finally:
        planted.unlink(missing_ok=True)
    # AST-level prohibited roots fail for a domain-scoped probe path.
    probe = DOMAIN_DIR / "_synthetic_probe.py"
    hits = guard._ast_violations(probe, "import mcp\nimport subprocess as sp\nsp.run(['x'])\n")
    assert any("[prohibited import] mcp" in hit for hit in hits)
    assert any("[prohibited import] subprocess" in hit for hit in hits)
    assert _run(GUARD).returncode == 0


def test_r10_a2_domain_import_allowlist_fail_closed():
    """Every domain file imports only dataclasses/typing/praxiom.skill.candidate."""
    for path in sorted(DOMAIN_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name in DOMAIN_IMPORT_ALLOWLIST, (
                        f"{path}:{node.lineno}: domain import outside the frozen "
                        f"seam allowlist: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # intra-package relative import stays in-domain
                    continue
                in_package = (node.module or "").startswith("praxiom.domain.")
                assert in_package or node.module in DOMAIN_IMPORT_ALLOWLIST, (
                    f"{path}:{node.lineno}: domain import outside the frozen "
                    f"seam allowlist: {node.module}"
                )


# --- A3: no Phone Harness / internal MCP device authority --------------------

def test_r10_a3_provenance_and_authority_guards_green():
    assert _run(PROVENANCE_GUARD).returncode == 0
    assert _run(GUARD).returncode == 0


# --- A4: mutations only via registry-active skill -> executor -> coordinator -> runtime

def test_r10_a4_domain_mutation_only_through_revision_bound_authority_chain():
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coordinator, registry=registry)
    skill = _activated_skill(_fixture_behavior(), registry=registry)

    revision = rt.observe()
    attempt = executor.execute(skill, revision=revision, op="launch_app")
    assert attempt.state == "succeeded"
    assert rt.device_calls == 1

    # The accepted revision was invalidated by the attempt: replaying the same
    # revision is stale, fails closed, and makes zero device calls.
    stale = executor.execute(skill, revision=revision, op="launch_app")
    assert stale.state == "failed"
    assert stale.evidence["error_code"] == "STALE_REVISION"
    assert stale.retry_safe is False
    assert rt.device_calls == 1

    # Registry authority is the only execution authority.
    registry.revoke(skill.skill_id, 1, evidence_id="rollback-drill")
    with pytest.raises(SkillExecutionError):
        executor.execute(skill, revision=rt.observe(), op="launch_app")


def test_r10_a4_domain_package_makes_no_runtime_operation_calls():
    """The seam stays pure data: no six-operation call site may appear in domain code."""
    guard = _load_guard()
    for path in sorted(DOMAIN_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            dotted = guard._dotted(node.func)
            op = dotted.rsplit(".", 1)[-1] if dotted else ""
            assert op not in guard.RUNTIME_OPERATION_CALLS, (
                f"{path}:{node.lineno}: domain code must not call Runtime "
                f"operations directly: {dotted}"
            )


# --- A5: lifecycle + human-gate authority stay registry-owned -----------------

def test_r10_a5_human_gate_forced_by_classification_and_binding_negatives():
    with pytest.raises(ValueError):
        behavior_to_candidate(
            _fixture_behavior(risk="high", reversibility="irreversible")
        )
    candidate = behavior_to_candidate(
        _fixture_behavior(risk="high", reversibility="irreversible", human_gate=True)
    )
    assert candidate.human_gate is True
    assert run_gates(candidate).passed
    # Medium/compensable work stays ungated at the seam.
    ungated = behavior_to_candidate(
        _fixture_behavior(risk="medium", reversibility="compensable")
    )
    assert ungated.human_gate is False
    assert run_gates(ungated).passed

    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    authority = HumanApprovalAuthority()
    registry = SkillRegistry(human_approval_authority=authority)
    executor = SkillExecutor(coordinator=coordinator, registry=registry)
    skill = _activated_skill(
        _fixture_behavior(risk="high", reversibility="irreversible", human_gate=True),
        registry=registry,
    )

    revision = rt.observe()
    with pytest.raises(SkillExecutionError):
        executor.execute(skill, revision=revision, op="launch_app")  # no approval
    payload = {"op": "launch_app"}
    evidence = authority.approve(
        skill_id=skill.skill_id, version=skill.version, revision=revision,
        payload=payload, evidence_id="hg-evidence-1",
    )
    approval = registry.issue_human_gate_approval(
        skill, revision=revision, payload=payload, evidence=evidence,
    )
    assert executor.execute(
        skill, revision=revision, op="launch_app", human_gate_approval=approval,
    ).state == "succeeded"
    # One-shot: replay against a fresh revision fails closed.
    with pytest.raises(SkillExecutionError):
        executor.execute(skill, revision=rt.observe(), op="launch_app",
                         human_gate_approval=approval)
    # Bound to the exact revision: a cross-revision use is rejected without
    # consuming the approval.
    revision_2 = rt.observe()
    evidence_2 = authority.approve(
        skill_id=skill.skill_id, version=skill.version, revision=revision_2,
        payload=payload, evidence_id="hg-evidence-2",
    )
    approval_2 = registry.issue_human_gate_approval(
        skill, revision=revision_2, payload=payload, evidence=evidence_2,
    )
    with pytest.raises(SkillExecutionError):
        executor.execute(skill, revision=revision_2 + "-other", op="launch_app",
                         human_gate_approval=approval_2)
    assert executor.execute(
        skill, revision=revision_2, op="launch_app", human_gate_approval=approval_2,
    ).state == "succeeded"


def test_r10_a5_registry_lifecycle_removes_domain_execution_authority():
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coordinator, registry=registry)
    skill = _activated_skill(_fixture_behavior(), registry=registry)
    registry.degrade(skill.skill_id, 1, evidence_id="quality-drop")
    assert registry.is_executable(skill) is False
    with pytest.raises(SkillExecutionError):
        executor.execute(skill, revision=rt.observe(), op="launch_app")


# --- A6: R9 budget/fallback floors stay authoritative over domain kinds -------

def test_r10_a6_r9_budgets_independent_and_fallback_safe_over_domain_kinds():
    from praxiom.adaptive.fallback import RegressionBudget, check_budget, safe_fallback

    behavior = _fixture_behavior()
    launch_kind = f"{behavior.domain}:launch"
    observe_kind = f"{behavior.domain}:observe"
    launch_budget = RegressionBudget(kind=launch_kind, max_latency_ms=100)
    observe_budget = RegressionBudget(kind=observe_kind, max_latency_ms=5000)

    breach = check_budget(launch_budget, p90_ms=500, observe_rate=0.1, recovery_rate=0.9)
    assert not breach.within and breach.fallback
    assert breach.reason == "latency-budget-exceeded"
    within = check_budget(observe_budget, p90_ms=10, observe_rate=0.1, recovery_rate=0.9)
    assert within.within and not within.fallback
    assert within.reason == "within-budget"

    # A breach in one domain kind disables optimization for that kind only,
    # via the unchanged R9-safe path (mode/optimization/reobserve fixed).
    for budget in (launch_budget, observe_budget):
        fallback = safe_fallback(signal_failed=True, reason=f"budget:{budget.kind}")
        assert fallback["mode"] == "r7-safe-baseline"
        assert fallback["optimization"] == "disabled"
        assert fallback["reobserve"] is True


# --- A7: unsupported ops fail closed; the six-op Runtime surface is intact ----

def test_r10_a7_unsupported_operations_fail_closed_at_the_seam():
    with pytest.raises(ValueError):
        behavior_to_candidate(
            _fixture_behavior(ops=frozenset({"launch_app", "wipe_app_data"}))
        )
    with pytest.raises(ValueError):
        behavior_to_candidate(_fixture_behavior(ops=frozenset()))
    candidate = behavior_to_candidate(
        _fixture_behavior(ops=frozenset({"launch_app", "swipe"}))
    )
    assert candidate.authority <= RUNTIME_OPS
    assert run_gates(candidate).passed

    # The executor keeps narrowing per-domain authority after activation.
    rt = FakeRuntime()
    coordinator = ExecutionCoordinator(rt, DeviceLeaseManager())
    registry = SkillRegistry()
    executor = SkillExecutor(coordinator=coordinator, registry=registry)
    skill = _activated_skill(_fixture_behavior(), registry=registry)
    with pytest.raises(SkillExecutionError, match="op-not-authorized"):
        executor.execute(skill, revision=rt.observe(), op="tap_point")


def test_r10_a7_runtime_public_surface_is_exactly_six_operations():
    tree = ast.parse(RUNTIME_SOURCE.read_text(encoding="utf-8"))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "NativeIosRuntime"]
    assert len(classes) == 1
    public_methods = {
        node.name for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    assert public_methods == SIX_OPERATIONS
    exports = [n for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)]
    assert ast.literal_eval(exports[0].value) == ["NativeIosRuntime"]


# --- seam contract: deterministic mapping + fail-closed field validation ------

def test_r10_adapter_maps_fixture_to_candidate_deterministically():
    behavior = _fixture_behavior()
    first = behavior_to_candidate(behavior)
    second = behavior_to_candidate(behavior)
    assert first == second  # pure, deterministic mapping
    assert first.skill_id == behavior.behavior_id
    assert first.version == 1
    assert first.inputs == behavior.inputs
    assert first.outputs == behavior.postconditions
    assert first.preconditions == behavior.preconditions
    assert first.postconditions == behavior.postconditions
    assert first.risk == behavior.risk
    assert first.reversibility == behavior.reversibility
    assert first.authority == behavior.ops
    assert first.provenance == behavior.source_evidence
    assert first.lifecycle == "candidate"
    assert first.code_ref is None
    assert first.human_gate is False
    assert behavior_to_candidate(behavior, version=3).version == 3


def test_r10_adapter_rejects_missing_revision_binding():
    with pytest.raises(ValueError, match="revision"):
        behavior_to_candidate(_fixture_behavior(preconditions=("board visible",)))


def test_r10_adapter_rejects_mismatched_or_malformed_behavior_id():
    for bad_id in (
        "other-domain:open-level-board",
        "mergeboss:Open Level",
        "mergeboss",
        "mergeboss:",
    ):
        with pytest.raises(ValueError):
            behavior_to_candidate(_fixture_behavior(behavior_id=bad_id))


def test_r10_adapter_rejects_contract_field_violations():
    violations = [
        dict(behavior_id="mergeboss:"),  # empty kebab-behavior
        dict(domain=""),
        dict(summary=""),
        dict(summary="x" * 281),
        dict(source_evidence=()),
        dict(inputs=()),
        dict(postconditions=()),
        dict(risk="extreme"),
        dict(reversibility="undoable"),
    ]
    for override in violations:
        with pytest.raises(ValueError):
            behavior_to_candidate(_fixture_behavior(**override))


def test_r10_adapter_rejects_non_positive_or_boolean_version():
    for bad_version in (0, -1, True):
        with pytest.raises(ValueError):
            behavior_to_candidate(_fixture_behavior(), version=bad_version)
