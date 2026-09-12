# Praxiom R6 + R7 — Safe Agent Foundation Orchestrator Handoff

Date: 2026-09-05

Status: **implementation authority for the next Praxiom execution block**

Sensitivity: **PUBLIC**

This handoff is intentionally self-contained so a fresh DSH Planner / multi-agent
run can design, implement, test, review, repair, re-review, and certify Praxiom
R6 + R7 without prior chat context.

The executing Planner must inspect CURRENT source, Git state, tests, retained
evidence, and host/device state before editing. Current repository evidence
overrides any stale statement in this document.

## 1. Decision: execute R6 and R7 as one Goal

**Yes: R6 and R7 should be orchestrated as one combined implementation Goal.**

The combined block is the **Safe Agent Foundation**:

```text
R5 execution foundation closure
        ↓
R6 Agent foundation
  - authority / execution lifecycle
  - Experience / Knowledge
  - reasoning escalation
  - goal-state recovery
        ↓
R7 Retrieval + post-action state safety
  - retrieve the right current Knowledge
  - reconcile stale/unknown state
  - adapt post-action validation cost safely
        ↓
R8 Capability Discovery / Skill Foundry   [NOT IN THIS GOAL]
```

Combined workload:

- **R6 = 44 points**;
- **R7 = 31 points**;
- **R6 + R7 = 75 points**.

R6 and R7 are one DSH Goal, but they are **not one undifferentiated coding
phase**. R6 establishes the authority, execution, Experience, Knowledge, and
recovery contracts that R7 consumes. Therefore:

1. R6 design/contracts are frozen first;
2. R6 implementation is independently accepted before R7 final acceptance;
3. R7 planning/tests may proceed in parallel where they do not freeze an R6
   implementation prematurely;
4. an R7 production path may start only when the R6 interfaces it consumes are
   stable and covered by tests;
5. combined completion is declared only after an independent R6+R7 final
   review and Goal Certification PASS.

This gives one continuous orchestration run without creating R6→R7 design
hand-off churn.

## 2. Current accepted baseline

Repository:

```text
<repository-root>
```

Accepted baseline at handoff authoring:

- Git HEAD: `01701462d17fd87ef04e3cfceca2428850cb5e54`;
- **R3 COMPLETE**;
- **R4 20/20 PASS**;
- **R5 7/7 PASS**;
- R4/R5 final independent certification:
  `run-69fb4ebb-a06a-427a-a530-05b6de142a74` → `PASS`;
- deterministic suite: **146/146 PASS** at R5 final closure;
- provenance guard: **PASS**;
- final real-device Runtime matrix: **29/29 PASS**;
- final direct stale-plumbing recovery proof:
  `DEGRADED/UNAVAILABLE -> recover() -> READY`, replay count 0;
- Phone Harness production/build/runtime dependency/execution edge: **0**;
- final XMind migration relationship:
  `R5_COMPLETE · superseded by Praxiom · 2026-09-05`;
- remote push was not performed;
- R6+ implementation had not started at R5 closure.

Re-run the current deterministic suite and provenance guard before R6 edits.
Do not assume the baseline test count remains exactly 146 after concurrent user
work; the important rule is that no accepted test is silently removed or
weakened.

## 3. Normative references

### 3.1 Current Praxiom authority

Read these first:

```text
README.md
pyproject.toml
docs/PROVENANCE.md
docs/evidence/20260905_r4-r5-final-completion.md
docs/evidence/20260905_r4-r5-final-live-gate.md
docs/evidence/20260905_r4-real-device-acceptance.md
docs/evidence/20260905_r5-separation-closure.md
src/praxiom/ios_runtime/
tests/
```

### 3.2 Historical planning authority — read-only/reference only

These documents define R6/R7 and the greenfield architecture. They are
planning/specification authority, **not permission to copy Phone Harness
production source**:

```text
<legacy-reference-root>\docs\design\20260831_r3-plus-execution-plan.md
<legacy-reference-root>\docs\design\20260831_adaptive-agent-greenfield-architecture-roadmap.md
<legacy-reference-root>\docs\design\20260901_prod-farm-ios-core-reference-audit.md
<legacy-reference-root>\docs\design\20260831_r2-native-ios-runtime-contract.md
```

Retrieval-order background may be consulted from:

```text
<legacy-reference-root>\docs\design\20260829_knowledge-core-and-upstream-thin-fork-plan.md
```

Its old assumption that the generic Knowledge system belongs inside Phone
Harness is **superseded**. Only generic retrieval concepts such as exact lookup,
typed graph traversal, deterministic lexical retrieval, and optional semantic
retrieval may be used as reference.

## 4. Target architecture for this Goal

R6/R7 add Agent-level control **above** the accepted Native iOS Runtime. Do not
move Agent concerns into device code.

