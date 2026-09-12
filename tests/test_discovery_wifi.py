"""Phase A / A6 deterministic tests: transport-neutral discovery + Wi-Fi transport.

No device, usbmuxd, bonjour, tunnel, or phone is required: every upstream
boundary is replaced by deterministic fakes (enumeration seams, tunnel
factories, WDA client). These tests prove the A6 contract only — endpoint
deduplication, exact-one selection, blocker taxonomy, privacy-safe identity,
and the Wi-Fi-only Runtime path feeding the unchanged WDA stack — without
fabricating any physical evidence.
"""

import asyncio
import contextlib

import pytest
from pymobiledevice3.exceptions import PyMobileDevice3Exception, UserspaceTunnelUnavailableError
from pymobiledevice3.remote import tunnel_service
from pymobiledevice3.remote import userspace_tunnel as userspace
from pymobiledevice3.usbmux import MuxDevice

from praxiom.ios_runtime.discovery import (
    DeviceDiscovery,
    DeviceTransport,
    DiscoveryBlocker,
    UsbEndpoint,
    WifiEndpoint,
    privacy_fingerprint,
)
from praxiom.ios_runtime.models import LifecycleState, TransportKind, WdaState
from praxiom.ios_runtime.transport import (
    AmbiguousDeviceError,
    DeviceNotFoundError,
    DiscoveryUnavailableError,
    IosTransport,
    TransportClosedError,
    TransportStatus,
    TunnelUnavailableError,
)
from praxiom.ios_runtime.wifi_tunnel import RemotePairingUserspaceRsdTunnel

RAW_UDID = "0123456789abcdef0123456789abcdef01234567"
RAW_UDID_B = "fedcba9876543210fedcba9876543210fedcba98"
RAW_IDENT = "REMOTEPAIRING-IDENT-A"
RAW_IDENT_B = "REMOTEPAIRING-IDENT-B"
RAW_HOST_V4 = "192.168.7.21"
RAW_HOST_V6 = "fe80::9a:b0c:d0e:1f2"
WIFI_PORT = 50101
RAW_VALUES = (RAW_UDID, RAW_UDID_B, RAW_IDENT, RAW_IDENT_B, RAW_HOST_V4, RAW_HOST_V6)


def run(coro):
    return asyncio.run(coro)


# --- discovery seam ------------------------------------------------------------


def make_usb_seam(serials):
    async def usb_devices():
        return [UsbEndpoint(serial=s) for s in serials]

    return usb_devices


def make_wifi_seam(devices):
    """``devices`` maps identifier -> [(hostname, port), ...] endpoints."""

    async def wifi_pairing_targets():
        return [
            WifiEndpoint(identifier=identifier, hostname=host, port=port)
            for identifier, endpoints in devices.items()
            for host, port in endpoints
        ]

    return wifi_pairing_targets


def test_probe_dedupes_wifi_endpoints_to_one_device():
    discovery = DeviceDiscovery(
        usb_devices=make_usb_seam([]),
        wifi_pairing_targets=make_wifi_seam(
            {RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT), (RAW_HOST_V6, WIFI_PORT)]}
        ),
    )
    report = run(discovery.probe())
    assert report.blocker is DiscoveryBlocker.NONE
    assert report.usb_device_count == 0
    assert report.wifi_device_count == 1  # IPv4 + IPv6 -> one device
    assert report.wifi_endpoint_count == 2
    assert report.selected_transport is DeviceTransport.WIFI
    assert report.selected_fingerprint is not None
    assert report.selected_fingerprint.startswith("dev#")


def test_probe_no_device():
    discovery = DeviceDiscovery(
        usb_devices=make_usb_seam([]), wifi_pairing_targets=make_wifi_seam({})
    )
    report = run(discovery.probe())
    assert report.blocker is DiscoveryBlocker.NO_DEVICE
    assert report.selected_fingerprint is None and report.selected_transport is None


