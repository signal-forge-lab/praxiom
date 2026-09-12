# R10 Lane S — Shared Domain Adapter Seam Implementation Evidence

- Sensitivity: PUBLIC
- Date: 2026-09-08
- Scope: Lane S (Phase C shared seam) only. No MB/GG/E/L/P lane authority claimed; no live device evidence claimed.
- Baseline: HEAD `ff0ab7f1b7bb92975f1e44e2aafabb7f4a1d4e7c` ("docs: retain normalized R10 workflow goal").
- Authority: `docs/evidence/r10-design-freeze.md` (§0–§5, §7, §9 R10-A), retained R8 freeze §3.

## Implemented (Lane-S owned file set, disjoint per freeze §7)

| File | Change |
|---|---|
| `src/praxiom/domain/adapter.py` | New. The entire shared seam: `DomainBehavior` (pure frozen data, exact frozen field set) + `behavior_to_candidate` (one pure mapping function). Zero device calls, zero I/O. Imports only `dataclasses` and `praxiom.skill.candidate` (`RUNTIME_OPS`, `SkillCandidate`) — the frozen seam allowlist. |
| `src/praxiom/domain/__init__.py` | New. Public-surface re-export only (`DomainBehavior`, `behavior_to_candidate`). |
| `tests/test_r10_domain.py` | New. 16 deterministic tests (matrix below). Fixtures are inline, repo-local, synthesized contract data — never recorded device captures. |
| `scripts/check_agent_boundaries.py` | Additive scan-scope gain only: `src/praxiom/domain` in `SCAN_DIRS` (see "Guard change" and flags below). |
| `tests/test_agent_boundaries.py` | New deterministic case `test_boundary_guard_fails_closed_on_domain_file_importing_banned_edge` (freeze §2 requirement). |

Generic core is untouched: `src/praxiom/{ios_runtime,agent,skill,adaptive,knowledge,retrieval}/**` and `pyproject.toml` received zero edits. Runtime public surface remains exactly six operations (asserted, not edited).

## Seam contract (as frozen; mapping decisions recorded)

`behavior_to_candidate(behavior, *, version=1)` is the single fail-closed choke point. It validates every frozen MUST/non-empty/enum rule and raises `ValueError` with machine-oriented kebab reasons otherwise: `<domain>:<kebab-behavior>` id format with domain match, non-empty kebab domain, non-blank summary ≤280, ≥1 source evidence, non-empty inputs/pre/post, `revision-bound` token present in preconditions, risk/reversibility enums, `ops` non-empty `frozenset ⊆ RUNTIME_OPS`, `human_gate=True` forced by `risk=="high"` or `reversibility=="irreversible"`, positive non-boolean version.

Mapping into the R8 `SkillCandidate` (fields the frozen `DomainBehavior` does not carry are derived, never widened):

- `skill_id := behavior_id` (identity preserved for closure mapping)
- `outputs := postconditions` (the observation-verifiable outputs; R8 schema gate requires non-empty outputs)
- `authority := ops` (per-domain authority is exactly the frozen ops subset)
- `provenance := source_evidence`
- `lifecycle="candidate"`, `code_ref=None` (declarative only — no generated code lane)

The result is untrusted until all ordered R8 gates pass and `SkillRegistry.activate` re-runs them; entry to execution remains exclusively candidate → gates → registry → `SkillExecutor.execute` → `ExecutionCoordinator.run(revision)` → `Runtime.execute(actions, expected_revision=...)`. No bypass lane exists or was added.

## Deterministic test matrix (R10-A mapping)

