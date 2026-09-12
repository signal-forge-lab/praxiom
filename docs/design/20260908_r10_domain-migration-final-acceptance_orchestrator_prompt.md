# DSH Orchestrator Prompt — Praxiom R10 Domain Migration & Final Acceptance

Date: 2026-09-08

Use the installed formal `@dsh-external/workflow` **Plan-and-Run** path. This document is Goal/acceptance guidance only; do not treat it as WorkflowCapsule source.

## Authoritative input order

1. current repository state / Git history / current tests / guards;
2. `docs/design/20260908_r10_domain-migration-final-acceptance_orchestrator_handoff.md`;
3. `docs/design/20260907_r8plus_execution_plan.md`;
4. `docs/evidence/20260907_adaptive-skill-platform-certification-packet.md`;
5. `docs/evidence/20260907_r8-r9-design-freeze.md`;
6. R6/R7 current-head certification and R4/R5/R3 retained evidence;
7. historical/legacy domain evidence discovered during the current-state audit.

Current repository evidence overrides stale prose.

## Goal

Complete **R10 Domain Migration & Final Acceptance (35/35)** without weakening the certified R3–R9 safety/authority floor.

The Goal must establish a minimal domain adapter seam, migrate the accepted Merge Boss and GoGoMatch behaviors through that seam, prove compatibility/provenance and domain isolation, run deterministic plus safely bounded real-workflow evidence, preserve full regression/performance/safety gates, retain R10 acceptance evidence, and then allow runtime-owned Goal Certification to decide final program acceptance.

## Mandatory starting assumptions to verify, not blindly trust

- R8/R9 combined certification is 94/94 with clean final review/Goal Reviewer/Final Judge;
- deterministic suite was 306/306 at the prior Goal close;
- six Runtime public operations remain unchanged;
- no R10 or Visual implementation was present at that close;
- no duplicate active/durable R10 Run or completed R10 implementation now exists.

Do not redo completed R3–R9 work unless a current reproduced defect blocks R10.

## Required work

- fresh current-state/duplicate audit;
- retain an R10 design freeze before parallel production edits;
- implement the minimal shared domain adapter boundary;
- migrate accepted Merge Boss behavior with explicit provenance, revision/pre/post/risk/reversibility/human-gate semantics and deterministic tests;
- migrate accepted GoGoMatch behavior to the same acceptance bar;
- close compatibility/provenance/legacy-only exclusions and rollback;
- update generalized boundary/provenance tests only where a real regression class warrants it;
- run deterministic R10 acceptance and full R3–R9 regression;
- run bounded real workflows only after deterministic gates pass, through Agent -> Skill/Coordinator -> Runtime only, in a single device-mutation lane and within the safe envelope defined in the handoff;
- compare performance to retained R9-safe baselines; safety always wins over optimization;
- perform a domain-specific architecture/migration review and repair concrete findings;
- retain a complete 35/35 acceptance package and local commits;
- leave final Goal Reviewer / repair / re-review / Final Judge to the runtime-owned certification chain.

## Hard constraints

- no provider/model override in the Workflow;
- use Stable Routing; do not encode usage/quota/transport priorities in the Goal;
- do not create WorkflowCapsule source manually;
- do not create duplicate Goal Certification tasks in the Workflow body;
- no Phone Harness production/build/runtime dependency or fallback;
- no internal MCP device chain;
- no transport/WDA/CoreDevice/AppService/usbmux/pymobiledevice3 edge above Runtime;
- no new Runtime public op without independent evidence that R10 cannot be safely completed otherwise;
- no stale-revision mutation or blind replay after PARTIAL/UNKNOWN;
- domain names remain in domain-specific paths and do not become generic-core taxonomy/authority;
- no Visual V0–V3 work;
- no remote push;
- preserve existing user work and current dirty state if any; do not overwrite unrelated changes;
- do not fabricate device/app/live evidence.

## Planning intent

- current-state/inventory: **fast**, read-only;
- design freeze / authority / migration architecture / live-workflow safety / final domain review: **deep**;
- normal implementation, tests, evidence, compatibility repairs: **balanced**;
- Merge Boss and GoGoMatch lanes may be parallel only after the shared seam is frozen and write ownership is disjoint;
- live device mutation is sequential/single-owner;
- reviews occur only after the reviewed implementation is complete enough to judge.

These are quality intents only. Provider/model/transport selection belongs to Stable Routing/runtime.

## Completion criteria

Do not report 100% merely because the body run terminates. Require all conditions in the R10 handoff, including:

- R10 35/35;
- terminal durable Run successful;
- outcome completed;
- required deterministic/full-suite/guard/performance verification green;
- bounded real-workflow evidence accepted;
- no major failed/completed-unverified tasks;
- retained acceptance/certification artifact;
- runtime-owned Independent Reviewer approved;
- Final Judge pass;
- unresolved=[];
- major errors=[];
- local final commit and clean working tree;
- no remote push.

If required safe live evidence cannot be obtained because of an external blocker, return the blocker precisely and do not claim 100%.

Sensitivity: **public**.

