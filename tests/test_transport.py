"""R3-02 deterministic transport lifecycle tests (no device attached).

Fakes replace the three upstream seams of ``IosTransport`` (device selection,
tunnel factory, WDA client factory) so every state transition, recreation, and
privacy property is exercised without usbmuxd, a tunnel, or a phone.
Device smoke is deferred to R3-08.
"""

import asyncio
import dataclasses
import itertools

import pytest
from pymobiledevice3.exceptions import WdaError
from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
from pymobiledevice3.usbmux import MuxDevice

from praxiom.ios_runtime.models import LifecycleState, TransportKind, WdaState
from praxiom.ios_runtime.transport import (
    DeviceNotFoundError,
    IosTransport,
    TransportClosedError,
    TransportStatus,
    TunnelUnavailableError,
    WdaUnreachableError,
    _default_wda_client_factory,
)

FAKE_UDID = "0123456789abcdef0123456789abcdef01234567"
_SESSIONS = itertools.count(1)


def run(coro):
    return asyncio.run(coro)


class FakeRsd:
    def __init__(self, in_process=True):
        self.is_in_process_tunnel = in_process
        self.udid = FAKE_UDID
        self.closed = False


class FakeRemoteRsd(RemoteServiceDiscoveryService):
    def __init__(self):
        self.connections = []

    async def create_service_connection(self, port):
        self.connections.append(port)
        return object()


def test_default_wda_client_keeps_remote_rsd_off_usbmux():
    provider = FakeRemoteRsd()
    client = _default_wda_client_factory(provider, 8100, 10.0)
    assert not isinstance(client.service_provider, RemoteServiceDiscoveryService)
    connection = run(client.service_provider.create_service_connection(8100))
    assert connection is not None
    assert provider.connections == [8100]


class FakeTunnel:
    def __init__(self, fail_open=False, in_process=True):
        self.rsd = FakeRsd(in_process=in_process)
        self.fail_open = fail_open
        self.open_calls = 0
        self.close_calls = 0

    async def aopen(self):
        self.open_calls += 1
        if self.fail_open:
            raise RuntimeError("tunnel handshake failed")
        return self.rsd

    async def aclose(self):
        self.close_calls += 1
        if self.rsd is not None:
            self.rsd.closed = True


class FakeWda:
    def __init__(self, harness=None, fail_status=False, fail_session=False):
        self.provider = None
        self.port = None
        self.timeout = None
        self.session_id = None
        # Live flags when wired to a Harness so tests can flip behavior
        # between lifecycle calls (e.g. connect fails, then recover succeeds).
        self.harness = harness
        self.fail_status = fail_status
        self.fail_session = fail_session
        self.calls = []

    @property
    def _status_fails(self):
        return self.harness.fail_status if self.harness else self.fail_status

    @property
    def _session_fails(self):
        return self.harness.fail_session if self.harness else self.fail_session

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def _require_session(self, session_id):
        """Mirror upstream's hard session-id precondition (no cached fallback).

        Upstream ``WdaServiceClient.get_window_size``/``send_keys``/``swipe``
        (pinned commit ec4ac06) raise ``WdaError("session_id is required")``
        when called without ``session_id`` — they do NOT fall back to the
        cached ``self.session_id`` — so this fake raises identically and
        session-less transport calls fail here exactly as they would on a
        real device instead of being silently masked.
        """
        if not session_id:
            raise WdaError("session_id is required")
        return session_id

    async def get_status(self):
        self._record("get_status")
        if self.harness and self.harness.status_hangs_before_ready > 0:
            self.harness.status_hangs_before_ready -= 1
            await asyncio.Future()
        if self.harness and self.harness.status_failures_before_ready > 0:
            self.harness.status_failures_before_ready -= 1
            raise ConnectionError("wda status probe not ready yet")
        if self._status_fails:
            raise ConnectionError("wda status probe lost")
        return {"status": 0}

    async def start_session(self, bundle_id=None):
        self._record("start_session", bundle_id=bundle_id)
        if self._session_fails:
            raise ConnectionError("wda session lost")
        self.session_id = f"session-{next(_SESSIONS)}"
        return self.session_id

    async def get_screenshot(self, session_id=None):
        self._record("get_screenshot", session_id=session_id)
        return b"<png-bytes>"

    async def get_source(self, session_id=None):
        self._record("get_source", session_id=session_id)
        return "<xml>source</xml>"

    async def _request_json(self, method, path, payload):
        self._record("_request_json", method, path, payload)
        if method == "GET" and path == "/wda/activeAppInfo":
            return {
                "value": {
                    "bundleId": "com.example.foreground",
                    "name": "Private App",
                    "pid": 1234,
                }
            }
        raise WdaError("unexpected endpoint", status_code=404)

    async def get_window_size(self, session_id=None):
        self._require_session(session_id)
        self._record("get_window_size", session_id=session_id)
        if self.harness and self.harness.stale_read_session_once:
            self.harness.stale_read_session_once = False
            raise WdaError("stale read session", status_code=404)
        return {"width": 390, "height": 844}

    async def swipe(self, x1, y1, x2, y2, duration=0.2, session_id=None):
        self._require_session(session_id)
        self._record("swipe", x1, y1, x2, y2, duration, session_id=session_id)
        if self.harness and self.harness.stale_mutation_session_once:
            self.harness.stale_mutation_session_once = False
            raise WdaError("stale mutation session", status_code=404)

    async def send_keys(self, text, session_id=None):
        self._require_session(session_id)
        self._record("send_keys", text, session_id=session_id)

    async def press_button(self, name, session_id=None):
        self._record("press_button", name, session_id=session_id)


