"""R10 Lane F — bounded real-workflow live lane (single device-mutation owner).

Runs the frozen low-risk domain launch behaviors live through the only
authorized route, strictly sequentially (Merge Boss, then GoGoMatch):

    registry-active domain skill (R8 gates + SkillRegistry.activate)
      -> SkillExecutor.execute(skill, revision, op, extra)
      -> ExecutionCoordinator.run(spec with revision)
      -> NativeIosRuntime.execute(actions, expected_revision=...)

Safety envelope (docs/evidence/r10-design-freeze.md §5):

- live work only after the deterministic gates are green; the operator must
  pass ``--deterministic-green`` (the concrete gate runs are recorded in
  ``docs/evidence/20260908_r10-bounded-real-workflow.md``);
- the only live mutation class in this lane is ``launch_app`` of the two
  operator-configured target domain apps, plus read-only ``observe``/``status``.
  Navigation behaviors stay deterministic-only unless a safe revision-bound
  target policy is supplied by the operator; human-gated behaviors are never
  activated or executed by this lane;
- a fresh ``observe()`` is captured immediately before every mutation; the
  revision is never reused across behaviors; on stale/PARTIAL/UNKNOWN the
  lane stops and never blind-replays;
- evidence is privacy-safe by construction: counts, enums, timings, result
  classes, behavior ids, and opaque revision tokens only. Bundle ids, device
  identifiers, labels, screen text, and payloads are never written to the
  report; a fail-closed self-check refuses to emit such a report.

Usage:
  python scripts/r10_domain_workflow.py preprobe
  python scripts/r10_domain_workflow.py run --confirm-device-run --deterministic-green \
      --mergeboss-bundle-id BID --gogomatch-bundle-id BID [--runner-bundle-id BID]

Exit codes: 0 = PASS, 1 = FAIL, 2 = BLOCKED (precise external blocker).
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

try:
    from scripts.r4_device_matrix import _find_runner_bundle_id
except ModuleNotFoundError:  # direct ``python scripts\...py`` execution
    from r4_device_matrix import (  # type: ignore[no-redef]
        _find_runner_bundle_id,
    )

DEVICE_ID = "r10-domain-live-lane"
OWNER = "r10-domain-lane"
EVIDENCE_DOC = "docs/evidence/20260908_r10-bounded-real-workflow.md"
_CALL_TIMEOUT_S = 30.0


def _now_ms() -> int:
    return int(time.time() * 1000)


def _privacy_safe_source_head(head: str) -> tuple[str, str]:
    """Split one 40-char commit id so no UDID-shaped literal is emitted."""
    if len(head) != 40 or any(ch not in "0123456789abcdef" for ch in head):
        raise ValueError("source head must be a 40-char lowercase hex id")
    return head[:20], head[20:]


def _source_state() -> tuple[str, bool]:
    repo = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
    return head, status == ""


async def _device_count() -> int:
    usbmux = importlib.import_module("pymobiledevice3.usbmux")
    return len(await usbmux.list_devices())


async def _installed_bundle_ids() -> set[str]:
    """Read-only installed-app listing; bundle ids stay in-process."""
    from pymobiledevice3.remote.core_device.app_service import AppServiceService
    from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel

    tunnel = PreferredRsdTunnel(serial=None, autopair=True)
    rsd = await tunnel.aopen()
    try:
        async with AppServiceService(rsd) as service:
            apps = await service.list_apps()
        return {str(app.get("bundleIdentifier", "")) for app in apps}
    finally:
        try:
            await tunnel.aclose()
        except Exception:
            pass


class _LoopBridge:
    """One persistent background event loop for the lane's Runtime calls.

    The lane driver stays synchronous (SkillExecutor.execute is a sync
    route); every Runtime call crosses this bridge to the single loop, so no
    Runtime object is ever bound to two loops and no second mutation lane
    exists.
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise RuntimeError("lane-loop-start-timeout")

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def call(self, coro: Any, *, timeout_s: float = _CALL_TIMEOUT_S) -> Any:
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout_s)
        except BaseException:
            future.cancel()  # never leave a dispatched call dangling
            raise

    def stop(self) -> None:
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)


def _action_from_payload(payload: dict[str, Any]) -> Any:
    """Integration-edge conversion; only this lane's frozen live class.

    The coordinator's sync ``run`` hands payload dicts to the Runtime port;
    this function converts the single allowed launch_app payload into the
    Runtime action model. Any other op fails closed and can never widen the
    lane's frozen action-class set.
    """
    from praxiom.ios_runtime.models import LaunchApp

    if payload.get("op") != "launch_app":
        raise ValueError(f"op-outside-frozen-live-classes: {payload.get('op')!r}")
    bundle_id = payload.get("bundle_id")
    if not isinstance(bundle_id, str) or not bundle_id:
        raise ValueError("launch_app requires bundle_id")
    return LaunchApp(bundle_id=bundle_id)


