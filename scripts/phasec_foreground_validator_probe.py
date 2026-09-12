"""Attached-device probe for a generic launch foreground validator.

This is Domain-specific evidence, not shared Learning logic.  It checks whether
the post-launch WDA accessibility root can prove that the expected application
is foreground without persisting application names, bundle identifiers, raw
XML, or user-visible UI text.

Mutation still flows Skill -> Coordinator -> Runtime.  The candidate validator
is read-only and never authors a Runtime revision.  Every probe sample is
corroborated by a normal fresh Runtime observation before the next mutation.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import sys
import time
from pathlib import Path
from typing import Any

from praxiom.domain.system import LAUNCH_APPLICATION, RETURN_HOME
from praxiom.ios_runtime.foreground import (
    inspect_active_application_info,
    observation_matches_foreground,
)
from praxiom.session import RunSession
from praxiom.skill.registry import SkillRegistry
from praxiom.telemetry.context import resolve_state_root


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
from phasec_limited_canary import (  # noqa: E402
    _discover_endpoint,
    _home_anchor,
    _runtime_and_transport,
)


EXPECTED_APP_NAME = "AliExpress"
CHEAP_TIMEOUT_S = 15.0
RECOVER_TIMEOUT_S = 60.0
REPORT_NAME = "foreground_validator_report.json"


def _project_probe_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return the privacy-safe durable subset of one foreground probe."""
    samples: list[dict[str, Any]] = []
    for raw in report.get("samples", ()):
        if not isinstance(raw, dict):
            continue
        samples.append(
            {
                "iteration": raw.get("iteration"),
                "launch_success_none": raw.get("launch_success_none"),
                "launch_replayed": raw.get("launch_replayed"),
                "application_node_count": raw.get("application_node_count"),
                "active_app_bundle_id_present": raw.get(
                    "active_app_bundle_id_present"
                ),
                "active_app_pid_present": raw.get("active_app_pid_present"),
                "cheap_foreground_match": raw.get("cheap_foreground_match"),
                "matched_attribute_keys": list(raw.get("matched_attribute_keys") or ()),
                "cheap_validator_latency_ms": raw.get("cheap_validator_latency_ms"),
                "cheap_validator_error_class": raw.get("cheap_validator_error_class"),
                "cheap_validator_fallback_full_observe": raw.get(
                    "cheap_validator_fallback_full_observe"
                ),
                "full_observe_foreground_match": raw.get("full_observe_foreground_match"),
                "home_restore_success_none": raw.get("home_restore_success_none"),
                "home_restore_icon_count": raw.get("home_restore_icon_count"),
            }
        )
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return {
        "schema_version": 1,
        "run_id": report.get("run_id"),
        "status": report.get("status"),
        "error_type": report.get("error_type"),
        "close_error_class": report.get("close_error_class"),
        "phase": "phase-c-validator-probe",
        "candidate_operation_class": "system:launch-application",
        "candidate_kind": "generic-foreground-application-state",
        "iterations": report.get("iterations"),
        "samples": samples,
        "privacy": {
            "raw_xml_persisted": False,
            "app_identity_persisted": False,
            "bundle_id_persisted": False,
        },
        "summary": {
            key: summary.get(key)
            for key in ("actions", "failures", "observe", "execute", "sequences")
            if key in summary
        },
    }