class FakeRunnerHandle:
    def __init__(self):
        self.cancel_calls = 0
        self.await_calls = 0
        self._done = False

    def done(self):
        return self._done

    def result(self):
        return None

    def cancel(self):
        self.cancel_calls += 1
        self._done = True

    def __await__(self):
        async def wait():
            self.await_calls += 1
            return None

        return wait().__await__()


class FakeAppService:
    def __init__(self, harness, provider):
        self.harness = harness
        self.provider = provider

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

    async def launch_application(self, bundle_id):
        self.harness.app_launches.append((self.provider, bundle_id))


class Harness:
    """Wires IosTransport to fakes and records every upstream-boundary call."""

    def __init__(self, *, with_device=True, fail_open=False, fail_status=False,
                 fail_session=False, in_process=True, xctrunner_bundle_id=None,
                 status_failures_before_ready=0,
                 status_hangs_before_ready=0,
                 stale_read_session_once=False,
                 stale_mutation_session_once=False):
        self.select_udids = []
        self.tunnels = []
        self.wda_clients = []
        self.runner_starts = []
        self.runner_handles = []
        self.app_launches = []
        self.fail_open = fail_open
        self.fail_status = fail_status
        self.fail_session = fail_session
        self.status_failures_before_ready = status_failures_before_ready
        self.status_hangs_before_ready = status_hangs_before_ready
        self.stale_read_session_once = stale_read_session_once
        self.stale_mutation_session_once = stale_mutation_session_once

        device = MuxDevice(devid=1, serial=FAKE_UDID, connection_type="USB")

        async def select_device(*, udid=None, connection_type=None, usbmux_address=None):
            self.select_udids.append(udid)
            return device if with_device else None

        def tunnel_factory(udid, autopair):
            tunnel = FakeTunnel(fail_open=fail_open, in_process=in_process)
            self.tunnels.append(tunnel)
            return tunnel

        def wda_client_factory(provider, port, timeout):
            client = FakeWda(harness=self)
            client.provider = provider
            client.port = port
            client.timeout = timeout
            self.wda_clients.append(client)
            return client

        async def xctrunner_start(provider, bundle_id):
            self.runner_starts.append((provider, bundle_id))
            handle = FakeRunnerHandle()
            self.runner_handles.append(handle)
            return handle

        def app_service_factory(provider):
            return FakeAppService(self, provider)

        self.transport = IosTransport(
            udid=FAKE_UDID,
            xctrunner_bundle_id=xctrunner_bundle_id,
            select_device=select_device,
            tunnel_factory=tunnel_factory,
            wda_client_factory=wda_client_factory,
            xctrunner_start=xctrunner_start,
            app_service_factory=app_service_factory,
        )


# --- state transitions -------------------------------------------------------


