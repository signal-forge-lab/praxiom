# Praxiom R8+ Consolidated Execution Plan — 2026-09-07

- Sensitivity: PUBLIC
- Baseline gate: R6 44/44 + R7 31/31 must be formally green on the current HEAD.
- Critical path: `R8 -> R9 -> R10`.
- Separate non-critical track: Visual Flight Recorder V0–V3.

**Current status (2026-09-08):** R8+R9 is **94/94 CERTIFIED**. R10 is the next
independent 35-point critical-path Goal and has not yet been certified. Visual
V0–V3 remains separate and is not an R10 prerequisite. R10 execution authority:
`docs/design/20260908_r10_domain-migration-final-acceptance_orchestrator_handoff.md`
and the companion orchestrator prompt in the same directory.

## 1. Consolidation decision

Use the following orchestration blocks:

1. **R8 + R9 — Adaptive Skill Platform**: one DSH Goal, **94 points total**.
   Keep R8 and R9 as separately accepted internal phases. R9 design/telemetry
   preparation may overlap R8 where contracts are not prematurely frozen, but
   R9 production optimization may not bypass the R8 Skill safety/lifecycle gate.
2. **R10 — Domain Migration & Final Acceptance**: independent DSH Goal,
   **35 points**. Do not merge this into R8+R9: domain semantics, migration,
   real-workflow evidence, and final program acceptance need a separate gate.
3. **Visual Flight Recorder V0–V3**: independent read-only track,
   **29 points**. It is not on the R8→R10 critical path and must never acquire
   device-mutation authority.

This is the largest safe grouping. A single R8+R9+R10 implementation Goal would
mix generic Skill-platform authority with domain-specific migration and weaken
the value of the R10 independence/final-acceptance gate.

## 2. R8 — Capability Discovery / Skill Foundry — 47 points

The historical authority fixes the phase total at 47; the workstream letters
below are orchestration decomposition, not a replacement per-subtask point
allocation.

### R8-A Capability-need discovery

- detect repeated capability gaps from Goal/Execution/Experience evidence;
- distinguish a missing capability from a one-off failure or stale state;
- produce traceable, domain-neutral capability-need records;
- never create a Skill solely from model confidence or frequency.

### R8-B Skill candidate definition

- convert accepted needs/successful procedures into versioned Skill candidates;
- explicit inputs, outputs, preconditions, postconditions, risk/reversibility,
  authority requirements, provenance, and lifecycle state;
- no raw device bypass and no domain taxonomy in generic core.

### R8-C Validation / Skill Gate

- static schema/authority/privacy/dependency checks;
- deterministic fixture validation;
- reject stale revision assumptions, unsafe irreversible behavior, hidden
  Phone Harness/MCP/transport edges, and unsupported Runtime operations;
- generated candidates are untrusted until all gates pass.

### R8-D Sandboxed candidate execution

- smallest sufficient same-host sandbox boundary for generated/procedural code;
- cancellation/deadline/resource bounds;
- no credential inheritance or unrestricted filesystem/network/device access;
- device mutation, when authorized, remains mediated by the existing
  Coordinator -> Native iOS Runtime six-operation boundary.

### R8-E Successful-procedure reuse

- reuse known successful procedures only when current preconditions/revision and
  Knowledge lifecycle remain valid;
- never convert a historical success into blind replay;
- retain Execution/Attempt/Experience linkage.

### R8-F Skill lifecycle and confidence

- candidate -> validated -> active -> degraded/superseded/revoked style lifecycle;
- provenance/evidence/conflict rules;
- confidence/reliability affects selection evidence but never bypasses safety or
  lifecycle authority;
- rollback/revocation path is explicit and auditable.

### R8-G R8 acceptance

- deterministic Skill lifecycle/creation/execution/evaluation matrix;
- sandbox breakout/authority-bypass negative tests;
- full R3–R7 regression, provenance, boundary, privacy, no-blind-replay gates;
- independent R8 review before R9 production optimization is accepted.