def test_probe_ambiguous_multiple_wifi_devices():
    discovery = DeviceDiscovery(
        usb_devices=make_usb_seam([]),
        wifi_pairing_targets=make_wifi_seam(
            {
                RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)],
                RAW_IDENT_B: [(RAW_HOST_V6, WIFI_PORT)],
            }
        ),
    )
    target, report = run(discovery.select())
    assert target is None
    assert report.blocker is DiscoveryBlocker.AMBIGUOUS_MULTIPLE_DEVICES
    assert report.wifi_device_count == 2


def test_probe_ambiguous_multiple_usb_devices():
    discovery = DeviceDiscovery(
        usb_devices=make_usb_seam([RAW_UDID, RAW_UDID_B]),
        wifi_pairing_targets=make_wifi_seam({}),
    )
    target, report = run(discovery.select())
    assert target is None
    assert report.blocker is DiscoveryBlocker.AMBIGUOUS_MULTIPLE_DEVICES
    assert report.usb_device_count == 2


def test_probe_paired_wifi_visible_when_wifi_disabled():
    discovery = DeviceDiscovery(
        usb_devices=make_usb_seam([]),
        wifi_pairing_targets=make_wifi_seam({RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)]}),
    )
    target, report = run(discovery.select(allow_wifi=False))
    assert target is None
    assert report.blocker is DiscoveryBlocker.PAIRED_WIFI_VISIBLE
    assert report.wifi_device_count == 1


def test_probe_usb_preferred_over_wifi():
    discovery = DeviceDiscovery(
        usb_devices=make_usb_seam([RAW_UDID]),
        wifi_pairing_targets=make_wifi_seam({RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)]}),
    )
    target, report = run(discovery.select())
    assert report.blocker is DiscoveryBlocker.NONE
    assert report.selected_transport is DeviceTransport.USB
    assert target is not None and target.usb is not None
    assert target.usb.serial == RAW_UDID  # raw identity lives in-process only
    assert target.transport is DeviceTransport.USB


def test_selected_target_repr_is_fingerprint_only():
    discovery = DeviceDiscovery(
        usb_devices=make_usb_seam([]),
        wifi_pairing_targets=make_wifi_seam({RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)]}),
    )
    target, _ = run(discovery.select())
    rendered = repr(target)
    for raw in (RAW_IDENT, RAW_HOST_V4):
        assert raw not in rendered
    assert target.fingerprint in rendered


def test_fingerprint_is_stable_within_process_and_hides_identity():
    first = privacy_fingerprint(RAW_IDENT)
    assert first == privacy_fingerprint(RAW_IDENT)
    assert first != privacy_fingerprint(RAW_IDENT_B)
    assert RAW_IDENT not in first


def test_probe_enumerates_even_when_only_usb_visible():
    wifi_seam = make_wifi_seam({RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)]})
    discovery = DeviceDiscovery(usb_devices=make_usb_seam([RAW_UDID]), wifi_pairing_targets=wifi_seam)
    report = run(discovery.probe())
    assert report.blocker is DiscoveryBlocker.NONE
    assert report.usb_device_count == 1 and report.wifi_device_count == 1


# --- transport: Wi-Fi-only path -------------------------------------------------


class FakeRsd:
    def __init__(self, in_process=True):
        self.is_in_process_tunnel = in_process


class FakeTunnelHandle:
    def __init__(self, rsd, fail_open=False):
        self.rsd = rsd
        self.fail_open = fail_open
        self.open_calls = 0
        self.close_calls = 0

    async def aopen(self):
        self.open_calls += 1
        if self.fail_open:
            raise RuntimeError("wifi tunnel handshake failed")
        return self.rsd

    async def aclose(self):
        self.close_calls += 1


class StubWda:
    def __init__(self, provider):
        self.provider = provider
        self.session_id = None

    async def get_status(self):
        return {"status": 0}

    async def start_session(self):
        self.session_id = "session-wifi"
        return self.session_id


