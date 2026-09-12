# R10 Lane MB — Merge Boss Domain Migration Implementation Evidence

- Sensitivity: PUBLIC
- Date: 2026-09-08
- Scope: Lane MB (Phase D Merge Boss migration) only. Disjoint ownership from GoGoMatch (Lane GG).
- Baseline: HEAD `ff0ab7f1b7bb92975f1e44e2aafabb7f4a1d4e7c` ("docs: retain normalized R10 workflow goal").
- Authority: `docs/evidence/r10-design-freeze.md` (§0–§5, §7, §9 R10-B), `docs/evidence/r10-seam.md`.

## Implemented (Lane-MB owned file set, disjoint per freeze §7)

| File | Change |
|---|---|
| `src/praxiom/domain/mergeboss.py` | Declarative-only Merge Boss behavior contracts (`DomainBehavior` records) and explicit migration provenance records. Zero device calls, zero I/O. Imports strictly restricted to the frozen seam allowlist (`dataclasses`, `typing`, `praxiom.domain.adapter`, `praxiom.skill.candidate`). |
| `tests/test_r10_mergeboss.py` | 17 deterministic acceptance tests covering all frozen rubric points B1–B6 plus GoGoMatch disjointness. |
| `tests/fixtures/r10/mergeboss/board_fixture.json` | Synthesized board state fixture (grid dimensions, slots, player state, active orders) with zero device payloads or identifiers. |
| `tests/fixtures/r10/mergeboss/scenarios.json` | Synthesized behavior test scenario fixture for deterministic end-to-end execution of all behaviors. |
| `tests/fixtures/r10/mergeboss/migration_spec.json` | Structured provenance specification distinguishing migrated, excluded-legacy-only, and deferred behaviors with exact rationales. |

Generic core is untouched: `src/praxiom/{ios_runtime,agent,skill,adaptive,knowledge,retrieval}/**` and `pyproject.toml` received zero edits. Runtime public surface remains exactly six operations.

## Provenance & Migration Decision Summary

In compliance with the Greenfield rule (`docs/PROVENANCE.md`):
- All 7 migrated behaviors are reimplemented from declarative behavior contracts, not copied from legacy source code.
- No Phone Harness or legacy-domain source files, modules, subprocesses, or hidden execution paths are imported or used.
- Every behavior cites authoritative source evidence:
  - `docs/design/20260907_r8plus_execution_plan.md`
  - `docs/PROVENANCE.md`
- 7 behaviors migrated:
  1. `mergeboss:launch`: low / reversible / human_gate=False / ops={launch_app}
  2. `mergeboss:open-level-board`: low / reversible / human_gate=False / ops={tap_point, tap_element}
  3. `mergeboss:spawn-generator-item`: medium / compensable / human_gate=False / ops={tap_point, tap_element}
  4. `mergeboss:merge-board-items`: medium / compensable / human_gate=False / ops={drag}
  5. `mergeboss:deliver-customer-order`: medium / compensable / human_gate=False / ops={tap_point, tap_element}
  6. `mergeboss:purchase-generator-part`: high / compensable / human_gate=True / ops={tap_point, tap_element}
  7. `mergeboss:speedup-generator-cooldown`: high / irreversible / human_gate=True / ops={tap_point, tap_element}
- Legacy-only behaviors are explicitly excluded with documented rationales:
  - `direct_memory_hack` -> `excluded-legacy-only` (violates greenfield native runtime boundary and execution model)
  - `cloud_sync_override` -> `excluded-legacy-only` (modifying external account/cloud state is prohibited by safety envelope)
  - `auto_purchase_real_money` -> `excluded-legacy-only` (real-money payment/purchase is strictly prohibited by safety envelope)
  - `batch_board_wipe` -> `excluded-legacy-only` (unsafe destructive deletion of user inventory prohibited)
- Deferred behaviors:
  - `cross_game_inventory_exchange` -> `deferred` (requires cross-domain persistent storage outside current scope)

## Deterministic Test Matrix (R10-B Mapping)

