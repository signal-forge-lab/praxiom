"""Narrow RemotePairing XCTest compatibility adapter.

Praxiom keeps the pinned upstream ``pymobiledevice3`` XCTest implementation as
the implementation authority.  This module does **not** copy or fork
``XCUITestService.run``.  It only scopes one observed Wi-Fi compatibility
difference: the RemotePairing DTX providers omit the published-capabilities
exchange that can stall before WebDriverAgent startup on the attached device.

The upstream module constructs its provider classes inside ``run()``, so the
smallest non-fork adapter is a process-scoped provider substitution around the
unchanged upstream call.  The substitution is:

* used only by the RemotePairing transport marker selected in ``transport``;
* serialized per event loop;
* restored in ``finally`` even when upstream raises/cancels;
* unrelated to Runtime actions and never retries/replays a mutation.

When the pinned upstream revision changes, re-audit whether this compatibility
seam is still required before carrying it forward.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from pymobiledevice3.services.dvt.testmanaged import xcuitest as _up

__all__ = ["RemotePairingXCUITestService"]


_PATCH_LOCK: asyncio.Lock | None = None
_PATCH_LOCK_LOOP: asyncio.AbstractEventLoop | None = None


class _NoCapabilityDvtProvider(_up.InstrumentsDvtProvider):
    """Upstream DVT provider with only the capability exchange disabled."""

    def __init__(self, lockdown: Any) -> None:
        super().__init__(lockdown)
        self.sent_capabilities = None


class _NoCapabilityTestManagerProvider(_up._TestManagerProvider):
    """Upstream testmanager provider with only capability exchange disabled."""

    def __init__(self, lockdown: Any) -> None:
        super().__init__(lockdown)
        self.sent_capabilities = None


def _patch_lock() -> asyncio.Lock:
    """Return a lock bound to the current loop (tests may create many loops)."""
    global _PATCH_LOCK, _PATCH_LOCK_LOOP
    loop = asyncio.get_running_loop()
    if _PATCH_LOCK is None or _PATCH_LOCK_LOOP is not loop:
        _PATCH_LOCK = asyncio.Lock()
        _PATCH_LOCK_LOOP = loop
    return _PATCH_LOCK


@asynccontextmanager
async def _remote_pairing_provider_scope() -> AsyncIterator[None]:
    """Temporarily substitute provider constructors for one upstream run."""
    async with _patch_lock():
        original_dvt = _up.InstrumentsDvtProvider
        original_tm = _up._TestManagerProvider
        _up.InstrumentsDvtProvider = _NoCapabilityDvtProvider
        _up._TestManagerProvider = _NoCapabilityTestManagerProvider
        try:
            yield
        finally:
            _up.InstrumentsDvtProvider = original_dvt
            _up._TestManagerProvider = original_tm


class RemotePairingXCUITestService(_up.XCUITestService):
    """Call upstream XCTest unchanged under the narrow provider scope."""

    async def run(self, *args: Any, **kwargs: Any) -> None:
        async with _remote_pairing_provider_scope():
            await super().run(*args, **kwargs)