class WifiHarness:
    """IosTransport with faked discovery, tunnels, and WDA (no device)."""

    def __init__(
        self,
        *,
        usb_serials=(),
        wifi_devices=None,
        wifi=True,
        fail_wifi_open=False,
        enumeration_error=False,
    ):
        self.usb_serials = list(usb_serials)
        self.wifi_devices = wifi_devices if wifi_devices is not None else {}
        self.usb_calls = 0
        self.wifi_calls = 0
        self.select_udids = []
        self.usb_tunnels = []
        self.wifi_tunnels = []
        self.wifi_targets = []
        self.wda_clients = []
        harness = self

        async def usb_devices():
            harness.usb_calls += 1
            if enumeration_error:
                raise RuntimeError("usbmux listing exploded")
            return [UsbEndpoint(serial=s) for s in harness.usb_serials]

        async def wifi_pairing_targets():
            harness.wifi_calls += 1
            return [
                WifiEndpoint(identifier=identifier, hostname=host, port=port)
                for identifier, endpoints in harness.wifi_devices.items()
                for host, port in endpoints
            ]

        async def select_device(*, udid=None, **kwargs):
            harness.select_udids.append(udid)
            if harness.usb_serials:
                return MuxDevice(devid=1, serial=harness.usb_serials[0], connection_type="USB")
            return None

        def tunnel_factory(udid, autopair):
            tunnel = FakeTunnelHandle(FakeRsd())
            harness.usb_tunnels.append(tunnel)
            return tunnel

        def wifi_tunnel_factory(target):
            tunnel = FakeTunnelHandle(FakeRsd(), fail_open=fail_wifi_open)
            harness.wifi_tunnels.append(tunnel)
            harness.wifi_targets.append(target)
            return tunnel

        def wda_client_factory(provider, port, timeout):
            client = StubWda(provider)
            harness.wda_clients.append(client)
            return client

        self.transport = IosTransport(
            wifi=wifi,
            discovery=DeviceDiscovery(
                usb_devices=usb_devices, wifi_pairing_targets=wifi_pairing_targets
            ),
            select_device=select_device,
            tunnel_factory=tunnel_factory,
            wifi_tunnel_factory=wifi_tunnel_factory,
            wda_client_factory=wda_client_factory,
        )


def test_connect_wifi_only_reaches_ready_without_usbmux():
    h = WifiHarness(
        usb_serials=[],
        wifi_devices={RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT), (RAW_HOST_V6, WIFI_PORT)]},
    )
    status = run(h.transport.connect())
    assert status == TransportStatus(
        LifecycleState.READY, TransportKind.RSD_USERSPACE, WdaState.READY, has_session=True
    )
    # usbmux is never consulted on the Wi-Fi-only path.
    assert h.select_udids == [] and h.usb_tunnels == []
    assert len(h.wifi_tunnels) == 1 and h.wifi_tunnels[0].open_calls == 1
    # The factory received the exactly-one selected target (raw identity
    # stays in-process; only the transport holds it).
    assert h.wifi_targets[0].wifi.identifier == RAW_IDENT
    assert h.wifi_targets[0].transport is DeviceTransport.WIFI
    # WDA runs on the RSD the Wi-Fi tunnel opened — same stack as USB.
    assert h.wda_clients[0].provider is h.wifi_tunnels[0].rsd
    report = h.transport.last_discovery()
    assert report.blocker is DiscoveryBlocker.NONE
    assert report.wifi_device_count == 1 and report.wifi_endpoint_count == 2
    assert report.selected_transport is DeviceTransport.WIFI


def test_wifi_tunnel_failure_classified_runtime_tunnel_unavailable():
    h = WifiHarness(
        usb_serials=[],
        wifi_devices={RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)]},
        fail_wifi_open=True,
    )
    with pytest.raises(TunnelUnavailableError):
        run(h.transport.connect())
    assert h.wda_clients == []
    assert h.transport.snapshot().lifecycle is LifecycleState.DISCONNECTED
    report = h.transport.last_discovery()
    assert report.blocker is DiscoveryBlocker.RUNTIME_TUNNEL_UNAVAILABLE


def test_connect_ambiguous_wifi_fails_closed_without_tunnel():
    h = WifiHarness(
        usb_serials=[],
        wifi_devices={
            RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)],
            RAW_IDENT_B: [(RAW_HOST_V6, WIFI_PORT)],
        },
    )
    with pytest.raises(AmbiguousDeviceError):
        run(h.transport.connect())
    assert h.wifi_tunnels == [] and h.wda_clients == []
    assert h.transport.snapshot().lifecycle is LifecycleState.DISCONNECTED
    assert h.transport.last_discovery().blocker is DiscoveryBlocker.AMBIGUOUS_MULTIPLE_DEVICES