```text
Goal / Teaching / operator event
            |
            v
  +----------------------------+
  | Praxiom Agent Core         |
  |                            |
  | Priority Arbiter           |
  | Reasoning Escalation       |
  | Goal-directed Recovery     |
  | Execution Coordinator      |
  | Current World / Revision   |
  | Retrieval / Validator      |
  +-------------+--------------+
                |
                | ordinary Python call / injected Runtime port
                v
  +----------------------------+
  | Native iOS Runtime v0      |
  | six operations only        |
  +-------------+--------------+
                |
                v
       upstream pymobiledevice3
                |
                v
         WDA/CoreDevice/iPhone

Agent events / outcomes
        |
        v
  +----------------------------+
  | Experience / Knowledge     |
  | Hygiene / Promotion        |
  | Retrieval / feedback       |
  +----------------------------+
```

The architecture ownership remains compatible with the target process model:

- `agent-core` owns arbitration, execution coordination, reasoning routing,
  state recovery, retrieval use, and post-action safety;
- Knowledge Promotion / Experience analysis belong to the learning side;
- Native iOS Runtime remains the only device-facing authority.

For R6/R7, conceptual ownership **does not justify a process per module**.
Implement deep modules first. Do not add process supervision, PostgreSQL,
pg-boss, or generic worker infrastructure merely because later architecture may
split components.

If a tiny Agent-facing Runtime protocol is useful for deterministic tests, it
may mirror the accepted six operations. It must not widen the Runtime contract
or expose transport/WDA internals.

## 5. Hard invariants

These are acceptance requirements, not preferences.

1. **Sensitivity is public.** Every authored DSH Agent task must explicitly use
   `sensitivity: 'public'`.
2. Workflow source may use only `modelHint: fast | balanced | deep`. Provider,
   model, fallback, and effort routing belong to Stable Routing.
3. Preserve the Native iOS Runtime six-operation public boundary:
   `status`, `observe`, `execute`, `invalidate`, `recover`, `close`.
4. Agent Core may control a device only through the accepted Runtime boundary.
   No direct `pymobiledevice3`, WDA, CoreDevice, AppService, usbmux, or transport
   calls from Agent/Knowledge/Retrieval code.
5. No Phone Harness import, subprocess, MCP edge, compatibility shim, fallback,
   copied/renamed production source, or production dependency.
6. MCP is an external integration boundary only. Do not create an internal
   Agent→Runtime MCP chain.
7. No domain/game/app semantics in Agent Core, Knowledge Core, Retrieval, or
   Runtime. Merge Boss / GoGoMatch migration belongs to R10.
8. **Do not start R8, R9, R10, or Visual V0–V3** under this Goal. In
   particular, do not implement Skill Foundry/generated code, adaptive macros,
   adaptive batching, or visual recorder work merely because R6/R7 creates
   interfaces they may later consume.
9. Generated code has no place in the trusted device path in R6/R7.
10. Reasoning tier selection is model/provider neutral and lives above Runtime.
    Heavy reasoning is never the default for known/high-confidence work.
11. No raw non-revision-bound `tap/swipe/type` task interface in ExecutionSpec.
    Device actions must be produced from current revision-bound state and sent
    through Runtime `execute`.
12. Ambiguous non-idempotent effects are never blindly replayed. `EFFECT_UNKNOWN`
    requires reconciliation, not retry-by-default.
13. Per-device mutation ownership is serialized. Only one trusted execution
    owner may hold the mutation lease for one device at a time.
14. Cancellation and deadline signals must propagate through waits, execution
    attempts, reasoning waits, Runtime request boundaries, and any owned local
    subprocess/sandbox work introduced by this Goal.
15. Execution/Attempt history must remain inspectable after restart. Use the
    smallest sufficient local durable mechanism. **No database server**.
16. Do not add recurring/delayed scheduling. `Schedule -> Execution`
    materialization is a future conditional gate.
17. Knowledge lifecycle and provenance are explicit. One observed failure must
    not silently become a universal terminal rule.
18. Human Teaching is an evidence/input type and must distinguish policy from
    factual claims; it is not absolute arbitration priority merely because it
    came from a human.
19. Default retrieval excludes superseded/disproved/non-active Knowledge from
    action authority unless the caller explicitly requests audit/history mode.
20. Semantic retrieval is **optional and non-authoritative**. Do not add a
    vector database or embedding dependency unless a measured deterministic
    retrieval miss class justifies it.
21. Semantic results, if enabled, resolve back to canonical Knowledge IDs and
    cannot directly promote truth or bypass lifecycle filters.
22. Post-action cheap validation never manufactures a new Runtime revision.
    When a next state-sensitive action needs a current revision, fresh
    `observe()` remains mandatory.
23. Unknown/partial effects, low-confidence state, security-sensitive state, or
    failed cheap validation must fall back to full reconciliation/escalation.
24. Evidence/repository fixtures must be synthetic or privacy-safe. Never
    commit raw user screen text, screenshots, action payloads, credentials,
    identifiers, local Knowledge stores, conversation text, or model secrets.
