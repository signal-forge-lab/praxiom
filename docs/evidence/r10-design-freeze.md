# R10 Domain Migration & Final Acceptance — Design Freeze (2026-09-08)

- Sensitivity: PUBLIC
- Owner: R10 single design owner (one freeze before any parallel production edit)
- Baseline: HEAD `ff0ab7f1b7bb92975f1e44e2aafabb7f4a1d4e7c` (2026-09-08, "docs: retain normalized R10 workflow goal"), clean working tree; certified floor R3 33/33, R4 20/20, R5 7/7, R6 44/44, R7 31/31, R8 47/47, R9 47/47 (R8+R9 94/94 CERTIFIED, unresolved=[], errors=[]) per `docs/STATUS.md`.
- Authority: `docs/design/20260908_r10_domain-migration-final-acceptance_orchestrator_handoff.md` (§3–§5, §9), `docs/design/20260908_r10_normalized_plan-and-run_goal.md`, retained `docs/evidence/20260907_r8-r9-design-freeze.md`, `docs/PROVENANCE.md`, `src/praxiom/ios_runtime/runtime.py` (six-operation contract).
- Freeze date: 2026-09-08. Everything below is frozen before Phase C/D production edits. The freeze may be corrected only by a dated amendment recorded in §12 with rationale; silent widening is a freeze violation.

## 0. Frozen scope and non-negotiable constraints

- Minimal domain adapter seam only: one new declarative package (`src/praxiom/domain/`). No second device-mutation path, no generic plugin host, no new Runtime public operation, no convenience widening.
- The Native iOS Runtime public surface remains exactly six operations: `status`, `observe`, `execute`, `invalidate`, `recover`, `close` (`src/praxiom/ios_runtime/runtime.py`). No R10 file may edit Runtime.
- Coordinator/Skill authority and revision binding are preserved unchanged: device mutation enters only via a registry-active `ActiveSkill` through `SkillExecutor.execute` → `ExecutionCoordinator.run(spec with revision)` → `Runtime.execute(actions, expected_revision=...)`.
- Generic core is frozen untouched: `src/praxiom/{ios_runtime,agent,skill,adaptive,knowledge,retrieval}/**` and `pyproject.toml` (no new dependencies) receive zero R10 edits. `scripts/check_provenance.py` already scans all of `src/`, so the new domain package is provenance-covered with no guard edit.
- Visual Flight Recorder V0–V3 (29 points) is out of scope, stays read-only/independent, and must not gain device-mutation authority.
- No remote push. All R10 work is committed locally only.

## 1. Minimal domain adapter seam

Generic core vs domain-specific split:

| Classification | Modules |
|---|---|
| Generic core (frozen, domain-neutral) | `src/praxiom/ios_runtime/*`, `src/praxiom/agent/*`, `src/praxiom/skill/*`, `src/praxiom/adaptive/*`, `src/praxiom/knowledge/*`, `src/praxiom/retrieval/*` |
| Domain adapter seam (new, declarative only) | `src/praxiom/domain/__init__.py`, `src/praxiom/domain/adapter.py` |
| Domain behaviors (new, per domain) | `src/praxiom/domain/mergeboss.py`, `src/praxiom/domain/gogomatch.py` |

The entire shared seam is one frozen contract in `adapter.py` — pure data plus one pure mapping function, zero device calls, zero I/O:

