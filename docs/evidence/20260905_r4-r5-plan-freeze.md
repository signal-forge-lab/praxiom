# R4 + R5 Plan Freeze — smallest evidence-backed implementation plan

- Date: 2026-09-05
- Authority: `docs/design/20260904_r4-r5_orchestrator_handoff.md` (primary),
  `docs/design/20260904_r4-r5_orchestrator_prompt.md`
- Sensitivity: **PUBLIC**
- Status: **PLAN FROZEN — no production change made by this document**
- Pre-plan Git baseline: `4273f2d` (HEAD), tree **clean**
  (`git status --short` empty); diff vs `acc16b8` was exactly the two
  orchestrator docs (667 insertions, 0 production changes). The only intended
  plan-freeze change is this documentation file; no production file is changed.

This document synthesizes the three Phase-A current-state audits
(contract/evidence, runtime/test, host/device/provenance), each re-verified
against live source rather than cached statements, and freezes the minimal
work delta for R4 (20 pts) + R5 (7 pts). **Do not implement production
changes under this plan without the Phase-B lanes; do not start R6+.**

## 1. Audit synthesis (re-opened source, 2026-09-05)

### Audit 1 — contract / evidence (vs R2 contract + R3 completion)

- R2 contract is readable at
  `phone-harness-windows/phone-harness/docs/design/20260831_r2-native-ios-runtime-contract.md`
  and remains the behavior authority. R3 completion report
  (`docs/evidence/20260901_r3-native-ios-runtime-v0-completion.md`, 33/33,
  R3_COMPLETE) plus `20260903_r3-08-attached-device-pass.md` and
  `20260903_praxiom-rename.md` are consistent with current source.
- Public boundary in `src/praxiom/ios_runtime/runtime.py` is exactly the six
  async operations (`status`, `observe`, `execute`, `invalidate`, `recover`,
  `close`) with `trace` as a state-projection attribute. **No contract change
  is justified by any current evidence** — the six-operation boundary is
  preserved into R4/R5.
- Deterministic A01–A10 all pass (fake transport); A11 real-device slice
  passed twice (R3-08 + rename regression: observe → Home → observe →
  launch Settings → observe → close, trace errors = 0).
- R4-06 artifact does not exist yet: no old-vs-new required-behavior report
  under `docs/evidence/`. R0/R1/R3 historical references needed for it are
  present in-tree or in the readable historical tree.

### Audit 2 — runtime / tests (source re-opened)

Re-read: `models.py`, `transport.py`, `observation.py`, `executor.py`,
`runtime.py`, `trace.py`, `scripts/check_provenance.py`, all 8 test files,
`tests/fixtures/` (fixture JSON + PROVENANCE.md present).

- Architecture matches the handoff target diagram: runtime → observation /
  executor / transport / trace → unmodified upstream `pymobiledevice3`.
  No Phone Harness import/subprocess/MCP/fallback/shim in `src/` (standalone
  guard run: PASS, exit 0).
- Whole-batch preflight, mandatory `expected_revision`, revision-bound refs,
  batch limit (default 32), no-blind-replay (`EFFECT_UNKNOWN`/`ACTION_FAILED`
  with `retry_safe=False`), owned-resource close, privacy-allowlisted trace —
  all present in source and covered deterministically.
- Per-cell deterministic coverage vs gap (detail in §3): transport lifecycle,
  observe/revision, all 7 primitives + batch rules, failure/recovery
  semantics, and trace counters are green on fakes. One deterministic R2
  contract gap is proven: `invalidate(reason)` validates only non-empty strings
  and discards the reason, while R2 §4.4 requires the machine-oriented reason
  to be bounded and retained for traceability. **What fakes cannot prove** —
  real RSD/WDA plumbing, on-hardware primitive effects, real timeout ambiguity,
  steady-state latency — is exactly the R4 device matrix.
