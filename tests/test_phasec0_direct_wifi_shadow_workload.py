from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phasec0_direct_wifi_shadow_workload.py"
SPEC = importlib.util.spec_from_file_location("phasec0_direct_wifi_shadow_workload", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class _SlowRuntime:
    def __init__(self) -> None:
        self.observe_calls = 0

    async def observe(self):
        self.observe_calls += 1
        await asyncio.sleep(3600)


def test_bounded_observe_times_out_once_without_retry():
    runtime = _SlowRuntime()
    with pytest.raises(RuntimeError, match="phasec0-observe-timeout"):
        asyncio.run(MODULE._observe_bounded(runtime, timeout_s=0.01))
    assert runtime.observe_calls == 1


class _RecoveringRuntime:
    def __init__(self) -> None:
        self.observe_calls = 0
        self.recover_calls = 0

    async def observe(self):
        self.observe_calls += 1
        if self.observe_calls == 1:
            await asyncio.sleep(3600)
        return _Observation("fresh-after-recover")

    async def recover(self):
        self.recover_calls += 1
        return object()


def test_post_action_observe_may_recover_plumbing_once_but_never_action():
    runtime = _RecoveringRuntime()
    observation = asyncio.run(
        MODULE._post_action_observe_with_one_recovery(
            runtime,
            observe_timeout_s=0.01,
            recover_timeout_s=0.1,
        )
    )
    assert observation.revision == "fresh-after-recover"
    assert runtime.observe_calls == 2
    assert runtime.recover_calls == 1


def test_c0_action_mapper_accepts_only_launch_and_home():
    home = MODULE._action_from_payload_c0({"op": "home"})
    launch = MODULE._action_from_payload_c0({"op": "launch_app", "bundle_id": "example.bundle"})
    assert type(home).__name__ == "Home"
    assert type(launch).__name__ == "LaunchApp"
    with pytest.raises(ValueError, match="phasec0-representative-op-not-allowed"):
        MODULE._action_from_payload_c0({"op": "tap_point", "x": 1, "y": 1})


def test_runtime_factory_is_lazy_and_constructs_without_device_io():
    runtime = MODULE._runtime_for_endpoint(
        identifier="paired-id",
        host="127.0.0.1",
        port=49152,
        runner_bundle_id="runner.bundle",
    )
    assert runtime is not None
    assert runtime._transport.snapshot().lifecycle.value == "DISCONNECTED"


class _Observation:
    def __init__(self, revision: str):
        self.revision = revision
        self.elements = ()
        self.screenshot = b""


class _Attempt:
    state = "succeeded"
    effect = "NONE"
    evidence = {"replayed": False}


def test_home_only_preflight_contract_is_narrow_and_no_live_enable():
    # Structural contract test: the mode is explicitly separate from the
    # broader representative workload and uses only the system Home behavior.
    assert MODULE.RETURN_HOME.behavior_id == "system:return-home"
    source = SCRIPT.read_text(encoding="utf-8")
    block = source[source.index("async def _collect_home_only_preflight"):
                   source.index("async def _collect_async_shadow_workload")]
    assert 'op="home"' in block
    assert "launch_app" not in block
    assert '"adaptive_live_apply": False' in block
    assert '"sequence_live_apply": False' in block
    assert "execute_skill" in block
    assert "replayed" in block
