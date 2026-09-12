"""In-process RemotePairing/userspace RSD tunnel adapter (Phase A / A6, D5=A).

Why this exists: the pinned upstream ``UserspaceRsdTunnel`` (commit
``ec4ac06a850a6a884ca778350621f354faf347c6``) acquires its tunnel provider
via ``_create_no_root_tunnel_provider``, which always opens a lockdown
connection over usbmux first. On a Wi-Fi-only host (usbmux lists nothing)
that raises before upstream's own RemotePairing fallback is ever reached,
which is exactly the observed 2026-09-09 failure: discovery healthy, Wi-Fi
Runtime establishment broken.

The frozen D5=A repair is a small in-process adapter inside ``ios_runtime``
that keeps one Runtime-owned transport stack:

- USB visible -> unchanged upstream usbmux + ``PreferredRsdTunnel`` path;
- USB absent, exactly one paired Wi-Fi target -> RemotePairing provider
  (``get_remote_pairing_tunnel_services``) -> in-process userspace RSD
  tunnel -> the same existing WDA/AppService Runtime primitives.

``RemotePairingUserspaceRsdTunnel`` subclasses the upstream handle and
re-implements only ``_aopen_locked`` with exactly one difference: the
provider is acquired over RemotePairing instead of the usbmux-gated
lockdown path. Everything after provider acquisition — the userspace
PyTCP tunnel, the per-RSD dial plane, the ``RemoteServiceDiscoveryService``
construction, the process-global userspace-tunnel bookkeeping, and the
whole teardown — is the pinned upstream establishment flow, inherited or
mirrored verbatim so the Wi-Fi path converges on the identical RSD/WDA
lifecycle the USB path uses.

Constraints honored (design freeze + handoff):

- no external tunneld process/service dependency anywhere in this path;
- no second mutation authority: this is transport plumbing below the
  six-operation Runtime surface, feeding the same WDA/AppService stack;
- no historical-product or external-harness fallback of any kind;
- identifiers/addresses stay in-process; nothing here logs or retains them
  (task names and errors are identifier-free by construction).

Deterministic tests inject the three constructor seams
(``pairing_services``, ``dial_plane``, ``rsd_factory``) and never touch real
networking or the PyTCP stack; no physical evidence is fabricated.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, suppress
from typing import Any, Callable

from pymobiledevice3.bonjour import DEFAULT_BONJOUR_TIMEOUT
from pymobiledevice3.exceptions import PyMobileDevice3Exception, UserspaceTunnelUnavailableError
from pymobiledevice3.remote import tunnel_service
from pymobiledevice3.remote import userspace_tunnel as _userspace
from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.remote.tunnel_service import get_remote_pairing_tunnel_services
from pymobiledevice3.remote.userspace_tunnel import UserspaceDialPlane, UserspaceRsdTunnel

__all__ = ["RemotePairingRsdService", "RemotePairingUserspaceRsdTunnel"]


class RemotePairingRsdService(RemoteServiceDiscoveryService):
    """Marker type for Praxiom's direct RemotePairing Wi-Fi RSD provider.

    The marker lets the XCTest startup seam apply the empirically required
    Wi-Fi-only DTX compatibility path without changing USB/native RSD behavior.
    It adds no device I/O and changes none of RemoteServiceDiscoveryService's
    protocol semantics.
    """

    pass


def _default_pairing_services(bonjour_timeout: float) -> Callable[[], Any]:
    """Bound read-only provider acquisition over RemotePairing (library API)."""

    async def _acquire() -> Any:
        return await get_remote_pairing_tunnel_services(bonjour_timeout=bonjour_timeout)

    return _acquire


def _default_rsd_factory(
    address: Any, open_connection: Any, auxiliary_metadata: Any
) -> Any:
    return RemotePairingRsdService(
        address, open_connection=open_connection, auxiliary_metadata=auxiliary_metadata
    )


class RemotePairingUserspaceRsdTunnel(UserspaceRsdTunnel):
    """Userspace RSD tunnel whose provider is a Wi-Fi RemotePairing service.

    Same handle contract as upstream ``UserspaceRsdTunnel`` (``aopen()`` ->
    connected RSD, ``aclose()`` idempotent teardown): the Runtime transport
    treats it exactly like the USB tunnel handle, so WDA reachability,
    session lifecycle, xctrunner startup, and recovery keep working
    unchanged over Wi-Fi. One userspace tunnel per process still applies
    (PyTCP stack singleton, enforced by the inherited/shared guard).

    ``identifier`` is the selected target's Remote Pairing identifier from
    discovery; it is used only to pick the matching provider and is never
    retained anywhere.
    """

    def __init__(
        self,
        identifier: str,
        *,
        bonjour_timeout: float = DEFAULT_BONJOUR_TIMEOUT,
        pairing_services: Callable[[], Any] | None = None,
        dial_plane: Callable[[Any, Any], Any] = UserspaceDialPlane,
        rsd_factory: Callable[..., Any] = _default_rsd_factory,
    ) -> None:
        super().__init__(serial=None, autopair=True)
        self._identifier = identifier
        self._bonjour_timeout = bonjour_timeout
        self._pairing_services = (
            pairing_services
            if pairing_services is not None
            else _default_pairing_services(bonjour_timeout)
        )
        self._dial_plane = dial_plane
        self._rsd_factory = rsd_factory

    async def _aopen_locked(self) -> Any:
        # Mirrors pinned upstream UserspaceRsdTunnel._aopen_locked with the
        # provider acquisition swapped for the RemotePairing path (no usbmux
        # device is required or consulted). If upstream establishment
        # changes at a future pin, this body must be re-audited against it.
        if _userspace._active_tunnel is not None:
            raise PyMobileDevice3Exception(
                "a userspace tunnel is already active in this process (PyTCP's stack is a "
                "process-global singleton; only one userspace tunnel per process is supported)"
            )
        tunnel_service.USE_USERSPACE_TUNNEL = True
        stack = AsyncExitStack()
        try:
            provider = await self._acquire_provider()
            stack.push_async_callback(provider.close)
            tunnel_result = await stack.enter_async_context(provider.start_tcp_tunnel())
            self.tun = tunnel_result.client.tun
            self.tun.set_peer(tunnel_result.address)
            dial_plane = await stack.enter_async_context(
                self._dial_plane(self.tun, tunnel_result.address)
            )
            rsd = self._rsd_factory(
                (tunnel_result.address, tunnel_result.port),
                open_connection=dial_plane.dial,
                auxiliary_metadata=tunnel_result.auxiliary_metadata,
            )
            stack.push_async_callback(rsd.close)
            await rsd.connect()
        except BaseException:
            await stack.aclose()
            tunnel_service.USE_USERSPACE_TUNNEL = False
            self.tun = None
            raise
        self._exit_stack = stack
        self.rsd = rsd
        _userspace._active_tunnel = self
        _userspace.USERSPACE_ACTIVE = True
        self._transport_watcher = asyncio.create_task(
            self._watch_transport_closed(tunnel_result.client),
            name="praxiom-wifi-rsd-transport-watcher",  # identifier-free by design
        )
        return rsd

    async def _acquire_provider(self) -> Any:
        """Pick this target's RemotePairing provider; close every other probe.

        Endpoint multiplicity (IPv4 + IPv6 of the same device) resolves to
        one provider; a vanished device surfaces as
        ``UserspaceTunnelUnavailableError`` so the transport can fail closed
        with the ``runtime-tunnel-unavailable`` blocker instead of guessing.
        """
        services = list(await self._pairing_services())
        provider = None
        for service in services:
            if provider is None and getattr(service, "remote_identifier", None) == self._identifier:
                provider = service
                continue
            with suppress(Exception):
                await service.close()
        if provider is None:
            raise UserspaceTunnelUnavailableError(
                "no paired remote-pairing device matched the selected target"
            )
        return provider
