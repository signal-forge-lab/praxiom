# Praxiom R10 — Domain Migration & Final Acceptance Orchestrator Handoff

Date: 2026-09-08

Status: **implementation authority after certified R8/R9 Adaptive Skill Platform**

Sensitivity: **PUBLIC**

This handoff is self-contained for the formal DSH External Workflow Plan-and-Run path. The Planner must inspect the current repository, Git state, retained evidence, current tests/guards, and any existing durable R10 Run before editing. Current repository evidence overrides stale prose.

## 1. Goal

Implement and certify **R10 Domain Migration & Final Acceptance (35 points)** as an independent Goal after the certified R8/R9 Adaptive Skill Platform.

R10 is the final critical-path milestone in the current Praxiom roadmap. It must connect the generic Runtime / Safe Agent / Skill Platform to the intended domain behaviors without contaminating generic core authority or weakening revision, lifecycle, human-gate, provenance, privacy, or no-blind-replay guarantees.

Visual Flight Recorder V0–V3 is outside this Goal.

## 2. Mandatory current-state gate

Before production edits, prove from the current committed checkout and retained evidence:

- R3 Native iOS Runtime v0 is complete: **33/33**;
- R4 real-device acceptance is complete: **20/20**;
- R5 separation/provenance closure is complete: **7/7**;
- R6 Agent Foundation is accepted: **44/44**;
- R7 Retrieval + Post-Action State Safety is accepted: **31/31**;
- R8 Capability Discovery / Skill Foundry is accepted: **47/47**;
- R9 Adaptive Execution Performance is accepted: **47/47**;
- R8+R9 combined certification is **94/94**, Independent Reviewer APPROVED, Goal Reviewer GOAL_PASS, Final Judge PASS, unresolved=[], errors=[];
- current deterministic suite and required guards are green;
- Native iOS Runtime public surface remains exactly six operations: `status`, `observe`, `execute`, `invalidate`, `recover`, `close`;
- no R10 implementation already exists that would make any planned work duplicate;
- no active/durable R10 Run already exists for this same Goal.

Known latest certified R8/R9 software checkpoint from retained evidence: `25d59d7d832b430556e56141198e03e8afd77c62`. Known docs successor at the close of the prior Goal: `2a632d98e4a2887cb3aeebcd5cf43528a37bf5e9`. These are evidence references, not substitutes for a fresh current-HEAD audit.

If the baseline is not green, repair only the precise blocker required to restore the certified floor before continuing R10. Do not reopen or redesign completed R3–R9 work without a reproduced current defect.

## 3. R10 design-freeze requirement

Before parallel production edits, one design owner must retain an R10 design freeze under `docs/evidence/` using the actual execution date. The freeze must decide, from the current code and retained legacy/domain evidence:

- the minimal domain adapter boundary;
- exactly which modules are generic core versus domain-specific;
- allowed dependency direction;
- how domain behavior enters Skill Gates / ActiveSkill / Coordinator without bypassing them;
- how Merge Boss and GoGoMatch behavior is represented without domain taxonomy leaking into generic core;
- migration/source-provenance rules and what may be behaviorally reimplemented versus copied;
- revision/precondition/postcondition semantics for migrated behaviors;
- risk/reversibility/human-gate classification for domain operations;
- deterministic fixtures and accepted historical evidence sources;
- bounded real-workflow safety envelope;
- performance baseline and non-regression budgets relative to retained R9-safe behavior;
- exact file ownership for parallel lanes;
- rollback/removal path for a defective domain adapter.

The design freeze may refine file names after inspecting the repository, but must not widen the six-operation Runtime contract or introduce a second device-mutation path merely for convenience.

## 4. R10 scoring rubric — 35 points

The historical roadmap fixes R10 at **35 total points**. This handoff freezes the following orchestration allocation unless stronger already-retained R10 authority is discovered during the current-state audit; any such authority must be cited rather than silently replaced.

### R10-A — Domain adapter seam and authority isolation — 7 points

Prove a minimal explicit domain boundary such that:

- generic core remains domain-neutral;
- domain adapters cannot call transport/WDA/CoreDevice/AppService/usbmux/pymobiledevice3 directly;
- adapters cannot obtain Phone Harness or internal MCP device authority;
- all mutations still pass through Skill/Coordinator/Runtime revision-bound authority;
- R8 Skill lifecycle, registry-owned authority, human-gate, one-shot approval, and R9 safety floors remain authoritative;
- unsupported operations fail closed rather than widening Runtime.

### R10-B — Merge Boss migration — 6 points

Migrate only the behavior required by accepted current/historical evidence into the new domain adapter seam:

- explicit behavior/contract mapping and provenance;
- deterministic fixtures/tests;
- precondition/postcondition/revision binding;
- risk/reversibility/human-gate classification;
- no copied legacy production dependency or hidden execution path;
- no blind replay after partial/unknown/stale effects.

### R10-C — GoGoMatch migration — 6 points

Apply the same acceptance bar independently to GoGoMatch. Merge Boss and GoGoMatch implementation lanes may run in parallel only after the shared adapter contract is frozen and only when write ownership does not overlap.

### R10-D — Compatibility, provenance, and migration closure — 4 points

- map retained legacy/domain behavior to the new adapter contracts;
- distinguish required behavior from legacy-only behavior;
- prove no prohibited source copy or runtime dependency was introduced;
- retain migration notes, supersession/rollback information, and compatibility evidence;
- update provenance/boundary guards when a generalized regression check is warranted.

### R10-E — Bounded real-workflow evidence — 5 points

Run bounded real workflows only after deterministic gates pass and only through `Agent -> Skill/Coordinator -> Runtime`.

The live lane must:

- be single-owner for device mutation;
- use fresh revision-bound observation where required;
- avoid purchase, payment, account/security changes, messaging, deletion, profile installation, or other unsafe side effects;
- avoid fabricating hardware/app evidence;
- stop and record a precise external blocker if the required device/app/safe state is unavailable;
- retain privacy-safe evidence only (counts/enums/timings/result classes; no secrets, raw identifiers, credentials, raw screen text, screenshots, or action payloads unless an already-approved evidence contract explicitly requires them).

If a domain action is not safely reversible/low-risk, it must remain human-gated or be proven through deterministic/non-mutating evidence instead of silently weakening the safety policy.

### R10-F — Full regression, safety, and performance gates — 4 points

- full R3–R9 regression remains green;
- R10 deterministic matrix remains green;
- provenance and architecture-boundary guards pass;
- no domain leakage into generic core;
- six-operation Runtime surface remains intact;
- no stale-revision mutation, blind replay, hidden authority, or false-green validation is introduced;
- compare R10 workflow performance against retained R9-safe baselines with explicit per-kind fallback/non-regression logic; performance never overrides safety.

### R10-G — R10 acceptance package and program closure evidence — 3 points

Retain a complete R10 acceptance package mapping all 35 points to evidence, changed files/commits, tests, bounded live evidence (or precise external blocker), domain-specific review findings/repairs, rollback, and final status.

A domain-specific migration/architecture review may be part of the Workflow body. **Do not create body tasks named goal-reviewer, goal-repair, goal-rereviewer, or goal-final-judge.** Overall Goal Certification is runtime-owned and runs after the Workflow body.

## 5. Dependency direction and hard boundaries

Allowed conceptual dependency direction:

```text
Domain-specific adapter / migrated behavior
        ↓
R8 Skill contracts + Skill Gates + SkillRegistry / SkillExecutor
        ↓
R6 ExecutionCoordinator / R7 state-safety contracts
        ↓
NativeIosRuntime six-operation boundary
        ↓
unmodified pinned upstream pymobiledevice3 / WDA / CoreDevice
```

Forbidden shortcuts include:

- domain adapter -> transport/WDA/CoreDevice/AppService/usbmux/pymobiledevice3;
- domain adapter -> Phone Harness;
- domain adapter -> internal MCP device chain;
- domain adapter -> direct Runtime private internals;
- unrevisioned device mutation;
- a second trusted plugin host/device execution path;
- confidence/performance-based bypass of Skill lifecycle, validator, revision, human-gate, or reconciliation rules.

Domain names may exist in clearly domain-specific adapter/fixture/test/evidence paths. They must not become taxonomy or branching authority in generic agent/knowledge/retrieval/skill/adaptive/runtime core.

## 6. Conceptual execution phases

