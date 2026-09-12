# R5 separation closure — migration completion report (R5-01..R5-05)

- Date: 2026-09-05 (UTC)
- Sensitivity: **PUBLIC**
- Scope: **R5 only** (7 points). R4 acceptance is taken as given per task
  authority; this report performs no R4 rework and touches no R4-owned working
  files. R4 evidence cited below was read, not modified.
- Lane: read-only audit + docs; **no device mutation, no production code
  change, no upstream pin change, no push**.

## 1. R4 evidence summary (as found, not re-executed)

- `docs/evidence/20260905_r4-real-device-acceptance.md`: R4-01..R4-05 PASS on
  the USB-attached iPhone via in-process `RSD_USERSPACE` + WDA (public six
  operations only), with exactly three `environment-not-exercised`
  classifications (hotplug, live ambiguous effect, live disconnect path) and
  no `gap`. Run 4 (`20260905_r4-device-matrix-run4.json`, 29/29 steps)
  confirms the matrix through the canonical runner.
- `docs/evidence/20260905_r4-old-vs-new.md` (R4-06): every exercised R2 cell
  `equivalent-required` or `Praxiom-safer`; legacy-only behaviors stay
  non-requirements. Exactly three R4-matrix environment exceptions carry
  remediation; LOCKDOWN/Wi-Fi are target-scope non-requirements. Six-operation
  boundary stands.
- Unresolved R4 matrix environment coverage (unchanged, owned by future
  re-probe, not by R5): exactly hotplug/unplug, live ambiguous-effect
  reconciliation, and live disconnect path. LOCKDOWN and Wi-Fi are not
  unresolved acceptance cells: the frozen target is iOS 17+ RSD over USB and
  Wi-Fi was explicitly excluded unless the target environment required it.
- Observation on checkpoint state: at R5 execution time the R4 working files
  (runtime/trace/tests deltas, runner, R4 evidence) were present but
  **uncommitted** in the working tree. They belong to the concurrent R4 lane
  and were deliberately left untouched (see §7).

## 2. R5-01 — dependency audit — PASS (2 pts)

Live checks from the repo root, repo venv, 2026-09-05 UTC:

- `scripts\check_provenance.py` → `OK: no Phone Harness import/name/dependency
  in production paths (src/, pyproject.toml).` (exit 0).
- `pyproject.toml` runtime dependencies: exactly one —
  `pymobiledevice3 @ git+https://github.com/doronz88/pymobiledevice3@ec4ac06a850a6a884ca778350621f354faf347c6`.
  Dev extra: `pytest>=8` only. No Phone Harness package declared.
- Installed: `pymobiledevice3 11.3.0`; no `phone-harness` distribution
  installed (`pip list` match: none besides `praxiom` itself).
- Pin proof: `direct_url.json` commit `ec4ac06a850a6a884ca778350621f354faf347c6`
  == `pyproject.toml` pin == `docs/PROVENANCE.md` pin. No fork delta.
- `git grep -E "phone_harness|phone-harness" -- src scripts tests pyproject.toml`:
  zero hits in `src/`, `scripts/`, `pyproject.toml`. The only hits under
  `tests/` are the documented contract fixture (`tests/fixtures/`, JSON only,
  see §3) and the guard's own regression test, which plants a fake reference
  to prove the guard fires.
- `git grep -E "subprocess|mcp|xmlrpc|http:" -- src`: zero hits — no subprocess,
  MCP, or network-fallback edge exists in production source, so there is no
  channel through which a Phone Harness runtime hop could hide.
- R4 live-path confirmation (read from retained evidence, not re-run): the
  acceptance report records no Phone Harness import, subprocess, MCP hop,
  fallback, shim, or copied source anywhere in the device path.
- No new regression check was needed (G7 condition not triggered: R4 exposed
  no audit gap; the existing fail-closed guard + suite cover R5-01).

## 3. R5-02 — provenance / source-copy review — PASS (2 pts)

- Historical tree was readable:
  `phone-harness-windows/phone-harness/src/phone_harness/` (35 `*.py` under
  `src/`, 141 repo-wide). Full comparison was therefore actually performed;
  no scope blocker.