def test_connect_reaches_ready_with_in_process_rsd():
    h = Harness()
    status = run(h.transport.connect())
    assert status == TransportStatus(
        LifecycleState.READY, TransportKind.RSD_USERSPACE, WdaState.READY, has_session=True
    )
    assert h.transport.snapshot() == status
    # WDA client is bound to the RSD the transport opened.
    assert h.wda_clients[0].provider is h.tunnels[0].rsd
    assert h.wda_clients[0].port == 8100
    assert h.select_udids == [FAKE_UDID]


def test_connect_native_rsd_classification():
    h = Harness(in_process=False)
    status = run(h.transport.connect())
    assert status.transport == TransportKind.RSD_NATIVE


def test_connect_bounds_xctrunner_configuration_startup(monkeypatch):
    """A hung TestConfig/create-start seam must not hang Runtime lifecycle."""
    import praxiom.ios_runtime.transport as transport_module

    h = Harness(fail_status=True, xctrunner_bundle_id="runner.bundle")
    cancelled = False

    async def never_returns(_provider, _bundle_id):
        nonlocal cancelled
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled = True
            raise

    h.transport._xctrunner_start = never_returns
    monkeypatch.setattr(transport_module, "_WDA_STARTUP_TIMEOUT_S", 0.01)

    with pytest.raises(WdaUnreachableError, match="runner could not be started"):
        run(h.transport.connect())
    assert cancelled is True
    assert h.transport.snapshot().lifecycle == LifecycleState.DEGRADED


def test_connect_bounds_hung_wda_probe_then_starts_configured_runner():
    h = Harness(
        xctrunner_bundle_id="runner.bundle",
        status_hangs_before_ready=1,
    )
    h.transport._timeout = 0.01

    status = run(h.transport.connect())

    assert status.lifecycle == LifecycleState.READY
    assert len(h.runner_starts) == 1
    assert [call[0] for call in h.wda_clients[0].calls[:3]] == [
        "get_status",
        "get_status",
        "start_session",
    ]


def test_connect_bounds_hung_wda_probe_without_runner():
    h = Harness(status_hangs_before_ready=1)
    h.transport._timeout = 0.01

    with pytest.raises(WdaUnreachableError, match="reachability probe failed"):
        run(h.transport.connect())

    assert h.transport.snapshot().lifecycle == LifecycleState.DEGRADED


def test_connect_without_device_raises_and_projects_disconnected():
    h = Harness(with_device=False)
    try:
        run(h.transport.connect())
        raise AssertionError("expected DeviceNotFoundError")
    except DeviceNotFoundError as exc:
        assert FAKE_UDID not in str(exc)
    assert h.transport.snapshot() == TransportStatus(
        LifecycleState.DISCONNECTED, TransportKind.NONE, WdaState.NONE, has_session=False
    )
    assert h.tunnels == [] and h.wda_clients == []


def test_connect_tunnel_failure_projects_disconnected():
    h = Harness(fail_open=True)
    try:
        run(h.transport.connect())
        raise AssertionError("expected TunnelUnavailableError")
    except TunnelUnavailableError:
        pass
    assert h.transport.snapshot().lifecycle == LifecycleState.DISCONNECTED
    assert h.wda_clients == []


def test_connect_wda_unreachable_projects_degraded():
    h = Harness(fail_status=True)
    try:
        run(h.transport.connect())
        raise AssertionError("expected WdaUnreachableError")
    except WdaUnreachableError as exc:
        assert FAKE_UDID not in str(exc)
    status = h.transport.snapshot()
    assert status.lifecycle == LifecycleState.DEGRADED
    assert status.transport == TransportKind.RSD_USERSPACE
    assert status.wda_state == WdaState.UNAVAILABLE
    # Reachability probe failed: no session was attempted.
    assert h.wda_clients[0].calls == [("get_status", (), {})]


def test_connect_session_failure_projects_degraded():
    h = Harness(fail_session=True)
    try:
        run(h.transport.connect())
        raise AssertionError("expected WdaUnreachableError")
    except WdaUnreachableError:
        pass
    status = h.transport.snapshot()
    assert status.lifecycle == LifecycleState.DEGRADED
    assert status.has_session is False


