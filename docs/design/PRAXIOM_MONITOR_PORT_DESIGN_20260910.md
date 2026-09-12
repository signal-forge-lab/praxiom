# Praxiom Monitor — Phone Harness Monitor Design Port

Initial design: 2026-09-10
Reviewed revision: 2026-09-11
Status: **IMPLEMENTATION AUTHORITY — reviewed**

## 1. Goal

Create a Praxiom-native Monitor that keeps the accepted Phone Harness Monitor
visual language while preserving Praxiom's own architecture and authority.

The first complete slice is deliberately **read-only and passive**:

```text
Existing Praxiom execution
├─ NativeIosRuntime
│  └─ privacy-safe Trace projection
├─ RunSession / RunJournal
│  └─ activity / policy / learning evidence
└─ already-captured screenshot
   └─ optional LatestFrame projection (one frame only)
              │
              ▼
      MonitorSnapshotBuilder
              │
              ▼
        read-only HTTP
              │
              ▼
        Praxiom Monitor UI
```

The Monitor is not a second observer, planner, executor, recovery path, human
approval authority, or persistence authority.

## 2. Authority order

1. Current Praxiom source, tests, and live guards.
2. This reviewed design.
3. Existing Praxiom design/evidence documents.
4. Phone Harness Monitor visual/UX behavior as historical design reference.

Phone Harness production source is never a Praxiom dependency or fallback.
Praxiom-owned domains such as `praxiom.domain.mergeboss` and
`praxiom.domain.gogomatch` are valid Praxiom concepts and are **not** Phone
Harness leakage.

## 3. Critical invariant: Monitor refresh must not observe

`NativeIosRuntime.observe()` creates a new opaque revision and supersedes the
previous current revision. Therefore a Monitor that calls `observe()` merely
to refresh the Current Screen can invalidate an execution plan.

The Monitor must never call any of these for refresh:

```text
runtime.observe()
runtime.execute()
runtime.recover()
runtime.invalidate()
MCP praxiom_observe
```

Required acceptance invariant:

```text
1. Runtime creates revision R through normal execution-side observe.
2. Monitor snapshot is refreshed repeatedly.
3. Runtime current_revision remains R.
4. screenshot / accessibility transport call counts do not increase.
5. No execute/recover/invalidate call is introduced.
```

## 4. Passive Current Screen seam

### 4.1 Execution-side publication

`ObservationEngine` accepts an optional synchronous frame sink. After a normal
successful observation has already produced its revision and immutable
`Observation`, the already-captured PNG may be mirrored to the sink.

Properties:

- no extra device call;
- no extra observation;
- no revision rotation;
- sink failure never changes Runtime success/effect semantics;
- sink is opt-in, not enabled by Monitor process startup;
- Runtime public operation surface remains exactly six operations.

### 4.2 Cross-process store

The first slice uses:

```text
<PRAXIOM_STATE_ROOT or ~/.praxiom>/monitor/
  latest-frame.png
  latest-frame.json
```

Only the latest frame is kept. Each publication replaces the existing pair.
This is **not** an Image Log, artifact archive, or Visual Flight Recorder.

Metadata is bounded and contains only:

- capture timestamp;
- width / height / format;
- fingerprinted revision reference;
- SHA-256 integrity digest;
- byte length.

The raw revision token is not retained.

### 4.3 Explicit opt-in

Screenshot persistence is sensitive. It is enabled only when the execution
process explicitly requests it.

Long-lived MCP Runtime:

```powershell
.\scripts\start_praxiom_mcp.ps1 -MonitorFrameProjection
```

Equivalent environment contract:

```text
PRAXIOM_MONITOR_FRAME_PROJECTION=1
```

Phase B workload:

```text
--monitor-frame-projection
```

Starting the Monitor UI alone never enables screenshot persistence.

## 5. Existing evidence reused by the Monitor

The Monitor must aggregate existing state rather than create a duplicate state
model.

### 5.1 RunJournal

Use the existing per-run JSONL journal for:

- run start/completion;
- Runtime operation events;
- attempt/execution events;
- policy decisions;
- sequence decisions;
- learning records;
- recovery/fallback diagnostics.

The Monitor exposes only a bounded recent window and projects an allowlisted
machine-readable subset. It does not become journal authority and does not
repair or rewrite journals.

### 5.2 Runtime Trace

Runtime Trace remains owned by Runtime/RunSession. The Monitor consumes its
durable RunJournal projection instead of importing device internals or adding
another trace drain path.

### 5.3 Phase B evidence

Current adaptive/shadow telemetry is valid Monitor input. Shadow suggestions
are displayed as advisory evidence only and never become control authority.

## 6. Human Channel scope

Praxiom already has Human Gate / HumanApprovalAuthority and Teaching-related
agent concepts, but it does **not** yet have a Phone Harness-equivalent
Questions/Teaching conversation store.

Therefore Slice v1 renders Human Channel as a truthful read-only state:

```text
state = NOT_PROJECTED
reason = authoritative-human-channel-not-implemented
```

The Monitor must not:

- invent pending human questions;
- mint or hold `HumanApprovalEvidence` / `HumanGateApproval`;
- hold `SkillTrustToken`;
- provide approval/Teaching write endpoints;
- import `HumanApprovalAuthority` into Monitor code.

