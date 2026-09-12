# Praxiom R6 + R7 — Plan Freeze (Safe Agent Foundation)

- Date: 2026-09-06
- Sensitivity: **PUBLIC**
- Scope: R6 + R7 design freeze only — **no production edits, no R4/R5 changes**
- Quality: **intent only** (this document freezes decisions; it does not implement them)
- Status: **frozen — parallel lanes must conform, not re-invent**
- Normative input:
  - `docs/design/20260905_r6-r7_safe-agent-foundation_orchestrator_handoff.md`
  - `docs/evidence/20260905_r4-r5-final-completion.md`
- Baseline carried forward (read-only, do not modify):
  - Git HEAD at handoff: `01701462d17fd87ef04e3cfceca2428850cb5e54`
  - R4 20/20 PASS, R5 7/7 PASS, combined certification `run-69fb4ebb-a06a-427a-a530-05b6de142a74` → PASS
  - Deterministic suite 146/146 PASS, provenance guard PASS, real-device matrix 29/29 PASS
  - Native iOS Runtime six operations (`status/observe/execute/invalidate/recover/close`) unchanged
  - Pinned upstream `pymobiledevice3 11.3.0`, unmodified; no Phone Harness production/build/runtime edge
- No remote push: this freeze performs and authorizes **no remote push**.
- No R8+: no R8/R9/R10 or Visual scope is authorized by this freeze.

## Freeze authority

1. This freeze decides the 16 topics required by handoff §6, with reasons.
2. **R4/R5 are untouched.** No Runtime, transport, observation, executor, or accepted-test weakening is authorized by this freeze.
3. **Serialize shared schema writes.** `Phase B` (shared contracts + fixture vocabulary) lands first and is reviewed before lanes C1/C2/E1/E2 diverge. No lane invents a parallel ExecutionSpec, Knowledge ID, revision, or retrieval record.
4. Six-operation contract and pinned upstream are preserved: Agent/Knowledge/Retrieval code controls a device only through the accepted Runtime seam.
5. **No Phone Harness edge or shim**: no import, subprocess, MCP edge, copied/renamed production source, or production dependency; historical Phone Harness docs are reference-only.

---

## T1 — Minimal package / module boundaries

Decision — keep the existing scaffold; add no new top-level packages in R6/R7:

```text
src/praxiom/agent/        arbiter.py, coordinator.py, reasoning.py, recovery.py
src/praxiom/knowledge/    experience.py, hygiene.py, promotion.py
src/praxiom/retrieval/    store.py, graph.py, semantic.py, feedback.py, reconcile.py, validator.py
src/praxiom/ios_runtime/  FROZEN (R3–R5) — no Agent concerns move into device code
scripts/check_agent_boundaries.py   (new, minimal — see T14 guard scaffold)
tests/  mirrors the above + one deterministic-matrix driver
```

Reasons:

- The scaffold already separates authority/execution (agent), learning (knowledge), and use-of-knowledge (retrieval) without a process per concept.
- Deep modules first; no PostgreSQL, pg-boss, worker infra, plugin host, scheduler, or vector-DB package.
- Domain adapters (Merge Boss / GoGoMatch) belong to R10 and must not appear as package names in generic core.

## T2 — Stable value contracts shared by R6 and R7 (records)

Decision — freeze these immutable/versioned records families in Phase B; every later module consumes them, none redefines them:

| Record | Owner file | Key invariants |
|---|---|---|
| `ExecutionSpec` records | `agent/coordinator.py` | namespace/owner, task type, positive task version, validated revision-bound payload; no raw tap/swipe bypass |
| `Execution` / `Attempt` records | `agent/coordinator.py` | stable IDs, lifecycle enum, evidence/trace links, effect (`OK/FAILED/PARTIAL/EFFECT_UNKNOWN`), `retry_safe=False` preserved |
| `Experience` records | `knowledge/experience.py` | Observation/Action/Transition/Outcome + revision + Execution/Attempt links; privacy-safe, bounded serialization |
| `Knowledge` records | `knowledge/promotion.py`, `retrieval/store.py` | canonical ID, `raw→normalized→candidate→conflict_checked→verified→promoted`, alternatives `superseded/disproved/rejected-insufficient-evidence`; provenance retained |
| `arbiter` records (`ArbitrationResult`) | `agent/arbiter.py` | selected/deferred/rejected + machine-readable reasons; deterministic ties |
| `route` records (`ReasoningRoute`) | `agent/reasoning.py` | `deterministic/lightweight/heavy`, reason, latency, outcome; provider/model-neutral |
| `World` / `recovery` records (`WorldState` / `RecoveryTransition`) | `agent/recovery.py` | current state + revision; bounded reversible/allowed transitions only |
| `retrieval` / `validation` records (`RetrievalResult` / `ValidationResult`) | `retrieval/*`, `retrieval/validator.py` | canonical Knowledge IDs, lifecycle-filter proof, method/confidence/cost-class trace |