def test_connect_fast_path_skips_io_when_ready():
    h = Harness()
    run(h.transport.connect())
    probe = h.wda_clients[0].calls
    run(h.transport.connect())
    assert h.wda_clients[0].calls == probe
    assert len(h.tunnels) == 1 and h.tunnels[0].open_calls == 1
    assert h.select_udids == [FAKE_UDID]


def test_connect_reopens_after_upstream_tunnel_watcher_clears_rsd():
    h = Harness()
    run(h.transport.connect())
    old_tunnel = h.tunnels[0]

    # Upstream UserspaceRsdTunnel.aclose() sets .rsd=None when its background
    # watcher detects the outer transport dying. IosTransport must not keep
    # projecting READY from the stale WDA/session references after that.
    old_tunnel.rsd = None
    assert h.transport.snapshot().lifecycle == LifecycleState.DISCONNECTED

    status = run(h.transport.connect())

    assert status.lifecycle == LifecycleState.READY
    assert old_tunnel.close_calls == 1
    assert len(h.tunnels) == 2
    assert len(h.wda_clients) == 2
    assert h.select_udids == [FAKE_UDID, FAKE_UDID]


def test_connect_resumes_from_degraded_without_reopening_tunnel():
    h = Harness(fail_status=True)
    try:
        run(h.transport.connect())
    except WdaUnreachableError:
        pass
    h.fail_status = False
    status = run(h.transport.connect())
    assert status.lifecycle == LifecycleState.READY
    # The already-open tunnel and device selection were reused.
    assert len(h.tunnels) == 1 and h.tunnels[0].close_calls == 0
    assert h.select_udids == [FAKE_UDID]


def test_connect_starts_configured_xctrunner_when_wda_is_not_running():
    h = Harness(
        xctrunner_bundle_id="com.example.WebDriverAgentRunner.xctrunner",
        status_failures_before_ready=1,
    )

    status = run(h.transport.connect())

    assert status.lifecycle == LifecycleState.READY
    assert len(h.runner_starts) == 1
    provider, bundle_id = h.runner_starts[0]
    assert provider is h.tunnels[0].rsd
    assert bundle_id == "com.example.WebDriverAgentRunner.xctrunner"
    assert [c[0] for c in h.wda_clients[0].calls[:3]] == [
        "get_status", "get_status", "start_session"
    ]

    runner = h.runner_handles[0]
    run(h.transport.close())
    assert runner.cancel_calls == 1
    assert runner.await_calls == 1


def test_connect_does_not_start_configured_runner_when_wda_is_already_ready():
    h = Harness(xctrunner_bundle_id="com.example.WebDriverAgentRunner.xctrunner")

    assert run(h.transport.connect()).lifecycle == LifecycleState.READY
    assert h.runner_starts == []


def test_recreate_replaces_owned_xctrunner_task():
    h = Harness(
        xctrunner_bundle_id="com.example.WebDriverAgentRunner.xctrunner",
        status_failures_before_ready=1,
    )
    run(h.transport.connect())
    first = h.runner_handles[0]
    h.status_failures_before_ready = 1

    assert run(h.transport.recreate()).lifecycle == LifecycleState.READY

    assert first.cancel_calls == 1
    assert first.await_calls == 1
    assert len(h.runner_handles) == 2


def test_snapshot_is_pure_projection_before_connect():
    h = Harness()
    assert h.transport.snapshot() == TransportStatus(
        LifecycleState.DISCONNECTED, TransportKind.NONE, WdaState.NONE, has_session=False
    )
    assert h.select_udids == []  # snapshot performed no device I/O


# --- operation primitives -----------------------------------------------------


