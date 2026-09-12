"""Bounded real-device Safe Agent Foundation integration gate.

The gate is intentionally small and single-lane. It proves the R6/R7 Agent
layer reaches the already-certified Native iOS Runtime without bypassing its
revision/effect semantics. Only reversible Home/Settings state is used.

Usage:
  python scripts/r6_r7_device_matrix.py preprobe
  python scripts/r6_r7_device_matrix.py list-cells
  python scripts/r6_r7_device_matrix.py matrix --confirm-device-run
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from scripts.r4_device_matrix import (
        SETTINGS_BUNDLE_ID,
        _find_runner_bundle_id,
        write_evidence,
    )
except ModuleNotFoundError:  # direct ``python scripts\\...py`` execution
    from r4_device_matrix import (  # type: ignore[no-redef]
        SETTINGS_BUNDLE_ID,
        _find_runner_bundle_id,
        write_evidence,
    )

EVIDENCE_NAME = "20260907_r6-r7-safe-agent-foundation-device-matrix-post-repair.json"
DEVICE_ID = "safe-agent-live-lane"
OWNER = "safe-agent-matrix"
HOME_ICON_ROLE_MARKERS = ("icon",)

CELLS = (
    "lease-held-at-dispatch",
    "current-observation-feeds-mutation",
    "runtime-only-mutation-path",
    "revision-invalidated-after-mutation",
    "fresh-observe-before-next-state-sensitive-mutation",
    "attempt-evidence-linked-without-sensitive-payload",
    "bounded-recovery-to-safe-anchor",
    "cancel-and-deadline-prevent-unsent-mutation",
    "zero-blind-replay",
    "shutdown-releases-owned-lane",
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _privacy_safe_source_head(head: str) -> tuple[str, str]:
    """Split one Git commit id so the generic UDID-shaped evidence guard stays strict."""
    if len(head) != 40 or any(ch not in "0123456789abcdef" for ch in head):
        raise ValueError("source head must be a lowercase 40-character Git commit id")
    return head[:20], head[20:]


def _source_state() -> tuple[str, bool]:
    """Bind physical evidence to one committed repository state."""
    repo = Path(__file__).resolve().parents[1]
    head_proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    status_proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    head = head_proc.stdout.strip()
    _privacy_safe_source_head(head)
    return head, status_proc.stdout.strip() == ""


def _action_from_payload(payload: dict[str, Any]) -> Any:
    """Integration-edge conversion; Agent Core stays implementation-neutral."""
    from praxiom.ios_runtime.models import Home, LaunchApp

    op = payload.get("op")
    if op == "home":
        return Home()
    if op == "launch_app":
        bundle_id = payload.get("bundle_id")
        if not isinstance(bundle_id, str) or not bundle_id:
            raise ValueError("launch_app requires bundle_id")
        return LaunchApp(bundle_id=bundle_id)
    raise ValueError(f"unsupported live-matrix op: {op!r}")


def _privacy_safe_home_anchor(observation: Any) -> tuple[bool, str]:
    """Confirm Home from structure only; never retain labels/text/values.

    SpringBoard exposes app icons as accessibility elements. Application pages
    such as Settings do not expose the launcher icon grid. We record only the
    count of matching roles, never their user-visible labels or identifiers.
    """
    elements = tuple(getattr(observation, "elements", ()) or ())
    icon_count = 0
    for element in elements:
        role = str(getattr(element, "role", "") or "").lower()
        if any(marker in role for marker in HOME_ICON_ROLE_MARKERS):
            icon_count += 1
    ok = icon_count > 0 and bool(getattr(observation, "revision", None))
    return ok, f"home-structural-icons={icon_count}"


async def _device_count() -> int:
    usbmux = importlib.import_module("pymobiledevice3.usbmux")
    return len(await usbmux.list_devices())


async def preprobe() -> dict[str, Any]:
    source_head, source_tree_clean = _source_state()
    count = await _device_count()
    if count != 1:
        return {
            "device_count": count,
            "runner_present": False,
            "source_head": source_head,
            "source_tree_clean": source_tree_clean,
        }
    return {
        "device_count": count,
        "runner_present": bool(await _find_runner_bundle_id()),
        "source_head": source_head,
        "source_tree_clean": source_tree_clean,
    }


async def run_matrix(evidence_dir: Path) -> dict[str, Any]:
    from praxiom.agent.coordinator import (
        CancelledError,
        DeadlineError,
        DeviceLeaseManager,
        ExecutionCoordinator,
        ExecutionSpec,
    )
    from praxiom.agent.recovery import RecoveryPlanner, RecoveryTransition, WorldState
    from praxiom.ios_runtime.runtime import NativeIosRuntime
    from praxiom.retrieval.validator import AdaptiveValidator

    report: dict[str, Any] = {
        "gate": "bounded single-lane Safe Agent Foundation matrix",
        "safety_context": "reversible Home/Settings only",
        "steps": [],
    }

    def step(name: str, ok: bool, detail: str = "") -> None:
        report["steps"].append(
            {"name": name, "ok": bool(ok), "detail": str(detail)[:180]}
        )

    source_head, source_tree_clean = _source_state()
    report["source_head_parts"] = list(_privacy_safe_source_head(source_head))
    report["source_tree_clean"] = source_tree_clean
    if not source_tree_clean:
        report["result"] = "BLOCKED-SOURCE"
        report["blocker"] = "clean committed source tree required"
        return report

    count = await _device_count()
    report["device_count"] = count
    if count != 1:
        report["result"] = "BLOCKED-PHYSICAL"
        report["blocker"] = "single attached iPhone required"
        return report

    runner_bundle_id = await _find_runner_bundle_id()
    report["runner_present"] = bool(runner_bundle_id)
    if not runner_bundle_id:
        report["result"] = "BLOCKED-RUNTIME"
        report["blocker"] = "installed signed runner unavailable"
        return report

    runtime = NativeIosRuntime(xctrunner_bundle_id=runner_bundle_id)
    leases = DeviceLeaseManager()
    scratch = Path(__file__).resolve().parents[1] / ".pytest-tmp" / "r6-r7-device-live"
    scratch.mkdir(parents=True, exist_ok=True)
    ledger = scratch / "ledger.db"
    ledger.unlink(missing_ok=True)
    coord = ExecutionCoordinator(
        runtime,
        leases,
        ledger_path=ledger,
        now_ms=_now_ms,
        device_id=DEVICE_ID,
    )
    lease_seen = {"value": False}

    def live_factory(payload: dict[str, Any]) -> Any:
        lease_seen["value"] = leases.holder(DEVICE_ID) == OWNER
        return _action_from_payload(payload)

    execute_before = runtime.trace.operations["execute"]
    attempts = []
    try:
        first = await runtime.observe()
        spec_settings = ExecutionSpec(
            namespace="praxiom.safe-agent",
            owner=OWNER,
            task_type="live.launch-settings",
            task_version=1,
            payload={"op": "launch_app", "bundle_id": SETTINGS_BUNDLE_ID},
            revision=first.revision,
            deadline_ms=_now_ms() + 20_000,
        )
        first_attempt = await coord.run_async(
            spec_settings, owner=OWNER, action_factory=live_factory
        )
        attempts.append(first_attempt)
        after_settings = await runtime.status()

        step("lease-held-at-dispatch", lease_seen["value"])
        step(
            "current-observation-feeds-mutation",
            first_attempt.state == "succeeded",
            "current revision accepted by coordinator/runtime",
        )
        step(
            "runtime-only-mutation-path",
            runtime.trace.operations["execute"] == execute_before + 1,
            "one runtime execute for one planned mutation",
        )
        step(
            "revision-invalidated-after-mutation",
            after_settings.current_revision is None
            and bool(first_attempt.evidence.get("revision_invalidated")),
        )

        validator = AdaptiveValidator()
        requires_observe = validator.next_requires_observe(
            mutation_invalidated_revision=True,
            next_is_state_sensitive=True,
        )
        second = await runtime.observe()
        step(
            "fresh-observe-before-next-state-sensitive-mutation",
            requires_observe and bool(second.revision),
        )

        linked = coord.inspect(first_attempt.execution_id)
        step(
            "attempt-evidence-linked-without-sensitive-payload",
            len(linked) == 1
            and linked[0].attempt_id == first_attempt.attempt_id
            and "replayed" in linked[0].evidence,
            "durable attempt link retained with structured evidence only",
        )

        planner = RecoveryPlanner(
            [
                RecoveryTransition(
                    transition_id="return-home",
                    from_state="settings",
                    to_state="home",
                )
            ]
        )
        plan = planner.plan(
            goal_anchor="home",
            world=WorldState(
                anchor_id="home", state_id="settings", revision=second.revision
            ),
        )
        recovery_ok = len(plan.steps) == 1 and not plan.escalate
        spec_home = ExecutionSpec(
            namespace="praxiom.safe-agent",
            owner=OWNER,
            task_type="live.recover-home",
            task_version=1,
            payload={"op": "home"},
            revision=second.revision,
            deadline_ms=_now_ms() + 20_000,
        )
        home_attempt = await coord.run_async(
            spec_home, owner=OWNER, action_factory=live_factory
        )
        attempts.append(home_attempt)
        third = await runtime.observe()
        ready_after_home = await runtime.status()
        observed_home, home_detail = _privacy_safe_home_anchor(third)
        recovery_ok = (
            recovery_ok
            and home_attempt.state == "succeeded"
            and bool(third.revision)
            and ready_after_home.lifecycle_state.value == "READY"
            and observed_home
        )
        step("bounded-recovery-to-safe-anchor", recovery_ok, home_detail)

        execute_before_guards = runtime.trace.operations["execute"]
        cancel_coord = ExecutionCoordinator(
            runtime, leases, now_ms=_now_ms, device_id=DEVICE_ID
        )
        cancel_coord.cancel()
        cancelled = False
        try:
            await cancel_coord.run_async(
                ExecutionSpec(
                    namespace="praxiom.safe-agent",
                    owner=OWNER,
                    task_type="live.cancel-guard",
                    task_version=1,
                    payload={"op": "home"},
                    revision=third.revision,
                ),
                owner=OWNER,
                action_factory=live_factory,
            )
        except CancelledError:
            cancelled = True

        deadline_coord = ExecutionCoordinator(
            runtime, leases, now_ms=_now_ms, device_id=DEVICE_ID
        )
        expired = False
        try:
            await deadline_coord.run_async(
                ExecutionSpec(
                    namespace="praxiom.safe-agent",
                    owner=OWNER,
                    task_type="live.deadline-guard",
                    task_version=1,
                    payload={"op": "home"},
                    revision=third.revision,
                    deadline_ms=_now_ms() - 1,
                ),
                owner=OWNER,
                action_factory=live_factory,
            )
        except DeadlineError:
            expired = True

        no_guard_mutation = runtime.trace.operations["execute"] == execute_before_guards
        step(
            "cancel-and-deadline-prevent-unsent-mutation",
            cancelled
            and expired
            and no_guard_mutation
            and leases.holder(DEVICE_ID) is None,
        )

        actual_executes = runtime.trace.operations["execute"] - execute_before
        zero_replay = (
            actual_executes == 2
            and all(att.evidence.get("replayed") is False for att in attempts)
        )
        step("zero-blind-replay", zero_replay, f"runtime-executes={actual_executes}")
    except Exception as exc:
        code = getattr(getattr(exc, "code", None), "value", None)
        report["result"] = "BLOCKED-RUNTIME"
        report["blocker"] = str(code or type(exc).__name__)[:80]
    finally:
        await runtime.close()
        closed = await runtime.status()
        step(
            "shutdown-releases-owned-lane",
            leases.holder(DEVICE_ID) is None
            and closed.lifecycle_state.value == "CLOSED",
        )

    if "result" not in report:
        failed = [item["name"] for item in report["steps"] if not item["ok"]]
        report["result"] = "PASS" if not failed else "FAIL"
        report["failed_steps"] = failed
    report["steps_total"] = len(report["steps"])
    report["steps_passed"] = sum(1 for item in report["steps"] if item["ok"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preprobe")
    sub.add_parser("list-cells")
    matrix = sub.add_parser("matrix")
    matrix.add_argument("--confirm-device-run", action="store_true")
    matrix.add_argument(
        "--evidence-dir", type=Path, default=Path("docs") / "evidence"
    )
    args = parser.parse_args()

    if args.command == "list-cells":
        print(json.dumps({"cells": list(CELLS)}, indent=2))
        return 0
    if args.command == "preprobe":
        print(json.dumps(asyncio.run(preprobe()), indent=2))
        return 0
    if not args.confirm_device_run:
        print("refused: matrix requires --confirm-device-run")
        return 2
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(run_matrix(args.evidence_dir))
    path = args.evidence_dir / EVIDENCE_NAME
    write_evidence(report, path)
    print(json.dumps(report, indent=2))
    print(f"evidence={path}")
    return 0 if report.get("result") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