### Phase A — Current-state verification and duplicate elimination

**Intent:** fast/deep, read-only.

- inspect current HEAD/status/evidence/tests/guards;
- locate accepted historical/domain sources;
- confirm R3–R9 certified floor;
- confirm no duplicate completed implementation or active/durable R10 Run;
- identify only genuinely missing R10 work.

### Phase B — R10 design freeze

**Intent:** deep, write required for retained design evidence.

Freeze adapter contract, dependency direction, domain isolation, migration semantics, real-workflow safety envelope, acceptance matrix, file ownership, and rollback.

### Phase C — Shared adapter seam

**Intent:** deep architecture + balanced implementation, write required.

Implement the smallest seam needed by both migrated domains. Review shared authority and revision semantics before domain lanes depend on it.

### Phase D — Domain migrations

**Intent:** balanced implementation; deep where migration semantics/authority are subtle.

- Merge Boss lane;
- GoGoMatch lane.

Parallelizable only after Phase C is accepted and only with disjoint write ownership.

### Phase E — Compatibility/provenance closure

**Intent:** balanced/deep, read/write.

Reconcile historical behavior, legacy-only exclusions, provenance, guards, rollback, and migration evidence.

### Phase F — Deterministic and bounded real-workflow evidence

**Intent:** deep verification; write only for tests/evidence/required repairs.

Deterministic gates precede any real-device mutation. Live work is a bounded single-owner lane and must stop honestly on an external blocker.

### Phase G — Full regression/performance/domain review

**Intent:** deep, primarily read-only except concrete finding repairs.

Run R3–R10 verification, performance comparison, architecture/domain-migration review, and repair/retest/re-review any concrete blocking findings.

### Runtime-owned — Goal Certification

After the Workflow body, allow the formal runtime to perform its independent Goal Reviewer / repair / re-review / Final Judge chain. Do not duplicate it in the Workflow body.

## 7. Verification intent

The formal Planner/Author should compile proof-oriented verification from the actual repository. At minimum the completed Goal must make it observable that:

- R10 implementation/evidence files were actually changed/created where required;
- accepted R3–R9 evidence was read, not ritualistically reimplemented;
- all 35 R10 rubric points map to deterministic or retained/live evidence;
- deterministic R10 tests pass;
- full current suite passes;
- provenance and architecture-boundary guards pass;
- six Runtime public operations remain unchanged;
- no prohibited dependency/domain leakage is introduced;
- bounded real-workflow evidence exists, or the Goal remains blocked rather than falsely complete;
- required migration/architecture review is clean after repairs;
- final implementation/evidence is committed locally and working tree is clean;
- no remote push occurs.

## 8. Completion criteria / 100% rule

R10 is 100% only when all of the following are true:

- terminal durable Run is successfully completed;
- `outcome.status = completed`;
- R10 = **35/35**;
- required deterministic verification passes;
- full R3–R9 regression passes together with R10 tests;
- required provenance/boundary/privacy/revision/no-blind-replay/performance gates pass;
- required bounded real-workflow evidence is accepted;
- no major failed or completed-unverified task remains;
- retained R10 acceptance/certification evidence exists;
- runtime-owned Independent Reviewer result is approved;
- runtime-owned Final Judge is pass;
- `unresolved = []`;
- major `errors = []`;
- local repository is clean at the final retained commit;
- no remote push was performed.

A missing device/app/safe state, unavailable required evidence, or other genuine external dependency remains a blocker and prevents 100%; do not downgrade the criterion or fabricate evidence.

## 9. Non-goals

- R8/R9 redesign or reimplementation without a reproduced current defect;
- Visual Flight Recorder V0–V3;
- a generic trusted plugin host;
- new Runtime public operations without independently proven necessity;
- vector DB / PostgreSQL / pg-boss / recurring scheduler / process-per-concept expansion;
- Phone Harness runtime/build fallback;
- internal MCP device execution;
- remote push.

## 10. Formal execution rule

This handoff describes **what must be achieved**, not Workflow DSL. ChatGPT must not author a WorkflowCapsule or `wf.*` source. Submit the normalized Goal exactly once through the installed formal `@dsh-external/workflow` Plan-and-Run path and preserve the same durable Run through provider/infrastructure recovery.