```python
# Only imports permitted in src/praxiom/domain/*: dataclasses, typing,
# and from praxiom.skill.candidate import RUNTIME_OPS, SkillCandidate.
# Nothing else from praxiom.* may be imported by domain code.

@dataclass(frozen=True)
class DomainBehavior:
    behavior_id: str                  # "<domain>:<kebab-behavior>", unique per domain
    domain: str                       # "mergeboss" | "gogomatch"
    summary: str                      # machine-oriented, <=280 chars, non-empty
    source_evidence: tuple[str, ...]  # >=1 accepted evidence/design refs (see §3)
    inputs: tuple[str, ...]           # non-empty
    preconditions: tuple[str, ...]    # MUST include the "revision-bound" token
    postconditions: tuple[str, ...]   # non-empty
    risk: str                         # "low" | "medium" | "high"
    reversibility: str                # "reversible" | "compensable" | "irreversible"
    ops: frozenset[str]               # non-empty subset of RUNTIME_OPS (never redefined here)
    human_gate: bool                  # MUST be True when risk=="high" or reversibility=="irreversible"

def behavior_to_candidate(behavior: DomainBehavior, *, version: int = 1) -> SkillCandidate:
    """Pure mapping to an R8 SkillCandidate. The result is untrusted until it
    passes all ordered R8 Skill Gates and SkillRegistry.activate re-runs them."""
```

Entry rules (frozen):

- Domain behavior enters execution only as `SkillCandidate` → all R8 gates → `SkillRegistry.activate` (registry-owned, re-runs gates, ≥2 distinct validation evidence ids, ≥2 distinct per-revision success ids) → `SkillExecutor.execute(...)` → `ExecutionCoordinator.run` → `Runtime.execute(..., expected_revision=...)`. No bypass lane exists or may be added.
- Unsupported operations fail closed: `ops ⊆ RUNTIME_OPS` is enforced at `behavior_to_candidate` and again by R8 gates/`SkillExecutor` (`op-not-authorized`); an unsupported op never widens Runtime.
- Domain taxonomy (the strings `mergeboss`, `gogomatch`, `merge boss`) may appear only in `src/praxiom/domain/`, `tests/test_r10_domain.py`, `tests/test_r10_mergeboss.py`, `tests/test_r10_gogomatch.py`, `tests/fixtures/r10/`, `scripts/r10_domain_workflow.py`, and `docs/`. The existing generic-core domain-token rejection (R8 freeze §3) is retained and extended to the new scan scope (§7).
- If a lane discovers a seam gap that appears to require editing generic core, it must stop and record a freeze amendment (§12) instead of editing.

## 2. Dependency direction (allowed and forbidden)

Allowed conceptual direction (identical to handoff §5; unchanged):

```text
Domain adapter / migrated behavior  (src/praxiom/domain/*, declarative only)
        ↓  imports only praxiom.skill.candidate (RUNTIME_OPS, SkillCandidate)
R8 Skill contracts + Gates + SkillRegistry / SkillExecutor
        ↓
R6 ExecutionCoordinator / R7 state-safety contracts
        ↓
NativeIosRuntime six-operation boundary
        ↓
unmodified pinned upstream pymobiledevice3 @ ec4ac06a850a6a884ca778350621f354faf347c6 / WDA / CoreDevice
```

Forbidden for domain code (guard-enforced, fail-closed):

- direct transport/WDA/CoreDevice/AppService/usbmux/pymobiledevice3 edges;
- Phone Harness in any form (production/build/runtime dependency, subprocess, fallback);
- internal MCP device chain or a second trusted plugin/device execution path;
- imports of `praxiom.agent`, `praxiom.ios_runtime` (including transport internals), `praxiom.adaptive`, `praxiom.knowledge`, `praxiom.retrieval` from `src/praxiom/domain/*`;
- Runtime private-internals access; unrevisioned device mutation;
- confidence/performance-based bypass of Skill lifecycle, gates, validator, revision, human-gate, or reconciliation rules.

Enforcement: `scripts/check_agent_boundaries.py` gains `src/praxiom/domain` in `SCAN_DIRS` (additive; the domain package is then subject to the same banned-edge, banned-import-root, and dynamic-call checks as skill/adaptive code). `tests/test_agent_boundaries.py` gains a deterministic case proving a domain file importing a banned edge fails the guard.

## 3. Migration provenance rules

