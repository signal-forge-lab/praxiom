# DSH execution prompt — Praxiom R6 + R7 Safe Agent Foundation

Use this prompt with the current DSH Planner / Plan-and-Run policy.

Primary handoff:

```text
<repository-root>\docs\design\20260905_r6-r7_safe-agent-foundation_orchestrator_handoff.md
```

Repository:

```text
<repository-root>
```

---

You are the implementation Planner for **Praxiom R6 + R7 — Safe Agent
Foundation**.

Treat R6 and R7 as **one 75-point Goal with two acceptance gates**:

- R6 Agent Foundation = 44 points;
- R7 Retrieval + post-action state safety = 31 points;
- R7 final acceptance depends on an accepted R6 foundation.

Read the primary handoff first. Then inspect CURRENT Praxiom source, Git state,
tests, R4/R5 completion evidence, the historical R6/R7 planning authorities,
current Python dependencies, and current device availability. Current evidence
overrides cached statements.

The accepted authoring-time baseline is R5 COMPLETE at Git
`01701462d17fd87ef04e3cfceca2428850cb5e54`, 146/146 deterministic tests,
provenance PASS, R4 real-device 29/29, Phone Harness execution edge 0, and
final R4/R5 Certification PASS. Re-verify before editing.

**Sensitivity is PUBLIC.** Every authored task must explicitly use
`sensitivity: 'public'`. Workflow source may use only
`modelHint: fast | balanced | deep`. Never specify provider/model/fallback/effort
from workflow source; Stable Routing owns those decisions.

Your job is not to produce a plan and stop. Design, implement, test, review,
repair, re-review, run bounded real-device integration when available, produce
retained evidence, and continue through runtime-owned final Goal Certification.

Do not start R8, R9, R10, Visual Flight Recorder, domain migration, Skill
Foundry/generated code, adaptive macros/batching, generic plugin hosting,
durable scheduling, PostgreSQL/pg-boss, or vector-database work.

## Critical execution sequence

1. Run a read-only current-state/authority audit using up to 3 agents:
   architecture/spec, current code/tests/boundaries, and execution/knowledge/
   retrieval reference audit.
2. Synthesize and retain one R6/R7 design freeze before production edits.
3. Freeze shared contracts/fixtures first: ExecutionSpec/Execution/Attempt,
   Experience/Knowledge identity+lifecycle, arbitration/reasoning records,
   World State/recovery transition seam, retrieval/validation records, fake
   Runtime seam, and architecture guard.
4. Implement R6 with at most two non-overlapping author lanes:
   - authority/execution: R6-A/E/F/G;
   - Experience/Knowledge: R6-B/C/D.
5. Run R6 scenario matrix, full regressions, provenance, architecture guard,
   then non-author deep R6 review. Repair/retest/re-review until R6 = 44/44.
6. Only after relevant R6 interfaces are accepted, implement R7:
   - retrieval/graph/optional semantic/feedback: R7-01..04;
   - reconciliation/validator: R7-05..06.
7. Run R7 scenario matrix, full R3-R7 regressions, provenance, architecture
   guard, then non-author deep R7 review. Repair/retest/re-review until
   R7 = 31/31.
8. If an iPhone is attached, run one bounded single mutation-lane Safe Agent
   Foundation integration matrix in Home/Settings only. Prove coordinator
   lease, Runtime-only mutation, revision invalidation, fresh observe before a
   next state-sensitive action, validator/reconciliation, bounded goal-state
   recovery, cancellation/deadline behavior, zero blind replay, and privacy-safe
   evidence. Do not manufacture dangerous ambiguity/disconnect.
9. Run a fresh non-author deep combined R6+R7 adversarial review. Repair every
   blocking finding and rerun every affected deterministic/device gate.
10. Run runtime-owned final Goal Certification and retain its exact run ID and
    PASS/FAIL verdict.
11. Produce/commit the final completion report and leave the intended Git tree
    clean. Do not push remotely.

## R6 work items

- R6-A Priority Arbiter — 8
- R6-B Experience Model — 5
- R6-C Knowledge Hygiene migration — 5
- R6-D Knowledge Promotion Pipeline — 8
- R6-E Reasoning Escalation v1 — 5
- R6-F Execution Coordinator v1 — 8
- R6-G Goal-directed State Recovery v1 — 5
- R6 total — **44**

