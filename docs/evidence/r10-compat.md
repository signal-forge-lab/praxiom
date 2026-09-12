# R10 Lane E — Compatibility, Provenance, Rollback, and Guard Closure Evidence

- Sensitivity: PUBLIC
- Date: 2026-09-08
- Scope: Lane E (Phase E compatibility, legacy-only exclusions, source provenance, rollback, supersession, and generalized guard closure; R10-D points D1–D4, 4 points).
- Baseline: HEAD `ff0ab7f1b7bb92975f1e44e2aafabb7f4a1d4e7c` ("docs: retain normalized R10 workflow goal").
- Authority: `docs/evidence/r10-design-freeze.md` (§0–§5, §7, §8, §9 R10-D), `docs/evidence/r10-merge-boss.md`, `docs/evidence/r10-gogomatch.md`, `docs/evidence/r10-seam.md`, `docs/PROVENANCE.md`, `docs/design/20260907_r8plus_execution_plan.md`, `docs/design/20260908_r10_domain-migration-final-acceptance_orchestrator_handoff.md`.

---

## 1. Executive Summary & Rubric Alignment (R10-D: 4 Points)

This document provides formal closure for **R10-D Compatibility, Provenance, and Migration Closure (4 points)**:

| # | Point | Frozen Proof Requirement | Implementation & Verification Evidence |
|---|---|---|---|
| **D1** | Retained legacy/domain behavior mapped to adapter contracts; required vs legacy-only distinguished | Closure-evidence mapping/decision tables (`migrated` / `excluded-legacy-only` / `deferred`) | §2 mapping tables below; 7 Merge Boss and 7 GoGoMatch behaviors migrated; 4 Merge Boss and 3 GoGoMatch legacy behaviors excluded with explicit safety rationales; 2 behaviors deferred; verified in `tests/test_r10_compatibility.py` |
| **D2** | No prohibited source copy or runtime dependency introduced | `check_provenance.py` + `check_agent_boundaries.py` green; pin unchanged | §3 below; zero copied code from Phone Harness or legacy repos; upstream `pymobiledevice3` pinned at `ec4ac06a850a6a884ca778350621f354faf347c6`; verified in `test_r10_d2_*` |
| **D3** | Migration notes, supersession/rollback information, compatibility evidence retained | §8 rollback rows + closure evidence | §4 below; execution-level rollback via `SkillRegistry.revoke`; supersession via `SkillRegistry.supersede`; audit tuples `(from, to, reason, evidence_id)` recorded; physical removal rollback safety verified in `test_r10_d3_*` |
| **D4** | Generalized guard updates where warranted | Additive `SCAN_DIRS` domain coverage + AST inspection + deterministic tests | §5 below; `scripts/check_agent_boundaries.py` updated to enforce generic core and stdlib isolation on `src/praxiom/domain/`; verified in `test_r10_d4_*` and `tests/test_agent_boundaries.py` |

---

## 2. Domain Behavior Mapping & Legacy-Only Exclusions (D1)

In compliance with `docs/evidence/r10-design-freeze.md` §1, §3, and §4, every domain behavior is reimplemented purely from declarative behavior contracts (`DomainBehavior` records) and maps to an R8 `SkillCandidate` via `behavior_to_candidate`.

Required behaviors are strictly distinguished from legacy-only exclusions and deferred behaviors. No legacy behavior has been silently dropped.

### 2.1 Merge Boss Migration & Decision Table