- Greenfield rule retained (`docs/PROVENANCE.md`): every migrated behavior is **reimplemented from its accepted behavior contract**, never copied. No Phone Harness or legacy-domain source file, module, subprocess, renamed port, or hidden execution path is imported or copied. Copying behavior contracts (small, cited, declarative data) is allowed; copying implementation code is not.
- Each `DomainBehavior` must cite `source_evidence`: accepted retained references (`docs/design/20260907_r8plus_execution_plan.md`, the R10 handoff, and any per-behavior contract row retained at migration time). Roadmap-level authority alone is not enough for a live-lane behavior — the per-behavior contract row (§5 fields) is the migration-time evidence.
- The compatibility/provenance closure evidence (`docs/evidence/20260908_r10-compatibility-provenance-closure.md`) must contain, per domain, a mapping table: legacy behavior → `behavior_id` → decision (`migrated` / `excluded-legacy-only` / `deferred`) → reason → evidence ref. Required behavior and legacy-only behavior must be explicitly distinguished; legacy-only exclusions are recorded, not silently dropped.
- Deterministic fixtures are repo-local synthesized data under `tests/fixtures/r10/{mergeboss,gogomatch}/` derived from the behavior contracts — never recorded device captures containing screen text, identifiers, or payloads.
- No prohibited source copy or runtime dependency may be introduced: `scripts/check_provenance.py` (scans all of `src/` + `pyproject.toml`) and `check_agent_boundaries.py` must stay green; the pin at `ec4ac06a850a6a884ca778350621f354faf347c6` is not advanced.
- Supersession/rollback notes per behavior are retained in the closure evidence (§8).

## 4. Revision / precondition / postcondition and risk / reversibility / human-gate semantics

Frozen semantics for all migrated behaviors (they refine, never relax, R7/R8 floors):

- Preconditions must include the `revision-bound` token (R8 revision gate). Every state-sensitive mutation executes only against the current revision obtained from a fresh `observe()`; a stale revision yields the existing fail-closed stale/`STALE_REVISION` behavior — never mutation (R2/R3 invariant: no state-sensitive mutation from stale revision).
- Whole-batch preflight semantics are inherited unchanged: a no-effect rejection (validation, stale revision, foreign/unknown ref) makes zero device calls and leaves the revision intact; any attempted mutation invalidates the accepted revision on success or failure; connection-class failure after send is `EFFECT_UNKNOWN`, never auto-replayed.
- Postconditions are non-empty, machine-oriented, and must be verifiable from observation or from the recorded effect class; a postcondition that cannot be checked is not accepted.
- Effect handling: `NONE` effects may batch/reuse under R8/R9 rules; `PARTIAL`/`UNKNOWN`/unrecognized effects never reuse, never auto-retry, never macro — reconciliation (R7) precedes any continuation. No blind replay after unknown/partial/stale effect, for domain work identically to generic work.
- Risk/reversibility use the R8 enums. Classification rule: navigation/launch/observe behaviors classify `low`/`reversible` only when a reproduced observation can prove the state returned; anything mutating persistent domain state that cannot be proven restorable classifies at least `compensable`; unprovable-restore or spend-like behavior classifies `irreversible`. `risk=="high"` or `reversibility=="irreversible"` forces `human_gate=True`.
- Human-gate execution uses the unchanged R8 registry machinery: a one-shot approval minted only by the configured human-approval authority, bound to exact skill/version/current revision/full canonical payload; copied, mutated, replayed, cross-revision, or payload-substituted approvals fail closed. A live-lane behavior that is not safely reversible/low-risk stays human-gated or is proven through deterministic/non-mutating evidence instead — the safety policy is never silently weakened.
- Domain confidence and performance signals never outrank lifecycle/safety/revision/human-gate authority.

## 5. Bounded real-workflow safety envelope (live lane)

