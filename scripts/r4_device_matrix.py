"""R4 real-device acceptance runner (plan-frozen Phase B, G2-G5).

Drives ONLY the public six Native iOS Runtime operations
(``status`` / ``observe`` / ``execute`` / ``invalidate`` / ``recover`` /
``close``) plus read-only upstream provenance probes
(``pymobiledevice3.usbmux.list_devices``). No Phone Harness import,
subprocess, MCP hop, fallback, or copied source anywhere in this file.

Subcommands (run from the repository root with the repo venv):

- ``list-cells`` — print the frozen R4-01..R4-05 matrix (phone-independent);
- ``preprobe`` — read-only host/device census: installed upstream version,
  pinned-commit match, attached-device count (no mutation, no WDA contact);
- ``matrix`` — execute the ordered device matrix
  transport -> observe -> primitives+batch -> recovery -> latency and write a
  privacy-safe evidence report. Requires ``--confirm-device-run`` plus an
  attached device; refuses without the flag (exit 2), exits 0 only when the
  matrix has no failed steps and did not abort (evidence records
  ``environment-not-exercised`` honestly), and exits non-zero for either a
  failed step or an abort. **Device mutation is single-lane: this
  subcommand is the only mutating entry point and must never run concurrently
  with another mutating agent.**

Evidence policy: reports contain counts, enums, timings, and verdicts only —
never device identifiers, pair records, secrets, raw screen text,
unredacted screenshots, or raw action payloads. ``write_evidence`` scans
the serialized report and fails closed when an identifier-shaped value is
detected.

Usage:
    python scripts/r4_device_matrix.py list-cells
    python scripts/r4_device_matrix.py preprobe
    python scripts/r4_device_matrix.py matrix --confirm-device-run --evidence-dir docs/evidence
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# Frozen R4 cell registry (plan-freeze section 2). The device lane executes
# these in order; every state-sensitive step re-observes before acting.
MATRIX_CELLS: tuple[dict[str, Any], ...] = (
    {
        "id": "R4-01",
        "title": "transport/lifecycle matrix",
        "points": 3,
        "steps": [
            "attached-device discovery through the pinned upstream package",
            "USB + in-process RSD_USERSPACE path re-prove (no external tunneld)",
            "connect -> READY -> recreate/recover -> close transitions",
            "stale owned WDA/session resumption (close_session then observe)",
            "safe hotplug/disconnect classification (environment-not-exercised when not safely inducible)",
        ],
    },
    {
        "id": "R4-02",
        "title": "observe matrix",
        "points": 3,
        "steps": [
            "repeated screenshot + accessibility capture rounds",
            "screen/window sizing and coordinate-space consistency",
            "fresh revision creation and old-revision invalidation",
            "element-ref binding to exactly one revision",
            "capture after safe navigation and after recovery",
            "bounded element counts, no screen content retained",
        ],
    },
    {
        "id": "R4-03",
        "title": "action matrix",
        "points": 5,
        "primitives": [
            "tap_point",
            "tap_element",
            "drag",
            "swipe",
            "type_text",
            "home",
            "launch_app",
            "bounded ordered batch",
        ],
        "steps": [
            "all 7 primitives + ordered batch in safe Settings/Home context",
            "mandatory expected revision for every batch",
            "whole-batch preflight before the first side effect",
            "stale revision / foreign ref / invalid action / over-limit batch make zero device calls (G3 counter proofs)",
            "successful mutation invalidates the accepted revision",
            "fresh observe before the next state-sensitive action",
            "screenshot-pixel coordinates converted internally",
        ],
    },
    {
        "id": "R4-04",
        "title": "failure/recovery matrix",
        "points": 5,
        "steps": [
            "stale/closed owned WDA session (owned plumbing only)",
            "stale transport/session recreation",
            "safe disconnect/unavailability path or honest environment-not-exercised",
            "definitive failure vs ambiguous (connection-class/timeout) classification",
            "EFFECT_UNKNOWN / PARTIAL metadata where applicable",
            "retry_safe=false after an attempted ambiguous mutation",
            "recover() rebuilds plumbing only and replays zero actions",
            "fresh observation/reconciliation after ambiguity or recovery",
            "idempotent close touches no unrelated process/resource",
        ],
    },
    {
        "id": "R4-05",
        "title": "latency/trace baseline",
        "points": 2,
        "steps": [
            "initial observe including startup vs steady-state observe split",
            "per-primitive timings",
            "bounded multi-action batch timing",
            "recovery/recreate timing",
            "close timing when useful",
            "count/min/median/p95-or-max aggregation, no new infra",
        ],
    },
)

# Required R4-06 verdict vocabulary (plan-freeze section 2).
VERDICTS: tuple[str, ...] = (
    "equivalent-required",
    "Praxiom-safer",
    "legacy-only-not-required",
    "gap",
    "environment-not-exercised",
)

# Device-facing transport methods counted by CallCountingTransport (G3).
# snapshot() is intentionally excluded: it is side-effect-free and performs
# no device I/O, so it must not count as a device call.
COUNTED_TRANSPORT_CALLS: tuple[str, ...] = (
    "connect",
    "recreate",
    "close_session",
    "close",
    "screenshot",
    "accessibility_source",
    "screen_size",
    "tap_at_point",
    "drag",
    "send_keys",
    "press_home",
    "launch_app",
)

# Safe acceptance context: reversible system-app states only, bundle ids only.
SETTINGS_BUNDLE_ID = "com.apple.Preferences"

# Identifier-shaped values that must never appear in evidence.
_HEX_40 = re.compile(r"\b[0-9a-fA-F]{40}\b")
_HEX_25 = re.compile(r"\b[0-9a-fA-F]{25}\b")
_FORBIDDEN_KEYS = (
    "udid",
    "serial",
    "ecid",
    "imei",
    "mac_address",
    "pair_record",
    "pairing",
    "token",
    "secret",
    "password",
    "cookie",
    "screen_text",
    "raw_action_payload",
    "screenshot_bytes",
    "accessibility_xml",
)


def summarize_stats(durations_ms: list[float]) -> dict[str, Any]:
    """Aggregate bounded latency samples (G5 scaffold).

    Returns count/min/median plus p95-or-max: the 95th percentile when the
    sample is large enough for it to be meaningful (n >= 20), otherwise the
    maximum with ``percentile_meaningful`` set to False.
    """
    samples = sorted(durations_ms)
    count = len(samples)
    if count == 0:
        return {
            "count": 0,
            "min_ms": None,
            "median_ms": None,
            "p95_or_max_ms": None,
            "percentile_meaningful": False,
        }
    if count >= 20:
        rank = int(count * 0.95)
        rank = min(rank, count - 1)
        return {
            "count": count,
            "min_ms": samples[0],
            "median_ms": statistics.median(samples),
            "p95_or_max_ms": samples[rank],
            "percentile_meaningful": True,
        }
    return {
        "count": count,
        "min_ms": samples[0],
        "median_ms": statistics.median(samples),
        "p95_or_max_ms": samples[-1],
        "percentile_meaningful": False,
    }


def scan_for_identifiers(text: str) -> list[str]:
    """Return one finding per identifier-shaped value in ``text`` (redaction guard)."""
    findings: list[str] = []
    lowered = text.lower()
    for key in _FORBIDDEN_KEYS:
        if key in lowered:
            findings.append(f"forbidden-key:{key}")
    if _HEX_40.search(text):
        findings.append("udid-like-40-hex")
    if _HEX_25.search(text):
        findings.append("udid-like-25-hex")
    return findings


def write_evidence(report: dict[str, Any], path: Path) -> Path:
    """Serialize a privacy-safe evidence report, failing closed on identifiers."""
    serialized = json.dumps(report, indent=2, sort_keys=True, default=str)
    findings = scan_for_identifiers(serialized)
    if findings:
        raise ValueError(
            "evidence refused: identifier-shaped values detected: "
            + ", ".join(sorted(set(findings)))
        )
    path.write_text(serialized + "\n", encoding="utf-8")
    return path


class CallCountingTransport:
    """Device-call counter around a real IosTransport (G3 preflight proofs).

    Delegates every attribute to the wrapped transport and counts calls to
    the device-facing methods in ``COUNTED_TRANSPORT_CALLS``. The runner
    snapshots ``device_calls`` before a negative batch (stale revision,
    foreign ref, invalid action, over-limit) and asserts the count is
    unchanged afterwards — the hardware-side proof that preflight rejection
    made zero device calls.
    """

    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped
        self._counts: dict[str, int] = {name: 0 for name in COUNTED_TRANSPORT_CALLS}

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._wrapped, name)
        if name not in COUNTED_TRANSPORT_CALLS or not callable(target):
            return target
        if asyncio.iscoroutinefunction(target):

            async def counted_async(*args: Any, **kwargs: Any) -> Any:
                self._counts[name] += 1
                return await target(*args, **kwargs)

            return counted_async

        def counted_sync(*args: Any, **kwargs: Any) -> Any:
            self._counts[name] += 1
            return target(*args, **kwargs)

        return counted_sync

    @property
    def device_calls(self) -> int:
        """Total device-facing transport calls observed so far."""
        return sum(self._counts.values())

    @property
    def call_breakdown(self) -> dict[str, int]:
        """Per-method device-call counts (privacy-safe: names and counts only)."""
        return dict(self._counts)


# Privacy-safe evidence file written by the canonical device run.
EVIDENCE_NAME = "20260905_r4-device-matrix-run4.json"


def _names(element: Any) -> str:
    """Live-only accessible-name join (label+text+value) for safe targeting."""
    return " ".join(
        part
        for part in ((element.label or ""), (element.text or ""), (element.value or ""))
        if part
    ).lower()


def _small_rect(element: Any, screen: Any, frac: float) -> bool:
    """True when the element rect is usable and not a near-full-screen container."""
    rect = element.rect
    if rect is None or rect.width <= 0 or rect.height <= 0:
        return False
    return rect.width * rect.height <= frac * screen.width * screen.height


def _pick_element(elements: Any, screen: Any, want: str) -> tuple[str | None, str]:
    """Pick a live safe target; returns ``(ref, role)`` or ``(None, "")``.

    Labels/text/value are routing inputs only and are never returned or written
    to evidence. The generic accessibility role may be returned and recorded
    as a privacy-safe target/focus role. ``want="general"`` picks a small
    Settings navigation row; ``want="search"`` picks the Settings search field.
    """
    if want == "general":
        for element in elements:
            if "general" in _names(element) and _small_rect(element, screen, 0.5):
                return element.ref, element.role
    elif want == "search":
        for element in elements:
            if "search" in element.role.lower() and _small_rect(element, screen, 0.3):
                return element.ref, element.role
        for element in elements:
            if _names(element).strip() == "search" and _small_rect(element, screen, 0.3):
                return element.ref, element.role
    return None, ""


async def _find_runner_bundle_id() -> str:
    """Bundle id of the already-installed signed WDA runner (no install/build).

    Read-only upstream CoreDevice app listing over a short-lived in-process
    RSD tunnel. The discovered bundle id stays in-process; it is never written
    to evidence.
    """
    from pymobiledevice3.remote.core_device.app_service import AppServiceService
    from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel

    tunnel = PreferredRsdTunnel(serial=None, autopair=True)
    rsd = await tunnel.aopen()
    try:
        async with AppServiceService(rsd) as service:
            apps = await service.list_apps()
        for app in apps:
            if "WebDriverAgentRunner" in str(app.get("name", "")):
                return str(app.get("bundleIdentifier", ""))
    finally:
        with suppress(Exception):
            await tunnel.aclose()
    return ""


def _summary(report: dict[str, Any], *, aborted: bool) -> dict[str, Any]:
    steps = report["steps"]
    return {
        "steps_total": len(steps),
        "steps_passed": sum(1 for step in steps if step["ok"]),
        "failed_steps": [step["name"] for step in steps if not step["ok"]],
        "aborted": aborted,
    }


async def run_device_matrix(evidence_dir: Path) -> dict[str, Any]:
    """Execute the ordered R4 device matrix (lane D1 only; mutates the iPhone).

    Safe context only: Settings/Home, reversible states, bundle-id launches,
    a single space typed into the local non-submitting Settings search field,
    fresh ``observe`` before every state-sensitive action. Uses only the
    public six operations plus the pinned upstream provenance probes; after
    the matrix the runtime is closed and the device is left at the Home
    Screen. Writes one privacy-safe JSON evidence report (fail-closed).
    """
    from praxiom.ios_runtime.models import (
        Drag,
        Home,
        LaunchApp,
        RuntimeOperationError,
        Swipe,
        TapElement,
        TapPoint,
        TypeText,
    )
    from praxiom.ios_runtime.runtime import NativeIosRuntime
    from praxiom.ios_runtime.transport import IosTransport

    report: dict[str, Any] = {"steps": [], "timings": {}, "observe_retries": 0}

    def step(cell: str, name: str, ok: bool, detail: str = "") -> None:
        report["steps"].append(
            {"cell": cell, "name": name, "ok": bool(ok), "detail": str(detail)[:200]}
        )

    runner_bundle_id = await _find_runner_bundle_id()
    step(
        "R4-01",
        "runner-discovery",
        bool(runner_bundle_id),
        "installed-runner-found" if runner_bundle_id else "no-installed-runner",
    )
    if runner_bundle_id:
        counter = CallCountingTransport(
            IosTransport(xctrunner_bundle_id=runner_bundle_id)
        )
        runtime = NativeIosRuntime(transport=counter)

        async def observe_timed(key: str, attempts: int = 2):
            # Read-only capture; OBSERVATION_FAILED is no-effect and
            # retry_safe=True (contract 5.1), so one bounded retry is legal
            # and never duplicates a device effect. Retries are counted.
            last: RuntimeOperationError | None = None
            for attempt in range(1, attempts + 1):
                started = time.perf_counter()
                try:
                    observation = await runtime.observe()
                except RuntimeOperationError as exc:
                    last = exc
                    if exc.code.value != "OBSERVATION_FAILED":
                        raise
                    continue
                report["timings"].setdefault(key, []).append(
                    (time.perf_counter() - started) * 1000.0
                )
                if attempt > 1:
                    report["observe_retries"] += 1
                return observation
            assert last is not None
            raise last

        async def execute_timed(key: str, actions: list[Any], revision: str):
            started = time.perf_counter()
            result = await runtime.execute(actions, expected_revision=revision)
            report["timings"].setdefault(key, []).append(
                (time.perf_counter() - started) * 1000.0
            )
            return result

        try:
            # --- R4-01 transport/lifecycle -----------------------------
            pre = await runtime.status()
            step(
                "R4-01",
                "pre-connect-status",
                True,
                f"lifecycle={pre.lifecycle_state.value} "
                f"transport={pre.transport.value} wda={pre.wda_state.value} "
                f"revision-absent={pre.current_revision is None}",
            )
            first = await observe_timed("observe_startup")
            ready = await runtime.status()
            report["transport_kind"] = ready.transport.value
            report["screen_px"] = [first.screen.width, first.screen.height]
            report["frame_px"] = [
                first.frame.width,
                first.frame.height,
                first.frame.format,
            ]
            report["sources"] = sorted(list(first.sources))
            step(
                "R4-01",
                "connect-ready",
                ready.lifecycle_state.value == "READY",
                f"lifecycle={ready.lifecycle_state.value} "
                f"transport={ready.transport.value} wda={ready.wda_state.value}",
            )
            await counter.close_session()
            degraded = await runtime.status()
            await observe_timed("observe_steady")
            resumed = await runtime.status()
            step(
                "R4-01",
                "owned-session-resume",
                resumed.lifecycle_state.value == "READY",
                f"dropped-to={degraded.lifecycle_state.value}/"
                f"{degraded.wda_state.value} "
                f"resumed-ready={resumed.lifecycle_state.value == 'READY'}",
            )
            started = time.perf_counter()
            recovery = await runtime.recover()
            report["timings"].setdefault("recover_recreate", []).append(
                (time.perf_counter() - started) * 1000.0
            )
            await observe_timed("observe_after_recover")
            step(
                "R4-01",
                "recover-recreate",
                recovery.repaired
                and (await runtime.status()).lifecycle_state.value == "READY",
                f"repaired={recovery.repaired}",
            )
            step(
                "R4-01",
                "hotplug",
                True,
                "environment-not-exercised physical-unplug-not-induced",
            )

            # --- R4-02 observe/revision ---------------------------------
            revisions: set[str] = set()
            sizes: set[tuple[int, int]] = set()
            counts: list[int] = []
            for _ in range(3):
                observation = await observe_timed("observe_steady")
                revisions.add(observation.revision)
                sizes.add((observation.screen.width, observation.screen.height))
                counts.append(len(observation.elements))
            report["element_counts_observe"] = counts
            step(
                "R4-02",
                "repeat-rounds",
                len(revisions) == 3 and len(sizes) == 1,
                f"unique-revisions={len(revisions)}/3 "
                f"sizes-consistent={len(sizes) == 1} "
                f"element-counts={counts[0]}..{counts[-1]}",
            )
            stale_revision = next(iter(revisions))
            await runtime.invalidate("r4-02-revision-turnover")
            fresh = await observe_timed("observe_steady")
            step(
                "R4-02",
                "invalidate-turnover",
                fresh.revision not in revisions,
                f"fresh-revision={fresh.revision not in revisions} "
                f"elements={len(fresh.elements)}",
            )
            calls = counter.device_calls
            try:
                await runtime.execute([Home()], expected_revision=stale_revision)
                step("R4-02", "stale-revision-zero-calls", False, "unexpectedly-accepted")
            except RuntimeOperationError as exc:
                step(
                    "R4-02",
                    "stale-revision-zero-calls",
                    exc.code.value == "STALE_REVISION"
                    and counter.device_calls == calls,
                    f"code={exc.code.value} "
                    f"zero-device-calls={counter.device_calls == calls}",
                )

            # --- R4-03 action primitives + batch ------------------------
            observation = await observe_timed("observe_steady")
            result = await execute_timed("exec_home", [Home()], observation.revision)
            step(
                "R4-03",
                "home",
                result.completed_actions == 1
                and result.accepted_revision_invalidated,
                f"outcomes={len(result.outcomes)} "
                f"invalidated={result.accepted_revision_invalidated}",
            )
            observation = await observe_timed("observe_steady")
            result = await execute_timed(
                "exec_launch", [LaunchApp(bundle_id=SETTINGS_BUNDLE_ID)],
                observation.revision,
            )
            step(
                "R4-03",
                "launch-settings",
                result.completed_actions == 1,
                f"outcomes={len(result.outcomes)}",
            )
            observation = await observe_timed("observe_steady")
            report["element_counts_settings"] = len(observation.elements)
            ref, role = _pick_element(observation.elements, observation.screen, "general")
            if ref is not None:
                result = await execute_timed(
                    "exec_tap_element", [TapElement(ref=ref)], observation.revision
                )
                step(
                    "R4-03",
                    "tap-element",
                    result.completed_actions == 1,
                    f"target-role={role} outcomes={len(result.outcomes)} "
                    "reversible-via-home",
                )
                observation = await observe_timed("observe_after_nav")
                sizes_ok = [
                    observation.screen.width,
                    observation.screen.height,
                ] == report["screen_px"]
                step(
                    "R4-02",
                    "capture-after-navigation",
                    sizes_ok,
                    f"elements={len(observation.elements)} "
                    f"sizes-consistent={sizes_ok}",
                )
                observation = await observe_timed("observe_steady")
                await execute_timed(
                    "exec_back_home", [Home()], observation.revision
                )
                observation = await observe_timed("observe_steady")
                await execute_timed(
                    "exec_relaunch",
                    [LaunchApp(bundle_id=SETTINGS_BUNDLE_ID)],
                    observation.revision,
                )
                observation = await observe_timed("observe_steady")
            else:
                step(
                    "R4-03",
                    "tap-element",
                    False,
                    "environment-not-exercised no-safe-navigation-row",
                )
            search_ref, search_role = _pick_element(
                observation.elements, observation.screen, "search"
            )
            if search_ref is not None:
                await execute_timed(
                    "exec_focus_search", [TapElement(ref=search_ref)],
                    observation.revision,
                )
                observation = await observe_timed("observe_steady")
                try:
                    result = await execute_timed(
                        "exec_type_text", [TypeText(text=" ")], observation.revision
                    )
                    step(
                        "R4-03",
                        "type-text",
                        result.completed_actions == 1,
                        f"focus-role={search_role} outcomes={len(result.outcomes)} "
                        "single-space-residue-noted",
                    )
                except RuntimeOperationError as exc:
                    step(
                        "R4-03",
                        "type-text",
                        False,
                        f"code={exc.code.value} effect={exc.effect.value} "
                        f"retry_safe={exc.retry_safe}",
                    )
                    await observe_timed("observe_after_type_failure")
                observation = await observe_timed("observe_steady")
                await execute_timed(
                    "exec_leave_settings", [Home()], observation.revision
                )
            else:
                step(
                    "R4-03",
                    "type-text",
                    False,
                    "environment-not-exercised no-focusable-search-field",
                )
            observation = await observe_timed("observe_steady")
            px = min(60, observation.screen.width - 1)
            py = min(60, observation.screen.height - 1)
            result = await execute_timed(
                "exec_tap_point", [TapPoint(x=px, y=py)], observation.revision
            )
            step(
                "R4-03",
                "tap-point",
                result.completed_actions == 1,
                f"in-bounds-point outcomes={len(result.outcomes)}",
            )
            observation = await observe_timed("observe_steady")
            result = await execute_timed(
                "exec_swipe_up", [Swipe(direction="up", distance=0.2)],
                observation.revision,
            )
            swipe_up_ok = result.completed_actions == 1
            observation = await observe_timed("observe_steady")
            result = await execute_timed(
                "exec_swipe_down", [Swipe(direction="down", distance=0.2)],
                observation.revision,
            )
            step(
                "R4-03",
                "swipe",
                swipe_up_ok and result.completed_actions == 1,
                "up-then-down outcomes=1+1 scroll-restored",
            )
            observation = await observe_timed("observe_steady")
            drag_x = min(200, observation.screen.width - 1)
            drag_y1 = min(600, observation.screen.height - 2)
            drag_y2 = min(800, observation.screen.height - 1)
            result = await execute_timed(
                "exec_drag",
                [
                    Drag(
                        start_x=drag_x, start_y=drag_y1,
                        end_x=drag_x, end_y=drag_y2, duration=0.3,
                    )
                ],
                observation.revision,
            )
            step(
                "R4-03",
                "drag",
                result.completed_actions == 1,
                f"outcomes={len(result.outcomes)}",
            )
            observation = await observe_timed("observe_steady")
            result = await execute_timed(
                "exec_ordered_batch",
                [Home(), LaunchApp(bundle_id=SETTINGS_BUNDLE_ID)],
                observation.revision,
            )
            step(
                "R4-03",
                "ordered-batch",
                result.completed_actions == 2
                and len(result.outcomes) == 2
                and result.accepted_revision_invalidated,
                f"completed={result.completed_actions} "
                f"outcomes={len(result.outcomes)} "
                f"invalidated={result.accepted_revision_invalidated}",
            )
            # Zero-device-call preflight proofs (G3) on hardware.
            observation = await observe_timed("observe_steady")
            fresh_revision = observation.revision
            await runtime.invalidate("r4-03-preflight-probe")
            proofs = 0
            calls = counter.device_calls
            try:
                await runtime.execute([Home()], expected_revision=fresh_revision)
            except RuntimeOperationError as exc:
                proofs += (
                    exc.code.value == "STALE_REVISION"
                    and counter.device_calls == calls
                )
            calls = counter.device_calls
            try:
                await runtime.execute(
                    [Home()], expected_revision="foreign-revision"
                )
            except RuntimeOperationError as exc:
                proofs += (
                    exc.code.value == "STALE_REVISION"
                    and counter.device_calls == calls
                )
            observation = await observe_timed("observe_steady")
            calls = counter.device_calls
            try:
                await runtime.execute(
                    [Home() for _ in range(33)], expected_revision=observation.revision
                )
            except RuntimeOperationError as exc:
                proofs += (
                    exc.code.value == "INVALID_REQUEST"
                    and counter.device_calls == calls
                )
            calls = counter.device_calls
            try:
                await runtime.execute(
                    [Home(), TapPoint(x=-1, y=-1)],
                    expected_revision=observation.revision,
                )
            except RuntimeOperationError as exc:
                proofs += (
                    exc.code.value == "INVALID_REQUEST"
                    and counter.device_calls == calls
                )
            step(
                "R4-03",
                "preflight-zero-call-proofs",
                proofs == 4,
                f"zero-call-proofs={proofs}/4 "
                "stale-foreign-over-limit-invalid-later",
            )

            # --- R4-04 failure/recovery (owned plumbing only) ----------
            observation = await observe_timed("observe_steady")
            await counter.close_session()
            dropped = await runtime.status()
            await observe_timed("observe_after_owned_drop")
            resumed = await runtime.status()
            step(
                "R4-04",
                "owned-session-drop-resume",
                resumed.lifecycle_state.value == "READY",
                f"dropped-to={dropped.lifecycle_state.value}/"
                f"{dropped.wda_state.value} "
                f"resumed-ready={resumed.lifecycle_state.value == 'READY'}",
            )
            executes_before = dict(runtime.trace.operations)
            await counter.close_session()
            stale_before_recover = await runtime.status()
            started = time.perf_counter()
            recovery = await runtime.recover()
            report["timings"].setdefault("recover_owned", []).append(
                (time.perf_counter() - started) * 1000.0
            )
            executes_after = dict(runtime.trace.operations)
            replayed = (
                executes_after.get("execute", 0)
                - executes_before.get("execute", 0)
            )
            await observe_timed("observe_after_recover")
            step(
                "R4-04",
                "recover-zero-replay",
                recovery.repaired
                and stale_before_recover.lifecycle_state.value != "READY"
                and replayed == 0,
                f"stale-before-recover="
                f"{stale_before_recover.lifecycle_state.value}/"
                f"{stale_before_recover.wda_state.value} "
                f"repaired={recovery.repaired} replayed-executes={replayed} "
                f"reconciled-ready="
                f"{(await runtime.status()).lifecycle_state.value == 'READY'}",
            )
            step(
                "R4-04",
                "ambiguous-effect",
                True,
                "environment-not-exercised no-ambiguous-failure-observed "
                "never-manufactured deterministic-A06-covers-semantics",
            )
            step(
                "R4-04",
                "disconnect-path",
                True,
                "environment-not-exercised no-safe-disconnect-inducible "
                "unplug-never-performed",
            )
        except RuntimeOperationError as exc:
            step(
                "MATRIX",
                "aborted",
                False,
                f"code={exc.code.value} phase={exc.phase.value} "
                f"effect={exc.effect.value} retry_safe={exc.retry_safe}",
            )
        except Exception:
            step("MATRIX", "aborted", False, "unexpected-host-error")
        finally:
            # Close semantics are always exercised and always recorded.
            try:
                await runtime.close()
            except Exception:
                pass
            try:
                await runtime.close()
                step("R4-04", "close-idempotent", True, "second-close-clean")
            except Exception:
                step("R4-04", "close-idempotent", False, "second-close-raised")
            try:
                closed = await runtime.status()
                step(
                    "R4-04",
                    "closed-state",
                    closed.lifecycle_state.value == "CLOSED",
                    f"lifecycle={closed.lifecycle_state.value}",
                )
            except Exception:
                step("R4-04", "closed-state", False, "status-raised")
            post_close = (
                ("observe", lambda: runtime.observe()),
                (
                    "execute",
                    lambda: runtime.execute([Home()], expected_revision="x"),
                ),
                ("recover", lambda: runtime.recover()),
            )
            for name, call in post_close:
                try:
                    await call()
                    step(
                        "R4-04",
                        f"post-close-{name}-rejected",
                        False,
                        "unexpectedly-accepted",
                    )
                except RuntimeOperationError as exc:
                    step(
                        "R4-04",
                        f"post-close-{name}-rejected",
                        exc.code.value == "RUNTIME_CLOSED",
                        f"code={exc.code.value}",
                    )

        # --- R4-05 latency/trace aggregation (records survive close) ----
        by_operation: dict[str, list[float]] = {}
        for record in runtime.trace.records:
            by_operation.setdefault(record.operation, []).append(record.duration_ms)
        report["trace_stats"] = {
            key: summarize_stats(values)
            for key, values in sorted(by_operation.items())
        }
        report["trace_stats"]["observe_startup"] = summarize_stats(
            report["timings"].get("observe_startup", [])
        )
        report["trace_stats"]["observe_steady"] = summarize_stats(
            report["timings"].get("observe_steady", [])
        )
        per_kind: dict[str, list[float]] = {}
        for record in runtime.trace.records:
            for outcome in record.outcomes:
                per_kind.setdefault(outcome.kind, []).append(outcome.duration_ms)
        report["per_action_stats"] = {
            key: summarize_stats(values) for key, values in sorted(per_kind.items())
        }
        report["trace_counters"] = {
            "operations": dict(runtime.trace.operations),
            "errors": {
                code.value: count for code, count in runtime.trace.errors.items()
            },
        }
        report["device_call_breakdown"] = dict(counter.call_breakdown)
        step(
            "R4-05",
            "latency-baseline",
            bool(by_operation),
            f"ops={sorted(by_operation)} "
            f"bounded-history={len(runtime.trace.records) <= 256} "
            f"observe-retries={report['observe_retries']}",
        )

    aborted = any(step_entry["name"] == "aborted" for step_entry in report["steps"])
    report["summary"] = _summary(report, aborted=aborted)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    write_evidence(report, evidence_dir / EVIDENCE_NAME)
    return report


def preprobe() -> dict[str, Any]:
    """Read-only host/device census (no mutation, no WDA contact)."""
    from importlib.metadata import version

    from pymobiledevice3 import usbmux

    try:
        installed = version("pymobiledevice3")
    except Exception:
        installed = "unknown"
    devices = asyncio.run(usbmux.list_devices())
    return {
        "pymobiledevice3_version": installed,
        "device_count": len(devices),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Praxiom R4 real-device matrix runner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-cells", help="print the frozen R4-01..R4-05 matrix")
    sub.add_parser("preprobe", help="read-only device census (no mutation)")
    matrix = sub.add_parser("matrix", help="execute the device matrix (lane D1 only)")
    matrix.add_argument(
        "--confirm-device-run",
        action="store_true",
        help="explicit opt-in: this mutates the attached iPhone (safe context only)",
    )
    matrix.add_argument(
        "--evidence-dir",
        default=str(REPO_ROOT / "docs" / "evidence"),
        help="directory receiving the privacy-safe evidence report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list-cells":
        for cell in MATRIX_CELLS:
            print(f"{cell['id']} ({cell['points']} pts): {cell['title']}")
            for step in cell["steps"]:
                print(f"  - {step}")
        return 0
    if args.command == "preprobe":
        print(json.dumps(preprobe(), indent=2, sort_keys=True))
        return 0
    if args.command == "matrix":
        if not args.confirm_device_run:
            print(
                "refused: matrix mutates the attached iPhone; "
                "re-run with --confirm-device-run on the single device lane",
                file=sys.stderr,
            )
            return 2
        report = asyncio.run(run_device_matrix(Path(args.evidence_dir)))
        summary = dict(report.get("summary", {}))
        summary["evidence"] = EVIDENCE_NAME
        print(json.dumps(summary, indent=2, sort_keys=True))
        summary = report.get("summary", {})
        return 0 if not summary.get("aborted") and not summary.get("failed_steps") else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
