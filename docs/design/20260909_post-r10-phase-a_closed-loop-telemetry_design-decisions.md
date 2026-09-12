# Praxiom Post-R10 Phase A — Closed Loop / Durable Telemetry Design Decisions

Date: 2026-09-09

Status: **FROZEN — D1-D5 approved as Option A on 2026-09-09**

Sensitivity: **PUBLIC**

## 1. Purpose

Freeze the minimum design decisions required before implementing the post-R10 Phase A foundation for:

- durable run telemetry;
- execution -> experience -> learning input;
- next-run adaptive improvement;
- adaptive shadow evaluation before live activation;
- bounded multi-action execution that avoids unnecessary one-action/one-full-observe behavior;
- transport-neutral real-device discovery, including existing Wi-Fi pairing;
- future Visual Flight Recorder V0-V3 correlation without granting visual tooling device-mutation authority.

The user only needs rough legacy-vs-current comparison. A common Phone Harness/Praxiom schema, comparison dashboard, or strict historical ETL is explicitly not required in Phase A.

## 2. Current facts that constrain the design

- Native iOS Runtime public operations remain exactly: `status`, `observe`, `execute`, `invalidate`, `recover`, `close`.
- `NativeIosRuntime.execute(actions, expected_revision=...)` already supports whole-batch preflight and ordered execution of multiple actions under one accepted revision.
- `SkillExecutor.execute()` currently emits one `ExecutionSpec` and calls `ExecutionCoordinator.run()` for one mutation.
- `adaptive.decide_batch()` exists, but the production Skill/domain path does not currently consume it.
- `ExecutionCoordinator.run_batch()` is not a true single-Runtime-call batch: it loops and invokes the Runtime port once per spec, so it must not be treated as the answer to the one-step/one-observe concern.
- `ExecutionCoordinator` already has an optional durable SQLite attempt ledger, but the R10 live domain lane does not pass `ledger_path`; the durable safety ledger is therefore not a general run telemetry solution today.
- Runtime `Trace` is privacy-safe and machine-readable, but process-local/in-memory.
- `TelemetryEvent`, `PerformanceBaseline`, macro/path learning, `ObservationPolicy`, fallback, selector/recovery stats, and latency-aware routing exist and are deterministically tested, but are not wired into a persistent online learning loop.
- `ExperienceEpisode` is serializable, but production execution does not currently generate and persist episodes automatically.
- `SkillTrustToken` is an in-process registry trust token and must never be persisted and replayed as authority across restarts.
- A read-only 2026-09-09 local probe found **no usbmux device** but did find the already paired iPhone over Bonjour/Remote Pairing Wi-Fi.
- A direct userspace RSD probe then failed with `Device is not connected`. Inspection shows the current `IosTransport._connect_locked()` requires `usbmux.select_device()` before tunnel creation, and pinned upstream `UserspaceRsdTunnel` also tries usbmux first before its RemotePairing fallback. Therefore discovery is healthy but the current Praxiom Wi-Fi-only Runtime path is not.
- Historical Phone Harness handled Wi-Fi differently: it used `pymobiledevice3 tunneld` and consumed the returned RSD endpoint. That path is reference evidence only, not an automatic choice for Praxiom.
- Visual Flight Recorder V0-V3 remains a separate read-only track: V0 rolling recorder, V1 action/trace/revision timeline correlation, V2 frame-diff/animation auto-clip, V3 AI visual-evidence retrieval.

## 3. Decision D1 — durable telemetry storage

Status: **APPROVED — Option A**

### Option A — separate append-only per-run JSONL journal — RECOMMENDED

Keep the existing Coordinator SQLite ledger as safety/restart authority. Add a separate observational run journal, for example:

```text
~/.praxiom/runs/<run_id>/
  events.jsonl
  summary.json               # derived/cache, not authority
  learning_snapshot.json     # derived/cache, not authority
  artifacts/                 # future Visual V0-V3 files/manifests
```

Properties:

- append-only, schema-versioned, sequence-numbered;
- easy to inspect manually and compare roughly with Phone Harness JSONL;
- low coupling to Coordinator lifecycle semantics;
- future Visual artifact layout maps naturally to one run directory;
- journal failure must not invent success or gain mutation authority;
- authoritative safety state remains Runtime/Coordinator/Skill lifecycle, never the journal.

