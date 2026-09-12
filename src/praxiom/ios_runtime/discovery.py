"""Transport-neutral USB + Wi-Fi Remote Pairing device discovery (Phase A / A6).

The pre-Phase-A Runtime preprobe was usbmux-gated: a Wi-Fi-paired iPhone with
no USB connection was reported as ``no device`` even though Remote Pairing
discovery was healthy. This module is the frozen D5/A6 repair seam: one
read-only, library-level discovery surface that enumerates both transports
behind injectable seams, deduplicates endpoints that belong to the same
device, and classifies the outcome into an explicit blocker taxonomy before
any tunnel is opened.

Enumeration sources (defaults use pinned upstream library APIs only — no
subprocess CLI parsing):

- USB: ``pymobiledevice3.usbmux.list_devices`` (read-only usbmux listing);
- Wi-Fi: ``pymobiledevice3.remote.tunnel_service.get_remote_pairing_tunnel_services``
  (RemotePairing over bonjour, verified against local pair records). The
  per-endpoint handshake is a pair-verify connection used only to resolve
  device identity; it performs no device mutation, and each probe connection
  is closed again before returning.

Blocker taxonomy (observable in ``DiscoveryReport``, never an exception):

- ``none`` — exactly one target selected (USB preferred, Wi-Fi otherwise);
- ``no-device`` — nothing visible on either transport;
- ``ambiguous-multiple-devices`` — more than one distinct device; live
  mutation requires exactly one selected target, so ambiguity fails closed;
- ``paired-wifi-visible`` — a paired Wi-Fi device is visible but the caller
  disabled the Wi-Fi transport, so it cannot be selected;
- ``runtime-tunnel-unavailable`` — a target was selected but establishing the
  Runtime RSD tunnel over it failed (set by the transport, not here, because
  this module never opens tunnels).

Deduplication: the same physical device appears as multiple endpoints — a
Wi-Fi iPhone answers on both IPv4 and IPv6. Endpoints are grouped by device
identity (usbmux serial on USB; Remote Pairing identifier on Wi-Fi), so
endpoint counts and device counts are reported separately and one device can
never be mistaken for an ambiguous multi-device environment.

Privacy: raw serials, Remote Pairing identifiers, and addresses never appear
in any report, error, or log produced here. Reports carry counts, the blocker
classification, and a process-local keyed fingerprint of the selected
identity (same construction as the Runtime's trace reason fingerprints:
equal identities map to equal fingerprints within one process, and nothing
raw is recoverable from retained output). Raw identities live only on the
in-process ``SelectedTarget`` handed to the Runtime transport, whose repr is
fingerprint-only by construction.

This module is discovery only: it selects nothing on its own, opens no
tunnels, and grants no mutation authority. The Runtime transport remains the
single selection-and-connection owner below the six-operation public
surface.
"""

from __future__ import annotations

import hashlib
import secrets
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

from pymobiledevice3 import usbmux
from pymobiledevice3.bonjour import DEFAULT_BONJOUR_TIMEOUT
from pymobiledevice3.remote.tunnel_service import get_remote_pairing_tunnel_services

__all__ = [
    "DeviceDiscovery",
    "DeviceTransport",
    "DiscoveryBlocker",
    "DiscoveryReport",
    "SelectedTarget",
    "UsbEndpoint",
    "WifiEndpoint",
    "privacy_fingerprint",
]


class DeviceTransport(StrEnum):
    """Which transport a selected target would be reached over."""

    USB = "usb"
    WIFI = "wifi"


class DiscoveryBlocker(StrEnum):
    """Why discovery could not select exactly one live-mutation target."""

    NONE = "none"
    NO_DEVICE = "no-device"
    AMBIGUOUS_MULTIPLE_DEVICES = "ambiguous-multiple-devices"
    PAIRED_WIFI_VISIBLE = "paired-wifi-visible"
    RUNTIME_TUNNEL_UNAVAILABLE = "runtime-tunnel-unavailable"


@dataclass(frozen=True)
class UsbEndpoint:
    """One usbmux-visible device endpoint (raw serial stays in-process)."""

    serial: str


@dataclass(frozen=True)
class WifiEndpoint:
    """One pair-verified RemotePairing endpoint of a paired device.

    ``identifier`` is the device's Remote Pairing identity (the dedupe key);
    ``hostname``/``port`` are the endpoint address. All three are raw and
    must never appear in retained output.
    """

    identifier: str
    hostname: str
    port: int


@dataclass(frozen=True)
class SelectedTarget:
    """The exactly-one device a live run may connect to.

    Raw endpoints are carried in-process for the Runtime transport only.
    The repr is deliberately fingerprint-only so an accidentally logged
    target can never leak a serial, identifier, or address.
    """

    transport: DeviceTransport
    fingerprint: str
    usb: UsbEndpoint | None = None
    wifi: WifiEndpoint | None = None

    def __repr__(self) -> str:  # privacy-by-construction
        return (
            f"SelectedTarget(transport={self.transport.value!r}, "
            f"fingerprint={self.fingerprint!r})"
        )


@dataclass(frozen=True)
class DiscoveryReport:
    """Privacy-safe projection of one discovery pass (counts/blocker only)."""

    usb_device_count: int
    wifi_device_count: int
    wifi_endpoint_count: int
    blocker: DiscoveryBlocker
    selected_fingerprint: str | None = None
    selected_transport: DeviceTransport | None = None


# Process-local keyed fingerprint key, generated once per process (same
# privacy construction as the Runtime's trace reason fingerprints): equal
# raw identities map to equal fingerprints within this process only, and no
# raw identity is recoverable from the digest.
_FINGERPRINT_KEY = secrets.token_bytes(16)