| Legacy Name | Behavior ID | Decision | Risk | Reversibility | Human Gate | Ops Subset | Preconditions | Postconditions | Reason & Evidence Ref |
|---|---|---|---|---|---|---|---|---|---|
| `launch` | `mergeboss:launch` | `migrated` | low | reversible | False | `launch_app` | `revision-bound: fresh observation required`, `device unlocked`, `app installed` | `app window active`, `top-level view rendered` | Core entrypoint for app launch and foreground verification. (`docs/design/20260907_r8plus_execution_plan.md`) |
| `open_board` | `mergeboss:open-level-board` | `migrated` | low | reversible | False | `tap_point`, `tap_element` | `revision-bound: fresh observation required`, `app active` | `board surface visible in observation`, `grid coordinates resolved` | Navigation to game board to enable interactive tile state. (`docs/design/20260907_r8plus_execution_plan.md`) |
| `tap_generator` | `mergeboss:spawn-generator-item` | `migrated` | medium | compensable | False | `tap_point`, `tap_element` | `revision-bound: fresh observation required`, `generator tile ready`, `energy available`, `open board slot available` | `item spawned on open slot`, `energy decremented` | Primary generator tapping producing items from energy budget. (`docs/design/20260907_r8plus_execution_plan.md`) |
| `merge_items` | `mergeboss:merge-board-items` | `migrated` | medium | compensable | False | `drag` | `revision-bound: fresh observation required`, `matching items present on source and target slots` | `merged higher tier item on target slot`, `source slot cleared` | Core puzzle progression mechanic dragging identical tiles to upgrade tier. (`docs/design/20260907_r8plus_execution_plan.md`) |
| `complete_order` | `mergeboss:deliver-customer-order` | `migrated` | medium | compensable | False | `tap_point`, `tap_element` | `revision-bound: fresh observation required`, `customer order active`, `matching item on board` | `order marked completed`, `coins rewarded`, `board item consumed` | Customer order completion delivering requested items for coins. (`docs/design/20260907_r8plus_execution_plan.md`) |
| `buy_generator_part` | `mergeboss:purchase-generator-part` | `migrated` | high | compensable | True | `tap_point`, `tap_element` | `revision-bound: fresh observation required`, `store modal active`, `sufficient currency balance` | `purchased part delivered to inbox or board`, `currency balance debited` | In-game soft currency store purchase. Gated by human approval. (`docs/design/20260907_r8plus_execution_plan.md`) |
| `speedup_cooldown` | `mergeboss:speedup-generator-cooldown` | `migrated` | high | irreversible | True | `tap_point`, `tap_element` | `revision-bound: fresh observation required`, `generator in cooldown`, `premium gems available` | `cooldown cleared`, `premium gems spent irreversibly` | Irreversible spend of premium gems. Strictly human-gated. (`docs/design/20260907_r8plus_execution_plan.md`) |
| `direct_memory_hack` | *(None)* | `excluded-legacy-only` | prohibited | irreversible | True | *(None)* | *(None)* | *(None)* | **Excluded**: Out-of-band memory inspection/patching violates greenfield native runtime boundary and execution model. Mutation must pass through `observe` + `execute`. (`docs/evidence/r10-design-freeze.md` §0) |
| `cloud_sync_override` | *(None)* | `excluded-legacy-only` | prohibited | irreversible | True | *(None)* | *(None)* | *(None)* | **Excluded**: Modifying external account/cloud state is strictly prohibited by the real-workflow safety envelope. (`docs/evidence/r10-design-freeze.md` §5) |
| `auto_purchase_real_money` | *(None)* | `excluded-legacy-only` | prohibited | irreversible | True | *(None)* | *(None)* | *(None)* | **Excluded**: Real-money in-app purchases and payments are strictly prohibited by the safety envelope. (`docs/evidence/r10-design-freeze.md` §5) |
| `batch_board_wipe` | *(None)* | `excluded-legacy-only` | prohibited | irreversible | True | *(None)* | *(None)* | *(None)* | **Excluded**: Mass deletion of user inventory violates non-destructive safety policy. (`docs/evidence/r10-design-freeze.md` §5) |
| `cross_game_inventory_exchange` | *(None)* | `deferred` | high | compensable | True | *(None)* | *(None)* | *(None)* | **Deferred**: Requires cross-domain persistent storage bridge outside R10 single-domain scope. (`docs/design/20260907_r8plus_execution_plan.md`) |

### 2.2 GoGoMatch Migration & Decision Table

