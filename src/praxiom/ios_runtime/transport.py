"""Upstream transport/session lifecycle for Native iOS Runtime v0 (R3-02).

Device plumbing built directly on unmodified upstream ``pymobiledevice3``
(pinned commit ``ec4ac06a850a6a884ca778350621f354faf347c6``):

- transport-neutral device discovery (Phase A / A6): a read-only
  ``DeviceDiscovery`` seam that enumerates usbmux devices and Wi-Fi
  RemotePairing devices, deduplicates endpoints per device, and applies the
  frozen D5=A exact-one selection policy (USB preferred; Wi-Fi only when
  USB is absent, exactly one paired device is visible, and the Wi-Fi
  transport is enabled);
- the normal iOS 17+ USB path via ``PreferredRsdTunnel`` (in-process
  ``UserspaceRsdTunnel`` on non-macOS hosts — no separate persistent
  ``tunneld`` process and no root);
- the Wi-Fi-only path (D5=A) via the in-process
  ``RemotePairingUserspaceRsdTunnel`` adapter, which acquires its provider
  over RemotePairing instead of the usbmux-gated lockdown path and then
  runs the identical userspace RSD/WDA stack;
- WDA reachability and session lifecycle via upstream ``WdaServiceClient``.

The Runtime slices (R3-03 observation, R3-04 executor, R3-05 recovery) are the
intended consumers. They consume this surface through fakes injected at the
upstream seams of ``IosTransport.__init__`` (``select_device``,
``tunnel_factory``, ``wda_client_factory``, plus the Phase A ``discovery``
and ``wifi_tunnel_factory`` seams); no seam exists below this module.

v0 transport scope: iOS 17+ in-process RSD is the only supported path; the
``LOCKDOWN`` transport kind of the public contract stays unimplemented for v0
(deferred until a pre-iOS-17 target is actually required).

Selection policy (D5=A, exact-one for live mutation): a pinned ``udid``
keeps the certified usbmux-only behavior. With ``udid=None`` the transport
runs transport-neutral discovery: one USB device (or a pinned serial) uses
the unchanged usbmux + ``PreferredRsdTunnel`` path; with USB absent and
exactly one paired Wi-Fi device visible, the Wi-Fi RemotePairing userspace
tunnel is used. Multiple visible devices, no device at all, a visible
paired Wi-Fi device while the Wi-Fi transport is disabled, and a selected
target whose tunnel cannot be established are surfaced through the typed
errors below and the privacy-safe ``last_discovery()`` blocker report
(``no-device`` / ``ambiguous-multiple-devices`` / ``paired-wifi-visible`` /
``runtime-tunnel-unavailable``). Discovery and tunnels never form a second
mutation authority: everything stays plumbing below the Runtime's six
public operations.

Downstream async primitive surface (consumed by R3-03/R3-04 through fakes)
--------------------------------------------------------------------------

Lifecycle / plumbing:

- ``snapshot() -> TransportStatus`` — synchronous, side-effect-free projection
  of tracked state (never performs device I/O, never exposes identifiers).
- ``connect() -> TransportStatus`` — establish missing plumbing: usbmux device
  selection -> in-process RSD tunnel -> WDA reachability probe (``get_status``)
  -> WDA session (``start_session``). Fast path: no I/O when already READY;
  resumes from partial plumbing without tearing healthy pieces down.
- ``recreate() -> TransportStatus`` — the recover() entry point: tear down all
  owned plumbing and re-establish from scratch (device reselection included).
  Knows nothing about actions, so it can never replay one.
- ``close_session()`` — discard the owned WDA client and session (upstream has
  no DELETE /session primitive; server-side sessions simply expire). Tunnel
  and device selection are kept.
- ``close()`` — idempotent; releases exactly the handles this transport
  created (tunnel, WDA client/session) and nothing else.

Operation primitives (each requires established plumbing and auto-ensures the
owned WDA session; coordinates are WDA logical points — conversion from the
public full-screen screenshot-pixel space belongs to the observation/executor
layers, never to the caller). Every session-capable upstream primitive is
called with the owned session id passed explicitly: upstream hard-requires
``session_id`` for ``get_window_size``/``send_keys``/``swipe`` (no cached-id
fallback), and the remaining primitives are pinned too so no device I/O
silently leaves the owned session:

- ``screenshot() -> bytes`` — full-screen PNG bytes (``get_screenshot``).
- ``accessibility_source() -> str`` — accessibility XML tree (``get_source``).
- ``screen_size() -> tuple[int, int]`` — ``(width, height)`` in WDA logical
  points (``get_window_size``).
- ``tap_at_point(x, y)`` — tap at a point; composed as a zero-length
  ``swipe`` because upstream exposes no dedicated coordinate-tap endpoint.
- ``drag(x1, y1, x2, y2, duration)`` — press-drag-release (``swipe``).
- ``send_keys(text)`` — type into the focused element (``send_keys``).
- ``press_home()`` — hardware Home button (``press_button("home")``).
- ``launch_app(bundle_id)`` — activate/launch by bundle id only (no human
  display-name resolution exists in v0) through upstream
  ``AppServiceService.launch_application(bundle_id)`` on the current RSD
  provider. This leaves the owned WDA session untouched.

Failure modes (R3-05 classifies effects from these):

- lifecycle methods raise typed ``TransportError`` subclasses —
  ``DeviceNotFoundError``, ``AmbiguousDeviceError``,
  ``DiscoveryUnavailableError``, ``TunnelUnavailableError``,
  ``WdaUnreachableError``, ``TransportClosedError`` — with static,
  identifier-free messages;
- operation primitives propagate raw upstream failures: ``WdaError`` for
  definitive WDA-level failures, and connection-class errors
  (``ConnectionError``/``OSError``/``TimeoutError``) for ambiguous in-flight
  failures where the request may already have applied — those must never be
  automatically replayed by higher layers. A session-scoped WDA 404 clears
  only the local cached session id so health stops projecting READY; the
  failing request still propagates unchanged and is never retried here.

Privacy: ``TransportStatus`` and every error message contain only state
enums/flags — raw UDIDs, pair records, screen text, and action payloads never
appear in any status-like output of this module.

One userspace tunnel exists per process (PyTCP stack is a process-global
singleton); ``recreate()`` therefore always closes the previous tunnel before
opening the next. Lifecycle methods (``connect``/``recreate``/``close``/
``close_session``) serialize on one asyncio lock; operation primitives are
lock-free because the Runtime serializes operations.
"""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Any, Callable