- One environmental (non-code) finding: full-suite run at freeze time gave
  **129 passed + 1 error** (`test_check_provenance_detects_phone_harness_reference`
  errors at `tmp_path` fixture setup — `PermissionError` on the sandbox temp
  directory, identical with `-p no:cacheprovider`). The test body never runs;
  the standalone guard passes. This is **not a code regression** but it must
  be re-run in a clean environment before any R4/R5 gate is claimed green
  (see §6 gate D0).

### Audit 3 — host / device / provenance (live probes, no mutation)

- Host: Windows, CPython 3.12.10, repo venv `.venv`; `pymobiledevice3`
  11.3.0 installed, pin `ec4ac06a850a6a884ca778350621f354faf347c6` confirmed
  (matches `pyproject.toml` + `docs/PROVENANCE.md`). No fork delta.
- **Device probe (read-only, pinned upstream `usbmux.list_devices()`):
  `DEVICE_COUNT=1` at freeze time** (differs from the handoff's
  preparation-time `DEVICE_COUNT=0` — re-probed per handoff §2, not assumed).
  No WDA/lockdown/pair inspection was performed during planning; WDA
  reachability, iOS version, and runner presence are **unprobed gates** for
  the device lane (§5), not claims.
- No real-device runner exists under `scripts/` yet (only
  `check_provenance.py`); R4 must add it outside production runtime.
- Pre-plan Git tree was clean; this plan-freeze document is the sole intended
  change. No concurrent-work conflicts observed; no push performed.

## 2. Exact R4/R5 matrix (points frozen)

| ID | Scope | Pts | Deterministic proof required | Real-device proof required |
|---|---|---:|---|---|
| R4-01 | Transport/lifecycle matrix | 3 | existing fake lifecycle tests stay green | USB + in-process `RSD_USERSPACE` re-prove; READY→recreate/recover→close; stale-owned-WDA resumption; safe hotplug classification |
| R4-02 | Observe matrix | 3 | existing revision/ref tests stay green | repeated screenshot+AX rounds; sizing/coordinate consistency; fresh/invalidated revision binding; capture after navigation + after recovery; bounded element counts |
| R4-03 | Action matrix | 5 | A03/A04/A05/A09/A10 stay green; screenshot-pixel conversion and ordered result counts/timings remain covered | all 7 primitives + ordered batch in safe Settings/Home context; preflight-zero-device-call proofs; revision invalidation per mutation; screenshot-pixel conversion; accurate ordered counts/timings |
| R4-04 | Failure/recovery matrix | 5 | A06/A07/A08 stay green | stale/closed owned WDA session; stale transport/session recreation; safe disconnect/unavailability or honest `environment-not-exercised`; ambiguous-vs-definitive classification; `retry_safe=false`; recover rebuilds plumbing only; fresh observation/reconciliation after ambiguity or recovery; idempotent close touches no unrelated process/resource |
| R4-05 | Latency/trace baseline | 2 | trace unit tests stay green | bounded samples: startup vs steady-state observe, per-primitive, batch, recovery, close; count/min/median/p95-or-max; no new infra |
| R4-06 | Old-vs-new evidence report | 2 | n/a (report) | map each R2 capability to Praxiom device evidence + historical reference; use required verdict vocabulary; attach exact remediation/evidence reference to every `gap` |
| R4 total | | **20** | | exit gate §6 |
| R5-01 | Dependency audit | 2 | provenance guard green in clean env; smallest missing regression check only if R4 exposes a gap | live-path confirmation: no Phone Harness package/process/MCP hop during device run |
| R5-02 | Provenance/source-copy review | 2 | inspect `src/` + dependencies; prove no production source was copied/renamed/adapted; distinguish acceptable contract/evidence fixture provenance from prohibited source copying; retain review under `docs/evidence/` | n/a |
| R5-03 | Active-path docs / XMind | 1 | Praxiom→upstream→WDA/CoreDevice/iPhone docs current | XMind update if a writable XMind tool exists; else retained node-change artifact + explicit external gate |
| R5-04 | Historical-reference classification | 1 | remaining mentions classified `historical` / `regression evidence` / `migration provenance`; no active-dependency language | n/a |
| R5-05 | Migration completion + final report | 1 | retained report with R4/R5 point totals, evidence/scans/path statement/comparison, deterministic test totals and commands, independent reviews/repairs, exact changed files/commits, rollback, Certification verdict, and `R5_COMPLETE` or precise blocker | includes real-device matrix commands/results, latency baseline, and unresolved environment coverage |
| R5 total | | **7** | | exit gate §6 |

