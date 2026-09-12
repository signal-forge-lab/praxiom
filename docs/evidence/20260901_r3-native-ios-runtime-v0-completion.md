# R3 Final Completion Report — Native iOS Runtime v0

- Goal ID: `goal-adaptive-agent-r3-greenfield-native-ios-runtime-v0-20260901`
- Date: 2026-09-01
- Repository at original report time: `products/adaptive-agent` (branch
  `main`; renamed to `products/praxiom` after R3 completion at the controlled
  naming checkpoint)
- Prior HEAD at report time: `992a44c54c45181527cc3443e13f7f1a3cb4c07c`
  (R3-08 checkpoint). This report is committed as the Goal's final commit; the
  resulting SHA is returned in the R3 completion response and is the value
  referenced as *final commit SHA*.
- **Final verdict (updated 2026-09-03): `R3_COMPLETE`.** The earlier
  `BLOCKED_R3_08` state was valid while no physical device was attached. A
  directly connected USB iPhone subsequently completed the mandatory
  upstream-only bounded smoke. Closure evidence:
  `docs/evidence/20260903_r3-08-attached-device-pass.md`.

## 1. Task status R3-00 … R3-08

Each task ran the required loop: implement → deterministic checks →
independent review → fix loop → checkpoint commit (atomic per task).

| Task | Scope | Checkpoint commit | Gate |
|---|---|---|---|
| R3-00 | Repository/bootstrap boundary, GPL license, provenance guard, pinned upstream baseline | `c76db11922e759840e4b832073e88902198d3d30` | PASSED |
| R3-01 | Contract models / error + effect semantics | `aec924717253b5c30919aa11fc10eef675f36940` | PASSED |
| R3-02 | Upstream transport/session lifecycle (in-process RSD path) | `1c3d9fd86d7d2cd2dbe25b017ce8fe236b763c8a` | PASSED |
| R3-03 | Observation, revision lifecycle, screenshot-pixel coordinates | `13405503aa3d1f8949419d77f881fa7cb11e64d3` | PASSED |
| R3-04 | Executor, whole-batch preflight, internal coordinate conversion | `a9e18218323dcae873538884e6d547adb9929d7c` | PASSED |
| R3-05 | Six-operation integration, unknown-effect semantics, recovery, close | `4f7f786448859c215bdfb9f91227aec64ad2fb87` | PASSED |
| R3-06 | Privacy-safe status/trace/latency observability | `ae97d841f6c9a8de2c4908fc10b88282b77c3d3d` | PASSED |
| R3-07 | A01–A10 deterministic contract fixture acceptance suite | `b15e809ba23d4857cc7d37863926266ef6d315d4` | PASSED |
| R3-08 | Upstream-only attached-device smoke | closure evidence commit follows this report | **PASSED 2026-09-03** (`docs/evidence/20260903_r3-08-attached-device-pass.md`) |

The final report commit also carries one pending R3-08 review repair that was
uncommitted at report time (see §9: explicit WDA session-id pinning in
`transport.py` plus a regression test that mirrors the upstream hard
precondition). Without it the deterministic suite passed while a real device
call through `get_window_size`/`send_keys`/`swipe` would have failed; committing
the report with a dirty tree was not acceptable, and discarding the fix would
have shipped a latent device-breaking defect.

## 2. 33-point progress table

| Task | Points | Cumulative when accepted | Accepted |
|---|---:|---:|---|
| R3-00 | 2 | 6% | yes |
| R3-01 | 3 | 15% | yes |
| R3-02 | 5 | 30% | yes |
| R3-03 | 5 | 45% | yes |
| R3-04 | 5 | 61% | yes |
| R3-05 | 5 | 76% | yes |
| R3-06 | 2 | 82% | yes |
| R3-07 | 3 | 91% | yes |
| R3-08 | 3 | 100% | **yes — attached-device smoke passed 2026-09-03** |

Accepted progress: **33 / 33 points (100%)**.

## 3. Dependency baseline — exact upstream pin

- `pymobiledevice3` **11.3.0**, unmodified upstream `doronz88/pymobiledevice3`,
  pinned at commit **`ec4ac06a850a6a884ca778350621f354faf347c6`** (the exact
  commit audited by the R1 upstream audit).