Tradeoff: cross-run queries require scanning run journals or a derived index later.

### Option B — extend Coordinator SQLite ledger with generic telemetry/events

Pros: one durable database, transactional queries.

Cons: observation/learning/Visual concerns become coupled to Coordinator's safety ledger; higher migration risk; non-Coordinator events need access to Coordinator persistence.

### Option C — new dedicated SQLite RunStore

Pros: queryable and decoupled from Coordinator ledger.

Cons: more infrastructure than Phase A needs, and rough comparison does not currently justify it.

**Decision: D1=A. Approved by user on 2026-09-09.**

## 4. Decision D2 — when learned/adaptive decisions may affect live control

Status: **APPROVED — Option A**

### Option A — shadow-first, feature-gated activation — RECOMMENDED

Implement the complete data path now, but default to:

```text
actual route      = current certified safe behavior
shadow suggestion = learned/adaptive recommendation
```

Persist both recommendation and actual choice. After a real-device baseline exists, enable application only for explicitly accepted low-risk classes.

This permits Phase A to complete the closed-loop plumbing without contaminating the pre-learning baseline or making unmeasured optimization authoritative.

### Option B — immediately apply low-risk learned decisions

Faster feedback, but the first real-device run is no longer a clean baseline and bad thresholds are harder to diagnose.

**Decision: D2=A. Approved by user on 2026-09-09.**

## 5. Decision D3 — true bounded multi-action execution API

Status: **APPROVED — Option A**

### Option A — add an explicit new internal sequence path — RECOMMENDED

Add a distinct internal path such as:

```text
SkillExecutor.execute_sequence(...)
  -> ExecutionCoordinator.run_sequence(...)
  -> RuntimePort.execute([payload1, payload2, ...], expected_revision=R)
  -> NativeIosRuntime.execute([Action1, Action2, ...], expected_revision=R)
```

Requirements:

- entire sequence preflight before first effect;
- all steps bound to the same accepted revision;
- one device lease for the sequence;
- one Runtime execute call;
- Runtime remains the sole mutation authority;
- partial/unknown effect stops immediately and never blind-replays;
- low-risk + reversible + non-human-gated only;
- state-sensitive sequences fall back to size 1 unless a later evidence contract explicitly proves otherwise;
- existing `run_batch()` semantics stay unchanged to avoid silently redefining certified behavior.

### Option B — redefine existing `ExecutionCoordinator.run_batch()` as the true Runtime batch

Smaller API surface, but changes certified semantics and creates larger regression/blast-radius risk.

**Decision: D3=A. Approved by user on 2026-09-09.**

## 6. Decision D4 — Visual Flight Recorder future integration surface

Status: **APPROVED — Option A**

### Option A — correlation/artifact hooks only in Phase A — RECOMMENDED

Phase A emits stable timeline/correlation data and optional capture hints, but does not implement video capture.

Required future-ready fields include:

- `run_id`, `event_id`, `seq`;
- UTC timestamp + monotonic timestamp;
- `parent_event_id` / correlation id;
- `execution_id`, `attempt_id`;
- domain/behavior/skill identifiers;
- opaque revision reference/fingerprint;
- action/validation/recovery phase;
- `visual_hint` such as `post-action`, `validation-mismatch`, `recovery`, `learning-change`;
- future `artifact_refs` containing identifiers/metadata only, not mutation authority.

V0/V1 can later subscribe read-only to the timeline. V2 can use a rolling frame buffer and event markers to retain a short clip or a small frame set when post-action/frame-diff activity is large. V3 can retrieve those visual artifacts for AI inspection.

### Option B — define a Visual-specific schema in Phase A

More premature coupling; details should be frozen in Visual V0/V1 when actual capture mechanics exist.

### Option C — implement Visual V0 now

Out of Phase A scope and would mix two independently gated tracks.

**Decision: D4=A. Approved by user on 2026-09-09.**

## 7. Decision D5 — Wi-Fi Runtime transport strategy

Status: **APPROVED — Option A**

The paired iPhone is currently discoverable over Remote Pairing Wi-Fi, but the certified Praxiom Runtime transport is usbmux-gated before it opens RSD. A real transport choice is therefore required; fixing only the preprobe would leave live Wi-Fi execution broken.

