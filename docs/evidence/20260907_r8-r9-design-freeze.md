# R8+R9 Adaptive Skill Platform — Design Freeze (2026-09-07)

- Sensitivity: PUBLIC
- Owner: parent orchestrator (single design owner)
- Baseline: HEAD `4dc3547` — R6 44/44 + R7 31/31 formally certified; 211 passed; provenance + boundary guards PASS; six Runtime ops intact.
- Freeze date: 2026-09-07. Contracts below are frozen before parallel production edits.

## 1. File ownership (parallel lanes)

- Lane 1 (R8 schema/lifecycle): `src/praxiom/skill/need.py`, `candidate.py`, `lifecycle.py`
- Lane 2 (R8 validator/sandbox negatives): `src/praxiom/skill/gates.py`, `sandbox.py`, `tests/test_r8_skill.py` (negatives)
- Lane 3 (R8 reuse + Coordinator): `src/praxiom/skill/reuse.py`, `executor.py`
- Lane 4 (R9 telemetry/baseline, preparatory): `src/praxiom/adaptive/telemetry.py`, `fallback.py`
- Lane 5 (fixtures/guards): `tests/test_r9_adaptive.py` fixtures, `scripts/check_agent_boundaries.py` (add skill/adaptive), `src/praxiom/skill/__init__.py`, `src/praxiom/adaptive/__init__.py`
- Post-R8-acceptance R9 lanes: `src/praxiom/adaptive/dag.py`, `batching.py`, `learning.py`, `temporal.py`, `observation.py`, `routing.py`, `feedback.py`

No other files may be touched by R8/R9 lanes except docs/evidence records and the two test files above.

## 2. Capability-need record (R8-A)

```python
@dataclass(frozen=True) CapabilityNeed:
  need_id: str          # need-<uuid4hex>
  summary: str          # domain-neutral, <=280 chars, non-empty
  evidence_ids: tuple[str,...]  # >=2 distinct Goal/Execution/Experience ids
  gap_kind: str         # "missing-capability" only after detector proves it
  observed_failures: int  # >=3 repeated, distinct revisions
  created_at: int       # injected ms clock
```

Rules: detector requires >=3 failures across >=2 revisions with same normalized signature;
one-off failure or stale-state signature never yields a need; model confidence/frequency
alone never yields a need; every need links evidence ids.

## 3. Skill candidate / active Skill contracts (R8-B)

```python
@dataclass(frozen=True) SkillCandidate:
  skill_id, version: int>=1, inputs/outputs: tuple[str,...],
  preconditions/postconditions: tuple[str,...],
  risk: "low"|"medium"|"high", reversibility: "reversible"|"compensable"|"irreversible",
  authority: frozenset[str]  # subset of RUNTIME_OPS only
  provenance: tuple[str,...], lifecycle: "candidate"
  code_ref: str|None  # untrusted until gates pass; never a transport path

@dataclass(frozen=True) ActiveSkill: same + lifecycle "active", gated_by: tuple[str,...], confidence: float
```

- `RUNTIME_OPS = {tap_point,tap_element,drag,swipe,type_text,home,launch_app}` (mirrors coordinator ALLOWED_OPS; no new Runtime public op).
- No domain taxonomy tokens in generic core (`gogomatch`, `merge boss` rejected by guard).
- No raw device bypass fields (`raw_tap`, `raw_swipe`, `wda`, `usbmux`, `pymobiledevice3`, `phone_harness`, `subprocess`, `mcp`) — gates reject.

## 4. Skill Gates (R8-C)

Ordered gates, all must pass: `schema → authority → privacy → dependency → revision → safety → sandbox-readiness`.
- schema: version>=1, non-empty inputs/pre/post, risk/reversibility enum.
- authority: authority ⊆ RUNTIME_OPS; irreversible+high-risk requires explicit `human-gate` flag (else reject).
- privacy: no credential/label/text payload words (`password`, `token`, `label:`, `screen-text`); code_ref must not contain banned substrings.
- dependency: banned imports/edges rejected (pymobiledevice3, wda, coredevice, appservice, usbmux, phone_harness, subprocess, mcp, transport internals).
- revision: preconditions must include `revision-bound` token; postconditions non-empty.
- safety: stale-revision assumption rejected; unsupported Runtime op rejected.
- Generated candidates are `untrusted` until ALL gates pass; one success never promotes.

