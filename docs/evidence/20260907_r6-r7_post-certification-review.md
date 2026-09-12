# Praxiom R6 + R7 Post-Certification Review — 2026-09-07

- Sensitivity: PUBLIC
- Scope: R6/R7 only; no R8+ implementation, no remote push, no device access.
- Baseline reviewed: `295e550` (`main`), previously formally certified 75/75.
- Purpose: independent source-level review before opening the R8+ program.

## Findings repaired

The prior deterministic suite and formal certification were green, but a fresh
source review found six fail-closed gaps not covered by the existing matrix.

1. **Unknown Runtime-port exception classification** — an exception without an
   explicit Runtime effect was defaulted to `NONE`. It is now classified as
   `UNKNOWN`, with revision invalidation retained, because an unexpected
   transport/port failure can occur after a mutation reached the device.
2. **Batch continuation after ambiguous effect** — `run_batch()` could continue
   to a later mutation after `PARTIAL`/`UNKNOWN` or an unexpected port failure.
   It now terminates the batch until reconciliation/fresh observation.
3. **Semantic rerank disturbed deterministic authority order** — semantic
   reranking re-sorted exact/lexical results by ID, which could move an exact
   canonical hit below a lexical hit. It now preserves deterministic retrieval
   order and appends only lifecycle-valid semantic candidates.
4. **Lifecycle-hidden graph root regained influence** — action-mode graph
   expansion could start from a superseded/candidate/disproved root and expose
   active descendants. Action-mode expansion now fails closed for a missing or
   non-action-visible root.
5. **Stale decay was non-idempotent** — evaluating decay repeatedly at the same
   timestamp repeatedly reduced reliability. Decay now tracks the last consumed
   decay interval, preserving deterministic same-time evaluation and fractional
   age carry.
6. **Unknown future/malformed effect values could pass cheap paths** — R7
   reconciliation/validation only special-cased literal `UNKNOWN`/`PARTIAL`.
   `NONE` is now the only definitive no-error effect; every other effect fails
   closed to reconciliation/full observation.

## Test-contract correction

The tests-only `FakeRuntime` previously represented stale revision as a bare
`ValueError`. It now mirrors the real Runtime contract with structured
`RuntimeOperationError(STALE_REVISION, effect=NONE)`. Existing shared-contract
tests were updated to assert that structured no-effect classification.

## Fresh verification after repair

```text
.venv\Scripts\python.exe -m pytest -q
=> 201 passed

.venv\Scripts\python.exe scripts\check_provenance.py
=> OK: no Phone Harness import/name/dependency in production paths

.venv\Scripts\python.exe scripts\check_agent_boundaries.py
=> OK: agent/knowledge/retrieval respect the Runtime boundary

git diff --check
=> PASS
```

## Current-HEAD Formal audit follow-up

The first current-HEAD certification workflow exposed two orchestration/tooling
limitations (delegated agents have no command runner) and, more importantly,
three additional source-level blockers in the four-repair audit. The source
blockers were repaired before another certification attempt:

1. **Ledger identifier collisions are now correctness-safe, not probabilistic.**
   UUID4 remains the normal ID source, but both Execution and Attempt IDs are
   checked against in-memory and durable history before use. Repeated collisions
   are bounded and fail closed before dispatch. Durable attempt writes no longer
   use destructive `ON CONFLICT ... DO UPDATE` across identities; an existing
   Attempt ID may only be updated when its Execution/spec identity matches.
   Forced-collision regression proves existing successful history is unchanged
   and no new device mutation occurs.
2. **A stale revision stops the entire batch before any later mutation.**
   `STALE_REVISION` is an explicit stop condition even though the Runtime
   correctly classifies its effect as `NONE` and does not invalidate the old
   revision token itself. A stale-first/two-spec regression proves the later
   otherwise-valid mutation is never dispatched (`device_calls == 0`).
3. **Boundary-guard indirection coverage is fail-closed.** Import/call aliases
   are resolved through simple assignment chains, so `builtins.__import__`
   aliases and subprocess callable aliases cannot escape detection. Runtime
   operation calls are no longer accepted based on a small receiver-name hint
   set: only the Coordinator's explicit `self._rt` seam (revision-bound for
   `execute`) and its known SQLite `_db.execute`/`_db.close` calls are allowed.
   Regressions cover dynamic-import alias chains and an unhinted `bridge.execute`
   receiver.

