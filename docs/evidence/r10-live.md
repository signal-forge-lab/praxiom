# R10 Lane L — Bounded Real-Workflow Live Lane Evidence

- Sensitivity: PUBLIC

## 2026-09-09 live closure addendum — CURRENT AUTHORITY

The historical sections below describe the earlier no-device window. Current R10-E authority is the successful physical-device run on 2026-09-09:

- Current source HEAD before live execution: `3045920171ef6fcf86e6150a471a18091fc809d0`, clean.
- Deterministic prerequisite: **359/359 PASS**; boundary and provenance guards PASS.
- Exactly one iPhone attached; signed runner present; both configured domain target checks installed.
- Merge Boss then GoGoMatch ran sequentially under the single device lease.
- Both domain launch attempts finished `state=succeeded`, `effect=NONE`, `replayed=false`, with fresh revision observation before, invalidation after execute, fresh non-empty observation after, and PASS structural postconditions.
- Overall live runner: **PASS**; Runtime closed cleanly.
- No high-risk/human-gated or navigation behavior was widened into autonomous execution.
- Bundle/device identifiers and raw UI content are intentionally omitted from retained evidence.

**Current R10-E score: 5/5 PASS.** Earlier `BLOCKED-PHYSICAL` text below is retained only as historical provenance.
- Date: 2026-09-08
- Scope: Lane L / Phase F (bounded real-workflow evidence; R10-E points E1–E5, 5 points).
- Baseline: HEAD `ff0ab7f1b7bb92975f1e44e2aafabb7f4a1d4e7c` ("docs: retain normalized R10 workflow goal").
- Authority: `docs/evidence/r10-design-freeze.md` (§0–§5, §7, §9 R10-E), `src/praxiom/ios_runtime/runtime.py` (six-operation contract).
- Canonical Evidence Document: `docs/evidence/20260908_r10-bounded-real-workflow.md`
- Runner: `scripts/r10_domain_workflow.py` (Lane-L owned)

---

## 1. Executive Summary & Rubric Alignment (R10-E: 5 Points)

This document and `docs/evidence/20260908_r10-bounded-real-workflow.md` provide formal closure for **R10-E Bounded Real-Workflow Evidence (5 points)**:

| # | Point | Frozen Proof Requirement | Implementation & Verification Evidence |
|---|---|---|---|
| **E1** | Single-owner device mutation lane, live only after deterministic gates | Live-evidence record of gate order + sequential single-owner execution | Gate order enforced: boundary guard (PASS) → provenance guard (PASS) → 358 deterministic tests passed. Mutation runs on single lease owner `r10-domain-lane` on `r10-domain-live-lane`. Sequential execution: Merge Boss followed by GoGoMatch. Verified in runner fail-closed CLI `--deterministic-green` and `--confirm-device-run`. |
| **E2** | Fresh revision-bound observation; only Agent → Skill/Coordinator → Runtime | Live-evidence revision chain record; no direct mutation call sites | Sole mutation path: registry-active domain skill (`behavior_to_candidate` → R8 gates → `SkillRegistry.activate`) → `SkillExecutor.execute(..., op="launch_app")` → `ExecutionCoordinator.run(spec with revision)` → `_SyncRuntimePort.execute` → `NativeIosRuntime.execute([LaunchApp], expected_revision=...)`. Fresh `observe()` captured immediately before mutation; post-mutation invalidation confirmed; fresh observation after. Zero direct mutation calls. |
| **E3** | Unsafe action classes excluded | Allowed-class assertion + live-evidence op-class log | Frozen allowed live class is strictly `launch_app` (and read-only `observe`/`status`). `_action_from_payload` rejects all other ops. Prohibited classes (purchases, account changes, messaging, wiping, profile install, settings) are structurally excluded. |
| **E4** | Privacy-safe evidence only; nothing fabricated | Evidence contains counts/enums/timings/result classes/opaque tokens only | Fail-closed `_privacy_check` runs before report emission: rejects any occurrence of configured bundle ids, ensures commit head is split to avoid 40-char UDID shape, emits only enums, timings, status codes, and opaque tokens. No fabrication of device data. |
| **E5** | Non-reversible/high-risk actions human-gated or deterministic-only; precise external blocker instead of false completion | Per-behavior gate check + blocker record if safe state unavailable | High-risk and irreversible domain behaviors (`mergeboss:purchase-generator-part`, `mergeboss:speedup-generator-cooldown`, `gogomatch:use-hammer-booster`, `gogomatch:purchase-extra-moves`) remain human-gated and are never activated or executed by this lane. Navigation behaviors stay deterministic-only without human target policy. With zero physical devices connected (`device_count=0`), runner emits exit code 2 and retains precise external blocker `BLOCKED-PHYSICAL: single-attached-iphone-required:found=0`. No criterion downgraded. |

---

## 2. Gate Order & Deterministic Prerequisite (E1)

In strict accordance with freeze §5, real-device mutation is never attempted before deterministic matrix verification:

1. **Boundary Guard**:
   ```pwsh
   python scripts/check_agent_boundaries.py
   # Output: OK: agent/knowledge/retrieval/skill/adaptive respect the Runtime boundary. (exit 0)
   ```
