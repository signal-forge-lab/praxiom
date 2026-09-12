# Phase B real-device baseline — 2026-09-10

Status: **BASELINE ESTABLISHED / LIVE OPTIMIZATION STILL OFF**

This evidence supersedes only the earlier statement that physical Wi-Fi Runtime
establishment had not yet been demonstrated. It does not alter the historical
Phase A certification record.

## Safety / activation posture

The first real-device baseline retained the frozen post-Phase-A posture:

- telemetry: ON;
- experience recorder: constructed/ON;
- learning snapshot projection: ON;
- shadow advisor: constructed/ON;
- adaptive live application: OFF;
- bounded-sequence live application: OFF;
- no automatic replay after a mutation;
- no Phone Harness fallback and no external `tunneld` dependency.

The read-only baseline performed no mutation. A separate execution baseline
performed one low-risk `home` action through `ExecutionCoordinator.run_async`
using a fresh observation revision, then re-observed after the accepted action
invalidated that revision.

## Physical Wi-Fi Runtime result

The paired iPhone was demonstrated over the production transport path:

`Bonjour/RemotePairing -> in-process userspace RSD -> WDA -> NativeIosRuntime`

Observed final transport state:

- lifecycle: `READY`;
- transport: `RSD_USERSPACE`;
- WDA: `READY`;
- MCP `praxiom_observe`: successful;
- full-screen frame: 1206 x 2622 pixels;
- accessibility source: 610 elements on the connection smoke observation.

Raw device identifiers, addresses, pairing material, screenshots, and element
text are intentionally not retained in this evidence file.

## Windows integration findings repaired before baseline

Two real-device blockers were found that deterministic fake coverage could not
surface:

1. Windows Uvicorn used a Proactor event loop, while the pinned
   `pymobiledevice3` Bonjour/RemotePairing path requires selector semantics on
   this host. The MCP entrypoint now uses `SelectorEventLoop` on Windows.
2. The pinned upstream `WdaServiceClient` special-cases
   `RemoteServiceDiscoveryService` by reconnecting through usbmux. That breaks
   Wi-Fi-only RSD. Praxiom now wraps the already-established RSD provider with
   a minimal delegate so WDA traffic continues through the RSD dialer.

The MCP virtualenv also uses Python 3.13+ on Windows. On Python 3.12 the
RemotePairing TCP path depends on the legacy native `sslpsk_pmd3` DLL, which
failed to load on this host; Python 3.13+ uses the standard-library TLS-PSK API.

## Durable observation baseline

Run: `phaseb-real-device-observe-baseline-20260910`

- full observations: 10 / 10 successful;
- stable screen dimensions across all samples: yes;
- accessibility element count: 610 min / 610 max;
- unique observation revisions: 10;
- failures: 0;
- recoveries: 0;
- execute actions: 0;
- run duration: 57.182 s;
- observe total: 54.550 s;
- observe median: 4.847 s;
- observe p90: 9.570 s.

Durable journal projections were produced under the external Praxiom state
root (`events.jsonl`, `summary.json`, `learning_snapshot.json`). The learning
snapshot contains zero episodes, as expected for a read-only run, and confirms
that no trust-token authority was persisted.

## Durable execution baseline

Run: `phaseb-real-device-execute-baseline-20260910`

- pre-action full observe: successful;
- action: one `home` operation through `ExecutionCoordinator.run_async`;
- attempt state: `succeeded`;
- effect: `NONE`;
- automatic retry/replay: none;
- accepted revision invalidated: yes;
- post-action fresh observation revision: yes;
- run-scoped Coordinator ledger executions: 1;
- runtime execute count: 1;
- execute median/p90: 243.014 ms (single sample);
- runtime observe count: 2;
- failures: 0;
- recoveries: 0;
- sequence live application: OFF.

This proves the live async Coordinator -> Runtime mutation path over Wi-Fi
without enabling learned/adaptive control.

## Post-baseline reconnect robustness

The live MCP smoke later reproduced one additional lifecycle edge case: an
upstream userspace tunnel watcher can clear its owned RSD after the outer
transport is lost while Praxiom still holds WDA/session references. Before the
repair, `status` could therefore continue to project `READY` even though the
next observation failed.

