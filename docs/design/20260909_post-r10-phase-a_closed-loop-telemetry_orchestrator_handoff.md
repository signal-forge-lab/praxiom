# Praxiom Post-R10 Phase A — Closed Loop & Durable Telemetry Orchestrator Handoff

Date: 2026-09-09

Status: **IMPLEMENTATION READY — D1-D5 frozen to Option A on 2026-09-09**

Sensitivity: **PUBLIC**

This handoff is self-contained for the formal DSH External Workflow Plan-and-Run path. Current repository state and retained evidence override stale prose.

## 1. Goal

Implement the **post-R10 Phase A Closed Loop & Durable Telemetry Foundation** before broad real-device learning trials.

Phase A must turn the already-certified Runtime / Safe Agent / Skill / Adaptive components into an observable, persistent, testable pipeline that can later learn from repeated real-device execution and reduce unnecessary work without weakening revision, lifecycle, effect, human-gate, or no-blind-replay guarantees.

The target is:

```text
Domain / ActiveSkill
       |
       v
SkillExecutor -> Coordinator -> Native iOS Runtime
       |              |                |
       |              |                +--> privacy-safe Runtime Trace
       |              +--> durable safety Attempt ledger
       |
       +-------------------------------> Run telemetry journal
                                          |
                                          +--> Experience projection
                                          +--> learning evidence
                                          +--> adaptive shadow recommendation
                                          +--> next-run derived learning snapshot
                                          +--> future Visual V0-V3 timeline/artifact refs
```

Phase A does **not** require a Phone Harness/Praxiom common schema or comparison dashboard. Existing Phone Harness JSONL/teaching/knowledge material is sufficient for rough historical comparison once Praxiom continuously retains equivalent high-level run evidence.

## 2. Mandatory design-decision gate

Read first:

`docs/design/20260909_post-r10-phase-a_closed-loop-telemetry_design-decisions.md`

All D1-D5 decisions are approved and frozen to Option A. Production implementation may proceed within that design envelope.

The Planner may inspect and improve the options, but must not silently select a materially different architecture. If repository evidence makes a recommended option unsafe or invalid, stop with the concrete conflict instead of inventing a new architecture in the implementation lane.

## 3. Current certified floor to preserve

Fresh-audit the current checkout before edits. Known retained floor at planning time:

- R3 Runtime 33/33;
- R4 real-device acceptance 20/20;
- R5 separation/provenance 7/7;
- R6 Agent Foundation 44/44;
- R7 Retrieval/Post-Action Safety 31/31;
- R8 Capability Discovery / Skill Foundry 47/47;
- R9 Adaptive Execution Performance 47/47;
- R10 Domain Migration & Final Acceptance 35/35 post-review certified;
- final retained post-review certification commit at planning time: `9fe2c9f` (reference only; fresh-audit actual HEAD);
- Runtime public surface exactly six operations;
- no Phone Harness production/build/runtime dependency or fallback;
- no remote push.

Do not reopen certified R3-R10 design unless a reproduced Phase A blocker requires a minimal compatible extension.

## 4. Phase A scope

### A0 — current-state audit and Phase A design freeze

Before parallel edits:

- inspect current Git status/history;
- verify deterministic suite and guards;
- inspect Coordinator ledger semantics, Runtime Trace, SkillExecutor/SkillRegistry, ExperienceEpisode, adaptive telemetry/learning/observation/routing/batching/fallback;
- verify the exact live-domain integration points;
- verify no existing general closed-loop/run-journal implementation already solves this Goal;
- retain a dated Phase A design freeze resolving D1-D4 and file ownership.

### A1 — RunContext + durable telemetry journal

Create the minimum run-scoped observational infrastructure.

If D1=A, recommended layout:

```text
<state-root>/runs/<run_id>/
  events.jsonl
  summary.json
  learning_snapshot.json
  coordinator-ledger.db       # if Coordinator durability is enabled for the run
  artifacts/                  # reserved/future Visual data
```

State root must be configurable and outside the repository by default. Tests use temporary directories.

Minimum event envelope:

```text
schema_version
run_id
event_id
seq
ts_utc
monotonic_ns
event_type
phase
parent_event_id / correlation_id
execution_id
attempt_id
domain
behavior_id
skill_id
skill_version
revision_ref              # opaque/fingerprinted, no raw sensitive payload
status
outcome/effect
duration_ms
policy_recommendation
actual_policy
fallback_reason
visual_hint
artifact_refs             # identifiers/metadata only
payload                    # bounded, allowlisted machine fields
```

Not every event must populate every optional field.

Properties:

- deterministic serialization;
- append-only sequence order;
- bounded payload sizes;
- fail-safe privacy allowlist;
- journal errors cannot create false success or silently grant authority;
- no screenshots/raw UI text/bundle ids/device identifiers in the core journal;
- clean close/final summary;
- crash-tolerant partial journal remains inspectable.

### A2 — wire existing safety ledger and Runtime/Coordinator/Skill telemetry

Do not duplicate lifecycle authority.