| Point | Proof (tests/test_r10_domain.py unless noted) |
|---|---|
| A1 generic core domain-neutral + guard green | `test_r10_a1_guard_green_with_domain_scan_scope_active` (SCAN_DIRS covers domain pkg; `gogomatch`/`merge boss` tripwire retained; guard run green) |
| A2 no direct transport/device edges | `test_r10_a2_banned_edge_imports_fail_guard_for_domain_files` (regex + AST negatives) and `test_r10_a2_domain_import_allowlist_fail_closed` (every domain file imports only dataclasses/typing/praxiom.skill.candidate) |
| A3 no Phone Harness / MCP authority | `test_r10_a3_provenance_and_authority_guards_green` (`check_provenance.py` + `check_agent_boundaries.py` green; `subprocess`/`mcp` banned roots proven for domain probes in A2 case) |
| A4 revision-bound authority chain only | `test_r10_a4_domain_mutation_only_through_revision_bound_authority_chain` (registry-active skill → executor → coordinator → fake Runtime; stale revision ⇒ `STALE_REVISION`, zero device calls; revoked ⇒ no authority) and `test_r10_a4_domain_package_makes_no_runtime_operation_calls` (AST: no six-operation call site in domain code) |
| A5 lifecycle/human-gate authority | `test_r10_a5_human_gate_forced_by_classification_and_binding_negatives` (gate forced by high/irreversible; missing/replayed/cross-revision approval negatives; exact-approval success) and `test_r10_a5_registry_lifecycle_removes_domain_execution_authority` |
| A6 R9 floors over domain kinds | `test_r10_a6_r9_budgets_independent_and_fallback_safe_over_domain_kinds` (per-kind independence, breach ⇒ fallback, unchanged R9-safe fallback shape) |
| A7 unsupported ops fail closed; six-op surface | `test_r10_a7_unsupported_operations_fail_closed_at_the_seam` (mapping rejects ops outside `RUNTIME_OPS`; executor keeps `op-not-authorized` narrowing) and `test_r10_a7_runtime_public_surface_is_exactly_six_operations` (AST: `NativeIosRuntime` public methods == {status, observe, execute, invalidate, recover, close}; `__all__ == ["NativeIosRuntime"]`) |
| Contract mapping/validation | deterministic-mapping, revision-binding, behavior-id, field-violation, and version tests (`test_r10_adapter_*`) |

## Guard change (freeze §2/§8)

`scripts/check_agent_boundaries.py` gains `src/praxiom/domain` in `SCAN_DIRS`, presence-conditional so the additive line is rollback-safe per freeze §8: `main()` otherwise hard-fails on a missing scan dir, and the frozen rollback drill requires the guard to stay green after the whole domain package is removed ("the scan simply finds nothing"). No other guard logic changed; domain files are thereby subject to the same banned-edge / banned-import-root / dynamic-call checks as skill/adaptive code, and the seam import allowlist (stricter than the guard, per the frozen contract comment) is enforced deterministically in `tests/test_r10_domain.py`.

## Verification record (this working tree)

- `pytest -q` (full suite) with the one environmentally-broken case deselected: **322 passed**, 1 deselected.
- Deselected: `tests/test_package.py::test_check_provenance_detects_phone_harness_reference` — pytest's `tmp_path` fixture is denied the platform temp area under this sandbox (access denied before the test body runs). Proven pre-existing and unrelated: identical single-test error reproduced at HEAD with Lane-S edits stashed via `git stash`; the repo's own `tests/test_agent_boundaries.py` documents this hazard ("Uses workspace-local scratch dirs (never tmp_path) to stay green under the sandbox file policy").
- `pytest tests/test_r10_domain.py tests/test_agent_boundaries.py -q`: **21 passed** (TDD: collection RED before `src/praxiom/domain` existed; mapping/validation negatives confirmed the fail-closed paths).
- `python scripts/check_agent_boundaries.py`: **OK** (domain scan scope active, clean).
- `python scripts/check_provenance.py`: **OK**.
- No remote push; all work is local working-tree changes only.

## Flags recorded for the design owner (not silent deviations; no out-of-row edits made)

1. Domain-leak token collision (future lane D): adding `src/praxiom/domain` to `SCAN_DIRS` extends the `"gogomatch"`/`"merge boss"`/`"r10"` leak-token scan over domain-package contents. The Lane-S seam modules are token-clean (guards green), but the frozen §1 behavior ids require the literal `gogomatch` in the future `src/praxiom/domain/gogomatch.py`, which would trip the leak-token list. Requires a dated §12 amendment (e.g., scope the leak-token scan to the generic-core dirs) before lane D files land.
2. Fixture directories: `tests/fixtures/r10/{mergeboss,gogomatch}/` belong to lanes MB/GG per freeze §7 and were intentionally not created here; Lane-S fixtures are inline synthesized contract data.

## Constraints honored

- Minimal adapter seam only: two new declarative modules; no second mutation path, no plugin host, no new Runtime operation, no convenience widening.
- No direct WDA/CoreDevice/AppService/usbmux/pymobiledevice3 edge above Runtime (guard-extended over `src/praxiom/domain`; negative tests in both boundary and seam suites).
- Six-operation Runtime preserved (asserted from `src/praxiom/ios_runtime/runtime.py` source; zero edits).
- No remote push.

## Lane S status: implementation complete, deterministic matrix green