from pymobiledevice3 import usbmux
from pymobiledevice3.exceptions import WdaError
from pymobiledevice3.remote.core_device.app_service import AppServiceService
from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel
from pymobiledevice3.services.dvt.testmanaged.xcuitest import TestConfig, XCUITestService
from pymobiledevice3.services.wda import DEFAULT_WDA_PORT, WdaServiceClient

from praxiom.ios_runtime.discovery import (
    DeviceDiscovery,
    DeviceTransport,
    DiscoveryBlocker,
    DiscoveryReport,
    SelectedTarget,
)
from praxiom.ios_runtime.models import LifecycleState, TransportKind, WdaState
from praxiom.ios_runtime.wifi_tunnel import RemotePairingUserspaceRsdTunnel
from praxiom.ios_runtime.wifi_tunnel import RemotePairingRsdService
from praxiom.ios_runtime.remote_pairing_xcuitest import RemotePairingXCUITestService

__all__ = [
    "AmbiguousDeviceError",
    "DeviceNotFoundError",
    "DiscoveryUnavailableError",
    "IosTransport",
    "TransportClosedError",
    "TransportError",
    "TransportStatus",
    "TunnelUnavailableError",
    "WdaUnreachableError",
]

# Tap composed as a zero-length drag; WDA needs a small non-zero duration.
_TAP_DURATION_S = 0.05
_WDA_STARTUP_TIMEOUT_S = 30.0
_WDA_STARTUP_POLL_S = 0.1


class TransportError(Exception):
    """Base class of transport plumbing failures (no device side effect)."""


class DeviceNotFoundError(TransportError):
    """No usable device: usbmux lists no match and Wi-Fi has no selection."""


class AmbiguousDeviceError(TransportError):
    """Discovery sees multiple devices; exactly one target is required."""


class DiscoveryUnavailableError(TransportError):
    """Transport-neutral enumeration itself failed before classification."""


class TunnelUnavailableError(TransportError):
    """The in-process RSD tunnel could not be established."""


class WdaUnreachableError(TransportError):
    """WDA did not answer a reachability probe or create a session."""


class TransportClosedError(TransportError):
    """The transport is closed; only snapshot() remains usable."""


@dataclass(frozen=True)
class TransportStatus:
    """Privacy-safe transport projection consumed by the Runtime status."""

    lifecycle: LifecycleState
    transport: TransportKind
    wda_state: WdaState
    has_session: bool