`IosTransport` now treats a tracked tunnel whose `rsd` has been cleared as
disconnected. The next `connect()` tears down only the stale owned plumbing and
performs a fresh discovery/tunnel/WDA establishment; it never retries or
replays a device action. Deterministic transport coverage includes this exact
state transition.

After loading the repair in a fresh MCP process, two consecutive
`praxiom_observe` calls succeeded over the Wi-Fi Runtime path. This closes the
stale-READY lifecycle issue without changing the six-operation Runtime surface
or the Coordinator mutation-authority boundary.

## Promotion decision

**Do not enable Phase C adaptive live application yet.**

The physical transport and baseline path are now proven, but the current
baseline contains only one controlled execution and zero Skill-level learning
episodes/shadow decisions. It is enough to establish transport/observe/execute
latency and safety plumbing, but not enough evidence to tune confidence
thresholds, useful sequence sizes, cheap-validation eligibility, or minimum
episode counts.

The next activation step should collect representative domain workload while
keeping adaptive live and sequence live OFF, then compare actual behavior with
shadow recommendations before promoting any optimization.

## Offline continuation prepared while the device is disconnected

The remaining Phase B collection work no longer requires keeping the iPhone
attached between runs. Two device-independent tools are prepared for the next
connection window:

- `scripts/phaseb_domain_shadow_workload.py` runs only the already-certified
  low-risk/reversible Merge Boss and GoGoMatch launch behaviors through
  `RunSession -> SkillExecutor -> ExecutionCoordinator -> NativeIosRuntime`.
  It keeps adaptive live application and bounded-sequence live application
  OFF, requires explicit device-run confirmation and bundle mapping, stops on
  the first non-NONE/unsuccessful attempt, never replays automatically, and
  uses a unique durable run id by default.
- `scripts/phaseb_shadow_report.py` is offline/read-only. It aggregates the
  privacy-safe journals and reports domain attempts, Experience/learning
  records, actual-vs-shadow policy decisions, latency, failures/effects,
  recovery/fallback evidence, and remaining evidence gaps. It never performs
  or recommends automatic Phase C promotion; tuning thresholds remain
  intentionally unset until representative real-device data exists.

Applied to the two baseline runs above, the offline report currently returns
`HOLD` with no safety blocker and exactly the expected evidence gaps:
representative domain attempts, shadow policy decisions, and learning records
have not yet been collected. Those are the next live-data targets when the
iPhone is reconnected.

## Final verification after reconnect repair

- full deterministic suite: 477 passed;
- Phone Harness provenance guard: PASS;
- Runtime/agent boundary guard: PASS;
- `compileall`: PASS;
- `git diff --check`: PASS;
- MCP smoke after restart: two consecutive `praxiom_observe` calls succeeded;
- Secure MCP Tunnel: ready;
- adaptive live apply: still OFF;
- sequence live apply: still OFF.

## Representative domain shadow follow-up

The next Phase B live window was completed with the same frozen safety posture
(adaptive live OFF, sequence live OFF, first non-NONE stops the lane, no blind
replay).  The canonical successful representative run is:

`phaseb-domain-20260910T115801Z-868993d4`

It produced:

- Merge Boss launch: 2 / 2 `succeeded`, `effect=NONE`, `replayed=false`;
- GoGoMatch launch: 2 / 2 `succeeded`, `effect=NONE`, `replayed=false`;
- representative domain attempts: 4;
- learning records: 4;
- shadow policy decisions: 4;
- recoveries: 0;
- safety blockers: 0.

Together with the observation and execution baselines, the offline reporter
returns 3 completed runs, 5 attempts, 5 / 5 `effect=NONE`, no evidence gaps,
and no safety blockers.  Automatic promotion remains disabled and the report
correctly returns `MANUAL_REVIEW_REQUIRED` rather than enabling Phase C.

## Phase B shadow-input wiring repair

Reviewing the first representative run exposed a production wiring gap rather
than a threshold problem.  `SkillExecutor` created each `ShadowContext` with
the default `pending=1`, so `decide_batch` could never recommend a bounded
batch larger than one even when the caller had multiple known pending actions.