def test_primitives_route_through_owned_session():
    h = Harness()
    run(h.transport.connect())
    wda = h.wda_clients[0]
    session = wda.session_id

    assert run(h.transport.screenshot()) == b"<png-bytes>"
    assert run(h.transport.accessibility_source()) == "<xml>source</xml>"
    assert run(h.transport.active_application_info())["bundleId"] == "com.example.foreground"
    assert run(h.transport.screen_size()) == (390, 844)
    run(h.transport.tap_at_point(100, 200))
    run(h.transport.drag(10, 20, 300, 400, 0.5))
    run(h.transport.send_keys("hi"))
    run(h.transport.press_home())

    # One shared owned session; no extra session churn from primitives.
    assert wda.session_id == session
    tap = [c for c in wda.calls if c[0] == "swipe"]
    # tap_at_point composes a zero-length swipe (no upstream coordinate-tap).
    assert tap[0][1] == (100, 200, 100, 200, 0.05)
    assert [c[1] for c in wda.calls if c[0] == "swipe"][1] == (10, 20, 300, 400, 0.5)
    assert [c[1] for c in wda.calls if c[0] == "send_keys"] == [("hi",)]
    assert [c[1] for c in wda.calls if c[0] == "press_button"] == [("home",)]

    # Every session-capable primitive is pinned to the owned session id.
    # Home is intentionally different: omitting session_id makes upstream use
    # its global /wda/homescreen path, which is the reliable current-iOS Home
    # transition rather than the session-scoped pressButton endpoint.
    session_scoped = {
        "get_screenshot", "get_source", "get_window_size",
        "swipe", "send_keys",
    }
    scoped_calls = [c for c in wda.calls if c[0] in session_scoped]
    assert len(scoped_calls) == 6
    assert all(c[2].get("session_id") == session for c in scoped_calls)
    home_calls = [c for c in wda.calls if c[0] == "press_button"]
    assert len(home_calls) == 1
    assert home_calls[0][1] == ("home",)
    assert home_calls[0][2].get("session_id") is None

    # The fake enforces upstream's session-id precondition, so a transport
    # regression that drops session_id from those operations fails here exactly
    # as it would on a real device (WdaError) instead of passing silently.
    with pytest.raises(WdaError):
        run(wda.get_window_size())
    with pytest.raises(WdaError):
        run(wda.send_keys("x"))
    with pytest.raises(WdaError):
        run(wda.swipe(0, 0, 1, 1))


def test_session_scoped_read_404_invalidates_cache_without_retry():
    h = Harness(stale_read_session_once=True)
    run(h.transport.connect())
    wda = h.wda_clients[0]

    with pytest.raises(WdaError, match="stale read session"):
        run(h.transport.screen_size())

    assert wda.session_id is None
    assert h.transport.snapshot().lifecycle == LifecycleState.DEGRADED
    assert len([call for call in wda.calls if call[0] == "get_window_size"]) == 1
    assert len([call for call in wda.calls if call[0] == "start_session"]) == 1

    assert run(h.transport.connect()).lifecycle == LifecycleState.READY
    assert len([call for call in wda.calls if call[0] == "start_session"]) == 2
    assert run(h.transport.screen_size()) == (390, 844)


def test_session_scoped_mutation_404_invalidates_cache_without_replay():
    h = Harness(stale_mutation_session_once=True)
    run(h.transport.connect())
    wda = h.wda_clients[0]

    with pytest.raises(WdaError, match="stale mutation session"):
        run(h.transport.tap_at_point(10, 20))

    assert wda.session_id is None
    assert h.transport.snapshot().lifecycle == LifecycleState.DEGRADED
    assert len([call for call in wda.calls if call[0] == "swipe"]) == 1
    assert len([call for call in wda.calls if call[0] == "start_session"]) == 1

    # An explicit later reconnect may create a fresh session, but it never
    # replays the failed mutation.
    assert run(h.transport.connect()).lifecycle == LifecycleState.READY
    assert len([call for call in wda.calls if call[0] == "start_session"]) == 2
    assert len([call for call in wda.calls if call[0] == "swipe"]) == 1


def test_launch_app_preserves_owned_session():
    h = Harness()
    run(h.transport.connect())
    owned = h.wda_clients[0]
    session_before = owned.session_id

    run(h.transport.launch_app("com.example.app"))

    # CoreDevice app launch does not create a second WDA session; the owned
    # runtime session survives the launch.
    assert len(h.wda_clients) == 1
    assert owned.session_id == session_before
    assert h.app_launches == [(owned.provider, "com.example.app")]


def test_primitives_without_connect_raise_wda_unreachable():
    h = Harness()
    operations = [
        h.transport.screenshot,
        h.transport.accessibility_source,
        h.transport.screen_size,
        lambda: h.transport.tap_at_point(1, 2),
        lambda: h.transport.launch_app("com.example.app"),
        h.transport.press_home,
    ]
    for operation in operations:
        try:
            run(operation())
            raise AssertionError("expected WdaUnreachableError")
        except WdaUnreachableError:
            pass
    assert h.select_udids == [] and h.wda_clients == []