- Preconditions for any live work: R10 deterministic matrix green, boundary/provenance guards green, full R3–R9 regression green.
- Single owner: exactly one live lane performs device mutation; Merge Boss and GoGoMatch live workflows run sequentially, never concurrently. The live lane is the only writer of device state during its window.
- Path: only `Agent → Skill/Coordinator → Runtime`. Live mutation occurs only through registry-active domain skills with revision-bound execution.
- Revision freshness: `observe()` immediately before each state-sensitive mutation; no cross-behavior revision reuse after invalidation; on stale/`PARTIAL`/`UNKNOWN`, stop and reconcile.
- Allowed live action classes (frozen closed set): `launch_app` of the two target domain apps, `observe`, and non-destructive navigation (`tap_point`/`tap_element`/`swipe`/`drag`) confined to the target app's non-purchasing, non-account, non-messaging UI surfaces. Any action class outside this set requires a freeze amendment plus human-gate approval, or stays deterministic-only.
- Prohibited live classes: purchase/payment, account or security changes, messaging, deletion/uninstall/data wipe, profile installation, credential entry, device-settings mutation, and any safety-critical system surface.
- Evidence privacy: retain only counts, enums, timings, result classes, privacy-safe Trace counters, behavior ids, and opaque revision tokens (the Runtime's `status()`/trace privacy guarantees). Never retain secrets, raw device identifiers, pair records, raw screen text, element labels, screenshots, or action payloads, unless an already-approved evidence contract explicitly requires them.
- Honesty rule: if the required device/app/safe state is unavailable, record a precise external blocker in the live evidence file (`docs/evidence/20260908_r10-bounded-real-workflow.md`); the Goal remains blocked rather than falsely complete. No fabricated hardware/app evidence; no criterion downgrade.

## 6. Performance baseline and non-regression budgets

- Baseline source: retained R9-safe behavior (`PerformanceBaseline` median/p90/sample-count per kind from the R8/R9 certification runs, `docs/evidence/20260907_adaptive-skill-platform-certification-packet.md`).
- New domain kinds (per-domain observe/navigate/launch workflow kinds) must first run with adaptive optimization disabled (the R9-safe path) to record their baseline before any fast path applies.
- Budgets: `RegressionBudget(max_latency_ms, max_observe_rate, min_recovery_rate)` per kind; the retained default `max_latency_ms=500` applies unless a per-kind budget is frozen here with rationale (none is: R10 freezes no custom budgets). Exceeding any budget disables optimization for that kind (independent per-kind fallback to the safe path), exactly per R9 `safe_fallback` semantics.
- Non-regression: R10 additions must not regress retained R9-safe kinds; `docs/evidence/20260908_r10-acceptance.md` must include the R10-vs-R9-safe per-kind comparison (privacy-safe timings only). Performance never overrides safety: budget breach ⇒ fallback, never a relaxation of revision/human-gate/reconciliation rules.

## 7. File ownership (parallel lanes, disjoint writes)

| Lane | Phase | Owned files (exclusive write scope) |
|---|---|---|
| S — shared seam | C | `src/praxiom/domain/__init__.py`, `src/praxiom/domain/adapter.py`, `tests/test_r10_domain.py`, `scripts/check_agent_boundaries.py` (add `src/praxiom/domain` to `SCAN_DIRS` only), `tests/test_agent_boundaries.py` (add domain-scan case) |
| MB — Merge Boss | D (after S accepted) | `src/praxiom/domain/mergeboss.py`, `tests/test_r10_mergeboss.py`, `tests/fixtures/r10/mergeboss/*` |
| GG — GoGoMatch | D (parallel with MB, after S accepted) | `src/praxiom/domain/gogomatch.py`, `tests/test_r10_gogomatch.py`, `tests/fixtures/r10/gogomatch/*` |
| E — compatibility/provenance closure | E | `docs/evidence/20260908_r10-compatibility-provenance-closure.md` |
| L — live workflow | F (single owner, sequential) | `scripts/r10_domain_workflow.py`, `docs/evidence/20260908_r10-bounded-real-workflow.md` |
| P — acceptance package | G | `docs/evidence/20260908_r10-acceptance.md`, `docs/STATUS.md` (R10 status rows at close only) |

- MB and GG may run in parallel only after Lane S is accepted and their write sets remain disjoint as listed.
- Frozen untouched by any lane: `src/praxiom/{ios_runtime,agent,skill,adaptive,knowledge,retrieval}/**`, `pyproject.toml`, `scripts/check_provenance.py` (already covers `src/`), and all retained R3–R9 evidence documents (historical statements are never rewritten).
- No lane may edit files outside its row; additions require a freeze amendment (§12).

## 8. Rollback / removal path for a defective domain adapter

- R10 is purely additive: the domain package (3 modules), domain tests/fixtures, one additive guard scan-dir line, one runner script, and docs/evidence. Removal = revert/delete exactly those paths; because the generic-core diff of every R10 commit must be empty, rollback cannot regress R3–R9.
- Instant execution-level rollback without code change: `SkillRegistry` `revoked` (terminal, never reactivates) for the defective behavior's skill, or `superseded` to a fixed higher version; the lifecycle provenance tuple `(from, to, reason, evidence_id)` records the rollback path (R8 freeze §7 retained).
- The additive guard line is rollback-safe: after removing `src/praxiom/domain`, the scan simply finds nothing; guards and full suite must still pass.
- No data/schema migration is introduced (Coordinator ledger schema stays v1), so there is no data rollback surface.
- Rollback drill (R10-F evidence): prove deterministically that deleting the domain package leaves the full R3–R9 suite plus provenance/boundary guards green.

## 9. Exact R10 matrix — 35 points (A7 B6 C6 D4 E5 F4 G3)

Frozen one-to-one mapping of all 35 rubric points to their proof artifacts. Total must equal 35; no point may be merged, split, or silently re-scoped.

### R10-A — Domain adapter seam and authority isolation — 7 points

| # | Point | Frozen proof |
|---|---|---|
| A1 | Generic core remains domain-neutral; no domain taxonomy in generic core | `tests/test_agent_boundaries.py` domain-token + `check_agent_boundaries.py` green |
| A2 | Adapters cannot call transport/WDA/CoreDevice/AppService/usbmux/pymobiledevice3 directly | guard scan over `src/praxiom/domain` + negative import test in `tests/test_r10_domain.py` |
| A3 | Adapters cannot obtain Phone Harness or internal MCP device authority | `check_provenance.py` + banned import roots (`subprocess`, `mcp`) green |
| A4 | All mutations pass through Skill/Coordinator/Runtime revision-bound authority | deterministic path test: registry-active skill → `SkillExecutor` → `coordinator.run(revision)` → fake Runtime; no other call site exists |
| A5 | R8 lifecycle, registry-owned authority, human-gate, one-shot approval remain authoritative for domain skills | domain candidates must pass gates + `SkillRegistry.activate`; approval binding negatives in `tests/test_r10_domain.py` |
| A6 | R9 safety floors remain authoritative (fallback/budget, confidence never bypasses) | `tests/test_r10_domain.py` reuses R9 budget/fallback invariants over domain kinds |
| A7 | Unsupported operations fail closed rather than widening Runtime; six-op surface intact | unsupported-op fail-closed test + six-operation surface assertion (`runtime.py` unchanged) |

### R10-B — Merge Boss migration — 6 points

| # | Point | Frozen proof |
|---|---|---|
| B1 | Explicit behavior/contract mapping and provenance | `mergeboss.py` `BEHAVIORS` with `source_evidence` + mapping table in compatibility/provenance closure |
| B2 | Deterministic fixtures/tests | `tests/test_r10_mergeboss.py` + `tests/fixtures/r10/mergeboss/*` green |
| B3 | Precondition/postcondition/revision binding | gate-level `revision-bound` precondition + revision-binding execution test |
| B4 | Risk/reversibility/human-gate classification per behavior | per-behavior classification table + human-gate-required negatives |
| B5 | No copied legacy production dependency or hidden execution path | `check_provenance.py` + boundary guard + closure-evidence copy review |
| B6 | No blind replay after partial/unknown/stale effect | PARTIAL/UNKNOWN/stale → reobserve/reconcile negatives |

### R10-C — GoGoMatch migration — 6 points

| # | Point | Frozen proof |
|---|---|---|
| C1 | Explicit behavior/contract mapping and provenance | `gogomatch.py` `BEHAVIORS` with `source_evidence` + mapping table in compatibility/provenance closure |
| C2 | Deterministic fixtures/tests | `tests/test_r10_gogomatch.py` + `tests/fixtures/r10/gogomatch/*` green |
| C3 | Precondition/postcondition/revision binding | gate-level `revision-bound` precondition + revision-binding execution test |
| C4 | Risk/reversibility/human-gate classification per behavior | per-behavior classification table + human-gate-required negatives |
| C5 | No copied legacy production dependency or hidden execution path | `check_provenance.py` + boundary guard + closure-evidence copy review |
| C6 | No blind replay after partial/unknown/stale effect | PARTIAL/UNKNOWN/stale → reobserve/reconcile negatives |

C1–C6 mirror B1–B6 at the same acceptance bar but are satisfied independently by the GoGoMatch lane — separate module, separate tests/fixtures, no shared implementation with B.

### R10-D — Compatibility, provenance, and migration closure — 4 points

| # | Point | Frozen proof |
|---|---|---|
| D1 | Retained legacy/domain behavior mapped to adapter contracts; required vs legacy-only distinguished | closure-evidence mapping/decision tables (migrated / excluded-legacy-only / deferred) |
| D2 | No prohibited source copy or runtime dependency introduced | `check_provenance.py` + `check_agent_boundaries.py` green; pin unchanged |
| D3 | Migration notes, supersession/rollback information, compatibility evidence retained | §8 rollback rows + closure evidence |
| D4 | Generalized guard updates where warranted | additive `SCAN_DIRS` domain coverage + its deterministic test |

### R10-E — Bounded real-workflow evidence — 5 points

| # | Point | Frozen proof |
|---|---|---|
| E1 | Single-owner device mutation lane, live only after deterministic gates | live-evidence record of gate order + sequential single-owner execution |
| E2 | Fresh revision-bound observation; only Agent → Skill/Coordinator → Runtime | live-evidence revision chain record; no direct mutation call sites |
| E3 | Unsafe action classes excluded (purchase/payment/account/security/messaging/deletion/profile install/credentials/settings) | allowed-class assertion + live-evidence op-class log |
| E4 | Privacy-safe evidence only; nothing fabricated | evidence contains counts/enums/timings/result classes/opaque tokens only |
| E5 | Non-reversible/high-risk actions human-gated or deterministic-only; precise external blocker instead of false completion | per-behavior gate check + blocker record if safe state unavailable |

### R10-F — Full regression, safety, and performance gates — 4 points

| # | Point | Frozen proof |
|---|---|---|
| F1 | Full R3–R9 regression + R10 deterministic matrix + provenance/boundary guards green; six-op Runtime surface intact | full-suite run record at R10 close |
| F2 | No domain leakage into generic core | domain-token guard green over generic-core scan |
| F3 | No stale-revision mutation, blind replay, hidden authority, or false-green validation introduced | deterministic negatives across R10 tests |
| F4 | R10 workflow performance vs retained R9-safe baselines with per-kind fallback/non-regression; safety outranks performance | §6 baseline/budget comparison in acceptance evidence |

### R10-G — R10 acceptance package and program closure — 3 points

| # | Point | Frozen proof |
|---|---|---|
| G1 | Complete acceptance package mapping all 35 points to evidence, files/commits, tests, live evidence or precise blocker | `docs/evidence/20260908_r10-acceptance.md` |
| G2 | Domain-specific migration/architecture review with concrete blocking findings repaired, retested, re-reviewed | review + repair/retest record in acceptance evidence |
| G3 | Final status/closure: runtime-owned Goal Certification chain, clean local tree, no remote push | certification results + local-commit/clean-tree record in acceptance evidence |

Count check: 7 + 6 + 6 + 4 + 5 + 4 + 3 = **35**.

## 10. Verification intent (frozen)

- All 35 points map to deterministic tests or retained evidence; each B/C point has at least one deterministic assertion.
- Accepted R3–R9 evidence is read and cited, not reimplemented; retained historical documents are not rewritten.
- Completion requires the handoff §8 criteria unchanged: terminal durable Run `completed`, R10 35/35, deterministic + full regression green, all guards green, live evidence accepted or Goal blocked, review clean after repairs, runtime-owned Independent Reviewer approved and Final Judge pass, `unresolved=[]`, major `errors=[]`, final commit local with clean tree, no remote push.

## 11. Non-goals (frozen)

R8/R9 redesign without a reproduced current defect; Visual Flight Recorder V0–V3; generic trusted plugin host; new Runtime public operations; vector DB/PostgreSQL/pg-boss/scheduler/process-per-concept expansion; Phone Harness or internal MCP as fallback; remote push.

## 12. Amendment rule

This freeze binds Phase C–G lanes. A lane that believes a frozen decision is wrong must stop and record a dated amendment here (what changed, why, evidence) before touching files outside its ownership row; unrecorded deviations are freeze violations and block acceptance.

### Amendment 2026-09-08.1 — Scope domain-token leak scan to generic core in check_agent_boundaries.py

- Author: Lane GG (GoGoMatch migration)
- Rationale: Lane S added `_DOMAIN_SCAN_DIR` to `SCAN_DIRS` so that domain code would be subject to AST and banned-edge checks (WDA, pymobiledevice3, subprocess, MCP). However, `main()` scanned `for d in SCAN_DIRS` when checking for domain-leak tokens (`gogomatch`, `merge boss`, etc.). Per freeze §1 line 58 and §9 point F2 ("domain-token guard green over generic-core scan"), domain taxonomy is explicitly permitted in `src/praxiom/domain/` and prohibited only in generic core (`src/praxiom/{agent,knowledge,retrieval,skill,adaptive}`). As flagged in `docs/evidence/r10-seam.md` (§1 Flag 1), scanning `SCAN_DIRS` for domain-leak tokens would prevent domain adapters from declaring their own frozen domain names.
- What changed: In `scripts/check_agent_boundaries.py`, the `seam_text` scan for domain-leak tokens is scoped to `_CORE_SCAN_DIRS` (already defined in that script) rather than all `SCAN_DIRS`. AST checks and banned-edge checks continue to scan all of `SCAN_DIRS` (including `src/praxiom/domain`).
- Evidence: `scripts/check_agent_boundaries.py` passes cleanly with both generic-core token rejection and domain-package edge/import enforcement active.

### Amendment 2026-09-08.2 — Generalized boundary guard coverage and compatibility test suite

- Author: Lane E (Compatibility, provenance, and migration closure)
- Rationale: Per freeze §2 lines 82/86 and §9 point D4 ("Generalized guard updates where warranted"), domain files in `src/praxiom/domain/` must be forbidden from importing generic core packages (`praxiom.agent`, `praxiom.ios_runtime`, `praxiom.adaptive`, `praxiom.knowledge`, `praxiom.retrieval`), forbidden from importing unsafe stdlib roots (`os`, `sys`, `pathlib`, etc.), and forbidden from bare dynamic calls (`eval`, `exec`, `open`, etc.). In addition, deterministic test coverage for R10-D points D1–D4 is established in `tests/test_r10_compatibility.py`.
- What changed:
  1. In `scripts/check_agent_boundaries.py`, added `BANNED_DOMAIN_IMPORTS` preventing domain code from importing generic core modules, and extended `BANNED_SKILL_ADAPTIVE_IMPORT_ROOTS` and `BANNED_BARE_CALLS` to scan `src/praxiom/domain/`.
  2. In `tests/test_agent_boundaries.py`, added `test_boundary_guard_fails_closed_on_domain_file_importing_generic_core_or_unsafe_builtins`.
  3. Created `tests/test_r10_compatibility.py` covering all R10-D requirements: D1 mapping/exclusions, D2 provenance/pins, D3 rollback/supersession, and D4 generalized guard coverage.
  4. Created `docs/evidence/20260908_r10-compatibility-provenance-closure.md`.
- Evidence: Full test suite passes (358 passed), boundary and provenance guards green, zero taxonomy leakage, no remote push.
