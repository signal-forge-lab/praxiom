# Praxiom Post-R10 Phase A — Integration Pass Evidence

Date: 2026-09-09

Scope: single shared integration pass wiring the five landed Phase A lanes
(T telemetry, L experience/shadow, S bounded sequences, D transport-neutral
discovery + in-process Wi-Fi RSD, V metadata-only visual hooks) into one
durable closed loop, under the frozen decisions D1=A..D5=A.

Sensitivity: PUBLIC

## What was wired (integration-owned changes)

1. `src/praxiom/agent/coordinator.py` — new `ExecutionCoordinator.run_sequence`
   (frozen D3=A, the previously missing shared seam):
   - whole-sequence preflight via `preflight_specs` before lease/effect
     (any rejection => `SpecValidationError`, zero device calls, zero ledger rows);
   - all specs must share exactly one revision;
   - one lease, one parent `Execution`, one correlated `Attempt`, and exactly
     one `RuntimePort.execute([payload...], expected_revision=R)` call;
   - outcome mapping mirrors `run()`: NONE -> succeeded, PARTIAL -> failed,
     else unknown; port errors (stale/PARTIAL/UNKNOWN) retained fail-closed —
     no continuation, no retry, no replay;
   - evidence carries `action_count`, per-action `action_kinds` (bounded),
     `replayed=False`, `retry_safe=False`, `revision_invalidated=True`;
   - `run_batch()` semantics, the six-op Runtime surface, and
     Runtime-only mutation authority are unchanged.

2. `src/praxiom/session.py` (new) — `RunSession`, the composition layer:
   - A1/A2: `RunContext` (configurable external state root,
     `PRAXIOM_STATE_ROOT`, default `~/.praxiom`) + append-only `RunJournal`;
     `run.started` / `run.completed` events; normal live-run construction now
     enables the durable run-scoped Coordinator attempt ledger
     (`ledger_path = <run dir>/coordinator-ledger.db`);
   - A2: privacy-safe Runtime `Trace` records drained into the journal via
     telemetry bridges (watermarked, oldest first, `recovery` visual hint),
     plus `attempt.completed` / `execution.*` correlation events; the
     Runtime trace projection is state, not a seventh operation;
   - A3: automatic Experience extraction wired through the existing
     `SkillExecutor` hooks; episodes persist under
     `<state-root>/experience/episodes.jsonl` (cross-run, outside the
     per-run D1 layout) via the lane L `ExperienceStore` and journal as
     `learning.recorded`;
   - A4: actual-vs-shadow decisions journaled as `policy.decision` (actual
     decision, shadow recommendation, reason, confidence, batch sizes,
     fallback reason); `LIVE_OPTIMIZATION_ENABLED` stays frozen False and
     the session never constructs an enabled gate — default-off live control;
   - D3=A: `RunSession.execute_sequence` delegates wholly to
     `SkillExecutor.execute_sequence -> ExecutionCoordinator.run_sequence`
     and journals `sequence.decision` (shadow recommended vs actual size,
     requested/steps counters, fallback reason) plus parent
     execution/attempt evidence; feature gate default OFF;
   - D4=A: metadata-only visual hints from the frozen vocabulary via
     `praxiom.visual_hooks` (`post-action`, `recovery`, `learning-change`);
     no capture, no bytes, no paths; artifact refs stay `reserved`;
   - A8: clean close writes `summary.json` + `learning_snapshot.json`
     (derived caches; run duration, observe/execute percentiles, action and
     batch-size histograms, failures by effect/error, fallback reasons,
     policy divergences, learning records, `token_authority_persisted=False`);
   - fail-loud journal semantics: a dead journal raises
     (`JournalClosedError`/`JournalWriteError`) instead of inventing success;
     hook failures stay bounded-retained in `SkillExecutor.hook_errors`;
     the durable Coordinator record is never lost;
   - imports no `praxiom.ios_runtime` module at all: Runtime ports arrive
     fully constructed; no direct Runtime operation call exists in the module.

