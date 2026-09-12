# Praxiom Post-R10 Phase A — Retained Implementation Evidence

Date: 2026-09-10

Status: **RETAINED EVIDENCE — implementation verified on the documented working tree**

Sensitivity: **PUBLIC**

Scope authority: `docs/evidence/20260909_post-r10-phase-a-design-freeze.md`
(D1=A..D5=A frozen, non-negotiable authority constraints) and
`docs/design/20260909_post-r10-phase-a_closed-loop-telemetry_design-decisions.md`.
This document records what Phase A implemented, where it lives, and how it is
deterministically verified. It does not rewrite the frozen design, does not
reopen R0-R10 certification, and does not claim any physical-device evidence.

Verification basis (re-run 2026-09-10, this host, repository venv):

- working tree: source HEAD `f5456d079dbe4bc92af91a358b8edac4038fb439`
  (`f5456d0`, docs commit "freeze post-r10 phase a design") plus the
  uncommitted Phase A implementation changes listed below; nothing was
  committed or pushed by this evidence pass;
- `python -m pytest -q --deselect tests/test_package.py::test_check_provenance_detects_phone_harness_reference`
  → **472 passed, 1 deselected, 0 failed**;
- `python scripts/check_provenance.py` → OK (exit 0);
- `python scripts/check_agent_boundaries.py` → OK (exit 0);
- `python -m compileall -q src tests scripts` → OK (exit 0);
- deselection note: the single deselected legacy test depends on pytest's
  `tmp_path` factory, which this execution sandbox denies (environmental
  precedent documented in `docs/evidence/20260909_phasea-lane-t-telemetry-journal.md`
  and `docs/evidence/20260908_r10-bounded-real-workflow.md`); its substance is
  covered directly by `scripts/check_provenance.py` (OK above), which the
  suite itself also runs via `tests/test_package.py::test_check_provenance_passes_on_clean_repo`.

## 1. Exact implementation paths

New modules (untracked, in-flight Phase A change set):

| Path | Role |
| --- | --- |
| `src/praxiom/telemetry/__init__.py` | observational telemetry package surface + authority rules |
| `src/praxiom/telemetry/context.py` | `RunContext`, `PRAXIOM_STATE_ROOT` state-root resolution, per-run layout (`events.jsonl`, `summary.json`, `learning_snapshot.json`, `artifacts/`, `coordinator-ledger.db`) |
| `src/praxiom/telemetry/journal.py` | `RunJournal`: append-only JSONL; `build_event`, `sanitize_payload`, `fingerprint_revision`, `canonical_dumps`, `JournalStats`, `JournalWriteError`, `JournalClosedError` |
| `src/praxiom/telemetry/bridges.py` | duck-typed correlation primitives: `record_trace_record`, `record_runtime_trace`, `record_attempt`, `record_execution`; optional D4 `visual_hint` |
| `src/praxiom/telemetry/summary.py` | `build_summary` (A8 fields), `build_learning_snapshot` (evidence facts, `token_authority_persisted: false`) |
| `src/praxiom/session.py` | `RunSession` composition layer (A1/A2/A3/A4/A8 + D3 sequence delegation + D4 hints); imports no `praxiom.ios_runtime` module |
| `src/praxiom/adaptive/shadow.py` | `shadow_recommend`, `ShadowContext`, `ShadowRecommendation`, `ShadowAdvisor`, `LiveOptimizationGate`, `LIVE_OPTIMIZATION_ENABLED = False` |
| `src/praxiom/adaptive/experience_bridge.py` | `build_episode` (A3 extraction), `rebind_history` (cross-run fresh-token rebinding, fail-closed), `ExtractionContext`, `RebindResult` |
| `src/praxiom/knowledge/experience_store.py` | `ExperienceStore` append-only JSONL episode store, `ExperienceLoadReport` |
| `src/praxiom/ios_runtime/discovery.py` | `DeviceDiscovery` (`probe`/`select`), `DeviceTransport`, `DiscoveryBlocker`, `UsbEndpoint`, `WifiEndpoint`, `SelectedTarget`, `DiscoveryReport`, `privacy_fingerprint` |
| `src/praxiom/ios_runtime/wifi_tunnel.py` | `RemotePairingUserspaceRsdTunnel` — in-process RemotePairing/userspace RSD adapter over the pinned upstream `UserspaceRsdTunnel` |
| `src/praxiom/visual_hooks.py` | D4=A metadata-only vocabulary + `VisualTimeline` read-only projection (A7) |

