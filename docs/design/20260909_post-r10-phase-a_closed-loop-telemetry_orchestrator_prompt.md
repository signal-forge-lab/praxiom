# DSH Orchestrator Prompt — Praxiom Post-R10 Phase A Closed Loop & Durable Telemetry

Date: 2026-09-09

Status: **READY — D1-D5 approved and frozen to Option A on 2026-09-09**

Use the installed formal `@dsh-external/workflow` **Plan-and-Run** path. This document is Goal/acceptance guidance only; do not hand-author WorkflowCapsule source.

## Authoritative input order

1. current repository / Git / tests / guards;
2. `docs/design/20260909_post-r10-phase-a_closed-loop-telemetry_design-decisions.md`;
3. `docs/design/20260909_post-r10-phase-a_closed-loop-telemetry_orchestrator_handoff.md`;
4. `docs/STATUS.md`;
5. `docs/design/20260907_r8plus_execution_plan.md` Visual V0-V3 section;
6. retained R8/R9/R10 design/evidence and current implementation;
7. Phone Harness only as historical/reference evidence, never a production dependency.

Current repository evidence overrides stale prose.

## Mandatory decision gate

Read D1-D5 from the design-decision file. They are frozen to Option A and are implementation authority for this Goal. If current repository evidence proves a frozen choice unsafe or impossible, stop and return the concrete conflict. **Do not silently replace a frozen choice with another architecture.**

## Goal after decisions are resolved

Complete deterministic implementation/certification of the post-R10 Phase A foundation:

- persistent run telemetry;
- production execution -> Experience/learning evidence bridge;
- next-run learning projection with no persisted trust-token authority;
- adaptive shadow recommendations;
- true bounded multi-action sequence path under existing safety authority;
- Wi-Fi/USB transport-neutral discovery plus the resolved Wi-Fi Runtime transport strategy for the already paired iPhone environment;
- future Visual Flight Recorder V0-V3 correlation/artifact hooks;
- rough per-run summaries sufficient for manual Phone Harness-vs-Praxiom and before/after judgment.

## Required work

- fresh current-state and duplicate audit;
- retain dated Phase A design freeze before parallel production edits;
- implement the resolved D1 telemetry architecture;
- wire normal live-run construction to the Coordinator durable ledger;
- instrument Runtime/Coordinator/Skill/domain boundaries without expanding Runtime public operations;
- automatically generate bounded Experience/learning evidence from execution outcomes;
- make cross-run learning revalidate current skill/version and issue fresh registry trust before reuse;
- wire ObservationPolicy/batching/latency routing/macro/path/fallback decisions in shadow mode according to D2;
- implement D3 sequence semantics with one Runtime execute call for accepted N-action sequences;
- repair USB-only preprobe/discovery so paired Wi-Fi devices are visible/deduped using library APIs;
- implement the resolved D5 Wi-Fi Runtime path so a Wi-Fi-only paired device can reach the existing RSD/WDA Runtime stack without creating a second mutation authority;
- implement D4 future Visual correlation metadata only unless the resolved decision explicitly says otherwise;
- provide a compact run summary/export;
- add deterministic tests first, then implementation;
- run full regression and guards;
- perform independent architecture/safety review, repair findings, re-review;
- retain local evidence/commits and leave the working tree clean.

## Hard constraints

- no provider/model override; Stable Routing owns routing;
- no duplicate active durable Goal/Run;
- no Phone Harness production/build/runtime dependency or fallback;
- no internal MCP device mutation chain;
- no direct transport/WDA/CoreDevice/AppService/usbmux/pymobiledevice3 mutation authority above Runtime;
- preserve exactly six Runtime public operations;
- telemetry/learning/Visual are never mutation authorities;
- no stale-revision mutation;
- no blind replay after PARTIAL/UNKNOWN;
- no persisted/replayed `SkillTrustToken` authority;
- optimization cannot outrank lifecycle/revision/effect/human-gate safety;
- do not redefine existing certified `run_batch()` semantics if D3 selects the recommended new sequence API;
- Visual V0-V3 capture implementation remains out of scope if D4=A;
- no raw device identifiers/IPs, bundle ids, raw UI text, screenshots or video bytes in the core telemetry journal;
- no remote push;
- do not fabricate physical evidence.

## Planning intent

- current-state, duplicate audit, discovery audit: fast/read-only;
- design freeze, trust rebinding, sequence semantics, journal/privacy, Visual future seam, final architecture review: deep;
- implementation/tests/reporting: balanced;
- parallelize only after file ownership is frozen;
- no physical device mutation is required for Phase A deterministic completion.

## Completion criteria

Use the handoff's Phase A completion criteria exactly. Phase A may reach 100% without proving real-world learning speedup, but only if all pre-device foundation work is fully implemented, reviewed, tested, committed, and clean.

The subsequent live phase must preserve an unoptimized/shadow-only baseline before enabling adaptive live control.

Sensitivity: **public**.
