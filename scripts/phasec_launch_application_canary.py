"""One-shot Phase C Adaptive Live canary for generic application launch.

This runner consumes the durable foreground-validator evidence collected by
``phasec_foreground_validator_probe.py``.  It permits exactly one live
observation-only optimization for ``system:launch-application``:

* launch remains Skill -> Coordinator -> Runtime;
* the immediate post-launch full observe may be replaced by WDA
  ``activeAppInfo`` only after the generic promotion engine says READY;
* the cheap validator never authors a Runtime revision;
* a fresh full observe still corroborates the canary before cleanup/any later
  mutation;
* sequence-live/action reduction remain OFF;
* no action is retried or replayed.

Application identity and bundle identifiers remain in-process only.
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

from praxiom.adaptive.promotion import (
    CanaryEnvironment,
    OperationEvidence,
    PromotionPolicy,
    PromotionReadiness,
    evaluate_canary_preflight,
    evaluate_promotion_readiness,
)
from praxiom.domain.system import LAUNCH_APPLICATION, RETURN_HOME
from praxiom.ios_runtime.foreground import (
    inspect_active_application_info,
    observation_matches_foreground,
)
from praxiom.retrieval.validator import ValidationContext
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
from phasec_foreground_validator_probe import (  # noqa: E402
    EXPECTED_APP_NAME,
    REPORT_NAME as VALIDATOR_REPORT_NAME,
)
from phasec_limited_canary import (  # noqa: E402
    _authorize_observation_live,
    _discover_endpoint,
    _home_anchor,
    _live_recommendation,
    _runtime_and_transport,
)


OPERATION_CLASS = "system:launch-application"
EXPECTED_FOREGROUND_ANCHOR = "foreground-application-match"
MIN_VALIDATOR_SAMPLES = 5
CHEAP_VALIDATE_TIMEOUT_S = 15.0
DEFAULT_VALIDATOR_RUN_ID = "phasec-foreground-validator-stability-20260912b"
CANARY_REPORT_NAME = "launch_application_canary_report.json"


def _state_root(state_root: Path | str | None) -> Path:
    return Path(state_root) if state_root is not None else resolve_state_root()


def _load_validator_report(
    *, state_root: Path | str | None, validator_run_id: str
) -> dict[str, Any]:
    path = _state_root(state_root) / "runs" / validator_run_id / VALIDATOR_REPORT_NAME
    if not path.is_file():
        raise RuntimeError("foreground-validator-report-missing")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("foreground-validator-report-invalid")
    return data


def _sample_shadow_ready(sample: dict[str, Any]) -> bool:
    cheap_match = sample.get("cheap_foreground_match") is True
    full_match = sample.get("full_observe_foreground_match") is True
    observed = (
        frozenset({EXPECTED_FOREGROUND_ANCHOR}) if cheap_match else frozenset()
    )
    context = ValidationContext(
        effect="NONE",
        expected_anchor=EXPECTED_FOREGROUND_ANCHOR,
        observed_labels=observed,
        confidence=1.0,
        high_risk=False,
        mismatch=not full_match or cheap_match != full_match,
    )
    decision, recommendation = _live_recommendation(context, confidence=0.95)
    return bool(
        decision.sufficient
        and recommendation.observation is not None
        and recommendation.observation.method == "cheap-validate"
        and recommendation.would_reduce_observe
        and not recommendation.would_reduce_actions
    )


def _promotion_readiness(
    *,
    state_root: Path | str | None,
    validator_run_id: str,
    fallback_proven: bool = True,
) -> tuple[PromotionReadiness, dict[str, Any]]:
    report = _load_validator_report(
        state_root=state_root, validator_run_id=validator_run_id
    )
    samples = [item for item in report.get("samples", ()) if isinstance(item, dict)]
    completed = report.get("status") == "completed"
    clean = [
        item
        for item in samples
        if item.get("launch_success_none") is True
        and item.get("launch_replayed") is False
    ]
    replay_count = sum(item.get("launch_replayed") is True for item in samples)
    causal_count = sum(
        item.get("cheap_foreground_match") is True
        and item.get("full_observe_foreground_match") is True
        and item.get("active_app_bundle_id_present") is True
        and item.get("active_app_pid_present") is True
        for item in samples
    )
    shadow_count = sum(_sample_shadow_ready(item) for item in samples)
    no_validator_fallbacks = all(
        item.get("cheap_validator_fallback_full_observe") is not True
        for item in samples
    )

    evidence = OperationEvidence(
        operation_class=OPERATION_CLASS,
        current_device_success_none=len(clean) if completed else 0,
        partial_count=0,
        unknown_count=0,
        replay_count=replay_count,
        shadow_evaluations=shadow_count,
        shadow_stable=(
            completed
            and len(samples) >= MIN_VALIDATOR_SAMPLES
            and shadow_count == len(samples)
        ),
        causal_validator_proven=(
            completed
            and len(samples) >= MIN_VALIDATOR_SAMPLES
            and causal_count == len(samples)
            and no_validator_fallbacks
        ),
        fallback_proven=bool(fallback_proven),
        teaching_conflicts=0,
        risk="low",
        reversibility="reversible",
        human_gate=False,
    )
    policy = PromotionPolicy(
        operation_class=OPERATION_CLASS,
        min_current_device_success_none=MIN_VALIDATOR_SAMPLES,
        min_shadow_evaluations=MIN_VALIDATOR_SAMPLES,
        max_partial=0,
        max_unknown=0,
        max_replay=0,
        max_teaching_conflicts=0,
        require_causal_validator=True,
        require_fallback_proof=True,
        required_risk="low",
        required_reversibility="reversible",
        allow_human_gate=False,
        allowed_surface="observation-only",
        sequence_live_allowed=False,
    )
    readiness = evaluate_promotion_readiness(policy, evidence)
    analysis = {
        "validator_run_id": validator_run_id,
        "completed": completed,
        "samples": len(samples),
        "clean_success_none": len(clean),
        "replay_count": replay_count,
        "causal_matches": causal_count,
        "shadow_evaluations": shadow_count,
        "no_validator_fallbacks": no_validator_fallbacks,
        "fallback_proven": bool(fallback_proven),
        "fallback_proof_ref": (
            "tests/test_phasec_foreground_validator_probe.py::"
            "test_cheap_validator_failure_recovers_plumbing_and_full_observes"
        ),
        "ready": readiness.ready,
        "reasons": list(readiness.reasons),
    }
    return readiness, analysis


def _persist_canary_report(session: RunSession, report: dict[str, Any]) -> Path:
    projected = {
        "schema_version": 1,
        "run_id": report.get("run_id"),
        "status": report.get("status"),
        "error_type": report.get("error_type"),
        "close_error_class": report.get("close_error_class"),
        "phase": "phase-c",
        "operation_class": OPERATION_CLASS,
        "adaptive_surface": "observation-only",
        "live_applied": report.get("live_applied"),
        "sequence_live": False,
        "attempt": report.get("attempt"),
        "cheap_validation": report.get("cheap_validation"),
        "full_audit_match": report.get("full_audit_match"),
        "home_cleanup": report.get("home_cleanup"),
        "promotion": report.get("promotion"),
        "summary": report.get("summary"),
        "privacy": {
            "app_identity_persisted": False,
            "bundle_id_persisted": False,
            "raw_response_persisted": False,
        },
    }
    target = session.context.run_dir / CANARY_REPORT_NAME
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(projected, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def _close_and_persist_canary_report(
    session: RunSession,
    report: dict[str, Any],
    *,
    close_status: str,
    close_reason: str | None,
    suppress_close_error: bool,
) -> None:
    close_error: BaseException | None = None
    try:
        summary = session.close(status=close_status, reason_code=close_reason)
        report["summary"] = {
            "actions": summary.get("actions"),
            "failures": summary.get("failures"),
            "policy": summary.get("policy"),
            "validation": summary.get("validation"),
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
        _persist_canary_report(session, report)
    if close_error is not None and not suppress_close_error:
        raise close_error


async def _run_canary(
    *,
    state_root: Path | str | None,
    run_id: str | None,
    validator_run_id: str,
) -> dict[str, Any]:
    readiness, promotion = _promotion_readiness(
        state_root=state_root, validator_run_id=validator_run_id
    )
    if not readiness.ready:
        return {
            "status": "blocked",
            "reason": "promotion-readiness-refused",
            "promotion": promotion,
            "mutation_count": 0,
        }

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
    worker = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="praxiom-phasec-launch-canary"
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
    primary_error: BaseException | None = None
    report: dict[str, Any] = {
        "run_id": session.run_id,
        "status": "running",
        "promotion": promotion,
        "live_applied": False,
    }
    try:
        launch_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                LAUNCH_APPLICATION,
                evidence_prefix="phasec:launch-application-live",
            ),
        )
        home_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                RETURN_HOME,
                evidence_prefix="phasec:launch-application-cleanup-home",
            ),
        )

        pre = await _observe_bounded(runtime)
        locked = _observation_is_locked(pre)
        status = await runtime.status()
        environment = CanaryEnvironment(
            runtime_ready=status.lifecycle_state.value == "READY",
            device_channel_ready=status.wda_state.value == "READY",
            fresh_observation_ready=bool(pre.revision),
            mutation_lane_idle=True,
            device_locked=locked,
            environment_error_class=(
                "" if status.last_error_code is None else status.last_error_code.value
            ),
        )
        gate = evaluate_canary_preflight(readiness, environment)
        if not gate.ready:
            report.update(
                status="blocked",
                reason="dynamic-canary-preflight-refused",
                preflight_reasons=list(gate.reasons),
            )
            return report
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

        attempt = await loop.run_in_executor(worker, execute_launch)
        replayed = bool(
            attempt.evidence.get("replayed", False)
            if isinstance(attempt.evidence, dict)
            else False
        )
        report["attempt"] = {
            "state": str(attempt.state),
            "effect": str(attempt.effect),
            "replayed": replayed,
        }
        if attempt.state != "succeeded" or attempt.effect != "NONE" or replayed:
            raise RuntimeError("launch-canary-attempt-not-clean")

        started = time.perf_counter()
        try:
            info = await asyncio.wait_for(
                transport.active_application_info(), timeout=CHEAP_VALIDATE_TIMEOUT_S
            )
            cheap_ms = (time.perf_counter() - started) * 1000.0
            foreground = inspect_active_application_info(info, app_bundle)
            info = {}
            observed = (
                frozenset({EXPECTED_FOREGROUND_ANCHOR})
                if foreground.expected_match
                else frozenset()
            )
            context = ValidationContext(
                effect="NONE",
                expected_anchor=EXPECTED_FOREGROUND_ANCHOR,
                observed_labels=observed,
                confidence=1.0,
                high_risk=False,
                mismatch=not foreground.expected_match,
            )
            validation_decision, recommendation = _live_recommendation(
                context, confidence=float(launch_skill.confidence)
            )
            recommendation = _authorize_observation_live(recommendation)
            report["live_applied"] = bool(recommendation.live_applied)
            report["cheap_validation"] = {
                "sufficient": bool(validation_decision.sufficient),
                "expected_match": foreground.expected_match,
                "bundle_id_present": foreground.bundle_id_present,
                "pid_present": foreground.pid_present,
                "latency_ms": round(cheap_ms, 3),
                "fallback": False,
            }
            session._note(
                session.journal.emit(
                    "validation.performed",
                    phase="validation",
                    behavior_id=OPERATION_CLASS,
                    skill_id=launch_skill.skill_id,
                    skill_version=str(launch_skill.version),
                    revision=pre.revision,
                    duration_ms=cheap_ms,
                    payload={
                        "observe_mode": "cheap_validate",
                        "confidence": float(validation_decision.confidence),
                        "reason_code": "phase-c-launch-live-causal-validator",
                        "detail": "foreground-application-match",
                    },
                )
            )
            session._note(
                session.journal.emit(
                    "policy.decision",
                    phase="policy",
                    behavior_id=OPERATION_CLASS,
                    skill_id=launch_skill.skill_id,
                    skill_version=str(launch_skill.version),
                    revision=pre.revision,
                    policy_recommendation="cheap-validate",
                    actual_policy="cheap-validate-live",
                    payload={
                        "recommended": True,
                        "actual_batch_size": 1,
                        "recommended_batch_size": 1,
                        "confidence": float(launch_skill.confidence),
                        "observe_mode": "cheap_validate",
                        "reason_code": "phase-c-launch-live-applied",
                    },
                )
            )
        except BaseException as exc:
            # The launch is never replayed.  Fall back to a fresh full observe
            # solely to reconcile state and permit safe cleanup.
            audit = await _observe_bounded(runtime)
            full_match = observation_matches_foreground(audit, EXPECTED_APP_NAME)
            report["cheap_validation"] = {
                "sufficient": False,
                "expected_match": False,
                "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
                "fallback": True,
                "error_class": type(exc).__name__,
            }
            report["full_audit_match"] = full_match
            if not audit.revision:
                raise RuntimeError("fresh-fallback-audit-required") from exc
            def execute_home_after_fallback():
                return session.execute_skill(
                    home_skill,
                    revision=audit.revision,
                    op="home",
                    shadow_pending=1,
                )

            cleanup = await loop.run_in_executor(
                worker, execute_home_after_fallback
            )
            report["home_cleanup"] = {
                "state": str(cleanup.state),
                "effect": str(cleanup.effect),
                "replayed": bool(
                    cleanup.evidence.get("replayed", False)
                    if isinstance(cleanup.evidence, dict)
                    else False
                ),
            }
            report["status"] = "fallback"
            return report

        # Full observation below is post-decision canary evidence and the
        # required fresh revision before the cleanup mutation.  It is not the
        # evidence that caused the Live decision above.
        audit = await _observe_bounded(runtime)
        full_match = observation_matches_foreground(audit, EXPECTED_APP_NAME)
        report["full_audit_match"] = full_match
        if not full_match or not audit.revision:
            raise RuntimeError("live-foreground-not-corroborated")

        def execute_home():
            return session.execute_skill(
                home_skill,
                revision=audit.revision,
                op="home",
                shadow_pending=1,
            )

        cleanup = await loop.run_in_executor(worker, execute_home)
        cleanup_replayed = bool(
            cleanup.evidence.get("replayed", False)
            if isinstance(cleanup.evidence, dict)
            else False
        )
        restored = await _observe_bounded(runtime)
        home_ok, icon_count = _home_anchor(restored)
        report["home_cleanup"] = {
            "state": str(cleanup.state),
            "effect": str(cleanup.effect),
            "replayed": cleanup_replayed,
            "home_anchor": home_ok,
            "icon_count": icon_count,
        }
        if (
            cleanup.state != "succeeded"
            or cleanup.effect != "NONE"
            or cleanup_replayed
            or not home_ok
        ):
            raise RuntimeError("launch-canary-home-cleanup-not-clean")

        report["status"] = "completed"
        return report
    except BaseException as exc:
        primary_error = exc
        close_status = "failed"
        close_reason = "phasec-launch-application-canary-exception"
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        raise
    finally:
        try:
            await loop.run_in_executor(
                worker,
                lambda: _close_and_persist_canary_report(
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
    parser.add_argument("--state-root", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--validator-run-id", default=DEFAULT_VALIDATOR_RUN_ID)
    args = parser.parse_args()
    if not args.confirm_device_run:
        print(json.dumps({"status": "refused", "reason": "confirmation-required"}))
        return 2
    runner = asyncio.Runner(
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None
    )
    with runner:
        report = runner.run(
            _run_canary(
                state_root=args.state_root,
                run_id=args.run_id,
                validator_run_id=args.validator_run_id,
            )
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