Fresh local verification after these additional repairs:

```text
.venv\Scripts\python.exe -m pytest -q
=> 207 passed

.venv\Scripts\python.exe scripts\check_provenance.py
=> PASS

.venv\Scripts\python.exe scripts\check_agent_boundaries.py
=> PASS

git diff --check
=> PASS
```

The command-capability limitation is not treated as product evidence: final
Formal certification must receive parent-observed current-HEAD/clean-tree/test/
guard results explicitly, while independent child reviewers continue to inspect
source and retained evidence read-only.

## Final review hardening

A final pass over the repaired safety boundaries added two more adversarial
regressions without changing architecture or scope:

- Runtime-operation calls through call-expression receivers such as
  `get_runtime().execute(...)` are rejected outside the Coordinator seam; and
  dynamic import construction through `getattr(builtins, "__import__")` or
  `getattr(importlib, "import_module")` is rejected before it can be aliased.
- Attempt-ID collision handling is forced deterministically in a regression,
  proving repeated collision fails closed before dispatch and preserves the
  existing successful ledger row.
- Runtime methods copied into a bare callable name, including alias chains such
  as `op = bridge.execute; again = op; again(...)`, now retain their resolved
  receiver identity in the AST guard and are rejected outside the direct
  Coordinator Runtime seam.  Focused planted regressions cover both the direct
  callable alias and chained-alias forms.

Fresh final local verification after this review:

```text
.venv\Scripts\python.exe -m pytest -q
=> 207 passed

.venv\Scripts\python.exe scripts\check_provenance.py
=> PASS

.venv\Scripts\python.exe scripts\check_agent_boundaries.py
=> PASS

git diff --check
=> PASS
```

The retained real-device matrix remains historical evidence only; no phone was
accessed during this review. A new Formal DSH certification must evaluate the
repaired committed HEAD before R8+ implementation is treated as open.

## Deep Formal review follow-up

Formal run `run-7b8a96b4-f74a-458e-a05c-090ad153f8d8` independently found four
additional blocking gaps. All code/test-addressable findings were repaired:

1. **Coordinator restart/crash durability** — Execution/Attempt IDs are now
   UUID-backed and collision-free across restart. A `planned` row is committed
   when the attempt is admitted and a `sent` row is committed immediately before
   Runtime dispatch. Reopening a ledger converts any incomplete
   `planned`/`sent`/`running` row to `unknown`, `retry_safe=false`,
   `replayed=false`, `revision_invalidated=true`, with `crash_recovered=true`.
   A regression simulates process death after dispatch without manually seeding
   counters and proves the row cannot be overwritten or replayed.
2. **Stale revision compensation** — stale revision now unconditionally returns
   `reobserve`, even when a reversible compensation is available. Compensation
   can be considered only after current state/revision is known.
3. **Boundary guard completeness** — the guard now parses Python AST, fails on
   subprocess and MCP imports (including aliases), `__import__`,
   `importlib.import_module`, subprocess process-launch calls, suspicious direct
   Runtime-operation receivers outside the Coordinator, and unrevisioned
   Coordinator Runtime `execute`. Regressions plant each prohibited class.
4. **Observed Home-anchor proof** — the live R6/R7 device runner no longer treats
   READY + fresh revision as sufficient. It requires a post-Home Observation
   with privacy-safe launcher-icon structural evidence and records only an icon
   count, never labels/text/values. Synthetic contract tests prove both positive
   and negative cases and prove the evidence string cannot leak a label.

No real-device rerun was performed during this follow-up; the current task did
not authorize new phone mutation. The retained 10/10 device matrix therefore
remains historical evidence, while the repaired runner is ready for the next
explicitly authorized bounded rerun if Formal certification requires fresh
physical evidence.

Fresh verification after these repairs:

```text
.venv\Scripts\python.exe -m pytest -q
=> 204 passed

.venv\Scripts\python.exe scripts\check_provenance.py
=> PASS

.venv\Scripts\python.exe scripts\check_agent_boundaries.py
=> PASS

git diff --check
=> PASS
```

