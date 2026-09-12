"""Agent architecture-boundary guard (fail-closed).

Proves Agent/Knowledge/Retrieval/Skill/Adaptive code cannot bypass the Native iOS Runtime
or reintroduce historical-product/direct-device dependencies. Trusted
device mutation enters only through the accepted Runtime seam
(observe + execute with expected_revision).

Usage: python scripts/check_agent_boundaries.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_CORE_SCAN_DIRS = (REPO_ROOT / "src" / "praxiom" / "agent",
                    REPO_ROOT / "src" / "praxiom" / "knowledge",
                    REPO_ROOT / "src" / "praxiom" / "retrieval",
                    REPO_ROOT / "src" / "praxiom" / "skill",
                    REPO_ROOT / "src" / "praxiom" / "adaptive")
# Additive shared domain-adapter seam scan scope: the domain package is then
# subject to the same banned-edge / banned-import-root / dynamic-call checks
# as skill/adaptive code. Presence-conditional so the additive line stays
# rollback-safe: after removing the domain package the scan simply finds
# nothing and the guard (and full suite) still pass.
_DOMAIN_SCAN_DIR = REPO_ROOT / "src" / "praxiom" / "domain"
SCAN_DIRS = _CORE_SCAN_DIRS + (
    (_DOMAIN_SCAN_DIR,) if _DOMAIN_SCAN_DIR.is_dir() else ()
)

BANNED = [
    (re.compile(r"pymobiledevice3", re.IGNORECASE), "direct upstream client import"),
    (re.compile(r"phone[\s_-]*harness", re.IGNORECASE), "historical product edge"),
    (re.compile(r"\bwda\b", re.IGNORECASE), "direct device-service edge"),
    (re.compile(r"coredevice", re.IGNORECASE), "direct device-service edge"),
    (re.compile(r"appservice", re.IGNORECASE), "direct device-service edge"),
    (re.compile(r"usbmux", re.IGNORECASE), "direct mux edge"),
    (re.compile(r"from\s+praxiom\.ios_runtime\.transport\s+import", re.IGNORECASE),
     "runtime transport-internals import"),
]

BANNED_IMPORT_ROOTS = frozenset({"subprocess", "mcp"})
BANNED_DOMAIN_IMPORTS = frozenset({
    "praxiom.agent",
    "praxiom.ios_runtime",
    "praxiom.adaptive",
    "praxiom.knowledge",
    "praxiom.retrieval",
})
BANNED_SKILL_ADAPTIVE_IMPORT_ROOTS = frozenset({
    "os", "sys", "socket", "pathlib", "io", "shutil", "tempfile",
    "urllib", "http", "requests", "importlib",
})
# The sandbox is trusted boundary implementation code rather than generated
# skill code.  It alone may use Python tracing to enforce in-step preemption.
TRUSTED_SKILL_IMPORT_EXCEPTIONS = {
    "src/praxiom/skill/sandbox.py": frozenset({"sys"}),
}
BANNED_DYNAMIC_CALLS = frozenset({
    "__import__", "builtins.__import__", "importlib.import_module",
})
BANNED_BARE_CALLS = frozenset({
    "eval", "exec", "compile", "open", "input", "getattr", "setattr", "delattr",
})
BANNED_SUBPROCESS_ATTRS = frozenset({
    "Popen", "run", "call", "check_call", "check_output",
})
RUNTIME_OPERATION_CALLS = frozenset({
    "execute", "observe", "invalidate", "recover", "status", "close",
})


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _const_str(node.left)
        right = _const_str(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _ast_violations(target: Path, text: str) -> list[str]:
    violations: list[str] = []
    try:
        tree = ast.parse(text, filename=str(target))
    except SyntaxError as exc:
        return [f"{target}:{exc.lineno or 1}: [syntax-unparseable] fail closed"]

    aliases: dict[str, str] = {}
    rel = target.relative_to(REPO_ROOT).as_posix()
    is_domain = rel.startswith("src/praxiom/domain/")
    skill_or_adaptive = rel.startswith("src/praxiom/skill/") or rel.startswith(
        "src/praxiom/adaptive/"
    )
    isolated_module = skill_or_adaptive or is_domain
    if rel != "src/praxiom/skill/registry.py":
        for node in ast.walk(tree):
            if ((isinstance(node, ast.Name) and node.id == "HumanApprovalAuthority")
                    or (isinstance(node, ast.Attribute) and node.attr == "HumanApprovalAuthority")):
                violations.append(
                    f"{target}:{getattr(node, 'lineno', 1)}: "
                    "[human approval authority bypass] HumanApprovalAuthority"
                )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                aliases[alias.asname or root] = alias.name
                if root in BANNED_IMPORT_ROOTS:
                    violations.append(
                        f"{target}:{node.lineno}: [prohibited import] {alias.name}"
                    )
                allowed_roots = TRUSTED_SKILL_IMPORT_EXCEPTIONS.get(rel, frozenset())
                if (isolated_module and root in BANNED_SKILL_ADAPTIVE_IMPORT_ROOTS
                        and root not in allowed_roots):
                    tag = "[unsafe domain import]" if is_domain else "[unsafe skill/adaptive import]"
                    violations.append(
                        f"{target}:{node.lineno}: {tag} {alias.name}"
                    )
                if is_domain:
                    for banned_mod in BANNED_DOMAIN_IMPORTS:
                        if alias.name == banned_mod or alias.name.startswith(banned_mod + "."):
                            violations.append(
                                f"{target}:{node.lineno}: [prohibited domain import of generic core] {alias.name}"
                            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0]
            if root in BANNED_IMPORT_ROOTS:
                violations.append(
                    f"{target}:{node.lineno}: [prohibited import] {module}"
                )
            allowed_roots = TRUSTED_SKILL_IMPORT_EXCEPTIONS.get(rel, frozenset())
            if (isolated_module and root in BANNED_SKILL_ADAPTIVE_IMPORT_ROOTS
                    and root not in allowed_roots):
                tag = "[unsafe domain import]" if is_domain else "[unsafe skill/adaptive import]"
                violations.append(
                    f"{target}:{node.lineno}: {tag} {module}"
                )
            if is_domain:
                for banned_mod in BANNED_DOMAIN_IMPORTS:
                    if module == banned_mod or module.startswith(banned_mod + "."):
                        violations.append(
                            f"{target}:{node.lineno}: [prohibited domain import of generic core] {module}"
                        )
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{module}.{alias.name}"
                if ((module == "praxiom.skill.registry" or (node.level and module.endswith("registry")))
                        and alias.name == "HumanApprovalAuthority"
                        and rel != "src/praxiom/skill/registry.py"):
                    violations.append(
                        f"{target}:{node.lineno}: [human approval authority bypass] {alias.name}"
                    )

    # Resolve simple callable/receiver aliases (including alias chains) so
    # indirection such as ``imp = __import__`` or ``runner = sp.run`` cannot
    # bypass the guard. Iterate to a fixed point because assignments may chain.
    assignments: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            assignments.append((node.targets[0].id, node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.value is not None:
            assignments.append((node.target.id, node.value))
    for _ in range(len(assignments) + 1):
        changed = False
        for name, value in assignments:
            dotted = _dotted(value)
            if not dotted:
                continue
            root = dotted.split(".", 1)[0]
            resolved = aliases.get(root, root) + dotted[len(root):]
            if aliases.get(name) != resolved:
                aliases[name] = resolved
                changed = True
        if not changed:
            break

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted(node.func)
        root = dotted.split(".", 1)[0]
        resolved = aliases.get(root, root) + dotted[len(root):]
        if (isinstance(node.func, ast.Name)
                and node.func.id != "getattr"
                and resolved == "getattr"):
            violations.append(
                f"{target}:{node.lineno}: [dynamic authority dispatch] getattr alias"
            )
        if isolated_module and (resolved in BANNED_BARE_CALLS or dotted in BANNED_BARE_CALLS):
            violations.append(
                f"{target}:{node.lineno}: [dynamic authority/builtin bypass] {resolved or dotted}"
            )
        if (isinstance(node.func, ast.Name) and node.func.id == "getattr"
                and len(node.args) >= 2):
            attr_value = _const_str(node.args[1])
            if attr_value is None:
                violations.append(
                    f"{target}:{node.lineno}: [dynamic authority dispatch] unresolved getattr(...)"
                )
                continue
            base = _dotted(node.args[0])
            base_root = base.split(".", 1)[0] if base else ""
            resolved_base = aliases.get(base_root, base_root) + base[len(base_root):]
            attr = attr_value
            if ((resolved_base in {"builtins", "__builtins__"} and attr == "__import__")
                    or (resolved_base == "importlib" and attr == "import_module")):
                violations.append(
                    f"{target}:{node.lineno}: [dynamic import bypass] getattr({resolved_base}, {attr})"
                )
            if attr in RUNTIME_OPERATION_CALLS or (skill_or_adaptive and attr == "run"):
                violations.append(
                    f"{target}:{node.lineno}: [dynamic authority dispatch] getattr(..., {attr})"
                )
            if rel != "src/praxiom/skill/registry.py" and attr == "HumanApprovalAuthority":
                violations.append(
                    f"{target}:{node.lineno}: "
                    "[human approval authority bypass] getattr(..., HumanApprovalAuthority)"
                )
        if dotted in BANNED_DYNAMIC_CALLS or resolved in BANNED_DYNAMIC_CALLS:
            violations.append(
                f"{target}:{node.lineno}: [dynamic import bypass] {dotted}"
            )
        if resolved.startswith("subprocess.") and resolved.rsplit(".", 1)[-1] in BANNED_SUBPROCESS_ATTRS:
            violations.append(
                f"{target}:{node.lineno}: [subprocess bridge] {resolved}"
            )

        # Resolve callable aliases before classifying Runtime operations.  A
        # bare-name call such as ``op = bridge.execute; op(...)`` must retain
        # the authority of the aliased receiver instead of escaping the
        # Attribute-only branch.
        runtime_dotted = resolved if resolved else dotted
        if isinstance(node.func, ast.Call) and _dotted(node.func.func) == "getattr" \
                and len(node.func.args) >= 2:
            attr = _const_str(node.func.args[1])
            base = _dotted(node.func.args[0])
            if attr:
                base_root = base.split(".", 1)[0] if base else ""
                resolved_base = aliases.get(base_root, base_root) + base[len(base_root):]
                runtime_dotted = f"{resolved_base}.{attr}" if resolved_base else attr
        op = runtime_dotted.rsplit(".", 1)[-1] if runtime_dotted else ""
        aliased_attribute_call = (
            isinstance(node.func, ast.Name)
            and resolved != dotted
            and "." in resolved
        )
        runtime_call = isinstance(node.func, ast.Attribute) or aliased_attribute_call
        if op in RUNTIME_OPERATION_CALLS and runtime_call:
            # Exemptions intentionally depend on the direct source call, not a
            # resolved alias.  Even inside Coordinator, hiding the Runtime seam
            # behind a local callable alias fails closed.
            is_coordinator_runtime = (
                rel == "src/praxiom/agent/coordinator.py"
                and isinstance(node.func, ast.Attribute)
                and dotted.startswith("self._rt.")
            )
            is_coordinator_db = (
                rel == "src/praxiom/agent/coordinator.py"
                and isinstance(node.func, ast.Attribute)
                and dotted in {"self._db.execute", "self._db.close"}
            )
            if not is_coordinator_runtime and not is_coordinator_db:
                violations.append(
                    f"{target}:{node.lineno}: [runtime bypass] {runtime_dotted or op}"
                )
            elif is_coordinator_runtime and op == "execute":
                if not any(kw.arg == "expected_revision" for kw in node.keywords):
                    violations.append(
                        f"{target}:{node.lineno}: [unrevisioned runtime execute]"
                    )
    return violations


def check_tree(root: Path) -> list[str]:
    violations: list[str] = []
    targets = sorted(root.rglob("*.py")) if root.is_dir() else []
    for target in targets:
        text = target.read_text(encoding="utf-8", errors="replace")
        for rx, label in BANNED:
            for lineno, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    violations.append(f"{target}:{lineno}: [{label}] {line.strip()}")
        violations.extend(_ast_violations(target, text))
    return violations


def main() -> int:
    missing = [str(d) for d in SCAN_DIRS if not d.is_dir()]
    if missing:
        print(f"BOUNDARY VIOLATION: missing module dirs: {missing}")
        return 1
    violations: list[str] = []
    for d in SCAN_DIRS:
        violations.extend(check_tree(d))
    seam_text = "".join(
        (p.read_text(encoding="utf-8", errors="replace"))
        for d in _CORE_SCAN_DIRS for p in sorted(d.rglob("*.py"))
    )
    # Domain-leak scan: generic core must not name deferred game/app domains.
    for token in (
        "gogomatch", "merge boss", "r10", "visual flight", "visual_v0",
        "visual-v0", "domain_adapter", "domain-adapter",
    ):
        if token in seam_text.lower():
            violations.append(f"boundary: domain leak [{token}]")
    if violations:
        print("BOUNDARY VIOLATION:")
        for v in violations:
            print(f"  {v}")
        return 1
    print("OK: agent/knowledge/retrieval/skill/adaptive respect the Runtime boundary.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