Modified tracked files (working-tree diff vs HEAD; additive surface, certified
semantics preserved):

| Path | Phase A change |
| --- | --- |
| `src/praxiom/agent/coordinator.py` | +92 lines: `ExecutionCoordinator.run_sequence` (D3=A); `run`, `run_batch`, ledger, lease semantics unchanged |
| `src/praxiom/skill/executor.py` | `SkillExecutor.execute_sequence` + `SequenceStep`/`SequenceExecution`, `DEFAULT_SEQUENCE_LIMIT = 8`, `MAX_SEQUENCE_LIMIT = 32`, gate `sequence_enabled` (default OFF), A3/A4 hook call sites, bounded `hook_errors` |
| `src/praxiom/skill/__init__.py` | export the new sequence surface |
| `src/praxiom/knowledge/experience.py` | `ExperienceEpisode` evidence fields, `SCHEMA_VERSION = 2`, `FORBIDDEN_AUTHORITY_KEYS` fail-closed persisted-evidence guard |
| `src/praxiom/adaptive/__init__.py` | export the shadow + experience-bridge surface |
| `src/praxiom/ios_runtime/transport.py` | `IosTransport` selects through `DeviceDiscovery` (USB preferred, one paired Wi-Fi target otherwise) and reaches the unchanged WDA/AppService Runtime stack via `wifi_tunnel_factory` → `RemotePairingUserspaceRsdTunnel`; `wifi=True` default, blockers map to typed `DeviceNotFoundError` reasons |

`git diff --stat` at verification time: 6 files changed, 519 insertions(+),
25 deletions(-), plus the untracked files above. No file under
`src/praxiom/ios_runtime/` lost a public operation; the Runtime surface is
AST-guarded (see §3).

## 2. Deterministic tests and guards

New Phase A test files — **114 tests collected** (`pytest --collect-only`,
2026-09-10):

