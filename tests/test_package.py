"""R3-00 bootstrap determinism checks: package imports + provenance guard."""

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_provenance.py"


def test_package_imports():
    import praxiom
    import praxiom.ios_runtime

    assert praxiom.ios_runtime is not None


def test_check_provenance_passes_on_clean_repo():
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_check_provenance_detects_phone_harness_reference(tmp_path):
    spec = importlib.util.spec_from_file_location("check_provenance", CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("import phone_harness\n", encoding="utf-8")
    hits = module.find_violations([bad_file])
    assert len(hits) == 1
    assert "bad.py:1" in hits[0]
