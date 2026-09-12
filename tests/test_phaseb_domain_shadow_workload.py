from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from praxiom.ios_runtime.models import (
    ActionOutcome,
    Element,
    ExecutionResult,
    FrameInfo,
    LifecycleState,
    Observation,
    RuntimeLimits,
    RuntimeStatus,
    ScreenSize,
    TransportKind,
    WdaState,
)


SCRIPT = Path(__file__).parents[1] / "scripts" / "phaseb_domain_shadow_workload.py"
SPEC = importlib.util.spec_from_file_location("phaseb_domain_shadow_workload", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class FakeRuntime:
    def __init__(
        self, *, fail_on_execute: int | None = None, locked: bool = False
    ) -> None:
        self.revision = 0
        self.execute_calls = 0
        self.closed = False
        self.fail_on_execute = fail_on_execute
        self.locked = locked
        self.trace = type("Trace", (), {"render": lambda self: []})()

    async def status(self):
        return RuntimeStatus(
            contract_version="v0",
            lifecycle_state=LifecycleState.READY,
            transport=TransportKind.RSD_USERSPACE,
            wda_state=WdaState.READY,
            limits=RuntimeLimits(max_batch_actions=32),
            current_revision=None,
        )

    async def observe(self):
        self.revision += 1
        return Observation(
            revision=f"r{self.revision}",
            captured_at=datetime.now(timezone.utc),
            screen=ScreenSize(width=100, height=200),
            frame=FrameInfo(width=100, height=200, format="png"),
            sources=("screenshot", "accessibility"),
            elements=(
                Element(
                    ref="lock",
                    role="XCUIElementTypeOther",
                    source="accessibility",
                    text=(
                        "client-identifier:com.apple.springboard,"
                        "element-identifier:systemApertureElementIdentifierLock"
                    ),
                    visible=True,
                ),
            ) if self.locked else (),
        )

    async def execute(self, actions, *, expected_revision):
        self.execute_calls += 1
        if self.fail_on_execute == self.execute_calls:
            raise RuntimeError("synthetic-device-failure")
        assert expected_revision.startswith("r")
        assert len(actions) == 1
        return ExecutionResult(
            completed_actions=1,
            accepted_revision_invalidated=True,
            outcomes=(ActionOutcome(index=0, kind="launch_app", duration_ms=1.0),),
        )

    async def close(self):
        self.closed = True


def test_shadow_workload_collects_distinct_revision_experience(tmp_path):
    runtime = FakeRuntime()
    report = module.collect_shadow_workload(
        runtime=runtime,
        bundle_ids={"mergeboss": "bundle-a", "gogomatch": "bundle-b"},
        state_root=tmp_path,
        run_id="shadow-fake",
        iterations=2,
    )

    assert report["status"] == "completed"
    assert report["adaptive_live_apply"] is False
    assert report["sequence_live_apply"] is False
    assert runtime.execute_calls == 4
    assert runtime.closed
    assert report["experience"]["episodes"] == 4
    assert report["experience"]["shadow_recommendations"] == 4
    assert report["summary"]["policy"]["decisions"] == 4
    assert report["summary"]["sequences"]["shadow_recommended_sizes"] == {
        "1": 2,
        "2": 2,
    }
    assert report["summary"]["sequences"]["actual_sizes"] == {}
    assert all(domain["status"] == "completed" for domain in report["domains"])
    assert all(
        attempt["effect"] == "NONE" and attempt["replayed"] is False
        for domain in report["domains"] for attempt in domain["attempts"]
    )

    events = (tmp_path / "runs" / "shadow-fake" / "events.jsonl").read_text(
        encoding="utf-8"
    )
    assert "bundle-a" not in events
    assert "bundle-b" not in events
    assert events.count('"event_type":"learning.recorded"') == 4
    assert events.count('"event_type":"policy.decision"') == 4


def test_shadow_workload_stops_after_failed_attempt_without_replay(tmp_path):
    runtime = FakeRuntime(fail_on_execute=2)
    report = module.collect_shadow_workload(
        runtime=runtime,
        bundle_ids={"mergeboss": "bundle-a", "gogomatch": "bundle-b"},
        state_root=tmp_path,
        run_id="shadow-failure",
        iterations=2,
    )

    assert report["status"] == "stopped"
    assert runtime.execute_calls == 2
    assert len(report["domains"]) == 1
    assert report["domains"][0]["attempts"][-1]["state"] != "succeeded"
    assert runtime.closed


def test_shadow_workload_blocks_locked_device_before_mutation(tmp_path):
    runtime = FakeRuntime(locked=True)
    report = module.collect_shadow_workload(
        runtime=runtime,
        bundle_ids={"mergeboss": "bundle-a", "gogomatch": "bundle-b"},
        state_root=tmp_path,
        run_id="shadow-locked",
        iterations=2,
    )

    assert report["status"] == "blocked"
    assert report["domains"] == [{
        "domain": "mergeboss",
        "behavior_id": "mergeboss:launch",
        "risk": "low",
        "reversibility": "reversible",
        "attempts": [],
        "status": "blocked",
        "stop_reason": "device-locked",
    }]
    assert runtime.execute_calls == 0
    assert runtime.closed


def test_shadow_workload_generates_unique_default_run_ids(tmp_path):
    first = module.collect_shadow_workload(
        runtime=FakeRuntime(),
        bundle_ids={"mergeboss": "bundle-a", "gogomatch": "bundle-b"},
        state_root=tmp_path,
        iterations=2,
    )
    second = module.collect_shadow_workload(
        runtime=FakeRuntime(),
        bundle_ids={"mergeboss": "bundle-a", "gogomatch": "bundle-b"},
        state_root=tmp_path,
        iterations=2,
    )

    assert first["run_id"].startswith("phaseb-domain-")
    assert second["run_id"].startswith("phaseb-domain-")
    assert first["run_id"] != second["run_id"]
    assert (tmp_path / "runs" / first["run_id"] / "events.jsonl").exists()
    assert (tmp_path / "runs" / second["run_id"] / "events.jsonl").exists()


@pytest.mark.parametrize("iterations", [0, 1])
def test_shadow_workload_requires_learning_minimum_iterations(tmp_path, iterations):
    with pytest.raises(ValueError, match="iterations must be >= 2"):
        module.collect_shadow_workload(
            runtime=FakeRuntime(),
            bundle_ids={"mergeboss": "a", "gogomatch": "b"},
            state_root=tmp_path,
            iterations=iterations,
        )


@pytest.mark.parametrize(
    ("status", "expected"),
    [("completed", 0), ("blocked", 2), ("stopped", 1)],
)
def test_phaseb_cli_exit_codes_distinguish_blocked(monkeypatch, status, expected):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--confirm-device-run",
            "--mergeboss-bundle-id",
            "a",
            "--gogomatch-bundle-id",
            "b",
        ],
    )
    import praxiom.ios_runtime.runtime as runtime_module

    monkeypatch.setattr(runtime_module, "NativeIosRuntime", lambda **_kwargs: object())
    monkeypatch.setattr(
        module,
        "collect_shadow_workload",
        lambda **_kwargs: {"status": status},
    )
    assert module.main() == expected