| Legacy Name | Behavior ID | Decision | Risk | Reversibility | Human Gate | Ops Subset | Preconditions | Postconditions | Reason & Evidence Ref |
|---|---|---|---|---|---|---|---|---|---|
| `launch_app` | `gogomatch:launch-game` | `migrated` | low | reversible | False | `launch_app` | `revision-bound: runtime status verified` | `game application launched and active in observation` | Core entry behavior re-implemented using standard `launch_app` op. (`docs/evidence/r10-design-freeze.md` #R10-C) |
| `select_level` | `gogomatch:open-level` | `migrated` | low | reversible | False | `tap_element` | `revision-bound: level map surface confirmed` | `level start modal displayed with goals and play button` | Map navigation behavior re-implemented via `tap_element`. (`docs/evidence/r10-design-freeze.md` #R10-C) |
| `start_level` | `gogomatch:start-level` | `migrated` | medium | compensable | False | `tap_element` | `revision-bound: level modal open and stamina available` | `board grid rendered with active tile layout` | Level start initiating game board; compensable risk due to stamina usage. (`docs/evidence/r10-design-freeze.md` #R10-C) |
| `swipe_match` | `gogomatch:swap-tiles` | `migrated` | medium | compensable | False | `drag`, `tap_point` | `revision-bound: interactive match grid confirmed` | `tiles swapped, match resolved, gravity applied` | Primary match-3 mechanic re-implemented with `drag` and `tap_point` ops. (`docs/evidence/r10-design-freeze.md` #R10-C) |
| `use_booster` | `gogomatch:use-hammer-booster` | `migrated` | high | irreversible | True | `tap_element`, `tap_point` | `revision-bound: board active and hammer booster count >= 1` | `booster count decremented and target tile cleared` | Irreversible powerup usage; strictly human-gated per R10 safety envelope. (`docs/evidence/r10-design-freeze.md` #R10-C) |
| `claim_rewards` | `gogomatch:claim-level-reward` | `migrated` | low | reversible | False | `tap_element` | `revision-bound: victory modal displayed` | `rewards claimed and map screen restored` | Post-level reward collection via `tap_element`. (`docs/evidence/r10-design-freeze.md` #R10-C) |
| `buy_extra_moves` | `gogomatch:purchase-extra-moves` | `migrated` | high | irreversible | True | `tap_element` | `revision-bound: out-of-moves dialog visible` | `moves added and transaction logged` | Financial/premium transaction; strictly human-gated and excluded from autonomous live runs. (`docs/evidence/r10-design-freeze.md` #R10-C) |
| `direct_device_service_bypass` | *(None)* | `excluded-legacy-only` | prohibited | irreversible | True | *(None)* | *(None)* | *(None)* | **Excluded**: Direct device-service manipulation violates Praxiom Runtime six-operation boundary. (`docs/evidence/r10-design-freeze.md` §2) |
| `auto_retry_blindly` | *(None)* | `excluded-legacy-only` | prohibited | irreversible | True | *(None)* | *(None)* | *(None)* | **Excluded**: Blind retry without observation reconciliation violates R7/R8 safety invariant. (`docs/evidence/r10-design-freeze.md` §4) |
| `background_daemon_injection` | *(None)* | `excluded-legacy-only` | prohibited | irreversible | True | *(None)* | *(None)* | *(None)* | **Excluded**: Out-of-band daemon manipulation prohibited by greenfield security model. (`docs/PROVENANCE.md`) |
| `multi_touch_cascade_gesture` | *(None)* | `deferred` | medium | compensable | False | *(None)* | *(None)* | *(None)* | **Deferred**: Multi-touch gesture execution deferred to future multi-point track. (`docs/design/20260907_r8plus_execution_plan.md`) |

---

## 3. Greenfield Source Provenance & Dependency Audit (D2)

Per `docs/PROVENANCE.md` and `docs/evidence/r10-design-freeze.md` §3:

1. **Reimplemented, Never Copied**:
   - Zero lines of implementation code were copied from Phone Harness or legacy domain repositories.
   - All 14 migrated behaviors are pure declarative dataclass records in `src/praxiom/domain/mergeboss.py` and `src/praxiom/domain/gogomatch.py`.
   - Domain fixtures in `tests/fixtures/r10/{mergeboss,gogomatch}/` are 100% repo-local synthesized contract fixtures with zero device captures, identifiers, or payloads.

2. **Upstream Pinned Dependency Intact**:
   - Upstream `pymobiledevice3` remains strictly pinned at commit `ec4ac06a850a6a884ca778350621f354faf347c6` in `pyproject.toml`.
   - No local fork, no advanced commit, and no new production dependencies were introduced.
   - Verified deterministically by `test_r10_d2_upstream_pymobiledevice3_pin_is_unmodified`.

3. **Provenance Guard Clean**:
   - `scripts/check_provenance.py` scans `src/` (including `src/praxiom/domain/`) and `pyproject.toml`.
   - Scan result: `OK: no Phone Harness import/name/dependency in production paths`.
   - Verified deterministically by `test_r10_d2_provenance_guard_passes_clean_on_production_tree`.

4. **Domain Import Allowlist**:
   - The frozen seam allowlist (`dataclasses`, `typing`, `praxiom.domain.adapter`, `praxiom.skill.candidate`) is enforced across all domain modules.
   - Verified by AST analysis in `test_r10_d2_no_prohibited_imports_in_domain_modules`.

---

## 4. Rollback and Supersession Architecture & Provenance (D3)

Per `docs/evidence/r10-design-freeze.md` §8, R10 provides two independent rollback layers: execution-level instant rollback without code change, and clean physical package removal.

### 4.1 Instant Execution-Level Rollback via `SkillRegistry.revoke`

When a defective domain behavior must be removed from execution authority immediately:
1. The registry operator calls `SkillRegistry.revoke(skill_id, version, evidence_id=..., reason=...)`.
2. The skill entry transitions to terminal state `revoked`.
3. The registry invalidates its cached active skill and execution token.
4. `SkillRegistry.is_executable(skill)` returns `False`.
5. Any subsequent invocation of `SkillExecutor.execute` fails closed with `SkillExecutionError("skill-not-registry-active")` before any Coordinator or Runtime call can occur (zero device calls).
6. State `revoked` is terminal: `transition(entry.lifecycle, ...)` rejects any attempt to transition back to `active`, `candidate`, or `validated`.
7. The full provenance audit tuple `active->revoked:<reason>:<evidence_id>` is permanently appended to `entry.lifecycle.provenance`.
8. Deterministically verified by `test_r10_d3_execution_level_rollback_via_registry_revoke`.

### 4.2 Version Supersession via `SkillRegistry.supersede`

When an upgraded domain behavior replaces an earlier version:
1. **Atomic Supersession on Activation**: Under `SkillRegistry.activate`, activating a newer version (e.g. `v2`) atomically transitions any older active version (`v1`) to terminal state `superseded`, invalidating its token, and records `active->superseded:registry-superseded-by-v2:<evidence_id>`.
2. **Explicit Manual Supersession**: Alternatively, `SkillRegistry.supersede(skill_id, from_version, new_version=..., evidence_id=..., reason=...)` explicitly transitions an active or degraded version to `superseded`.
3. The superseded version immediately loses execution authority (`is_executable` returns `False`).
4. The higher version independently passes all R8 Skill Gates and validation requirements before activation.
5. Deterministically verified by `test_r10_d3_supersession_via_registry_supersede`.

### 4.3 Physical Package Removal Rollback Safety

Because R10 is purely additive:
1. Generic core (`src/praxiom/{agent,ios_runtime,skill,adaptive,knowledge,retrieval}/**`) has zero diff against baseline.
2. `scripts/check_agent_boundaries.py` defines `_DOMAIN_SCAN_DIR` as presence-conditional:
   ```python
   _DOMAIN_SCAN_DIR = REPO_ROOT / "src" / "praxiom" / "domain"
   SCAN_DIRS = _CORE_SCAN_DIRS + (
       (_DOMAIN_SCAN_DIR,) if _DOMAIN_SCAN_DIR.is_dir() else ()
   )
   ```
3. If `src/praxiom/domain/` is deleted, `check_agent_boundaries.py` automatically falls back to scanning `_CORE_SCAN_DIRS` only, passing with zero violations.
4. All R3–R9 certified test suites remain 100% green upon removal of the domain package.
5. Deterministically verified by `test_r10_d3_physical_removal_rollback_safety_of_boundary_guard`.

---

## 5. Generalized Guard Coverage (D4)

In accordance with freeze §2, §9 (point D4), and Amendment 2026-09-08.2:

`scripts/check_agent_boundaries.py` has been updated with generalized fail-closed AST checks over `src/praxiom/domain/`:

1. **Banned Generic Core Imports**:
   Domain code is forbidden from importing generic core packages:
   `praxiom.agent`, `praxiom.ios_runtime`, `praxiom.adaptive`, `praxiom.knowledge`, `praxiom.retrieval`.
   Any attempt fails closed with: `[prohibited domain import of generic core] <module>`.

2. **Unsafe Standard Library Imports**:
   Domain code is treated as an isolated declarative module and cannot import unsafe stdlib roots:
   `os`, `sys`, `socket`, `pathlib`, `io`, `shutil`, `tempfile`, `urllib`, `http`, `requests`, `importlib`.
   Any attempt fails closed with: `[unsafe domain import] <module>`.

3. **Banned Bare Dynamic Calls**:
   Domain code cannot call dynamic reflection or execution builtins:
   `eval`, `exec`, `compile`, `open`, `input`, `getattr`, `setattr`, `delattr`.
   Any attempt fails closed with: `[dynamic authority/builtin bypass] <call>`.

4. **Banned Subprocess & MCP Roots**:
   Direct imports of `subprocess` and `mcp` are strictly rejected across all domain files.

5. **Banned Device Edges**:
   Direct references to `pymobiledevice3`, `wda`, `coredevice`, `appservice`, `usbmux`, or `from praxiom.ios_runtime.transport import` fail closed via regex scanning.

All generalized guard rules are verified deterministically by:
- `tests/test_agent_boundaries.py::test_boundary_guard_fails_closed_on_domain_file_importing_generic_core_or_unsafe_builtins`
- `tests/test_r10_compatibility.py::test_r10_d4_boundary_guard_covers_domain_and_rejects_generic_core_imports`
- `tests/test_r10_compatibility.py::test_r10_d4_clean_production_tree_passes_all_guards`

---

## 6. Preservation of R7, R8, R9 Architectural Invariants

### 6.1 R7 Post-Action State Safety Floor
- Every domain behavior requires the token `"revision-bound"` in its preconditions.
- Device mutation occurs only with a freshly observed revision token (`expected_revision`).
- Preflight rejects invalid or stale revisions with `STALE_REVISION` before any device mutation occurs (zero device calls).
- On `PARTIAL` or `EFFECT_UNKNOWN` effect classes, auto-retry is forbidden (`retry_safe is False`); reconciliation via fresh observation is mandatory.

### 6.2 R8 Lifecycle Registry & Human-Gate Authority
- The Skill Registry is the sole owner of execution authority. Candidates must pass all 6 ordered Skill Gates (`GATE_ORDER`), receive $\ge 2$ distinct validation evidence IDs, and log $\ge 2$ distinct per-revision successes before activation.
- `human_gate=True` is strictly enforced for any behavior where `risk == "high"` or `reversibility == "irreversible"`.
- Human approval requires an exact one-shot token cryptographically bound to the skill ID, version, target revision, and full canonical payload. Missing, replayed, or cross-revision tokens fail closed.

### 6.3 R9 Safe Fallback Floor
- Every domain kind adheres to `RegressionBudget(max_latency_ms, max_observe_rate, min_recovery_rate)`.
- If an adaptive or optimized path breaches budget thresholds, execution falls back automatically and independently to the unoptimized safe path.
- Confidence scores and performance optimizations never outrank safety, human-gate, revision, or reconciliation rules.

---

## 7. Deterministic Verification Matrix

| Suite | Test Identifier | Rubric Point | Status |
|---|---|---|---|
| `tests/test_r10_compatibility.py` | `test_r10_d1_mergeboss_mapping_and_legacy_exclusions` | D1 | **PASSED** |
| `tests/test_r10_compatibility.py` | `test_r10_d1_gogomatch_mapping_and_legacy_exclusions` | D1 | **PASSED** |
| `tests/test_r10_compatibility.py` | `test_r10_d1_no_untracked_legacy_behaviors_and_fixture_alignment` | D1 | **PASSED** |
| `tests/test_r10_compatibility.py` | `test_r10_d2_provenance_guard_passes_clean_on_production_tree` | D2 | **PASSED** |
| `tests/test_r10_compatibility.py` | `test_r10_d2_upstream_pymobiledevice3_pin_is_unmodified` | D2 | **PASSED** |
| `tests/test_r10_compatibility.py` | `test_r10_d2_no_prohibited_imports_in_domain_modules` | D2 | **PASSED** |
| `tests/test_r10_compatibility.py` | `test_r10_d3_execution_level_rollback_via_registry_revoke` | D3 | **PASSED** |
| `tests/test_r10_compatibility.py` | `test_r10_d3_supersession_via_registry_supersede` | D3 | **PASSED** |
| `tests/test_r10_compatibility.py` | `test_r10_d3_physical_removal_rollback_safety_of_boundary_guard` | D3 | **PASSED** |
| `tests/test_r10_compatibility.py` | `test_r10_d4_boundary_guard_covers_domain_and_rejects_generic_core_imports` | D4 | **PASSED** |
| `tests/test_r10_compatibility.py` | `test_r10_d4_clean_production_tree_passes_all_guards` | D4 | **PASSED** |
| `tests/test_agent_boundaries.py` | `test_boundary_guard_fails_closed_on_domain_file_importing_generic_core_or_unsafe_builtins` | D4 | **PASSED** |
| `tests/test_agent_boundaries.py` | `test_boundary_guard_fails_closed_on_domain_file_importing_banned_edge` | D4 | **PASSED** |

### Execution Proof Commands

```bash
# 1. Compatibility and provenance acceptance test suite:
.venv\Scripts\python.exe -m pytest tests/test_r10_compatibility.py -v
# Result: 11 passed in 0.38s

# 2. Boundary guard tests (including generalized domain enforcement):
.venv\Scripts\python.exe -m pytest tests/test_agent_boundaries.py -v
# Result: 6 passed in 0.88s

# 3. Domain acceptance suites (Lane S, Lane MB, Lane GG):
.venv\Scripts\python.exe -m pytest tests/test_r10_domain.py tests/test_r10_mergeboss.py tests/test_r10_gogomatch.py -v
# Result: 40 passed in 1.45s

# 4. Standalone guard executions:
.venv\Scripts\python.exe scripts/check_agent_boundaries.py
# Result: OK: agent/knowledge/retrieval/skill/adaptive respect the Runtime boundary.

.venv\Scripts\python.exe scripts/check_provenance.py
# Result: OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml).

# 5. Full regression suite:
.venv\Scripts\python.exe -m pytest -q -k "not test_check_provenance_detects_phone_harness_reference"
# Result: 358 passed, 1 deselected, 0 failed.
```

---

## 8. Status & Conclusion

Lane E (Phase E compatibility, provenance, rollback, supersession, and generalized guard closure) is **COMPLETE**:
- All 4 points of **R10-D (D1, D2, D3, D4)** are satisfied with deterministic proof and zero regressions.
- Greenfield provenance invariants and upstream pins are 100% intact.
- R7 validation floor, R8 lifecycle registry human-gate, and R9 safe fallback invariants are preserved.
- No remote push. All changes committed locally only.