3. `src/praxiom/telemetry/bridges.py` — additive optional
   `visual_hint` kwarg on `record_attempt` (D4=A metadata marker);
   existing bridge behavior unchanged.

4. `tests/test_phasea_a5_skill_sequence.py` — the
   `sequence-coordinator-unavailable` test now uses a minimal seam-less
   coordinator double: the real `ExecutionCoordinator` ships `run_sequence`
   (this integration), and seam-less coordinators still fail closed. All
   other lane S assertions untouched.

## Transport-neutral discovery / in-process Wi-Fi RSD (D5=A)

Lane D's wiring is verified (not redesigned) by the integration suite:
`IosTransport` selects through `DeviceDiscovery` (USB preferred, one paired
Wi-Fi target otherwise), the Wi-Fi path feeds the unchanged WDA/AppService
Runtime stack through `wifi_tunnel.RemotePairingUserspaceRsdTunnel`
(subclass of the pinned upstream `UserspaceRsdTunnel`), with no external
`tunneld` process, no Phone Harness fallback, no second mutation authority,
and privacy-safe identity handling. No physical-device evidence is claimed.

## Tests and verification

- `tests/test_phasea_integration.py` (new, 17 deterministic tests):  one-lease/one-Runtime-call sequences; zero-call whole-sequence preflight;
  stale/PARTIAL/UNKNOWN fail-closed with no replay; durable ledger rows +
  restart-safe inspection; cancelled/closed fail-closed; unchanged
  `run_batch`; full single-action closed loop (journal, ledger ON, policy,
  learning, summary, snapshot); sequence closed loop + state-sensitive
  size-1 fallback; preflight rejection journaling; dead-journal fail-loud
  with intact safety record; watermarked trace draining; privacy scan of
  durable records (no secrets/UDIDs/IPs/bundle ids/screen text/raw
  revisions; `fp:` fingerprints only); cross-run Experience rebinding with a
  fresh live token (provenance/version mismatch fails closed); discovery/
  Wi-Fi wiring guards; six-op Runtime surface guard; `session.py` boundary
  guard (no ios_runtime import, no banned tokens, no direct Runtime op calls).
- Full suite: **472 passed, 1 deselected, 0 failed** (`python -m pytest -q`).
  The single deselected test
  (`tests/test_package.py::test_check_provenance_detects_phone_harness_reference`)
  depends on pytest's `tmp_path` factory, which this execution sandbox denies
  (documented environmental precedent retained from the lane evidence; the
  suite otherwise runs without any basetemp override). Its substance was
  verified directly in a workspace scratch dir: `find_violations()` reports
  exactly one hit (`bad.py:1: import phone_harness`) for a planted
  violation, and `scripts/check_provenance.py` passes on the real tree.
- `scripts/check_provenance.py` — OK.
- `scripts/check_agent_boundaries.py` — OK (includes the new
  `run_sequence` seam: `self._rt.execute(..., expected_revision=...)` only
  inside the Coordinator, no unrevisioned execute anywhere).
- `python -m compileall src tests scripts` — OK.

## Preserved invariants

- Runtime public surface exactly `status, observe, execute, invalidate,
  recover, close` (AST-guarded test).
- Only Skill/Coordinator/Runtime mutate device state; telemetry, learning,
  shadow, discovery, visual hooks, and session wiring are observational.
- R0-R10 behavior and `run_batch` semantics unchanged (regression-tested).
- No SkillTrustToken/secret/device-id/IP/bundle-id/screen-text/payload is
  ever persisted; persisted evidence cannot forge authority (fresh-token
  rebind required, machine-checked).
- No Phone Harness dependency or external tunneld; discovery is a read-only
  library-level seam.
- D1=A..D5=A preserved exactly; no frozen certification evidence rewritten.

## Repository state

All changes left uncommitted and unpushed for verification, review,
evidence retention, and the finalizer. Scratch dirs (`.tmp-*`) are
disposable test residue, not part of the change set.