- preserve Coordinator attempt ledger as the durable safety/restart record;
- ensure normal real-device run construction supplies a run-scoped `ledger_path` instead of leaving it disabled;
- emit observational journal events for observe/execute/attempt/validation/recovery/fallback/policy/learning boundaries;
- expose Runtime trace records to the run summary without changing Runtime public operations;
- correlate Runtime trace -> execution -> attempt -> domain behavior with ids/timestamps rather than raw payload capture.

### A3 — execution -> Experience -> learning evidence bridge

Create production wiring so successful/failed attempts generate bounded learning evidence automatically.

Requirements:

- Experience records include enough identity to distinguish skill id/version and behavior/path/macro provenance;
- PARTIAL/UNKNOWN/stale/validator failure are retained, never filtered into success;
- historical persisted evidence never contains a live `SkillTrustToken` authority;
- at the start of a later run, the current matching skill/version must be independently revalidated/activated before historical evidence can be rebound to a fresh live trust token for macro/path scoring;
- incompatible skill version or provenance mismatch fails closed to non-reusable history;
- derived macro/path/performance summaries are caches/projections, not mutation authority.

### A4 — adaptive shadow mode

Wire existing R9 logic to real execution context in shadow mode first.

For each eligible decision, retain:

```text
actual decision
shadow recommendation
reason
confidence/evidence
cost/budget inputs
whether recommendation would reduce observe/action count
fallback reason if shadow optimization was refused
```

Shadow at least:

- ObservationPolicy: full-observe vs cheap-validate;
- `decide_batch`: recommended bounded sequence size;
- `route_latency_aware`: careful/standard/fast-path;
- macro/path reuse eligibility;
- failure/loop strategy adaptation;
- selector/recovery statistics where applicable.

No shadow recommendation may itself mutate the device.

### A5 — true bounded multi-action sequence path

Address the one-action/one-full-observe concern without weakening safety.

If D3=A, add a new explicit internal path rather than redefining certified `run_batch()`.

Acceptance semantics:

- sequence has one accepted starting revision;
- all specs/actions preflight before first effect;
- one lease;
- one Runtime `execute([...], expected_revision=R)` call;
- Runtime ActionExecutor remains responsible for action-level ordered outcomes;
- low-risk/reversible/non-human-gated only;
- state-sensitive or uncertain sequence => size 1;
- PARTIAL/UNKNOWN/STALE => stop, revision invalid, no continuation/no replay;
- sequence outcome produces one parent execution plus correlated per-action evidence;
- action count and duration are retained so later real-device data can decide useful batch thresholds;
- initially feature-gated according to D2/baseline rules.

Do not allow the adaptive layer to call Runtime directly.

### A6 — transport-neutral discovery + Wi-Fi Runtime transport readiness

Repair both the current Wi-Fi discovery false-negative and the Wi-Fi-only Runtime connection blocker before the next physical baseline.

Current local evidence showed:

- `usbmux list`: zero devices;
- pymobiledevice3 Remote Pairing browse: one paired iPhone visible over Wi-Fi (IPv4/IPv6 endpoints deduplicate to one device identity).
- a userspace RSD connection probe still failed because the current Praxiom transport requires usbmux selection before tunnel creation.
- historical Phone Harness avoided that limitation by using external `pymobiledevice3 tunneld`; this is reference evidence only and must not be reintroduced silently.

Implement a library-level discovery seam that:

- sees USB and Wi-Fi/RSD transports;
- deduplicates endpoints representing the same device;
- can require exactly one selected target for live mutation;
- does not log raw UDID/IP in public telemetry/evidence;
- distinguishes `no-device`, `ambiguous-multiple-devices`, `paired-wifi-visible`, and `runtime-tunnel-unavailable` blockers;
- remains read-only during probe/discovery;
- feeds the existing `PreferredRsdTunnel` runtime path rather than adding a second device authority.

A subprocess CLI parser is not the preferred production design; use pymobiledevice3 library APIs where practical.

Then implement the resolved D5 transport strategy. If D5=A, keep Wi-Fi tunnel/provider selection inside `ios_runtime` so the Runtime remains the single transport/mutation owner. The Wi-Fi path must converge on the same existing RSD/WDA/AppService primitives and lifecycle semantics as USB; it must not create a parallel higher-level execution route.

### A7 — future Visual Flight Recorder V0-V3 compatibility hooks

Do not implement video capture in Phase A unless D4 explicitly selects it.

Phase A must make later Visual work additive:

```text
Run journal monotonic timeline
      |
      +-- action.sent / action.completed markers
      +-- observe / validation / recovery markers
      +-- learning/policy-change markers
      +-- optional visual_hint
                 |
                 v
       Visual V0 rolling recorder   # future, read-only
                 |
       V1 timeline correlation
                 |
       V2 frame-diff / auto-clip
                 |
       V3 AI retrieval of clip or selected frames
```

Future behavior envisioned by the user:

- normal rolling video primarily for logging;
- after an operation, retain a short lightweight clip or selected captures when useful;
- when animation/frame difference is large, retain a compact clip or small frame set;
- AI may receive those selected visual artifacts for analysis;
- Visual failure must not grant or widen mutation authority;
- visual artifact ids correlate through event ids/monotonic time, not through hidden Runtime calls.

Reserve artifact metadata only. Do not store image/video bytes inside JSONL.

### A8 — reporting for rough improvement judgment

No common legacy schema is required.

Provide a small run summary/export sufficient to answer manually:

- total goal/run duration;
- observe count and total/median/p90 observe time;
- execute count and total/median/p90 execute time;
- action count;
- full-observe vs cheap-validation count;
- shadow recommended batch sizes;
- actual sequence sizes;
- recovery attempts/successes;
- failures by class/effect;
- macro/path candidates and reuse recommendations;
- fallback reasons;
- learned/adaptive recommendations that changed across runs.

This is enough to compare roughly with historical Phone Harness JSONL without building a cross-system analytics product.

## 5. Test-first requirements

Use deterministic fakes and temporary state directories before any real-device run.

Minimum test categories:

1. journal ordering/schema/privacy/crash tolerance;
2. Coordinator ledger still recovers planned/sent work as UNKNOWN after restart;
3. Runtime public surface remains six ops;
4. attempt/trace/event correlation;
5. Experience extraction from NONE/PARTIAL/UNKNOWN/stale outcomes;
6. persisted history cannot forge/replay SkillTrustToken authority;
7. version/provenance mismatch blocks learning reuse;
8. shadow decisions never change actual execution;
9. true sequence performs exactly one Runtime execute call for N accepted actions;
10. whole-sequence preflight rejection makes zero device calls;
11. mid-sequence failure yields correct partial/unknown action evidence and no replay;
12. state-sensitive/high-risk/human-gated paths fall back to size 1;
13. Wi-Fi + USB discovery dedupes one device without retaining raw identifiers, and the resolved D5 transport can deterministically reach a fake/contract RSD path without usbmux;
14. Visual artifact refs/hints are metadata-only and cannot cause mutation;
15. full regression/provenance/boundary guards remain green.

## 6. Real-device boundary

Phase A implementation and deterministic certification can proceed without the iPhone.

Do not use physical evidence to invent thresholds during Phase A.

After Phase A, first live baseline should use:

```text
telemetry              ON
experience extraction  ON
learning projection    ON
shadow recommendations ON
adaptive live apply    OFF
sequence live apply    OFF unless separately accepted for baseline
```

Real-device data is required later to tune/accept:

- confidence thresholds;
- useful sequence sizes;
- cheap-validation eligibility by domain/state;
- latency budgets;
- minimum evidence/episode counts for live reuse;
- frame-diff/clip retention thresholds in Visual V2.

## 7. Parallel orchestration / ownership

After design freeze, safe parallel lanes may be:

- lane T: RunContext/journal/reporting;
- lane L: Experience/learning projection + shadow policy;
- lane S: true sequence execution + safety tests;
- lane D: transport-neutral device discovery;
- lane V: Visual compatibility metadata/tests only.

Do not parallel-edit shared Coordinator/Skill interfaces without explicit file ownership. One integration owner resolves shared seam changes.

No device mutation lanes are needed during Phase A deterministic implementation.

## 8. Hard constraints

- no Phone Harness production/build/runtime dependency or fallback;
- historical Phone Harness is reference/comparison evidence only;
- no internal MCP device chain;
- no direct WDA/CoreDevice/AppService/usbmux/pymobiledevice3 mutation authority above Runtime, except the bounded read-only discovery seam needed to select/connect the Runtime transport;
- preserve exactly six Runtime public operations;
- no stale-revision mutation;
- no blind replay after PARTIAL/UNKNOWN;
- no persisted trust-token authority;
- optimization never outranks lifecycle/revision/human-gate/effect safety;
- Visual V0-V3 remains read-only and independent of mutation authority;
- no remote push;
- do not fabricate physical/live evidence.

## 9. Completion criteria for Phase A deterministic implementation

Do not report 100% until:

- all D1-D5 decisions are resolved and retained in the design freeze;
- run-scoped durable telemetry is implemented and tested;
- Coordinator durable attempt ledger is enabled in the normal live-run construction path;
- production execution generates persisted Experience/learning evidence automatically;
- cross-run evidence rebinding cannot persist/forge SkillTrustToken authority;
- adaptive shadow mode is production-wired and observable;
- true bounded sequence path exists under the frozen safety conditions;
- Wi-Fi/USB discovery and Runtime transport support the current paired-Wi-Fi environment without raw identifier retention or a second mutation authority;
- Visual V0-V3 correlation hooks are additive/read-only;
- rough per-run summary is available;
- deterministic new tests pass;
- full existing suite, boundary/provenance checks, compile, diff-check pass;
- independent architecture/safety review completed and concrete findings repaired;
- local commit(s) retained;
- working tree clean;
- no remote push.

Physical learning/optimization effectiveness is **not** a Phase A completion requirement; it belongs to the subsequent real-device baseline/activation phase.
