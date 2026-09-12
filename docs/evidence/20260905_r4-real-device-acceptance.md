# R4 real-device acceptance — retained evidence

- Date: 2026-09-05 (UTC)
- Sensitivity: **PUBLIC**
- Lane: D1 (sole device-mutation lane; no other agent touched the device)
- Runtime: `praxiom.ios_runtime` public six operations only
  (`status` / `observe` / `execute` / `invalidate` / `recover` / `close`)
- Upstream: unmodified `doronz88/pymobiledevice3` 11.3.0,
  pin `ec4ac06a850a6a884ca778350621f354faf347c6` (matches `pyproject.toml`)
- Path: USB-attached iPhone, in-process `RSD_USERSPACE` tunnel, no external
  `tunneld`; WDA via the already-installed signed runner started through the
  pinned upstream `TestConfig` + `XCUITestService` path (R3-08 precedent; the
  runner bundle identifier is intentionally omitted here, as in R3-08)
- Screen: 1206 x 2622 PNG; sources `accessibility` + `screenshot` every round
- Safe context only: Home / Settings (bundle-id launch), reversible states,
  fresh `observe` before every state-sensitive `execute`; no purchase, submit,
  message, delete, account/security change, profile install, or domain/game
  automation
- No Phone Harness import, subprocess, MCP hop, fallback, shim, or copied
  source anywhere in the device path

This report contains counts, enums, booleans, and timings only. No device
identifier, pair record, secret, token, raw screen text, screenshot, revision
or element token, or raw action payload is retained.

## Method

Three short single-lane runs against the current tree (including the Phase-B
`invalidate(reason)` bound work, six-operation surface unchanged):

- run 1: R4-01, R4-02, R4-03 (minus two element picks), R4-04 (partial);
- run 2: R4-03 tap_element + type_text with corrected projection rules,
  R4-02 after-navigation capture, R4-04 (partial);
- run 3: R4-04 recovery proof to completion, R4-05 aggregation, close
  semantics.

A `CallCountingTransport` wrapper (from `scripts/r4_device_matrix.py`, G3
scaffold) counted the 12 device-facing transport methods around every
negative batch; `snapshot()` is side-effect-free and never counted.

## R4-01 — transport/lifecycle — PASS (hotplug environment-not-exercised)

- Pre-connection `status`: `DISCONNECTED / NONE / NONE`, revision none.
- First `observe`: `READY / RSD_USERSPACE / READY`; in-process tunnel
  confirmed, no external `tunneld` required.
- Owned WDA/session drop (`close_session`, owned plumbing only) then
  `observe`: `DEGRADED / UNAVAILABLE` -> `READY` (3/3 runs).
- `recover()` (transport `recreate`): `repaired=true`, `READY /
  RSD_USERSPACE / READY` afterwards (4/4 calls across runs).
- Hotplug/unplug: `environment-not-exercised` — physical unplug cannot be
  induced safely and was not fabricated.

## R4-02 — observe/revision — PASS

- 3 consecutive observes: 3 unique revisions, identical screen/frame geometry,
  element counts 556/556/556 (Home Screen) and 173/183 (Settings across runs).
- `invalidate("r4-02-revision-turnover")` then `observe`: fresh revision,
  bounded element count, no screen content retained.
- Stale-revision batch rejected with `STALE_REVISION` and zero device calls
  (counter unchanged).
- Capture after safe navigation (Settings row -> submenu): consistent sizes,
  bounded elements. Capture after recovery: consistent (run 3, 456 elements).
- Screenshot/accessibility share one logical revision per capture, as intended.

## R4-03 — action matrix — PASS (all 7 primitives + ordered batch)

| Primitive | Evidence |
|---|---|
| `home` | 3 executions, 1 outcome each, accepted revision invalidated |
| `launch_app` (Settings, bundle id) | 3 executions, 1 outcome each |
| `tap_element` | PASS run 2: navigation-row target, 1 outcome; run 1 pick rule missed (see notes) |
| `tap_point` | in-bounds point, 1 outcome, no adverse state change observed |
| `swipe` | up then down (scroll restored), 1+1 outcomes |
| `drag` | small vertical drag, 1 outcome |
| `type_text` | PASS run 2: search-field focus then single space, 1 outcome; run 1 pick rule missed |
| ordered batch `[home, launch_app]` | completed=2, outcomes=2, accepted revision invalidated |

