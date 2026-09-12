# Praxiom Learning Platform Architecture Invariants

Status: **MANDATORY / architecture guardrail**  
Scope: all current and future learning-cycle, Phase C readiness, Adaptive/Shadow, Experience, telemetry, Runtime, Coordinator, Skill, and domain work.

## 1. Purpose

Praxiom is a general-purpose iOS learning and execution platform. Merge Boss is the first substantial learning domain, not the architecture of the learning system itself.

The repository must therefore preserve a strict boundary between:

1. **generic platform mechanisms**, which must remain reusable across unrelated tasks; and
2. **domain semantics**, which describe how a particular app, game, or workflow behaves.

This boundary is an architectural invariant, not a temporary preference.

## 2. Generic platform responsibilities

The following concepts belong in shared infrastructure when implemented generically:

- observation acquisition and revision tracking;
- action dispatch and effect accounting;
- Coordinator mutation authority;
- RunSession lifecycle and durable journal handling;
- Experience and episode recording;
- evidence aggregation;
- Shadow recommendation generation and comparison;
- confidence and promotion mechanisms;
- risk and reversibility handling;
- validation and postcondition plumbing;
- retry/replay safety and UNKNOWN/PARTIAL handling;
- fallback and recovery control;
- telemetry, latency, and outcome reporting;
- feature-gated Adaptive Live and bounded sequence mechanisms.

These facilities must not require knowledge of Merge Boss vocabulary or rules.

## 3. Domain-layer responsibilities

Domain-specific code may define, for example:

- what a domain state means;
- which observations are relevant to that domain;
- domain action candidates;
- success/failure postconditions;
- risk and reversibility classification for domain operations;
- Skill definitions and preconditions;
- validators and domain policies;
- UI semantics and app-specific state interpretation;
- task-specific reward or completion signals.

For Merge Boss, concepts such as board layout, merge levels, generators, orders, energy, item families, and game-specific UI recognition belong here.

For another application, a different set of domain concepts should plug into the same platform without requiring a redesign of the shared learning system.

## 4. Forbidden coupling patterns

The following are architecture violations unless an explicit dated amendment is approved:

- Merge Boss identifiers or rules inside shared learning, Runtime, Coordinator, RunSession, Adaptive, promotion, or telemetry implementations;
- shared branches such as `if domain == "mergeboss"` or equivalent hidden special cases;
- common data models whose required fields are meaningful only to Merge Boss;
- confidence, episode, promotion, recovery, or batching algorithms whose semantics depend on Merge Boss-specific concepts rather than generic evidence;
- using a Merge Boss test failure as justification to hard-code a game-specific workaround into shared infrastructure;
- importing Phone Harness-specific production code or semantics into the Praxiom shared foundation.

## 5. Required extension pattern

When a new requirement appears during Merge Boss learning, use this decision order:

1. Can it be represented as domain data or configuration?
2. Can it live in a domain adapter, Skill, validator, or policy?
3. Is there a genuinely reusable capability missing from the generic platform?
4. If a shared capability is necessary, define it using domain-neutral inputs/outputs and prove it with at least one non-Merge-Boss use case or generic deterministic test.

Only step 4 should change shared architecture.

## 6. Phase C-specific rule

Phase C may use Merge Boss evidence to determine whether a **generic** mechanism is safe to activate for a specific operation class. It must not turn Merge Boss behavior into shared platform behavior.

Examples:

- acceptable: a generic promotion engine receives evidence for a Merge Boss operation class and decides whether that class satisfies configured confidence/evidence criteria;
- acceptable: a Merge Boss validator supplies a causal postcondition through a generic validation interface;
- unacceptable: the promotion engine understands merge levels, generators, board occupancy, orders, or energy;
- unacceptable: the generic executor contains a Merge Boss-specific fast path.

Adaptive Live and sequence-live activation must therefore remain feature-gated and operation/domain scoped while the underlying mechanism stays generic.

## 7. Mandatory review questions

Every review that touches learning or Phase C readiness should answer:

1. Does any shared module now know a Merge Boss-specific noun, rule, state, or UI concept?
2. Could the same shared API be used unchanged by GoGoMatch?
3. Could an unrelated iOS workflow use the mechanism without dummy Merge Boss fields or assumptions?
4. Is new special-case logic better expressed as a Skill, validator, domain policy, adapter, or configuration?
5. Are evidence/confidence/promotion semantics generic rather than game-specific?
6. Has any Phone Harness-specific behavior leaked into Praxiom production architecture?
7. If shared architecture changed, is the reusable need demonstrated rather than inferred from one Merge Boss scenario?

Any "yes" to question 1 or 6, or "no" to questions 2, 3, or 5, blocks acceptance until the boundary is repaired or an explicit design amendment is approved.

## 8. Generality test

Use this as the final architectural check:

> Remove Merge Boss conceptually. The shared Runtime, Coordinator, RunSession, Experience, learning, Adaptive/Shadow, promotion, safety, and telemetry layers should still form a coherent platform for GoGoMatch and unrelated iOS tasks.

If that is not true, the implementation has drifted from the intended architecture.

## 9. Change control

This invariant may be changed only by an explicit, dated architecture decision with user approval. A temporary experiment, schedule pressure, test convenience, or Phase C milestone is not sufficient justification to bypass it.