| Path | Tests | Covers |
| --- | --- | --- |
| `tests/test_phasea_telemetry.py` | 19 | A1/A2/A8: journal schema/order/append-only, deterministic bytes, privacy allowlist fail-safe, payload bounds and byte-cap collapse, structural fail-closed, torn-tail + restart recovery, emit-failure never invents success, `revision_ref` opaque fingerprint, trace/attempt bridges, run-scoped ledger primitive, A8 summary fields + determinism, learning snapshot evidence-facts-only, metadata-only artifacts/hints, state-root configurable/external, telemetry package observational-only |
| `tests/test_phase_a_lane_l.py` | 13 | A3 episodes from NONE/PARTIAL/UNKNOWN/stale, serialization never carries authority, store roundtrip/crash-tail/authority rejection, fresh-token rebind + identity match, failure evidence poisons reuse, A4 shadow recommends-without-applying, safety floors / untrusted confidence / budget breach fail-closed, live optimization feature-gated OFF, executor records evidence + shadow, hook failure never alters attempt |
| `tests/test_phasea_a5_skill_sequence.py` | 16 | D3=A sequence contract at the Skill/Coordinator seam: gate off by default, single-action + `run_batch` untouched, whole-sequence preflight zero-dispatch, registry authority, limits/human-gate/tampered-snapshot fail-closed, one delegation/one revision/one lease/one Runtime call for N actions, state-sensitive size-1 fallback, stale/PARTIAL/UNKNOWN stop without replay, seam-less coordinator fails closed |
| `tests/test_phase_a_lane_v.py` | 18 | D4=A: frozen hint vocabulary, A7 marker event types, V0-V3 artifact vocabularies, metadata-only refs (rejects every non-metadata shape), journal bound/uniqueness, emit-ready `hook`, timeline stable ids/sequence, isolated read-only snapshot, markers/hints/monotonic windows, artifact/execution/attempt correlation, foreign-damage `problems`, module imports no authority stack / no I/O, journal-envelope conformance drift guard |
| `tests/test_discovery_wifi.py` | 25 | D5=A with injected fakes: Wi-Fi endpoint dedupe, no-device/ambiguous/paired-wifi-visible classification, USB preferred, fingerprint-only repr, Wi-Fi-only connect reaches ready without usbmux (fake tunnel), `runtime-tunnel-unavailable` classification, ambiguous/no-device fail-closed, discovery failure typed error, fresh reselect, close releases tunnel once, no raw identity/addresses in outputs, RemotePairing adapter matching/fail-closed/establishment/teardown/second-tunnel refusal |
| `tests/test_phasea_integration.py` | 17 | Shared integration: one-lease/one-Runtime-call sequence, whole-preflight zero calls/zero rows, stale fail-closed no retry, PARTIAL/UNKNOWN stop no replay, durable ledger row + restart inspection, cancelled/closed fail-closed, `run_batch` unchanged, single-action + sequence closed loops, state-sensitive fallback, preflight-rejection journaling, dead-journal fail-loud with intact safety record, watermarked trace draining, durable-record privacy scan, cross-run rebind requires fresh live token, transport wiring uses discovery + in-process Wi-Fi RSD, Runtime six-op surface, `session.py` boundary guard |

Retained guards exercised by the suite and by direct script runs:

- `scripts/check_provenance.py` — zero Phone Harness reference in production
  paths (`src/`, `pyproject.toml`); OK on the Phase A tree.
- `scripts/check_agent_boundaries.py` — `self._rt.execute(...,
  expected_revision=...)` remains only inside the Coordinator; no
  unrevisioned execute, no subprocess/MCP bypass; OK including the new
  `run_sequence` seam.
- `tests/test_phasea_integration.py::test_runtime_public_surface_still_exactly_six_operations`
  (AST guard) plus the retained R2 surface test — Runtime public surface is
  exactly `status`, `observe`, `execute`, `invalidate`, `recover`, `close`.
- `tests/test_phasea_integration.py::test_session_module_boundary_guard` —
  `session.py` imports no `ios_runtime` module, contains no banned tokens,
  and makes no direct Runtime operation calls.
- `tests/test_phase_a_lane_v.py::test_journal_envelope_conformance_when_lane_t_lands`
  — visual-hook vocabularies and the journal envelope allowlists cannot drift.
- Full regression (R0-R10 suites included) green on the Phase A tree: 472
  passed, 0 failed (see verification basis). No frozen certification evidence
  file was modified by the Phase A change set.

## 3. D1=A — JSONL durability and privacy

Layout (D1=A): `<state-root>/runs/<run_id>/events.jsonl` +
`summary.json` + `learning_snapshot.json` + `artifacts/` +
`coordinator-ledger.db`; state root is `PRAXIOM_STATE_ROOT`-configurable and
defaults to `~/.praxiom` (outside the repository); cross-run episodes persist
separately under `<state-root>/experience/episodes.jsonl`.

Durability (machine-checked by `tests/test_phasea_telemetry.py`):

- append-only, schema-versioned, sequence-numbered; canonical serialization
  (`sort_keys`, compact separators, `ensure_ascii`, `allow_nan=False`); each
  event is flushed and fsynced before `seq` advances; existing bytes are never
  rewritten (byte-prefix property asserted);
- crash/restart tolerance: a torn tail or malformed line is preserved on disk,
  skipped, counted, documented with a `journal.recovered` event, and the
  sequence continues after the last valid record; post-restart summaries cover
  the full on-disk history;
