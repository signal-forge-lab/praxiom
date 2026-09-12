# R10 independent-review repair record — 2026-09-09

## Scope

This record addresses the independent R0–R10 review findings without reopening
accepted R0–R9 design or adding new product scope. The review found no current
Runtime/Agent/Skill safety break. Repairs are limited to R10 acceptance,
provenance, and evidence accuracy.

## Finding disposition

### R10-CERT-001 — certification retention

The independent review correctly observed that the repository still said
`runtime Goal Certification pending`, but its stronger claim that certification
had not completed was incomplete. Durable DSH state contains the completed
pre-review certification run:

```text
run-e90f257e-6c9c-4ed8-bdf6-6f1d6df758eb
status = completed
initial Goal Reviewer = approved
final Goal Reviewer = approved
findings = []
blockers = []
Final Judge = pass
unresolved = []
```

That run certified source HEAD `6a4bf06`. Because this independent-review
repair changes the R10 domain declarations/evidence, the old run is retained as
historical proof only. A fresh runtime-owned certification is required after
this repair commit before current R10 status returns to `CERTIFIED`.

### R10-PERF-002 — F4 performance evidence

The review finding is valid. The old R10 acceptance package quoted R9 baseline
numbers that are not supported by the cited R9 acceptance record.

Authoritative retained R9 deterministic baseline from
`docs/evidence/20260907_r9-acceptance.md`:

```text
execute: median 14 ms, p90 16 ms, 10 samples
observe: median 43 ms, p90 45 ms, 5 samples
default execute max-latency budget: 500 ms
```

R10 non-regression is re-established on the same evidence model:

1. `git diff --name-only ff0ab7f..6a4bf06 --` over
   `src/praxiom/{ios_runtime,agent,skill,adaptive,knowledge,retrieval}` is empty.
   The accepted R9 execute/observe hot path was not modified by R10.
2. The only R10 production source added before this review was
   `src/praxiom/domain/**`. The review repair continues to change only that
   domain package; it does not add an execution wrapper or alternate device
   path.
3. `behavior_to_candidate()` is a pure, one-time pre-activation mapping. After
   mapping, execution uses the unchanged R8/R9 `SkillExecutor ->
   ExecutionCoordinator -> Runtime` path. Therefore its cost is not inserted
   into every Runtime `execute` or `observe` operation.
4. Fresh mapping benchmark in the certified `.venv`, seven current accepted
   domain behaviors, `timeit.repeat(..., repeat=9, number=10000)`:

```text
median for mapping all 7 behaviors = 0.036470 ms
p90 for mapping all 7 behaviors    = 0.037701 ms
median per behavior                = 0.005210 ms
```

5. `test_r10_a6_r9_budgets_independent_and_fallback_safe_over_domain_kinds`
   remains green and proves a budget breach disables optimization only for that
   kind and returns to `r7-safe-baseline` with re-observation enabled.

This closes F4 without inventing a new live-device performance number. The R9
baseline itself is a retained deterministic telemetry fixture, so comparing it
to unrelated physical wall-clock timings would be a category error. Physical
R10 live timings remain useful operational evidence, but are not substituted
for the frozen R9 deterministic baseline.

### R10-PROV-003 — per-behavior migration provenance

Valid finding. Roadmap/freeze documents were being used as if they were direct
domain evidence. The root correction is recorded in
`docs/evidence/20260909_r10-domain-provenance-repair.md`.

Current runnable migrated set:

```text
Merge Boss (5)
  mergeboss:launch
  mergeboss:open-level-board
  mergeboss:spawn-generator-item
  mergeboss:merge-board-items
  mergeboss:deliver-customer-order

GoGoMatch (2)
  gogomatch:launch-game
  gogomatch:swap-tiles
```

Previously declared but unsupported purchase/cooldown/booster/reward/level-flow
contracts are now `deferred` and have no runnable `behavior_id`. This is
fail-closed evidence correction, not feature removal: the R10 freeze only
authorizes behavior supported by accepted current/historical evidence.

### R10-DOC-004 — duplicate evidence

Accepted as non-blocking documentation debt. No historical evidence file is
deleted or rewritten merely to remove duplication. Current authority is the
dated evidence chain referenced by `docs/STATUS.md`; undated aliases are
historical lane artifacts and must not override dated successor evidence.

### R4-COV-005

Informational only. No repair is required; the R4 environment-not-exercised
cells were honestly retained and deterministic effect semantics remain green.

## Fresh verification after repair

Before the final certification rerun, the repair was verified with:

```text
targeted R10 migration/provenance tests: 35/35 PASS
full deterministic suite:               359/359 PASS
```

Final provenance/boundary/compile/diff gates and runtime-owned certification are
recorded at repair close.