def privacy_fingerprint(raw_identity: str) -> str:
    """Keyed short fingerprint of a raw device identity (``dev#<hex>``)."""
    return "dev#" + hashlib.blake2s(
        raw_identity.encode("utf-8"), key=_FINGERPRINT_KEY, digest_size=8
    ).hexdigest()


async def _default_usb_devices() -> list[UsbEndpoint]:
    """Read-only usbmux listing normalized to endpoints (no mutation)."""
    return [UsbEndpoint(serial=device.serial) for device in await usbmux.list_devices()]


async def _default_wifi_pairing_targets() -> list[WifiEndpoint]:
    """Enumerate paired RemotePairing devices over bonjour (read-only probe).

    Uses the pinned upstream library API: each visible endpoint of every
    locally paired device is pair-verified (identity resolution only, no
    device mutation) and the probe connections are closed again before
    returning. The caller re-acquires services fresh when it later opens the
    actual tunnel.
    """
    services = await get_remote_pairing_tunnel_services(
        bonjour_timeout=DEFAULT_BONJOUR_TIMEOUT
    )
    endpoints = [
        WifiEndpoint(identifier=service.remote_identifier, hostname=service.hostname, port=service.port)
        for service in services
    ]
    for service in services:
        with suppress(Exception):
            await service.close()
    return endpoints


def _classify(
    usb_devices: list[UsbEndpoint],
    wifi_devices: dict[str, list[WifiEndpoint]],
    allow_wifi: bool,
) -> tuple[SelectedTarget | None, DiscoveryReport]:
    """Apply the frozen D5=A selection policy to one enumeration.

    USB is preferred when visible (the certified path); Wi-Fi is selected
    only when USB is absent, exactly one paired Wi-Fi device is visible, and
    the caller allows the Wi-Fi transport. Anything else fails closed into
    an explicit blocker instead of silently picking a device.
    """
    # Deterministic order: identity-sorted Wi-Fi devices.
    wifi_representatives = [wifi_devices[key][0] for key in sorted(wifi_devices)]
    blocker = DiscoveryBlocker.NONE
    target: SelectedTarget | None = None
    if len(usb_devices) > 1:
        blocker = DiscoveryBlocker.AMBIGUOUS_MULTIPLE_DEVICES
    elif usb_devices:
        endpoint = usb_devices[0]
        target = SelectedTarget(
            DeviceTransport.USB, privacy_fingerprint(endpoint.serial), usb=endpoint
        )
    elif not wifi_representatives:
        blocker = DiscoveryBlocker.NO_DEVICE
    elif len(wifi_representatives) > 1:
        blocker = DiscoveryBlocker.AMBIGUOUS_MULTIPLE_DEVICES
    elif not allow_wifi:
        blocker = DiscoveryBlocker.PAIRED_WIFI_VISIBLE
    else:
        endpoint = wifi_representatives[0]
        target = SelectedTarget(
            DeviceTransport.WIFI, privacy_fingerprint(endpoint.identifier), wifi=endpoint
        )
    report = DiscoveryReport(
        usb_device_count=len(usb_devices),
        wifi_device_count=len(wifi_representatives),
        wifi_endpoint_count=sum(len(endpoints) for endpoints in wifi_devices.values()),
        blocker=blocker,
        selected_fingerprint=target.fingerprint if target else None,
        selected_transport=target.transport if target else None,
    )
    return target, report


class DeviceDiscovery:
    """Read-only transport-neutral discovery over USB and Wi-Fi RemotePairing.

    Both enumeration seams are constructor-injectable for deterministic
    tests. ``probe()`` classifies without selecting; ``select()`` additionally
    applies the exact-one policy. Neither opens a tunnel or mutates a device.
    """

    def __init__(
        self,
        *,
        usb_devices: Callable[[], Any] | None = None,
        wifi_pairing_targets: Callable[[], Any] | None = None,
    ) -> None:
        self._usb_devices = usb_devices if usb_devices is not None else _default_usb_devices
        self._wifi_pairing_targets = (
            wifi_pairing_targets
            if wifi_pairing_targets is not None
            else _default_wifi_pairing_targets
        )

    async def probe(self, *, allow_wifi: bool = True) -> DiscoveryReport:
        """Read-only classification of the current transport visibility."""
        _, report = await self._select(allow_wifi=allow_wifi)
        return report

    async def select(
        self, *, allow_wifi: bool = True
    ) -> tuple[SelectedTarget | None, DiscoveryReport]:
        """Exact-one target selection (still read-only; tunnels stay closed).

        Returns ``(target, report)``; ``target`` is ``None`` whenever the
        blocker is anything but ``none`` — callers must fail closed on that.
        """
        return await self._select(allow_wifi=allow_wifi)

    async def _select(
        self, *, allow_wifi: bool
    ) -> tuple[SelectedTarget | None, DiscoveryReport]:
        usb_devices, wifi_devices = await self._enumerate()
        return _classify(usb_devices, wifi_devices, allow_wifi)

    async def _enumerate(
        self,
    ) -> tuple[list[UsbEndpoint], dict[str, list[WifiEndpoint]]]:
        """Enumerate both transports and deduplicate endpoints per device."""
        raw_usb = list(await self._usb_devices())
        usb: dict[str, UsbEndpoint] = {}
        for endpoint in raw_usb:
            if not isinstance(endpoint, UsbEndpoint):
                # Duck-typed mux devices (upstream ``MuxDevice``) carry .serial.
                endpoint = UsbEndpoint(serial=endpoint.serial)
            usb.setdefault(endpoint.serial, endpoint)
        raw_wifi = list(await self._wifi_pairing_targets())
        wifi: dict[str, list[WifiEndpoint]] = {}
        for endpoint in raw_wifi:
            wifi.setdefault(endpoint.identifier, []).append(endpoint)
        return list(usb.values()), wifi
