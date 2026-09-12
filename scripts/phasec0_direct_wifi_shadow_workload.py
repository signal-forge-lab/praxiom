"""Phase C0 direct-Wi-Fi wrapper for the certified Phase-B shadow workload.

This script exists only to collect Phase C0 real-device evidence when Bonjour
discovery is intermittent but a previously observed endpoint is still directly
reachable.  It resolves the exactly-one local RemotePairing identity in-process,
discovers the installed AliExpress and WDA runner bundle identifiers read-only,
then delegates all device mutation to the existing certified
``collect_shadow_workload`` path.

Raw device identifiers, bundle identifiers and endpoint values are never
printed or persisted by this script.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import sys
from pathlib import Path
from typing import Any

from pymobiledevice3.remote.core_device.app_service import AppServiceService
from pymobiledevice3.remote.tunnel_service import (
    create_core_device_tunnel_service_using_remotepairing,
    iter_remote_paired_identifiers,
)

from praxiom.ios_runtime.discovery import DeviceDiscovery, WifiEndpoint
from praxiom.ios_runtime.models import Home, LaunchApp
from praxiom.ios_runtime.runtime import NativeIosRuntime
from praxiom.ios_runtime.transport import IosTransport
from praxiom.ios_runtime.wifi_tunnel import RemotePairingUserspaceRsdTunnel
from praxiom.domain.system import RETURN_HOME


SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from phaseb_domain_shadow_workload import (  # noqa: E402
    DEVICE_ID,
    OWNER,
    _activate_launch_behavior,
    _domain_specs,
    _observation_is_locked,
)
from praxiom.session import RunSession  # noqa: E402
from praxiom.skill.registry import SkillRegistry  # noqa: E402


OBSERVE_TIMEOUT_S = 60.0
RECOVER_TIMEOUT_S = 60.0


async def _observe_bounded(
    runtime: NativeIosRuntime, *, timeout_s: float = OBSERVE_TIMEOUT_S
) -> Any:
    """Bound one read-only observation so a stalled WDA read cannot hang C0.

    Timing out never retries or replays a mutation.  The caller's run-finally
    path closes the session/runtime and records a failed terminal result.
    """
    if timeout_s <= 0:
        raise ValueError("observe-timeout-must-be-positive")
    try:
        return await asyncio.wait_for(runtime.observe(), timeout=timeout_s)
    except TimeoutError as exc:
        raise RuntimeError("phasec0-observe-timeout") from exc


async def _post_action_observe_with_one_recovery(
    runtime: NativeIosRuntime,
    *,
    observe_timeout_s: float = OBSERVE_TIMEOUT_S,
    recover_timeout_s: float = RECOVER_TIMEOUT_S,
) -> Any:
    """Get one fresh post-action observation, with at most one plumbing repair.

    This helper is intentionally usable only *after* a caller has established
    that the action itself completed successfully with a known effect and was
    not replayed.  On an observation timeout it may rebuild Runtime plumbing
    once through ``Runtime.recover()`` and then retries the **read-only**
    observation.  It never calls or replays the action callback.
    """
    if recover_timeout_s <= 0:
        raise ValueError("recover-timeout-must-be-positive")
    try:
        return await _observe_bounded(runtime, timeout_s=observe_timeout_s)
    except RuntimeError as exc:
        if str(exc) != "phasec0-observe-timeout":
            raise
    try:
        await asyncio.wait_for(runtime.recover(), timeout=recover_timeout_s)
    except TimeoutError as exc:
        raise RuntimeError("phasec0-recover-timeout") from exc
    return await _observe_bounded(runtime, timeout_s=observe_timeout_s)


async def _discover_bundles(
    identifier: str, host: str, port: int
) -> tuple[str, str]:
    async def direct_services():
        return [
            await create_core_device_tunnel_service_using_remotepairing(
                identifier, host, port
            )
        ]

    tunnel = RemotePairingUserspaceRsdTunnel(
        identifier, pairing_services=direct_services
    )
    rsd = await tunnel.aopen()
    try:
        async with AppServiceService(rsd) as service:
            apps = await service.list_apps()
            ali = [
                item["bundleIdentifier"]
                for item in apps
                if item.get("name") == "AliExpress"
                and isinstance(item.get("bundleIdentifier"), str)
            ]
            runners = [
                item["bundleIdentifier"]
                for item in apps
                if "WebDriverAgentRunner" in str(item.get("name", ""))
                and isinstance(item.get("bundleIdentifier"), str)
            ]
            if len(ali) != 1:
                raise RuntimeError("exactly-one-aliexpress-install-required")
            if len(runners) != 1:
                raise RuntimeError("exactly-one-wda-runner-required")
            return ali[0], runners[0]
    finally:
        await tunnel.aclose()


def _runtime_for_endpoint(
    *, identifier: str, host: str, port: int, runner_bundle_id: str
) -> NativeIosRuntime:
    async def no_usb():
        return []

    async def wifi_targets():
        return [WifiEndpoint(identifier=identifier, hostname=host, port=port)]

    async def direct_services():
        return [
            await create_core_device_tunnel_service_using_remotepairing(
                identifier, host, port
            )
        ]

    discovery = DeviceDiscovery(
        usb_devices=no_usb,
        wifi_pairing_targets=wifi_targets,
    )

    def wifi_tunnel_factory(target: Any):
        return RemotePairingUserspaceRsdTunnel(
            target.wifi.identifier,
            pairing_services=direct_services,
        )

    return NativeIosRuntime(
        transport=IosTransport(
            xctrunner_bundle_id=runner_bundle_id,
            discovery=discovery,
            wifi_tunnel_factory=wifi_tunnel_factory,
        )
    )


class _AsyncRuntimeSyncPort:
    """Coordinator sync port that schedules Runtime I/O on its owner loop."""

    def __init__(self, runtime: NativeIosRuntime, loop: asyncio.AbstractEventLoop) -> None:
        self._runtime = runtime
        self._loop = loop

    def execute(self, payloads: list[dict[str, Any]], *, expected_revision: str) -> dict[str, Any]:
        actions = [_action_from_payload_c0(payload) for payload in payloads]
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


def _action_from_payload_c0(payload: dict[str, Any]) -> Any:
    """Narrow C0 action mapper: certified launch plus reversible Home only."""
    op = payload.get("op")
    if op == "home":
        return Home()
    if op == "launch_app":
        bundle_id = payload.get("bundle_id")
        if not isinstance(bundle_id, str) or not bundle_id:
            raise ValueError("launch_app requires bundle_id")
        return LaunchApp(bundle_id=bundle_id)
    raise ValueError("phasec0-representative-op-not-allowed")


async def _collect_representative_shadow_workload(
    *,
    runtime: NativeIosRuntime,
    bundle_ids: dict[str, str],
    state_root: Path | str | None,
    run_id: str | None,
    cycles: int,
) -> dict[str, Any]:
    """Collect three low-risk classes in one WDA session, never batching live."""
    if cycles < 1:
        raise ValueError("cycles must be >= 1")
    loop = asyncio.get_running_loop()
    worker = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="praxiom-c0-representative"
    )
    port = _AsyncRuntimeSyncPort(runtime, loop)
    registry = SkillRegistry()

    def make_session() -> RunSession:
        return RunSession.start(
            runtime=port,
            registry=registry,
            state_root=state_root,
            run_id=run_id,
            sequence_enabled=False,
            device_id=DEVICE_ID,
        )

    session = await loop.run_in_executor(worker, make_session)
    await loop.run_in_executor(worker, session.attach_trace_source, runtime)
    report: dict[str, Any] = {
        "run_id": session.run_id,
        "mode": "shadow-only-representative",
        "adaptive_live_apply": False,
        "sequence_live_apply": False,
        "cycles": cycles,
        "classes": {},
    }
    close_status = "ok"
    close_reason: str | None = None
    try:
        mb_behavior = _domain_specs()[0][1]
        gg_behavior = _domain_specs()[1][1]
        mb_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry, mb_behavior, evidence_prefix="phasec0:representative:mergeboss"
            ),
        )
        gg_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry, gg_behavior, evidence_prefix="phasec0:representative:gogomatch"
            ),
        )
        home_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry, RETURN_HOME, evidence_prefix="phasec0:representative:system-home"
            ),
        )
        classes = {
            mb_behavior.behavior_id: {"attempts": 0, "success_none": 0},
            gg_behavior.behavior_id: {"attempts": 0, "success_none": 0},
            RETURN_HOME.behavior_id: {"attempts": 0, "success_none": 0},
        }
        report["classes"] = classes

        async def one(skill: Any, behavior_id: str, op: str, extra: dict[str, Any] | None = None):
            observation = await _observe_bounded(runtime)
            if _observation_is_locked(observation):
                raise RuntimeError("device-locked")
            revision = observation.revision
            if not revision:
                raise RuntimeError("empty-pre-action-revision")

            def execute_one():
                return session.execute_skill(
                    skill,
                    revision=revision,
                    op=op,
                    extra=extra,
                    shadow_pending=1,
                )

            attempt = await loop.run_in_executor(worker, execute_one)
            classes[behavior_id]["attempts"] += 1
            if attempt.state != "succeeded" or attempt.effect != "NONE":
                raise RuntimeError("representative-attempt-not-success-none")
            if bool(attempt.evidence.get("replayed", False)):
                raise RuntimeError("representative-attempt-replayed")
            post = await _post_action_observe_with_one_recovery(runtime)
            if not post.revision or post.revision == revision:
                raise RuntimeError("fresh-post-action-revision-required")
            classes[behavior_id]["success_none"] += 1

        for _ in range(cycles):
            await one(
                mb_skill,
                mb_behavior.behavior_id,
                "launch_app",
                {"bundle_id": bundle_ids["mergeboss"]},
            )
            await one(home_skill, RETURN_HOME.behavior_id, "home")
            await one(
                gg_skill,
                gg_behavior.behavior_id,
                "launch_app",
                {"bundle_id": bundle_ids["gogomatch"]},
            )
            await one(home_skill, RETURN_HOME.behavior_id, "home")
        report["status"] = "completed"
        return report
    except BaseException as exc:
        close_status = "failed"
        close_reason = "representative-workload-exception"
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        raise
    finally:
        try:
            def close_session():
                summary = session.close(status=close_status, reason_code=close_reason)
                report["summary"] = {
                    "actions": summary.get("actions"),
                    "failures": summary.get("failures"),
                    "policy": summary.get("policy"),
                    "sequences": summary.get("sequences"),
                }
                report["experience"] = {
                    "episodes": len(session.experience_store.load().episodes),
                    "shadow_recommendations": len(session.shadow_advisor.history),
                }
            await loop.run_in_executor(worker, close_session)
        finally:
            await runtime.close()
            worker.shutdown(wait=True)


async def _collect_home_only_preflight(
    *,
    runtime: NativeIosRuntime,
    state_root: Path | str | None,
    run_id: str | None,
    iterations: int,
) -> dict[str, Any]:
    """Fresh-observe -> one certified Home -> fresh-observe operational preflight.

    This is the narrow 97% -> 100% C0 gate for the first Phase-C candidate.
    It never launches a user app, never enables Adaptive Live/sequence-live,
    and never retries/replays a mutation.  A Runtime/WDA/lock failure before
    ``session.execute_skill`` leaves the run with zero device action attempts.
    """
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    loop = asyncio.get_running_loop()
    worker = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="praxiom-c0-home-preflight"
    )
    port = _AsyncRuntimeSyncPort(runtime, loop)
    registry = SkillRegistry()

    def make_session() -> RunSession:
        return RunSession.start(
            runtime=port,
            registry=registry,
            state_root=state_root,
            run_id=run_id,
            sequence_enabled=False,
            device_id=DEVICE_ID,
        )

    session = await loop.run_in_executor(worker, make_session)
    await loop.run_in_executor(worker, session.attach_trace_source, runtime)
    report: dict[str, Any] = {
        "run_id": session.run_id,
        "mode": "phasec0-home-only-operational-preflight",
        "candidate_operation_class": RETURN_HOME.behavior_id,
        "adaptive_live_apply": False,
        "sequence_live_apply": False,
        "iterations": iterations,
        "attempts": [],
    }
    close_status = "ok"
    close_reason: str | None = None
    try:
        home_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                RETURN_HOME,
                evidence_prefix="phasec0:operational-preflight:system-home",
            ),
        )
        for index in range(iterations):
            observation = await _observe_bounded(runtime)
            if _observation_is_locked(observation):
                report["status"] = "blocked"
                report["stop_reason"] = "device-locked"
                return report
            revision = observation.revision
            if not revision:
                raise RuntimeError("empty-pre-action-revision")

            def execute_one():
                return session.execute_skill(
                    home_skill,
                    revision=revision,
                    op="home",
                    shadow_pending=1,
                )

            attempt = await loop.run_in_executor(worker, execute_one)
            evidence = attempt.evidence if isinstance(attempt.evidence, dict) else {}
            row = {
                "iteration": index + 1,
                "state": attempt.state,
                "effect": attempt.effect,
                "replayed": bool(evidence.get("replayed", False)),
            }
            report["attempts"].append(row)
            if attempt.state != "succeeded" or attempt.effect != "NONE":
                report["status"] = "stopped"
                report["stop_reason"] = "home-attempt-not-success-none"
                return report
            if row["replayed"]:
                raise RuntimeError("home-preflight-attempt-replayed")

            post = await _observe_bounded(runtime)
            if not post.revision or post.revision == revision:
                raise RuntimeError("fresh-post-action-revision-required")

        report["status"] = "completed"
        return report
    except BaseException as exc:
        close_status = "failed"
        close_reason = "home-preflight-exception"
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        raise
    finally:
        try:
            def close_session():
                summary = session.close(status=close_status, reason_code=close_reason)
                report["summary"] = {
                    "actions": summary.get("actions"),
                    "failures": summary.get("failures"),
                    "policy": summary.get("policy"),
                    "sequences": summary.get("sequences"),
                }
                report["experience"] = {
                    "episodes": len(session.experience_store.load().episodes),
                    "shadow_recommendations": len(session.shadow_advisor.history),
                }
            await loop.run_in_executor(worker, close_session)
        finally:
            await runtime.close()
            worker.shutdown(wait=True)


async def _collect_async_shadow_workload(
    *,
    runtime: NativeIosRuntime,
    bundle_ids: dict[str, str],
    state_root: Path | str | None,
    run_id: str | None,
    iterations: int,
) -> dict[str, Any]:
    """Collect the same certified shadow workload without cross-loop Runtime I/O."""
    if iterations < 2:
        raise ValueError("iterations must be >= 2 for distinct-revision learning evidence")
    if set(bundle_ids) != {"mergeboss", "gogomatch"}:
        raise ValueError("exact domain bundle mapping required")
    if any(not isinstance(value, str) or not value for value in bundle_ids.values()):
        raise ValueError("non-empty bundle ids required")

    loop = asyncio.get_running_loop()
    worker = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="praxiom-c0-coordinator"
    )
    port = _AsyncRuntimeSyncPort(runtime, loop)
    registry = SkillRegistry()

    def make_session() -> RunSession:
        return RunSession.start(
            runtime=port,
            registry=registry,
            state_root=state_root,
            run_id=run_id,
            sequence_enabled=False,
            device_id=DEVICE_ID,
        )

    session = await loop.run_in_executor(worker, make_session)
    # Runtime trace projection is read-only and can be attached to the session.
    await loop.run_in_executor(worker, session.attach_trace_source, runtime)
    report: dict[str, Any] = {
        "run_id": session.run_id,
        "mode": "shadow-only",
        "adaptive_live_apply": False,
        "sequence_live_apply": False,
        "iterations_per_domain": iterations,
        "domains": [],
    }
    close_status = "ok"
    close_reason: str | None = None
    try:
        for domain, behavior in _domain_specs():
            skill = await loop.run_in_executor(
                worker,
                lambda b=behavior, d=domain: _activate_launch_behavior(
                    registry, b, evidence_prefix=f"phasec0:{d}"
                ),
            )
            domain_result: dict[str, Any] = {
                "domain": domain,
                "behavior_id": behavior.behavior_id,
                "risk": behavior.risk,
                "reversibility": behavior.reversibility,
                "attempts": [],
            }
            observation = await _observe_bounded(runtime)
            for index in range(iterations):
                if _observation_is_locked(observation):
                    domain_result["status"] = "blocked"
                    domain_result["stop_reason"] = "device-locked"
                    report["domains"].append(domain_result)
                    report["status"] = "blocked"
                    return report
                before_revision = observation.revision
                if not before_revision:
                    raise RuntimeError("empty-pre-action-revision")

                def execute_one():
                    return session.execute_skill(
                        skill,
                        revision=before_revision,
                        op="launch_app",
                        extra={"bundle_id": bundle_ids[domain]},
                        shadow_pending=iterations - index,
                    )

                attempt = await loop.run_in_executor(worker, execute_one)
                domain_result["attempts"].append(
                    {
                        "iteration": index + 1,
                        "state": attempt.state,
                        "effect": attempt.effect,
                        "replayed": bool(attempt.evidence.get("replayed", False)),
                    }
                )
                if attempt.state != "succeeded" or attempt.effect != "NONE":
                    domain_result["status"] = "stopped"
                    domain_result["stop_reason"] = "non-none-or-unsuccessful-attempt"
                    report["domains"].append(domain_result)
                    report["status"] = "stopped"
                    return report
                observation = await _observe_bounded(runtime)
                if not observation.revision or observation.revision == before_revision:
                    raise RuntimeError("fresh-post-action-revision-required")
            domain_result["status"] = "completed"
            report["domains"].append(domain_result)
        report["status"] = "completed"
        return report
    except BaseException as exc:
        close_status = "failed"
        close_reason = "workload-exception"
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        raise
    finally:
        try:
            def close_session():
                summary = session.close(status=close_status, reason_code=close_reason)
                report["summary"] = {
                    "actions": summary.get("actions"),
                    "failures": summary.get("failures"),
                    "policy": summary.get("policy"),
                    "sequences": summary.get("sequences"),
                }
                report["experience"] = {
                    "episodes": len(session.experience_store.load().episodes),
                    "shadow_recommendations": len(session.shadow_advisor.history),
                }
            await loop.run_in_executor(worker, close_session)
        finally:
            await runtime.close()
            worker.shutdown(wait=True)


async def _run_device_workload(args: Any) -> dict[str, Any]:
    identifiers = list(iter_remote_paired_identifiers())
    if len(identifiers) != 1:
        return {
            "status": "blocked",
            "reason": "exactly-one-paired-device-required",
            "paired_device_count": len(identifiers),
        }
    identifier = identifiers[0]
    ali_bundle, runner_bundle = await _discover_bundles(
        identifier, args.wifi_host, args.wifi_port
    )
    runtime = _runtime_for_endpoint(
        identifier=identifier,
        host=args.wifi_host,
        port=args.wifi_port,
        runner_bundle_id=runner_bundle,
    )
    bundle_ids = {"mergeboss": ali_bundle, "gogomatch": ali_bundle}
    if args.home_only:
        return await _collect_home_only_preflight(
            runtime=runtime,
            state_root=args.state_root,
            run_id=args.run_id,
            iterations=args.iterations,
        )
    if args.representative:
        return await _collect_representative_shadow_workload(
            runtime=runtime,
            bundle_ids=bundle_ids,
            state_root=args.state_root,
            run_id=args.run_id,
            cycles=args.iterations,
        )
    return await _collect_async_shadow_workload(
        runtime=runtime,
        bundle_ids=bundle_ids,
        state_root=args.state_root,
        run_id=args.run_id,
        iterations=args.iterations,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm-device-run", action="store_true")
    parser.add_argument("--wifi-host", required=True)
    parser.add_argument("--wifi-port", type=int, required=True)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument(
        "--representative",
        action="store_true",
        help="alternate launch/home across three low-risk behavior classes",
    )
    parser.add_argument(
        "--home-only",
        action="store_true",
        help="run only the system:return-home operational preflight",
    )
    parser.add_argument("--state-root", default=None)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    if not args.confirm_device_run:
        print(json.dumps({"status": "refused", "reason": "confirmation-required"}))
        return 2
    if not 1 <= args.wifi_port <= 65535:
        print(json.dumps({"status": "blocked", "reason": "wifi-port-invalid"}))
        return 2
    if args.representative and args.home_only:
        print(json.dumps({"status": "blocked", "reason": "workload-mode-conflict"}))
        return 2
    minimum = 1 if (args.representative or args.home_only) else 2
    if args.iterations < minimum:
        print(json.dumps({"status": "blocked", "reason": "iterations-below-mode-minimum"}))
        return 2

    # Keep the same selector-loop semantics used by the certified Windows MCP
    # path. RemotePairing/userspace networking is not reliable on Proactor.
    runner = asyncio.Runner(
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None
    )
    with runner:
        report = runner.run(_run_device_workload(args))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "completed" else 2 if report.get("status") == "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
