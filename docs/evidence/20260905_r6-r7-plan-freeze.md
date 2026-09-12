# R6 + R7 Plan Freeze — Safe Agent Foundation (retained implementation authority)

- Date: 2026-09-05
- Authority: `docs/design/20260905_r6-r7_safe-agent-foundation_orchestrator_handoff.md` (primary),
  `docs/design/20260905_r6-r7_safe-agent-foundation_orchestrator_prompt.md`
- Baseline: R5 COMPLETE, Native iOS Runtime six-operation boundary intact
  (`status`, `observe`, `execute`, `invalidate`, `recover`, `close`)
- Sensitivity: **PUBLIC**
- Status: **PLAN FROZEN** — contracts below are stable for R6/R7 production edits
- Pre-freeze verification (repo root, repo venv):
  - `.venv\Scripts\python -m pytest -q` → 145 passed + 1 environmental `tmp_path`
    sandbox error (pre-existing, unrelated to production code)
  - `.venv\Scripts\python scripts\check_provenance.py` → PASS (exit 0)

All fixtures/evidence in this Goal are synthetic and privacy-safe. No raw screen
text, screenshots, action payloads, credentials, identifiers, or conversation
text is committed.

## 1. Module boundaries (frozen)

```text
src/praxiom/ios_runtime/   device authority (unchanged, six ops only)
src/praxiom/agent/         arbiter.py, reasoning.py, coordinator.py, recovery.py
src/praxiom/knowledge/     experience.py, hygiene.py, promotion.py
src/praxiom/retrieval/     store.py, graph.py, semantic.py, feedback.py,
                           reconcile.py, validator.py
scripts/check_agent_boundaries.py   fail-closed architecture guard
tests/test_r6_agent.py              R6 scenario matrix (deterministic)
tests/test_r7_retrieval.py          R7 scenario matrix (deterministic)
tests/test_agent_boundaries.py      guard regression (fail-closed)
```

Reasons: deep modules first; no process-per-layer, no DB server/queue/
scheduler, no vector DB, no R8+ scope. Agent/Knowledge/Retrieval depend only
on the Runtime seam (injected port mirroring the six operations), never on
device internals.

## 2. Shared value contracts (frozen)

- `ExecutionSpec`: frozen dataclass (`namespace`, `owner`, `task_type`,
  `task_version: int >= 1`, `payload: Mapping` limited to revision-bound
  device intents `{op, ref?, point?, text?, bundle_id?}`, `revision`,
  `deadline_ms?`, `spec_version=1`). Rejects raw non-revision-bound
  `tap/swipe/type` envelopes and invalid version/payload before execution.
- `Execution`: (`execution_id` stable `exe-<counter>`, `spec`, `state`
  created/running/cancelled/expired/succeeded/failed/unknown, `attempt_ids`).
- `Attempt`: (`attempt_id` `att-<counter>`, `execution_id`, `state`,
  `effect NONE|PARTIAL|UNKNOWN`, `evidence: dict`, no blind replay).
- `InterruptEvent`: (`event_id`, `kind` goal/teaching/operator/deadline/risk,
  `priority 0..100`, `reversibility`, `risk`, `deadline_ms?`,
  `safe_boundary_only bool`, `payload_summary` — never raw private payload).
- `ArbitrationResult`: (`selected_id`, `deferred_ids`, `rejected_ids`,
  `reasons: {id: reason}`, `stale_plan_invalidated bool`, deterministic ties
  by `(priority desc, event_id asc)`).
- `ReasoningRoute`: (`tier deterministic|lightweight|heavy`, `reason`,
  `latency_ms`, `outcome?`). No provider/model names in production interface.
- `ExperienceEpisode`: (`episode_id`, `execution_id?`, `attempt_id?`,
  `revision?`, `transition`, `outcome`, `provenance`, `schema_version=1`,
  `captured_at`). Bounded JSON; no screenshot/action payload.
