# Phase A Lane T — Durable Run Telemetry Journal, Correlation Primitives, Rough Summary (A1/A2/A8)

Date: 2026-09-09

Status: **IMPLEMENTED / DETERMINISTICALLY VERIFIED — left uncommitted for the single integration owner**

Sensitivity: **PUBLIC**

Scope authority: `docs/evidence/20260909_post-r10-phase-a-design-freeze.md` (D1=A, D4=A),
`docs/design/20260909_post-r10-phase-a_closed-loop-telemetry_orchestrator_handoff.md` (A1/A2/A8).
Lane T implements **only** A1 (RunContext + durable telemetry journal), the lane-T portions of
A2 (privacy-safe correlation fields and ledger integration primitives), and A8 (rough
improvement summary + learning snapshot). Shared coordinator/skill wiring is explicitly **not**
owned by this lane and was not edited.

## Change set (new files only; zero edits to existing files)

- `src/praxiom/telemetry/__init__.py` — observational package surface + authority rules.
- `src/praxiom/telemetry/context.py` — `RunContext`, `PRAXIOM_STATE_ROOT` / `~/.praxiom` state
  root resolution, per-run layout (`events.jsonl`, `summary.json`, `learning_snapshot.json`,
  `artifacts/`, run-scoped `coordinator-ledger.db` path).
- `src/praxiom/telemetry/journal.py` — `RunJournal`: append-only, schema-versioned,
  sequence-numbered, deterministically serialized JSONL; fail-safe allowlists; crash/restart
  tolerance; atomic derived-cache writes.
- `src/praxiom/telemetry/bridges.py` — duck-typed correlation primitives
  (`record_trace_record`, `record_runtime_trace`, `record_attempt`, `record_execution`);
  no import of `ios_runtime`/`agent`/`skill`/`domain`.
- `src/praxiom/telemetry/summary.py` — `build_summary` (A8 fields) and
  `build_learning_snapshot` (evidence facts only, `token_authority_persisted: false`).
- `tests/test_phasea_telemetry.py` — 19 deterministic tests (injected clocks; isolated
  workspace scratch state roots).

## Design conformance

- **D1=A**: separate append-only per-run JSONL journal; Coordinator SQLite ledger remains the
  safety/restart authority. The journal is observational only — it never invents success and
  never gains mutation authority (append failures raise `JournalWriteError`; sequence does not
  advance; nothing is replayed).
- **D4=A hooks**: envelope carries `run_id`/`event_id`/`seq`, UTC + monotonic timestamps,
  `parent_event_id`/`correlation_id`, `execution_id`/`attempt_id`, domain/behavior/skill
  identity, fingerprinted `revision_ref`, phase, `visual_hint` (bounded allowlist:
  `post-action`, `validation-mismatch`, `recovery`, `learning-change`), and metadata-only
  `artifact_refs` (`artifact_id`/`kind`/`status`/`format` — no path/bytes/URL key exists).
  No media pipeline was implemented.
- **Runtime surface untouched**: zero edits under `src/praxiom/ios_runtime/`; `runtime.trace`
  is consumed read-only via duck-typed projections. Existing six-operation surface test remains
  green.
- **State root**: configurable via `PRAXIOM_STATE_ROOT`, default `~/.praxiom` (outside the
  repository by default); tests use disposable workspace scratch roots.

## Privacy enforcement (fail-safe, machine-checked)

- Structural fields (`event_type`, `phase`) must match bounded allowlists or construction
  fails loudly; content fields are token-shaped (`[A-Za-z0-9_.:@+-]{1,96}`), otherwise replaced
  by a deterministic truncated SHA-256 fingerprint (`fp:` + 16 hex).
- `revision_ref` is always a fingerprint of the opaque revision token; raw revision/element
  tokens are never journaled.
- `payload` accepts only an explicit machine-key allowlist with bounded scalars / token strings
  / ≤16-item scalar lists / one bounded `counters` map; everything else is dropped and counted
  (`redacted_keys`, `truncated_items`); a still-oversized payload collapses to its counters.