Future Human Channel work is a separate slice with its own authoritative data
model and safety review.

## 7. Image Viewer / Image Log scope

Slice v1 supports **Current Screen viewing only**.

The UI may offer Fit / Height / 100% display modes, all based on the one
passively published latest frame. Height/Fit may shrink but must not upscale
beyond the image's intrinsic size.

Historical Image Log is intentionally out of this slice. It must later consume
an accepted artifact/history source (for example the Visual Flight Recorder)
rather than creating a second screenshot-retention system just for Monitor.

## 8. HTTP seam and dependency direction

The Monitor HTTP implementation lives in `praxiom.monitor` and depends on
Praxiom projections. Dependency direction is one-way:

```text
ios_runtime / agent / skill / domain
          X  (must not import monitor)

monitor
  -> telemetry read model
  -> passive frame files
```

The one allowed core seam is the generic optional `frame_sink` callback passed
at Runtime construction. `ios_runtime` does not import `praxiom.monitor`.

MCP is **not** an internal Monitor transport. The external MCP process may opt
in to publishing its already-observed frames, but the Monitor does not call
MCP tools.

## 9. HTTP security contract

Default:

```text
host = 127.0.0.1
port = 17680
methods = GET / HEAD only
```

Routes:

```text
GET /                 static Monitor UI
GET /monitor.css      static stylesheet
GET /monitor.js       static script
GET /healthz          health only
GET /api/snapshot     bounded passive snapshot
GET /api/frame        latest optional PNG
```

There are no Runtime-control, filesystem, upload, Teaching, approval, or shell
routes. POST/PUT/PATCH/DELETE return 405.

Non-loopback binding is rejected unless `--allow-lan` is explicitly supplied.
The server does not alter Windows Firewall rules. LAN exposure therefore
requires a separate operator decision and network policy.

Responses set no-store, CSP, frame denial, nosniff, and no-referrer headers.
UI JavaScript renders journal values via `textContent`, never dynamic HTML.

## 10. UI design contract

The visual direction is the accepted Phone Harness Monitor Graphite / Slate
design, independently implemented in Praxiom.

### 10.1 Palette

```text
App background       #111418
Surface 1            #171B20
Surface 2            #1D2228
Surface 3            #242A31
Hover                #2A3139
Border subtle        #2B323A
Border strong        #3A434D
Primary text         #E7E9EC
Secondary text       #A9B0B8
Muted text           #747E89
Accent               #6EA8D7
Accent hover/focus   #82B7DF
Accent selected      #203342
Success              #68C99A
Warning              #D8AD63
Error                #DF7D85
Info                 #74A9D0
```

Color communicates state/selection, not panel identity.

### 10.2 Layout

Desktop / landscape tablet:

```text
Current Screen | AI State | Human Channel
-----------------------------------------
Activity & Diagnostics
```

Phone/narrow viewport:

```text
Current Screen
AI State
Human Channel
Activity & Diagnostics
```

### 10.3 Controls

- action buttons: compact 30px desktop/tablet;
- phone touch targets: minimum 44px;
- status chips: compact, non-button appearance;
- fixed-size focus rings must not change geometry;
- headings are English, explanatory prose is Japanese;
- Activity on tablet is height-bounded and internally scrollable;
- no dependency/library skin is accepted as product styling.

Dockview is not required for the minimal read-only slice. Adding advanced
docking later is a separate feature, not a prerequisite for Monitor v1.

## 11. Snapshot shape

The Monitor snapshot is derived and non-authoritative:

```text
generated_at
mode = read-only-passive
run
frame
runtime
ai_state
human_channel
diagnostics
activity[]
```

RunJournal records are filtered through a bounded allowlist before HTTP
rendering. Raw action payloads, device identifiers, trust tokens, screen text,
and arbitrary payload dictionaries are not part of the interface.

## 12. Test / acceptance matrix

Required deterministic checks:

1. Monitor refresh does not change Runtime revision.
2. Monitor refresh adds zero screenshot/device calls.
3. Frame sink failure cannot fail Runtime observe.
4. LatestFrameStore retains one frame pair only.
5. Persisted revision is fingerprinted, never raw.
6. Snapshot reuses existing RunJournal and does not invent Human state.
7. HTTP server serves snapshot/frame through GET.
8. Mutating HTTP methods return 405.
9. Non-loopback bind requires explicit opt-in.
10. Runtime public operations remain exactly six.
11. Existing Runtime/Observation/Phase B regression stays green.
12. Full deterministic Praxiom suite stays green.
13. Provenance/boundary guards stay green.
14. Static JS syntax and package resources are valid.
15. Final review checks correctness, simplicity, architecture, security,
    performance, and documentation alignment.

## 13. Explicit non-goals for Slice v1

- no Runtime mutation controls;
- no pause/restart/device actions;
- no Questions/Teaching write workflow;
- no human approval UI;
- no Image Log/history;
- no video capture or Visual Flight Recorder implementation;
- no Dockview/float/pin/layout persistence requirement;
- no desktop shell/Tauri/Electron requirement;
- no internal MCP hop;
- no automatic LAN/firewall exposure;
- no Phone Harness source dependency or copied implementation.

These are future slices only when separately requested and designed.
