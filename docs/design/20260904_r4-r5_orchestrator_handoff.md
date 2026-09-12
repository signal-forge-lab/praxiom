# Praxiom R4 + R5 — Orchestrator Handoff

Date: 2026-09-04

Status: **implementation authority for the next Praxiom execution block**

Sensitivity: **PUBLIC**

This package is written so a DSH multi-agent run can implement, verify, review,
repair, and close R4 and R5 without relying on prior chat context. The executing
Planner must inspect current files and real host/device state first. Current
evidence overrides cached statements in this document.

## 1. Goal

Complete the next critical-path block after R3:

1. **R4 — Full real-device acceptance / evidence comparison (20 points)**:
   prove the current greenfield Native iOS Runtime v0 supplies all required R2
   device capabilities on real hardware, characterize transport/failure/latency
   behavior, and compare required behavior with historical Phone Harness
   evidence without adding a Phone Harness dependency.
2. **R5 — Separation closure (7 points)**: after R4 acceptance, close the
   execution-foundation migration so Phone Harness is reference-only in code
   and active planning.

R4 and R5 are one execution block, but **R5 must not be accepted before the R4
exit gate passes**.

## 2. Current accepted baseline

Repository:

```text
<repository-root>
```

Current accepted R3 baseline at authoring time:

- repository/package/runtime identity: `praxiom` / `praxiom.ios_runtime`;
- R3: **R3_COMPLETE, 33/33 points, 100%**;
- deterministic suite: **130 passed** at the R3 closure checkpoint;
- directly attached iPhone bounded smoke: PASS;
- current public runtime boundary: exactly six async operations:
  `status`, `observe`, `execute`, `invalidate`, `recover`, `close`;
- upstream device dependency: unmodified `doronz88/pymobiledevice3`, pinned at
  commit `ec4ac06a850a6a884ca778350621f354faf347c6`;
- production/build/runtime Phone Harness dependency: **none**;
- current Git baseline at handoff authoring: `acc16b8`.

The executing agents must re-check Git status, commit, tests, installed upstream
pin, attached devices, WDA reachability, and current source before editing.

Preparation-time host probe on 2026-09-04 returned `DEVICE_COUNT=0`. This is
only a point-in-time observation, not a permanent assumption. Re-probe at run
start. If no device is attached, complete every deterministic/AI-executable R4
and R5-preparatory task, retain the exact physical gate, and do not claim the
real-device R4 exit gate passed.

## 3. Normative references

### Current Praxiom sources

Read these first:

```text
README.md
pyproject.toml
docs/PROVENANCE.md
docs/evidence/20260901_r3-native-ios-runtime-v0-completion.md
docs/evidence/20260903_r3-08-attached-device-pass.md
docs/evidence/20260903_praxiom-rename.md
src/praxiom/ios_runtime/runtime.py
src/praxiom/ios_runtime/transport.py
src/praxiom/ios_runtime/observation.py
src/praxiom/ios_runtime/executor.py
src/praxiom/ios_runtime/models.py
src/praxiom/ios_runtime/trace.py
tests/
```

### Historical specification/evidence authority

Phone Harness remains **historical/reference evidence only**. Reading these
documents is allowed; importing/calling/copying production Phone Harness code is
not.

```text
<legacy-reference-root>\docs\design\20260831_r2-native-ios-runtime-contract.md
<legacy-reference-root>\docs\design\20260831_r3-plus-execution-plan.md
<legacy-reference-root>\docs\design\20260831_r0-baseline-freeze.md
```

The R2 contract and current Praxiom behavior are authoritative. Historical
Phone Harness behavior is evidence, **not an API compatibility target**.

## 4. Hard invariants

These are acceptance requirements, not preferences.

1. **Sensitivity is public.** Every authored DSH task must explicitly set
   `sensitivity: 'public'`. Local checkout paths do not make this work private.
2. Workflow source may use only `modelHint: fast | balanced | deep`. Provider
   and model selection belongs exclusively to Stable Routing.
3. Native iOS Runtime keeps the R2 six-operation public surface unless a
   focused real-device acceptance failure proves a contract change is required.
4. No Phone Harness import, subprocess, MCP hop, compatibility shim, runtime
   fallback, renamed source copy, or production dependency.
5. Keep the pinned, unmodified upstream `pymobiledevice3` baseline unless a
   generic upstream defect is reproduced and the existing R1 fork gate is met.
6. No blind replay after an action with ambiguous effect.
7. Whole-batch preflight, mandatory revision validation, revision-bound element
   refs, bounded batch size, effect-aware errors, and owned-resource close remain
   intact.
8. Device mutation is **single-lane**. Never run two mutating agents against the
   same iPhone concurrently.
9. Real-device actions must be bounded and reversible/non-destructive. Never
   purchase, submit, send a message, delete user content, modify account/security
   settings, install profiles, or perform domain/game automation as acceptance
   actions.