def test_connect_multiple_usb_devices_fails_closed_without_usbmux_call():
    h = WifiHarness(usb_serials=[RAW_UDID, RAW_UDID_B])
    with pytest.raises(AmbiguousDeviceError):
        run(h.transport.connect())
    assert h.select_udids == [] and h.usb_tunnels == []
    report = h.transport.last_discovery()
    assert report.blocker is DiscoveryBlocker.AMBIGUOUS_MULTIPLE_DEVICES


def test_connect_no_devices_anywhere_raises_device_not_found():
    h = WifiHarness(usb_serials=[], wifi_devices={})
    with pytest.raises(DeviceNotFoundError):
        run(h.transport.connect())
    assert h.wifi_tunnels == [] and h.usb_tunnels == []
    assert h.transport.last_discovery().blocker is DiscoveryBlocker.NO_DEVICE


def test_wifi_disabled_surfaces_paired_wifi_visible_blocker():
    h = WifiHarness(
        usb_serials=[],
        wifi_devices={RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)]},
        wifi=False,
    )
    with pytest.raises(DeviceNotFoundError) as excinfo:
        run(h.transport.connect())
    assert "wi-fi" in str(excinfo.value)
    assert h.wifi_tunnels == []
    report = h.transport.last_discovery()
    assert report.blocker is DiscoveryBlocker.PAIRED_WIFI_VISIBLE
    assert report.wifi_device_count == 1


def test_usb_still_preferred_when_present():
    h = WifiHarness(
        usb_serials=[RAW_UDID],
        wifi_devices={RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)]},
    )
    status = run(h.transport.connect())
    assert status == TransportStatus(
        LifecycleState.READY, TransportKind.RSD_USERSPACE, WdaState.READY, has_session=True
    )
    assert h.select_udids == [None]
    assert len(h.usb_tunnels) == 1 and h.wifi_tunnels == []
    report = h.transport.last_discovery()
    assert report.blocker is DiscoveryBlocker.NONE
    assert report.selected_transport is DeviceTransport.USB


def test_discovery_enumeration_failure_wrapped_as_typed_error():
    h = WifiHarness(usb_serials=[], wifi_devices={}, enumeration_error=True)
    with pytest.raises(DiscoveryUnavailableError):
        run(h.transport.connect())
    assert h.transport.snapshot().lifecycle is LifecycleState.DISCONNECTED


def test_recreate_reselects_target_from_fresh_discovery():
    h = WifiHarness(usb_serials=[], wifi_devices={RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)]})
    run(h.transport.connect())
    # The paired device changes between runs; recreate must reselect rather
    # than reuse a stale selection.
    h.wifi_devices.clear()
    h.wifi_devices[RAW_IDENT_B] = [(RAW_HOST_V6, WIFI_PORT)]

    status = run(h.transport.recreate())

    assert status.lifecycle is LifecycleState.READY
    assert h.wifi_tunnels[0].close_calls == 1
    assert len(h.wifi_tunnels) == 2
    assert h.wifi_targets[1].wifi.identifier == RAW_IDENT_B
    assert h.transport.last_discovery().selected_transport is DeviceTransport.WIFI


def test_wifi_path_close_releases_tunnel_once():
    h = WifiHarness(usb_serials=[], wifi_devices={RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)]})
    run(h.transport.connect())
    status = run(h.transport.close())
    assert status.lifecycle is LifecycleState.CLOSED
    assert h.wifi_tunnels[0].close_calls == 1
    with pytest.raises(TransportClosedError):
        run(h.transport.connect())


