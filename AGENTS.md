# Praxiom repository instructions

These instructions apply to all implementation, review, refactoring, and Phase C readiness work in this repository.

Operational short name: **Phase C0** means **Phase C Readiness**. `Phase C0`
ends at the point where the first narrowly scoped Phase C Adaptive Live canary
is safe to start. The canary itself belongs to Phase C, not Phase C0.

## Non-negotiable architecture invariant: the learning platform is generic

Praxiom's learning, Experience, Shadow/Adaptive, promotion, telemetry, recovery, Runtime, Coordinator, and RunSession layers are **general-purpose infrastructure**. Merge Boss is only one domain used to exercise that infrastructure.

MUST:

- Keep game/app/task-specific rules in domain-facing code such as domain adapters, Skills, validators, policies, or other explicitly domain-scoped modules.
- Keep shared learning code expressed in generic concepts such as observation, state, action, outcome, evidence, confidence, risk, reversibility, episode, recommendation, promotion, fallback, and validation.
- Design new shared APIs so another unrelated iOS task can use them without importing, naming, or understanding Merge Boss concepts.
- Treat GoGoMatch and future non-game tasks as first-class consumers of the same learning foundation.
- During code review, explicitly check that new behavior has not moved domain semantics into shared infrastructure merely because Merge Boss is the current training target.

MUST NOT:

- Add Merge Boss concepts such as board cells, merge levels, generators, orders, energy, item families, or Merge Boss UI semantics to shared learning/runtime/coordinator/telemetry modules.
- Encode special cases such as `if domain == "mergeboss"` inside generic learning, adaptive, promotion, Runtime, Coordinator, RunSession, or telemetry paths.
- Tune a shared algorithm around a Merge Boss-only assumption when the requirement can instead be represented as domain data, a Skill contract, a validator, a policy, or an adapter.
- Promote Phone Harness-specific behavior, terminology, dependencies, or historical heuristics into Praxiom shared production code.
- Sacrifice generality solely to make a current Merge Boss experiment pass.

Before accepting any change to shared learning infrastructure, apply this test:

> If Merge Boss disappeared from the repository tomorrow, would this shared code and its API still make sense for GoGoMatch and an unrelated iOS automation task?

If the answer is no, move the logic to a domain-specific layer or stop and document why a generic abstraction is genuinely required.

Any intentional exception to this invariant requires explicit user approval and a dated design amendment. Do not silently weaken this rule during Phase C readiness work.

The detailed architectural rationale and review checklist are in:

`docs/design/LEARNING_PLATFORM_ARCHITECTURE_INVARIANTS.md`

## Phase C readiness

Phase C readiness work must preserve the invariant above. Evidence collection may be performed with Merge Boss as the primary real-device training domain, but Phase C infrastructure and promotion mechanisms must remain domain-agnostic. Domain-specific evidence may parameterize or configure generic mechanisms; it must not redefine their architecture.

Every Phase C0 work item must be classified as one of:

- `Generic platform`: reusable Praxiom mechanism that must remain domain-neutral;
- `Domain-specific evidence`: app/game/task-specific evidence used to validate or
  parameterize a generic mechanism, never shared-core logic;
- `Migration-only`: bounded compatibility/bootstrap work needed to move trusted
  historical material into Praxiom candidate evidence without creating a
  permanent legacy dependency.

Before starting or reviewing Phase C readiness work, read and follow:

`docs/evidence/PHASE_C_READINESS_PROGRESS.md`

Historical Phone Harness Knowledge/Teaching may be used only through the Legacy
Knowledge/Teaching Bootstrap rules defined there. Historical material is seed
evidence/candidate input, never inherited live authority. Imported facts must
retain provenance, pass hygiene/conflict handling, and receive current Praxiom
device corroboration before they can contribute to Phase C live promotion.