25. Do not weaken an existing test/gate to get a pass.
26. Do not push/publish remotely unless explicitly instructed by the user.

## 6. Design-freeze requirements before production edits

The first orchestration phase must produce a retained R6/R7 design freeze.
Do not let multiple authors invent incompatible schemas in parallel.

The freeze must decide, with reasons:

1. minimal package/module boundaries for Agent Core and Knowledge/Experience;
2. the stable value contracts shared by R6 and R7;
3. Runtime dependency direction / test seam;
4. ExecutionSpec, Execution, Attempt lifecycle and invariants;
5. cancellation/deadline semantics;
6. per-device lease semantics;
7. the smallest local durable ledger mechanism and crash-consistency rules;
8. Experience episode schema and privacy policy;
9. Knowledge lifecycle, evidence/provenance, conflict and supersession model;
10. model-neutral ReasoningRoute / escalation record;
11. World State / recovery-transition abstraction without domain taxonomy;
12. retrieval interfaces and canonical identity rules;
13. post-action validation signal hierarchy;
14. dependency guards that prevent Agent code from bypassing Runtime;
15. deterministic fixture matrix and any bounded real-device integration gate;
16. exact file ownership for parallel implementation lanes.

Prefer concrete immutable/versioned records and simple functions over abstract
frameworks. Do not pre-build plugin/provider/repository hierarchies without a
current requirement.

Recommended retained artifact:

```text
docs/evidence/20260905_r6-r7-plan-freeze.md
```

Use the actual execution date instead if the run happens later.

## 7. R6 requirements — Agent Foundation — 44 points

### R6-A — Priority Arbiter — 8 points

Required behavior:

- define an `InterruptEvent`-like domain-neutral contract;
- arbitrate from deadline, reversibility, risk, operator urgency, staleness,
  Teaching, and normal goal/planning inputs;
- preempt only at a safe boundary;
- invalidate stale plans when a higher-priority accepted event changes the
  world/goal assumptions;
- treat Teaching as one event type, not unconditional highest priority;
- return a traceable arbitration result with selected event/goal, rejected or
  deferred candidates, and machine-readable reasons;
- deterministic tie handling for identical effective priority.

Acceptance examples:

- urgent but unsafe/irreversible work does not bypass a safety gate;
- a stale plan cannot continue after an accepted interrupt invalidates it;
- a reversible deadline-sensitive event can preempt normal work at a safe
  boundary;
- Teaching that conflicts with a higher safety policy is deferred/rejected with
  an explicit reason;
- arbitration traces contain no raw private payloads.

### R6-B — Experience Model — 5 points

Required behavior:

- domain-neutral Observation / Action / Transition / Outcome / revision episode
  records;
- execution/attempt identity links;
- provenance and result/evidence links;
- explicit timestamps/schema version where durability requires them;
- bounded serialization/storage behavior;
- no raw screenshot/action payload in normal durable records;
- deterministic round-trip and compatibility tests.

Experience is evidence, not automatically promoted truth.

### R6-C — Knowledge Hygiene migration — 5 points

Required behavior:

- mojibake detection/normalization or explicit rejection flow;
- lifecycle states including at least active/candidate/superseded/disproved
  semantics required by current authority;
- duplicate and conflict detection before promotion;
- explicit supersession support;
- remove/supersede the obsolete idea that one failed recovery loop implies a
  universal terminal condition;
- retain provenance during normalization.

The current Praxiom repo may not yet contain real migrated Knowledge. If so,
implement and prove the generic hygiene pipeline using synthetic fixtures.
Historical domain data may be inspected read-only for shape/evidence, but **do
not migrate Merge Boss/other domain content in R6**.

### R6-D — Knowledge Promotion Pipeline — 8 points

Required lifecycle:

```text
raw
 -> normalized
 -> candidate
 -> conflict_checked
 -> verified
 -> promoted
```

with explicit alternatives:

```text
superseded
disproved
rejected/insufficient-evidence   [name may differ if the design freeze chooses]
```

Required behavior:

- Human Teaching distinguishes policy/instruction from factual assertion;
- promotion is backed by evidence aggregation, not one opaque score;
- conflicts block or branch promotion rather than being silently overwritten;
- supersession keeps history/provenance;
- promotion decisions are traceable;
- no semantic-retrieval score can directly promote Knowledge;
- no Agent hot-path mutation is blocked on expensive learning analysis.

### R6-E — Reasoning Escalation v1 — 5 points

Required explicit tiers:

```text
deterministic
lightweight
heavy
```

Required escalation triggers include at minimum:

- unknown state;
- conflict with current promoted Knowledge;
- repeated unexplained failure;
- low confidence near a side-effect boundary;
- unexplained post-action transition;
- Human Teaching contradicting current Knowledge.

Every route decision records the tier, machine-readable reason, latency, and
outcome. The production interface must not contain provider/model names.

Acceptance may use fake/stub reasoners. R6 does **not** require an external LLM
service for deterministic tests.