def test_wifi_path_outputs_contain_no_raw_identity_or_addresses():
    h = WifiHarness(
        usb_serials=[],
        wifi_devices={RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT), (RAW_HOST_V6, WIFI_PORT)]},
    )
    run(h.transport.connect())
    rendered = [
        str(h.transport.last_discovery()),
        repr(h.transport.last_discovery()),
        repr(h.wifi_targets[0]),
        str(h.transport.snapshot()),
        repr(h.transport.snapshot()),
    ]
    ambiguous = WifiHarness(
        usb_serials=[],
        wifi_devices={
            RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)],
            RAW_IDENT_B: [(RAW_HOST_V6, WIFI_PORT)],
        },
    )
    with pytest.raises(AmbiguousDeviceError) as amb:
        run(ambiguous.transport.connect())
    rendered += [str(amb.value), repr(amb.value)]
    missing = WifiHarness(usb_serials=[], wifi_devices={})
    with pytest.raises(DeviceNotFoundError) as nf:
        run(missing.transport.connect())
    rendered += [str(nf.value), repr(nf.value)]
    unavailable = WifiHarness(
        usb_serials=[],
        wifi_devices={RAW_IDENT: [(RAW_HOST_V4, WIFI_PORT)]},
        fail_wifi_open=True,
    )
    with pytest.raises(TunnelUnavailableError) as tun:
        run(unavailable.transport.connect())
    rendered += [str(tun.value), repr(tun.value)]
    for text in rendered:
        for raw in RAW_VALUES:
            assert raw not in text


# --- Wi-Fi tunnel adapter -------------------------------------------------------


class FakeTun:
    def __init__(self):
        self.peer = None

    def set_peer(self, address):
        self.peer = address


class FakeTunnelClient:
    def __init__(self, tun):
        self.tun = tun

    async def wait_closed(self):
        # Park like a live transport; teardown cancels the watcher.
        await asyncio.sleep(3600)


class FakeTunnelResult:
    def __init__(self):
        self.client = FakeTunnelClient(FakeTun())
        self.address = "fd00:praxiom:fake::1"  # synthetic fake, never a real host
        self.port = 12345
        self.auxiliary_metadata = {"com.example": {"enabled": True}}


class FakeTunnelContext:
    def __init__(self, result, fail=False):
        self.result = result
        self.fail = fail
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        if self.fail:
            raise RuntimeError("remote pairing tunnel start failed")
        self.entered = True
        return self.result

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exited = True
        return False


class FakePairingService:
    def __init__(self, identifier, result=None, fail_tunnel=False):
        self.remote_identifier = identifier
        self.close_calls = 0
        self.tunnel_context = FakeTunnelContext(result or FakeTunnelResult(), fail=fail_tunnel)

    async def close(self):
        self.close_calls += 1

    def start_tcp_tunnel(self):
        return self.tunnel_context


class FakeDialPlane:
    def __init__(self, tun, address):
        self.tun = tun
        self.address = address
        self.entered = False
        self.exited = False

    async def dial(self, *args, **kwargs):
        raise AssertionError("not dialed in these tests")

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exited = True
        return False


class RecordingRsd:
    def __init__(self):
        self.ctor_args = None
        self.connected = False
        self.close_calls = 0

    async def connect(self):
        self.connected = True

    async def close(self):
        self.close_calls += 1


@contextlib.contextmanager
def userspace_globals():
    """Save/restore the process-global userspace-tunnel bookkeeping."""
    saved = (
        userspace._active_tunnel,
        userspace.USERSPACE_ACTIVE,
        tunnel_service.USE_USERSPACE_TUNNEL,
    )
    try:
        yield
    finally:
        (
            userspace._active_tunnel,
            userspace.USERSPACE_ACTIVE,
            tunnel_service.USE_USERSPACE_TUNNEL,
        ) = saved


async def _settle():
    # Let the transport-watcher task finish its cancellation.
    await asyncio.sleep(0)
    await asyncio.sleep(0)


def make_adapter(identifier, services, dial_planes, rsds):
    def dial_plane(tun, address):
        plane = FakeDialPlane(tun, address)
        dial_planes.append(plane)
        return plane

    def rsd_factory(address, open_connection=None, auxiliary_metadata=None):
        rsd = RecordingRsd()
        rsd.ctor_args = (address, open_connection, auxiliary_metadata)
        rsds.append(rsd)
        return rsd

    async def pairing_services():
        return services

    return RemotePairingUserspaceRsdTunnel(
        identifier,
        pairing_services=pairing_services,
        dial_plane=dial_plane,
        rsd_factory=rsd_factory,
    )


