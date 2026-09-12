# DSH execution prompt — Praxiom R4 + R5

Use this prompt with the current DSH Planner / Plan-and-Run policy.

Primary handoff:

```text
<repository-root>\docs\design\20260904_r4-r5_orchestrator_handoff.md
```

Repository:

```text
<repository-root>
```

---

You are the implementation Planner for **Praxiom R4 + R5**.

Read the primary handoff first, then inspect the CURRENT Praxiom repository,
current Git state, current R2/R3 evidence, current pinned upstream
`pymobiledevice3`, current device/WDA state, and current tests. Current evidence
overrides cached handoff statements.

The preparation-time probe on 2026-09-04 saw `DEVICE_COUNT=0`; re-probe rather
than assuming that state is still true. If no iPhone is attached, finish every
AI-executable deterministic implementation/test/review task and preserve only
the precise physical real-device gate as blocked.

Plan and execute R4 and R5 end-to-end: implementation, deterministic tests,
real-device acceptance, privacy-safe evidence, independent review, repairs,
re-review, R5 separation closure, final verification, retained completion
reports, and runtime-owned Goal Certification. Do not stop at planning or a
partial smoke when further AI-executable work remains.

**Sensitivity is PUBLIC.** Every authored Agent task must explicitly use
`sensitivity: 'public'`. Treat this ordinary/open-source repository as public;
do not infer private sensitivity merely because files are local. Use only
`modelHint: fast | balanced | deep`; never specify provider/model names from
workflow source. Stable Routing remains the sole provider/model authority.

Use a maximum useful concurrency of 3. The physical iPhone is a **single
mutation lane**: never let two agents mutate the same device concurrently.
Parallelize only read-only auditing, non-overlapping implementation, evidence
analysis, and review where safe.

Critical sequence:

1. read-only current-state audit: contract/evidence, runtime/tests, and
   host/device/provenance;
2. freeze the smallest implementation/evidence delta;
3. add only necessary deterministic acceptance harnesses/regressions and
   root-cause runtime fixes;
4. execute the R4 real-device matrices in one mutation lane:
   transport/lifecycle -> observe/revision -> all safe v0 action primitives and
   bounded batch -> failure/recovery -> latency/trace;
5. produce the required old-vs-new behavior evidence report;
6. independent deep R4 review by a non-author; repair every blocking finding,
   rerun affected/full/device gates, and re-review;
7. only after R4 passes, perform R5 dependency/provenance/source-copy audits,
   active-path docs/XMind work, historical-reference classification, and the
   migration completion report;
8. independent deep R5/final review; repair/retest/re-review until no blocking
   finding remains;
9. leave Goal-level Independent Reviewer / Repair / Re-review / Final Judge to
   the runtime-owned Certification path;
10. create focused local Git checkpoint commits as appropriate; do not push or
    publish remotely.

Hard invariants:

- preserve the R2 six-operation public runtime boundary unless real-device
  evidence proves a minimal contract change is required;
- no Phone Harness production/build/runtime dependency, import, subprocess,
  MCP hop, compatibility shim, fallback, or copied/renamed production source;
- keep unmodified pinned upstream `pymobiledevice3` unless the R1 fork gate is
  actually satisfied;
- preserve whole-batch preflight, mandatory/current revision, revision-bound
  refs, bounded batch limits, effect-aware errors, no blind replay, and owned
  resource shutdown;
- device acceptance actions are bounded, reversible/non-destructive, and must
  not purchase, submit, message, delete user content, or alter account/security
  settings;
- evidence must remain privacy-safe and omit device identifiers, pair records,
  secrets, raw user screen content, and raw action payloads;
- default deterministic tests remain phone-independent;
- do not start R6 or later work;
- do not weaken a test or gate to get a pass;
- if a physical/external step is genuinely impossible, continue every other
  AI-executable task and report the smallest precise blocker instead of falsely
  declaring R4/R5 complete.

R4 work items and points:

- R4-01 transport/lifecycle matrix — 3
- R4-02 observe matrix — 3
- R4-03 action matrix — 5
- R4-04 failure/recovery matrix — 5
- R4-05 latency/trace baseline — 2
- R4-06 old-vs-new evidence report — 2
- R4 total — 20

R5 work items and points:

- R5-01 dependency audit — 2
- R5-02 provenance/source-copy review — 2
- R5-03 active-path docs/XMind — 1
- R5-04 historical-reference classification — 1
- R5-05 migration completion report — 1
- R5 total — 7

R4 exit requires full R2-A11 retained real-device evidence, required
capabilities passing on the current target environment, deterministic tests
green, honest environment/upstream/runtime classification, zero new Phone
Harness execution dependency, no unjustified permanent upstream fork, and an
independent accepted R4 review.

R5 exit requires accepted R4, zero Phone Harness production/build/runtime
dependency or execution edge, provenance/source-copy review PASS, current
active-path documentation, historical-only classification of old references,
an independently reviewed migration completion report, final regression PASS,
and a clean intended Git checkpoint state.

Completion is 100% only when no AI-executable R4/R5 work remains and the final
report includes points, exact changed files/commits, deterministic test totals,
real-device matrix evidence, latency baseline, review findings/repairs,
provenance/dependency results, runtime Certification verdict, external/physical
coverage limits, and final R4/R5 status.

Begin now and continue through runtime-owned Certification.