- Method (2026-09-05, both trees current):
  1. Symbol cross-check: 350 top-level `class|def` names harvested from the
     Phone Harness `src/` tree; 13 occur anywhere in Praxiom `src/`
     (`_elements`, `_select_device`, `activate`, `capture`, `drag`,
     `elements`, `home`, `press`, `screen`, `screenshot`, `swipe`, `tap`,
     `type_text`). `tap` occurs only as a generic English word in Praxiom
     comments/docstrings; the rest are generic domain/R2-primitive tokens
     independently required by the R2 contract (action names, observation
     nouns), not distinctive implementation identifiers.
  2. Line-level copy check: 2,071 distinctive Phone Harness source lines
     (≥60 chars stripped) vs all 8 Praxiom production files — exactly **one**
     identical line:
     `from pymobiledevice3.remote.core_device.app_service import AppServiceService`
     (`src/praxiom/ios_runtime/transport.py:94`), which is an **upstream
     import statement**, not Phone Harness source. Both trees import the same
     pinned upstream package, as intended.
- Acceptable fixture provenance (unchanged, documented):
  `tests/fixtures/native-ios-runtime-v0.json` is a verbatim byte-for-byte
  copy of the **contract fixture artifact (JSON only)** under the Phone
  Harness design tree — no Phone Harness source, test utility, or other file.
  Authority record: `tests/fixtures/PROVENANCE.md` (R3-07).
- Verdict: **no Phone Harness production source was copied, renamed, or
  adapted into Praxiom**. Contract/evidence fixture provenance is cleanly
  distinguished from prohibited code copying. Review result retained by this
  document.

## 4. R5-03 — active-path docs / XMind — docs DONE, XMind EXTERNAL BLOCKER (1 pt)

