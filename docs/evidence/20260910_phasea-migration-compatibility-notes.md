# Praxiom Post-R10 Phase A — Migration & Compatibility Notes

Date: 2026-09-10

Status: **RETAINED NOTES — operator/caller migration and compatibility reference**

Sensitivity: **PUBLIC**

Companion to `docs/evidence/20260910_phasea-implementation-evidence.md`
(exact paths, verification) and the frozen authorities
`docs/evidence/20260909_post-r10-phase-a-design-freeze.md` +
`docs/design/20260909_post-r10-phase-a_closed-loop-telemetry_design-decisions.md`.
Nothing here rewrites frozen design or R0-R10 certification. No production
code was edited by this notes pass; no commit, no push.

## 1. Compatibility summary (what cannot change — and did not)

| Invariant | Phase A status | Guard |
| --- | --- | --- |
| Runtime public surface exactly `status`, `observe`, `execute`, `invalidate`, `recover`, `close` | UNCHANGED; `runtime.trace` is consumed as read-only state, not a seventh operation | AST test `tests/test_phasea_integration.py::test_runtime_public_surface_still_exactly_six_operations` + retained R2 surface test |
| Device mutation only via Agent/Skill/Coordinator → Runtime | UNCHANGED; telemetry, learning, shadow, discovery, visual hooks, `session.py` are observational | `scripts/check_agent_boundaries.py`, session boundary test, telemetry/lane-V import-graph tests |
| `ExecutionCoordinator.run_batch()` semantics | UNCHANGED (per-spec loop, one Runtime call per spec) | `tests/test_phasea_integration.py::test_run_batch_semantics_unchanged_by_integration` |
| Certified single-action `SkillExecutor.execute()` path | UNCHANGED (new hooks are observational; failures land in bounded `hook_errors` and never alter the attempt) | `tests/test_phasea_a5_skill_sequence.py::test_a5_gate_off_by_default_and_single_action_unchanged`, lane-L hook tests |
| Coordinator durable attempt-ledger schema | UNCHANGED format; `inspect(execution_id)` remains the restart-safe path; sequences add rows, not schema | `tests/test_phasea_integration.py::test_run_sequence_durable_ledger_row_and_restart_safe_inspection`, retained R6/R7 lane tests |
| No Phone Harness production/build/runtime dependency or fallback | PRESERVED (zero references in `src/`, `pyproject.toml`) | `scripts/check_provenance.py` + suite run |
| Upstream pin `pymobiledevice3 @ ...@ec4ac06a850a6a884ca778350621f354faf347c6` | UNCHANGED; Wi-Fi adapter subclasses the pinned upstream class | `tests/test_r10_compatibility.py::test_r10_d2_upstream_pymobiledevice3_pin_is_unmodified`, `docs/PROVENANCE.md` |
| No stale-revision mutation, no blind replay after PARTIAL/UNKNOWN | PRESERVED and extended to sequences | R10 replay tests + §5 tests below |
| No persisted/replayed `SkillTrustToken` authority | PRESERVED; enforced at serialize/store/load | `FORBIDDEN_AUTHORITY_KEYS`, rebind test, privacy scan |
| R0-R10 deterministic certification | NOT reopened; full runnable suite green on the Phase A tree (472 passed, 1 environmental deselect, 0 failed, 2026-09-10) | retained evidence docs; certification files untouched |

## 2. New surfaces callers may adopt (all optional/additive)

- `praxiom.session.RunSession` — composition entry point:
  `RunSession.start(runtime=..., registry=...)` opens the journal, enables the
  run-scoped durable Coordinator ledger, wires the experience recorder and
  shadow advisor, and provides `execute_skill` / `execute_sequence` /
  `note_attempt` / `drain_trace` / `close`. Callers may instead keep their
  existing construction and `attach_executor(...)` to gain the observational
  hooks only.
- `praxiom.telemetry` (`RunContext`, `RunJournal`, bridges, summary) —
  standalone observational infrastructure; usable without `RunSession`.
- `praxiom.visual_hooks` — metadata-only D4 vocabulary + `VisualTimeline`
  read-only projection.
- `praxiom.ios_runtime.discovery.DeviceDiscovery` — read-only transport-neutral
  discovery (`probe` / `select`, blocker taxonomy, fingerprint-only outputs).
- `praxiom.skill` sequence surface — `SkillExecutor.execute_sequence`,
  `SequenceStep`, `SequenceExecution` (gated; see §5).
- `praxiom.adaptive` shadow/experience surface — `shadow_recommend`,
  `ShadowAdvisor`, `LiveOptimizationGate`, `build_episode`, `rebind_history`.

Existing imports and call sites keep working unchanged: every addition is a
new module, a new method, or a default-off flag; no existing public name was
removed or re-typed (the only tracked-file surface edits are additive
exports in `praxiom/adaptive/__init__.py` and `praxiom/skill/__init__.py`).

## 3. Behavioral changes to be aware of (compatible but observable)

1. **Normal live-run construction now enables the durable Coordinator
   ledger.** `RunSession.start(runtime=...)` passes
   `ledger_path = <run dir>/coordinator-ledger.db` (A2 fix: the R10-era
   domain lane left the ledger disabled). Restart safety improves; disk usage
   grows by one small SQLite file per run. Callers constructing
   `ExecutionCoordinator` directly are unaffected.