- `pyproject.toml` declares:
  `pymobiledevice3 @ git+https://github.com/doronz88/pymobiledevice3@ec4ac06a850a6a884ca778350621f354faf347c6`.
- `pip freeze` (repo venv `.venv`, CPython 3.12.10), relevant line:

  ```text
  pymobiledevice3 @ git+https://github.com/doronz88/pymobiledevice3@ec4ac06a850a6a884ca778350621f354faf347c6
  pytest==9.1.1
  ```

- Commit proof — `.venv\Lib\site-packages\pymobiledevice3-11.3.0.dist-info\direct_url.json`:

  ```json
  {"url": "https://github.com/doronz88/pymobiledevice3", "vcs_info": {"commit_id": "ec4ac06a850a6a884ca778350621f354faf347c6", "requested_revision": "ec4ac06a850a6a884ca778350621f354faf347c6", "vcs": "git"}}
  ```

- The local downstream fork (signal-forge-lab, `d73fa942...`, including its
  `wda_ext.py` extensions) is **not** used, imported, or referenced anywhere in
  the dependency or source tree. No fork delta exists; the pin was never
  advanced.
- Current upstream Python APIs are used directly: `PreferredRsdTunnel` /
  userspace RSD tunnel (in-process; no persistent `tunneld` requirement),
  `WdaServiceClient`, and lockdown/usbmux services. No legacy/downstream API
  shapes.
- Full installed-version evidence: `docs/PROVENANCE.md`.

## 4. Production files / modules created

Runtime package `src/praxiom/ios_runtime/`:

| File | Role |
|---|---|
| `__init__.py` | package doc + provenance boundary pointer |
| `models.py` | action variants, `RuntimeStatus`, `Observation`/element ref/screen, `ExecutionResult`, `RecoveryResult`, opaque revision, machine-readable error (code/phase/effect/retry_safe), no-effect vs PARTIAL/UNKNOWN distinction |
| `transport.py` | upstream transport/session lifecycle; in-process RSD; owned WDA session; WDA primitives (screenshot, source, window size, swipe/tap/drag, keys, home, launch) |
| `observation.py` | screenshot + accessibility acquisition, normalized elements, revision creation/invalidation, revision-bound refs, screenshot-pixel public space |
| `executor.py` | mandatory `expected_revision`, whole-batch preflight, batch limit, enum/range/string/coordinate validation, internal screenshot-pixel→WDA conversion, ordered execution, invalidation at first attempted mutation |
| `runtime.py` | public six-operation surface: `status()`, `observe()`, `execute()`, `invalidate()`, `recover()`, `close()` |
| `trace.py` | privacy-safe latency records + operation/error counters |

Repository scaffolding: `pyproject.toml` (package metadata + upstream pin +
pytest config), `LICENSE` (GPL-3.0-or-later, canonical text), `README.md`,
`.gitignore`, `docs/PROVENANCE.md`, `scripts/check_provenance.py` (provenance
guard), `tests/` (deterministic suite, incl. `tests/fixtures/` and
`tests/fixtures/PROVENANCE.md`).

The public runtime surface is **exactly six async operations**; `trace` is a
state projection attribute, not an operation. No plugin/factory/provider
hierarchies, no internal MCP hops, no OCR, and no Agent/Teaching/Knowledge/
domain/game logic exist in the runtime.

## 5. Test commands and results

All commands from the repository root with the repo venv
(`.venv\Scripts\python.exe`). The suite has **no physical-device dependency**.

| Command | Result |
|---|---|
| `python -m pytest -q` | **`127 passed in 0.70s`** (final run on the exact code state committed with this report; earlier same-state runs: `127 passed in 0.66s` / `1.46s` — timing jitter only) |
| `python scripts/check_provenance.py` | `OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml).` — exit 0 (this check also runs inside the pytest suite) |
| `python -c "import praxiom.ios_runtime"` | `import-ok` |

Test layout: `tests/test_acceptance.py` is the R3-07 contract fixture runner
driving scenarios `R2-A01`…`R2-A10` from the copied fixture artifact against
the real public runtime over a fake transport; slice tests live in
`test_models.py`, `test_observation.py`, `test_executor.py`,
`test_runtime.py`, `test_transport.py`, `test_trace.py`, `test_package.py`.

## 6. A01–A10 result matrix (fixture IDs)