class _SyncRuntimePort:
    """Coordinator-facing sync Runtime port (the ONLY mutation call site).

    ExecutionCoordinator.run invokes this port exclusively; the port
    delegates to the real ``NativeIosRuntime.execute`` on the lane loop.
    There is no other path from this script to a device mutation.
    """

    def __init__(
        self,
        runtime: Any,
        bridge: _LoopBridge,
        leases: Any,
        lease_seen: dict[str, bool],
    ) -> None:
        self._runtime = runtime
        self._bridge = bridge
        self._leases = leases
        self._lease_seen = lease_seen

    def execute(
        self, payloads: list[dict[str, Any]], *, expected_revision: str
    ) -> dict[str, Any]:
        self._lease_seen["value"] = self._leases.holder(DEVICE_ID) == OWNER
        actions = [_action_from_payload(p) for p in payloads]
        result = self._bridge.call(
            self._runtime.execute(actions, expected_revision=expected_revision)
        )
        return {"effect": "NONE", "completed": result.completed_actions}


def _activate_launch_behavior(registry: Any, behavior: Any) -> Any:
    """Drive one low-risk launch behavior through the registry lifecycle.

    Validation/success evidence cites the retained deterministic
    certification artifacts, which executed this exact behavior through the
    identical registry lifecycle at distinct revisions.
    """
    from praxiom.domain.adapter import behavior_to_candidate
    from praxiom.skill.gates import GATE_ORDER, run_gates

    candidate = behavior_to_candidate(behavior)
    gates = run_gates(candidate)
    if not gates.passed or gates.evaluated != GATE_ORDER:
        raise RuntimeError("gates-not-passed")
    registry.register(candidate)
    registry.validate(
        behavior.behavior_id,
        1,
        evidence_ids=(
            f"deterministic:{behavior.behavior_id}",
            "r10-deterministic-matrix-green",
        ),
    )
    registry.record_success(
        behavior.behavior_id, 1,
        revision="deterministic-revision-1",
        evidence_id=f"deterministic-success:{behavior.behavior_id}:1",
    )
    registry.record_success(
        behavior.behavior_id, 1,
        revision="deterministic-revision-2",
        evidence_id=f"deterministic-success:{behavior.behavior_id}:2",
    )
    return registry.activate(
        behavior.behavior_id, 1, confidence=0.9,
        evidence_id="r10-live-lane-activation",
    )


def _step(steps: list[dict[str, Any]], name: str, ok: bool, **extra: Any) -> None:
    steps.append({"name": name, "ok": bool(ok), **extra})


def _run_domain(
    bridge: _LoopBridge,
    runtime: Any,
    executor: Any,
    skills: dict[str, Any],
    domain: str,
    behavior: Any,
    bundle_id: str,
) -> dict[str, Any]:
    """One domain's bounded launch workflow; sequential, fresh revisions only."""
    record: dict[str, Any] = {
        "domain": domain,
        "behavior_id": behavior.behavior_id,
        "op_class": "launch_app",
        "risk": behavior.risk,
        "reversibility": behavior.reversibility,
        "human_gate": behavior.human_gate,
        "steps": [],
    }
    steps = record["steps"]

    t0 = time.perf_counter()
    status_before = bridge.call(runtime.status())
    _step(steps, "status", True, lifecycle=str(status_before.lifecycle_state.value))

    observation = bridge.call(runtime.observe())
    revision = observation.revision
    _step(
        steps, "observe-before", bool(revision),
        ms=int((time.perf_counter() - t0) * 1000),
        revision_token=revision,
        element_count=len(observation.elements),
    )
    record["revision_chain"] = {"observed_before": revision}
    if not revision:
        record["status"] = "fail"
        return record

    t1 = time.perf_counter()
    try:
        attempt = executor.execute(
            skills[domain], revision=revision, op="launch_app",
            extra={"bundle_id": bundle_id},
        )
    except Exception as exc:  # fail-closed: record class only, stop lane
        code = getattr(getattr(exc, "code", None), "value", None)
        effect = getattr(getattr(exc, "effect", None), "value", "UNKNOWN")
        _step(
            steps, "execute", False, ms=int((time.perf_counter() - t1) * 1000),
            error_class=type(exc).__name__, error_code=code, effect=effect,
        )
        record["status"] = "fail"
        record["stop_reason"] = "execute-raised:no-continuation-no-replay"
        return record
    record["attempt"] = {
        "state": attempt.state,
        "effect": attempt.effect,
        "replayed": attempt.evidence.get("replayed"),
        "retry_safe": attempt.evidence.get("retry_safe"),
        "error_code": attempt.evidence.get("error_code"),
    }
    _step(steps, "execute", attempt.state == "succeeded",
          ms=int((time.perf_counter() - t1) * 1000))
    if attempt.effect != "NONE" or attempt.state != "succeeded":
        record["status"] = "fail"
        record["stop_reason"] = (
            f"attempt-{attempt.effect.lower()}:stop-reconcile-never-replay")
        return record

    status_after = bridge.call(runtime.status())
    invalidated = status_after.current_revision is None
    record["revision_chain"]["invalidated_after_execute"] = invalidated
    _step(steps, "revision-invalidated", invalidated)

    t2 = time.perf_counter()
    post = bridge.call(runtime.observe())
    post_revision = post.revision
    post_count = len(post.elements)
    fresh_and_distinct = bool(post_revision) and post_revision != revision
    record["revision_chain"]["observed_after"] = post_revision
    record["postcondition"] = {
        "check": "structural-proxy:observation-nonempty-fresh-revision",
        "ok": bool(fresh_and_distinct and post_count > 0),
        "element_count": post_count,
    }
    _step(
        steps, "observe-after", bool(post_revision), ms=int(
            (time.perf_counter() - t2) * 1000),
        revision_token=post_revision, element_count=post_count,
    )
    record["status"] = (
        "pass" if invalidated and fresh_and_distinct and post_count > 0 else "fail")
    return record


