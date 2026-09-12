"""Read/route probe for a current-device Merge Boss board visual postcondition.

The route is bound from fresh accessibility observations only.  Historical
board geometry/color values are treated strictly as candidate features and are
revalidated against the current screenshot before any board claim is made.
Raw screenshots and coordinates are not persisted by this probe.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import concurrent.futures
import io
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

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
    MERGE_BOSS_LABELS,
)
from phasec_mergeboss_route_probe import (  # noqa: E402
    _PhaseCRouteRuntimeSyncPort,
    _activate_domain_behavior,
    _select_single_cluster_button,
    _select_unique_exact_bindable,
)


REPORT_NAME = "mergeboss_board_probe_report.json"
REFERENCE_SCREEN = (1206, 2622)
REFERENCE_BOARD = (35, 910, 1135, 1485)
REFERENCE_EMPTY_RGB = (223, 220, 197)
REFERENCE_TOLERANCE = 24
GRID_COLS = 7
GRID_ROWS = 9

# Current-device visual binding for the Merge Boss entry Play control.
# Derived from fresh Praxiom evidence on 2026-09-12. The raw screenshot is not
# retained; only this compact RGB4 descriptor plus normalized geometry is kept.
PLAY_REFERENCE_SCREEN = (1206, 2622)
PLAY_REFERENCE_CENTER = (0.120232, 0.972502)
PLAY_REFERENCE_SIZE = (0.150912, 0.037376)
PLAY_TEMPLATE_SIZE = (16, 8)
PLAY_TEMPLATE_RGB4_B64 = (
    "dwetD1sPaw9bD1oPSA43DjgOOA8VDiQOVw6LDXgKRgdmBqwOWw85DzgONw44DicOFQ4UDkYOig15C2gKVgdWBlUFigtaD1kOWg5ZDjgONw5GDooNigtoCmkNWAtFBVYGVgZFBnkMaQ6LDosPWA6LDWkLWAxpDIsOmw5GCFUGVgZWBlUGRghpDYsPVwp6DHoOeg5pDFgLmw55DEQFVgZVBlUGVQVGCXoNVghEBVYJmw1oCUUFRARHCWgMRQVVBkUGRQZFBkUGRAZFBVUGVQVEBUQFVQVVBkUGRQZFBkUGRQZFBkUGRQZFBkUGRQZFBlUGRQZFBkUGRQZFBkUGRQZFBg=="
)
PLAY_TEMPLATE_MATCH_THRESHOLD = 0.90
BLOCKED_CTA_TERMS = (
    "buy",
    "purchase",
    "order",
    "cart",
    "coupon",
    "payment",
    "checkout",
    "cash",
    "diamond",
    "security",
    "購入",
    "注文",
    "カート",
    "クーポン",
    "支払",
    "決済",
    "ダイヤ",
)


def _channel_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return max(abs(int(a) - int(b)) for a, b in zip(left, right))


def _patch_mean(image: Image.Image, x: int, y: int, radius: int = 5) -> tuple[int, int, int]:
    x0 = max(0, x - radius)
    y0 = max(0, y - radius)
    x1 = min(image.width, x + radius + 1)
    y1 = min(image.height, y + radius + 1)
    crop = image.crop((x0, y0, x1, y1)).convert("RGB")
    if crop.width <= 0 or crop.height <= 0:
        return (0, 0, 0)
    return tuple(round(value) for value in ImageStat.Stat(crop).mean[:3])


def _board_visual_metrics(png: bytes) -> dict[str, Any]:
    image = Image.open(io.BytesIO(png)).convert("RGB")
    x, y, width, height = REFERENCE_BOARD
    if image.size != REFERENCE_SCREEN:
        return {
            "screen_size_match": False,
            "candidate_cells": 0,
            "grid_cells": GRID_COLS * GRID_ROWS,
            "candidate_ratio": 0.0,
            "reference_geometry_revalidated": False,
        }

    cell_w = width / GRID_COLS
    cell_h = height / GRID_ROWS
    offsets = ((0.16, 0.16), (0.84, 0.16), (0.16, 0.84), (0.84, 0.84))
    candidate_cells = 0
    sample_hits = 0
    sample_total = 0
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            hits = 0
            for ox, oy in offsets:
                sx = round(x + (col + ox) * cell_w)
                sy = round(y + (row + oy) * cell_h)
                color = _patch_mean(image, sx, sy)
                sample_total += 1
                if _channel_distance(color, REFERENCE_EMPTY_RGB) <= REFERENCE_TOLERANCE:
                    hits += 1
                    sample_hits += 1
            if hits >= 2:
                candidate_cells += 1
    grid_cells = GRID_COLS * GRID_ROWS
    ratio = candidate_cells / grid_cells
    return {
        "screen_size_match": True,
        "grid_cells": grid_cells,
        "candidate_cells": candidate_cells,
        "candidate_ratio": round(ratio, 4),
        "reference_color_sample_hits": sample_hits,
        "reference_color_sample_total": sample_total,
        "reference_geometry_revalidated": candidate_cells >= 12,
    }


def _contains_blocked_cta_term(element: Any) -> bool:
    values = []
    for field in ("label", "text", "value"):
        value = getattr(element, field, None)
        if isinstance(value, str):
            values.append(" ".join(value.split()).casefold())
    return any(term.casefold() in value for value in values for term in BLOCKED_CTA_TERMS)


def _entry_cta_candidates(observation: Any) -> tuple[Any, ...]:
    screen = getattr(observation, "screen", None)
    width = int(getattr(screen, "width", 0) or 0)
    height = int(getattr(screen, "height", 0) or 0)
    if width <= 0 or height <= 0:
        return ()
    candidates: list[Any] = []
    for element in tuple(getattr(observation, "elements", ()) or ()):
        rect = getattr(element, "rect", None)
        if (
            not bool(getattr(element, "ref", ""))
            or rect is None
            or getattr(element, "enabled", None) is False
            or getattr(element, "visible", None) is False
            or rect.width <= 0
            or rect.height <= 0
            or _contains_blocked_cta_term(element)
        ):
            continue
        width_ratio = rect.width / width
        height_ratio = rect.height / height
        aspect = rect.width / rect.height
        center_y = (rect.y + rect.height / 2.0) / height
        if (
            width_ratio >= 0.35
            and 0.025 <= height_ratio <= 0.18
            and aspect >= 2.0
            and 0.30 <= center_y <= 0.92
        ):
            candidates.append(element)
    return tuple(candidates)


def _entry_cta_shape_metrics(observation: Any) -> dict[str, Any]:
    screen = getattr(observation, "screen", None)
    height = int(getattr(screen, "height", 0) or 0)
    candidates = _entry_cta_candidates(observation)
    bands: list[str] = []
    if height > 0:
        for element in candidates:
            rect = getattr(element, "rect", None)
            if rect is None:
                continue
            center_y = (rect.y + rect.height / 2.0) / height
            if center_y < 0.5:
                bands.append("upper-middle")
            elif center_y < 0.72:
                bands.append("middle")
            else:
                bands.append("lower")
    return {
        "candidate_count": len(candidates),
        "single_candidate": len(candidates) == 1,
        "roles": sorted({str(getattr(item, "role", "")) for item in candidates}),
        "vertical_bands": sorted(set(bands)),
    }


def _visual_cta_candidates(png: bytes) -> tuple[tuple[int, int, int, int], ...]:
    """Return fresh screenshot-pixel CTA rectangles without persisting them.

    The detector intentionally uses only Pillow and conservative shape/color
    constraints.  It is not durable Knowledge: callers must bind the result to
    the exact observation revision that produced ``png`` and discard it after
    the next mutation/observation.
    """
    image = Image.open(io.BytesIO(png)).convert("RGB")
    if image.width <= 0 or image.height <= 0:
        return ()
    target_w = 240
    target_h = max(1, round(image.height * target_w / image.width))
    small = image.resize((target_w, target_h), Image.Resampling.BILINEAR)
    quantized = small.quantize(
        colors=24,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    palette = quantized.getpalette() or []
    pixels = list(quantized.get_flattened_data())
    visited = bytearray(target_w * target_h)
    raw: list[tuple[int, int, int, int]] = []

    def palette_rgb(index: int) -> tuple[int, int, int]:
        base = index * 3
        if base + 2 >= len(palette):
            return (0, 0, 0)
        return (palette[base], palette[base + 1], palette[base + 2])

    for start in range(len(pixels)):
        if visited[start]:
            continue
        color_index = pixels[start]
        stack = [start]
        visited[start] = 1
        area = 0
        min_x = max_x = start % target_w
        min_y = max_y = start // target_w
        while stack:
            idx = stack.pop()
            x = idx % target_w
            y = idx // target_w
            area += 1
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            if x > 0:
                nxt = idx - 1
                if not visited[nxt] and pixels[nxt] == color_index:
                    visited[nxt] = 1
                    stack.append(nxt)
            if x + 1 < target_w:
                nxt = idx + 1
                if not visited[nxt] and pixels[nxt] == color_index:
                    visited[nxt] = 1
                    stack.append(nxt)
            if y > 0:
                nxt = idx - target_w
                if not visited[nxt] and pixels[nxt] == color_index:
                    visited[nxt] = 1
                    stack.append(nxt)
            if y + 1 < target_h:
                nxt = idx + target_w
                if not visited[nxt] and pixels[nxt] == color_index:
                    visited[nxt] = 1
                    stack.append(nxt)
        if area < 120:
            continue
        box_w = max_x - min_x + 1
        box_h = max_y - min_y + 1
        width_ratio = box_w / target_w
        height_ratio = box_h / target_h
        center_y = (min_y + max_y + 1) / (2.0 * target_h)
        aspect = box_w / max(1, box_h)
        fill_ratio = area / max(1, box_w * box_h)
        r, g, b = palette_rgb(int(color_index))
        hi = max(r, g, b)
        lo = min(r, g, b)
        saturation = (hi - lo) / max(1, hi)
        brightness = (r + g + b) / 3.0
        if (
            width_ratio >= 0.30
            and 0.055 <= height_ratio <= 0.18
            and 0.25 <= center_y <= 0.94
            and 1.8 <= aspect <= 3.6
            and fill_ratio >= 0.32
            and saturation >= 0.14
            and 45 <= brightness <= 235
        ):
            scale_x = image.width / target_w
            scale_y = image.height / target_h
            raw.append(
                (
                    round(min_x * scale_x),
                    round(min_y * scale_y),
                    max(1, round(box_w * scale_x)),
                    max(1, round(box_h * scale_y)),
                )
            )

    def iou(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
        lx, ly, lw, lh = left
        rx, ry, rw, rh = right
        ix0 = max(lx, rx)
        iy0 = max(ly, ry)
        ix1 = min(lx + lw, rx + rw)
        iy1 = min(ly + lh, ry + rh)
        iw = max(0, ix1 - ix0)
        ih = max(0, iy1 - iy0)
        intersection = iw * ih
        if intersection <= 0:
            return 0.0
        union = lw * lh + rw * rh - intersection
        return intersection / max(1, union)

    clusters: list[tuple[int, int, int, int]] = []
    for candidate in sorted(raw, key=lambda item: item[2] * item[3], reverse=True):
        if any(iou(candidate, existing) >= 0.45 for existing in clusters):
            continue
        clusters.append(candidate)
    return tuple(clusters)


def _visual_cta_metrics(png: bytes) -> dict[str, Any]:
    candidates = _visual_cta_candidates(png)
    image = Image.open(io.BytesIO(png)).convert("RGB")
    projections: list[dict[str, Any]] = []
    for x, y, width, height in candidates:
        crop = image.crop((x, y, min(image.width, x + width), min(image.height, y + height)))
        hsv = crop.convert("HSV")
        hsv_mean = ImageStat.Stat(hsv).mean if crop.width > 0 and crop.height > 0 else (0, 0, 0)
        center_y = (y + height / 2.0) / image.height
        if center_y < 0.5:
            band = "upper-middle"
        elif center_y < 0.72:
            band = "middle"
        else:
            band = "lower"
        projections.append(
            {
                "width_ratio": round(width / image.width, 3),
                "height_ratio": round(height / image.height, 3),
                "aspect": round(width / max(1, height), 2),
                "vertical_band": band,
                "mean_saturation": round(float(hsv_mean[1]) / 255.0, 3),
                "mean_brightness": round(float(hsv_mean[2]) / 255.0, 3),
            }
        )
    return {
        "candidate_count": len(candidates),
        "single_candidate": len(candidates) == 1,
        "candidates": projections,
    }


def _rgb4_descriptor(image: Image.Image, rect: tuple[int, int, int, int]) -> bytes:
    x, y, width, height = rect
    crop = image.crop((x, y, x + width, y + height)).convert("RGB")
    crop = crop.resize(PLAY_TEMPLATE_SIZE, Image.Resampling.LANCZOS)
    packed = bytearray()
    for r, g, b in crop.get_flattened_data():
        packed.append(((int(r) >> 4) << 4) | (int(g) >> 4))
        packed.append(int(b) >> 4)
    return bytes(packed)


def _rgb4_similarity(left: bytes, right: bytes) -> float:
    if len(left) != len(right) or not left or len(left) % 2:
        return 0.0
    distance = 0
    channels = 0
    for index in range(0, len(left), 2):
        l0, l1 = left[index], left[index + 1]
        r0, r1 = right[index], right[index + 1]
        for lvalue, rvalue in (
            (l0 >> 4, r0 >> 4),
            (l0 & 0x0F, r0 & 0x0F),
            (l1 & 0x0F, r1 & 0x0F),
        ):
            distance += abs(lvalue - rvalue)
            channels += 1
    return max(0.0, 1.0 - distance / (15.0 * channels))


def _play_visual_binding(png: bytes) -> tuple[tuple[int, int, int, int] | None, float]:
    image = Image.open(io.BytesIO(png)).convert("RGB")
    if image.size != PLAY_REFERENCE_SCREEN:
        return None, 0.0
    reference = base64.b64decode(PLAY_TEMPLATE_RGB4_B64)
    center_x = PLAY_REFERENCE_CENTER[0] * image.width
    center_y = PLAY_REFERENCE_CENTER[1] * image.height
    width = max(1, round(PLAY_REFERENCE_SIZE[0] * image.width))
    height = max(1, round(PLAY_REFERENCE_SIZE[1] * image.height))
    best_rect: tuple[int, int, int, int] | None = None
    best_score = 0.0
    for dx in (-12, -6, 0, 6, 12):
        for dy in (-8, -4, 0, 4, 8):
            x = round(center_x + dx - width / 2.0)
            y = round(center_y + dy - height / 2.0)
            if x < 0 or y < 0 or x + width > image.width or y + height > image.height:
                continue
            rect = (x, y, width, height)
            score = _rgb4_similarity(_rgb4_descriptor(image, rect), reference)
            if score > best_score:
                best_score = score
                best_rect = rect
    if best_rect is None or best_score < PLAY_TEMPLATE_MATCH_THRESHOLD:
        return None, best_score
    return best_rect, best_score


def _play_visual_binding_metrics(png: bytes) -> dict[str, Any]:
    image = Image.open(io.BytesIO(png))
    rect, score = _play_visual_binding(png)
    return {
        "screen_size_match": image.size == PLAY_REFERENCE_SCREEN,
        "matched": rect is not None,
        "similarity": round(score, 4),
        "threshold": PLAY_TEMPLATE_MATCH_THRESHOLD,
        "template_source": "current-device-praxiom-20260912",
    }


def _persist_report(session: RunSession, report: dict[str, Any]) -> Path:
    target = session.context.run_dir / REPORT_NAME
    payload = {
        "schema_version": 1,
        "run_id": report.get("run_id"),
        "status": report.get("status"),
        "phase": "phase-c-domain-board-probe",
        "domain": "mergeboss",
        "foreground_verified": report.get("foreground_verified"),
        "account_attempt": report.get("account_attempt"),
        "entry_attempt": report.get("entry_attempt"),
        "board_visual": report.get("board_visual"),
        "entry_cta_shape": report.get("entry_cta_shape"),
        "visual_cta": report.get("visual_cta"),
        "play_visual_binding": report.get("play_visual_binding"),
        "advance_visual_cta": report.get("advance_visual_cta"),
        "cta_attempt": report.get("cta_attempt"),
        "post_cta_board_visual": report.get("post_cta_board_visual"),
        "post_cta_board_samples": report.get("post_cta_board_samples"),
        "open_level_board_accepted": report.get("open_level_board_accepted"),
        "post_entry_element_count": report.get("post_entry_element_count"),
        "home_cleanup": report.get("home_cleanup"),
        "summary": report.get("summary"),
        "privacy": {
            "raw_screenshot_persisted": False,
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
    advance_visual_cta: bool = False,
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
    worker = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="praxiom-phasec-mergeboss-board")
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
    report: dict[str, Any] = {
        "run_id": session.run_id,
        "status": "running",
        "advance_visual_cta": bool(advance_visual_cta),
        "open_level_board_accepted": False,
    }
    close_status = "ok"
    close_reason: str | None = None
    try:
        launch_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                LAUNCH_APPLICATION,
                evidence_prefix="phasec:mergeboss-board:launch",
            ),
        )
        home_skill = await loop.run_in_executor(
            worker,
            lambda: _activate_launch_behavior(
                registry,
                RETURN_HOME,
                evidence_prefix="phasec:mergeboss-board:home",
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

        app_view = await _observe_bounded(runtime)
        foreground = inspect_active_application_info(await transport.active_application_info(), app_bundle)
        report["foreground_verified"] = bool(foreground.expected_match)
        account = _select_single_cluster_button(app_view, ACCOUNT_KEYWORDS, contains=True)
        if account is None:
            raise RuntimeError("account-binding-not-unique")
        account_attempt = await loop.run_in_executor(
            worker,
            lambda: session.execute_skill(
                route_skill,
                revision=app_view.revision,
                op="tap_element",
                extra={"ref": account.ref},
                shadow_pending=1,
            ),
        )
        account_replayed = bool(account_attempt.evidence.get("replayed", False))
        report["account_attempt"] = {
            "state": account_attempt.state,
            "effect": account_attempt.effect,
            "replayed": account_replayed,
        }
        if account_attempt.state != "succeeded" or account_attempt.effect != "NONE" or account_replayed:
            raise RuntimeError("account-route-attempt-not-clean")

        account_view = await _observe_bounded(runtime)
        entry = _select_unique_exact_bindable(account_view, MERGE_BOSS_LABELS)
        if entry is None:
            raise RuntimeError("merge-boss-entry-not-unique")
        entry_attempt = await loop.run_in_executor(
            worker,
            lambda: session.execute_skill(
                route_skill,
                revision=account_view.revision,
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
        }
        if entry_attempt.state != "succeeded" or entry_attempt.effect != "NONE" or entry_replayed:
            raise RuntimeError("merge-boss-entry-attempt-not-clean")

        await asyncio.sleep(1.5)
        board_view = await _observe_bounded(runtime)
        png = await transport.screenshot()
        report["post_entry_element_count"] = len(board_view.elements)
        report["board_visual"] = _board_visual_metrics(png)
        report["entry_cta_shape"] = _entry_cta_shape_metrics(board_view)
        report["visual_cta"] = _visual_cta_metrics(png)
        report["play_visual_binding"] = _play_visual_binding_metrics(png)
        cleanup_view = board_view

        if advance_visual_cta:
            play_rect, _play_score = _play_visual_binding(png)
            if play_rect is None:
                report["status"] = "blocked"
            else:
                x, y, width, height = play_rect
                cta_attempt = await loop.run_in_executor(
                    worker,
                    lambda: session.execute_skill(
                        route_skill,
                        revision=board_view.revision,
                        op="tap_point",
                        extra={
                            "x": int(round(x + width / 2.0)),
                            "y": int(round(y + height / 2.0)),
                        },
                        shadow_pending=1,
                    ),
                )
                cta_replayed = bool(cta_attempt.evidence.get("replayed", False))
                report["cta_attempt"] = {
                    "state": cta_attempt.state,
                    "effect": cta_attempt.effect,
                    "replayed": cta_replayed,
                }
                # Never replay the visual mutation. Reconcile by observing
                # only, across a bounded settle window, because the embedded
                # WebView can take several seconds to transition after a
                # successful tap.
                samples: list[dict[str, Any]] = []
                post_metrics: dict[str, Any] = {}
                elapsed = 0.0
                for wait_s in (1.5, 2.5, 4.0):
                    await asyncio.sleep(wait_s)
                    elapsed += wait_s
                    cleanup_view = await _observe_bounded(runtime)
                    post_png = await transport.screenshot()
                    post_metrics = _board_visual_metrics(post_png)
                    samples.append(
                        {
                            "elapsed_s": elapsed,
                            **post_metrics,
                        }
                    )
                    if post_metrics.get("reference_geometry_revalidated") is True:
                        break
                report["post_cta_board_samples"] = samples
                report["post_cta_board_visual"] = post_metrics
                clean_attempt = (
                    cta_attempt.state == "succeeded"
                    and cta_attempt.effect == "NONE"
                    and not cta_replayed
                )
                accepted = bool(
                    clean_attempt
                    and post_metrics.get("reference_geometry_revalidated") is True
                )
                report["open_level_board_accepted"] = accepted
                report["status"] = "completed" if accepted else "hold"
        else:
            report["status"] = "completed"

        cleanup = await loop.run_in_executor(
            worker,
            lambda: session.execute_skill(
                home_skill,
                revision=cleanup_view.revision,
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
        close_reason = "phasec-mergeboss-board-probe-exception"
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
    parser.add_argument("--advance-visual-cta", action="store_true")
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
                advance_visual_cta=args.advance_visual_cta,
            )
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