def _persist_probe_report(session: RunSession, report: dict[str, Any]) -> Path:
    """Atomically persist only the bounded projection under the run directory."""
    target = session.context.run_dir / REPORT_NAME
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_project_probe_report(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def _close_and_persist_probe_report(
    session: RunSession,
    report: dict[str, Any],
    *,
    close_status: str,
    close_reason: str | None,
    suppress_close_error: bool,
) -> None:
    """Close the run while preserving a durable probe report on close failure."""
    close_error: BaseException | None = None
    try:
        summary = session.close(status=close_status, reason_code=close_reason)
        report["summary"] = {
            "actions": summary.get("actions"),
            "failures": summary.get("failures"),
            "observe": summary.get("observe"),
            "execute": summary.get("execute"),
            "sequences": summary.get("sequences"),
        }
    except BaseException as exc:
        close_error = exc
        report["close_error_class"] = type(exc).__name__
        if report.get("status") == "completed":
            report["status"] = "failed"
    finally:
        _persist_probe_report(session, report)
    if close_error is not None and not suppress_close_error:
        raise close_error


def _assert_unused_run_id(state_root: Path | str | None, run_id: str | None) -> None:
    """Refuse explicit evidence-id reuse before any device discovery or mutation."""
    if not run_id:
        return
    root = Path(state_root) if state_root is not None else resolve_state_root()
    if (root / "runs" / run_id).exists():
        raise RuntimeError("run-id-already-exists")


async def _foreground_validation_with_safe_fallback(
    runtime: Any,
    transport: Any,
    expected_bundle_id: str,
) -> tuple[Any | None, float, str | None, Any, bool]:
    """Cheap foreground read plus one plumbing-only recovery/full-observe fallback.

    This helper is called only after the launch attempt is known to have
    completed with effect NONE and replayed=false. A cheap validator failure
    never replays launch: it rebuilds Runtime plumbing once and obtains a
    fresh full observation instead.
    """
    started = time.perf_counter()
    try:
        info = await asyncio.wait_for(
            transport.active_application_info(), timeout=CHEAP_TIMEOUT_S
        )
    except BaseException as exc:
        cheap_ms = (time.perf_counter() - started) * 1000.0
        try:
            await asyncio.wait_for(runtime.recover(), timeout=RECOVER_TIMEOUT_S)
        except TimeoutError as recovery_exc:
            raise RuntimeError("foreground-validator-recovery-timeout") from recovery_exc
        audit = await _observe_bounded(runtime)
        return None, cheap_ms, type(exc).__name__, audit, True

    cheap_ms = (time.perf_counter() - started) * 1000.0
    foreground = inspect_active_application_info(info, expected_bundle_id)
    # Drop raw active-app metadata immediately. Only bounded booleans survive.
    info = {}
    audit = await _observe_bounded(runtime)
    return foreground, cheap_ms, None, audit, False


async def _run_probe(*, state_root: Path | str | None, run_id: str | None, iterations: int) -> dict[str, Any]:
    _assert_unused_run_id(state_root, run_id)
    try:
        identifier, host, port = await _discover_endpoint()
    except Exception as exc:
        return {
            "status": "blocked",
            "phase": "phase-c-validator-probe",
            "candidate_kind": "generic-foreground-application-state",
            "reason": "remote-pairing-unavailable",
            "error_class": type(exc).__name__,
            "mutation_count": 0,
        }
    try:
        app_bundle, runner_bundle = await _discover_bundles(identifier, host, port)
    except Exception as exc:
        return {
            "status": "blocked",
            "phase": "phase-c-validator-probe",
            "candidate_kind": "generic-foreground-application-state",
            "reason": "device-service-unavailable",
            "error_class": type(exc).__name__,
            "mutation_count": 0,
        }
    runtime, transport = _runtime_and_transport(
        identifier=identifier,
        host=host,
        port=port,
        runner_bundle_id=runner_bundle,
        state_root=state_root,
        monitor_frame_projection=True,
    )
    loop = asyncio.get_running_loop()
    worker = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="praxiom-phasec-foreground-probe")
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
    primary_error: BaseException | None = None
    report: dict[str, Any] = {
        "run_id": session.run_id,
        "status": "running",
        "phase": "phase-c-validator-probe",
        "candidate_kind": "generic-foreground-application-state",
        "iterations": iterations,
        "samples": [],
        "privacy": {
            "raw_xml_persisted": False,
            "app_identity_persisted": False,
            "bundle_id_persisted": False,
        },
    }
    try:
        launch_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                LAUNCH_APPLICATION,
                evidence_prefix="phasec:foreground-validator:system-launch",
            ),
        )
        home_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                RETURN_HOME,
                evidence_prefix="phasec:foreground-validator:home",
            ),
        )

        for index in range(iterations):
            pre = await _observe_bounded(runtime)
            if _observation_is_locked(pre):
                raise RuntimeError("device-locked")
            if not pre.revision:
                raise RuntimeError("fresh-pre-launch-revision-required")

            def execute_launch():
                return session.execute_skill(
                    launch_skill,
                    revision=pre.revision,
                    op="launch_app",
                    extra={"bundle_id": app_bundle},
                    shadow_pending=1,
                )

            launch_attempt = await loop.run_in_executor(worker, execute_launch)
            launch_replayed = bool(
                launch_attempt.evidence.get("replayed", False)
                if isinstance(launch_attempt.evidence, dict)
                else False
            )
            if launch_attempt.state != "succeeded" or launch_attempt.effect != "NONE" or launch_replayed:
                raise RuntimeError("launch-probe-attempt-not-clean")

            foreground, cheap_ms, cheap_error_class, audit, used_full_fallback = (
                await _foreground_validation_with_safe_fallback(
                    runtime, transport, app_bundle
                )
            )
            full_match = observation_matches_foreground(audit, EXPECTED_APP_NAME)
            if not audit.revision:
                raise RuntimeError("fresh-post-launch-audit-required")

            def execute_home():
                return session.execute_skill(
                    home_skill,
                    revision=audit.revision,
                    op="home",
                    shadow_pending=1,
                )

            home_attempt = await loop.run_in_executor(worker, execute_home)
            home_replayed = bool(
                home_attempt.evidence.get("replayed", False)
                if isinstance(home_attempt.evidence, dict)
                else False
            )
            if home_attempt.state != "succeeded" or home_attempt.effect != "NONE" or home_replayed:
                raise RuntimeError("home-restore-attempt-not-clean")
            restored = await _observe_bounded(runtime)
            home_ok, home_icons = _home_anchor(restored)
            if not home_ok:
                raise RuntimeError("home-restore-anchor-failed")

            report["samples"].append(
                {
                    "iteration": index + 1,
                    "launch_success_none": True,
                    "launch_replayed": False,
                    "application_node_count": None,
                    "active_app_bundle_id_present": (
                        foreground.bundle_id_present if foreground is not None else False
                    ),
                    "active_app_pid_present": (
                        foreground.pid_present if foreground is not None else False
                    ),
                    "cheap_foreground_match": (
                        foreground.expected_match if foreground is not None else False
                    ),
                    "matched_attribute_keys": (
                        ["bundleId"]
                        if foreground is not None and foreground.expected_match
                        else []
                    ),
                    "cheap_validator_latency_ms": round(cheap_ms, 3),
                    "cheap_validator_error_class": cheap_error_class,
                    "cheap_validator_fallback_full_observe": used_full_fallback,
                    "full_observe_foreground_match": full_match,
                    "home_restore_success_none": True,
                    "home_restore_icon_count": home_icons,
                }
            )

        report["status"] = "completed"
        return report
    except BaseException as exc:
        primary_error = exc
        close_status = "failed"
        close_reason = "phasec-foreground-validator-probe-exception"
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        raise
    finally:
        try:
            await loop.run_in_executor(
                worker,
                lambda: _close_and_persist_probe_report(
                    session,
                    report,
                    close_status=close_status,
                    close_reason=close_reason,
                    suppress_close_error=primary_error is not None,
                ),
            )
        finally:
            await runtime.close()
            worker.shutdown(wait=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm-device-run", action="store_true")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--state-root", default=None)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    if not args.confirm_device_run:
        print(json.dumps({"status": "refused", "reason": "confirmation-required"}))
        return 2
    if not 1 <= args.iterations <= 5:
        print(json.dumps({"status": "blocked", "reason": "iterations-out-of-range"}))
        return 2
    try:
        _assert_unused_run_id(args.state_root, args.run_id)
    except RuntimeError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "mutation_count": 0}))
        return 2
    runner = asyncio.Runner(
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None
    )
    with runner:
        report = runner.run(
            _run_probe(
                state_root=args.state_root,
                run_id=args.run_id,
                iterations=args.iterations,
            )
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "completed" else 2 if report.get("status") == "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