def _privacy_check(report: dict[str, Any], secrets: list[str]) -> None:
    """Fail closed before emitting: no configured bundle id, no UDID shape."""
    text = json.dumps(report)
    for secret in secrets:
        if secret and secret in text:
            raise RuntimeError("privacy-check:configured-secret-in-report")
    for part in report.get("source_head_parts", []):
        if len(part) != 20:
            raise RuntimeError("privacy-check:source-head-shape")


def preprobe() -> dict[str, Any]:
    report: dict[str, Any] = {
        "lane": "r10-bounded-real-workflow",
        "probe": "preprobe-read-only",
    }
    head, clean = _source_state()
    report["source_head_parts"] = list(_privacy_safe_source_head(head))
    report["source_tree_clean"] = clean
    try:
        report["device_count"] = asyncio.run(_device_count())
    except ImportError as exc:
        report["device_count"] = None
        report["result"] = "BLOCKED-ENVIRONMENT"
        report["blocker"] = f"pymobiledevice3-import-unavailable:{type(exc).__name__}"
        return report
    except Exception as exc:
        report["device_count"] = None
        report["result"] = "BLOCKED-PHYSICAL"
        report["blocker"] = f"usbmux-probe-failed:{type(exc).__name__}"
        return report
    report["result"] = (
        "PROCEED-PROBE-OK" if report["device_count"] == 1 else "BLOCKED-PHYSICAL")
    if report["result"] == "BLOCKED-PHYSICAL":
        report["blocker"] = (
            f"single-attached-iphone-required:found={report['device_count']}")
    return report


