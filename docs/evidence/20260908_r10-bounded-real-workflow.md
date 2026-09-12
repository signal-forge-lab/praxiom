# R10 Bounded Real-Workflow — Live Lane Evidence (2026-09-08)

- Sensitivity: PUBLIC

## 2026-09-09 live closure addendum — CURRENT AUTHORITY

This addendum supersedes the earlier `BLOCKED-PHYSICAL` statements below **for current R10 status only**. The older sections are intentionally retained as the historical 2026-09-08 device-unavailable window.

- Source HEAD before the successful live lane: `3045920171ef6fcf86e6150a471a18091fc809d0`; working tree clean.
- Current deterministic gates: **359/359 pytest PASS**, boundary guard PASS, provenance guard PASS.
- Read-only preprobe: `device_count=1`, `result=PROCEED-PROBE-OK`.
- Signed runner: present.
- Both configured target-installed checks: true. Bundle identifiers stayed in-process and are not retained in evidence.
- Single writer: `r10-domain-lane` held `r10-domain-live-lane`; execution was strictly sequential Merge Boss -> GoGoMatch.
- Merge Boss `mergeboss:launch`: one `launch_app` attempt, `state=succeeded`, `effect=NONE`, `replayed=false`; fresh observation before mutation, revision invalidated after execution, fresh non-empty observation after, lease held at dispatch, structural postcondition PASS.
- GoGoMatch `gogomatch:launch-game`: same acceptance bar and the same successful revision/postcondition chain, executed only after Merge Boss completed.
- Overall runner result: **PASS** (exit 0); Runtime closed cleanly (`runtime_closed=true`).
- Unsafe/high-risk actions remained excluded. Navigation actions still remain deterministic-only without a human-supplied revision-bound safe-surface target policy.
- Privacy: no device identifier, bundle identifier, pair record, raw screen text, element label, screenshot, or raw action payload is retained here.

Therefore **R10-E = 5/5 PASS** as of 2026-09-09. The earlier `device_count=0` blocker below is historical evidence, not an active blocker.
- Lane: F — live workflow (single owner, sequential; freeze §7)
- Authority: `docs/evidence/r10-design-freeze.md` §5 (bounded real-workflow safety envelope), §9 R10-E
- Runner: `scripts/r10_domain_workflow.py` (Lane-F owned)
- Source state at lane window: HEAD `ff0ab7f1b7bb92975f1e44e2aafabb7f4a1d4e7c`; working tree carries the uncommitted R10 lane S–E artifacts (domain seam, domain modules, R10 tests/fixtures, guard scan-scope changes, closure evidence) — recorded as provenance, not silently normalized
- Result: **BLOCKED-PHYSICAL — no attached iOS device in this lane window** (precise external blocker retained; no fabrication; no criterion weakened)

## 1. Gate order record (R10-E1)

Live work was attempted only after the deterministic gates were run in this lane window, in this order:

| Order | Gate | Command (certified `.venv`, Python 3.12.10, pymobiledevice3 11.3.0, pytest 9.1.1) | Result |
|---|---|---|---|
| 1 | Boundary guard | `python scripts/check_agent_boundaries.py` | PASS — `OK: agent/knowledge/retrieval/skill/adaptive respect the Runtime boundary.` (exit 0) |
| 2 | Provenance guard | `python scripts/check_provenance.py` | PASS — `OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml).` (exit 0) |
| 3 | Full deterministic suite (R3–R9 regression + R10 matrix) | `python -m pytest -q -p no:cacheprovider` | **358 passed**, 1 setup-only error — see §1.1 |

### 1.1 Precise note on the single non-passing collection item (honesty record)

`tests/test_package.py::test_check_provenance_detects_phone_harness_reference` failed during **fixture setup**, before any test assertion ran: this execution session's sandbox denies process-level directory creation, so pytest's `tmp_path` factory raised `PermissionError [WinError 5]` while creating its basetemp (attempted under both the platform temp area and the workspace). This is a session-environment denial, not product behavior. The test's substance was verified directly in the same environment, bypassing only the fixture:

- probe file `.r10-scratch-bad.py` (content `import phone_harness`) created via the sanctioned file-write path, then `check_provenance.find_violations([Path('.r10-scratch-bad.py')])` returned exactly one hit, `.r10-scratch-bad.py:1: import phone_harness` — the exact assertion of the setup-blocked test (detection + line attribution). The probe file was then deleted.

The deterministic gate is therefore reported as: 358 in-suite passes, guards green, and the one fixture-blocked test substance-verified as above. No result in this document depends on treating that setup error as a pass or a failure of product logic.

## 2. Route record (R10-E2) — Agent → Skill/Coordinator → Runtime only

The runner implements exactly one device-mutation route and no other call site:

```text
registry-active domain skill (behavior_to_candidate → R8 gates → SkillRegistry.activate)
  → SkillExecutor.execute(skill, revision, op="launch_app", extra={bundle_id})
  → ExecutionCoordinator.run(spec with revision)   [sync port; DeviceLeaseManager single owner]
  → NativeIosRuntime.execute([LaunchApp], expected_revision=...)
```