### Option A — add an in-process Wi-Fi RemotePairing provider inside `ios_runtime` — RECOMMENDED

Keep one Runtime-owned transport stack and select inside `IosTransport`:

```text
USB visible
  -> current usbmux + PreferredRsdTunnel path

USB absent, one paired Wi-Fi target visible
  -> upstream RemotePairing service/provider
  -> in-process userspace RSD tunnel
  -> existing WDA/AppService Runtime path
```

Properties:

- preserves the R3 goal of no persistent external tunneld service;
- Wi-Fi selection/tunnel creation remains below the Runtime boundary;
- no second mutation authority;
- can use the already pinned upstream RemotePairing APIs and keep raw identifiers private;
- requires a small Runtime transport adapter because the pinned upstream `PreferredRsdTunnel` does not currently reach its RemotePairing fallback when no usbmux device exists.

Tradeoff: more local transport code and upstream-internal compatibility surface than the existing USB path.

### Option B — restore an external `pymobiledevice3 tunneld` Wi-Fi fallback

This is the historical Phone Harness approach and is operationally familiar.

Pros:

- known model for Wi-Fi on Windows;
- tunnel endpoint is explicit and can be supervised as a service.

Cons:

- reintroduces a persistent/elevated external daemon dependency that Praxiom R3 intentionally removed;
- adds operational lifecycle outside the Runtime process;
- needs careful ownership so tunneld remains transport infrastructure only, never a second mutation authority.

### Option C — fix/update upstream `PreferredRsdTunnel` and move the pinned dependency

Long-term cleanest if upstream accepts/contains the desired no-usbmux RemotePairing fallback.

Cons:

- widens Phase A into upstream dependency work/pin review;
- blocks local Phase A progress on external code/version decisions;
- still needs deterministic regression of the full Runtime transport contract.

**Decision: D5=A for Phase A. Approved by user on 2026-09-09. An upstream fix/PR may be considered separately later and is not a Phase A blocker.**

## 8. Non-optional design requirements

These are not open choices.

### 8.1 Transport-neutral device discovery

Before the next real-device baseline, replace USB-only preprobe logic with a library-level discovery seam that can enumerate/deduplicate:

- USB/RSD devices;
- Wi-Fi Remote Pairing devices.

The current environment has one Wi-Fi-paired device visible through pymobiledevice3 Remote Pairing even when `usbmux list` is empty. Discovery alone is not sufficient: the resolved D5 transport must also reach the existing Runtime RSD/WDA path. Do not persist raw UDIDs/IP addresses in public evidence. Device identity used internally for safe selection must be privacy-safe in retained logs.

### 8.2 Safety authority

Telemetry, learning, adaptive policy, and Visual tooling are advisory/read-only relative to mutation authority.

They must never bypass:

`Skill lifecycle / human gate -> Coordinator -> Runtime revision check -> Runtime execute`.

### 8.3 Cross-run learning cannot persist authority tokens

Persist evidence facts such as:

- skill id/version;
- behavior/path/macro id;
- outcome/effect;
- revision evidence reference;
- execution/attempt id;
- timestamps and counts.

On a later run, historical evidence may only become reusable after the current registry has independently activated the matching skill/version and issued a fresh live `SkillTrustToken`. Persisted token ids must never be treated as authority.

### 8.4 Baseline preservation

The first real-device runs after Phase A must run with:

- durable telemetry ON;
- learning extraction ON;
- shadow recommendations ON;
- adaptive live application OFF;
- bounded sequence live application OFF unless separately accepted before baseline.

This preserves a meaningful Praxiom pre-learning baseline.

## 9. User decision block

Resolve before implementation begins:

```text
D1 telemetry store: A — per-run append-only JSONL
D2 activation mode: A — shadow-first, feature-gated activation
D3 sequence API: A — explicit internal run_sequence/execute_sequence path
D4 Visual hook: A — correlation/artifact hooks only in Phase A
D5 Wi-Fi transport: A — in-process RemotePairing/userspace RSD path
```

The design gate is now satisfied. The orchestrator may start Phase A implementation only within these frozen choices. If current repository evidence proves one of them unsafe or impossible, stop and return that concrete conflict rather than silently substituting another architecture.