Normative fixture source: the R2 acceptance fixture artifact
(`docs/design/fixtures/native-ios-runtime-v0.json` under the read-only
authority tree), copied **verbatim byte-for-byte** into
`tests/fixtures/native-ios-runtime-v0.json` (provenance recorded in
`tests/fixtures/PROVENANCE.md`; the artifact copy is JSON only — no Phone
Harness source or test utility was copied). The fixture artifact also contains
`R2-A11` (real-device smoke path), which maps to R3-08 and is out of scope for
the no-device suite.

| Fixture ID | Scenario | Result |
|---|---|---|
| `R2-A01` | ready status is privacy-safe and advertises limits | PASS |
| `R2-A02` | observe creates revision-bound element references | PASS |
| `R2-A03` | valid bounded batch executes in order | PASS |
| `R2-A04` | stale revision is rejected before side effects | PASS |
| `R2-A05` | invalid later action rejects the entire batch before side effects | PASS |
| `R2-A06` | ambiguous mid-batch failure is never blindly retryable | PASS |
| `R2-A07` | recover replaces stale device plumbing without replaying actions | PASS |
| `R2-A08` | close is idempotent and releases only owned resources | PASS |
| `R2-A09` | element reference from another revision is rejected | PASS |
| `R2-A10` | over-limit batch is rejected before side effects | PASS |
| `R2-A11` | real-device upstream-only smoke path | **PASS — bounded R3-08 smoke completed 2026-09-03** |

Each fixture scenario is also covered by dedicated slice-level tests named
after its ID across the module test files; all pass deterministically without
a phone. Fault injection proves the automatic replay count after an ambiguous
attempted effect remains zero (`R2-A06` semantics).

## 7. Attached-device R3-08 smoke — steps/results

**Status: PASS — 2026-09-03.** The earlier no-device evidence remains at
`docs/evidence/20260901_r3-08-blocked.md`; the authoritative closure record is
`docs/evidence/20260903_r3-08-attached-device-pass.md`.

The pinned upstream usbmux path detected one USB iPhone. `NativeIosRuntime`
established `RSD_USERSPACE` transport, started/used the installed WDA runner
through upstream APIs, captured screenshot + accessibility, executed a
revision-bound `Home()`, observed a fresh revision, executed a revision-bound
launch of Apple's Settings app, observed another fresh revision, and closed
cleanly. Five privacy-safe trace records were retained with zero trace errors.

No Phone Harness host package/process/MCP hop, downstream `pymobiledevice3`
fork, blind replay, destructive action, or private device identifier was used.

## 8. Device / iOS / transport description (redacted)

- Host: Windows 11 desktop (`Windows-11-10.0.26200-SP0`), CPython 3.12.10,
  repo venv `.venv`, git 2.54.0.windows.1.
- Target device class: physical iPhone (`iPhone18,3`), iOS `26.6.1`, directly
  attached over USB for the accepted smoke. No raw UDID, serial, ECID, MAC,
  IMEI, pair-record file name, or pair-record content is recorded anywhere in
  this repository.
- Accepted normal transport: **in-process RSD userspace tunnel** via
  upstream `PreferredRsdTunnel` (no subprocess, no CLI, no persistent
  `tunneld`), WDA via upstream `WdaServiceClient` over lockdown/usbmux
  services.
- WDA runner strategy: use the runner already installed on the paired device,
  launched/attached through upstream WDA service APIs; no custom runner build
  step introduced by R3. The runner bundle id is not needed in retained public
  evidence.

## 9. Upstream / runtime / environment issues discovered

1. **Upstream WDA session-id hard requirement (runtime fix, R3-08 review).**
   Pinned upstream `WdaServiceClient.get_window_size` / `send_keys` / `swipe`
   raise `WdaError("session_id is required")` when called without an explicit
   `session_id` — there is **no** cached-id fallback — while
   `get_screenshot` / `get_source` / `press_button` accept it. The R3-08
   review found the transport calling some primitives session-less (a lenient
   test fake masked this; the deterministic suite passed either way). Repair
   (included in the final report commit): every session-capable transport
   primitive now passes the owned session id explicitly, and the test fake
   mirrors upstream's hard precondition so a regression fails exactly as it
   would on a real device. Classification: `runtime_bug` → repaired; no
   upstream patch, no pin change, no adapter.