The repair retained the certified execution path unchanged and added only an
observational `shadow_pending` value along this path:

`RunSession.execute_skill -> SkillExecutor.execute -> ShadowContext.pending`

The Phase B runner supplies the remaining iteration count as that shadow-only
metadata.  Actual execution is still one action at a time and sequence live
application remains OFF.  The run summary now reads the already-journaled
`policy.decision.payload.recommended_batch_size`, while retaining the older
`sequence.decision` representation as a compatibility fallback.

The ObservationPolicy result remains `full-observe` for the launch workload.
This is intentional: the launch workload does not currently provide a valid
cheap causal postcondition to the R7 validator, so no synthetic validator
evidence or lowered safety threshold was introduced merely to obtain an
optimization recommendation.

Repair commit: `2be6eb7` (`fix(phaseb): wire shadow pending and block locked runs`).

## Locked-device failure and preflight repair

During the current-head follow-up the iPhone had become locked.  Praxiom's
accessibility observation explicitly exposed the SpringBoard lock marker and
the Japanese lock-state labels.  Before the new preflight existed, two bounded
launch attempts failed with `PARTIAL / ACTION_FAILED`; each run stopped at the
first failure and did not replay:

- `phaseb-domain-20260910T121839Z-7c0371fc`;
- `phaseb-domain-20260910T122301Z-2dfb217d`.

This revealed a real contract-enforcement gap: the Merge Boss launch behavior
already declared `device unlocked` as a precondition, but the Phase B live
runner did not verify that condition before dispatching `launch_app`.

The runner now checks the fresh observation for the machine-oriented
SpringBoard lock marker before any domain mutation.  When locked it returns
`status=blocked`, `stop_reason=device-locked`, performs zero attempts and zero
actions, and the CLI distinguishes that external precondition (`exit 2`) from
an execution failure (`exit 1`).  The first physical proof of the new guard was
`phaseb-domain-20260910T122746Z-26935289`, which stopped with zero actions,
zero attempts, and zero failures.

No automatic unlock, passcode/biometric handling, or retry of a failed launch
was added.

## Current physical blocker and Phase C decision

The device remains locked at the end of this follow-up.  A later read-only
Runtime observation also found that the existing WDA runner had a stale
application attachment (`local.pid.0` no longer running).  A proposed generic
"retry a 404 read after recreating the WDA session" change was tested locally,
but it did not repair the actual physical state because the new WDA session
was attached to the same stale application.  That uncommitted change was
therefore reverted rather than adding ineffective retry complexity.

Accordingly:

- Phase C adaptive live application remains **OFF**;
- bounded-sequence live application remains **OFF**;
- the successful representative Phase B evidence remains valid historical
  evidence, but the new `shadow_pending` wiring still needs one clean
  current-head physical run after the operator unlocks the iPhone;
- no further automated mutation is safe or useful while the unlock
  precondition is false.

The remaining physical step is deliberately small: unlock the already-paired
iPhone, then rerun the same 2 x 2 representative shadow workload on the current
clean HEAD and regenerate the offline report.  No design or code decision is
pending before that step.

Final MCP restoration check: the local Praxiom MCP server was restarted and
`praxiom_status` again responded normally.  The Runtime initially projects
`DISCONNECTED` as expected before a connection attempt.  A subsequent
read-only `praxiom_observe` returned `OBSERVATION_FAILED` with `effect=NONE`,
`retry_safe=true`, and no revision invalidation; therefore the connector/server
path is restored, while physical observation remains blocked by the locked /
stale-WDA device state described above.  No mutation was attempted by this
final check.

### WDA stale-session READY projection hardening

That final MCP check exposed one additional lifecycle defect: after the
session-scoped WDA request returned HTTP 404 because its backing XCTest
application was no longer present, the cached `session_id` remained set.
`IosTransport.snapshot()` therefore continued to report `READY / WDA READY`
even though the immediately preceding observation had proved that the session
was unusable.

The repair is deliberately state-oriented rather than retry-oriented.  All
session-scoped WDA primitives now share one internal call seam.  If WDA returns
HTTP 404, Praxiom clears only the cached session id and propagates the original
failure unchanged.  It does **not** retry the request.  This applies equally to
read and mutation primitives, so a failed swipe/type request can never be
silently replayed.  A later explicit `connect()`/`observe()` may create a new
session under the existing certified lifecycle rules.

