"""R4 runner harness tests: matrix registry, stats, redaction, counter (G2-G5).

Phone-independent by construction: these tests import only the runner's pure
helpers plus a duck-typed fake transport. They never touch usbmux, WDA, or a
device. (The scratch evidence file below uses a repo-root path with explicit
cleanup instead of the ``tmp_path`` fixture.)
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

RUNNER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "r4_device_matrix.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("r4_device_matrix", RUNNER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclass processing resolves KW_ONLY sentinels
    # through sys.modules[cls.__module__].
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = load_runner()

_ALL_PRIMITIVES = (
    "tap_point",
    "tap_element",
    "drag",
    "swipe",
    "type_text",
    "home",
    "launch_app",
)


def test_matrix_cells_cover_r4_01_through_r4_05_in_order():
    ids = [cell["id"] for cell in runner.MATRIX_CELLS]
    assert ids == ["R4-01", "R4-02", "R4-03", "R4-04", "R4-05"]
    assert [cell["points"] for cell in runner.MATRIX_CELLS] == [3, 3, 5, 5, 2]
    assert sum(cell["points"] for cell in runner.MATRIX_CELLS) == 18


def test_r4_03_cell_covers_every_v0_primitive_plus_batch():
    (cell,) = [cell for cell in runner.MATRIX_CELLS if cell["id"] == "R4-03"]
    for primitive in _ALL_PRIMITIVES:
        assert primitive in cell["primitives"]
    assert "bounded ordered batch" in cell["primitives"]


def test_r4_06_verdict_vocabulary_is_exact():
    assert runner.VERDICTS == (
        "equivalent-required",
        "Praxiom-safer",
        "legacy-only-not-required",
        "gap",
        "environment-not-exercised",
    )


def test_summarize_stats_reports_count_min_median_p95_or_max():
    stats = runner.summarize_stats([10.0, 20.0, 30.0])
    assert stats["count"] == 3
    assert stats["min_ms"] == 10.0
    assert stats["median_ms"] == 20.0
    # Too few samples for a meaningful percentile: maximum is reported.
    assert stats["p95_or_max_ms"] == 30.0
    assert stats["percentile_meaningful"] is False

    stats = runner.summarize_stats(list(range(1, 101)))
    assert stats["count"] == 100
    assert stats["percentile_meaningful"] is True
    assert stats["p95_or_max_ms"] == 96

    assert runner.summarize_stats([])["count"] == 0


def test_scan_for_identifiers_detects_udid_shaped_values():
    udid_40 = "0123456789abcdef0123456789abcdef01234567"
    udid_25 = "f" * 25
    assert runner.scan_for_identifiers(f"device {udid_40}") != []
    assert runner.scan_for_identifiers(f"device {udid_25}") != []
    assert runner.scan_for_identifiers("pair_record blob") != []
    clean = "lifecycle=READY transport=RSD_USERSPACE samples=12 verdict=pass"
    assert runner.scan_for_identifiers(clean) == []


def test_write_evidence_round_trips_clean_report_and_refuses_tainted():
    scratch = Path(__file__).resolve().parent / "test-r4-evidence-probe.json"
    try:
        report = {
            "cell": "R4-05",
            "verdict": "pass",
            "samples": 12,
            "median_ms": 20.0,
        }
        written = runner.write_evidence(report, scratch)
        assert written == scratch
        assert json.loads(scratch.read_text(encoding="utf-8")) == report

        tainted = dict(report)
        tainted["note"] = "device 0123456789abcdef0123456789abcdef01234567"
        with pytest.raises(ValueError):
            runner.write_evidence(tainted, scratch)
    finally:
        if scratch.exists():
            scratch.unlink()


class FakeDeviceFreeTransport:
    """Minimal async transport surface for the G3 counting wrapper."""

    def __init__(self):
        self.calls: list[str] = []

    def snapshot(self):
        self.calls.append("snapshot")
        return "snapshot"

    async def connect(self):
        self.calls.append("connect")
        return "connected"

    async def tap_at_point(self, x, y):
        self.calls.append("tap_at_point")


def test_call_counting_transport_counts_device_calls_only():
    transport = FakeDeviceFreeTransport()
    counter = runner.CallCountingTransport(transport)
    assert counter.device_calls == 0
    assert asyncio.run(counter.connect()) == "connected"
    assert asyncio.run(counter.tap_at_point(1, 2)) is None
    # snapshot() is side-effect-free: delegated but never counted.
    assert counter.snapshot() == "snapshot"
    assert counter.device_calls == 2
    assert counter.call_breakdown["connect"] == 1
    assert counter.call_breakdown["tap_at_point"] == 1
    assert counter.call_breakdown["close"] == 0


def test_cli_list_cells_is_phone_independent(capsys):
    assert runner.main(["list-cells"]) == 0
    out = capsys.readouterr().out
    for cell_id in ("R4-01", "R4-02", "R4-03", "R4-04", "R4-05"):
        assert cell_id in out


def test_cli_matrix_refuses_without_explicit_device_consent(capsys):
    assert runner.main(["matrix"]) == 2
    err = capsys.readouterr().err
    assert "--confirm-device-run" in err


def test_cli_matrix_returns_nonzero_when_any_step_failed(monkeypatch, capsys):
    async def fake_run_device_matrix(_evidence_dir):
        return {
            "summary": {
                "aborted": False,
                "failed_steps": ["R4-04:recover-zero-replay"],
                "steps_passed": 28,
                "steps_total": 29,
            }
        }

    monkeypatch.setattr(runner, "run_device_matrix", fake_run_device_matrix)
    assert runner.main(["matrix", "--confirm-device-run"]) == 1
    assert '"failed_steps"' in capsys.readouterr().out
