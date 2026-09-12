# R9 Acceptance — Adaptive Execution Performance 47/47 (independently accepted)

- Sensitivity: PUBLIC
- Date: 2026-09-07
- Safety floor: accepted R7 validator + accepted R8 lifecycle; optimization fails closed to R7-safe baseline.

## R9 rubric result

All 47 R9 assertions in `tests/test_r9_adaptive.py` pass (R9-01..R9-47).
Full suite after final R8/R9 hardening: **306 passed**.
Guards: provenance PASS; boundary PASS; diff-check PASS.

## Mapping (summary)

- Telemetry 01-04: kinds-only, malformed dropped, baseline from ok-only, median/p90.
- DAG 05-10: revision-bound waves, self/unknown/cycle/missing-or-mixed-revision rejected, state-sensitive serialize, max-width bound.
- Batching 11-16: revision-bound confidence sizing; unbound/risky/state-sensitive/untrusted work falls back single; preflight+stops.
- Learning 17-20: live R8 trust-token macros/paths, distinct-revision all-NONE evidence, insufficient/unbound evidence untrusted; factory-issued stats retain private issuance claims so caller mutation/direct construction cannot forge reuse authority, and revocation/degradation/supersession invalidates reuse through the live token.
- Temporal 21-23: remaining/expired/none-deadline.
- Observation 24-28: frozen public R7 `ValidationDecision` input remains supported; an optional originating `ValidationContext` is strictly type/range validated, re-run through `AdaptiveValidator`, and must agree with any supplied decision; malformed/mismatched/revision-authoring/high-risk signals fail closed to full observe; only proven low-risk reversible non-state-sensitive work can use cheap validation.
- Routing 29-33: fast/standard/careful consumes only a factory-issued immutable `PerformanceBaseline`; forged/mutated baselines, insufficient samples, malformed/empty kind, high risk, irreversible work, missing telemetry, or invalid budget fail closed to careful; strategy tiers remain provider-neutral.
- Feedback 34-36: selector/recovery rates; no lifecycle leak.
- Fallback 37-41: latency/observe/recovery budgets; within-budget; safe_fallback shape.
- Integration 42-47: signal-failure fallback; batch stops; validator never creates revision; six ops; guard passes; per-kind budgets.

## Performance evidence (retained, deterministic)

- Safe-baseline sample (deterministic fixture, 10 execute + 5 observe events):
  execute median 14ms p90 16ms; observe median 43ms p90 45ms.
- Budgets: execute max 500ms default; per-kind independence proven (R9-47).
- Optimization disabled/fallback independently per kind; no increase in unsafe replay/stale use/hidden authority/false-green validation by construction + tests.

## Independent review

The non-author R9 review verified the 47-point mapping and found no blocking safety,
lifecycle, revision, authority, or scope defect. In particular it confirmed:

- DAG cycles/self/unknown dependencies fail closed and state-sensitive nodes serialize;
- batching preflight is mandatory and stops on PARTIAL/UNKNOWN/STALE_REVISION;
- learned macros are evidence-only until validated/revision-bound and do not create a replay edge;
- learned reuse authority is tied to private issuance claims plus a live R8 registry trust token and all-NONE distinct-revision evidence; mutating public frozen stats cannot forge authority;
- observation optimization preserves the actual R7 validator-decision contract and can additionally revalidate the originating context; malformed or mismatched context/decision never enables the cheap path and no decision can author a Runtime revision;
- latency routing accepts only a measured factory-issued baseline with enough samples and a valid kind; forged baselines, malformed kinds, high-risk work, or invalid/missing latency budget never select the fast route;
- feedback is evidence-only and cannot mutate lifecycle authority;
- malformed telemetry is dropped, baselines use valid successful events only, and regression budgets/fallback are per-kind;
- adaptive code has no direct device/transport/Phone-Harness/subprocess/MCP authority edge and no R10/Visual leakage.

Independent reviewer verdict: **APPROVED**.

- unresolved: `[]`
- errors: `[]`

## Acceptance: R9 47/47 ACCEPTED

Combined R8+R9 adversarial re-review: **APPROVED**, `unresolved=[]`, `errors=[]` after all cross-module findings were closed.

Final hardening review additionally covered real in-step preemption in an ordinary fresh interpreter, exact-type sandbox data admission, host-capture isolation, full-payload one-shot human approval, registry-owned authority snapshots, learned-stat/baseline issuance integrity, malformed validation/telemetry/routing inputs, computed `getattr` authority bypasses, and R10/Visual scope leakage. The final independent reviewer returned **APPROVED**, `unresolved=[]`, `errors=[]`.

Runtime-owned Goal Reviewer on committed clean software HEAD `25d59d7d832b430556e56141198e03e8afd77c62`: **GOAL_PASS**, `R8=47/47`, `R9=47/47`, `combined=94/94`, `unresolved=[]`, `errors=[]`.

Runtime-owned Final Judge on the same committed clean HEAD: **PASS**, `R8=47/47`, `R9=47/47`, `combined=94/94`, `unresolved=[]`, `errors=[]`.