## 3. Deterministic gaps (smallest test/harness delta — Phase B only)

No public-contract expansion is proven. Phase B implements the one proven
R2 requirement gap below, then adds only harnesses/regressions plus root-cause
fixes for failures a check actually demonstrates:

1. **G1 — bounded, traceable `invalidate(reason)` (proven deterministic gap).**
   Add focused tests for a documented finite reason bound, rejection before any
   side effect, and privacy-safe traceability; then make the narrowest runtime/
   trace repair that satisfies R2 §4.4 without changing the six-operation
   surface. Do not retain raw user/device content in the reason.
2. **G2 — real-device runner (new, `scripts/` only).** One script
   (e.g. `scripts/r4_device_matrix.py`) driving **only the public six
   operations + upstream provenance probes**, emitting privacy-safe
   `docs/evidence/` reports (counts, enums, timings; never identifiers,
   screen text, payloads). Any `tests/`-placed device test must be
   excluded/skipped by default so the canonical suite stays phone-free.
3. **G3 — R4-03 device-counter preflight proofs.** Deterministic fakes prove
   zero-device-call rejection logically; the runner must record transport
   call counts around stale/foreign/invalid/over-limit batches **on hardware**
   (new assertions live in the runner/evidence, not in production code).
4. **G4 — R4-04 owned-plumbing disruption harness.** Fake ambiguous-failure
   semantics exist; the runner needs stale/closed owned-WDA and stale-transport/
   session recreation steps, plus a safely reproducible disconnect/unavailable
   path or honest `environment-not-exercised` classification. Verify
   `EFFECT_UNKNOWN`/`PARTIAL`, `retry_safe=false`, recover-no-replay, required
   fresh observation/reconciliation, idempotent close, and zero termination of
   unrelated processes/resources. Never manufacture ambiguity by replaying a
   non-idempotent action.
5. **G5 — R4-05 sampling scaffold.** `trace.py` records suffice; the runner
   aggregates count/min/median/p95-or-max with startup vs steady-state split.
   Bounded 256-record history stays unless evidence proves insufficiency —
   no DB/telemetry/stream in R4/R5.
6. **G6 — clean-environment suite re-run.** Clear the §1 environmental error
   (129+1 → 130 passed expected) before any gate claim; if it reproduces
   outside the sandbox, classify and repair it as a repository test defect.
7. **G7 — R5-01 regression check (conditional).** Only if R4 exposes an audit
   gap; otherwise the existing guard + suite is the check.

Explicitly **not** in the delta: new runtime abstractions, provider/factory
frameworks, OCR, Wi-Fi scope (unless the device lane finds the target
environment requires it), upstream pin change (R1 gate not met), contract
expansion (no evidence requires it).

## 4. Physical / device gates (honest blockers, not assumptions)

- **P1 — device presence: CURRENTLY SATISFIED at freeze time
  (`DEVICE_COUNT=1`, USB unconfirmed — list probe only).** Must be re-probed
  by the device lane at run start; if the device is gone, R4 device cells
  block and only AI-executable work completes.
- **P2 — WDA reachability + installed runner: UNPROBED.** R3-08 used an
  already-installed runner via upstream APIs; the lane must confirm the same
  without installing/building anything. If WDA is unreachable, classify as
  environment/upstream per evidence, do not fork or patch.
- **P3 — safe hotplug/unplug (R4-01):** only if inducible without risk;
  otherwise record as `environment-not-exercised`, never fabricate.
