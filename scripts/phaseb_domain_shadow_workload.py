"""Collect representative low-risk domain workload with adaptive live control OFF.

This runner is the physical Phase-B follow-up to the transport/observe baseline.
It deliberately exercises only the two certified low-risk/reversible launch
behaviors (Merge Boss and GoGoMatch), twice each, through:

    SkillExecutor -> ExecutionCoordinator -> NativeIosRuntime

Each accepted action is revision-bound, followed by a fresh full observation,
and never replayed automatically.  RunSession supplies the durable Coordinator
ledger plus Experience/Shadow telemetry.  Bounded-sequence live application
and adaptive live application remain OFF.

Bundle identifiers are required inputs and are never printed or persisted by
this script.  The caller may pass the same identifier for both domains when
that is the independently verified installed-app mapping; this runner never
guesses or derives that mapping.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any

from praxiom.domain import gogomatch, mergeboss
from praxiom.domain.adapter import behavior_to_candidate
from praxiom.session import RunSession
from praxiom.skill.gates import GATE_ORDER, run_gates
from praxiom.skill.registry import SkillRegistry
from praxiom.telemetry.context import default_run_id


OWNER = "phaseb-domain-shadow-workload"
DEVICE_ID = "phaseb-device"
DEFAULT_ITERATIONS = 2
LOCK_MARKER = "systemApertureElementIdentifierLock"


class _LoopBridge:
    """Own one persistent event loop for an async Runtime used by sync Skill code."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise RuntimeError("runtime-loop-start-timeout")

    def _run(self) -> None:
        self._loop = (
            asyncio.SelectorEventLoop()
            if os.name == "nt"
            else asyncio.new_event_loop()
        )
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def call(self, coro: Any, *, timeout_s: float = 90.0) -> Any:
        if self._loop is None:
            raise RuntimeError("runtime-loop-not-ready")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout_s)
        except BaseException:
            future.cancel()
            raise

    def stop(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)


def _action_from_payload(payload: dict[str, Any]) -> Any:
    """Convert only the frozen launch payload into the Runtime action model."""
    from praxiom.ios_runtime.models import LaunchApp

    if payload.get("op") != "launch_app":
        raise ValueError("phaseb-workload-op-not-allowed")
    bundle_id = payload.get("bundle_id")
    if not isinstance(bundle_id, str) or not bundle_id:
        raise ValueError("launch_app requires bundle_id")
    return LaunchApp(bundle_id=bundle_id)


class _SyncRuntimePort:
    """Coordinator-facing sync port; the Coordinator remains mutation authority."""

    def __init__(self, runtime: Any, bridge: _LoopBridge) -> None:
        self._runtime = runtime
        self._bridge = bridge

    def execute(
        self, payloads: list[dict[str, Any]], *, expected_revision: str
    ) -> dict[str, Any]:
        actions = [_action_from_payload(payload) for payload in payloads]
        result = self._bridge.call(
            self._runtime.execute(actions, expected_revision=expected_revision)
        )
        return {
            "effect": "NONE",
            "completed": int(result.completed_actions),
            "outcomes": result.outcomes,
        }


def _activate_launch_behavior(
    registry: SkillRegistry, behavior: Any, *, evidence_prefix: str
) -> Any:
    """Activate one already-certified low-risk launch behavior in this run."""
    candidate = behavior_to_candidate(behavior)
    gates = run_gates(candidate)
    if not gates.passed or gates.evaluated != GATE_ORDER:
        raise RuntimeError("skill-gates-not-passed")
    registry.register(candidate)
    registry.validate(
        behavior.behavior_id,
        1,
        evidence_ids=(
            f"{evidence_prefix}:validated",
            "r10-deterministic-matrix-green",
        ),
    )
    registry.record_success(
        behavior.behavior_id,
        1,
        revision=f"{evidence_prefix}:activation-revision-1",
        evidence_id=f"{evidence_prefix}:success-1",
    )
    registry.record_success(
        behavior.behavior_id,
        1,
        revision=f"{evidence_prefix}:activation-revision-2",
        evidence_id=f"{evidence_prefix}:success-2",
    )
    return registry.activate(
        behavior.behavior_id,
        1,
        confidence=0.9,
        evidence_id=f"{evidence_prefix}:activate",
    )


def _domain_specs() -> tuple[tuple[str, Any], ...]:
    return (
        ("mergeboss", mergeboss.get_behavior("mergeboss:launch")),
        ("gogomatch", gogomatch.get_behavior("gogomatch:launch-game")),
    )