2. **`xonsh` pytest11 plugin crash (upstream transitive dependency +
   environment).** `xonsh` (pulled in by `pymobiledevice3`) auto-registers a
   pytest11 plugin that builds an interactive `prompt_toolkit` shell and
   crashes under non-console pytest runs on Windows
   (`NoConsoleScreenBufferError`). Repo-local composition config disables
   exactly that plugin (`addopts = "-p no:xonsh"` in `pyproject.toml`); `xonsh`
   is irrelevant to the runtime library path. Repo-local config, not an
   upstream patch.
3. **Provenance guard catch (R3-00).** The guard caught one docstring mention
   of the forbidden harness name inside `src/`; the source was reworded and
   the guard was not weakened.
4. **Windows usbmux environment.** The classic `\\.\usbmuxd` named pipe is
   absent; the pinned upstream resolves usbmux to TCP `127.0.0.1:27015`,
   served by the Store-app `AppleMobileDeviceProcess`. Probe code that reads
   the pipe instead of the upstream API is not authoritative. Host plumbing
   works; on the accepted rerun the authoritative upstream probe returned one
   USB device.
5. **Probe correctness note (R3-08, honesty record).** A first
   `list_devices()` probe call was made without awaiting the coroutine
   (`TypeError`); that was an API-usage error, not device evidence. The
   awaited re-run is the relied-on result.

## 10. Runtime-local adapters added

**None.** Upstream primitives were sufficient for the entire v0 surface; the
implementation uses current upstream Python APIs directly. The two repo-local
items are not runtime adapters:

- `-p no:xonsh` pytest addopts — test-runner composition config, not runtime
  code (§9.2);
- explicit `session_id` pinning in `transport.py` — direct use of the
  documented current-upstream parameter, not a wrapper/adaptor layer (§9.1).

No `wda_ext.py` equivalent, no vendored `pymobiledevice3`, no private patch,
and no fork delta exists. No internal MCP hops exist anywhere in the execution
path.

## 11. Provenance scan result

```text
$ .venv\Scripts\python scripts\check_provenance.py
OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml).
exit=0
```

The same check runs inside the pytest suite, so every deterministic run also
re-verifies it. Scope: production inputs (`src/`, `pyproject.toml`); `docs/`
and `README.md` are intentionally excluded because they must state the
prohibition itself.

## 12. Phone Harness execution-path statement

**Phone Harness is not in the production, build, or runtime execution path of
this repository — at all.** It is historical/reference material only. No
`phone_harness` package/module is imported, copied, renamed-port, called,
subprocessed, wrapped, depended on, or fallen back to here; there is no Phone
Harness MCP server/hop, adapter, or build dependency. This is enforced by
`scripts/check_provenance.py` (non-zero exit on any hit; runs in every test
run) and was proven during R3-00 when the guard caught and rejected a
docstring mention. The R3-08 smoke, when rerun, must additionally show the
same on the live execution path (no Phone Harness package/process/MCP hop).

## 13. Latency evidence

`trace.py` (R3-06) records, per operation, a privacy-safe
`TraceRecord(operation, duration_ms, error_code, failed_action_index,
outcomes)`:

- one record per `observe` call;
- one record per `execute` batch (batch duration plus the executor's
  per-action `ActionOutcome` durations on success);
- one record per `recover` call;
- machine-readable counters (`operations`, `errors`) and a bounded history
  (`records` / `render()`), records surviving `close()` for post-run
  inspection.

Deterministic tests assert latency records and counters exist and stay
privacy-safe (allowlisted structured fields only — no raw action payloads,
screen text, revision/element tokens, device identifiers, or exception
messages). **Real-device latency is now captured** by R3-08: observe calls were
approximately 7154.0 ms (initial startup), 4999.7 ms, and 1943.0 ms; execute
calls were approximately 636.8 ms (`home`) and 120.7 ms (`launch_app`). Broader
characterization remains R4 work.

## 14. Review/fix iterations performed

- `R3-00: repairs=0`
- `R3-01: repairs=0`
- `R3-02: repairs=0`
- `R3-03: repairs=0`
- `R3-04: repairs=0`
- `R3-05: repairs=0`
- `R3-06: repairs=0`
- `R3-07: repairs=0`
- `R3-08: repairs=1` — independent review of the deterministic work against
  the pinned upstream API surfaced the session-id precondition defect (§9.1);
  fixed with regression coverage. The repair was pending uncommitted at report
  time and is included in the final report commit (files:
  `src/praxiom/ios_runtime/transport.py`, `tests/test_transport.py`).