# --- recreation / recovery seam ------------------------------------------------


def test_recreate_replaces_all_plumbing_and_reselects_device():
    h = Harness()
    run(h.transport.connect())
    old_tunnel, old_client = h.tunnels[0], h.wda_clients[0]
    old_session = old_client.session_id
    old_calls = list(old_client.calls)

    status = run(h.transport.recreate())

    assert status.lifecycle == LifecycleState.READY
    assert old_tunnel.close_calls == 1 and old_tunnel.rsd.closed
    assert len(h.tunnels) == 2 and h.tunnels[1] is not old_tunnel
    assert len(h.wda_clients) == 2 and h.wda_clients[1] is not old_client
    # Device was reselected; the old WDA client sees no further calls.
    assert h.select_udids == [FAKE_UDID, FAKE_UDID]
    assert old_client.calls == old_calls
    assert h.wda_clients[1].session_id != old_session


def test_recreate_repairs_degraded_wda_and_reports_failure_state():
    h = Harness()
    run(h.transport.connect())
    h.fail_status = True
    try:
        run(h.transport.recreate())
        raise AssertionError("expected WdaUnreachableError")
    except WdaUnreachableError:
        pass
    status = h.transport.snapshot()
    assert status.lifecycle == LifecycleState.DEGRADED
    assert status.transport == TransportKind.RSD_USERSPACE
    assert status.has_session is False
    h.fail_status = False
    assert run(h.transport.recreate()).lifecycle == LifecycleState.READY


# --- session teardown / close ---------------------------------------------------


def test_close_session_drops_session_and_keeps_tunnel():
    h = Harness()
    run(h.transport.connect())
    old_session = h.wda_clients[0].session_id

    status = run(h.transport.close_session())

    assert status.lifecycle == LifecycleState.DEGRADED
    assert status.transport == TransportKind.RSD_USERSPACE
    assert status.has_session is False
    assert h.tunnels[0].close_calls == 0  # tunnel untouched
    assert run(h.transport.connect()).lifecycle == LifecycleState.READY
    assert h.wda_clients[1].session_id != old_session


def test_close_is_idempotent_and_owned_handles_only():
    h = Harness()
    run(h.transport.connect())
    tunnel = h.tunnels[0]

    first = run(h.transport.close())
    second = run(h.transport.close())

    assert first.lifecycle == LifecycleState.CLOSED
    assert second == first
    assert tunnel.close_calls == 1  # idempotent: closed exactly once
    for operation in (
        h.transport.connect,
        h.transport.recreate,
        lambda: h.transport.close_session(),
        h.transport.screenshot,
        h.transport.press_home,
    ):
        try:
            run(operation())
            raise AssertionError("expected TransportClosedError")
        except TransportClosedError:
            pass
    assert h.transport.snapshot() == TransportStatus(
        LifecycleState.CLOSED, TransportKind.NONE, WdaState.NONE, has_session=False
    )


# --- privacy -------------------------------------------------------------------


def _status_strings(status: TransportStatus) -> set[str]:
    values = [str(v) for v in dataclasses.astuple(status)]
    return {*values, str(status), repr(status)}


def test_status_output_contains_no_device_identifiers():
    h = Harness()
    run(h.transport.connect())
    for status in (h.transport.snapshot(), run(h.transport.close())):
        for rendered in _status_strings(status):
            assert FAKE_UDID not in rendered


def test_error_messages_contain_no_device_identifiers():
    missing = Harness(with_device=False)
    try:
        run(missing.transport.connect())
    except DeviceNotFoundError as exc:
        assert FAKE_UDID not in str(exc) and FAKE_UDID not in repr(exc)
    unreachable = Harness(fail_status=True)
    try:
        run(unreachable.transport.connect())
    except WdaUnreachableError as exc:
        assert FAKE_UDID not in str(exc) and FAKE_UDID not in repr(exc)
    closed = Harness()
    run(closed.transport.connect())
    run(closed.transport.close())
    try:
        run(closed.transport.connect())
    except TransportClosedError as exc:
        assert FAKE_UDID not in str(exc)
