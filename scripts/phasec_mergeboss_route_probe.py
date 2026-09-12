"""Bounded Phase-C route evidence for entering Merge Boss from AliExpress.

The probe uses only current-observation semantic bindings.  It may tap the
single Account button cluster once, then re-observes and reports whether a
Merge Boss/Play control becomes semantically bindable.  It never guesses
coordinates, never replays an action, and always returns Home for cleanup.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from praxiom.domain.adapter import behavior_to_candidate
from praxiom.domain.mergeboss import get_behavior
from praxiom.domain.system import LAUNCH_APPLICATION, RETURN_HOME
from praxiom.ios_runtime.foreground import inspect_active_application_info
from praxiom.ios_runtime.models import TapElement, TapPoint
from praxiom.session import RunSession
from praxiom.skill.gates import GATE_ORDER, run_gates
from praxiom.skill.registry import SkillRegistry


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from phaseb_domain_shadow_workload import (  # noqa: E402
    DEVICE_ID,
    _activate_launch_behavior,
    _observation_is_locked,
)
from phasec0_direct_wifi_shadow_workload import (  # noqa: E402
    _AsyncRuntimeSyncPort,
    _action_from_payload_c0,
    _discover_bundles,
    _observe_bounded,
)
from phasec_limited_canary import (  # noqa: E402
    _discover_endpoint,
    _home_anchor,
    _runtime_and_transport,
)
from phasec_mergeboss_entry_target_probe import (  # noqa: E402
    ACCOUNT_KEYWORDS,
    MERGE_BOSS_KEYWORDS,
    MERGE_BOSS_LABELS,
    PLAY_KEYWORDS,
    PLAY_LABELS,
    _matching_elements,
    _project_target,
    _same_visual_cluster,
)


REPORT_NAME = "mergeboss_route_report.json"


def _action_from_payload_phasec_route(payload: dict[str, Any]) -> Any:
    """Allow only C0-safe actions plus revision-bound Phase-C navigation taps."""
    if payload.get("op") == "tap_element":
        ref = payload.get("ref")
        if not isinstance(ref, str) or not ref:
            raise ValueError("tap_element requires ref")
        return TapElement(ref=ref)
    if payload.get("op") == "tap_point":
        x = payload.get("x")
        y = payload.get("y")
        if type(x) is not int or type(y) is not int:
            raise ValueError("tap_point requires integer x/y")
        return TapPoint(x=x, y=y)
    return _action_from_payload_c0(payload)


class _PhaseCRouteRuntimeSyncPort(_AsyncRuntimeSyncPort):
    """Phase-C integration-edge port; does not widen the C0 adapter."""

    def execute(self, payloads: list[dict[str, Any]], *, expected_revision: str) -> dict[str, Any]:
        actions = [_action_from_payload_phasec_route(payload) for payload in payloads]
        future = asyncio.run_coroutine_threadsafe(
            self._runtime.execute(actions, expected_revision=expected_revision),
            self._loop,
        )
        result = future.result(timeout=90)
        return {
            "effect": "NONE",
            "completed": int(result.completed_actions),
            "outcomes": result.outcomes,
        }


def _select_single_cluster_button(
    observation: Any,
    labels: Iterable[str],
    *,
    contains: bool,
) -> Any | None:
    matches = _matching_elements(observation, labels, contains=contains)
    bindable = [
        element
        for element, _field in matches
        if bool(getattr(element, "ref", ""))
        and getattr(element, "rect", None) is not None
        and getattr(element, "enabled", None) is not False
        and getattr(element, "visible", None) is not False
    ]
    if not bindable:
        return None
    first = bindable[0]
    if any(not _same_visual_cluster(first, item) for item in bindable[1:]):
        return None
    buttons = [
        item
        for item in bindable
        if str(getattr(item, "role", "")) == "XCUIElementTypeButton"
    ]
    return buttons[0] if len(buttons) == 1 else None


def _select_unique_exact_bindable(observation: Any, labels: Iterable[str]) -> Any | None:
    matches = _matching_elements(observation, labels, contains=False)
    bindable = [
        element
        for element, _field in matches
        if bool(getattr(element, "ref", ""))
        and getattr(element, "rect", None) is not None
        and getattr(element, "enabled", None) is not False
        and getattr(element, "visible", None) is not False
    ]
    return bindable[0] if len(bindable) == 1 else None


def _activate_domain_behavior(registry: SkillRegistry, behavior_id: str) -> Any:
    behavior = get_behavior(behavior_id)
    candidate = behavior_to_candidate(behavior)
    gates = run_gates(candidate)
    if not gates.passed or gates.evaluated != GATE_ORDER:
        raise RuntimeError("gates-not-passed")
    registry.register(candidate)
    registry.validate(
        behavior_id,
        1,
        evidence_ids=(f"deterministic:{behavior_id}", "r10-deterministic-matrix-green"),
    )
    registry.record_success(
        behavior_id,
        1,
        revision="deterministic-revision-1",
        evidence_id=f"deterministic-success:{behavior_id}:1",
    )
    registry.record_success(
        behavior_id,
        1,
        revision="deterministic-revision-2",
        evidence_id=f"deterministic-success:{behavior_id}:2",
    )
    return registry.activate(
        behavior_id,
        1,
        confidence=0.9,
        evidence_id="phasec-mergeboss-route-probe",
    )


def _target_projection(observation: Any) -> dict[str, Any]:
    projections = (
        _project_target(
            observation,
            target_kind="merge-boss-entry",
            labels=MERGE_BOSS_LABELS,
        ),
        _project_target(
            observation,
            target_kind="merge-boss-keyword-hints",
            labels=MERGE_BOSS_KEYWORDS,
            contains=True,
        ),
        _project_target(
            observation,
            target_kind="play-control",
            labels=PLAY_LABELS,
        ),
        _project_target(
            observation,
            target_kind="play-keyword-hints",
            labels=PLAY_KEYWORDS,
            contains=True,
        ),
    )
    return {
        item.target_kind: {
            "count": item.count,
            "bindable_count": item.bindable_count,
            "unique_bindable": item.unique_bindable,
            "semantic_cluster_count": item.semantic_cluster_count,
            "single_semantic_cluster": item.single_semantic_cluster,
            "bindable_button_count": item.bindable_button_count,
            "roles": list(item.roles),
            "matched_fields": list(item.matched_fields),
        }
        for item in projections
    }


def _persist_report(session: RunSession, report: dict[str, Any]) -> Path:
    target = session.context.run_dir / REPORT_NAME
    payload = {
        "schema_version": 1,
        "run_id": report.get("run_id"),
        "status": report.get("status"),
        "phase": "phase-c-domain-route-probe",
        "domain": "mergeboss",
        "foreground_verified": report.get("foreground_verified"),
        "account_binding": report.get("account_binding"),
        "account_attempt": report.get("account_attempt"),
        "post_account_targets": report.get("post_account_targets"),
        "entry_binding": report.get("entry_binding"),
        "entry_attempt": report.get("entry_attempt"),
        "post_entry_targets": report.get("post_entry_targets"),
        "home_cleanup": report.get("home_cleanup"),
        "summary": report.get("summary"),
        "privacy": {
            "arbitrary_ui_text_persisted": False,
            "element_refs_persisted": False,
            "coordinates_persisted": False,
            "bundle_id_persisted": False,
        },
    }
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


async def _run(
    *,
    state_root: Path | str | None,
    run_id: str | None,
    advance_entry: bool = False,
) -> dict[str, Any]:
    identifier, host, port = await _discover_endpoint()
    app_bundle, runner_bundle = await _discover_bundles(identifier, host, port)
    runtime, transport = _runtime_and_transport(
        identifier=identifier,
        host=host,
        port=port,
        runner_bundle_id=runner_bundle,
        state_root=state_root,
        monitor_frame_projection=True,
    )
    loop = asyncio.get_running_loop()
    worker = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="praxiom-phasec-mergeboss-route")
    registry = SkillRegistry()
    port_adapter = _PhaseCRouteRuntimeSyncPort(runtime, loop)

    def make_session() -> RunSession:
        return RunSession.start(
            runtime=port_adapter,
            registry=registry,
            state_root=state_root,
            run_id=run_id,
            sequence_enabled=False,
            device_id=DEVICE_ID,
        )

    session = await loop.run_in_executor(worker, make_session)
    await loop.run_in_executor(worker, session.attach_trace_source, runtime)
    report: dict[str, Any] = {"run_id": session.run_id, "status": "running"}
    close_status = "ok"
    close_reason: str | None = None
    try:
        launch_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                LAUNCH_APPLICATION,
                evidence_prefix="phasec:mergeboss-route:launch",
            ),
        )
        home_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                RETURN_HOME,
                evidence_prefix="phasec:mergeboss-route:home",
            ),
        )
        route_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_domain_behavior(registry, "mergeboss:open-level-board"),
        )

        pre = await _observe_bounded(runtime)
        if _observation_is_locked(pre) or not pre.revision:
            raise RuntimeError("fresh-unlocked-pre-observation-required")

        launch = await loop.run_in_executor(
            worker,
            lambda: session.execute_skill(
                launch_skill,
                revision=pre.revision,
                op="launch_app",
                extra={"bundle_id": app_bundle},
                shadow_pending=1,
            ),
        )
        if launch.state != "succeeded" or launch.effect != "NONE" or bool(launch.evidence.get("replayed", False)):
            raise RuntimeError("launch-attempt-not-clean")

        observation = await _observe_bounded(runtime)
        foreground = inspect_active_application_info(await transport.active_application_info(), app_bundle)
        report["foreground_verified"] = bool(foreground.expected_match)
        account_button = _select_single_cluster_button(
            observation,
            ACCOUNT_KEYWORDS,
            contains=True,
        )
        report["account_binding"] = {
            "single_cluster_button": account_button is not None,
            "binding_source": "fresh-accessibility-keyword-cluster",
        }
        if account_button is None:
            report["status"] = "blocked"
            report["post_account_targets"] = {}
        else:
            account_attempt = await loop.run_in_executor(
                worker,
                lambda: session.execute_skill(
                    route_skill,
                    revision=observation.revision,
                    op="tap_element",
                    extra={"ref": account_button.ref},
                    shadow_pending=1,
                ),
            )
            account_replayed = bool(account_attempt.evidence.get("replayed", False))
            report["account_attempt"] = {
                "state": account_attempt.state,
                "effect": account_attempt.effect,
                "replayed": account_replayed,
                "semantic_postcondition_satisfied": False,
            }
            if account_attempt.state != "succeeded" or account_attempt.effect != "NONE" or account_replayed:
                raise RuntimeError("account-route-attempt-not-clean")
            post_account = await _observe_bounded(runtime)
            report["post_account_targets"] = _target_projection(post_account)
            observation = post_account
            if advance_entry:
                entry = _select_unique_exact_bindable(
                    post_account,
                    MERGE_BOSS_LABELS,
                )
                report["entry_binding"] = {
                    "unique_exact_bindable": entry is not None,
                    "binding_source": "fresh-accessibility-exact-semantic",
                }
                if entry is None:
                    report["status"] = "blocked"
                else:
                    entry_attempt = await loop.run_in_executor(
                        worker,
                        lambda: session.execute_skill(
                            route_skill,
                            revision=post_account.revision,
                            op="tap_element",
                            extra={"ref": entry.ref},
                            shadow_pending=1,
                        ),
                    )
                    entry_replayed = bool(entry_attempt.evidence.get("replayed", False))
                    report["entry_attempt"] = {
                        "state": entry_attempt.state,
                        "effect": entry_attempt.effect,
                        "replayed": entry_replayed,
                        "semantic_postcondition_satisfied": False,
                    }
                    if entry_attempt.state != "succeeded" or entry_attempt.effect != "NONE" or entry_replayed:
                        raise RuntimeError("merge-boss-entry-attempt-not-clean")
                    post_entry = await _observe_bounded(runtime)
                    report["post_entry_targets"] = _target_projection(post_entry)
                    observation = post_entry
                    report["status"] = "completed"
            else:
                report["status"] = "completed"

        cleanup = await loop.run_in_executor(
            worker,
            lambda: session.execute_skill(
                home_skill,
                revision=observation.revision,
                op="home",
                shadow_pending=1,
            ),
        )
        cleanup_replayed = bool(cleanup.evidence.get("replayed", False))
        restored = await _observe_bounded(runtime)
        home_ok, icon_count = _home_anchor(restored)
        report["home_cleanup"] = {
            "state": cleanup.state,
            "effect": cleanup.effect,
            "replayed": cleanup_replayed,
            "home_anchor": home_ok,
            "icon_count": icon_count,
        }
        if cleanup.state != "succeeded" or cleanup.effect != "NONE" or cleanup_replayed or not home_ok:
            raise RuntimeError("home-cleanup-not-clean")
        return report
    except BaseException:
        close_status = "failed"
        close_reason = "phasec-mergeboss-route-probe-exception"
        report["status"] = "failed"
        raise
    finally:
        try:
            def close_session() -> None:
                summary = session.close(status=close_status, reason_code=close_reason)
                report["summary"] = {
                    key: summary.get(key)
                    for key in ("actions", "failures", "observe", "execute", "sequences")
                    if key in summary
                }
                _persist_report(session, report)

            await loop.run_in_executor(worker, close_session)
        finally:
            await runtime.close()
            worker.shutdown(wait=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm-device-run", action="store_true")
    parser.add_argument("--state-root", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--advance-entry", action="store_true")
    args = parser.parse_args()
    if not args.confirm_device_run:
        print(json.dumps({"status": "refused", "reason": "confirmation-required"}))
        return 2
    runner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
    with runner:
        report = runner.run(
            _run(
                state_root=args.state_root,
                run_id=args.run_id,
                advance_entry=args.advance_entry,
            )
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"completed", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