Reasons: one shared vocabulary prevents C1/C2/E1/E2 schema divergence — the failure mode the handoff explicitly warns against. Records are plain frozen dataclasses + pure functions, not frameworks.

## T3 — Runtime dependency direction / test seam (fake Runtime)

Decision:

```text
Agent Core / Retrieval / Validator  ──ordinary Python call──>  Runtime port  ──> NativeIosRuntime
```

- Production direction is strictly Agent → Runtime; Runtime never imports Agent/Knowledge/Retrieval.
- A tiny `FakeRuntime` test seam (fake Runtime, in `tests/`, not `src/`) mirrors **only** the six operations with injected observations, revisions, effects (including `EFFECT_UNKNOWN`), latency, and failure modes. It must not widen the contract or expose transport/WDA internals.
- Routine tests use the fake Runtime; real-device cells (§T15 device gate) use the accepted Runtime.

Reasons: deterministic lease/cancel/deadline/restart/revision tests without phone dependence; production authority stays with the R3–R5 Runtime.

## T4 — ExecutionSpec / Execution / Attempt lifecycle and invariants

Decision (owned by `agent/coordinator.py`):

- `ExecutionSpec`: versioned identity (namespace/owner, task type, positive version); payload validated **before** execution; any raw non-revision-bound device-automation envelope is rejected with `INVALID_REQUEST`.
- `Execution`: `pending → running → (succeeded | failed | cancelled | expired)`; terminal states release the lease.
- `Attempt`: `planned → sent → (ok | failed | unknown-effect | cancelled | expired)`; every attempt records revision consumed, effect, evidence links.
- Invariants frozen: no second device authority; same-process deep module; no external queue; **no blind replay** — `EFFECT_UNKNOWN`/failed effects are retained with zero auto-replay; restart inspects history without silently changing task semantics.

## T5 — Cancellation / deadline semantics (lease · cancel · deadline · restart)

Decision (owned by `agent/coordinator.py`, consumed by recovery/retrieval/validator):

- Cancel: cancellation tokens propagate through waits, execution attempts, reasoning waits, Runtime request boundaries, and any owned local subprocess/sandbox work.
- Deadline: deadlines use an injected/testable clock; expiry is checked **before every next mutation** and during reconciliation/retrieval/validation waits.
- Cancel-during-wait prevents the next mutation; expired deadline prevents the next mutation; terminal attempts release the lease; no orphan lease on cancel/expire paths.
- Restart: restart re-reads the durable ledger (T7); prior attempts remain inspectable; task semantics version binds restart behavior.

## T6 — Per-device lease semantics (lease)

Decision (owned by `agent/coordinator.py`):

- Exactly one trusted execution owner holds the mutation lease per device at a time; second concurrent acquisition fails closed.
- Lease covers mutation-affecting paths only (observation/validation reads do not require it).
- Lease release on: terminal attempt, cancellation, deadline expiry, coordinator close. Shutdown releases only owned resources; Runtime remains sole device authority.

## T7 — Smallest local durable ledger + crash-consistency (restart)

Decision:

- Standard-library SQLite (single file, WAL-safe usage) OR append-only JSONL ledger — Phase B author picks whichever proves atomic attempt append + restart inspection + schema/version safety + bounded cleanup with less code. **No database server, no pg-boss, no external queue.**
- Rules frozen: atomic attempt-history append (a torn write never invents a phantom success); schema version column; `ExecutionSpec` version binds interpretation on restart; bounded cleanup (TTL/count cap) never deletes non-terminal history silently; ledger files are never committed (test ledgers live in temp dirs).

## T8 — Experience episode schema + privacy policy (Experience)

Decision (owned by `knowledge/experience.py`):

- Domain-neutral `Observation / Action / Transition / Outcome / revision` episode with Execution/Attempt identity, provenance, result/evidence links, timestamps + schema version where durability requires them.
- Privacy: no raw screenshots, screen text, action payloads, credentials, identifiers, or conversation text in durable records — opaque refs/counters/hashes only.
- Bounded serialization; deterministic round-trip + compatibility tests; Experience is evidence, never auto-promoted truth.

## T9 — Knowledge lifecycle, evidence/provenance, conflict + supersession (Knowledge)

Decision (owned by `knowledge/hygiene.py` + `knowledge/promotion.py`):

