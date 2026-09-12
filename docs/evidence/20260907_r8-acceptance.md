# R8 Acceptance — Skill Foundry 47/47 (independently accepted)

- Sensitivity: PUBLIC
- Date: 2026-09-07
- Scope: R8 only; no R9 production authority claimed by this record.

## R8 rubric result

All 47 R8 assertions in `tests/test_r8_skill.py` pass (R8-01..R8-47).
Full suite with R8+R9 after final hardening: **306 passed**.
Guards: provenance PASS; boundary PASS (skill/adaptive included); diff-check PASS.

## Mapping (summary)

- R8-A need (01-08): repeated-gap detection, one-off/stale/distinct/single-revision/insufficient-evidence/confidence-alone/empty-summary rejections.
- R8-B candidate (09-14): shape, authority subset, no domain taxonomy, no raw bypass, version positive, pre/post required.
- R8-C gates (15-23): schema/authority/human-gate/privacy/dependency/revision/safety/code-ref + order.
- R8-D sandbox (24-33): minimal ok; network/fs/credential/device rejected; plain-function static gate rejects unsafe imports/globals/closures/defaults, exception handlers, nested/generated control-flow escapes, attribute/external mutation access, unsafe formatting/resource-amplification ops, shadowed trusted globals, mutable host captures, non-finite/oversized/subclassed data; input state is deeply isolated; real wall-clock + injected-clock checks and cancellation/resource checks run during generated-step execution (line-event fallback plus opcode tracing); fresh-interpreter regression proves a dynamically compiled non-returning step is preempted outside pytest; zero device calls.
- R8-E reuse (34-42): valid reuse; partial/unknown/unrecognized/stale/precondition-invalid mapped to reobserve/reject; linkage retained.
- R8-F lifecycle+executor (43-47): validated needs gates+two distinct evidence ids; one/same-revision repeated success never active; two distinct-revision successes active; degraded/superseded/revoked terminal; registry-bound ActiveSkill only; registry-owned execution-policy snapshot is authoritative even if caller-visible frozen fields are mutated; human-gated mutations require an independently issued, one-shot approval bound to exact skill/version/revision/full canonical payload; executor only via coordinator active/revision/authority and reserved-op overwrite rejected.

## Independent review repair round

The first non-author review returned `NEEDS_REPAIR` with six blocking findings and two minor findings. All were repaired and regression-tested:

1. reserved `extra["op"]` authority overwrite blocked;
2. arbitrary sandbox exceptions contained fail-closed;
3. callable static gate added for dynamic imports, unsafe globals/closures/defaults and device/process/network/filesystem escape paths;
4. lifecycle activation now requires successes on two distinct revisions;
5. executable skills now require fresh gates + lifecycle provenance through `SkillRegistry` identity binding;
6. non-cancellable sandbox policies rejected;
7. caller transition reasons retained in provenance;
8. procedure reuse aligned to the actual R7 knowledge lifecycle `{verified,promoted}`.

Final hardening additionally closed in-step preemption outside pytest, pure-data host-memory escapes, resource-amplification paths, caller-visible authority mutation, human-approval forgery/replay/payload substitution, and dynamic authority-dispatch bypasses. A final Python 3.14 review then found that f-string bytecode had split from `FORMAT_VALUE` into `FORMAT_SIMPLE` / `FORMAT_WITH_SPEC`; commit `25d59d7d832b430556e56141198e03e8afd77c62` changed the static gate to reject the complete `FORMAT_*` family before execution. The independent 3.14.4 re-review confirmed the transient huge-width allocation path is closed. All extra regressions remain within the frozen R8-01..47 rubric rather than adding criteria.

Repair verification: R8 **47/47 PASS**, targeted R8/R9/boundary **98/98 PASS**, full suite **306/306 PASS**, provenance/boundary/compileall/diff guards PASS.

Final independent re-review verdict: **APPROVED**.

- unresolved: `[]`
- errors: `[]`
- Python 3.14.4 format-opcode re-review: **APPROVED**, `unresolved=[]`, `errors=[]`.

## Hard-rule posture (review-confirmed)

- Generated code untrusted until all gates pass; sandbox makes zero device calls.
- Skill→device only via SkillExecutor→ExecutionCoordinator.run(expected_revision)→Runtime.execute.
- One success never promotes; PARTIAL/UNKNOWN never auto-replays.
- Safety/lifecycle outrank confidence; six Runtime ops preserved; no R10/Visual leakage.

## Reviewer verdict: APPROVED
## Acceptance: R8 47/47 ACCEPTED