## 5. Sandbox contract (R8-D)

```python
@dataclass(frozen=True) SandboxPolicy:
  allow_network=False, allow_filesystem=False, allow_credentials=False,
  allow_device=False, max_steps>=1, deadline_ms>=1, cancellable=True
@dataclass(frozen=True) SandboxResult: ok, steps_used, timed_out, cancelled, detail
```

- Same-host, in-process, pure-function sandbox: candidate step fn `(state, budget) -> (effect, new_state)` with step/deadline/cancel bounds.
- Only plain functions whose code/globals/closures/defaults pass the static pure-data gate may execute. Dunder/dynamic-import/eval/exec/open/socket/banned-edge symbols and unsafe object/module captures fail closed before step 1.
- No credential inheritance, no fs/network/device syscalls (static callable gate + runtime policy flags).
- Device mutation only via `SkillExecutor -> ExecutionCoordinator.run(spec with expected_revision) -> Runtime.execute`; sandbox itself makes zero device calls.
- Deadline/cancellation/resource checks also preempt **during** generated-step execution: a real monotonic wall-clock deadline is enforced independently of the injectable logical clock, with line-event fallback plus opcode tracing and a hard trace-event budget. Unsafe exception handlers, nested code, generator/await control flow, attribute/method access, external mutation, unsafe formatting/high-amplification operations, oversized/non-finite values, mutable host captures, and non-exact built-in data subclasses fail closed. Formatting rejection is version-robust across supported CPython 3.12–3.14 by denying the `FORMAT_*` opcode family (`FORMAT_VALUE`, `FORMAT_SIMPLE`, `FORMAT_WITH_SPEC`) before execution. Caller state is deep-cloned before generated code receives it, so host-owned mutable memory is not shared.

## 6. Reuse / no-blind-replay (R8-E)

`reuse_decision(procedure, current_revision, current_ts, knowledge_state)` returns
`reuse | reobserve | reject`:
- reuse only when: procedure effect==NONE, revision matches current, preconditions subset of current facts, knowledge lifecycle in {verified,promoted}, not expired, not superseded/revoked.
- PARTIAL/UNKNOWN/unrecognized effect → never reuse, never auto-retry/macro; returns `reobserve`.
- Stale revision → `reobserve` even if compensable.
- Retains Execution/Attempt/Experience linkage ids in decision evidence.

## 7. Lifecycle / confidence / provenance (R8-F)

States: `candidate → validated → active → degraded → superseded | revoked`. Terminal: superseded/revoked.
- `candidate→validated` requires all gates pass plus ≥2 distinct evidence ids.
- `validated→active` requires ≥2 successful sandboxed episodes recorded on distinct revisions (one success or repeated success on one revision never promotes).
- `active→degraded` on contradiction/failure signal; `→superseded` only to higher version; `→revoked` on safety violation; revoked never reactivates.
- Confidence ∈[0,1] affects selection evidence only; never bypasses gates/lifecycle.
- Provenance: every transition appends `(from,to,reason,evidence_id)`; rollback path explicit.
- Executable `ActiveSkill` instances are issued only by `SkillRegistry.activate`, which re-runs all Skill Gates and verifies registry-owned lifecycle identity, ≥2 distinct validation evidence ids, and ≥2 distinct per-revision success evidence ids. Directly constructed/forged `ActiveSkill` objects are non-executable.
- Execution authority is retained in a registry-owned policy snapshot rather than caller-visible `ActiveSkill` fields. Human-gated execution additionally requires a one-shot approval minted only from the configured human-approval authority and bound to the exact Skill/version/current revision/full canonical mutation payload; copied, mutated, replayed, cross-revision, or payload-substituted approvals fail closed.

## 8. Execution direction (R8-D/R9)

