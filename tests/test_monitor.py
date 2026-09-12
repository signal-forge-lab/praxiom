from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import pytest

from praxiom.ios_runtime.models import LifecycleState, TransportKind, WdaState
from praxiom.ios_runtime.runtime import NativeIosRuntime
from praxiom.monitor.projection import (
    LatestFrameStore,
    MonitorSnapshotBuilder,
    frame_sink_from_env,
)
from praxiom.monitor.server import _loopback, create_server


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00"
)


class _Snapshot:
    lifecycle = LifecycleState.READY
    transport = TransportKind.RSD_USERSPACE
    wda_state = WdaState.READY


class _Transport:
    def __init__(self) -> None:
        self.screenshot_calls = 0

    async def connect(self) -> None:
        return None

    async def screenshot(self) -> bytes:
        self.screenshot_calls += 1
        return PNG_1X1

    async def accessibility_source(self) -> str:
        return '<XCUIElementTypeApplication x="0" y="0" width="1" height="1" />'

    async def screen_size(self) -> tuple[int, int]:
        return 1, 1

    async def tap_at_point(self, *_args, **_kwargs) -> None:
        return None

    async def drag(self, *_args, **_kwargs) -> None:
        return None

    async def send_keys(self, *_args, **_kwargs) -> None:
        return None

    async def press_home(self, *_args, **_kwargs) -> None:
        return None

    async def launch_app(self, *_args, **_kwargs) -> None:
        return None

    def snapshot(self) -> _Snapshot:
        return _Snapshot()

    async def close(self) -> None:
        return None


def _run(coro):
    return asyncio.run(coro)


def _write_run(root: Path) -> None:
    run_dir = root / "runs" / "run-monitor-test"
    run_dir.mkdir(parents=True)
    events = [
        {
            "schema_version": 1,
            "event_id": "evt-1",
            "seq": 1,
            "timestamp_utc": "2026-09-11T00:00:00.000Z",
            "event_type": "run.started",
            "phase": "run",
            "status": "running",
        },
        {
            "schema_version": 1,
            "event_id": "evt-2",
            "seq": 2,
            "timestamp_utc": "2026-09-11T00:00:01.000Z",
            "event_type": "runtime.observe",
            "phase": "observe",
            "status": "ok",
            "duration_ms": 12.5,
        },
        {
            "schema_version": 1,
            "event_id": "evt-3",
            "seq": 3,
            "timestamp_utc": "2026-09-11T00:00:02.000Z",
            "event_type": "policy.decision",
            "phase": "policy",
            "status": "ok",
            "policy_recommendation": "observe-cheap",
            "actual_policy": "observe-full",
            "payload": {"recommended": True},
        },
    ]
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )


def test_monitor_refresh_never_observes_or_changes_runtime_revision(tmp_path: Path):
    store = LatestFrameStore(tmp_path)
    transport = _Transport()
    runtime = NativeIosRuntime(transport=transport, frame_sink=store.publish)

    observation = _run(runtime.observe())
    revision = observation.revision
    calls = transport.screenshot_calls

    builder = MonitorSnapshotBuilder(state_root=tmp_path, frame_store=store)
    first = builder.build()
    second = builder.build()

    assert first["frame"]["available"] is True
    assert second["frame"]["revision"] == first["frame"]["revision"]
    assert _run(runtime.status()).current_revision == revision
    assert transport.screenshot_calls == calls


def test_frame_sink_failure_does_not_change_observe_semantics():
    transport = _Transport()

    def broken_sink(_png, _observation):
        raise OSError("monitor projection unavailable")

    runtime = NativeIosRuntime(transport=transport, frame_sink=broken_sink)
    observation = _run(runtime.observe())

    assert observation.revision
    assert transport.screenshot_calls == 1


def test_latest_frame_store_keeps_only_latest_frame_and_fingerprints_revision(
    tmp_path: Path,
):
    store = LatestFrameStore(tmp_path)
    transport = _Transport()
    runtime = NativeIosRuntime(transport=transport, frame_sink=store.publish)

    first = _run(runtime.observe())
    first_meta = store.read_metadata()
    second = _run(runtime.observe())
    second_meta = store.read_metadata()

    assert first.revision != second.revision
    assert first_meta is not None and second_meta is not None
    assert first_meta["revision"].startswith("fp:")
    assert second_meta["revision"].startswith("fp:")
    assert second_meta["revision"] != second.revision
    assert store.read_frame() == PNG_1X1
    assert sorted(path.name for path in (tmp_path / "monitor").iterdir()) == [
        "latest-frame.json",
        "latest-frame.png",
    ]


def test_snapshot_projects_authoritative_human_channel_without_touching_runtime(
    tmp_path: Path,
):
    _write_run(tmp_path)
    snapshot = MonitorSnapshotBuilder(state_root=tmp_path).build()

    assert snapshot["run"]["run_id"] == "run-monitor-test"
    assert snapshot["ai_state"]["policy_recommendation"] == "observe-cheap"
    assert snapshot["ai_state"]["actual_policy"] == "observe-full"
    assert snapshot["human_channel"]["available"] is True
    assert snapshot["human_channel"]["state"] == "READY"
    assert snapshot["human_channel"]["counts"]["teachings"] == 0
    assert [item["event_type"] for item in snapshot["activity"]][-1] == "policy.decision"


