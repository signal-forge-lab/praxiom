# Praxiom R8 + R9 — Adaptive Skill Platform Orchestrator Handoff

Date: 2026-09-07

Status: **implementation authority after the current R6/R7 HEAD is formally certified**

Sensitivity: **PUBLIC**

This handoff is self-contained for a DSH Planner / multi-agent execution. The
Planner must inspect current source, Git state, tests, retained evidence, and the
latest Formal R6/R7 certification before editing. Current repository evidence
overrides stale prose.

## Goal

Implement and certify **R8 Capability Discovery / Skill Foundry (47)** and
**R9 Adaptive Execution Performance (47)** as one internally gated
**Adaptive Skill Platform Goal (94 points)**.

R8 and R9 are combined to remove contract handoff churn, but are not one
undifferentiated coding phase. R8 establishes Skill authority/lifecycle/sandbox
contracts. R9 may prepare telemetry and deterministic fixtures in parallel, but
must not let optimization become a production authority path until the R8 gate
is accepted.

R10 and Visual V0–V3 are outside this Goal.

## Mandatory baseline

Before production edits, prove from current evidence and fresh checks:

- R6 44/44 and R7 31/31 are accepted on current committed HEAD;
- all deterministic tests pass;
- provenance and agent-boundary guards pass;
- Runtime remains six-operation-only;
- retained real-device R6/R7 evidence is readable; do not repeat device mutation
  merely to recreate already sufficient historical evidence;
- no blocking R6/R7 review finding remains.

If the current HEAD is not formally R6/R7 green, stop R8/R9 implementation and
return the precise blocker.

## Required first phase: design freeze

One design owner freezes shared contracts before parallel authorship. Decide:

- capability-need record and evidence threshold;
- versioned Skill candidate/active Skill contracts;
- Skill lifecycle, provenance, conflict, supersession/revocation;
- precondition/postcondition and revision-binding semantics;
- generated/procedural code trust boundary and minimal sandbox contract;
- cancellation/deadline/resource/network/filesystem/credential restrictions;
- Skill execution -> Coordinator -> Runtime dependency direction;
- procedure reuse/no-blind-replay rules;
- R9 telemetry contracts and privacy-safe aggregation;
- action-dependency DAG and adaptive batching invariants;
- observation optimization/R7-validator integration;
- temporal model/test clock;
- performance baseline and regression budgets;
- exact file ownership for parallel lanes.

Retain the freeze under `docs/evidence/` using the actual execution date.

## R8 required behavior

Implement the workstreams defined in
`docs/design/20260907_r8plus_execution_plan.md`:

- capability-need discovery;
- Skill candidate definition;
- validation / Skill Gates;
- sandboxed candidate execution;
- successful-procedure reuse;
- Skill lifecycle/confidence/provenance;
- deterministic and adversarial acceptance.

Hard rules:

- generated/procedural code has zero trusted device authority by origin;
- no direct Runtime bypass, Phone Harness fallback, internal MCP bridge, raw
  transport call, or unrevisioned mutation;
- one successful episode never auto-promotes a Skill;
- unknown/partial effect never becomes an automatic retry or macro continuation;
- policy/safety/lifecycle gates outrank frequency/confidence/performance.

R8 must be independently reviewed and accepted before R9 production authority
is considered accepted.

## R9 required behavior

Implement/adapt only on top of the accepted R7/R8 safety floor:

- action dependency DAG;
- adaptive bounded batching;
- transition/macro learning from validated procedures;
- temporal/countdown modeling;
- observation strategy optimization;
- selector/retrieval reliability feedback;
- successful/action-path reuse optimization;
- latency-aware routing;
- recovery-rate/Skill-confidence/performance feedback;
- reasoning/execution strategy adaptation;
- explicit safe fallback and regression budgets.

Any optimization that cannot prove a next mutation's current state/revision must
fall back to fresh observe/reconciliation. Performance never overrides safety.

## Parallel lanes

Safe parallelism after design freeze:

1. R8 capability/Skill schema + lifecycle;
2. R8 validator/sandbox negative-test lane;
3. R8 procedure-reuse + Coordinator integration lane;
4. R9 telemetry/performance-baseline lane (preparatory only until R8 accepted);
5. deterministic fixture / architecture-guard lane.

After R8 acceptance, R9 DAG/batching/observation/routing/adaptation lanes may
proceed in parallel against the frozen interfaces. Keep merge ownership explicit.

## Required reviews and certification

The orchestrator must complete, not merely propose:

1. current-state audit;
2. design freeze;
3. implementation;
4. deterministic tests and guards;
5. R8 independent review;
6. repair + retest + re-review for every blocking R8 finding;
7. R8 acceptance;
8. R9 implementation/performance evidence;
9. R9 independent review;
10. repair + retest + re-review for every blocking R9 finding;
11. combined R8+R9 adversarial review;
12. runtime-owned Goal Reviewer;
13. runtime-owned Final Judge;
14. retained completion evidence.

100% requires R8=47/47, R9=47/47, combined=94/94, current tests/guards green,
no unresolved/errors, Reviewer approved, Final Judge PASS, and no R10/Visual
scope leakage.

Do not push remotely unless the user explicitly requests it.