- **P4 — disconnect/unavailability and ambiguous effect (R4-04):** induce only
  when safe and through owned resources; otherwise retain
  `environment-not-exercised`. Never repeat a non-idempotent action to force or
  reconcile ambiguity.
- **P5 — XMind writable tool (R5-03):** availability unknown; fallback is a
  retained node-change artifact + explicit external gate, never a false claim.
- **P6 — historical reference tree readability: SATISFIED** (R2 contract
  read OK at freeze time); R0/R1 docs re-verified when R4-06 is authored.

## 5. File ownership + single device lane

Concurrency max 3; device mutation strictly single-lane. Every authored
implementation, device, analysis, or review task must explicitly declare
`sensitivity: 'public'`; routing uses only the allowed semantic hints, never a
provider/model/fallback directive.

- **Lane B1 (deterministic harness):** owns `scripts/r4_device_matrix.py`
  (new), focused `tests/` changes (including `test_runtime.py`/`test_trace.py`
  for G1; never weaken existing assertions), and new `docs/evidence/` reports.
  No `src/` edits.
- **Lane B2 (narrow repair, conditional):** owns `src/praxiom/ios_runtime/*`
  only for root-cause fixes proven by a failing new check; must not overlap
  files with B1 in the same step. Runs focused tests per fix.
- **Lane D1 (sole device-mutating lane, Phase C):** owns the attached iPhone
  exclusively for the ordered matrix
  transport → observe → primitives+batch → recovery → latency → R4-06.
  Only D1 executes the runner against hardware; all other lanes analyze
  already-captured privacy-safe evidence and never touch the device.
  Safe context only: Settings/Home, reversible states, bundle-id launches,
  non-submitting text field cleared afterward; never purchase, submit, message,
  delete user content, alter account or security settings, install a profile,
  or perform domain/game automation.
- **Phase D/E lanes (review + R5):** own `docs/` (+ conditional XMind
  artifact), read-only over `src/` except review-mandated minimal repairs;
  R5-02 review output retained under `docs/evidence/`.
- **Forbidden everywhere:** `Phone Harness` production import/subprocess/MCP/
  shim/fallback/copied source; upstream pin change; speculative `src/`
  abstractions; raw UDID/serial/ECID/MAC/IMEI, pair records, credentials,
  cookies, tokens, secrets, raw screen text, unredacted user-data screenshots,
  or raw action payloads in any artifact or commit.

## 6. Verification commands + gates (canonical, repo-current)

Deterministic (phone-independent; run from repo root with repo venv):

```text
.venv\Scripts\python -m pytest -q
.venv\Scripts\python scripts\check_provenance.py
```

- **D0 (pre-gate):** clean-environment rerun must show the §1 tmp-dir error
  gone (130 passed expected) + guard exit 0. No R4/R5 gate may be claimed
  while D0 is red for a code reason.
- **R4 exit:** full R2-A11 retained device evidence; R4-01…R4-06 accepted by
  independent non-author review; deterministic suite green (D0); required
  capabilities passing on current target env; honest failure classification;
  zero new Phone Harness execution dependency; no unjustified fork;
  diff limited to intentional R4 files.
- **R5 exit (only after accepted R4):** zero Phone Harness prod/build/runtime
  dependency or execution edge; provenance/source-copy PASS retained;
  active-path docs current (+ XMind or explicit artifact gate); historical-only
  classification; independently reviewed migration report; final regression
  PASS; clean tree at intended checkpoint commit(s).
- Read-only device pre-probe for lane start (no mutation, privacy-safe):

```text
.venv\Scripts\python -c "import asyncio; from pymobiledevice3 import usbmux; print(len(asyncio.run(usbmux.list_devices())))"
```

## 7. No-R6 boundary