Zero-device-call preflight proofs on hardware, 4/4: stale revision,
foreign revision token, 33-action over-limit batch (`INVALID_REQUEST`), and
invalid later action (`TapPoint` out of bounds, `INVALID_REQUEST`) each left
the device-call counter unchanged. Every batch carried the exact current
`expected_revision`; every successful mutation invalidated it before the next
fresh observe. Screenshot-pixel coordinates were converted internally
(1206x2622 space accepted on-device).

## R4-04 — failure/recovery — PASS (ambiguity/disconnect environment-not-exercised)

- Historical runs 1-4 used owned-session drop -> observe -> `recover()` ->
  observe. That proved no replay, but not direct stale-plumbing recovery. The
  post-certification repair rerun below supersedes that gap with a distinct
  `close_session` -> `DEGRADED/UNAVAILABLE` -> `recover()` -> observe sequence.
- Runs 1-2 each saw one transient post-`recover` observe fail with
  `OBSERVATION_FAILED` (phase `lifecycle`, effect `NONE`, `retry_safe=true`);
  both were no-effect plumbing flakes, never an attempted mutation, and the
  dedicated run-3 sequence passed with zero trace errors.
- Ambiguous in-flight effect: `environment-not-exercised` — no ambiguous
  failure occurred naturally and none was manufactured (replaying a
  non-idempotent action to force ambiguity is forbidden). Deterministic A06
  covers `EFFECT_UNKNOWN` / `PARTIAL` / `retry_safe=false` semantics.
- Safe disconnect/unavailability: `environment-not-exercised` (unplug never
  performed).
- `close()` idempotent (second call clean), `status` reports `CLOSED`,
  post-close `observe` / `execute` / `recover` each reject with
  `RUNTIME_CLOSED`. Close released only owned handles (tunnel, WDA
  client/session); no unrelated process or resource was terminated.
- No blind replay occurred in any run.

## R4-05 — latency/trace baseline — PASS (no new infra)

Pooled across the three runs. Startup = first observe per run (includes
tunnel/runner/WDA startup). Steady = all later observes. Small samples report
max (`percentile_meaningful=false`); steady observe n=32 reports p95.
All values in ms.

| Sample | count | min | median | p95-or-max |
|---|---:|---:|---:|---:|
| observe, incl. startup | 3 | 3042.7 | 5483.2 | 15151.4 (max) |
| observe, steady | 32 | 1566.7 | 2525.6 | 4762.6 (p95) |
| execute `home` batch | 3 | 626.6 | 632.0 | 682.5 (max) |
| execute `launch_app` batch | 3 | 89.4 | 374.5 | 479.5 (max) |
| execute `tap_element` batch | 2 | 1125.6 | 1523.9 | 1922.3 (max) |
| execute `tap_point` batch | 1 | 753.0 | 753.0 | 753.0 (max) |
| execute `swipe` batch | 2 | 2920.9 | 2976.6 | 3032.3 (max) |
| execute `drag` batch | 1 | 1557.1 | 1557.1 | 1557.1 (max) |
| execute `type_text` batch | 1 | 925.8 | 925.8 | 925.8 (max) |
| execute ordered 2-action batch | 1 | 695.5 | 695.5 | 695.5 (max) |
| `recover` (recreate) | 4 | 398.4 | 1135.7 | 1499.8 (max) |

Trace policy holds: bounded in-memory history (256 records, never approached),
privacy allowlist intact (operation names, durations, action kinds, machine
error codes, counts, keyed invalidate-reason fingerprints only; raw reasons
are not retained). Steady observe is
bimodal (~1.6-2.6 s vs ~4.0-5.1 s); the slower cluster correlates with
post-plumbing-change captures. No runtime behavior was changed for numbers.

