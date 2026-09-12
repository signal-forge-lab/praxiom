"""Provenance guard for the Praxiom greenfield boundary.

Phone Harness is historical/reference only: it is never a production, build,
or runtime dependency of this repository. This script exits non-zero if any
Phone Harness package/module name appears in the production source tree or in
the dependency declaration (pyproject.toml).

Scan paths are deliberately limited to production inputs (``src/`` and
``pyproject.toml``). Documentation that states the prohibition (docs/,
README.md) is intentionally excluded from the scan.

Usage:
    python scripts/check_provenance.py
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Production inputs only. docs/ and README.md are excluded on purpose: they
# are allowed (and required) to mention the prohibition itself.
SCAN_TARGETS: tuple[Path, ...] = (REPO_ROOT / "src", REPO_ROOT / "pyproject.toml")

PATTERN = re.compile(r"phone[\s_-]*harness", re.IGNORECASE)


def find_violations(paths: Iterable[Path]) -> list[str]:
    """Return one ``file:line: text`` string per Phone Harness reference."""
    violations: list[str] = []
    for path in paths:
        if path.is_dir():
            targets = sorted(path.rglob("*.py"))
        elif path.is_file():
            targets = [path]
        else:
            continue
        for target in targets:
            text = target.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if PATTERN.search(line):
                    violations.append(f"{target}:{lineno}: {line.strip()}")
    return violations


def main() -> int:
    violations = find_violations(SCAN_TARGETS)
    if violations:
        print("PROVENANCE VIOLATION: Phone Harness reference found in production paths:")
        for hit in violations:
            print(f"  {hit}")
        return 1
    print("OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