## 3. R9 — Adaptive Execution Performance — 47 points

R9 consumes R7 post-action safety and R8 Skill lifecycle rather than replacing
them. Optimization must fail closed to the safe baseline.

### R9 workstreams

- action-dependency DAG and bounded parallelizable planning where safe;
- adaptive bounded batching with whole-batch preflight and reconciliation stops;
- transition/macro learning from validated successful procedures;
- temporal/countdown modeling with injected/testable clocks;
- observation-strategy optimization using R7 Adaptive Validator as the safety
  floor; fewer observes only when the next decision is sufficiently proven;
- selector/retrieval reliability feedback;
- action-path and successful-path reuse optimization;
- latency-aware reasoning/execution routing without provider/model coupling;
- recovery-rate improvement and loop/failure telemetry;
- Skill confidence and performance feedback without lifecycle truth leakage;
- execution/reasoning strategy adaptation with explainable decisions;
- regression budgets so optimization can be disabled/fallen back independently.

### R9 acceptance

- deterministic telemetry and adaptive-decision matrix;
- measured improvement against a retained R7/R8-safe baseline;
- no increase in unsafe replay, stale revision use, hidden authority, or
  false-green post-action validation;
- safe fallback behavior when telemetry/model/semantic/Skill signals fail;
- independent R9 review plus combined R8+R9 Goal Certification.

## 4. R10 — Domain Migration / Final Acceptance — 35 points

Keep R10 independent after Adaptive Skill Platform certification.

- introduce the domain adapter/plugin seam without domain names in generic core;
- migrate Merge Boss / GoGoMatch behaviors through explicit adapters/Skill Gates;
- prove legacy/domain compatibility and migration correctness;
- execute bounded real workflows through Agent -> Coordinator -> Runtime only;
- full R3–R9 regression;
- safety/privacy/provenance/independence gates;
- performance gates against retained pre-migration baselines;
- final external/non-author review and program acceptance.

## 5. Visual Flight Recorder — separate 29-point track

Current planned allocation:

- V0 read-only low-FPS rolling recorder/adapters + benchmark gate: **8**;
- V1 action/trace/revision timeline correlation: **5**;
- V2 frame-diff / animation auto-clip: **8**;
- V3 AI visual-evidence retrieval: **8**.

V0/V1 may run in parallel now that trace/event timestamps are stable. V3's R7
dependency is satisfied, but the Visual track should remain independently gated
and read-only; it must not be folded into Skill execution authority.

## 6. Recommended DSH execution graph

```text
CURRENT HEAD formal R6/R7 certification
        |
        v
R8+R9 Adaptive Skill Platform Goal (94)
  Phase A  current-state audit + design freeze
  Phase B  R8 contracts / capability discovery / Skill lifecycle
  Phase C  R8 validation + sandbox + reuse
  Phase D  R8 deterministic acceptance + independent review
  Phase E  R9 telemetry/DAG/optimization contracts
  Phase F  R9 adaptive execution implementation
  Phase G  R9 deterministic/performance/regression matrix
  Phase H  combined R8+R9 review / repair / re-review / Final Judge
        |
        v
R10 Domain Migration & Final Acceptance Goal (35)

Visual V0–V3 -------------------- independent parallel read-only track
```

## 7. Global constraints carried forward

- preserve Native iOS Runtime public operations exactly:
  `status`, `observe`, `execute`, `invalidate`, `recover`, `close`;
- no Phone Harness production/build/runtime dependency or fallback;
- no internal MCP device chain;
- no direct WDA/CoreDevice/AppService/usbmux/pymobiledevice3 edge above Runtime;
- no blind replay after unknown/partial effect;
- no state-sensitive mutation from a stale revision;
- generated code/Skills are untrusted until gated;
- no vector DB, PostgreSQL/pg-boss, recurring scheduler, generic trusted plugin
  host, process-per-concept split, or new Runtime public operation unless a
  separately proven requirement justifies it;
- no remote push unless explicitly requested.

