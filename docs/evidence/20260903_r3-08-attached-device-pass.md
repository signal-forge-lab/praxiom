# R3-08 evidence — upstream-only attached-device bounded smoke PASS

- Goal: `goal-adaptive-agent-r3-greenfield-native-ios-runtime-v0-20260901`
- Task: R3-08 — Upstream-only attached-device smoke
- Date: 2026-09-03
- Host: Windows 11, CPython 3.12.10, repository venv `.venv`
- Verdict: **PASS — R3_COMPLETE**

This evidence closes the blocker recorded in
`20260901_r3-08-blocked.md`. The physical iPhone was connected by USB and the
bounded smoke was executed directly from this repository through the pinned,
unmodified upstream `pymobiledevice3`. No Phone Harness Python package,
process, MCP hop, subprocess, or downstream `pymobiledevice3` fork was used.

## 1. Device and upstream baseline

The authoritative upstream usbmux probe returned exactly one directly attached
device:

```text
DEVICE_COUNT=1
CONNECTION_TYPE=USB
```

Privacy-safe generic device facts read through upstream lockdown:

```text
device_class=IPHONE
product_type=iPhone18,3
product_version=26.6.1
```

No UDID, serial, ECID, MAC, IMEI, pair-record filename/content, screen text,
or raw action payload is recorded here.

Loaded dependency evidence:

```text
pymobiledevice3 version = 11.3.0
module root              = pymobiledevice3
direct_url.json          = present
commit                   = ec4ac06a850a6a884ca778350621f354faf347c6
repository               = https://github.com/doronz88/pymobiledevice3
```

The commit exactly matches the R1-audited upstream pin. The production
provenance guard also passes with zero Phone Harness dependencies.

## 2. WDA runner path

Upstream CoreDevice `AppServiceService.list_apps()` found an already-installed
`WebDriverAgentRunner-Runner`. The smoke launched it through the pinned upstream
`TestConfig` + `XCUITestService` path implemented by `IosTransport`; the runner
bundle identifier is intentionally omitted from this evidence because it is
not needed to establish the runtime contract.

This is an existing signed WebDriverAgent runner on the device, not a host-side
Phone Harness package/process or an execution hop through Phone Harness.

## 3. Bounded smoke results

The orchestrator's required 10-step smoke was executed as follows.

1. **Runtime import/start — PASS.** `NativeIosRuntime` was instantiated from
   this repository.
2. **Upstream provenance — PASS.** The loaded `pymobiledevice3` distribution
   is upstream 11.3.0 at commit
   `ec4ac06a850a6a884ca778350621f354faf347c6`.
3. **`status()` — PASS.** Before connection it reported
   `DISCONNECTED / NONE / NONE`, the expected side-effect-free initial state.
4. **First `observe()` — PASS.** Runtime became
   `READY / RSD_USERSPACE / READY`; screenshot and accessibility were both
   available. Captured frame and public screen size were `1206 x 2622`, PNG,
   with 586 normalized accessibility elements.
5. **Safe revision-bound action #1 — PASS.** `Home()` completed once,
   invalidated the accepted revision, and reported one `home` outcome.
6. **Fresh `observe()` — PASS.** A new revision was generated and screenshot
   + accessibility remained available.
7. **Safe different primitive #2 — PASS.** `LaunchApp` launched Apple's
   Settings app by bundle id. It completed once, invalidated the accepted
   revision, and reported one `launch_app` outcome. This is a non-destructive
   local navigation action.
8. **Fresh `observe()` — PASS.** A new revision was generated; screenshot and
   accessibility remained available, with 183 normalized elements on the
   resulting screen.
9. **`close()` — PASS.** Status became `CLOSED / NONE / NONE` and the current
   revision was cleared.
10. **Latency/trace inspection — PASS.** Five operation records were retained,
    with zero trace errors.

## 4. Real-device latency evidence

Privacy-safe trace output from the successful bounded smoke:

| Operation | Duration |
|---|---:|
| observe #1, including initial RSD/WDA startup | 7154.0 ms |
| execute Home | 636.8 ms |
| observe #2 | 4999.7 ms |
| execute launch Settings | 120.7 ms |
| observe #3 | 1943.0 ms |

Per-action timings were approximately 636.7 ms for `home` and 120.6 ms for
`launch_app`. Trace counters were `observe=3`, `execute=2`, errors=`0`.

The initial observation includes tunnel/WDA startup and should not be treated
as steady-state observe latency. R4 owns broader latency characterization.

## 5. Safety / effect-semantics result

- Every mutating batch used the exact current `expected_revision`.
- Each successful mutation invalidated that revision before the next observe.
- Each follow-up observe produced a fresh revision.
- No timeout, ambiguous effect, blind retry, recovery replay, or partial
  action occurred.
- Actions were limited to Home and launching Apple's Settings app; no purchase,
  submit, delete, message, account/security mutation, or domain/game automation
  was performed.
- The runtime was explicitly closed after the bounded smoke.

## 6. Completion-gate verdict

All R3-08 acceptance conditions are satisfied:

- connected-device bounded smoke succeeds;
- direct upstream USB/RSD/WDA path succeeds;
- screenshot + accessibility observation succeeds;
- two safe revision-bound primitives succeed with fresh observations between
  them;
- no Phone Harness host package/process/MCP hop is in the execution path;
- no downstream `pymobiledevice3` fork delta or runtime-local upstream patch is
  required;
- no blind replay occurs;
- real-device operation latency is captured;
- evidence contains no raw private device identifiers.

**R3-08 = PASS. R3 = R3_COMPLETE (33/33 points, 100%).**

The subsequent controlled product/package rename was independently
regression-tested, including a second real-device smoke. See
`docs/evidence/20260903_praxiom-rename.md`.