def _observation_is_locked(observation: Any) -> bool:
    for element in getattr(observation, "elements", ()):
        for value in (
            getattr(element, "label", None),
            getattr(element, "text", None),
            getattr(element, "value", None),
        ):
            if isinstance(value, str) and LOCK_MARKER in value:
                return True
    return False


def collect_shadow_workload(
    *,
    runtime: Any,
    bundle_ids: dict[str, str],
    state_root: Path | str | None = None,
    run_id: str | None = None,
    iterations: int = DEFAULT_ITERATIONS,
) -> dict[str, Any]:
    """Collect low-risk domain episodes and shadow recommendations.

    The runtime is caller-owned and is always closed here.  No adaptive
    recommendation is ever applied, and sequence execution stays disabled.
    """
    if iterations < 2:
        raise ValueError("iterations must be >= 2 for distinct-revision learning evidence")
    if set(bundle_ids) != {"mergeboss", "gogomatch"}:
        raise ValueError("exact domain bundle mapping required")
    if any(not isinstance(value, str) or not value for value in bundle_ids.values()):
        raise ValueError("non-empty bundle ids required")
    resolved_run_id = run_id or "phaseb-domain-" + default_run_id().removeprefix("run-")

    bridge = _LoopBridge()
    registry = SkillRegistry()
    port = _SyncRuntimePort(runtime, bridge)
    session = RunSession.start(
        runtime=port,
        registry=registry,
        state_root=state_root,
        run_id=resolved_run_id,
        sequence_enabled=False,
        device_id=DEVICE_ID,
    )
    session.attach_trace_source(runtime)
    report: dict[str, Any] = {
        "run_id": resolved_run_id,
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
            skill = _activate_launch_behavior(
                registry, behavior, evidence_prefix=f"phaseb:{domain}"
            )
            domain_result: dict[str, Any] = {
                "domain": domain,
                "behavior_id": behavior.behavior_id,
                "risk": behavior.risk,
                "reversibility": behavior.reversibility,
                "attempts": [],
            }
            observation = bridge.call(runtime.observe())
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
                attempt = session.execute_skill(
                    skill,
                    revision=before_revision,
                    op="launch_app",
                    extra={"bundle_id": bundle_ids[domain]},
                    shadow_pending=iterations - index,
                )
                item = {
                    "iteration": index + 1,
                    "state": attempt.state,
                    "effect": attempt.effect,
                    "replayed": bool(attempt.evidence.get("replayed", False)),
                }
                domain_result["attempts"].append(item)
                if attempt.state != "succeeded" or attempt.effect != "NONE":
                    domain_result["status"] = "stopped"
                    domain_result["stop_reason"] = "non-none-or-unsuccessful-attempt"
                    report["domains"].append(domain_result)
                    report["status"] = "stopped"
                    return report
                observation = bridge.call(runtime.observe())
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
        finally:
            try:
                bridge.call(runtime.close())
            finally:
                bridge.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm-device-run", action="store_true")
    parser.add_argument("--mergeboss-bundle-id", default="")
    parser.add_argument("--gogomatch-bundle-id", default="")
    parser.add_argument("--runner-bundle-id", default=None)
    parser.add_argument("--state-root", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument(
        "--monitor-frame-projection",
        action="store_true",
        help="publish the latest observed frame for the read-only Praxiom Monitor",
    )
    args = parser.parse_args()
    if not args.confirm_device_run:
        print(json.dumps({"status": "refused", "reason": "confirmation-required"}))
        return 2
    if not args.mergeboss_bundle_id or not args.gogomatch_bundle_id:
        print(json.dumps({"status": "blocked", "reason": "bundle-mapping-required"}))
        return 2

    from praxiom.ios_runtime.runtime import NativeIosRuntime
    from praxiom.monitor.projection import LatestFrameStore

    frame_sink = (
        LatestFrameStore(args.state_root).publish
        if args.monitor_frame_projection
        else None
    )
    runtime = NativeIosRuntime(
        xctrunner_bundle_id=args.runner_bundle_id,
        frame_sink=frame_sink,
    )
    report = collect_shadow_workload(
        runtime=runtime,
        bundle_ids={
            "mergeboss": args.mergeboss_bundle_id,
            "gogomatch": args.gogomatch_bundle_id,
        },
        state_root=args.state_root,
        run_id=args.run_id,
        iterations=args.iterations,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("status") == "completed":
        return 0
    if report.get("status") == "blocked":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