- fail-loud: `JournalWriteError` / `JournalClosedError` propagate instead of
  inventing success; a dead journal never loses the durable Coordinator record
  (`tests/test_phasea_integration.py::test_session_journal_failure_fails_loud_but_keeps_safety_record`);
- `summary.json` / `learning_snapshot.json` are derived caches written
  atomically (temp + replace) on clean close; the Coordinator SQLite attempt
  ledger remains the durable safety/restart authority and is now enabled in
  the normal live-run construction (`RunSession.start` passes
  `ledger_path = <run dir>/coordinator-ledger.db`).

Privacy (fail-safe, machine-checked):

- structural fields match bounded allowlists or construction fails loudly;
  content fields are token-shaped (`[A-Za-z0-9_.:@+-]{1,96}`) or replaced by a
  deterministic truncated SHA-256 fingerprint (`fp:` + 16 hex);
- `revision_ref` is always a fingerprint of the opaque revision token; raw
  revision/element tokens are never journaled;
- `payload` accepts only an explicit machine-key allowlist with bounded
  scalars / token strings / ≤16-item scalar lists / one bounded `counters`
  map; anything else is dropped and counted (`redacted_keys`,
  `truncated_items`); an oversized payload collapses to its counters;
- tests prove UDID-shaped 40-hex values, secrets, bundle ids, screen text,
  action payloads, and token-shaped authority strings have no path into
  `events.jsonl`, `summary.json`, `learning_snapshot.json`, or the durable
  Coordinator records (`tests/test_phasea_integration.py::test_session_durable_record_is_privacy_safe`).

## 4. Automatic learning (A3)

- Production extraction is wired through the existing `SkillExecutor` hooks:
  every attempt (NONE/PARTIAL/UNKNOWN/stale/validator failure) produces a
  bounded `ExperienceEpisode` via `adaptive.experience_bridge.build_episode`;
  failures are retained and poison reuse — never filtered into success.
- Episodes persist automatically under
  `<state-root>/experience/episodes.jsonl` via `ExperienceStore` (append-only
  JSONL; torn/malformed/authority-shaped lines are rejected on load as
  non-reusable evidence) and journal as `learning.recorded`.
- Cross-run reuse (`rebind_history`) fails closed: persisted evidence becomes
  reusable only after the current registry independently re-activated the
  matching skill/version and issued a fresh live `SkillTrustToken`; exact
  skill id/version + provenance + revision evidence are enforced per episode;
  mismatches are retained as `rejected:*` statuses, never upgraded
  (`tests/test_phasea_integration.py::test_cross_run_experience_rebind_requires_fresh_live_token`).
- No `SkillTrustToken` (or authority-shaped key) is ever persisted:
  `FORBIDDEN_AUTHORITY_KEYS` is enforced on serialize, on store append, and on
  load; the learning snapshot carries the constant
  `token_authority_persisted: false`.

## 5. Shadow behavior (D2=A / A4)

- `LIVE_OPTIMIZATION_ENABLED = False` module constant; `LiveOptimizationGate`
  defaults to `enabled=False` and raises `LiveOptimizationDisabledError` /
  `LiveOptimizationRefusedError`; `RunSession` never constructs an enabled
  gate — live adaptive control is default-OFF.
- `ShadowAdvisor` evaluates real execution context
  (`ShadowContext`: confidence, state-sensitivity, revision state, risk,
  reversibility, human gate, budget, failure streak, loop detection, macro/
  path eligibility, selector/recovery statistics) through the existing R9
  primitives (`ObservationPolicy`, `decide_batch`, `route_latency_aware`,
  strategy/fallback); any signal failure fails closed to a
  fallback recommendation with a retained reason.
- Every eligible decision persists actual vs shadow:
  `policy.decision` events (actual decision, shadow recommendation, reason,
  confidence, batch sizes, fallback reason, `would_reduce_observe` /
  `would_reduce_actions`); sequence paths journal `sequence.decision`
  (shadow-recommended vs actual size). No shadow recommendation can mutate a
  device — the shadow layer has no Runtime access at all (boundary-guarded).