def _default_tunnel_factory(udid: str | None, autopair: bool) -> Any:
    # Construction is synchronous; only aopen()/aclose() are async.
    return PreferredRsdTunnel(serial=udid, autopair=autopair)


def _default_wifi_tunnel_factory(target: SelectedTarget) -> Any:
    # D5=A Wi-Fi path: in-process RemotePairing userspace RSD tunnel for the
    # exactly-one selected paired target. Same aopen()/aclose() handle
    # contract as the USB tunnel, so everything downstream is shared.
    return RemotePairingUserspaceRsdTunnel(target.wifi.identifier)


class _RsdWdaProviderAdapter:
    """Keep WDA traffic on the active RSD dialer instead of falling back to usbmux.

    The pinned upstream ``WdaServiceClient`` special-cases
    ``RemoteServiceDiscoveryService`` and reconnects through usbmux. That is
    valid for its historical USB path but breaks Praxiom's Wi-Fi-only RSD
    transport. A tiny duck-typed wrapper deliberately avoids that type check
    and delegates the one method WDA needs back to the already-established
    RSD provider.
    """

    def __init__(self, provider: RemoteServiceDiscoveryService) -> None:
        self._provider = provider

    async def create_service_connection(self, port: int) -> Any:
        return await self._provider.create_service_connection(port)


def _default_wda_client_factory(provider: Any, port: int, timeout: float) -> Any:
    wda_provider = (
        _RsdWdaProviderAdapter(provider)
        if isinstance(provider, RemoteServiceDiscoveryService)
        else provider
    )
    return WdaServiceClient(service_provider=wda_provider, port=port, timeout=timeout)


async def _default_xctrunner_start(provider: Any, bundle_id: str) -> asyncio.Task[None]:
    config = await TestConfig.create_for(provider, runner_bundle_id=bundle_id)
    service = (
        RemotePairingXCUITestService(provider)
        if isinstance(provider, RemotePairingRsdService)
        else XCUITestService(provider)
    )
    return asyncio.create_task(
        service.run(config),
        name="praxiom-wda-xctrunner",
    )