Every task passed independent review before its checkpoint commit; no gate was
weakened to make a test pass.

## 15. Remaining limitations deferred to R4

- Real-device latency characterization and trace-volume tuning (bounded
  history is a documented `ponytail:` deferral — raise/stream only if R4
  proves it needs full fidelity).
- WDA runner install/update policy beyond the accepted existing-runner path.
- Multi-device selection policy and device hotplug/unplug behavior beyond
  v0's single-device assumption.
- Broader real-device matrices (device/iOS-version coverage, stress/flake
  characterization) — explicitly out of R3 scope per orchestrator §17.
- Any contract gap discovered on real hardware (recorded as evidence and
  proposed as the smallest explicit contract change, never silently changed).

## 16. Final verification matrix

| Gate | Required result | Result |
|---|---|---|
| New repo/package import | PASS | PASS (`import-ok`) |
| GPL/dependency/provenance metadata | PASS | PASS (GPL-3.0-or-later `LICENSE`; `pyproject.toml` pins upstream; `docs/PROVENANCE.md`) |
| `pymobiledevice3` exact upstream pin verified | PASS | PASS (`ec4ac06a850a6a884ca778350621f354faf347c6` via pip freeze + `direct_url.json`) |
| Phone Harness production dependency scan | **0 hits** | **PASS — 0 hits** (exit 0; also enforced per test run) |
| Phone Harness production-source copy review | PASS | PASS (independent review each task; only the fixture artifact JSON was copied, with recorded provenance) |
| R2-A01 deterministic | PASS | PASS |
| R2-A02 deterministic | PASS | PASS |
| R2-A03 deterministic | PASS | PASS |
| R2-A04 deterministic | PASS | PASS |
| R2-A05 deterministic | PASS | PASS |
| R2-A06 deterministic | PASS | PASS |
| R2-A07 deterministic | PASS | PASS |
| R2-A08 deterministic | PASS | PASS |
| R2-A09 deterministic | PASS | PASS |
| R2-A10 deterministic | PASS | PASS |
| Review/fix loop complete | PASS | PASS (R3-00…R3-07 repairs=0; R3-08 repairs=1, closed) |
| Attached-device bounded R2-A11/R3-08 smoke | PASS | **PASS — 2026-09-03** |
| Phone Harness runtime/process/MCP edge | **NONE** | **NONE — confirmed on live smoke** |
| Permanent pymobiledevice3 fork delta | **NONE** unless documented exception | **NONE** (no delta, no patch, no pin change) |
| New repo Git status | clean | clean after the final report commit |

## 17. Final verdict

**`R3_COMPLETE`.**

R3-00 … R3-08 are accepted. The final connected-device gate passed on a
directly attached USB iPhone using the exact pinned upstream dependency. The
real-device run confirmed the six-operation boundary's observation/revision/
action/close behavior required by the bounded A11 slice, captured latency,
and required no Phone Harness execution hop, fork delta, adapter, or contract
expansion. R3 progress is **33/33 points (100%)**.

## 18. Privacy / redaction statement

This report records no UDID, serial, ECID, MAC, IMEI, pair-record file name or
content, screen text, or raw action payload. Device references are generic
product/class terms only; lockdown evidence is counts; PnP friendly names are
product/profile labels. This matches the runtime's own privacy rule for
`status()` and trace.

## 19. 2026-09-03 R3-08 closure update

The earlier readiness blocker is closed. After USB attachment, the fresh
pinned-upstream usbmux probe reported **1 attached USB device** and the bounded
smoke passed end-to-end:

- optional startup of an already-installed XCUITest runner is implemented with
  upstream `TestConfig` / `XCUITestService` and is owned by transport teardown;
- app launch uses upstream CoreDevice `AppServiceService`, avoiding replacement
  of the owned WDA session;
- fresh deterministic suite: **130 passed**;
- provenance guard: **PASS / 0 production Phone Harness dependencies**;
- no `pymobiledevice3` fork delta or runtime-local adapter was introduced.
- `Home()` and Settings launch both completed with revision invalidation and
  fresh observations between actions;
- trace counters recorded three observes, two executes, and zero errors.

The controlled repository/package rename checkpoint is therefore unblocked.