### R6-F — Execution Coordinator v1 — 8 points

This is on the critical path.

Required model:

```text
versioned ExecutionSpec
        ↓
Execution
        ↓
Attempt
        ↓
Native iOS Runtime
```

`ExecutionSpec` must carry a validated, versioned identity including:

- namespace/owner;
- task type;
- positive task version;
- validated payload that does **not** expose a raw device-automation bypass.

Required behavior:

- stable Execution and Attempt IDs/lifecycle;
- restart/history inspection through the smallest local durable ledger;
- cancellation token propagation;
- deadline propagation and expiry handling;
- one per-device mutation lease/lane;
- evidence/trace/result links by execution and attempt;
- no second device authority;
- no raw non-revision-bound tap/swipe task envelope;
- no PostgreSQL/pg-boss/external queue requirement;
- same-process deep module first.

Storage selection is deliberately not prescribed. The design freeze must
choose the smallest mechanism that can prove atomic/consistent attempt history,
restart inspection, schema/version safety, and bounded cleanup. Standard-library
SQLite is acceptable if justified; an external database service is not.

Required failure tests:

- invalid task version/payload rejected before execution;
- second execution cannot concurrently acquire the same device mutation lease;
- cancellation during wait prevents the next mutation;
- expired deadline prevents the next mutation;
- terminal attempt releases its lease;
- restart can inspect prior attempts without silently changing task semantics;
- failed/unknown effect is retained in attempt evidence and never auto-replayed.

### R6-G — Goal-directed State Recovery v1 — 5 points

This is **Agent task-state recovery**, distinct from Runtime transport/WDA
`recover()`.

Required loop:

```text
Goal + Current World / Revision
        ↓
off-goal?
  no -> normal planning
  yes
   ↓
classify current state
   ↓
retrieve state-specific recovery transition(s)
   ↓
choose bounded reversible/allowed transition
   ↓
execute through revision-safe Runtime
   ↓
validate resulting state
   ↓
known anchor / goal path OR escalation
```

Required behavior:

- retrieve recovery transitions by current state, not one fixed task query;
- every state-changing step is validated;
- suppress repeated ineffective state/action loops;
- failed transition evidence stays scoped to the state/control context;
- escalation order:
  deterministic transition -> lightweight -> heavy -> human/physical gate;
- paid/irreversible/security-sensitive/disallowed transitions fail closed;
- successful recovery episodes feed Experience and may later feed Knowledge
  Promotion;
- no macro/Skill promotion in R6.

### R6 exit gate

R6 is **44/44 accepted** only when:

- all R6-A..G acceptance scenarios pass deterministically;
- Execution Coordinator preserves Runtime authority/revision/effect semantics;
- Knowledge/Experience records are privacy/provenance-safe;
- cancellation/deadline/lease/restart semantics are proven;
- goal-directed recovery is loop-bounded and fail-closed;
- full pre-existing Runtime tests remain green;
- provenance + new architecture-boundary checks pass;
- an independent non-author deep R6 review finds no blocking correctness,
  architecture, safety, privacy, durability, provenance, or test issue;
- every blocking R6 review finding is repaired, retested, and re-reviewed.

Do not mark R6 accepted merely because individual modules compile.

## 8. R7 requirements — Retrieval and post-action state safety — 31 points

### R7-01 — Deterministic retrieval + active-state filtering — 3 points

Required behavior:

- exact canonical ID/key retrieval first;
- deterministic active-state/lifecycle filtering;
- deterministic lexical/key ranking with stable tie behavior;
- default action-authority retrieval excludes candidate/superseded/disproved
  items unless explicitly requested for audit/history;
- provenance and canonical Knowledge IDs survive retrieval;
- bounded result count.

### R7-02 — Typed graph expansion — 5 points

Required behavior:

- domain-neutral Knowledge nodes and typed edges;
- domain adapters may later provide type values as data, but core must not
  freeze a universal game/app taxonomy;
- bounded depth/node count;
- cycle-safe traversal;
- lifecycle filtering applies during graph expansion;
- deterministic expansion/ranking;
- provenance/canonical identity retained.

### R7-03 — Optional semantic retrieval + rerank — 5 points

Do not add semantic retrieval merely to tick a box.

Required implementation contract:

- optional semantic retrieval/rerank seam exists and is testable;
- disabled or unused by default unless deterministic retrieval evidence proves
  a meaningful miss class;
- no vector database required;
- no semantic result becomes truth authority;
- semantic candidates resolve to canonical Knowledge IDs;
- lifecycle filters remain authoritative;
- deterministic/exact evidence can outrank or reject semantic candidates;
- semantic-provider failures degrade safely to deterministic retrieval.

If the executing run proves a real miss class and chooses an embedding backend,
record why, keep the dependency optional/minimal, and preserve all rules above.
Otherwise accept R7-03 with the optional seam + deterministic test adapter and a
retained decision that production semantic retrieval remains disabled.