10. Evidence must omit raw UDID, serial, ECID, MAC, IMEI, pair records,
    credentials, cookies/tokens, raw screen text, screenshots containing user
    data unless explicitly redacted, and raw action payloads.
11. Do not weaken tests or acceptance gates to make R4/R5 pass.
12. R5 begins only after R4 exit is independently reviewed and accepted.

## 5. Target architecture

R4 is an acceptance-and-hardening phase, **not a redesign**. Preserve the deep
module boundary already established in R3:

```text
Agent / acceptance caller
        |
        v
NativeIosRuntime                      public six-operation contract
        |
        +--> ObservationEngine        observation + revision ownership
        +--> ActionExecutor           whole-batch preflight + ordered mutation
        +--> IosTransport             upstream RSD/WDA/CoreDevice composition
        +--> Trace                    privacy-safe timing/error evidence
        |
        v
unmodified upstream pymobiledevice3
        |
        v
WDA / CoreDevice / iPhone
```

Prefer **test/evidence harnesses and narrow root-cause fixes** over adding new
runtime abstractions. Do not pre-create provider/factory/plugin frameworks.

If R4 needs a reusable real-device runner, keep it outside production runtime,
preferably under `scripts/`; it must call only the public Praxiom runtime plus
upstream provenance probes. A real-device test placed under `tests/` must be
explicitly excluded/skipped from the default phone-independent suite. The
default deterministic `pytest` command must remain runnable without a phone.

## 6. R4 requirements and implementation work

R4 total: **20 points**.

### R4-01 — Transport/lifecycle matrix — 3 points

Purpose: prove the transport path actually required by the target Windows +
iPhone environment and its lifecycle behavior.

Required work:

- re-prove attached-device discovery through the pinned upstream package;
- exercise the supported current path (at minimum attached USB plus in-process
  `RSD_USERSPACE` when that remains the target path);
- characterize connect -> READY -> recreate/recover -> close transitions;
- test stale owned WDA/session handling and fresh session establishment;
- test hotplug/disconnect behavior when it can be induced safely; classify any
  physically-required unplug/replug step explicitly instead of fabricating it;
- evaluate Wi-Fi only if the current target environment actually requires it
  or the device is currently available over that transport. Do not add Wi-Fi
  scope merely to satisfy a matrix label.

Acceptance:

- lifecycle states are predictable and privacy-safe;
- supported normal path does not require external `tunneld`;
- recovery/close touches only owned resources;
- environment-only and physically blocked cases are distinguished from runtime
  defects.

### R4-02 — Observe matrix — 3 points

Purpose: prove real-device observation/revision behavior beyond the R3 smoke.

Required work:

- repeated screenshot + accessibility capture rounds;
- screen/window sizing and coordinate-space consistency;
- fresh revision creation and old-revision invalidation;
- element-ref binding to exactly one revision;
- capture behavior before/after safe navigation and after recovery;
- record source availability and bounded element counts without retaining screen
  content in normal evidence.

Acceptance:

- R2-A02/A04/A09 semantics remain true on real hardware;
- screenshot/accessibility share one logical revision where intended;
- stale revisions/refs fail before a device mutation;
- coordinate dimensions stay internally consistent.

### R4-03 — Action matrix — 5 points

Purpose: prove every v0 action primitive and bounded batch semantics on a real
device.

Required primitive coverage:

```text
tap_point
tap_element
drag
swipe
type_text
home
launch_app(bundle_id)
bounded ordered batch
```

Use a safe system-app context such as Settings/Home and reversible UI states.
For text input, use a non-submitting local field (for example a Settings search
field) and clear/exit afterward when practical. Use only bundle identifiers for
launch.

Required checks:

- current expected revision is mandatory for every batch;
- full preflight occurs before the first side effect;
- stale revision / foreign element ref / invalid later action / over-limit
  batch make zero device calls;
- successful mutation invalidates the accepted revision;
- fresh observe is taken before planning the next state-sensitive action;
- coordinates are accepted in screenshot pixels and converted internally;
- ordered batch result counts/timings are accurate.

Acceptance: all action primitives pass with bounded non-destructive evidence,
and deterministic R2-A03/A04/A05/A09/A10 remain green.

### R4-04 — Failure/recovery matrix — 5 points

Purpose: prove safe behavior when WDA/session/transport state is stale or an
action result is ambiguous.

Required work:

- induce failures only through resources owned by the Praxiom runtime/test
  harness where possible;
- stale/closed WDA session;
- stale transport/session recreation;
- disconnect/unavailability path when safely reproducible;
- definitive action failure vs connection-class/timeout ambiguous effect;
- `EFFECT_UNKNOWN` / `PARTIAL` metadata where applicable;
- verify `retry_safe=false` after an attempted ambiguous mutation;
- verify `recover()` rebuilds plumbing only and replays zero actions;
- require fresh observation/reconciliation after ambiguous execution/recovery;
- verify idempotent `close()` and no unrelated process/resource termination.