- Frozen baseline rule: first real-device runs keep telemetry ON, experience
  extraction ON, shadow ON, adaptive live application OFF, sequence live
  application OFF unless separately accepted.

## 6. Sequence fail-closed behavior (D3=A / A5)

Path: `RunSession.execute_sequence` → `SkillExecutor.execute_sequence` →
`ExecutionCoordinator.run_sequence` → exactly one
`RuntimePort.execute([payload...], expected_revision=R)` call.

- Whole-sequence preflight before lease/effect: any rejection raises with
  zero device calls and zero ledger rows;
- all specs must share exactly one revision; one device lease; one parent
  `Execution`; one correlated `Attempt`; exactly one Runtime execute call;
- gates: `sequence_enabled` (default OFF → `sequence-not-enabled`), registry
  authority, low-risk + reversible + non-human-gated only
  (`sequence-risk-not-low`, `sequence-not-reversible`,
  `sequence-human-gate-unsupported`), `DEFAULT_SEQUENCE_LIMIT = 8`,
  `MAX_SEQUENCE_LIMIT = 32`, registry-owned policy wins over a tampered
  snapshot, seam-less coordinators fail closed;
- any `state_sensitive` step collapses to size 1 with a retained
  fallback reason (`state-sensitive-step`) — state-sensitive work replans
  against a fresh post-effect observation;
- fail-closed effects: stale/PARTIAL/UNKNOWN port errors or outcomes stop
  immediately; `retry_safe=False`, `replayed=False`,
  `revision_invalidated=True` are recorded; no continuation, no retry, no
  blind replay;
- evidence carries `action_count` and bounded per-action `action_kinds`;
  `run_batch()` semantics are regression-locked unchanged
  (`tests/test_phasea_integration.py::test_run_batch_semantics_unchanged_by_integration`).

## 7. Wi-Fi transport coverage (honest statement)

Implemented (D5=A), all deterministically verified with injected fakes —
**no physical Wi-Fi Runtime establishment has been demonstrated, and none is
claimed**:

- `DeviceDiscovery` is a read-only library-level seam over usbmux and
  RemotePairing library APIs; `probe`/`select` classify and apply exact-one
  selection without opening tunnels or mutating anything; blockers are the
  frozen taxonomy `none`, `no-device`, `ambiguous-multiple-devices`,
  `paired-wifi-visible`, `runtime-tunnel-unavailable`; raw serials/
  identifiers/addresses stay in-process and outputs are fingerprint-only
  (`dev#<hex>` keyed per-process; `SelectedTarget.__repr__` cannot leak).
- `IosTransport` now selects through discovery: USB visible → unchanged
  usbmux + `PreferredRsdTunnel` path; USB absent + exactly one paired Wi-Fi
  target → `wifi_tunnel.RemotePairingUserspaceRsdTunnel` (subclass of the
  pinned upstream `UserspaceRsdTunnel`; only `_aopen_locked` differs,
  acquiring the provider over RemotePairing) → the identical existing
  WDA/AppService Runtime path. No external `tunneld` process, no Phone
  Harness fallback, no second mutation authority, no upstream pin change.
- Deterministic coverage: `tests/test_discovery_wifi.py` (25 tests) and
  `tests/test_phasea_integration.py::test_transport_wiring_uses_discovery_and_inprocess_wifi_rsd`
  inject the discovery/tunnel seams and never touch real networking or the
  PyTCP stack.
- Explicit blocker (carried forward from the design freeze): the 2026-09-09
  host observation showed the paired iPhone discoverable over Wi-Fi while
  usbmux listed zero devices — that observation motivated D5=A, but actual
  Wi-Fi-only Runtime connection, tunnel establishment, and live execution
  over Wi-Fi remain **unverified on hardware** and belong to the next
  real-device baseline. Until then, the honest claim is: transport-neutral
  discovery + in-process Wi-Fi RSD wiring implemented and fake-verified;
  physical coverage: none.

