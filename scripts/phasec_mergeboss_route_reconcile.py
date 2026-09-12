"""Read-only reconciliation after an ambiguous Merge Boss route action.

This script performs no device mutation.  It reconnects to the current device,
captures one fresh observation, and emits only bounded structural/boolean state
needed to decide whether the previous navigation action took effect.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from phasec0_direct_wifi_shadow_workload import _discover_bundles, _observe_bounded  # noqa: E402
from phasec_limited_canary import _discover_endpoint, _home_anchor, _runtime_and_transport  # noqa: E402
from phasec_mergeboss_entry_target_probe import (  # noqa: E402
    ACCOUNT_KEYWORDS,
    MERGE_BOSS_KEYWORDS,
    MERGE_BOSS_LABELS,
    PLAY_KEYWORDS,
    PLAY_LABELS,
    _project_target,
)
from praxiom.ios_runtime.foreground import inspect_active_application_info  # noqa: E402


def _bounded_projection(observation, *, foreground_expected_app: bool) -> dict:
    home, icons = _home_anchor(observation)
    specs = (
        ("account-keyword-hints", ACCOUNT_KEYWORDS, True),
        ("merge-boss-entry", MERGE_BOSS_LABELS, False),
        ("merge-boss-keyword-hints", MERGE_BOSS_KEYWORDS, True),
        ("play-control", PLAY_LABELS, False),
        ("play-keyword-hints", PLAY_KEYWORDS, True),
    )
    targets = {}
    for name, labels, contains in specs:
        item = _project_target(
            observation,
            target_kind=name,
            labels=labels,
            contains=contains,
        )
        targets[name] = {
            "count": item.count,
            "bindable_count": item.bindable_count,
            "semantic_cluster_count": item.semantic_cluster_count,
            "bindable_button_count": item.bindable_button_count,
            "roles": list(item.roles),
            "matched_fields": list(item.matched_fields),
        }
    return {
        "status": "completed",
        "mutation_count": 0,
        "foreground_expected_app": bool(foreground_expected_app),
        "home_anchor": bool(home),
        "home_icon_count": icons,
        "targets": targets,
        "privacy": {
            "arbitrary_ui_text_persisted": False,
            "element_refs_persisted": False,
            "coordinates_persisted": False,
            "bundle_id_persisted": False,
        },
    }


async def _run() -> dict:
    identifier, host, port = await _discover_endpoint()
    app_bundle, runner_bundle = await _discover_bundles(identifier, host, port)
    runtime, transport = _runtime_and_transport(
        identifier=identifier,
        host=host,
        port=port,
        runner_bundle_id=runner_bundle,
        monitor_frame_projection=True,
    )
    try:
        observation = await _observe_bounded(runtime)
        foreground = inspect_active_application_info(
            await transport.active_application_info(), app_bundle
        )
        return _bounded_projection(
            observation,
            foreground_expected_app=foreground.expected_match,
        )
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
