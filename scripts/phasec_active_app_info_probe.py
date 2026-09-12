"""Read-only Phase C probe for a cheaper generic foreground-app signal.

This probe never mutates the device. It establishes the normal Praxiom WDA
transport, then checks whether the attached WebDriverAgent exposes an
``activeAppInfo`` endpoint. Returned application identity values are never
printed or persisted; only endpoint support, latency, and response-key names
are reported.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from phasec0_direct_wifi_shadow_workload import (  # noqa: E402
    _discover_bundles,
    _observe_bounded,
)
from phasec_limited_canary import (  # noqa: E402
    _discover_endpoint,
    _runtime_and_transport,
)


async def _probe_endpoint(wda: Any, path: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        data = await asyncio.wait_for(
            wda._request_json("GET", path, None),  # integration-edge probe only
            timeout=10.0,
        )
    except Exception as exc:
        return {
            "supported": False,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "error_class": type(exc).__name__,
        }

    latency_ms = (time.perf_counter() - started) * 1000.0
    value = data.get("value") if isinstance(data, dict) else None
    value_keys = sorted(str(key) for key in value) if isinstance(value, dict) else []
    return {
        "supported": True,
        "latency_ms": round(latency_ms, 3),
        "value_kind": type(value).__name__,
        "value_keys": value_keys,
        "identity_values_persisted": False,
    }


async def _run() -> dict[str, Any]:
    identifier, host, port = await _discover_endpoint()
    _app_bundle, runner_bundle = await _discover_bundles(identifier, host, port)
    runtime, transport = _runtime_and_transport(
        identifier=identifier,
        host=host,
        port=port,
        runner_bundle_id=runner_bundle,
        monitor_frame_projection=True,
    )
    try:
        observation = await _observe_bounded(runtime)
        if not observation.revision:
            raise RuntimeError("fresh-observation-required")
        wda = await transport._session()  # integration-edge probe only
        session_id = str(getattr(wda, "session_id", "") or "")
        if not session_id:
            raise RuntimeError("wda-session-required")
        global_result = await _probe_endpoint(wda, "/wda/activeAppInfo")
        session_result = await _probe_endpoint(
            wda, f"/session/{session_id}/wda/activeAppInfo"
        )
        return {
            "status": "completed",
            "mutation_count": 0,
            "global": global_result,
            "session_scoped": session_result,
            "privacy": {
                "app_identity_persisted": False,
                "raw_response_persisted": False,
            },
        }
    finally:
        await runtime.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm-device-read", action="store_true")
    args = parser.parse_args()
    if not args.confirm_device_read:
        print(json.dumps({"status": "refused", "reason": "confirmation-required"}))
        return 2
    runner = asyncio.Runner(
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None
    )
    with runner:
        result = runner.run(_run())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