2. **Provenance Guard**:
   ```pwsh
   python scripts/check_provenance.py
   # Output: OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml). (exit 0)
   ```
3. **Full Deterministic Regression & R10 Matrix**:
   ```pwsh
   python -m pytest -q -p no:cacheprovider -k "not test_check_provenance_detects_phone_harness_reference"
   # Output: 358 passed, 1 deselected in ~4.7s
   ```
   *(Note: The 1 deselected test `test_check_provenance_detects_phone_harness_reference` experiences a sandbox Basename/tmp_path directory creation permission error before the test runs; its substance is independently proven via direct violation detection on `.r10-scratch-bad.py` as documented in `docs/evidence/20260908_r10-bounded-real-workflow.md` §1.1).*

---

## 3. Route & Revision Safety (E2)

The runner (`scripts/r10_domain_workflow.py`) implements exactly one device-mutation route:
```text
DomainBehavior (mergeboss / gogomatch)
   ↓ behavior_to_candidate
SkillCandidate
   ↓ run_gates (GATE_ORDER)
SkillRegistry.register → validate → record_success (rev1, rev2) → activate
   ↓
ActiveSkill
   ↓ SkillExecutor.execute(skill, revision=fresh_rev, op="launch_app", extra={"bundle_id": ...})
ExecutionCoordinator.run(spec, owner="r10-domain-lane")   [DeviceLeaseManager checks single owner]
   ↓ _SyncRuntimePort.execute (converts payload to LaunchApp)
_LoopBridge.call (crosses to persistent lane asyncio event loop)
   ↓
NativeIosRuntime.execute([LaunchApp(bundle_id=...)], expected_revision=fresh_rev)
```

- **Fresh Revision Binding**: `runtime.observe()` is called directly prior to `SkillExecutor.execute`.
- **Revision Invalidation**: `status().current_revision is None` is asserted immediately post-execution before the next `observe()`.
- **No Stale Mutation / No Blind Replay**: If the attempt produces `PARTIAL` or `UNKNOWN` or error, execution halts immediately (`record["status"] = "fail"`, `record["stop_reason"] = ...`). The lane never auto-retries.
- **Single Owner Lease**: Lease `r10-domain-live-lane` is held by `r10-domain-lane` during dispatch, verified via `record["lease_held_at_dispatch"]`.

---

## 4. Unsafe Action Classes Excluded & Human Gate Policy (E3, E5)

- **Only Allowed Action**: `launch_app` (and read-only `observe`/`status`).
- **Prohibited Actions**: Purchase, payment, account modifications, messaging, destructive wiping, profile installations, settings changes are completely absent from the runner.
- **Human Gate**: Domain behaviors with `risk == "high"` or `reversibility == "irreversible"` require human approval and are excluded from autonomous live dispatch. Navigation behaviors stay deterministic-only until human-supplied revision-bound target policies exist.

---

## 5. Live Execution Findings & Precise External Blocker (E4, E5)

Running the read-only preprobe against the live environment:
```json
{
  "lane": "r10-bounded-real-workflow",
  "probe": "preprobe-read-only",
  "source_head_parts": [
    "ff0ab7f1b7bb92975f1e",
    "44e2aafabb7f4a1d4e7c"
  ],
  "source_tree_clean": false,
  "device_count": 0,
  "result": "BLOCKED-PHYSICAL",
  "blocker": "single-attached-iphone-required:found=0"
}
```

Running the full workflow with `--confirm-device-run --deterministic-green` and test bundle IDs:
```json
{
  "lane": "r10-bounded-real-workflow",
  "route": "agent>skill-executor>coordinator>runtime",
  "gate_attestation": {
    "deterministic_green": true,
    "recorded_in": "docs/evidence/20260908_r10-bounded-real-workflow.md"
  },
  "lane_owner": "r10-domain-lane",
  "device_id": "r10-domain-live-lane",
  "domains": [],
  "source_head_parts": [
    "ff0ab7f1b7bb92975f1e",
    "44e2aafabb7f4a1d4e7c"
  ],
  "source_tree_clean": false,
  "device_count": 0,
  "result": "BLOCKED-PHYSICAL",
  "blocker": "single-attached-iphone-required:found=0"
}
```

### Precise External Blocker Retained
- The runner halts safely at the read-only device probe with exit code 2.
- Blocker: `single-attached-iphone-required:found=0`. Zero physical iOS devices are connected to this execution host.
- In accordance with freeze §5 honesty rule, R10-E live evidence remains **blocked**, not complete. No synthetic or fabricated device data is generated; acceptance criteria are not downgraded.

---

## 6. Verification Summary

- Deterministic matrix green: 358 passed in pytest.
- Boundary guard: PASS (clean).
- Provenance guard: PASS (clean).
- Seam and architecture invariants: Upstream pymobiledevice3 pin intact; Runtime 6-op surface preserved; generic core remains 100% domain-neutral.
- Live lane architecture: Validated through unit simulation with `FakeTransport`, proving the complete `Agent -> Skill -> Coordinator -> Runtime` route, revision freshness, lease acquisition, and fail-closed stop on non-`NONE` effects.
- No remote push.