R6 invariants include safe-boundary preemption, stale-plan invalidation,
Teaching not absolute priority, domain-neutral Experience, explicit Knowledge
lifecycle/provenance, model-neutral deterministic/light/heavy reasoning,
versioned ExecutionSpec→Execution→Attempt, local durable ledger,
cancellation/deadline, per-device mutation lease, zero raw device-automation
task bypass, and bounded validated goal-state recovery.

R6 must be independently accepted before R7 is finally accepted.

## R7 work items

- R7-01 deterministic retrieval + active-state filtering — 3
- R7-02 typed graph expansion — 5
- R7-03 optional semantic retrieval + rerank — 5
- R7-04 retrieval outcome feedback / stale decay — 5
- R7-05 generic rollback / state-revision reconciliation — 5
- R7-06 Post-Action Adaptive Validator — 8
- R7 total — **31**

Retrieval order is deterministic-first. Semantic retrieval is optional,
non-authoritative, canonical-ID resolving, lifecycle-filtered, and must not add
a vector DB merely to satisfy the point item. If no real deterministic miss
class is proven, implement/test the optional seam and leave the production
semantic backend disabled with retained evidence explaining why.

The Post-Action Adaptive Validator may use cheap causal checks before full
observation only when sufficient. Cheap validation never creates a Runtime
revision. After a mutation invalidates the revision, the next revision-bound
state-sensitive mutation still requires a fresh observe. `EFFECT_UNKNOWN`,
partial effect, low confidence, mismatch, or high-risk state requires full
reconciliation/escalation. Never blind replay.

## Hard boundaries

- Native iOS Runtime remains exactly the six-operation device authority unless
  new acceptance evidence proves a minimal contract change unavoidable.
- Agent/Knowledge/Retrieval code may not import/call `pymobiledevice3`, WDA,
  CoreDevice, usbmux, AppService, or Runtime transport internals directly.
- No Phone Harness production/build/runtime dependency, subprocess, MCP hop,
  compatibility shim, fallback, or copied source.
- No internal MCP chain.
- No game/app/domain semantics in generic core.
- One trusted mutation owner per device.
- Cancellation/deadline must prevent not-yet-sent mutations.
- Ambiguous effect never auto-replays.
- Durable records/evidence must remain privacy-safe; use synthetic fixtures.
- Do not add process-per-layer infrastructure.
- No external DB server/queue/scheduler.
- No heavy reasoning in Native Runtime.
- Do not weaken tests or review gates.
- Do not use `requiredReadPaths` tracking as the final correctness oracle;
  prior DSH runs proved it can false-negative valid review. Use explicit
  reviewer results and adversarial verification instead.

## Verification minimums

Run from current repo root using the current canonical commands:

```text
.venv\Scripts\python -m pytest -q
.venv\Scripts\python scripts\check_provenance.py
```

Add and run a fail-closed Agent architecture-boundary guard proving generic
Agent/Knowledge/Retrieval code cannot bypass Native Runtime or reintroduce
Phone Harness/direct device dependencies.

Create deterministic synthetic acceptance coverage at least equivalent to the
scenario lists in the primary handoff. Default tests must remain phone
independent.

If no iPhone is attached, continue every AI-executable design, implementation,
test, review, repair, and evidence task. Retain only the exact physical
combined-integration blocker and do not falsely claim 100%.

## Completion rule

Do not declare 100% until all are true:

- R6 = 44/44 accepted;
- R7 = 31/31 accepted;
- combined = 75/75;
- full deterministic regressions pass;
- provenance + architecture-boundary guards pass;
- no direct device bypass, stale-revision continuation, blind replay,
  lease/cancellation race, unsafe recovery loop, Knowledge lifecycle corruption,
  semantic truth-authority leak, or validator false-green remains;
- bounded real-device Safe Agent integration passes or one precise unavoidable
  physical blocker is retained instead of a false completion claim;
- independent R6 review PASS after repairs;
- independent R7 review PASS after repairs;
- combined adversarial review PASS after repairs;
- final Goal Certification PASS;
- final evidence/commits are retained and intended Git tree is clean;
- no R8+ or unrelated work was started;
- remote push was not performed unless the user explicitly requested it.

Begin now and continue until the combined R6+R7 Goal reaches the completion
rule or one genuinely non-AI-executable external/physical blocker is the only
remaining item.

