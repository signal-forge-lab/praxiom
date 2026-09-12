"""Phase C limited Adaptive Live canary for the accepted Home operation class.

The first Phase C surface is intentionally tiny:

* operation class: ``system:return-home`` only;
* one certified Home mutation at a time;
* Adaptive Live may replace only the immediate full post-observe with a
  bounded, read-only causal validator;
* the validator never authors a Runtime revision;
* every later mutation still requires a fresh full Runtime observation;
* sequence-live remains disabled;
* a validator/gate/preflight failure falls back to full observe or blocks
  before mutation; no action is retried or replayed.

The runner is an integration edge. Device mutation remains exclusively
Skill -> Coordinator -> Runtime. The read-only cheap validator uses the
already-owned WDA transport only to count structural accessibility roles; it
never retains labels, text, XML, identifiers, or coordinates.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import math
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from pymobiledevice3.remote.tunnel_service import (
    create_core_device_tunnel_service_using_remotepairing,
    get_remote_pairing_tunnel_services,
)

from praxiom.adaptive.promotion import (
    CanaryEnvironment,
    PromotionReadiness,
    evaluate_canary_preflight,
)
from praxiom.adaptive.shadow import (
    LiveOptimizationGate,
    LiveOptimizationRefusedError,
    ShadowContext,
    shadow_recommend,
)
from praxiom.domain.system import RETURN_HOME
from praxiom.ios_runtime.discovery import DeviceDiscovery, WifiEndpoint
from praxiom.ios_runtime.runtime import NativeIosRuntime
from praxiom.ios_runtime.transport import IosTransport
from praxiom.ios_runtime.wifi_tunnel import RemotePairingUserspaceRsdTunnel
from praxiom.monitor.projection import LatestFrameStore
from praxiom.retrieval.validator import AdaptiveValidator, ValidationContext
from praxiom.session import RunSession
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
    _discover_bundles,
    _observe_bounded,
)
from phasec0_readiness_analysis import analyze as analyze_c0  # noqa: E402


OPERATION_CLASS = "system:return-home"
EXPECTED_HOME_ANCHOR = "system-home-structural-icons"
CHEAP_VALIDATE_TIMEOUT_S = 15.0
AUTO_DISCOVERY_TIMEOUT_S = 8.0


def _count_icon_roles(xml: str) -> int:
    """Count structural Home icon roles without retaining user-visible data."""
    if not isinstance(xml, str) or not xml:
        return 0
    root = ElementTree.fromstring(xml)
    count = 0
    for node in root.iter():
        role = node.tag.rsplit("}", 1)[-1].lower()
        if "icon" in role:
            count += 1
    return count


async def _cheap_home_context(
    transport: IosTransport,
    *,
    effect: str,
    timeout_s: float = CHEAP_VALIDATE_TIMEOUT_S,
) -> tuple[ValidationContext, int, float]:
    """Return one bounded, revision-free Home causal validation context."""
    if timeout_s <= 0:
        raise ValueError("cheap-validator-timeout-must-be-positive")
    started = time.perf_counter()
    xml = await asyncio.wait_for(transport.accessibility_source(), timeout=timeout_s)
    latency_ms = (time.perf_counter() - started) * 1000.0
    icon_count = _count_icon_roles(xml)
    observed = frozenset({EXPECTED_HOME_ANCHOR}) if icon_count > 0 else frozenset()
    return (
        ValidationContext(
            effect=effect,
            expected_anchor=EXPECTED_HOME_ANCHOR,
            observed_labels=observed,
            confidence=1.0,
            high_risk=False,
            mismatch=False,
        ),
        icon_count,
        latency_ms,
    )


def _live_recommendation(context: ValidationContext, *, confidence: float):
    decision = AdaptiveValidator().decide(context)
    recommendation = shadow_recommend(
        ShadowContext(
            validated_confidence=confidence,
            next_is_state_sensitive=False,
            revision_invalidated=True,
            risk="low",
            reversibility="reversible",
            human_gate=False,
            validator_decision=decision,
            validation_context=context,
            pending=1,
            max_batch=1,
        )
    )
    return decision, recommendation


def _authorize_observation_live(recommendation: Any) -> Any:
    gate = LiveOptimizationGate(enabled=True)
    gate.authorize(
        recommendation,
        risk="low",
        reversibility="reversible",
        human_gate=False,
    )
    if recommendation.observation is None or recommendation.observation.method != "cheap-validate":
        raise LiveOptimizationRefusedError("observation-only-canary-requires-cheap-validate")
    if recommendation.would_reduce_actions:
        raise LiveOptimizationRefusedError("sequence-or-action-reduction-not-allowed")
    return replace(recommendation, live_applied=True)


def _promotion_readiness(state_root: Path | str | None) -> PromotionReadiness:
    report = analyze_c0(state_root=state_root)
    if not bool(report.get("c0_completion", {}).get("ready")):
        raise RuntimeError("phasec0-not-complete")
    data = report.get("promotion_decision")
    if not isinstance(data, dict):
        raise RuntimeError("promotion-decision-missing")
    return PromotionReadiness(
        ready=bool(data.get("ready")),
        operation_class=str(data.get("operation_class") or ""),
        allowed_surface=str(data.get("allowed_surface") or ""),
        sequence_live_allowed=bool(data.get("sequence_live_allowed")),
        reasons=tuple(str(item) for item in (data.get("reasons") or ())),
    )


async def _discover_endpoint(*, attempts: int = 3) -> tuple[str, str, int]:
    """Bound read-only Bonjour discovery without ever retrying a mutation."""
    if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
        raise ValueError("discovery-attempts-positive")
    last_error = "exactly-one-remote-paired-device-required"
    for index in range(attempts):
        services = list(
            await get_remote_pairing_tunnel_services(
                bonjour_timeout=AUTO_DISCOVERY_TIMEOUT_S
            )
        )
        try:
            identifiers = {
                str(getattr(item, "remote_identifier", "") or "")
                for item in services
                if getattr(item, "remote_identifier", None)
            }
            if len(identifiers) != 1:
                last_error = "exactly-one-remote-paired-device-required"
            else:
                identifier = next(iter(identifiers))
                matching = [
                    item for item in services
                    if getattr(item, "remote_identifier", None) == identifier
                ]
                if not matching:
                    last_error = "remote-pairing-endpoint-required"
                else:
                    selected = matching[0]
                    host = str(getattr(selected, "hostname", "") or "")
                    port = int(getattr(selected, "port", 0) or 0)
                    if host and 1 <= port <= 65535:
                        return identifier, host, port
                    last_error = "remote-pairing-endpoint-invalid"
        finally:
            for service in services:
                try:
                    await service.close()
                except Exception:
                    pass
        if index + 1 < attempts:
            await asyncio.sleep(0.5)
    raise RuntimeError(last_error)


def _runtime_and_transport(
    *,
    identifier: str,
    host: str,
    port: int,
    runner_bundle_id: str,
    state_root: Path | str | None = None,
    monitor_frame_projection: bool = False,
) -> tuple[NativeIosRuntime, IosTransport]:
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

    transport = IosTransport(
        xctrunner_bundle_id=runner_bundle_id,
        discovery=discovery,
        wifi_tunnel_factory=wifi_tunnel_factory,
    )
    frame_sink = (
        LatestFrameStore(state_root).publish if monitor_frame_projection else None
    )
    return NativeIosRuntime(transport=transport, frame_sink=frame_sink), transport


def _home_anchor(observation: Any) -> tuple[bool, int]:
    count = 0
    for element in tuple(getattr(observation, "elements", ()) or ()):
        if "icon" in str(getattr(element, "role", "") or "").lower():
            count += 1
    return bool(count > 0 and getattr(observation, "revision", None)), count


async def _run_canary(
    *,
    state_root: Path | str | None,
    run_id: str | None,
    iterations: int,
    monitor_frame_projection: bool,
) -> dict[str, Any]:
    readiness = _promotion_readiness(state_root)
    if (
        not readiness.ready
        or readiness.operation_class != OPERATION_CLASS
        or readiness.allowed_surface != "observation-only"
        or readiness.sequence_live_allowed
    ):
        return {"status": "blocked", "reason": "promotion-readiness-refused"}

    identifier, host, port = await _discover_endpoint()
    _ali_bundle, runner_bundle = await _discover_bundles(identifier, host, port)
    runtime, transport = _runtime_and_transport(
        identifier=identifier,
        host=host,
        port=port,
        runner_bundle_id=runner_bundle,
        state_root=state_root,
        monitor_frame_projection=monitor_frame_projection,
    )
    loop = asyncio.get_running_loop()
    worker = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="praxiom-phasec-home"
    )
    port_adapter = _AsyncRuntimeSyncPort(runtime, loop)
    registry = SkillRegistry()

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
    close_status = "ok"
    close_reason: str | None = None
    report: dict[str, Any] = {
        "run_id": session.run_id,
        "status": "running",
        "phase": "phase-c",
        "candidate_operation_class": OPERATION_CLASS,
        "adaptive_surface": "observation-only",
        "adaptive_live_apply": True,
        "sequence_live_apply": False,
        "monitor_frame_projection": bool(monitor_frame_projection),
        "iterations": iterations,
        "attempts": [],
        "cheap_validation": [],
        "audit": [],
    }
    try:
        skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                RETURN_HOME,
                evidence_prefix="phasec:limited-canary:system-home",
            ),
        )
        previous_live_applied = False
        for index in range(iterations):
            pre = await _observe_bounded(runtime)
            if _observation_is_locked(pre):
                raise RuntimeError("device-locked")
            if previous_live_applied:
                anchored, count = _home_anchor(pre)
                report["audit"].append(
                    {"iteration": index, "full_observe_home_anchor": anchored, "icon_count": count}
                )
                if not anchored:
                    raise RuntimeError("previous-cheap-validation-not-corroborated")
            status = await runtime.status()
            environment = CanaryEnvironment(
                runtime_ready=status.lifecycle_state.value == "READY",
                device_channel_ready=status.wda_state.value == "READY",
                fresh_observation_ready=bool(pre.revision),
                mutation_lane_idle=True,
                device_locked=False,
                environment_error_class=(
                    "" if status.last_error_code is None else status.last_error_code.value
                ),
            )
            gate = evaluate_canary_preflight(readiness, environment)
            if not gate.ready:
                raise RuntimeError("dynamic-canary-preflight-refused:" + "+".join(gate.reasons))

            revision = pre.revision
            if not revision:
                raise RuntimeError("fresh-pre-action-revision-required")

            def execute_home():
                return session.execute_skill(
                    skill,
                    revision=revision,
                    op="home",
                    shadow_pending=1,
                )

            attempt = await loop.run_in_executor(worker, execute_home)
            attempt_row = {
                "iteration": index + 1,
                "state": str(attempt.state),
                "effect": str(attempt.effect),
                "replayed": bool(
                    attempt.evidence.get("replayed", False)
                    if isinstance(attempt.evidence, dict)
                    else False
                ),
            }
            report["attempts"].append(attempt_row)
            if (
                attempt_row["state"] != "succeeded"
                or attempt_row["effect"] != "NONE"
                or attempt_row["replayed"]
            ):
                raise RuntimeError("phasec-home-attempt-not-clean")

            live_applied = False
            fallback_reason = ""
            try:
                validation_context, icon_count, validator_ms = await _cheap_home_context(
                    transport,
                    effect=attempt_row["effect"],
                )
                validation_decision, recommendation = _live_recommendation(
                    validation_context,
                    confidence=float(skill.confidence),
                )
                recommendation = _authorize_observation_live(recommendation)
                live_applied = bool(recommendation.live_applied)
                report["cheap_validation"].append(
                    {
                        "iteration": index + 1,
                        "sufficient": bool(validation_decision.sufficient),
                        "method": validation_decision.method,
                        "icon_count": icon_count,
                        "latency_ms": round(validator_ms, 3),
                        "live_applied": live_applied,
                    }
                )
                session._note(
                    session.journal.emit(
                        "validation.performed",
                        phase="validation",
                        behavior_id=OPERATION_CLASS,
                        skill_id=skill.skill_id,
                        skill_version=str(skill.version),
                        revision=revision,
                        duration_ms=validator_ms,
                        payload={
                            "observe_mode": "cheap_validate",
                            "confidence": float(validation_decision.confidence),
                            "reason_code": "phase-c-live-causal-validator",
                            "detail": "home-structural-anchor",
                        },
                    )
                )
            except Exception as exc:
                fallback_reason = type(exc).__name__
                post = await _observe_bounded(runtime)
                anchored, icon_count = _home_anchor(post)
                report["cheap_validation"].append(
                    {
                        "iteration": index + 1,
                        "sufficient": False,
                        "method": "full-observe-fallback",
                        "icon_count": icon_count,
                        "latency_ms": None,
                        "live_applied": False,
                        "fallback_reason": fallback_reason,
                    }
                )
                session._note(
                    session.journal.emit(
                        "validation.performed",
                        phase="validation",
                        behavior_id=OPERATION_CLASS,
                        skill_id=skill.skill_id,
                        skill_version=str(skill.version),
                        revision=revision,
                        payload={
                            "observe_mode": "full",
                            "confidence": float(skill.confidence),
                            "reason_code": "phase-c-full-observe-fallback",
                            "detail": fallback_reason,
                        },
                    )
                )
                if not anchored:
                    raise RuntimeError("full-observe-fallback-home-anchor-failed") from exc

            session._note(
                session.journal.emit(
                    "policy.decision",
                    phase="policy",
                    behavior_id=OPERATION_CLASS,
                    skill_id=skill.skill_id,
                    skill_version=str(skill.version),
                    revision=revision,
                    policy_recommendation="cheap-validate",
                    actual_policy=("cheap-validate-live" if live_applied else "full-observe"),
                    fallback_reason=fallback_reason or None,
                    payload={
                        "recommended": True,
                        "actual_batch_size": 1,
                        "recommended_batch_size": 1,
                        "confidence": float(skill.confidence),
                        "observe_mode": ("cheap_validate" if live_applied else "full"),
                        "reason_code": ("phase-c-live-applied" if live_applied else "phase-c-fallback"),
                    },
                )
            )
            previous_live_applied = live_applied

        # Final audit is observation-only and happens after the live decision;
        # it is evidence for the canary, not the success criterion that caused
        # the live optimization to be applied.
        final_observation = await _observe_bounded(runtime)
        final_anchor, final_count = _home_anchor(final_observation)
        report["audit"].append(
            {
                "iteration": iterations,
                "final_full_observe_home_anchor": final_anchor,
                "icon_count": final_count,
            }
        )
        session._note(
            session.journal.emit(
                "validation.performed",
                phase="validation",
                behavior_id=OPERATION_CLASS,
                skill_id=skill.skill_id,
                skill_version=str(skill.version),
                revision=final_observation.revision,
                payload={
                    "observe_mode": "full",
                    "confidence": 1.0,
                    "reason_code": "phase-c-final-audit",
                    "detail": "home-structural-anchor",
                },
            )
        )
        if not final_anchor:
            raise RuntimeError("final-canary-audit-home-anchor-failed")
        report["status"] = "completed"
        return report
    except BaseException as exc:
        close_status = "failed"
        close_reason = "phasec-limited-canary-exception"
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
                    "observe": summary.get("observe"),
                    "execute": summary.get("execute"),
                }

            await loop.run_in_executor(worker, close_session)
        finally:
            await runtime.close()
            worker.shutdown(wait=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm-device-run", action="store_true")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--state-root", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--monitor-frame-projection",
        action="store_true",
        help="publish this canary Runtime's fresh PNG frames to the shared Monitor store",
    )
    args = parser.parse_args()
    if not args.confirm_device_run:
        print(json.dumps({"status": "refused", "reason": "confirmation-required"}))
        return 2
    if not 1 <= args.iterations <= 12:
        print(json.dumps({"status": "blocked", "reason": "iterations-out-of-range"}))
        return 2
    runner = asyncio.Runner(
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None
    )
    with runner:
        report = runner.run(
            _run_canary(
                state_root=args.state_root,
                run_id=args.run_id,
                iterations=args.iterations,
                monitor_frame_projection=bool(args.monitor_frame_projection),
            )
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