Deterministic tests prove both sides of the contract:

- a read-side WDA 404 makes the transport `DEGRADED`, performs one request
  only, and permits a later explicit reconnect to create a new session;
- a mutation-side WDA 404 also makes the transport `DEGRADED`, performs the
  mutation primitive exactly once, and an explicit reconnect does not replay
  it.

Physical MCP validation matched the deterministic result.  After loading the
repair, the first read-only `praxiom_observe` still failed because the locked
device's existing WDA runner remained physically stale, but the following
`praxiom_status` correctly projected `DEGRADED / WDA UNAVAILABLE` with
`last_error_code=OBSERVATION_FAILED` instead of the previous false `READY`.
A second explicit read-only observation remained blocked and status stayed
`DEGRADED`.  No device mutation was issued during either check.

## Final unlocked Phase B acceptance — 2026-09-11

After the operator unlocked the iPhone, the stale device-side WDA runner was
re-established without persisting any machine-specific runner identifier in
the repository.  A fresh Praxiom MCP read-only observation then succeeded over
the normal `RemotePairing -> userspace RSD -> WDA` path and returned a fresh
revision from the unlocked AliExpress foreground state.

The final current-head representative shadow workload was then executed with
adaptive live application and sequence live application still OFF:

- run: `phaseb-domain-20260911T082707Z-ad634216`;
- Merge Boss launch: 2 / 2 `succeeded`, `effect=NONE`, `replayed=false`;
- GoGoMatch launch: 2 / 2 `succeeded`, `effect=NONE`, `replayed=false`;
- execute actions: 4, all actual batch size 1;
- learning records: 4;
- shadow policy decisions: 4;
- failures: 0;
- recovery attempts: 0;
- sequence live application: OFF;
- adaptive live application: OFF.

The repaired `shadow_pending` wiring was proven physically in this run.  The
shadow batch recommendation distribution was:

- recommended size 2: 2 decisions;
- recommended size 1: 2 decisions;
- actual multi-action sequences: 0, as required while sequence live remains
  disabled.

The canonical four-run offline report now contains the observation baseline,
the single-action execution baseline, the original representative domain run,
and this final current-head representative run.  Aggregate result:

- completed runs: 4;
- total attempts: 9;
- successful `effect=NONE`: 9 / 9;
- representative domain attempts: 8 (`mergeboss=4`, `gogomatch=4`);
- learning records: 8;
- shadow policy decisions: 8;
- shadow optimization recommendations: 2;
- rejected journal records: 0;
- recoveries: 0;
- evidence gaps: none;
- safety blockers: none;
- reporter decision: `MANUAL_REVIEW_REQUIRED`;
- automatic promotion: false.

### Final Phase C promotion decision

**Phase B is accepted as complete.  Phase C adaptive live application remains
HOLD / OFF.  Bounded-sequence live application also remains OFF.**

This is no longer caused by a physical blocker.  The final unlocked run closes
the previously outstanding current-head physical acceptance item.  The HOLD is
instead the deliberate D2=A manual promotion decision: the design requires
real-device data to tune or explicitly accept confidence thresholds, useful
sequence sizes, cheap-validation eligibility by domain/state, latency budgets,
and minimum evidence/episode counts before learned/adaptive choices become
authoritative.

The current evidence is sufficient to prove the Phase B plumbing and to show a
useful bounded-batch shadow signal for the two pending launch operations, but it
is still intentionally narrow:

- all representative live workload is the low-risk launch class;
- launch validation correctly remains `full-observe` because no valid cheap
  causal postcondition is currently wired for that class;
- no live bounded sequence has been accepted or executed;
- confidence and minimum-evidence thresholds remain intentionally unset.

Enabling Phase C from these data would therefore invent live-control thresholds
that the frozen design explicitly deferred to a later acceptance decision.
The safe final state for this Phase B task is telemetry/experience/shadow ON,
adaptive live OFF, sequence live OFF, with no remaining Phase B evidence gap or
physical blocker.