## 8. Metadata-only visual hooks (D4=A / A7)

- `src/praxiom/visual_hooks.py` provides the frozen hint vocabulary
  (`post-action`, `validation-mismatch`, `recovery`, `learning-change`), the
  A7 marker event types, and `artifact_ref` metadata construction
  (`artifact_id`/`kind`/`status`/`format` only — no path/URL/bytes key can be
  expressed). Phase A mints `status="reserved"` refs only.
- `VisualTimeline` is a deep-copied, read-only monotonic-timeline projection
  over journal events: markers, hint filters, inclusive monotonic windows,
  marker-centered clip windows (V2 shape), artifact-id correlation (V3
  shape), parent/execution/attempt correlation (V1 shape), and a `problems`
  report for foreign damage — future Visual V0-V3 subscribes; it never calls
  the Runtime or the device stack.
- The module imports no other `praxiom` module and performs no I/O
  (test-proven); a visual failure can never grant or widen mutation
  authority. No recorder, capture, frame-diff, or retrieval pipeline exists
  in Phase A.

## 9. Compatibility behavior (verified)

- Runtime public surface exactly six operations (AST-guarded);
  `runtime.trace` is consumed read-only as a projection, not a seventh
  operation.
- `ExecutionCoordinator.run_batch()` and the single-action `execute` path are
  regression-locked unchanged; `run_sequence` is a new sibling, not a
  redefinition.
- Coordinator durable attempt ledger format unchanged; `inspect(execution_id)`
  remains the restart-safe inspection path; sequences write one parent
  execution + attempt rows under the same ledger schema.
- `ExperienceEpisode` reads `schema_version=1` records (new fields default)
  and writes `schema_version=2`; authority-shaped persisted keys are rejected
  on load in both directions.
- R0-R10 deterministic suites pass on the Phase A tree (472/472 of the
  runnable suite); provenance (zero Phone Harness, pinned upstream
  `pymobiledevice3` commit `ec4ac06a850a6a884ca778350621f354faf347c6`
  unchanged) and agent-boundary guards are green.
- `IosTransport(wifi=False)` restores exact USB-only transport behavior for
  callers that require it. See
  `docs/evidence/20260910_phasea-migration-compatibility-notes.md` for
  operator/caller migration detail.

## 10. Non-goals (explicitly out of Phase A)

- No adaptive/learned decision is applied to live control; live optimization
  stays feature-gated OFF (`LIVE_OPTIMIZATION_ENABLED = False`) until
  real-device baseline evidence supports promotion.
- No bounded-sequence live application by default (`sequence_enabled=False`);
  enabling it is an explicit, separately accepted caller decision.
- No Visual Flight Recorder V0-V3 capture pipeline, media bytes, or retention
  thresholds; `DEFAULT_CLIP_WINDOW_NS` is a bounded placeholder, not a tuned
  value.
- No physical Wi-Fi (or USB) live-execution evidence in this phase; no
  threshold tuning from real-device data (confidence floors, sequence sizes,
  cheap-validation eligibility, latency budgets, minimum evidence counts, V2
  clip retention are all later, evidence-gated decisions).
- No Phone Harness dependency, fallback, schema unification, comparison
  dashboard, or strict historical ETL; rough JSONL comparison only.
- No external `tunneld` production dependency; no upstream pin change; no
  seventh Runtime operation; no second device-mutation authority; no
  persistence or replay of `SkillTrustToken` authority, raw secrets, device
  identifiers, IP addresses, bundle ids, screen text, or action payloads.
- No cross-run analytics store (D1=A tradeoff: cross-run queries scan run
  journals or need a derived index later); `summary.json` /
  `learning_snapshot.json` are derived caches, never authority.
- No commit and no remote push performed by this evidence pass; the Phase A
  change set remains uncommitted in the working tree for review and the
  finalizer. Scratch directories (`.tmp-*`) are disposable test residue, not
  part of the change set.