- `KnowledgeRecord`: (`kid` canonical `k-<slug>`, `claim`, `state`
  raw|normalized|candidate|conflict_checked|verified|promoted|superseded|
  disproved|rejected`, `provenance: [source]`, `evidence: {supports, contradicts}`,
  `teaching_kind policy|fact|none`, `reliability 0..1`, `last_used_ts?`,
  `supersedes?`). Lifecycle filters authoritative over ranking.
- `WorldState`: (`anchor_id`, `state_id`, `revision?`, `labels: frozenset`).
- `RecoveryTransition`: (`transition_id`, `from_state`, `to_state`,
  `reversible bool`, `allowed bool`, `risk high|low`, `uses_runtime bool`).
- `RetrievalHit`: (`kid`, `score`, `source exact|lexical|graph|semantic`,
  `snippet_hash` — never raw claim text in traces).
- `ValidationDecision`: (`method cheap-causal|full-observe|escalate`,
  `sufficient bool`, `confidence 0..1`, `reason`, `cost cheap|expensive`,
  `creates_revision False always for cheap`).

## 3. Runtime dependency direction / test seam

- Direction: `agent/coordinator/recovery/validator` → injected Runtime port
  (`observe()`, `execute(actions, expected_revision)`, `invalidate()`,
  `recover()`, `status()`, `close()`). The port mirrors the six operations.
- Native `NativeIosRuntime` is the only production device authority.
- Deterministic tests inject `FakeRuntime` (defined once in
  `src/praxiom/agent/coordinator.py` as `FakeRuntime`, reused by retrieval
  tests via import) — in-memory revision counter, programmable outcomes,
  zero hardware.
- No `pymobiledevice3`, WDA/CoreDevice/AppService/usbmux, transport
  internals, child-process bridge, internal MCP chain, or historical product
  source in Agent/Knowledge/Retrieval.

## 4. ExecutionSpec / Execution / Attempt lifecycle

```text
validate spec -> create Execution(created) -> acquire lease -> Attempt(running)
  -> runtime execute -> record outcome -> release lease -> Execution terminal
```

- Lease: one `DeviceLease(owner, device_id)` per device; second concurrent
  acquire raises `LeaseBusyError` (no queue).
- Cancellation token (`Cancelled` flag) and absolute `deadline_ms` clock are
  checked before every mutation; expired/cancelled prevents the next mutation
  and marks Execution cancelled/expired.
- Ledger: stdlib `sqlite3` file `ledger.db` (WAL off, single table, atomic
  per-attempt insert); restart re-opens read-only inspection without changing
  task semantics. Bounded cleanup `pragma`/delete keeps ≤1000 rows.
- Failed/unknown effects retained in Attempt evidence; never auto-replayed.

## 5. Cancellation / deadline semantics

Injected monotonic clock `now_ms()`. Checks at: spec validation, lease
acquire, before each attempt, inside reconciliation/validation loops. A set
cancel flag or `now >= deadline` raises `CancelledError`/`DeadlineError`
before any device call and releases the lease.

## 6. Lease semantics

`DeviceLeaseManager.acquire(device_id, owner)` — reentrant by same owner is
rejected (explicit release required); terminal attempt always releases in
`finally`. Shutdown releases only owned leases; Runtime authority untouched.

## 7. Durable ledger + crash consistency

One SQLite file under caller-chosen dir (tests use workspace-local dirs, never
`tmp_path`). Schema `attempts(attempt_id PK, execution_id, spec_hash,
state, effect, evidence_json, ts)`. Writes are single-statement atomic;
restart inspection = `SELECT` by execution id. No server, no queue.

## 8. Experience episode schema + privacy

Frozen fields in §2. `to_json/from_json` round-trip tested; `redact()` drops
any accidental `raw_*` keys. Size bound 8 KiB per episode enforced.

## 9. Knowledge lifecycle / provenance / conflicts

Pipeline: `raw → normalized → candidate → conflict_checked → verified →
promoted`, alternatives `superseded|disproved|rejected`. Mojibake detection
via replacement-character/lone-surrogate rate; normalization NFKC+strip.
Duplicates by normalized-claim hash; conflicts by `conflicts_with` key pairs
block promotion (branch, never silent overwrite). One failed recovery loop
never becomes universal terminal rule (scoped evidence only). Teaching:
`teaching_kind policy` routes to instruction store (never fact-promoted);
`fact` requires corroborating evidence count ≥ 2.

## 10. ReasoningRoute / escalation record

`route(signals)`: default deterministic; escalate to lightweight on unknown
state / conflict / low confidence near side-effect boundary / unexplained
transition / teaching-vs-knowledge; heavy on repeated unexplained failure or
security boundary. Records tier+reason+latency always.

## 11. World State / recovery seam

`WorldState` labels are domain-neutral (`anchor`, `off-goal:*`,
`risk:*`). `RecoveryPlanner.plan(goal, world, transitions)` filters by
`from_state`, prefers reversible+allowed+low-risk, suppresses
`(state, transition)` repeats via `seen` set (loop bound = len(transitions)),
escalates on paid/irreversible/disallowed/unknown. Successful episodes feed
Experience via caller.

## 12. Retrieval interfaces + identity

`KnowledgeStore` owns canonical IDs. `retrieve(query, mode action|audit)`:
exact ID → lexical token overlap → stable tie `(score desc, kid asc)`,
action mode excludes non-`promoted|verified` unless audit requested. Bounded
`top_k` (default 5). Graph `expand(kid, depth≤3, budget≤50)` cycle-safe BFS
with lifecycle filter. Semantic seam `SemanticAdapter` disabled by default
(`enabled=False`); test adapter resolves canonical IDs; provider failure
falls back to deterministic.

## 13. Validation signal hierarchy

`AdaptiveValidator.decide(context)`: `EFFECT_UNKNOWN`/partial/mismatch/low
confidence/high-risk → `full-observe`; sufficient cheap causal postcondition
(`expected_anchor in observed_labels`, no risk flags) → `cheap-causal`
(deferred observe, creates no revision); else `escalate`. Cheap never creates
a revision; next state-sensitive mutation still needs fresh `observe()`.

## 14. Dependency guards

`scripts/check_agent_boundaries.py` scans `src/praxiom/agent`,
`src/praxiom/knowledge`, `src/praxiom/retrieval` for banned tokens
(`pymobiledevice3`, `phone[_- ]?harness`, `wda`, `coredevice`, `appservice`,
`usbmux`, `transport.impl`, child-process bridge, internal chain hop) and
asserts mutation only via the Runtime seam (`expected_revision`, `observe(`,
`execute(`). Regression test plants violations in workspace-local dirs and
asserts fail-closed (exit 1), plus clean-tree PASS.

## 15. Fixture matrix + device gate

Deterministic matrices: R6-A01..G03 (13), R7-01..12 (12) — see handoff §9
mapping in `tests/test_r6_agent.py` / `tests/test_r7_retrieval.py`. Bounded
single-lane device matrix (Home/Settings only) deferred to Phase G with
`FakeRuntime`-proven semantics; physical run retained as evidence or one
precise blocker.

## 16. File ownership for parallel lanes

- Lane C1 owns `agent/arbiter.py`, `agent/reasoning.py`,
  `agent/coordinator.py`, `agent/recovery.py`.
- Lane C2 owns `knowledge/*.py`.
- Lane E1 owns `retrieval/store.py`, `graph.py`, `semantic.py`,
  `feedback.py`.
- Lane E2 owns `retrieval/reconcile.py`, `validator.py`.
- Shared contracts frozen here; lanes do not rename fields.

*End of freeze — implementation must conform; deviations need a freeze
amendment with reason.*