## Notes and honest residue

1. Run-1 element picks failed on harness matching rules (`label` only,
   exact role equality) because the projection carries the accessible name in
   `text` and WDA roles are `XCUIElementType*` tags; run 2 matched
   label/text/value plus role substrings with a small-rect guard (full-screen
   containers excluded). This was a harness rule defect, not a runtime defect;
   no production code changed.
2. `type_text` typed a single space into the Settings search field. Residue: one
   space character in a local non-submitting search field; the run left via
   Home. Bounded, non-destructive, user-clearable; recorded here instead of
   hidden.
3. Device left at Home Screen; runtime explicitly closed after every run.

## Verdict

Required R4 real-device capabilities pass on the current target environment:
R4-01 PASS, R4-02 PASS, R4-03 PASS, R4-04 PASS, R4-05 PASS, with exactly three
`environment-not-exercised` classifications (hotplug, live ambiguous effect,
live disconnect path) and no `gap`.

## Run 4 — canonical runner execution (repair)

The lane's first pass executed the matrix through lane-local scratch drivers
(deleted afterwards), which left the canonical runner subcommand
(`scripts/r4_device_matrix.py matrix`) still refusing to execute. That gap is
repaired: the subcommand now performs the real ordered matrix (single-lane
device mutation, public six operations + upstream probes only), and it was
executed end-to-end on the attached iPhone:

```text
.venv\Scripts\python scripts/r4_device_matrix.py matrix --confirm-device-run --evidence-dir docs/evidence
# exit 0; 29/29 steps passed; aborted=false; failed_steps=[]
```

Retained machine evidence: `docs/evidence/20260905_r4-device-matrix-run4.json`
(written through the fail-closed privacy scan). Highlights: all cells R4-01
through R4-05 represented; all 7 action kinds executed (`home`, `launch_app`,
`tap_element`, `tap_point`, `swipe`, `drag`, `type_text`) plus the ordered
2-action batch; 4/4 zero-device-call preflight proofs; owned-session resume;
`recover` with zero replayed executes and a clean reconciled observe; zero
observe retries this run; close idempotent with 3x `RUNTIME_CLOSED`
rejections. Trace errors recorded were exactly the 5 expected no-effect
preflight rejections (3x `STALE_REVISION`, 2x `INVALID_REQUEST`). The latency
numbers in this historical Run-4 paragraph are superseded by the current
canonical machine JSON after the certification-repair rerun; current values
are steady observe n=21, median 1345.6 ms, and startup 1552.3 ms. The runs 1-3
findings and the verdict above are unchanged; the retained machine JSON is the
authority for current per-run timing values.

## Post-certification repair rerun — canonical current evidence

After independent certification identified that the earlier runner let
`observe()` heal the owned WDA session before `recover()`, the runner was
repaired and the canonical matrix was rerun on the attached USB iPhone from
commit `d2505f2` plus the already-committed runner repair:

```text
.venv\Scripts\python scripts/r4_device_matrix.py matrix --confirm-device-run --evidence-dir docs/evidence
# exit 0
# steps_passed=29 / steps_total=29
# aborted=false
# failed_steps=[]
```

The current retained machine evidence in
`docs/evidence/20260905_r4-device-matrix-run4.json` now records the repaired
R4-04 proof explicitly:

```text
owned-session-drop-resume:
  dropped-to=DEGRADED/UNAVAILABLE resumed-ready=True

recover-zero-replay:
  stale-before-recover=DEGRADED/UNAVAILABLE
  repaired=True
  replayed-executes=0
  reconciled-ready=True
```

This is the required direct proof that `recover()` itself rebuilds stale owned
session/plumbing before any reconciliation `observe()`. The same current run
also reconfirms all seven action primitives, ordered batch, 4/4 zero-device-call
preflight proofs, idempotent close, post-close rejections, and the same three
honest `environment-not-exercised` classifications only (hotplug, naturally
occurring ambiguity, physical disconnect). No R6 work was involved.
