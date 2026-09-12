"""Fail-closed regression test for the architecture-boundary guard.

Uses workspace-local scratch dirs (never tmp_path) to stay green under the
sandbox file policy.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "check_agent_boundaries.py"
SCRATCH = REPO_ROOT / ".pytest-tmp" / "boundary-guard"


def _run_guard() -> int:
    return subprocess.run([sys.executable, str(GUARD)],
                          capture_output=True, text=True).returncode


def test_boundary_guard_passes_on_clean_tree():
    assert _run_guard() == 0


def test_boundary_guard_fails_closed_on_planted_violation():
    target_dir = SCRATCH / "agent"
    target_dir.mkdir(parents=True, exist_ok=True)
    planted = target_dir / "_planted_violation.py"
    # Plant inside a shadow tree by monkey-checking check_tree directly.
    import importlib.util
    spec = importlib.util.spec_from_file_location("boundary_guard", str(GUARD))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    planted.write_text("x = 1  # pymobiledevice3\n", encoding="utf-8")
    try:
        hits = mod.check_tree(SCRATCH)
        assert any("pymobiledevice3" in h or "upstream" in h for h in hits)
    finally:
        planted.unlink(missing_ok=True)
    # And the real scan still passes after cleanup.
    assert _run_guard() == 0


def test_boundary_guard_fails_closed_on_subprocess_mcp_dynamic_and_runtime_bypass():
    target_dir = SCRATCH / "agent"
    target_dir.mkdir(parents=True, exist_ok=True)
    import importlib.util
    spec = importlib.util.spec_from_file_location("boundary_guard_hard", str(GUARD))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cases = {
        "subprocess_alias.py": "import subprocess as sp\nsp.run(['x'])\n",
        "subprocess_callable_alias.py": "import subprocess as sp\nrunner = sp.run\nrunner(['x'])\n",
        "mcp_alias.py": "import mcp as bridge\nbridge.ClientSession()\n",
        "dynamic_import.py": "import importlib\nimportlib.import_module('subprocess')\n",
        "dunder_import.py": "__import__('subprocess')\n",
        "dunder_import_alias.py": "from builtins import __import__ as imp\nimp('subprocess')\n",
        "dunder_import_alias_chain.py": "from builtins import __import__ as imp\nloader = imp\nloader('subprocess')\n",
        "dunder_import_getattr.py": "import builtins\nloader = getattr(builtins, '__import__')\nloader('subprocess')\n",
        "import_module_getattr.py": "import importlib\nloader = getattr(importlib, 'import_module')\nloader('subprocess')\n",
        "runtime_bypass.py": "def x(port):\n    port.execute([], expected_revision='r')\n",
        "runtime_unhinted_receiver.py": "def x(bridge):\n    bridge.execute([], expected_revision='r')\n",
        "runtime_call_receiver.py": "def x(get_runtime):\n    get_runtime().execute([], expected_revision='r')\n",
        "runtime_callable_alias.py": "def x(bridge):\n    op = bridge.execute\n    op([], expected_revision='r')\n",
        "runtime_callable_alias_chain.py": "def x(bridge):\n    op = bridge.execute\n    again = op\n    again([], expected_revision='r')\n",
    }
    try:
        for name, source in cases.items():
            planted = target_dir / name
            planted.write_text(source, encoding="utf-8")
            hits = mod.check_tree(SCRATCH)
            assert hits, name
            planted.unlink()
    finally:
        for p in target_dir.glob("*.py"):
            p.unlink(missing_ok=True)
    assert _run_guard() == 0


def test_boundary_guard_fails_closed_on_skill_adaptive_builtin_import_getattr_and_scope_bypasses():
    import importlib.util
    spec = importlib.util.spec_from_file_location("boundary_guard_adaptive_hard", str(GUARD))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    skill_target = REPO_ROOT / "src" / "praxiom" / "skill" / "_synthetic_probe.py"
    adaptive_target = REPO_ROOT / "src" / "praxiom" / "adaptive" / "_synthetic_probe.py"
    retrieval_target = REPO_ROOT / "src" / "praxiom" / "retrieval" / "_synthetic_probe.py"

    skill_cases = {
        "import os\ndef x():\n    return os.getcwd()\n": "unsafe skill/adaptive import",
        "def x():\n    return eval('1+1')\n": "dynamic authority/builtin bypass",
        "def x():\n    return open('x')\n": "dynamic authority/builtin bypass",
        "def x(rt):\n    return getattr(rt, 'execute')([], expected_revision='r')\n": "dynamic authority",
    }
    for source, marker in skill_cases.items():
        hits = mod._ast_violations(skill_target, source)
        assert any(marker in hit for hit in hits), (source, hits)

    # sys remains prohibited for ordinary skill code.  The sole narrow
    # exception is the trusted sandbox implementation, which needs settrace to
    # preempt a non-returning generated step.
    hits = mod._ast_violations(skill_target, "import sys\ndef x():\n    return sys.gettrace()\n")
    assert any("unsafe skill/adaptive import" in hit for hit in hits)
    sandbox_target = REPO_ROOT / "src" / "praxiom" / "skill" / "sandbox.py"
    hits = mod._ast_violations(sandbox_target, "import sys\n")
    assert not any("unsafe skill/adaptive import" in hit for hit in hits)

    hits = mod._ast_violations(
        adaptive_target,
        "def x(rt):\n    return getattr(rt, 'execute')([], expected_revision='r')\n",
    )
    assert any("dynamic authority" in hit for hit in hits)

    # Runtime getattr dispatch is prohibited across every scanned production layer,
    # not only skill/adaptive.
    hits = mod._ast_violations(
        retrieval_target,
        "def x(rt):\n    return getattr(rt, 'execute')([], expected_revision='r')\n",
    )
    assert any("dynamic authority" in hit for hit in hits)
    for source in (
        "def x(rt, name):\n    return getattr(rt, name)([], expected_revision='r')\n",
        "def x(rt):\n    name = 'execute'\n    return getattr(rt, name)([], expected_revision='r')\n",
        "def x(rt):\n    return getattr(rt, ''.join(['exe', 'cute']))([], expected_revision='r')\n",
    ):
        hits = mod._ast_violations(retrieval_target, source)
        assert any("dynamic authority dispatch" in hit for hit in hits), (source, hits)

    hits = mod._ast_violations(
        adaptive_target,
        "from praxiom.skill.registry import HumanApprovalAuthority\n",
    )
    assert any("human approval authority bypass" in hit for hit in hits)
    for source in (
        "import praxiom.skill.registry as registry\nregistry.HumanApprovalAuthority()\n",
        "from .registry import HumanApprovalAuthority\nHumanApprovalAuthority()\n",
        "import praxiom.skill.registry as registry\ndef x():\n    return getattr(registry, 'HumanApprovalAuthority')()\n",
    ):
        hits = mod._ast_violations(adaptive_target, source)
        assert any("human approval authority bypass" in hit for hit in hits), (source, hits)
    for area in ("agent", "knowledge", "retrieval"):
        target = REPO_ROOT / "src" / "praxiom" / area / "_synthetic_probe.py"
        hits = mod._ast_violations(
            target,
            "import praxiom.skill.registry as registry\nregistry.HumanApprovalAuthority()\n",
        )
        assert any("human approval authority bypass" in hit for hit in hits), (area, hits)

    for area in ("agent", "knowledge", "retrieval", "adaptive", "skill"):
        target = REPO_ROOT / "src" / "praxiom" / area / "_synthetic_probe.py"
        hits = mod._ast_violations(
            target,
            "g = getattr\ndef x(rt, name):\n    return g(rt, name)([], expected_revision='r')\n",
        )
        assert any("dynamic authority dispatch" in hit for hit in hits), (area, hits)

    # Deferred R10/Visual scope names are covered by the main seam-level tripwire.
    guard_text = GUARD.read_text(encoding="utf-8")
    assert '"r10"' in guard_text and '"visual flight"' in guard_text
    assert _run_guard() == 0


def test_boundary_guard_fails_closed_on_domain_file_importing_banned_edge():
    # The shared domain-adapter seam is inside the guard scan scope: a domain
    # file importing a direct device edge (transport internals / upstream
    # client / MCP) must fail the guard, and the clean tree stays green.
    import importlib.util
    spec = importlib.util.spec_from_file_location("boundary_guard_domain", str(GUARD))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert any(
        p.as_posix().endswith("src/praxiom/domain") for p in mod.SCAN_DIRS
    ), mod.SCAN_DIRS

    domain_probe = REPO_ROOT / "src" / "praxiom" / "domain" / "_synthetic_probe.py"
    for source, marker in (
        ("import mcp\n", "[prohibited import] mcp"),
        ("import subprocess as sp\nsp.run(['x'])\n", "[prohibited import] subprocess"),
    ):
        hits = mod._ast_violations(domain_probe, source)
        assert any(marker in hit for hit in hits), (source, hits)

    # Regex-level banned edges fail the file scan over a domain-shaped tree.
    domain_scratch = SCRATCH / "domain"
    domain_scratch.mkdir(parents=True, exist_ok=True)
    planted = domain_scratch / "_planted_domain_edge.py"
    planted.write_text(
        "from praxiom.ios_runtime.transport import IosTransport\n"
        "import pymobiledevice3\n",
        encoding="utf-8",
    )
    try:
        hits = mod.check_tree(SCRATCH)
        assert any("transport-internals" in hit for hit in hits)
        assert any("upstream" in hit for hit in hits)
    finally:
        planted.unlink(missing_ok=True)
    assert _run_guard() == 0


def test_boundary_guard_fails_closed_on_domain_file_importing_generic_core_or_unsafe_builtins():
    # Generalized guard coverage (R10-D / D4): domain files cannot import generic core
    # packages (praxiom.agent, praxiom.ios_runtime, praxiom.adaptive, praxiom.knowledge,
    # praxiom.retrieval) or unsafe stdlib modules (os, sys, pathlib, etc.) or bare calls.
    import importlib.util
    spec = importlib.util.spec_from_file_location("boundary_guard_domain_gen", str(GUARD))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    domain_probe = REPO_ROOT / "src" / "praxiom" / "domain" / "_synthetic_probe.py"
    probes = (
        ("import praxiom.agent.coordinator\n", "[prohibited domain import of generic core]"),
        ("from praxiom.ios_runtime import NativeIosRuntime\n", "[prohibited domain import of generic core]"),
        ("from praxiom.adaptive.fallback import check_budget\n", "[prohibited domain import of generic core]"),
        ("from praxiom.knowledge import store\n", "[prohibited domain import of generic core]"),
        ("from praxiom.retrieval import search\n", "[prohibited domain import of generic core]"),
        ("import os\n", "[unsafe domain import]"),
        ("import pathlib\n", "[unsafe domain import]"),
        ("x = open('test.txt')\n", "[dynamic authority/builtin bypass]"),
        ("eval('1+1')\n", "[dynamic authority/builtin bypass]"),
    )
    for source, marker in probes:
        hits = mod._ast_violations(domain_probe, source)
        assert any(marker in hit for hit in hits), f"Expected {marker} in hits for {source!r}, got: {hits}"