`SkillExecutor(coordinator, lease_owner)` is the ONLY Skill→device path:
`ActiveSkill + current_revision → ExecutionSpec(op ∈ RUNTIME_OPS, revision) → coordinator.run → Attempt`.
Agent/Skill/Retrieval/Adaptive code never imports transport, never calls Runtime ops directly
(boundary guard enforces; only `coordinator.py:self._rt.*` seam allowed, execute requires expected_revision).

## 9. R9 telemetry + privacy (preparatory)

```python
@dataclass(frozen=True) TelemetryEvent: kind, latency_ms>=0, ok:bool, ts:int, skill_id|None, revision_invalidated:bool
```
- Privacy-safe aggregation only: counts, sums, buckets; never labels/text/credentials.
- Deterministic injectable clock; aggregation is pure function.
- Baseline: `PerformanceBaseline` retained from R7/R8-safe runs; regression budgets per kind.

## 10. R9 DAG + batching invariants

- DAG nodes carry `deps: frozenset[int]` plus a non-empty revision binding; duplicate ids, self/unknown deps, cycles, missing revisions, and mixed revisions fail closed.
- Bounded parallel planning: `max_width>=1`; state-sensitive nodes serialize and never share a wave with another state-sensitive node.
- Batching: whole-batch preflight first; revision-unbound, non-low-risk, state-sensitive, human-gated, or malformed-confidence work falls back to a single item; batch stops at first PARTIAL/UNKNOWN/STALE_REVISION and requires reconciliation before continuation.

## 10.1 R9 learned reuse authority

- Macro/path learning is evidence-only and consumes a live `SkillTrustToken` from the R8 registry.
- Trusted macro/path evidence requires the same still-active token, all `NONE` effects, and at least two distinct revisions.
- Revocation/degradation/supersession invalidates the token and therefore invalidates learned reuse authority.

## 11. Observation optimization + R7 floor

`ObservationPolicy.decide(..., validator_decision: ValidationDecision, validation_context: ValidationContext | None = None)`:
- Preserves the frozen public R7 `ValidationDecision` input; a caller-supplied boolean cannot stand in for validator authority.
- When an originating `ValidationContext` is supplied, it is strictly validated and re-run through `AdaptiveValidator`; any disagreement with the supplied decision fails closed to `full-observe`.
- Malformed/non-finite context, decision, confidence, risk/reversibility, state-sensitivity, or human-gate signals fail closed rather than becoming optimization authority.
- Any validator decision claiming `creates_revision=True` fails closed to `full-observe`.
- Cheap path is allowed only when the validator decision is sufficient, confidence≥threshold, risk/reversibility stay on the low/reversible floor, and the next action is not state-sensitive after invalidation.
- Otherwise `full-observe`. The R7 validator never creates a revision.

## 12. Temporal model / test clock

`TestClock`/`ManualClock` injectable ms; `Countdown(deadline_ms, now)` returns remaining; expiry fails closed (`reobserve`/deadline error); clock never moves backwards.

## 13. Performance baseline + regression budgets

- `PerformanceBaseline.measure(events)` retains median/p90/sample-count per kind only from valid successful telemetry events. Baselines are factory-issued, immutable to callers, and identity-checked at consumption so direct construction or caller-visible field mutation cannot forge a fast-path sample.
- `RegressionBudget(max_latency_ms, max_observe_rate, min_recovery_rate)`; optimization disabled/fallback independently per kind when budget exceeded.
- Every optimization falls back to R7-safe baseline on telemetry/model/skill-signal failure.

## 14. Scoring rubrics (47+47)

- R8-01..47 and R9-01..47 enumerated in `docs/evidence/20260907_r8-acceptance.md` and `docs/evidence/20260907_r9-acceptance.md`; each maps to ≥1 deterministic test assertion in `tests/test_r8_skill.py` / `tests/test_r9_adaptive.py`.
- Combined 94/94 + full suite + guards green + unresolved=[] + errors=[] + Reviewer approved + Final Judge PASS = Goal complete.

## 15. Global boundaries (frozen)

Six Runtime ops unchanged; no Phone Harness/MCP/subprocess/direct-transport edge in src (guard-enforced);
generated code untrusted until gates pass; no blind replay; no stale-revision mutation;
perf falls back to safe baseline; no R10; no Visual V0-V3; no remote push.