def test_snapshot_journal_window_is_bounded_to_recent_events(tmp_path: Path):
    run_dir = tmp_path / "runs" / "run-many-events"
    run_dir.mkdir(parents=True)
    with (run_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
        for seq in range(1, 301):
            handle.write(
                json.dumps(
                    {
                        "event_id": f"evt-{seq}",
                        "seq": seq,
                        "timestamp_utc": "2026-09-11T00:00:00.000Z",
                        "event_type": "runtime.observe",
                        "phase": "observe",
                        "status": "ok",
                    }
                )
                + "\n"
            )

    snapshot = MonitorSnapshotBuilder(state_root=tmp_path, event_limit=25).build()

    assert len(snapshot["activity"]) == 25
    assert snapshot["activity"][0]["seq"] == 276
    assert snapshot["activity"][-1]["seq"] == 300


def test_monitor_server_stays_device_passive_and_exposes_human_channel(tmp_path: Path):
    _write_run(tmp_path)
    store = LatestFrameStore(tmp_path)
    transport = _Transport()
    runtime = NativeIosRuntime(transport=transport, frame_sink=store.publish)
    _run(runtime.observe())

    server = create_server("127.0.0.1", 0, state_root=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        with urllib.request.urlopen(f"http://{host}:{port}/healthz") as response:
            health = json.load(response)
            assert health == {
                "ok": True,
                "name": "praxiom-monitor",
                "mode": "passive-device+human-channel",
            }
        with urllib.request.urlopen(f"http://{host}:{port}/api/snapshot") as response:
            payload = json.load(response)
            assert response.headers["Content-Security-Policy"]
            assert payload["frame"]["available"] is True

        with urllib.request.urlopen(f"http://{host}:{port}/api/frame") as response:
            assert response.headers["Content-Type"] == "image/png"
            assert response.read() == PNG_1X1

        with urllib.request.urlopen(f"http://{host}:{port}/praxiom-icon.png") as response:
            assert response.headers["Content-Type"] == "image/png"
            icon = response.read()
            assert len(icon) == 70_926
            assert hashlib.sha256(icon).hexdigest().upper() == (
                "7FBC4B69BBBD2002451B56BEEF367DBE44191B04DAA2DBF7BDDFF90BCFFD8E6D"
            )

        request = urllib.request.Request(
            f"http://{host}:{port}/api/human-teaching",
            data=json.dumps(
                {"text": "Synthetic teaching", "teaching_kind": "policy"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            created = json.load(response)
            assert created["ok"] is True
        with urllib.request.urlopen(f"http://{host}:{port}/api/human-channel") as response:
            human = json.load(response)
            assert human["counts"]["teachings"] == 1
        # Human Channel writes local learning evidence only. No extra Runtime
        # observe/device action is triggered by monitor refresh or Teaching.
        assert transport.screenshot_calls == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_non_loopback_bind_requires_explicit_opt_in(tmp_path: Path):
    with pytest.raises(ValueError, match="allow_lan"):
        create_server("0.0.0.0", 0, state_root=tmp_path)


def test_human_channel_write_boundary_recognizes_only_loopback_clients():
    assert _loopback("127.0.0.1") is True
    assert _loopback("::1") is True
    assert _loopback("localhost") is True
    assert _loopback("192.168.0.50") is False


def test_frame_projection_requires_explicit_opt_in(tmp_path: Path):
    assert frame_sink_from_env(tmp_path, environ={}) is None
    assert callable(
        frame_sink_from_env(
            tmp_path,
            environ={"PRAXIOM_MONITOR_FRAME_PROJECTION": "1"},
        )
    )


def test_static_ui_keeps_product_contract_and_uses_safe_dom_updates():
    html = files("praxiom.monitor.static").joinpath("index.html").read_text(encoding="utf-8")
    css = files("praxiom.monitor.static").joinpath("monitor.css").read_text(encoding="utf-8")
    js = files("praxiom.monitor.static").joinpath("monitor.js").read_text(encoding="utf-8")
    icon = files("praxiom.monitor.static").joinpath("praxiom-icon.png").read_bytes()

    assert "Current Screen" in html
    assert "AI State" in html
    assert "Human Channel" in html
    assert "Activity &amp; Diagnostics" in html
    assert "#111418" in css and "#6EA8D7" in css
    assert "min-height: 44px" in css
    assert "textContent" in js
    assert "innerHTML" not in js
    assert "/api/human-teaching" in js
    assert "answered" in html and "learned" in html
    assert "Asia/Tokyo" in js
    assert "formatJstSeconds" in js
    assert "/praxiom-icon.png" in html
    assert hashlib.sha256(icon).hexdigest().upper() == (
        "7FBC4B69BBBD2002451B56BEEF367DBE44191B04DAA2DBF7BDDFF90BCFFD8E6D"
    )