### R7-04 — Retrieval outcome feedback / stale decay — 5 points

Required behavior:

- link retrieval candidates to later execution/validation outcomes;
- update bounded reliability/recency/usefulness evidence deterministically;
- stale decay uses an injected/testable clock or explicit timestamps;
- feedback changes ranking/evidence, not lifecycle truth by itself;
- negative feedback does not auto-disprove from one event;
- promoted/superseded/disproved lifecycle rules outrank popularity;
- ranking changes are explainable/reversible and traceable.

Avoid opaque self-reinforcing scores that can make frequently retrieved wrong
Knowledge increasingly dominant.

### R7-05 — Generic rollback / state-revision reconciliation — 5 points

Required behavior:

- general stale-state and unknown-effect reconciliation above Runtime;
- stale plan/revision invalidates the continuation path;
- `EFFECT_UNKNOWN` and partial/ambiguous outcomes require state reconciliation
  before continuing;
- no blind retry of non-idempotent mutation;
- rollback occurs only when a known allowed reversible compensation exists;
- otherwise re-observe/retrieve/replan/escalate;
- Execution/Attempt evidence records what is known vs unknown;
- cancellation/deadline is respected during reconciliation.

### R7-06 — Post-Action Adaptive Validator — 8 points

Goal: use the cheapest sufficient causal post-check without weakening state
safety.

Validation signal ladder should be explicit and may use, as appropriate:

1. ExecutionResult / attempted-effect semantics;
2. Execution/Attempt expectations and known causal invariant;
3. privacy-safe Runtime status / trace signals;
4. cheap deterministic state evidence already available;
5. fresh full Runtime `observe()` when state meaning is not otherwise proven;
6. reasoning/human escalation when still ambiguous.

Hard rules:

- cheap validation can defer/avoid an immediate expensive observation only
  when its postcondition is sufficient for the next decision;
- cheap validation **does not create a Runtime revision**;
- after a successful mutation invalidates the accepted revision, a subsequent
  revision-bound/state-sensitive device action still requires a fresh current
  observation;
- `EFFECT_UNKNOWN`, partial effect, state mismatch, low confidence, or a
  security/irreversibility boundary forces full reconciliation/escalation;
- validator feedback may later improve policy, but one success/failure does not
  bypass fixed safety gates;
- validator decisions are traceable by validation method, confidence/reason,
  latency/cost class, and outcome.

### R7 exit gate

R7 is **31/31 accepted** only when:

- R6 exit has already passed;
- R7-01..06 deterministic scenario matrix passes;
- deterministic retrieval remains the safe fallback;
- semantic retrieval, if present, is optional/non-authoritative;
- unknown/stale effects cannot produce blind replay;
- post-action validator cannot authorize a state-sensitive next mutation using
  a stale/invalid revision;
- retrieval feedback cannot silently override Knowledge lifecycle truth;
- full R3-R6 regression suites remain green;
- provenance + architecture-boundary checks pass;
- an independent non-author deep R7 review finds no blocking issue;
- every blocking finding is repaired/retested/re-reviewed.

## 9. Required deterministic acceptance matrix

Create retained synthetic fixtures/scenarios rather than relying only on unit
tests around implementation details. Names may differ, but coverage must be at
least equivalent to the following.

### R6 scenario set

```text
R6-A01 arbitration deadline/risk/reversibility
R6-A02 safe-boundary preemption + stale-plan invalidation
R6-B01 Experience round-trip / bounds / privacy / provenance
R6-C01 mojibake/duplicate/conflict/supersession hygiene
R6-D01 Knowledge promotion evidence/conflict/Teaching policy-vs-fact
R6-E01 deterministic/light/heavy routing + escalation trace
R6-F01 ExecutionSpec validation/version rejection
R6-F02 Execution/Attempt durable lifecycle + restart inspection
R6-F03 cancellation/deadline prevents later mutation
R6-F04 per-device lease serializes mutation ownership
R6-F05 failed/unknown effect retained with zero auto-replay
R6-G01 known reversible off-goal recovery returns to anchor
R6-G02 ineffective transition loop suppression
R6-G03 high-risk/unknown recovery escalates without unsafe mutation
```

### R7 scenario set

```text
R7-01 active-filter + exact/deterministic retrieval stability
R7-02 bounded cycle-safe typed graph expansion
R7-03 optional semantic rerank resolves canonical IDs / safe fallback
R7-04 outcome feedback + stale decay without lifecycle corruption
R7-05 stale revision reconciliation
R7-06 EFFECT_UNKNOWN reconciliation with no replay
R7-07 known reversible rollback vs no-safe-rollback escalation
R7-08 cheap post-check accepted only for a sufficient postcondition
R7-09 cheap post-check mismatch -> full observe/reconciliation
R7-10 mutation invalidates revision -> next state-sensitive action requires observe
R7-11 cancellation/deadline during retrieval/validation
R7-12 end-to-end Goal -> retrieve -> execute -> validate -> Experience linkage
```

