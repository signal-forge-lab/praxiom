from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pymobiledevice3.services.dvt.testmanaged import xcuitest as upstream_xcuitest
from praxiom.ios_runtime.remote_pairing_xcuitest import (
    _NoCapabilityDvtProvider,
    _NoCapabilityTestManagerProvider,
    RemotePairingXCUITestService,
)
from praxiom.ios_runtime.wifi_tunnel import (
    RemotePairingRsdService,
    _default_rsd_factory,
)


def test_remote_pairing_rsd_factory_marks_only_wifi_provider_type():
    async def open_connection(*_args, **_kwargs):  # pragma: no cover - no I/O here
        raise AssertionError("must not connect")

    rsd = _default_rsd_factory(("::1", 1), open_connection, {})
    assert isinstance(rsd, RemotePairingRsdService)


def test_wifi_xctest_providers_skip_only_published_capability_exchange():
    provider = SimpleNamespace(product_version="26.0")
    dvt = _NoCapabilityDvtProvider(provider)
    tm = _NoCapabilityTestManagerProvider(provider)
    assert dvt.sent_capabilities is None
    assert tm.sent_capabilities is None
    assert dvt._service_name == dvt.SERVICE_NAME
    assert tm._service_name == tm.SERVICE_NAME


def test_wrapper_calls_upstream_run_under_scope_and_restores_globals(monkeypatch):
    original_dvt = upstream_xcuitest.InstrumentsDvtProvider
    original_tm = upstream_xcuitest._TestManagerProvider
    seen: dict[str, object] = {}

    async def fake_upstream_run(self, *args, **kwargs):
        seen["dvt"] = upstream_xcuitest.InstrumentsDvtProvider
        seen["tm"] = upstream_xcuitest._TestManagerProvider
        seen["args"] = args
        seen["kwargs"] = kwargs

    monkeypatch.setattr(upstream_xcuitest.XCUITestService, "run", fake_upstream_run)
    service = RemotePairingXCUITestService(SimpleNamespace())
    asyncio.run(service.run("cfg", timeout=12.5))

    assert seen["dvt"] is _NoCapabilityDvtProvider
    assert seen["tm"] is _NoCapabilityTestManagerProvider
    assert seen["args"] == ("cfg",)
    assert seen["kwargs"] == {"timeout": 12.5}
    assert upstream_xcuitest.InstrumentsDvtProvider is original_dvt
    assert upstream_xcuitest._TestManagerProvider is original_tm


def test_wrapper_restores_provider_globals_when_upstream_raises(monkeypatch):
    original_dvt = upstream_xcuitest.InstrumentsDvtProvider
    original_tm = upstream_xcuitest._TestManagerProvider

    async def fake_upstream_run(self, *args, **kwargs):
        raise RuntimeError("synthetic-upstream-failure")

    monkeypatch.setattr(upstream_xcuitest.XCUITestService, "run", fake_upstream_run)
    service = RemotePairingXCUITestService(SimpleNamespace())
    with pytest.raises(RuntimeError, match="synthetic-upstream-failure"):
        asyncio.run(service.run("cfg"))

    assert upstream_xcuitest.InstrumentsDvtProvider is original_dvt
    assert upstream_xcuitest._TestManagerProvider is original_tm