R6+ work is not planned, not staffed, and not started under this freeze.
Deferred explicitly out of scope: latency optimization from the R4-05
baseline, runner install/update policy, multi-device policy, stress/flake
characterization beyond the bounded matrices, trace-volume expansion, any
contract addition. If the device lane discovers a suspected contract gap, it
is recorded as evidence with the smallest explicit change proposal — never
silently implemented.

## 8. Frozen execution order

1. D0 clean-env suite + guard (unblocks all gate claims).
2. Phase B: G1 focused test/repair → G2 runner → G3/G4/G5 scaffolds → G6
   confirm; G7 only if an R4 audit gap requires it. Focused tests per change;
   full suite after each repair.
3. Phase C (lane D1 only on device): §2 device column in order, fresh
   observe before every state-sensitive action, evidence per cell.
4. R4-06 report → independent deep R4 review → repair/re-run/re-review until
   no blocking R4 finding remains.
5. R5-01…R5-05 only after R4 acceptance.
6. Independent deep R5/combined-final review → repair/retest/re-review until no
   blocking finding remains.
7. Create focused local checkpoint commit(s) only after the respective
   independent review accepts each unit; never push.
8. Hand the combined state to the runtime-owned Goal Certification sequence
   (Independent Reviewer → Repair → Re-review → Final Judge). Retain the final
   report with R4/R5 point totals, exact files/commits, deterministic test total,
   real-device matrix and latency results, unresolved physical/environment
   coverage, Certification verdict, rollback, and final R4/R5 status.

*End of plan freeze — implementation authority remains the handoff; current
evidence overrides any cached statement above at execution time.*

## 9. Phase-B actual delta (deterministic only, executed 2026-09-05 UTC)

Scope actually implemented: plan-frozen deterministic acceptance
harnesses/regressions (G1–G5 scaffolds, G6) plus the one narrow
runtime/trace root-cause fix proven by the frozen gap analysis. **No device
mutation was performed**; the device lane (D1), R4-06, R4 exit review, and
all of R5 remain for later phases. No production contract expansion, no
upstream pin change, no Phone Harness dependency. No commit was created by
this unit (checkpoint commits wait for independent domain review).

### 9.1 G1 — bounded, traceable `invalidate(reason)` (implemented + repaired)

- `src/praxiom/ios_runtime/runtime.py`: added documented
  `INVALIDATE_REASON_MAX_LENGTH = 128` and `_check_invalidate_reason()`.
  A reason must be a non-blank ASCII-printable string within the bound;
  anything else raises no-effect `INVALID_REQUEST`/PREFLIGHT **before**
  any side effect (revision intact, zero device calls). The Phase-B version
  initially retained the validated reason verbatim; final-certification review
  later superseded that detail in commit `0cd1c81`, and current behavior keeps
  only a Runtime-local keyed fingerprint. Six-operation surface unchanged.
- `src/praxiom/ios_runtime/trace.py`: `TraceRecord` gains
  `detail: str | None` (set only on `invalidate` records) plus
  `Trace.record(..., detail=...)`; module docs updated. Only validated
  machine-oriented tokens can reach the field, so the privacy allowlist
  holds.
- Focused tests (existing assertions unweakened):
  `test_invalidate_reason_is_bounded_and_rejected_before_side_effect`
  (`tests/test_runtime.py`: bound value, 9 hostile reasons rejected with
  revision intact + zero device calls, 128-char boundary accepted/invalidated/
  traced) and the subsequently renamed
  `test_trace_invalidate_reason_is_fingerprinted_and_privacy_safe`
  (`tests/test_trace.py`: hostile reasons never recorded; accepted reasons are
  represented only by keyed fingerprints; UDID/secret/revision/ref scan clean).

### 9.2 G2–G5 — `scripts/r4_device_matrix.py` + `tests/test_r4_runner.py`