Machine-readable fixture/output is recommended so reviewers can audit coverage
without interpreting prose. Keep all content synthetic and privacy-safe.

## 10. Architecture/dependency guard to add

R6/R7 introduce the first production code above Native iOS Runtime. Add a
small automated architecture guard, test, or script proving at minimum:

- `src/praxiom/agent*`, Knowledge/Experience/Retrieval modules do not import
  `pymobiledevice3`;
- they do not import/use Phone Harness;
- they do not invoke WDA/CoreDevice/AppService/usbmux directly;
- they do not use subprocess/MCP as a hidden internal Runtime bridge;
- trusted device mutation enters through the accepted Praxiom Runtime seam;
- no domain-specific package/name has entered generic core.

Do not require a specific filename, but a discoverable command such as
`scripts/check_agent_boundaries.py` is preferred if that is the smallest
implementation. It must itself have a regression test proving it fails closed
when a prohibited import/edge is planted in a synthetic temp tree.

The existing guard remains mandatory:

```text
.venv\Scripts\python scripts\check_provenance.py
```

## 11. Real-device combined integration gate

Most R6/R7 behavior must be deterministic with a fake Runtime and synthetic
World State. Do not make routine tests phone-dependent.

Before final combined certification, when an iPhone is available, run **one
bounded single-lane Safe Agent Foundation integration matrix** to prove the new
Agent layer does not bypass R3-R5 safety on real hardware.

This is an integration gate, not additional R6/R7 points.

Use only safe reversible system-app context such as Home/Settings. At minimum
prove:

1. Execution Coordinator obtains one device mutation lease;
2. a current observation/revision feeds a safe planned mutation;
3. mutation is sent only through Native iOS Runtime;
4. accepted revision becomes invalid after mutation;
5. validator/reconciliation performs a fresh observation before any next
   state-sensitive revision-bound mutation;
6. Execution/Attempt evidence links the result without raw user/device data;
7. a bounded reversible off-goal state can use Goal-directed State Recovery to
   reach a known safe anchor and validate it;
8. cancellation/deadline can prevent a not-yet-sent next mutation without
   leaving an orphan lease;
9. no blind replay occurs;
10. Agent shutdown releases only owned resources and Runtime remains the sole
    device authority.

Do **not** manufacture a dangerous ambiguous effect or physical disconnect to
prove R7; deterministic fixtures already own exact ambiguity semantics.

If no device is attached, complete all AI-executable R6/R7 work, reviews, and
deterministic evidence, retain this exact physical blocker, and do not falsely
declare combined 100% completion.

Recommended evidence:

```text
docs/evidence/<date>_r6-r7-safe-agent-foundation-device-matrix.json
docs/evidence/<date>_r6-r7-safe-agent-foundation-acceptance.md
```

## 12. Orchestration graph

Maximum useful concurrency: **3**.

Use **at most two concurrent code-author lanes**. Device mutation is always
single-lane. Prefer lower concurrency when files/contracts overlap.

### Phase A — read-only audit / reconciliation

Up to 3 read-only agents:

1. **Architecture/spec auditor — deep / public**
   - reconcile R6/R7 execution plan, greenfield roadmap, R5 current closure;
   - enumerate mandatory contracts/invariants;
   - identify superseded historical assumptions.
2. **Current source/test/boundary auditor — deep / public**
   - inspect current Praxiom Runtime, tests, package dependencies, public seam;
   - map R6/R7 work onto the smallest new module boundaries;
   - identify architecture-guard requirements.
3. **Execution/Knowledge/retrieval reference auditor — deep or balanced / public**
   - re-read the prod-FARM Execution Coordinator reference audit;
   - inspect generic retrieval concepts only;
   - recommend the smallest durable ledger and retrieval design without
     importing old architecture/source.

Gate A: one deep synthesis writes the design freeze before production edits.

### Phase B — shared contracts / deterministic fixture skeleton

One primary author should establish the shared R6/R7 value contracts and
fixture vocabulary to prevent schema divergence.

May include:

- ExecutionSpec / Execution / Attempt;
- Experience / Knowledge identity + lifecycle;
- arbitration and reasoning route records;
- World State / recovery transition seam;
- retrieval/validation result records;
- fake Runtime/test seam;
- architecture boundary guard scaffold.

Run focused tests and an independent design review before allowing multiple
implementation lanes.

### Phase C — R6 implementation

Recommended maximum two author lanes after Phase B review:

**Lane C1 — authority/execution critical path — deep/balanced / public**

- R6-A Priority Arbiter;
- R6-E Reasoning Escalation;
- R6-F Execution Coordinator;
- R6-G Goal-directed State Recovery.

These components share lifecycle/authority semantics and should not be split
across many overlapping authors.

**Lane C2 — Experience/Knowledge — balanced/deep / public**

- R6-B Experience Model;
- R6-C Knowledge Hygiene;
- R6-D Knowledge Promotion.