- Lifecycle: `raw → normalized → candidate → conflict_checked → verified → promoted`, with `superseded / disproved / rejected-insufficient-evidence`.
- Hygiene: mojibake detection/normalization-or-reject; duplicate + conflict detection before promotion; explicit supersession with history/provenance retained; **remove the obsolete "one failed recovery loop ⇒ universal terminal rule"** — failures scope to state/control context.
- Promotion: evidence aggregation (not one opaque score); conflicts block/branch, never silent overwrite; Teaching splits policy/instruction vs factual assertion; no semantic score promotes; hot-path mutation never blocks on expensive learning analysis; one observed failure never becomes a universal terminal rule.

## T10 — Model-neutral ReasoningRoute / escalation record (route)

Decision (owned by `agent/reasoning.py`):

- Tiers frozen: `deterministic / lightweight / heavy`. Production interface carries no provider/model names.
- Triggers (minimum): unknown state; conflict with promoted Knowledge; repeated unexplained failure; low confidence near side-effect boundary; unexplained post-action transition; Teaching contradicting Knowledge.
- Every route records tier + machine-readable reason + latency + outcome. Heavy reasoning is never the default for known/high-confidence work. R6 accepts fake/stub reasoners; no external LLM in deterministic tests.

## T11 — World State / recovery-transition abstraction, no domain taxonomy (World · recovery · recovery-loop suppression)

Decision (owned by `agent/recovery.py`):

- `WorldState { state_key, revision, confidence, observed_at }` + `RecoveryTransition { from_state, to_state, reversibility, risk_class, allowed, compensation }` — domain-neutral; core freezes no game/app taxonomy (adapters supply type values as data in R10+).
- Agent task-state recovery loop (distinct from Runtime transport `recover()`): off-goal? → classify → retrieve by **current state** → choose bounded reversible/allowed → execute revision-safe → validate → anchor-or-escalate.
- Escalation order: deterministic → lightweight → heavy → human/physical gate. Paid/irreversible/security-sensitive/disallowed transitions fail closed.
- **Recovery-loop suppression**: visited `(state, transition)` pairs with ineffective outcomes are suppressed with a bound; repeated ineffective loops escalate instead of cycling; successful episodes feed Experience (later Promotion); no macro/Skill promotion in R6.

## T12 — Retrieval interfaces + canonical identity rules (retrieval · semantic optionality)

Decision (owned by `retrieval/store.py`, `retrieval/graph.py`, `retrieval/semantic.py`, `retrieval/feedback.py`):

- Order frozen: exact canonical ID/key → deterministic active-state/lifecycle filter → deterministic lexical/key ranking with stable ties → (optional) semantic rerank.
- Default action-authority retrieval **excludes** candidate/superseded/disproved/non-active items; audit/history mode is explicit opt-in.
- Typed graph: domain-neutral nodes/edges, bounded depth/node count, cycle-safe, lifecycle filtering during expansion, deterministic ranking, provenance + canonical IDs retained.
- **Semantic optionality**: the seam exists and is testable, but production semantic retrieval ships **disabled** unless a measured deterministic miss class justifies enabling; no vector DB / embedding dependency in R6/R7; semantic candidates resolve to canonical IDs, never directly promote truth, never bypass lifecycle filters; deterministic/exact evidence outranks or rejects semantic candidates; provider failure degrades safely to deterministic.

## T13 — Post-action validation signal hierarchy (validation · revision binding · no blind replay · preemption context)

Decision (owned by `retrieval/validator.py` + `retrieval/reconcile.py`):

- Ladder (cheapest sufficient first): ExecutionResult/effect semantics → Execution/Attempt expectations + causal invariants → privacy-safe status/trace signals → cheap deterministic state evidence → fresh full `observe()` → reasoning/human escalation.
- Frozen rules: cheap validation **never manufactures a Runtime revision** (revision binding); after a mutation invalidates the revision, the next revision-bound/state-sensitive action requires fresh `observe()`; `EFFECT_UNKNOWN`/partial/mismatch/low-confidence/security-or-irreversibility forces full reconciliation/escalation (no blind replay); validator feedback may inform policy later but never bypasses fixed gates in one shot; decisions traceable by method/confidence/reason/latency-cost-class/outcome.
- `reconcile.py`: stale plan/revision invalidates continuation; rollback only on known allowed reversible compensation, else re-observe/retrieve/replan/escalate; cancellation/deadline respected during reconciliation.

## T14 — Dependency guards (guard scaffold)

Decision:

- New minimal guard scaffold `scripts/check_agent_boundaries.py` (+ regression test that plants a prohibited import in a temp tree and asserts fail-closed) proving:
  - `agent*` / `knowledge*` / `retrieval*` do not import `pymobiledevice3`, WDA/CoreDevice/AppService/usbmux, Phone Harness, subprocess/MCP-as-internal-Runtime-bridge;
  - trusted mutation enters only through the accepted Runtime seam;
  - no domain package/name in generic core.
- Existing `scripts/check_provenance.py` remains mandatory. Both run in every integration phase.

## T15 — Deterministic fixture matrix + bounded real-device gate (deterministic matrices · device gate)

Decision — deterministic matrices (synthetic, privacy-safe, machine-readable where practical):

R6 (13): `R6-A01, R6-A02, R6-B01, R6-C01, R6-D01, R6-E01, R6-F01…F05, R6-G01…G03` per handoff §9.
R7 (12): `R7-01…R7-12` per handoff §9 (active-filter, graph bounds, semantic seam/fallback, feedback/decay, stale + EFFECT_UNKNOWN reconciliation, rollback-vs-escalate, cheap-check sufficiency/mismatch, revision-invalidated next-observe, cancel/deadline during retrieval/validation, end-to-end linkage).

- **Device gate**: one bounded single-lane matrix on safe reversible system-app context (Home/Settings) proving the 10 handoff §11 cells (lease → revision-fed mutation → Runtime-only send → revision invalidation → fresh-observe-before-next → evidence linkage → bounded recovery to anchor → cancel/deadline without orphan lease → no blind replay → clean shutdown). Never manufacture dangerous ambiguity or physical disconnect for the gate — fixtures own ambiguity semantics. If no iPhone is attached, retain the exact physical blocker and do not claim 100%.

## T16 — Exact file ownership for parallel lanes

Decision — non-overlapping ownership; shared-schema writes serialize through Phase B:

| Lane | Files owned | Must not touch |
|---|---|---|
| B shared contracts + guard scaffold | record dataclasses across `agent/*`, `knowledge/*`, `retrieval/*` (schema only), `tests/fakes.py` (FakeRuntime), `scripts/check_agent_boundaries.py` scaffold, matrix skeleton | production logic beyond schema/fakes |
| C1 authority/execution (R6-A,E,F,G) | `agent/arbiter.py`, `agent/reasoning.py`, `agent/coordinator.py`, `agent/recovery.py` | `knowledge/*`, `retrieval/*` |
| C2 experience/knowledge (R6-B,C,D) | `knowledge/experience.py`, `knowledge/hygiene.py`, `knowledge/promotion.py` | `agent/*`, `retrieval/*` |
| E1 retrieval/graph/semantic/feedback (R7-01…04) | `retrieval/store.py`, `retrieval/graph.py`, `retrieval/semantic.py`, `retrieval/feedback.py` | `retrieval/validator.py`, `retrieval/reconcile.py`, `agent/*` |
| E2 reconciliation/validator (R7-05/06) | `retrieval/reconcile.py`, `retrieval/validator.py` | E1 files except via frozen records |
| Reviews/repairs | smallest diff in the owning lane's files only | cross-lane refactors without freeze amendment |

Max two concurrent code-author lanes; device mutation always single-lane.

---

## Cross-cutting frozen rules (consolidated)

- **Revision binding**: no raw non-revision-bound tap/swipe/type envelope; every mutation consumes a current revision; successful mutation invalidates it; cheap validation never creates one.
- **No blind replay**: `EFFECT_UNKNOWN`/failed/partial effects are retained with `retry_safe=False`, zero auto-replay; continuation requires reconciliation.
- **Preemption**: arbiter preempts only at safe boundaries; accepted interrupts invalidate stale plans; Teaching is one event type with explicit reasons, never unconditional top priority; urgent-but-unsafe never bypasses gates.
- **Recovery-loop suppression**: ineffective `(state, transition)` cycles are bounded and escalate; failures stay scoped, never universal terminal rules.
- **Semantic optionality**: seam testable, production disabled by default; no vector DB unless a measured miss class justifies it.
- **Device gate**: deterministic-first; one bounded single-lane hardware proof; honest blocker if no device.
- **R4/R5 untouched**: Runtime six-operation boundary, pinned upstream, 146/146 + 29/29 baselines, provenance guard, and separation (0 Phone Harness edges) are regression gates, not editing targets.

## What this freeze does not do

- Implements nothing; starts no R8/R9/R10 or Visual work; adds no scheduler, PostgreSQL/pg-boss, plugin host, vector DB, or process-per-concept split.
- Changes no R4/R5 source, tests, or evidence.
- Performs no remote push.

## Next step

Phase B author establishes the shared records + FakeRuntime + guard scaffold + matrix skeleton from this freeze, then requests the independent shared-contract review before lanes C1/C2 open.
