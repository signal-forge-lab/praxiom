"""Read-only target-discovery probe for the current Merge Boss entry route.

The probe performs only already-accepted generic mutations: launch the current
test application once and return Home once. Between them it inspects the fresh
Runtime observation for exact, predeclared semantic anchors. It never taps a
Merge Boss/account/play target and never persists arbitrary UI text.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from praxiom.domain.system import LAUNCH_APPLICATION, RETURN_HOME
from praxiom.ios_runtime.foreground import inspect_active_application_info
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
from phasec_limited_canary import (  # noqa: E402
    _discover_endpoint,
    _home_anchor,
    _runtime_and_transport,
)


REPORT_NAME = "mergeboss_entry_target_report.json"
MERGE_BOSS_LABELS = ("マージボス", "Merge Boss")
ACCOUNT_LABELS = ("アカウント", "Account", "My Account")
PLAY_LABELS = ("プレイ", "Play")
MERGE_BOSS_KEYWORDS = ("マージ", "ボス", "merge", "boss", "game", "ゲーム")
ACCOUNT_KEYWORDS = ("アカウント", "account", "my account")
PLAY_KEYWORDS = ("プレイ", "play", "start", "開始")


@dataclass(frozen=True, kw_only=True)
class TargetProjection:
    target_kind: str
    count: int
    bindable_count: int
    unique_bindable: bool
    semantic_cluster_count: int
    single_semantic_cluster: bool
    bindable_button_count: int
    roles: tuple[str, ...]
    matched_fields: tuple[str, ...]


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def _matching_elements(
    observation: Any,
    labels: Iterable[str],
    *,
    contains: bool = False,
) -> list[tuple[Any, str]]:
    expected = {_normalize(item) for item in labels}
    matches: list[tuple[Any, str]] = []
    for element in tuple(getattr(observation, "elements", ()) or ()):
        for field in ("label", "text", "value"):
            value = getattr(element, field, None)
            if not isinstance(value, str):
                continue
            normalized = _normalize(value)
            matched = (
                any(token and token in normalized for token in expected)
                if contains
                else normalized in expected
            )
            if matched:
                matches.append((element, field))
                break
    return matches


def _same_visual_cluster(left: Any, right: Any) -> bool:
    """Treat strongly overlapping/nested fresh rectangles as one control cluster."""
    a = getattr(left, "rect", None)
    b = getattr(right, "rect", None)
    if a is None or b is None:
        return False
    ax2, ay2 = a.x + a.width, a.y + a.height
    bx2, by2 = b.x + b.width, b.y + b.height
    iw = max(0, min(ax2, bx2) - max(a.x, b.x))
    ih = max(0, min(ay2, by2) - max(a.y, b.y))
    intersection = iw * ih
    smaller = min(max(0, a.width * a.height), max(0, b.width * b.height))
    return smaller > 0 and intersection / smaller >= 0.8


def _semantic_cluster_count(elements: list[Any]) -> int:
    clusters: list[list[Any]] = []
    for element in elements:
        for cluster in clusters:
            if any(_same_visual_cluster(element, member) for member in cluster):
                cluster.append(element)
                break
        else:
            clusters.append([element])
    return len(clusters)


def _project_target(
    observation: Any,
    *,
    target_kind: str,
    labels: Iterable[str],
    contains: bool = False,
) -> TargetProjection:
    matches = _matching_elements(observation, labels, contains=contains)
    bindable = [
        (element, field)
        for element, field in matches
        if bool(getattr(element, "ref", ""))
        and getattr(element, "rect", None) is not None
        and getattr(element, "enabled", None) is not False
        and getattr(element, "visible", None) is not False
    ]
    cluster_count = _semantic_cluster_count([element for element, _ in bindable])
    button_count = sum(
        1
        for element, _ in bindable
        if str(getattr(element, "role", "")) == "XCUIElementTypeButton"
    )
    return TargetProjection(
        target_kind=target_kind,
        count=len(matches),
        bindable_count=len(bindable),
        unique_bindable=len(bindable) == 1,
        semantic_cluster_count=cluster_count,
        single_semantic_cluster=cluster_count == 1 and bool(bindable),
        bindable_button_count=button_count,
        roles=tuple(sorted({str(getattr(item[0], "role", "")) for item in matches})),
        matched_fields=tuple(sorted({field for _, field in matches})),
    )


def _persist_report(session: RunSession, report: dict[str, Any]) -> Path:
    projected = {
        "schema_version": 1,
        "run_id": report.get("run_id"),
        "status": report.get("status"),
        "phase": "phase-c-domain-target-probe",
        "domain": "mergeboss",
        "targets": report.get("targets"),
        "foreground_verified": report.get("foreground_verified"),
        "launch_attempt": report.get("launch_attempt"),
        "home_cleanup": report.get("home_cleanup"),
        "summary": report.get("summary"),
        "privacy": {
            "arbitrary_ui_text_persisted": False,
            "element_refs_persisted": False,
            "coordinates_persisted": False,
            "bundle_id_persisted": False,
        },
    }
    target = session.context.run_dir / REPORT_NAME
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(projected, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


async def _run(*, state_root: Path | str | None, run_id: str | None) -> dict[str, Any]:
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
        max_workers=1, thread_name_prefix="praxiom-phasec-mergeboss-target"
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
        "targets": {},
    }
    try:
        launch_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                LAUNCH_APPLICATION,
                evidence_prefix="phasec:mergeboss-target:launch",
            ),
        )
        home_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                RETURN_HOME,
                evidence_prefix="phasec:mergeboss-target:cleanup-home",
            ),
        )

        pre = await _observe_bounded(runtime)
        if _observation_is_locked(pre) or not pre.revision:
            raise RuntimeError("fresh-unlocked-pre-observation-required")

        def execute_launch():
            return session.execute_skill(
                launch_skill,
                revision=pre.revision,
                op="launch_app",
                extra={"bundle_id": app_bundle},
                shadow_pending=1,
            )

        launch = await loop.run_in_executor(worker, execute_launch)
        replayed = bool(
            launch.evidence.get("replayed", False)
            if isinstance(launch.evidence, dict)
            else False
        )
        report["launch_attempt"] = {
            "state": str(launch.state),
            "effect": str(launch.effect),
            "replayed": replayed,
        }
        if launch.state != "succeeded" or launch.effect != "NONE" or replayed:
            raise RuntimeError("generic-launch-not-clean")

        active = inspect_active_application_info(
            await transport.active_application_info(), app_bundle
        )
        report["foreground_verified"] = bool(active.expected_match)
        if not active.expected_match:
            raise RuntimeError("expected-application-not-foreground")

        observation = await _observe_bounded(runtime)
        if not observation.revision:
            raise RuntimeError("fresh-target-observation-required")
        projections = (
            _project_target(
                observation, target_kind="merge-boss-entry", labels=MERGE_BOSS_LABELS
            ),
            _project_target(
                observation, target_kind="account-anchor", labels=ACCOUNT_LABELS
            ),
            _project_target(
                observation, target_kind="play-control", labels=PLAY_LABELS
            ),
            _project_target(
                observation,
                target_kind="merge-boss-keyword-hints",
                labels=MERGE_BOSS_KEYWORDS,
                contains=True,
            ),
            _project_target(
                observation,
                target_kind="account-keyword-hints",
                labels=ACCOUNT_KEYWORDS,
                contains=True,
            ),
            _project_target(
                observation,
                target_kind="play-keyword-hints",
                labels=PLAY_KEYWORDS,
                contains=True,
            ),
        )
        report["targets"] = {
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

        def execute_home():
            return session.execute_skill(
                home_skill,
                revision=observation.revision,
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
            raise RuntimeError("home-cleanup-not-clean")

        report["status"] = "completed"
        return report
    except BaseException as exc:
        close_status = "failed"
        close_reason = "phasec-mergeboss-target-probe-exception"
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
                    "observe": summary.get("observe"),
                    "execute": summary.get("execute"),
                    "sequences": summary.get("sequences"),
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
    args = parser.parse_args()
    if not args.confirm_device_run:
        print(json.dumps({"status": "refused", "reason": "confirmation-required"}))
        return 2
    runner = asyncio.Runner(
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None
    )
    with runner:
        report = runner.run(_run(state_root=args.state_root, run_id=args.run_id))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