Keep file ownership non-overlapping with C1 where practical.

### Phase D — R6 integration / independent review / repair

1. run the full R6 synthetic scenario matrix;
2. run full existing tests, provenance, architecture guard;
3. non-author deep R6 review covering:
   - authority/preemption;
   - cancellation/deadline/lease races;
   - crash/durability semantics;
   - revision/effect semantics;
   - recovery-loop safety;
   - privacy/provenance;
   - Knowledge promotion correctness;
   - unnecessary infrastructure/framework expansion;
4. repair all blocking findings with smallest changes;
5. rerun focused/full gates;
6. re-review until R6 = 44/44 accepted.

### Phase E — R7 retrieval implementation

After R6 interfaces consumed by retrieval are stable, use up to two lanes:

**Lane E1 — deterministic retrieval/graph/semantic seam/feedback**

- R7-01;
- R7-02;
- R7-03;
- R7-04.

**Lane E2 — reconciliation/validator**

- R7-05;
- R7-06.

Both must share the frozen canonical Knowledge IDs/lifecycle and
Execution/Attempt/revision semantics rather than inventing parallel state
models.

### Phase F — R7 integration / independent review / repair

1. run the full R7 scenario matrix;
2. run full R3-R7 regressions;
3. provenance + architecture guard;
4. non-author deep R7 safety/retrieval review;
5. repair/retest/re-review until R7 = 31/31 accepted.

### Phase G — bounded real-device Safe Agent integration

One mutating device lane only. Other agents may analyze already-produced
privacy-safe evidence but must not touch the device.

Run the §11 matrix and retain evidence. If a code repair changes execution,
revision, validation, or lease semantics, rerun every affected device cell.

### Phase H — combined final review and Goal Certification

Run a fresh **non-author deep combined R6+R7 review** over current committed
state and retained evidence.

Review specifically for:

- hidden direct device bypass;
- stale revision continuation;
- ambiguous-effect replay;
- lease/cancellation/deadline races;
- unsafe recovery loops;
- Knowledge lifecycle/provenance corruption;
- semantic retrieval becoming truth authority;
- post-action validator false-green behavior;
- privacy leaks in durable stores/traces/evidence;
- Phone Harness/runtime dependency regression;
- domain leakage;
- unnecessary R8+/scheduler/plugin/vector-DB/process scope.

Repair all blocking findings, rerun affected tests/device integration, and
re-review until no blocking finding remains.

Then run the runtime-owned Goal Certification path / final independent judge.
The final report must contain the exact Certification run ID and verdict.

## 13. DSH task construction rules

Every task authored by the Planner must include:

```text
sensitivity: public
modelHint: fast | balanced | deep
```

Never put provider/model names in workflow source.

Recommended modelHint use:

- `fast`: bounded Git/status scans, format checks, deterministic evidence
  extraction, simple non-author verification;
- `balanced`: ordinary isolated implementation and tests;
- `deep`: architecture/contracts, execution/effect semantics, durability,
  recovery/retrieval safety, adversarial review, final synthesis.

Do not use modelHint as a substitute for task decomposition.

Avoid `requiredReadPaths` as a final correctness oracle. Previous R4/R5
certification proved that DSH read-tracking can false-negative even when agents
perform valid review. Require explicit review output/evidence and use
read-only/adversarial verifier tasks instead.

## 14. Recommended task DAG

Exact IDs may differ, but preserve dependencies approximately as follows:

```text
A1 spec-authority-audit ──────┐
A2 current-code-audit ────────┼─> A4 design-freeze
A3 execution-retrieval-audit ─┘

A4 design-freeze
  -> B1 shared-contracts
  -> B2 fixture-and-boundary-guard
  -> B3 shared-contract-review

B3
  -> C1 authority-execution
  -> C2 experience-knowledge

C1 + C2
  -> D1 R6-integration
  -> D2 R6-independent-review
  -> D3 R6-repair-if-needed
  -> D4 R6-re-review

D4 PASS
  -> E1 retrieval-graph-feedback
  -> E2 reconciliation-validator

E1 + E2
  -> F1 R7-integration
  -> F2 R7-independent-review
  -> F3 R7-repair-if-needed
  -> F4 R7-re-review

F4 PASS
  -> G1 device-preprobe
  -> G2 single-lane-device-matrix
  -> G3 evidence-analysis

G2/G3 accepted
  -> H1 combined-adversarial-review
  -> H2 repair/retest/re-device-if-needed
  -> H3 combined-re-review
  -> H4 final-certification
  -> H5 final-completion-report
```

Repair tasks are conditional and must target actual blocking findings only.
Do not invent extra work because a lane is idle.

## 15. Verification requirements

At run start and after every cross-cutting repair:

```text
.venv\Scripts\python -m pytest -q
.venv\Scripts\python scripts\check_provenance.py
```

Also run the new architecture-boundary guard/check introduced by this Goal.

Recommended additional verification categories:

- focused tests per R6/R7 subsystem;
- deterministic fixture matrix;
- static import/dependency boundary scan;
- ledger restart/crash scenarios using temporary synthetic stores;
- concurrency tests for per-device lease using fakes, not simultaneous real
  device mutations;
- cancellation/deadline race tests with deterministic clocks/events;
- retrieval ranking tests with explicit deterministic clocks;
- validator false-positive/false-negative adversarial fixtures;
- full suite after each review repair;
- `git diff --check` before checkpoint/final commits;
- final `git status --short` must be clean except explicitly documented
  concurrent user work that the run must not overwrite.

Never commit `.pytest_cache`, runtime ledgers, local Knowledge databases,
screenshots, model logs, credentials, pair records, or other runtime data.

## 16. Required retained evidence

At minimum retain:

```text
docs/evidence/<date>_r6-r7-plan-freeze.md
docs/evidence/<date>_r6-acceptance.md
docs/evidence/<date>_r7-acceptance.md
docs/evidence/<date>_r6-r7-safe-agent-foundation-acceptance.md
docs/evidence/<date>_r6-r7-final-completion.md
```

Recommended machine evidence:

```text
docs/evidence/<date>_r6-r7-deterministic-matrix.json
docs/evidence/<date>_r6-r7-safe-agent-foundation-device-matrix.json
```

Final completion report must include:

- R6 and R7 points and per-item verdicts;
- architecture/package decisions and reasons;
- exact current public Agent/Runtime boundaries;
- full deterministic test command/count;
- provenance and architecture-boundary guard result;
- durable ledger implementation/validation summary;
- cancellation/deadline/lease evidence;
- Knowledge lifecycle/promotion evidence;
- retrieval/semantic-enabled-or-disabled decision and evidence;
- reconciliation/no-blind-replay evidence;
- validator safety evidence;
- real-device integration result or exact physical blocker;
- independent review findings and each repair;
- final Certification run ID/verdict;
- exact commits/files;
- remote push status;
- explicit statement that R8+ was not started.

## 17. Git / change policy

- Inspect Git state before edits and preserve concurrent user work.
- Prefer small coherent checkpoint commits after reviewed units.
- Do not rewrite unrelated history.
- Do not delete useful historical evidence to make scans look cleaner.
- Do not commit runtime/private data.
- Do not push/publish unless explicitly instructed.
- Final report lists exact local commits and confirms push status.

Suggested checkpoints, not mandatory commit names:

```text
R6: freeze Safe Agent contracts
R6: implement execution and knowledge foundation
R6: accept Agent foundation
R7: implement retrieval and state safety
R7: accept retrieval and validator
R6 R7: record Safe Agent integration evidence
R6 R7: finalize certified completion
```

## 18. Scope explicitly deferred

Do not implement these under this Goal unless a blocking R6/R7 acceptance fact
proves a minimal prerequisite is unavoidable:

- R8 Capability Need Discovery / Skill Foundry / generated-code sandbox;
- R9 adaptive batching/macros/timing/observation/reasoning optimization;
- R10 domain migration / plugin seam / Skill Gates;
- Visual Flight Recorder V0–V3;
- recurring/delayed scheduler;
- PostgreSQL / pg-boss / multi-worker durable queue;
- generic trusted plugin host;
- vector database;
- process-per-concept architecture;
- new Native iOS Runtime public operation;
- upstream pymobiledevice3 fork/patch unless its independent R1 gate is truly
  met by a newly reproduced upstream defect.

## 19. Completion definition — 100%

For the combined **R6 + R7 Safe Agent Foundation Goal**, 100% means all of the
following are true:

- R6-A..G = **44/44 accepted**;
- R7-01..06 = **31/31 accepted**;
- combined = **75/75 accepted**;
- all current and new deterministic tests pass;
- provenance guard passes;
- Agent architecture/dependency guard passes fail-closed regression tests;
- Runtime six-operation boundary and R3-R5 safety semantics remain intact;
- no direct device bypass exists outside Runtime;
- cancellation/deadline/per-device mutation lease semantics are proven;
- durable execution history/restart inspection is proven;
- Knowledge/Experience lifecycle/provenance/privacy gates pass;
- retrieval/semantic/feedback gates pass without truth-authority leakage;
- stale/unknown-effect reconciliation cannot blind replay;
- Post-Action Adaptive Validator cannot false-green a stale revision into the
  next state-sensitive mutation;
- bounded real-device combined integration gate passes, or one precise
  external/physical blocker is honestly retained instead of claiming 100%;
- independent R6 review passes after any repairs;
- independent R7 review passes after any repairs;
- independent combined adversarial review passes after any repairs;
- runtime-owned final Goal Certification returns PASS;
- final retained completion report is committed;
- intended working tree is clean;
- no R8+ or unrelated work was started;
- remote push was not performed unless explicitly requested.

Do not stop at design, implementation, unit tests, or first review while any
AI-executable work in this Goal remains.