Never manufacture an ambiguous test by repeatedly sending the same
non-idempotent device action. Prefer controlled fakes for exact error semantics
and owned-session disruption for real-device plumbing evidence.

Acceptance: R2-A06/A07/A08 remain deterministic and the real-device recovery
path preserves no-blind-replay semantics.

### R4-05 — Latency/trace baseline — 2 points

Purpose: establish a useful, privacy-safe performance baseline for R7/R9
optimization without changing runtime behavior merely to improve numbers.

Collect bounded samples for:

- initial observe including startup;
- steady-state observe;
- screenshot/accessibility contribution when separable with existing evidence;
- each safe action primitive;
- bounded multi-action batch;
- recovery/recreate;
- close if useful.

Report at minimum count, min/median/p95-or-max when sample size is too small for
a meaningful percentile, and clear separation of startup vs steady state.

Trace-volume policy:

- keep current bounded in-memory history unless evidence proves it insufficient;
- do not add a database, telemetry service, or unbounded trace stream in R4;
- preserve the privacy allowlist.

### R4-06 — Old-vs-new evidence report — 2 points

Purpose: compare **required behavior**, not implementation ancestry.

Produce a retained report mapping:

- each R2 required capability/acceptance scenario;
- current Praxiom real-device evidence;
- relevant historical Phone Harness/R0 evidence when useful;
- verdict: `equivalent-required`, `Praxiom-safer`, `legacy-only-not-required`,
  `gap`, or `environment-not-exercised`;
- exact remediation/evidence reference for every `gap`.

Do not turn legacy-only behavior into a Praxiom requirement without R2/R4
evidence.

### R4 exit gate

R4 is complete only when all of the following are true:

- full R2-A11 is represented by retained real-device evidence;
- R4-01 through R4-06 are accepted by an independent non-author review;
- deterministic tests pass;
- required real-device capabilities pass on the current target environment;
- failures are classified honestly as runtime bug, upstream gap, environment,
  or physical gate;
- no permanent upstream fork is introduced unless the R1 gate is satisfied;
- no Phone Harness execution dependency is introduced;
- Git diff contains only intentional R4 work and evidence.

If a physically required device action is impossible, continue every
AI-executable task and report the smallest explicit blocker. Do not falsely mark
R4 complete.

## 7. R5 requirements and implementation work

R5 total: **7 points**. Start only after R4 exit review passes.

### R5-01 — New-system dependency audit — 2 points

- production dependency graph contains no Phone Harness package;
- no import, subprocess, process-control, MCP, network fallback, or runtime edge
  points to Phone Harness;
- `scripts/check_provenance.py` remains fail-closed and passes;
- add only the smallest missing regression check if R4 exposes an audit gap.

### R5-02 — Provenance/source-copy review — 2 points

- inspect current production source and dependency declarations;
- prove no Phone Harness production source was copied, renamed, or adapted into
  Praxiom;
- distinguish acceptable contract/evidence fixture provenance from prohibited
  code copying;
- retain the review result under `docs/evidence/`.

### R5-03 — Active-path documentation / XMind — 1 point

- update Praxiom repository docs so the active execution path is unambiguously
  Praxiom -> upstream `pymobiledevice3` -> WDA/CoreDevice/iPhone;
- update the active project XMind representation when a writable XMind tool is
  available to the executing environment, marking Phone Harness historical and
  Praxiom active;
- if the XMind tool is genuinely unavailable, preserve the exact requested node
  changes as a small evidence artifact and report that external artifact gate
  explicitly; do not claim the XMind update happened.

The same honesty rule applies if the historical Phone Harness reference tree is
outside the executing agent's filesystem scope: continue all other work, record
the exact scope blocker, and do not claim a historical comparison/source-copy
review that was not actually performed.

### R5-04 — Historical-reference classification — 1 point

- classify remaining Phone Harness mentions in planning/evidence as
  `historical`, `regression evidence`, or `migration provenance`;
- remove or correct active-planning language that implies Phone Harness remains
  an execution dependency;
- do not delete useful historical evidence merely to obtain zero text hits.

### R5-05 — Migration completion report — 1 point

Produce a final retained report covering:

- R4 evidence summary and unresolved environment coverage, if any;
- dependency/provenance scan results;
- execution-path statement;
- old-vs-new required-behavior comparison;
- tests and real-device commands/results;
- independent review findings and repairs;
- exact commits/files;
- rollback notes;
- final `R5_COMPLETE` or a precise blocker.

### R5 exit gate

R5 is complete only when:

- R4 is already accepted;
- Phone Harness is reference-only in code and active planning;
- production/build/runtime dependency and execution edge count is zero;
- provenance/source-copy review passes;
- active-path docs are current;
- migration completion report is independently reviewed;
- deterministic regressions pass after final documentation/code repairs;
- Git working tree is clean after the intended checkpoint commit(s), excluding
  explicitly documented user/concurrent work that must not be overwritten.

## 8. Orchestration graph and concurrency

Maximum useful concurrency: **3**. Prefer less when file/device ownership
overlaps.

### Phase A — current-state audit (up to 3 read-only agents)

1. **Contract/evidence auditor — deep / public**
   - reconcile R2, R3 completion evidence, and this handoff;
   - produce a precise R4/R5 acceptance checklist;
   - identify any conflict without editing production code.
2. **Runtime/test auditor — deep / public**
   - inspect current source/tests and map each R4 matrix cell to existing code,
     missing deterministic coverage, or real-device-only evidence;
   - propose the smallest implementation delta.
3. **Host/device/provenance auditor — balanced / public**
   - inspect Git, Python/pin, device count/transport, WDA availability, existing
     runner, provenance guard, and safe evidence constraints;
   - no device mutation in this audit.

Gate A: freeze one minimal implementation/evidence plan before edits.

### Phase B — deterministic harness/fixes

Use at most two implementation lanes only when their files do not overlap:

- acceptance harness + deterministic regressions — balanced / public;
- narrow transport/trace/runtime repair proven by an existing failing check —
  balanced or deep / public.

Run focused tests after each root-cause repair. Do not refactor unrelated code.

### Phase C — real-device acceptance

**One mutating device lane only.** Other agents may analyze already-captured
privacy-safe evidence in parallel, but they must not control the device.

Suggested order:

```text
transport/lifecycle
  -> observe/revision
  -> safe primitive actions + batch
  -> owned-session/recovery failures
  -> latency/trace summary
  -> old-vs-new evidence report
```

After every state-sensitive mutation, follow the R2 revision/fresh-observation
rules.

### Phase D — independent R4 review and repair

Assign a **deep / public non-author reviewer** to correctness, architecture,
safety/effect semantics, provenance, privacy, tests, and evidence sufficiency.

Repair every blocking finding with the smallest change, rerun affected focused
checks, the full deterministic suite, and any real-device cell invalidated by
the repair. Re-review until no blocking R4 finding remains.

### Phase E — R5 separation closure

Only after Phase D passes:

- dependency/provenance audit;
- source-copy review;
- active-path docs/XMind work;
- historical-reference classification;
- migration completion report.

### Phase F — independent R5/final review and certification

Run a non-author deep review of R5 and the combined R4+R5 final state. Repair
blocking findings, rerun relevant checks, then allow the runtime-owned Goal
Certification path (Independent Reviewer / Repair / Re-review / Final Judge) to
decide the orchestration Goal.

## 9. Model-role guidance

Workflow code must not name providers/models.

Use semantic roles approximately as follows:

- `fast`: bounded repository/status scans, formatting checks, deterministic
  evidence extraction;
- `balanced`: ordinary implementation, test harnesses, docs/evidence writing;
- `deep`: contract reconciliation, failure/effect semantics, architecture,
  independent reviews, final comparison/certification preparation.

All tasks: `sensitivity: 'public'`.

## 10. Verification requirements

At minimum preserve these deterministic gates:

```text
.venv\Scripts\python -m pytest -q
.venv\Scripts\python scripts\check_provenance.py
```

Before using a command copied from this handoff, inspect the current repository
and use its current canonical command if it has changed.

Real-device verification must retain a privacy-safe evidence report under
`docs/evidence/` with exact pass/fail/blocker classification and operation
timings. A passing deterministic fake is not a substitute for R4 real-device
evidence.

## 11. Change / Git policy

- Inspect current Git state before edits and preserve concurrent user work.
- Keep changes focused on R4/R5; no R6+ implementation.
- Prefer small checkpoint commits that leave the repository runnable.
- Never commit logs, raw screenshots/device dumps, credentials, pair records,
  tokens, browser/device profiles, caches, or other private runtime material.
- Do not push/publish unless explicitly instructed by the user.
- Final report must list exact commits and whether remote push occurred.

## 12. Completion definition

For the **R4+R5 implementation Goal**, 100% means:

- all AI-executable R4/R5 implementation, tests, evidence, reviews, repairs,
  final verification, and retained reports are complete;
- every R4 and R5 gate is accepted, or the Goal reports one precise external or
  physical blocker instead of claiming completion;
- no unresolved blocking review finding remains;
- no requested R6+ work was started;
- runtime-owned Goal Certification has a final verdict;
- final output reports points completed, exact evidence, tests, commits,
  remaining physical/environment limits, and final R4/R5 status.