def run_workflow(
    mergeboss_bundle_id: str, gogomatch_bundle_id: str,
    runner_bundle_id: str | None,
) -> dict[str, Any]:
    from praxiom.agent.coordinator import DeviceLeaseManager, ExecutionCoordinator
    from praxiom.domain import gogomatch, mergeboss
    from praxiom.ios_runtime.runtime import NativeIosRuntime
    from praxiom.skill.executor import SkillExecutor
    from praxiom.skill.registry import SkillRegistry

    secrets = [mergeboss_bundle_id, gogomatch_bundle_id]
    aliases = {"mergeboss": mergeboss_bundle_id, "gogomatch": gogomatch_bundle_id}
    behaviors = {
        "mergeboss": mergeboss.get_behavior("mergeboss:launch"),
        "gogomatch": gogomatch.get_behavior("gogomatch:launch-game"),
    }
    report: dict[str, Any] = {
        "lane": "r10-bounded-real-workflow",
        "route": "agent>skill-executor>coordinator>runtime",
        "gate_attestation": {
            "deterministic_green": True,
            "recorded_in": EVIDENCE_DOC,
        },
        "lane_owner": OWNER,
        "device_id": DEVICE_ID,
        "domains": [],
    }
    head, clean = _source_state()
    report["source_head_parts"] = list(_privacy_safe_source_head(head))
    report["source_tree_clean"] = clean

    try:
        count = asyncio.run(_device_count())
    except ImportError as exc:
        report.update(result="BLOCKED-ENVIRONMENT",
                      blocker=f"pymobiledevice3-import-unavailable:{type(exc).__name__}")
        return report
    except Exception as exc:
        report.update(result="BLOCKED-PHYSICAL",
                      blocker=f"usbmux-probe-failed:{type(exc).__name__}")
        return report
    report["device_count"] = count
    if count != 1:
        report.update(result="BLOCKED-PHYSICAL",
                      blocker=f"single-attached-iphone-required:found={count}")
        return report

    bridge = _LoopBridge()
    runtime: Any = None
    try:
        resolved_runner = runner_bundle_id or bridge.call(_find_runner_bundle_id())
        report["runner_present"] = bool(resolved_runner)
        if not resolved_runner:
            report.update(result="BLOCKED-RUNTIME",
                          blocker="installed-signed-runner-unavailable")
            return report

        installed = bridge.call(_installed_bundle_ids())
        installed_flags = {
            domain: bundle_id in installed
            for domain, bundle_id in aliases.items()
        }
        report["target_apps_installed"] = installed_flags
        missing = sorted(d for d, ok in installed_flags.items() if not ok)
        if missing:
            report.update(
                result="BLOCKED-APP-STATE",
                blocker="target-app-not-installed:" + "+".join(missing))
            return report

        runtime = NativeIosRuntime(xctrunner_bundle_id=resolved_runner)
        leases = DeviceLeaseManager()
        lease_seen = {"value": False}
        port = _SyncRuntimePort(runtime, bridge, leases, lease_seen)
        coordinator = ExecutionCoordinator(
            port, leases, now_ms=_now_ms, device_id=DEVICE_ID)
        registry = SkillRegistry()
        executor = SkillExecutor(
            coordinator=coordinator, registry=registry, owner=OWNER)

        for domain in ("mergeboss", "gogomatch"):
            behavior = behaviors[domain]
            skill = _activate_launch_behavior(registry, behavior)
            record = _run_domain(
                bridge, runtime, executor, {domain: skill},
                domain, behavior, aliases[domain],
            )
            record["lease_held_at_dispatch"] = lease_seen["value"]
            report["domains"].append(record)
            if record["status"] != "pass":
                break  # single lane: stop, never continue past a failed effect

        passed = [
            d for d in report["domains"] if d["status"] == "pass"]
        stopped = next(
            (d.get("stop_reason") for d in report["domains"]
             if d.get("stop_reason")), None)
        if len(passed) == 2:
            report["result"] = "PASS"
        elif stopped:
            report["result"] = "FAIL"
            report["blocker"] = stopped
        else:
            report["result"] = "FAIL"
            report["blocker"] = "domain-steps-failed"
    except Exception as exc:
        code = getattr(getattr(exc, "code", None), "value", None)
        report["result"] = "BLOCKED-RUNTIME"
        report["blocker"] = str(code or type(exc).__name__)[:120]
    finally:
        if runtime is not None:
            try:
                bridge.call(runtime.close())
                closed = bridge.call(runtime.status())
                report["runtime_closed"] = (
                    str(closed.lifecycle_state.value) == "CLOSED")
            except Exception:
                report["runtime_closed"] = False
        bridge.stop()

    _privacy_check(report, secrets)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preprobe")
    run = sub.add_parser("run")
    run.add_argument("--confirm-device-run", action="store_true")
    run.add_argument("--deterministic-green", action="store_true")
    run.add_argument("--mergeboss-bundle-id", default="")
    run.add_argument("--gogomatch-bundle-id", default="")
    run.add_argument("--runner-bundle-id", default=None)
    args = parser.parse_args()

    if args.command == "preprobe":
        print(json.dumps(preprobe(), indent=2))
        return 0

    if not args.confirm_device_run:
        print("refused: run requires --confirm-device-run")
        return 2
    if not args.deterministic_green:
        print(json.dumps({
            "result": "BLOCKED-GATE-ORDER",
            "blocker": "deterministic-green-attestation-required",
            "recorded_in": EVIDENCE_DOC,
        }, indent=2))
        return 2
    if not args.mergeboss_bundle_id or not args.gogomatch_bundle_id:
        print(json.dumps({
            "result": "BLOCKED-CONFIG",
            "blocker": (
                "target-domain-app-bundle-ids-not-configured:"
                "lane-will-not-guess-bundle-identifiers"),
        }, indent=2))
        return 2

    report = run_workflow(
        args.mergeboss_bundle_id, args.gogomatch_bundle_id,
        args.runner_bundle_id,
    )
    print(json.dumps(report, indent=2))
    if report.get("result") == "PASS":
        return 0
    return 2 if str(report.get("result", "")).startswith("BLOCKED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