- New real-device runner (outside production runtime, public six
  operations + read-only upstream `usbmux.list_devices` probe only) with:
  frozen `MATRIX_CELLS` R4-01…R4-05 in lane order; exact R4-06 `VERDICTS`
  vocabulary; `CallCountingTransport` G3 zero-device-call proofs (counts
  the 12 device-facing transport methods, never `snapshot()`); G4
  owned-plumbing disruption steps (one `close_session` → observe resumption
  proof, then a separate `close_session` → `recover` with zero replay →
  observe reconciliation proof); G5 `summarize_stats`
  count/min/median/p95-or-max with startup/steady-state keys; `preprobe`
  read-only census; `write_evidence` fail-closed identifier scan;
  `matrix` refuses without `--confirm-device-run` (exit 2) — the device
  run itself is lane-D1 work and was **not** executed here.
- `tests/test_r4_runner.py` (9 tests, phone-independent, no `tmp_path`
  fixture): cell order/points (3+3+5+5+2=18), R4-03 primitive coverage,
  verdict vocabulary, stats incl. empty + n=100 p95 branch, redaction
  detect/clean, evidence round-trip + tainted refusal, counter
  device-calls-only semantics, `list-cells` exit 0,
  `matrix`-without-consent exit 2.
- G6: full suite re-run below. G7: not triggered (no R4 audit gap found).

### 9.3 Commands and results (repo root, repo venv)

```text
.venv\Scripts\python -m pytest -q -p no:cacheprovider
# 140 passed, 1 error in ~1.2s
# The 1 error is tests/test_package.py::
# test_check_provenance_detects_phone_harness_reference failing in the
# tmp_path fixture setup: os.scandir on any pytest tmp root raises
# PermissionError [WinError 5] under this session's sandbox (reproduced
# with system temp and a workspace-local TEMP redirect, before any repo
# code runs). The test BODY was verified PASS via an equivalent manual
# run (find_violations detects the planted bad.py reference, 1 hit).
# Pre-existing identical signature at freeze time (then 129 passed).

.venv\Scripts\python scripts\check_provenance.py
# OK: no Phone Harness import/name/dependency in production paths (exit 0)

.venv\Scripts\python scripts/r4_device_matrix.py list-cells   # exit 0
.venv\Scripts\python scripts/r4_device_matrix.py preprobe
# {"device_count": 1, "pymobiledevice3_version": "11.3.0"} (read-only)

.venv\Scripts\python -c "from importlib.metadata import version; ..."
# pymobiledevice3 11.3.0 == pyproject pin ec4ac06a850a6a884ca778350621f354faf347c6; no fork delta
```

Baseline delta: 129 passed + 1 environmental error (freeze) →
**140 passed** + the same 1 environmental error (+11 new tests, zero
regressions). Default `pytest` remains phone-independent; no `tests/`
device test was added. Untracked sandbox dir noise (`.pytest-tmp`,
`tests/.pytest-tmp-r4-freeze` + git enumeration warnings) is
environmental and not part of the delta.

### 9.4 Remaining blockers (unchanged, owned by later phases)

- P1 re-probe at lane start (currently `DEVICE_COUNT=1`, USB/WDA unprobed).
- P2 WDA reachability + installed runner confirmation (lane D1, no
  install/build).
- P3/P4 hotplug + disconnect/ambiguity inducibility (or honest
  `environment-not-exercised`).
- R4-06 report, independent R4 review, all of R5, Goal Certification.

## 10. Fresh R4 checkpoint re-verification (2026-09-05 JST)

The earlier sandbox-only `tmp_path` failure is no longer reproducible in the
current repository environment. Immediately before the R4 checkpoint, the
canonical phone-independent gates were re-run from the repository root:

```text
.venv\Scripts\python -m pytest -q
# 141 passed

.venv\Scripts\python scripts\check_provenance.py
# OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml).
```

`git diff --check` also passed (line-ending conversion warnings only; no
whitespace errors). The attached-device read-only preprobe still reports one
device and installed upstream `pymobiledevice3 11.3.0`. R4 real-device
acceptance remains represented by the retained canonical 29/29 matrix in
`20260905_r4-device-matrix-run4.json` and the independent R4 review verdict is
PASS. No R6+ work was started.