- The only mutation call site in the lane script is `_SyncRuntimePort.execute`, invoked exclusively by `ExecutionCoordinator.run`; it converts the single allowed payload class (`launch_app`) at the integration edge and delegates to the real `Runtime.execute` on one persistent lane event loop. No payload conversion exists outside it, and no lane code calls `Runtime.execute`/`recover` directly.
- Revision freshness: the lane captures a fresh `observe()` immediately before each mutation, records `status().current_revision is None` after the mutation (revision invalidation evidence), and then captures a second fresh `observe()`; revisions are never reused across behaviors.
- No blind replay: on any non-`NONE` effect, stale revision, raised runtime error, or failed step, the lane stops the whole run (`stop_reason` recorded); replay is structurally impossible from the lane (one attempt per behavior, no retry code path exists in the runner).
- Human-gated behaviors (`mergeboss:purchase-generator-part`, `mergeboss:speedup-generator-cooldown`, `gogomatch:use-hammer-booster`, `gogomatch:purchase-extra-moves`) are **never registered, activated, or executed** by this lane. Navigation behaviors (`mergeboss:open-level-board`, `mergeboss:spawn-generator-item`, `mergeboss:merge-board-items`, `mergeboss:deliver-customer-order`, `gogomatch:open-level`, `gogomatch:start-level`, `gogomatch:swap-tiles`, `gogomatch:claim-level-reward`) remain **deterministic-only** in this window: the frozen non-destructive-navigation class requires a revision-bound safe-surface target policy that no human authority supplied in this window, and the lane does not guess tap targets. This is the freeze §5/E5 rule applied verbatim: not safely provable ⇒ deterministic-only, never a silent widening.

## 3. Allowed-class assertion (R10-E3)

Frozen closed set actually constructible by the lane: `launch_app` (of the two operator-configured target domain apps) plus read-only `observe`/`status`. `_action_from_payload` raises on any other op (fail-closed); `ExecutionSpec.validate` re-proves `op ∈ ALLOWED_OPS`; `SkillExecutor` re-proves `op ∈ registry authority`. Prohibited classes (purchase/payment, account/security, messaging, deletion, profile install, credentials, device settings) are unreachable: no behavior that maps to them is activated, and no payload shape for them exists in the lane.

## 4. Live execution record (R10-E4/E5) and precise external blocker

Single lane, single owner (`r10-domain-lane` on lease `r10-domain-live-lane`), sequential Merge Boss → GoGoMatch, zero concurrent writers.

### 4.1 Read-only preprobe (executed)

```json
{
  "lane": "r10-bounded-real-workflow",
  "probe": "preprobe-read-only",
  "source_head_parts": ["ff0ab7f1b7bb92975f1e", "44e2aafabb7f4a1d4e7c"],
  "source_tree_clean": false,
  "device_count": 0,
  "result": "BLOCKED-PHYSICAL",
  "blocker": "single-attached-iphone-required:found=0"
}
```

`pymobiledevice3` (pinned upstream, installed at 11.3.0 in the certified `.venv`) imported successfully and the usbmux device listing executed: the probe machinery is functional and the answer is a genuine zero — **no iOS device is attached to this host in this lane window**.

### 4.2 Run-path gate order, fail-closed verification (executed, zero device mutation)

| Check | Outcome |
|---|---|
| `run` without `--confirm-device-run` | refused (exit 2): `refused: run requires --confirm-device-run` |
| `run` with confirmation + attestation but no target bundle ids | `BLOCKED-CONFIG` (exit 2): `target-domain-app-bundle-ids-not-configured:lane-will-not-guess-bundle-identifiers` |
| `run` with placeholder bundle ids configured | `BLOCKED-PHYSICAL` (exit 2): `single-attached-iphone-required:found=0` — stopped at the read-only device probe, before runner discovery, app listing, registry activation, or any mutation |

### 4.3 Blocker (retained verbatim)

> **External blocker:** the required device/app safe state is unavailable — zero iOS devices are attached to the execution host (`device_count=0` via the pinned upstream usbmux probe), so no fresh revision-bound observation, no `launch_app` mutation through Skill/Coordinator/Runtime, and no observation-based postcondition check can be executed. Per-design-freeze §5 honesty rule, R10-E live evidence remains **blocked**, not complete; no hardware/app evidence is fabricated and no acceptance criterion is downgraded.

Environment facts that are NOT blockers (recorded to bound the blocker precisely): runtime dependency importable and probe functional; lane script fail-closed gates verified above; deterministic gates green (§1).

## 5. What unblocks the lane (no criterion change)

1. One attached, unlocked iPhone (single device, `device_count == 1`).
2. Signed WDA runner installed (or `--runner-bundle-id` supplied); both target domain apps installed.
3. Operator supplies `--mergeboss-bundle-id` / `--gogomatch-bundle-id` (kept in-process; never recorded in evidence).
4. Re-run, in this exact order, after re-running the §1 gates on current HEAD:
   `python scripts/r10_domain_workflow.py run --confirm-device-run --deterministic-green --mergeboss-bundle-id … --gogomatch-bundle-id …`
   Expected evidence per domain: behavior id `mergeboss:launch` / `gogomatch:launch-game`, op class `launch_app`, attempt `state=succeeded, effect=NONE, replayed=false`, revision chain `observed → invalidated → fresh-observed`, postcondition structural proxy (fresh revision, non-empty element count), and privacy-safe timings. Any non-`NONE`/stale result stops the lane and is recorded verbatim.
5. Navigation-class live behaviors additionally require a human-supplied revision-bound safe-surface target policy in a later lane window; human-gated behaviors stay human-gated or deterministic-only per freeze §4/§5.

## 6. Privacy statement (R10-E4)

This document and all runner output retain only: gate/enums/results, behavior ids, op classes, counts, timings, opaque revision tokens (when a live run exists), and the blocker strings above. No device identifiers, bundle ids, pair records, screen text, element labels, screenshots, or action payloads are retained. The runner enforces this with a fail-closed `_privacy_check` before emitting any report.

— Lane F, R10 bounded real-workflow. Recorded 2026-09-08.