class IosTransport:
    """Owner of exactly one device/tunnel/WDA plumbing stack.

    The transport owns only the resources it created itself (the tunnel handle
    and the WDA client/session); ``close()`` releases those and nothing else.
    """

    def __init__(
        self,
        udid: str | None = None,
        *,
        wda_port: int = DEFAULT_WDA_PORT,
        timeout: float = 10.0,
        autopair: bool = True,
        xctrunner_bundle_id: str | None = None,
        wifi: bool = True,
        select_device: Callable[..., Any] = usbmux.select_device,
        tunnel_factory: Callable[..., Any] = _default_tunnel_factory,
        wda_client_factory: Callable[..., Any] = _default_wda_client_factory,
        xctrunner_start: Callable[..., Any] = _default_xctrunner_start,
        app_service_factory: Callable[..., Any] = AppServiceService,
        discovery: DeviceDiscovery | None = None,
        wifi_tunnel_factory: Callable[..., Any] | None = None,
    ) -> None:
        """``udid=None`` enables transport-neutral exact-one selection (A6).

        With ``udid=None`` the transport selects through ``discovery``:
        USB preferred, Wi-Fi RemotePairing only when USB is absent and
        exactly one paired device is visible (and ``wifi=True``). A pinned
        ``udid`` keeps the certified usbmux-only behavior unchanged.

        The keyword seams replace upstream calls in deterministic tests:
        ``select_device(udid=...) -> MuxDevice | None``,
        ``tunnel_factory(udid, autopair) -> aopen()/aclose() handle``,
        ``wda_client_factory(provider, port, timeout) -> WDA client``,
        ``discovery`` (a ``DeviceDiscovery`` with fake enumeration seams),
        and ``wifi_tunnel_factory(selected_target) -> aopen()/aclose()
        handle`` for the Wi-Fi path.
        """
        self._udid = udid
        self._wda_port = wda_port
        self._timeout = timeout
        self._autopair = autopair
        self._xctrunner_bundle_id = xctrunner_bundle_id
        self._wifi = wifi
        self._select_device = select_device
        self._tunnel_factory = tunnel_factory
        self._wda_client_factory = wda_client_factory
        self._xctrunner_start = xctrunner_start
        self._app_service_factory = app_service_factory
        self._discovery = discovery if discovery is not None else DeviceDiscovery()
        self._wifi_tunnel_factory = (
            wifi_tunnel_factory
            if wifi_tunnel_factory is not None
            else _default_wifi_tunnel_factory
        )

        self._closed = False
        self._mux_device: Any | None = None
        self._tunnel: Any | None = None
        self._rsd: Any | None = None
        self._kind = TransportKind.NONE
        self._wda: Any | None = None
        self._wda_reachable = False
        self._xctrunner_task: Any | None = None
        self._selection: SelectedTarget | None = None
        self._last_report: DiscoveryReport | None = None
        self._lifecycle_lock = asyncio.Lock()

    # --- lifecycle ---------------------------------------------------------

    def snapshot(self) -> TransportStatus:
        """Project tracked state without any device I/O."""
        if self._closed:
            return TransportStatus(
                LifecycleState.CLOSED, TransportKind.NONE, WdaState.NONE, has_session=False
            )
        if self._tunnel is None or self._tunnel_lost_rsd():
            return TransportStatus(
                LifecycleState.DISCONNECTED, TransportKind.NONE, WdaState.NONE, has_session=False
            )
        if not self._wda_reachable or self._wda is None:
            return TransportStatus(
                LifecycleState.DEGRADED, self._kind, WdaState.UNAVAILABLE, has_session=False
            )
        if not self._wda.session_id:
            return TransportStatus(
                LifecycleState.DEGRADED, self._kind, WdaState.UNAVAILABLE, has_session=False
            )
        return TransportStatus(
            LifecycleState.READY, self._kind, WdaState.READY, has_session=True
        )

    def last_discovery(self) -> DiscoveryReport | None:
        """Privacy-safe report of the latest discovery-driven selection.

        ``None`` until a discovery-driven connect/recreate ran (a pinned
        ``udid`` keeps the certified usbmux-only path and never discovers).
        Counts, blocker classification, and a keyed fingerprint only — no
        raw serials, identifiers, or addresses by construction.
        """
        return self._last_report

    async def connect(self) -> TransportStatus:
        """Establish missing plumbing; no-op fast path when already READY."""
        if self._closed:
            raise TransportClosedError("transport is closed")
        async with self._lifecycle_lock:
            return await self._connect_locked()

    async def recreate(self) -> TransportStatus:
        """Tear down all owned plumbing and re-establish it from scratch.

        This is the recover() entry point: it reselects the device, reopens the
        tunnel, and rebuilds the WDA session. It never replays actions.
        """
        if self._closed:
            raise TransportClosedError("transport is closed")
        async with self._lifecycle_lock:
            await self._teardown_locked()
            return await self._connect_locked()

    async def close_session(self) -> TransportStatus:
        """Discard the owned WDA client/session; keep device and tunnel."""
        if self._closed:
            raise TransportClosedError("transport is closed")
        async with self._lifecycle_lock:
            self._drop_wda()
            return self.snapshot()

    async def close(self) -> TransportStatus:
        """Idempotently release every handle this transport created."""
        async with self._lifecycle_lock:
            await self._teardown_locked()
            self._closed = True
            return self.snapshot()

    # --- operation primitives ----------------------------------------------

    async def screenshot(self) -> bytes:
        """Full-screen screenshot as PNG bytes."""
        return await self._session_scoped_call("get_screenshot")

    async def accessibility_source(self) -> str:
        """Accessibility tree as an XML string."""
        return await self._session_scoped_call("get_source")

    async def active_application_info(self) -> dict[str, Any]:
        """Return WDA's current foreground-application metadata in-process.

        This is a read-only transport primitive below the frozen Runtime
        operation surface.  It intentionally uses WDA's global
        ``/wda/activeAppInfo`` endpoint so a stale cached XCTest session does
        not turn a foreground check into an action retry.  Callers must keep
        identity values in-process and project only bounded boolean/structural
        evidence into durable telemetry.
        """
        wda = self._require_wda()
        data = await asyncio.wait_for(
            wda._request_json("GET", "/wda/activeAppInfo", None),
            timeout=self._timeout,
        )
        value = data.get("value") if isinstance(data, dict) else None
        if not isinstance(value, dict):
            raise WdaError("WDA did not return active application info")
        return dict(value)

    async def screen_size(self) -> tuple[int, int]:
        """Screen dimensions in WDA logical points as (width, height)."""
        size = await self._session_scoped_call("get_window_size")
        return int(size["width"]), int(size["height"])

    async def tap_at_point(self, x: int, y: int) -> None:
        """Tap at WDA logical point (x, y); composed as a zero-length swipe."""
        await self._session_scoped_call("swipe", x, y, x, y, _TAP_DURATION_S)

    async def drag(
        self, x1: int, y1: int, x2: int, y2: int, duration: float
    ) -> None:
        """Press-drag-release between WDA logical points over ``duration`` s."""
        await self._session_scoped_call("swipe", x1, y1, x2, y2, duration)

    async def send_keys(self, text: str) -> None:
        """Type ``text`` into the currently focused element."""
        await self._session_scoped_call("send_keys", text)

    async def press_home(self) -> None:
        """Return to the Home screen through upstream's global Home endpoint."""
        wda = await self._session()
        # Deliberately omit session_id. pymobiledevice3 routes this exact form
        # to /wda/homescreen; the session-scoped /wda/pressButton path can
        # acknowledge "home" while leaving the foreground app unchanged.
        await wda.press_button("home")

    async def launch_app(self, bundle_id: str) -> None:
        """Activate/launch the app with ``bundle_id`` without replacing WDA session."""
        self._require_wda()
        async with self._app_service_factory(self._rsd) as service:
            await service.launch_application(bundle_id)

    # --- internal ----------------------------------------------------------

    async def _connect_locked(self) -> TransportStatus:
        if self._tunnel is not None and self._tunnel_lost_rsd():
            # Upstream userspace tunnel watchers tear their own RSD down when
            # the outer transport dies. Drop our now-stale tracked plumbing so
            # the next connect can rediscover/reopen it; never replay actions.
            await self._teardown_locked()
        if self._is_ready():
            return self.snapshot()
        if self._tunnel is None:
            if self._udid is not None:
                # Certified pinned-USB selection: no transport-neutral
                # discovery, unchanged usbmux-gated behavior.
                tunnel = await self._open_usb_tunnel_locked()
            else:
                if self._selection is None:
                    self._selection = await self._resolve_selection_locked()
                if self._selection.transport is DeviceTransport.USB:
                    tunnel = await self._open_usb_tunnel_locked()
                else:  # D5=A Wi-Fi-only path (exact-one paired target)
                    tunnel = self._wifi_tunnel_factory(self._selection)
            try:
                rsd = await tunnel.aopen()
            except Exception as exc:
                if self._last_report is not None:
                    self._last_report = replace(
                        self._last_report,
                        blocker=DiscoveryBlocker.RUNTIME_TUNNEL_UNAVAILABLE,
                    )
                raise TunnelUnavailableError("rsd tunnel could not be established") from exc
            self._tunnel = tunnel
            self._rsd = rsd
            self._kind = (
                TransportKind.RSD_USERSPACE
                if getattr(rsd, "is_in_process_tunnel", False)
                else TransportKind.RSD_NATIVE
            )
        if self._wda is None:
            self._wda = self._wda_client_factory(self._rsd, self._wda_port, self._timeout)
            self._wda_reachable = False
        if not self._wda_reachable:
            try:
                # Upstream's HTTP read path can wait indefinitely even when
                # WdaServiceClient was constructed with a request timeout.
                # Bound the lifecycle reachability probe here so a wedged WDA
                # can fall through to the already-certified xctrunner startup
                # path instead of hanging the whole Runtime. This is plumbing
                # only: no action exists to retry or replay at this point.
                await asyncio.wait_for(
                    self._wda.get_status(), timeout=self._timeout
                )
            except Exception as exc:
                if self._xctrunner_bundle_id is None:
                    raise WdaUnreachableError("wda reachability probe failed") from exc
                try:
                    if self._xctrunner_task is None:
                        self._xctrunner_task = await asyncio.wait_for(
                            self._xctrunner_start(
                                self._rsd, self._xctrunner_bundle_id
                            ),
                            timeout=_WDA_STARTUP_TIMEOUT_S,
                        )
                    deadline = asyncio.get_running_loop().time() + _WDA_STARTUP_TIMEOUT_S
                    while True:
                        if self._xctrunner_task.done():
                            self._xctrunner_task.result()
                            raise RuntimeError("xctrunner exited before WDA became reachable")
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            raise TimeoutError("WDA startup timed out")
                        try:
                            await asyncio.wait_for(
                                self._wda.get_status(),
                                timeout=min(self._timeout, remaining),
                            )
                        except Exception:
                            if asyncio.get_running_loop().time() >= deadline:
                                raise TimeoutError("WDA startup timed out")
                            await asyncio.sleep(_WDA_STARTUP_POLL_S)
                            continue
                        break
                except Exception as runner_exc:
                    raise WdaUnreachableError("wda runner could not be started") from runner_exc
            self._wda_reachable = True
        if not self._wda.session_id:
            try:
                await self._wda.start_session()
            except Exception as exc:
                raise WdaUnreachableError("wda session could not be created") from exc
        return self.snapshot()

    async def _open_usb_tunnel_locked(self) -> Any:
        """usbmux selection + ``PreferredRsdTunnel`` handle (USB path)."""
        if self._mux_device is None:
            self._mux_device = await self._select_device(udid=self._udid)
            if self._mux_device is None:
                raise DeviceNotFoundError("no matching usbmux device available")
        return self._tunnel_factory(self._udid, self._autopair)

    async def _resolve_selection_locked(self) -> SelectedTarget:
        """Run read-only transport-neutral discovery and enforce exact-one.

        Fail-closed mapping of the discovery blockers: ambiguity raises
        ``AmbiguousDeviceError``; no usable target raises
        ``DeviceNotFoundError`` (with the paired-wifi-visible case stated
        explicitly when the Wi-Fi transport is disabled); enumeration
        failures surface as ``DiscoveryUnavailableError`` rather than being
        misreported as "no device".
        """
        try:
            target, report = await self._discovery.select(allow_wifi=self._wifi)
        except Exception as exc:
            raise DiscoveryUnavailableError(
                "transport-neutral device discovery could not enumerate transports"
            ) from exc
        self._last_report = report
        if target is None:
            if report.blocker is DiscoveryBlocker.AMBIGUOUS_MULTIPLE_DEVICES:
                raise AmbiguousDeviceError(
                    "multiple candidate devices visible; exactly one target is required"
                )
            if report.blocker is DiscoveryBlocker.PAIRED_WIFI_VISIBLE:
                raise DeviceNotFoundError(
                    "no usbmux device available; a paired wi-fi device is visible"
                    " but the wi-fi transport is disabled"
                )
            raise DeviceNotFoundError("no matching usbmux device available")
        return target

    async def _teardown_locked(self) -> None:
        if self._xctrunner_task is not None:
            self._xctrunner_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._xctrunner_task
        self._xctrunner_task = None
        if self._tunnel is not None:
            with suppress(Exception):
                await self._tunnel.aclose()
        self._tunnel = None
        self._rsd = None
        self._kind = TransportKind.NONE
        self._drop_wda()
        self._mux_device = None
        self._selection = None  # recreate() reselects from scratch

    def _drop_wda(self) -> None:
        # Upstream WdaServiceClient holds no closeable connection between
        # requests (each request opens and closes its own service connection),
        # so teardown is a reference drop of the owned client and session.
        self._wda = None
        self._wda_reachable = False

    def _tunnel_lost_rsd(self) -> bool:
        """Detect an upstream tunnel watcher teardown without device I/O."""
        tunnel = self._tunnel
        return tunnel is not None and hasattr(tunnel, "rsd") and tunnel.rsd is None

    def _is_ready(self) -> bool:
        return (
            self._tunnel is not None
            and not self._tunnel_lost_rsd()
            and self._wda is not None
            and self._wda_reachable
            and bool(self._wda.session_id)
        )

    def _require_wda(self) -> Any:
        if self._closed:
            raise TransportClosedError("transport is closed")
        if self._wda is None or not self._wda_reachable:
            raise WdaUnreachableError("wda plumbing is not established")
        return self._wda

    async def _session(self) -> Any:
        wda = self._require_wda()
        if not wda.session_id:
            await wda.start_session()
        return wda

    async def _session_scoped_call(
        self, method_name: str, *args: Any
    ) -> Any:
        """Invoke one session-scoped WDA operation without replaying it.

        A cached session id is only local bookkeeping. WDA can invalidate the
        backing XCTest application independently and then return HTTP 404 for
        a session-scoped request. When that happens, clear only the cached
        session id so ``snapshot()`` stops projecting READY and a later,
        explicit ``connect()`` may establish a fresh session.

        The failing request is always propagated unchanged and is never
        retried here. This is important for mutation calls such as swipe/type:
        Praxiom must not replay an action whose effect is not known.
        """
        wda = await self._session()
        method = getattr(wda, method_name)
        try:
            return await method(*args, session_id=wda.session_id)
        except WdaError as exc:
            if getattr(exc, "status_code", None) == 404:
                wda.session_id = None
            raise