- Tests prove UDID-shaped 40-hex values, secrets, bundle ids, screen text, action payloads, and
  token-shaped authority strings have no path into `events.jsonl`, `summary.json`, or
  `learning_snapshot.json`; the learning snapshot stores only evidence facts (skill id/version,
  behavior/domain, effect counts, bounded execution-id references, timestamps) and carries the
  constant `token_authority_persisted: false` marker.

## Crash / restart tolerance

- Canonical serialization (`sort_keys`, compact separators, `ensure_ascii`, `allow_nan=False`);
  each event flushed and fsynced before `seq` advances; existing bytes are never rewritten
  (byte-prefix property is asserted).
- Reopen scans existing history: a torn tail (partial line) or malformed line is preserved on
  disk, skipped, counted, documented with a `journal.recovered` event, and the sequence
  continues after the last valid record. Summaries written after restart cover pre-crash
  history (in-memory list is a disk-replayed cache).
- `close()` closes the journal first, then writes `summary.json` / `learning_snapshot.json`
  atomically (temp + replace) as derived caches only. `abandon()` simulates process death for
  tests.

## A2 primitives delivered (wiring intentionally deferred)

- `RunContext.ledger_path`: run-scoped Coordinator ledger path; the test proves
  `ExecutionCoordinator(ledger_path=ctx.ledger_path)` is durable, reopens with
  `ledger_schema_version == 1`, and survives restart inspection — without this lane editing any
  shared coordinator/executor file.
- Bridges correlate Runtime trace → execution → attempt → domain behavior by ids/timestamps/
  fingerprinted revision references; per-attempt `planned`/`sent`/`completed` states, effects
  (`NONE`/`PARTIAL`/`UNKNOWN`), and machine error codes map onto the journal envelope.
- Production call sites (live run construction supplying the run-scoped `ledger_path`, runtime
  trace/attempt emission points) are left to the single integration owner per the handoff.

## A8 rough summary fields implemented

Run duration; observe and execute counts with total/median/p90 (R9 percentile convention);
action count and execute batch-size histogram; full-observe vs cheap-validation counts; shadow
recommended vs actual sequence sizes; recovery attempts/successes; failures by effect and by
machine error class; fallback reasons; policy/shadow divergence pairs; learning candidate kinds
and reuse recommendations; artifact refs reserved; event totals by type plus journal integrity
(torn/malformed counts).

## Verification (this session, source HEAD `f5456d0` + in-flight sibling lanes)

- Lane tests: `tests/test_phasea_telemetry.py` — **19/19 passed**.
- Full deterministic suite (shared tree including sibling lanes' in-flight files):
  **455 passed, 1 deselected** (`tests/test_package.py::test_check_provenance_detects_phone_harness_reference`
  — see environment note below).
- `scripts/check_provenance.py`: **OK** (no historical-product reference in production paths).
- `scripts/check_agent_boundaries.py`: **OK** (core packages respect the Runtime boundary).
- `python -m compileall src tests`: **OK**.
- Telemetry-specific extra scans: no banned edge tokens in `src/praxiom/telemetry/` (none); AST
  test proves the package imports no Runtime/Agent/Skill/Adaptive/Domain module and makes no
  mutation-shaped calls.
- Diff footprint vs HEAD: additions only (`src/praxiom/telemetry/**`,
  `tests/test_phasea_telemetry.py`); no modifications to any existing tracked file by this lane;
  nothing committed; no remote push.

## Environment note (fixture-level, not product behavior)

This execution sandbox denies pytest's `tmp_path` factory (same session-environment denial
already documented in `docs/evidence/20260908_r10-bounded-real-workflow.md`). The single
tmp_path-dependent legacy test was therefore deselected for the suite run; its substance was
verified directly via `scripts/check_provenance.py` (OK above). Lane-T tests avoid `tmp_path`
entirely (workspace-local scratch roots), matching the established workaround in
`tests/test_agent_boundaries.py` / `tests/test_r6_review_repairs.py`. Disposable scratch was
removed where the sandbox permits; pid-scoped leftovers under `.tmp-phasea-telemetry/` are
untracked scratch, not part of the change set.