2. **`IosTransport` is transport-neutral by default (`wifi=True`).** With no
   USB device visible and exactly one paired Wi-Fi target, connect now
   attempts the in-process RemotePairing/userspace RSD path instead of
   failing with a usbmux-not-found error. Rollback/compat switch: construct
   with `wifi=False` for exact USB-only behavior. Blockers are typed
   (`no-device`, `ambiguous-multiple-devices`, `paired-wifi-visible`,
   `runtime-tunnel-unavailable`); device identity in reports/errors is
   fingerprint-only. Note honestly: the Wi-Fi path is fake-verified only; no
   physical Wi-Fi establishment has been demonstrated yet.
3. **`ExperienceEpisode` schema_version 1 → 2.** New fields (`skill_id`,
   `skill_version`, `effect`, `state`, `error_code`, `macro_id`, `path_id`)
   default empty, so persisted v1 lines still load; new writes are v2.
   `from_json` / `ExperienceStore.load` now reject any record carrying an
   authority-shaped key (`FORBIDDEN_AUTHORITY_KEYS`) instead of loading it —
   deliberate fail-closed tightening, not a format break for clean records.
4. **SkillExecutor attempts can now carry hook errors.** Experience/shadow
   hook failures are bounded-retained in `SkillExecutor.hook_errors`
   (observational); the returned attempt and its safety semantics are
   unchanged.
5. **New journal event types** appear in run journals
   (`run.started`, `run.completed`, `attempt.sent/completed`,
   `execution.*`, `policy.decision`, `sequence.decision`,
   `learning.recorded`, `journal.recovered`, `runtime.*` trace
   projections). Consumers of `events.jsonl` written before Phase A see only
   their old records; nothing is migrated in place (journals are
   append-only and never rewritten).

## 4. State-root / data migration

- Default state root is `~/.praxiom` (override with `PRAXIOM_STATE_ROOT`),
  outside the repository; per-run data lives under
  `runs/<run_id>/` (`events.jsonl`, `summary.json`, `learning_snapshot.json`,
  `artifacts/`, `coordinator-ledger.db`), cross-run episodes under
  `experience/episodes.jsonl`.
- `summary.json` / `learning_snapshot.json` are derived caches: deleting them
  is always safe; they are rebuilt on the next clean close. They are never
  authority.
- No migration step is required or provided for pre-Phase A data: R10-era
  Coordinator ledgers remain readable by the unchanged ledger code; legacy
  run journals do not exist (D1 starts fresh); old episode files load as v1
  records. Corrupt/torn episode lines are rejected as non-reusable evidence
  and counted, never silently dropped or "repaired".
- Journal privacy model is fail-safe by construction: non-token-shaped
  content is fingerprinted (`fp:`), payloads are allowlisted and bounded. If
  a future schema tightens the allowlist, older lines remain readable because
  readers parse per-record and skip malformed/torn tails without rewriting
  bytes.

## 5. Enabling the gated behaviors (later phases — not baseline defaults)

- Bounded sequences: construct the executor/session with
  `sequence_enabled=True` (explicit caller decision; frozen baseline keeps it
  OFF). Limits: 1..`MAX_SEQUENCE_LIMIT` (32) steps per call, default cap 8;
  low-risk + reversible + non-human-gated registry policies only;
  state-sensitive steps collapse to size 1; stale/PARTIAL/UNKNOWN stop with
  no replay (`tests/test_phasea_a5_skill_sequence.py`,
  `tests/test_phasea_integration.py` sequence tests).
- Live adaptive application: only through an explicitly constructed
  `LiveOptimizationGate(enabled=True)`; the module constant
  `LIVE_OPTIMIZATION_ENABLED` stays `False`, and `RunSession` never enables
  the gate. Promotion still requires the real-device baseline evidence
  contract from the frozen design (§8.4 baseline preservation).
- First real-device baseline checklist (carried from the handoff, unchanged):
  telemetry ON, experience extraction ON, shadow ON, adaptive live apply OFF,
  sequence live apply OFF unless separately accepted.

## 6. Rollback notes

- The Phase A change set is additive; reverting the uncommitted working tree
  to HEAD `f5456d0` removes the new surface entirely and restores the exact
  R10-certified behavior (that HEAD is the certification-adjacent docs
  commit; R10 certification evidence itself is untouched by Phase A).
- Per-feature rollback without a full revert: `RunSession` is opt-in
  (don't call it); `IosTransport(wifi=False)` restores USB-only transport;
  `sequence_enabled=False` (default) and the disabled
  `LiveOptimizationGate` keep learning/shadow strictly observational; the
  journal can be ignored by not opening a `RunContext`.
- `ExecutionCoordinator.run_sequence` and the `wifi_tunnel` adapter are the
  only shared-stack additions; removing them restores prior semantics with
  the two known consequences: no true single-call batch (by design) and no
  Wi-Fi Runtime path (the pre-Phase A, honestly-broken state documented in
  the design freeze).

## 7. Non-goals (unchanged from the implementation evidence)

No live adaptive application in Phase A; no Visual V0-V3 capture; no physical
Wi-Fi/USB live-execution evidence claimed; no Phone Harness schema/dashboard/
ETL; no external `tunneld`; no upstream pin change; no seventh Runtime
operation; no second mutation authority; no persistence of trust tokens,
secrets, raw device identifiers, IPs, bundle ids, screen text, or action
payloads; no cross-run analytics store; no commit/push in this pass.