def test_adapter_picks_matching_identifier_and_closes_other_services():
    match_v4 = FakePairingService(RAW_IDENT)
    match_v6 = FakePairingService(RAW_IDENT)
    other = FakePairingService(RAW_IDENT_B)
    adapter = make_adapter(RAW_IDENT, [other, match_v4, match_v6], [], [])
    with userspace_globals():
        provider = run(adapter._acquire_provider())
        assert provider is match_v4
        assert match_v4.close_calls == 0
        assert match_v6.close_calls == 1  # duplicate endpoint of the same device
        assert other.close_calls == 1  # different device


def test_adapter_without_matching_identifier_fails_closed():
    only_other = FakePairingService(RAW_IDENT_B)
    adapter = make_adapter(RAW_IDENT, [only_other], [], [])
    with userspace_globals():
        with pytest.raises(UserspaceTunnelUnavailableError):
            run(adapter._acquire_provider())
        assert only_other.close_calls == 1


def test_adapter_establishes_userspace_flow_over_remote_pairing():
    service = FakePairingService(RAW_IDENT)
    result = service.tunnel_context.result
    dial_planes, rsds = [], []
    adapter = make_adapter(RAW_IDENT, [service], dial_planes, rsds)
    with userspace_globals():
        rsd = run(adapter.aopen())
        assert rsd is rsds[0] and rsd.connected
        # RSD is built on the tunnel endpoint with the in-process dialer and
        # the pairing handshake's auxiliary metadata (pinned upstream flow).
        assert rsd.ctor_args[0] == (result.address, result.port)
        # Bound-method identity is not stable across attribute accesses, so
        # prove the injected dialer belongs to the established dial plane.
        assert rsd.ctor_args[1].__self__ is dial_planes[0]
        assert rsd.ctor_args[1].__func__ is FakeDialPlane.dial
        assert rsd.ctor_args[2] is result.auxiliary_metadata
        assert dial_planes[0].entered and dial_planes[0].tun is result.client.tun
        assert result.client.tun.peer == result.address  # set_peer recorded
        # Process-global userspace bookkeeping mirrors upstream.
        assert userspace._active_tunnel is adapter and userspace.USERSPACE_ACTIVE is True
        assert tunnel_service.USE_USERSPACE_TUNNEL is True
        assert service.tunnel_context.entered and not service.tunnel_context.exited
        assert adapter.rsd is rsd

        run(adapter.aclose())

        assert userspace._active_tunnel is None and userspace.USERSPACE_ACTIVE is False
        assert tunnel_service.USE_USERSPACE_TUNNEL is False
        assert service.close_calls == 1
        assert rsds[0].close_calls == 1
        assert dial_planes[0].exited and service.tunnel_context.exited
        run(_settle())
        assert adapter._transport_watcher is None or adapter._transport_watcher.cancelled()


def test_adapter_failed_start_restores_userspace_flags():
    service = FakePairingService(RAW_IDENT, fail_tunnel=True)
    adapter = make_adapter(RAW_IDENT, [service], [], [])
    with userspace_globals():
        with pytest.raises(RuntimeError):
            run(adapter.aopen())
        assert tunnel_service.USE_USERSPACE_TUNNEL is False
        assert userspace._active_tunnel is None and userspace.USERSPACE_ACTIVE is False
        assert service.close_calls == 1  # provider released by the unwind
        assert adapter.rsd is None and adapter.tun is None
        run(adapter.aclose())  # idempotent after failure


def test_adapter_refuses_second_userspace_tunnel_in_process():
    service = FakePairingService(RAW_IDENT)
    adapter = make_adapter(RAW_IDENT, [service], [], [])
    with userspace_globals():
        userspace._active_tunnel = object()  # simulate an already-active tunnel
        with pytest.raises(PyMobileDevice3Exception):
            run(adapter.aopen())
        assert tunnel_service.USE_USERSPACE_TUNNEL is False