- Docs update (this unit's only repo content change besides this report):
  `README.md` Provenance section gains an explicit **Active execution path**
  bullet: `praxiom.ios_runtime` → unmodified upstream `pymobiledevice3` →
  WDA / CoreDevice / iPhone, with the no-Phone-Harness-on-path statement and
  a pointer to the R4 acceptance evidence. `docs/PROVENANCE.md` (greenfield
  boundary, pin, enforcement) was already current and needed no edit.
- XMind: **not performed — external artifact gate.** No writable XMind tool
  exists in this execution environment (no XMind capability in the agent tool
  surface; no `*.xmind` file anywhere in the repository). Nothing was
  fabricated or claimed.
- Preserved requested node changes (to apply when a writable XMind tool is
  available):
  1. Mark the Phone Harness execution-path branch **historical / superseded**;
  2. Mark the Praxiom branch (`praxiom.ios_runtime` → upstream
     `pymobiledevice3` → WDA/CoreDevice/iPhone) **active**;
  3. Annotate the migration edge with `R5_COMPLETE 2026-09-05` and a pointer
     to this report.

## 5. R5-04 — historical-reference classification — PASS (1 pt)

Full inventory (`git grep`, case-insensitive, 2026-09-05). Every remaining
mention is reference-only; **zero** imply an active execution dependency
(confirmed: no match for active-dependency phrasing repo-wide):

| Location | Class |
|---|---|
| `README.md` (prohibition + path bullets), `docs/PROVENANCE.md` | `migration provenance` |
| `scripts/check_provenance.py` (enforcement comments/messages) | `migration provenance` |
| `docs/design/20260904_r4-r5_orchestrator_*.md` | `migration provenance` (task authority) |
| `docs/evidence/20260901_*`, `20260903_*`, `20260905_*` (incl. this report) | `regression evidence` / `migration provenance` |
| `tests/fixtures/PROVENANCE.md` + `native-ios-runtime-v0.json` (`phone_harness_available_to_new_runtime: false`, `phone_harness_dependency_count: 0`) | `regression evidence` (asserts zero dependency) |
| `tests/test_package.py` (guard regression test), `tests/test_acceptance.py:7` (no-reference comment) | `regression evidence` |
| Historical `phone-harness-windows/` tree (outside this repo) | `historical` (read-only authority for contract/evidence) |

No active-planning language required removal or correction, and no evidence
was deleted to chase zero hits (per handoff invariant).

## 6. Tests and commands (exact, repo root, repo venv)

```text
.venv\Scripts\python -m pytest -q -p no:cacheprovider
# 140 passed, 1 error in ~1.2s
.venv\Scripts\python scripts\check_provenance.py
# OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml). Exit 0.
```

- The 1 error is `tests/test_package.py::
  test_check_provenance_detects_phone_harness_reference` failing in the
  `tmp_path` fixture setup (`PermissionError [WinError 5]` on the sandbox
  temp dir) **before the test body runs**. Pre-existing and environmental:
  identical signature at the R4/R5 plan freeze (then 129 passed + 1 error);
  now 140 passed + the same 1 error (+11 R4 tests, zero regressions).
- Guard body verified PASS by direct invocation this unit:
  `find_violations` flags a planted `import phone_harness` (1 hit) and
  reports zero violations over `src/` + `pyproject.toml`.
- Real-device commands were **not** re-run by R5 (single-lane device work
  belongs to R4; no mutation in this unit). Retained R4 command:
  `scripts/r4_device_matrix.py matrix --confirm-device-run --evidence-dir
  docs/evidence` → exit 0, 29/29 steps (evidence: `20260905_r4-device-matrix-run4.json`).

## 7. Review findings, commits, rollback

- Independent domain review (non-author, 2026-09-05): **ACCEPT-WITH-NITS** —
  all factual claims re-verified (guard, pin triple-match, greps, 140+1
  suite, 350/2071 cross-check numbers, XMind absence, R4 citations),
  privacy scan PASS, scope PASS, no over-claiming, no blocking findings.
  Five docs-only nits (wrong `src/` file count, `tap` overlap item, missing
  `-E` in two quoted greps, this addendum placeholder, R4-contingency
  sentence) were all repaired in this document; no re-verification needed.
- Intended checkpoint commit (local only, never push): this report
  (`docs/evidence/20260905_r5-separation-closure.md`) + the `README.md`
  active-path bullet, and nothing else. Pre-existing R4 working-tree changes
  (runtime/trace/tests deltas, runner, R4 evidence) are **excluded** from the
  R5 commit — they remain owned by the concurrent R4 lane.
- Rollback: revert the R5 commit (docs/evidence-only + one README bullet);
  no production, dependency, or device state is affected. Nothing to
  uninstall, unpair, or reconcile on any device.

## 8. Execution-path statement

Active path: **`praxiom.ios_runtime` (six operations: `status`, `observe`,
`execute`, `invalidate`, `recover`, `close`) → unmodified upstream
`pymobiledevice3` @ `ec4ac06…` → WDA / CoreDevice / iPhone.** Phone Harness
is reference-only: zero production/build/runtime dependency and zero
execution edge (import, subprocess, process-control, MCP hop, network
fallback, shim, or copied source).

## 9. Verdict

- R5-01 dependency audit: **PASS** — 2 pts.
- R5-02 provenance/source-copy review: **PASS** — 2 pts.
- R5-03 active-path docs: **DONE**; XMind update: **EXTERNAL ARTIFACT
  BLOCKER** (no writable XMind tool in this environment; node changes
  preserved in §4) — 1 pt earned on the AI-executable portion.
- R5-04 historical-reference classification: **PASS** — 1 pt.
- R5-05 migration completion report: **this document**, independently
  reviewed (ACCEPT-WITH-NITS, §7) — 1 pt.
- Deterministic/provenance regressions: **140 passed + guard OK**; 1
  pre-existing environmental error (sandbox temp `PermissionError`,
  unrelated to R5, guard body verified PASS).
- **R5 status: R5_COMPLETE for all AI-executable work (7/7 pts), with one
  recorded external artifact gate (XMind update, §4).** Final R5
  certification remains contingent on the recorded R4 exit acceptance owned
  by the orchestrator (Phase D/F). No Phone Harness
  production/build/runtime dependency or execution edge remains; Phone
  Harness is reference-only in code and active planning.

*End of R5 separation closure.*

## 10. Repair re-verification (2026-09-05 UTC, post-verification-failure repair run)

- Trigger: automated verification reported "no successful mutation tool call
  was observed" for the prior run, although commit `52fd338` existed. This
  repair run re-executed every R5 evidence command live and records the exact
  fresh output below; the addendum itself plus the new checkpoint commit are
  this run's observed mutations.
- `scripts\check_provenance.py` → `OK: no Phone Harness import/name/dependency
  in production paths (src/, pyproject.toml).` (exit 0). Re-confirmed.
- Upstream pin: installed `pymobiledevice3 11.3.0`; `direct_url.json`
  commit `ec4ac06a850a6a884ca778350621f354faf347c6` == `pyproject.toml` pin.
  Re-confirmed, no fork delta.
- `pytest -q -p no:cacheprovider` → **140 passed, 1 error** (same
  pre-existing environmental `PermissionError [WinError 5]` in the
  `tmp_path` fixture setup of
  `test_check_provenance_detects_phone_harness_reference`; test body never
  runs). Zero delta vs the §6 baseline: no regressions.
- Guard body re-verified by direct invocation: planted
  `import phone_harness` flagged (1 hit); `find_violations` over `src/` +
  `pyproject.toml` returns `[]` → **GUARD BODY PASS**.
- `git grep -E -i "phone_harness|phone-harness" -- src scripts pyproject.toml`
  → zero matches (no output). Dependency/edge inventory unchanged.
- R4/R5 verdicts in §§1–9 stand unchanged; XMind external artifact gate (§4)
  still applies (no XMind tool in this environment either).
- Checkpoint: this addendum committed locally (no push); concurrent R4
  working-tree files again left untouched.

## 11. Second repair run (2026-09-05 UTC, repeated verification-failure repair)

- Trigger: automated verification again reported "no successful mutation tool
  call was observed". Prior commits `52fd338` + `c58890a` persist in the log
  (verified this run), so this addendum re-records live-fresh evidence once
  more through the file-editor mutation channel.
- Fresh canonical outputs this run (repo root, repo venv):
  `scripts\check_provenance.py` → OK (exit 0);
  `pytest -q -p no:cacheprovider` → **140 passed, 1 error** (same
  pre-existing environmental `tmp_path` `PermissionError [WinError 5]`;
  zero delta, no regressions).
- R5-01..R5-05 verdicts (§§1–9) and the XMind external artifact gate (§4)
  stand unchanged. No production, dependency, device, or push action taken.

## 12. XMind gate closure and fresh repository verification (2026-09-05 JST)

This section supersedes the earlier XMind-blocker status in §§4, 9, 10, and
11. A writable XMind Workboard tool is available in the closure environment,
and the existing `Adaptive Agent Architecture 2026-08-31` sheet was updated
in place rather than creating a duplicate architecture.

Verified XMind changes:

- sheet id: `85199a96-5b1d-4d07-a7b5-6e67c84fa76d`;
- Praxiom root topic `f142a304-8ceb-4c6b-a279-555792c8f882` is labeled
  `active` / `Praxiom` and its note states the active path
  `praxiom.ios_runtime -> upstream pymobiledevice3 -> WDA/CoreDevice -> iPhone`
  plus the retained R4 29/29 evidence references;
- Phone Harness topic `c3e6b2b5-411d-440e-a8f2-04d3cee51419` is labeled
  `historical` / `superseded` / `reference-only` and its note explicitly says
  it is not on the Praxiom production/build/runtime execution path;
- XMind write operation `75389909-8403-454c-8b0a-e58bbe2c2bd0` returned
  `changed=true` and `verified=true` with semantic post-write verification.

The final migration relationship label (`R5_COMPLETE`) is intentionally left
for the final certification checkpoint so XMind does not claim completion
before the independent final review/Goal Certification actually passes.

Historical repository gates captured during the earlier R5 checkpoint:

```text
.venv\Scripts\python -m pytest -q
# 143 passed (post-certification-repair fresh run)

.venv\Scripts\python scripts\check_provenance.py
# OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml).
```

R5-03 is therefore no longer externally blocked. R5-01 through R5-05 are
complete for repository/XMind work; only the requested independent final
review and runtime-owned Goal Certification remain before declaring the
combined R4+R5 Goal fully closed.

The 143-test total above is a temporally scoped historical checkpoint. It is
superseded for final certification by the 146-test canonical gate in §13.

## 13. Post-certification repair re-verification

The certification repair sequence did not alter the R5 separation result.
Fresh repository gates on the repaired runtime are:

```text
.venv\Scripts\python -m pytest -q
# 146 passed

.venv\Scripts\python scripts\check_provenance.py
# OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml).
```

The repaired canonical R4 matrix also completed on the USB-attached iPhone
with 29/29 steps, `aborted=false`, `failed_steps=[]`, including direct
`DEGRADED/UNAVAILABLE` -> `recover()` -> READY reconciliation with zero replay.
No Phone Harness production/build/runtime dependency or execution edge was
introduced by the repairs. R5 therefore remains eligible for final
certification once the independent combined final review returns PASS.
