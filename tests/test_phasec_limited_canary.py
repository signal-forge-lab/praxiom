from __future__ import annotations

import importlib.util
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phasec_limited_canary.py"
SPEC = importlib.util.spec_from_file_location("phasec_limited_canary", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_icon_validator_uses_roles_only():
    xml = """<App><XCUIElementTypeIcon label='private-a'/><Other name='private-b'/>
    <XCUIElementTypeIcon value='private-c'/></App>"""
    assert MODULE._count_icon_roles(xml) == 2


def test_live_recommendation_authorizes_only_cheap_observation_surface():
    context = MODULE.ValidationContext(
        effect="NONE",
        expected_anchor=MODULE.EXPECTED_HOME_ANCHOR,
        observed_labels=frozenset({MODULE.EXPECTED_HOME_ANCHOR}),
        confidence=1.0,
        high_risk=False,
        mismatch=False,
    )
    decision, recommendation = MODULE._live_recommendation(context, confidence=0.9)
    assert decision.sufficient is True
    assert decision.creates_revision is False
    assert recommendation.observation.method == "cheap-validate"
    assert recommendation.would_reduce_observe is True
    assert recommendation.would_reduce_actions is False
    applied = MODULE._authorize_observation_live(recommendation)
    assert applied.live_applied is True


def test_live_authorization_refuses_non_reduction():
    context = MODULE.ValidationContext(
        effect="NONE",
        expected_anchor=MODULE.EXPECTED_HOME_ANCHOR,
        observed_labels=frozenset(),
        confidence=1.0,
        high_risk=False,
        mismatch=False,
    )
    _decision, recommendation = MODULE._live_recommendation(context, confidence=0.9)
    assert recommendation.would_reduce_observe is False
    with pytest.raises(Exception):
        MODULE._authorize_observation_live(recommendation)


def test_home_anchor_projects_only_structural_roles():
    observation = SimpleNamespace(
        revision="r1",
        elements=(
            SimpleNamespace(role="XCUIElementTypeIcon", label="private"),
            SimpleNamespace(role="XCUIElementTypeButton", label="private"),
        ),
    )
    assert MODULE._home_anchor(observation) == (True, 1)


def test_runtime_factory_can_enable_shared_monitor_frame_projection(monkeypatch, tmp_path: Path):
    published = []

    class _Store:
        def __init__(self, state_root):
            assert Path(state_root) == tmp_path

        def publish(self, png, observation):
            published.append((png, observation))

    monkeypatch.setattr(MODULE, "LatestFrameStore", _Store)
    runtime, _transport = MODULE._runtime_and_transport(
        identifier="paired-id",
        host="127.0.0.1",
        port=49152,
        runner_bundle_id="runner.bundle",
        state_root=tmp_path,
        monitor_frame_projection=True,
    )
    assert runtime._engine._frame_sink is not None
    assert published == []


def test_promotion_readiness_fails_when_c0_is_not_complete(monkeypatch):
    monkeypatch.setattr(
        MODULE,
        "analyze_c0",
        lambda **_kwargs: {"c0_completion": {"ready": False}},
    )
    with pytest.raises(RuntimeError, match="phasec0-not-complete"):
        MODULE._promotion_readiness(None)


def test_endpoint_discovery_retries_read_only_bonjour_only(monkeypatch):
    calls = 0

    class _Service:
        remote_identifier = "paired-id"
        hostname = "device.local"
        port = 49152

        async def close(self):
            return None

    async def discover(*, bonjour_timeout):
        nonlocal calls
        calls += 1
        assert bonjour_timeout == MODULE.AUTO_DISCOVERY_TIMEOUT_S
        return [] if calls == 1 else [_Service()]

    monkeypatch.setattr(MODULE, "get_remote_pairing_tunnel_services", discover)
    identifier, host, port = asyncio.run(MODULE._discover_endpoint(attempts=2))
    assert (identifier, host, port) == ("paired-id", "device.local", 49152)
    assert calls == 2


def test_endpoint_discovery_stays_bounded(monkeypatch):
    calls = 0

    async def discover(*, bonjour_timeout):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(MODULE, "get_remote_pairing_tunnel_services", discover)
    with pytest.raises(RuntimeError, match="exactly-one-remote-paired-device-required"):
        asyncio.run(MODULE._discover_endpoint(attempts=3))
    assert calls == 3