| Point | Description | Proof (`tests/test_r10_mergeboss.py`) |
|---|---|---|
| B1 | Explicit behavior/contract mapping and provenance | `test_r10_b1_behaviors_defined_with_valid_contract_and_provenance`, `test_r10_b1_behavior_lookup_and_batch_helpers`, `test_r10_b1_migration_records_distinguish_migrated_excluded_and_deferred`: proves all 7 behaviors map through `behavior_to_candidate`, pass all R8 skill gates (`GATE_ORDER`), have valid contracts, and migration records correctly categorize migrated vs excluded vs deferred. |
| B2 | Deterministic fixtures/tests | `test_r10_b2_fixtures_exist_and_contain_synthesized_data`, `test_r10_b2_scenarios_execute_deterministically_via_fixtures`: verifies synthesized fixtures exist, contain no captured device identifiers/payloads, match code behaviors, and drive complete skill registry activation and execution cycles against `FakeRuntime`. |
| B3 | Precondition/postcondition/revision binding | `test_r10_b3_all_behaviors_have_revision_bound_precondition`, `test_r10_b3_gate_level_validation_passes_for_all_candidates`, `test_r10_b3_execution_requires_fresh_revision_and_rejects_stale_revision`: proves gate-level `revision-bound` precondition presence, successful execution on fresh revision, rejection of stale/foreign revision with `STALE_REVISION` (zero device calls on rejection), and requirement of fresh observation. |
| B4 | Risk/reversibility/human-gate classification per behavior | `test_r10_b4_classification_table_integrity`, `test_r10_b4_human_gate_forced_for_high_risk_and_irreversible`, `test_r10_b4_human_gate_execution_enforcement_and_one_shot_approval`: asserts classification table, enforces fail-closed validation when high-risk/irreversible lacks human gate, proves unapproved execution fails closed, and validates one-shot human approval token bound to exact payload and revision. |
| B5 | No copied legacy production dependency or hidden execution path | `test_r10_b5_mergeboss_module_import_allowlist`, `test_r10_b5_mergeboss_makes_no_runtime_operation_calls`, `test_r10_b5_architecture_and_provenance_guards_pass`, `test_r10_b5_no_leak_tokens_in_mergeboss_module`: proves `check_provenance.py` and `check_agent_boundaries.py` pass, AST verifies import allowlist compliance, and confirms zero direct calls to Runtime operations from domain code. |
| B6 | No blind replay after partial/unknown/stale effect | `test_r10_b6_no_blind_replay_after_effect_unknown_or_failure`: simulates `EFFECT_UNKNOWN` and `PARTIAL` failure modes, proves `retry_safe is False`, proves blind replay fails closed with `STALE_REVISION`, and proves only fresh observation/reconciliation permits continuation. |
| Disjoint | Independence from GoGoMatch | `test_r10_b_disjoint_from_gogomatch`: verifies AST and text of `mergeboss.py` and all fixtures contain zero occurrences of "gogomatch". |

## Verification Record

- `.venv\Scripts\python.exe -m pytest tests/test_r10_mergeboss.py -v`: **17 passed**
- `.venv\Scripts\python.exe -m pytest tests/test_agent_boundaries.py tests/test_r10_domain.py tests/test_r10_gogomatch.py tests/test_r10_mergeboss.py -v`: **45 passed**
- `.venv\Scripts\python.exe -m pytest -q -k "not test_check_provenance_detects_phone_harness_reference"`: **346 passed, 1 deselected** (full regression suite green)
- `.venv\Scripts\python.exe scripts/check_agent_boundaries.py`: **OK** (clean tree, boundary respected, domain scan active)
- `.venv\Scripts\python.exe scripts/check_provenance.py`: **OK** (no Phone Harness or legacy copied artifacts)
- Zero taxonomy leakage into generic core (`src/praxiom/{agent,knowledge,retrieval,skill,adaptive,ios_runtime}`) verified.
- No remote push.

## Constraints Honored

- **Frozen seam only**: `src/praxiom/domain/mergeboss.py` interacts with Praxiom solely via `DomainBehavior` and `behavior_to_candidate` from `praxiom.domain.adapter` and `RUNTIME_OPS` from `praxiom.skill.candidate`.
- **Explicit provenance copy versus reimplement**: Reimplemented declarative behavior contracts; legacy code not copied.
- **No domain taxonomy in generic core**: Generic core remains 100% domain-neutral; leak tokens rejected.
- **No stale-revision mutation**: Proven fail-closed at Coordinator, Executor, and Runtime boundaries.
- **Disjoint ownership from GoGoMatch**: Disjoint file ownership (`mergeboss.py`, fixtures, tests) with zero shared implementation code or cross-domain references.
- **No remote push**: All work is local only.
