# Orchestrator Prompt — Praxiom Read-only Monitor Slice v1

Initial prompt: 2026-09-10
Reviewed revision: 2026-09-11
Status: **READY / REVIEWED**

Use the current Praxiom checkout as authority. Read
`docs/design/PRAXIOM_MONITOR_PORT_DESIGN_20260910.md` before implementation.

## Goal

Implement and certify the complete **Read-only Praxiom Monitor Slice v1**:

```text
existing Runtime/RunSession/RunJournal
        +
optional passive latest-frame mirror
        ↓
MonitorSnapshotBuilder
        ↓
GET-only local HTTP
        ↓
Graphite/Slate Praxiom Monitor UI
```

Completion means implementation, deterministic tests, integration verification,
full regression/guards, final independent-style review, required repairs, and a
clean local Git state. Do not remote-push.

## Mandatory preflight

1. Confirm branch/HEAD and `git status --short`.
2. Read repository instructions and current `docs/STATUS.md`.
3. Verify current Runtime still exposes exactly six public operations.
4. Inspect current `ObservationEngine`, `NativeIosRuntime`, `RunSession`,
   `RunJournal`, Phase B telemetry, and MCP construction.
5. Confirm no existing Praxiom Monitor implementation already satisfies the
   Goal; reuse canonical helpers rather than duplicate them.
6. Preserve unrelated dirty changes if any; never reset/clean/stash them away.

Current repository evidence overrides this prose if they conflict. Stop and
report a concrete architectural conflict rather than silently weakening safety.

## Hard architecture rules

### A. Monitor refresh is never a Runtime observation

The Monitor must not call:

```text
NativeIosRuntime.observe
NativeIosRuntime.execute
NativeIosRuntime.recover
NativeIosRuntime.invalidate
praxiom_observe MCP
```

for Monitor refresh. `observe()` rotates the current revision; a Monitor doing
that would violate execution safety.

Add a regression that proves repeated snapshot refresh keeps the pre-existing
revision unchanged and performs no extra screenshot/device calls.

### B. Passive frame only

Add the narrowest generic internal seam needed for execution code to mirror the
PNG it **already captured**. Requirements:

- no extra device call;
- Runtime public operation surface unchanged;
- sink failure cannot affect observe success or effect semantics;
- core Runtime does not import Monitor;
- persistence is explicit opt-in;
- retain latest frame only, not history;
- fingerprint revision metadata;
- no Visual Flight Recorder implementation.

### C. Reuse existing evidence

Build activity/diagnostics from current RunJournal/telemetry. Do not create a
second telemetry database, second run state machine, or Monitor-specific
learning model.

### D. Human Channel honesty

Praxiom does not yet have an authoritative Phone Harness-style Questions /
Teaching conversation store. Slice v1 must show this truthfully as
`NOT_PROJECTED`; it must not invent a writable conversation model.

Monitor production code must not import or hold:

```text
HumanApprovalAuthority
HumanApprovalEvidence
HumanGateApproval
SkillTrustToken
```

### E. Dependency direction

`ios_runtime`, agent, skill, and domain packages must not depend on Monitor.
The only generic Runtime seam is an optional frame callback supplied by an
outer composition root.

MCP is not the Monitor's internal transport.

### F. Phone Harness separation

Phone Harness is visual/reference evidence only. Do not import/call/copy
Phone Harness production code.

Do **not** treat Praxiom's own `mergeboss` or `gogomatch` domain names as a
Phone Harness leak.

## HTTP/security requirements

- standard library / existing dependencies only; do not add a web dependency
  merely for this small read-only server;
- default `127.0.0.1:17680`;
- GET/HEAD routes only;
- no control/upload/filesystem/shell/approval routes;
- POST/PUT/PATCH/DELETE => 405;
- non-loopback bind fails unless operator explicitly passes `--allow-lan`;
- do not mutate Windows Firewall;
- bounded JSON output;
- no arbitrary exception details in responses;
- CSP + nosniff + frame deny + no-referrer + no-store;
- dynamic UI data rendered with text nodes, not HTML injection.

## UI requirements

Independently implement the reviewed Graphite/Slate design. Do not copy Phone
Harness source.

Use the palette and component rules in the design document. Layout:

```text
Current Screen | AI State | Human Channel
-----------------------------------------
Activity & Diagnostics
```

At narrow widths stack vertically. English section names, Japanese explanatory
prose. Desktop/tablet action controls 30px; narrow/mobile touch targets at least
44px. Focus must never resize controls. Fit/Height must not upscale the frame.

No Dockview dependency is needed for Slice v1.

## TDD / verification workflow

1. Write failing Monitor tests first.
2. Confirm RED for missing behavior.
3. Implement minimum code.
4. Run focused Monitor + Runtime/Observation/Phase B tests.
5. Verify static JS syntax and packaged static resources.
6. Start a local ephemeral Monitor and verify `/healthz`, `/api/snapshot`,
   `/api/frame`, static UI, GET-only contract, and security headers.
7. Run the full deterministic suite once after final code changes.
8. Run provenance/agent-boundary guards and compile/diff checks.
9. Review the final diff on five axes: correctness, readability/simplicity,
   architecture, security/privacy, performance.
10. Repair every blocking/required finding and rerun only affected checks plus
    final full suite if code changed.

## Required acceptance evidence

Report at minimum:

```text
Monitor-focused tests
Runtime/Observation regression
Phase B regression
full pytest count
six-operation Runtime guard
provenance guard
agent-boundary guard
JS syntax / static resource check
HTTP live smoke
git diff --check
git status
final review verdict + unresolved findings
```

Do not fabricate physical-device evidence. Real-device interaction is not
required to certify this passive Monitor slice; the deterministic contract is
that the Monitor cannot itself create device work.

## Completion definition

100% only when:

- reviewed design is reflected in source;
- all implementation is present;
- all deterministic tests/guards pass;
- live local HTTP smoke passes;
- no Monitor refresh rotates a revision;
- no Phone Harness production dependency exists;
- final review is APPROVED with no unresolved required findings;
- local worktree is clean after local commit(s);
- nothing was pushed remotely.
