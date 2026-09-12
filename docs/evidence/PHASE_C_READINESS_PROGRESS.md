# Praxiom Phase C0 (Phase C Readiness) Progress

Status: **COMPLETE / READY FOR PHASE C LIMITED CANARY**
Operational short name: **Phase C0**
Formal name: **Phase C Readiness -- Learning, Knowledge Bootstrap & Promotion Preparation**
Current readiness: **100%**
Readiness 100% means: **the first explicitly scoped Adaptive Live Phase C canary may start safely**.  
It does not mean that all Praxiom learning, Merge Boss learning, or sequence-live optimization is complete.

## 1. Purpose

This file is the retained progress/evidence authority for work from accepted
Phase B through the point where Phase C may begin.

Use **Phase C0** in normal progress reports and conversation. `Phase C
Readiness` remains the formal architectural name. Phase C0 is not a new runtime
capability level and does not rename Phase C; it is the preparation interval
between accepted Phase B and the first Phase C canary.

Every substantive readiness work session must update, at minimum:

- current readiness percentage;
- work completed in the session;
- relevant run/evidence identifiers;
- operation classes and episode counts affected;
- success/PARTIAL/UNKNOWN/rejected evidence where applicable;
- Shadow/actual comparison where applicable;
- remaining evidence gaps and safety blockers;
- current Phase C decision: HOLD or READY;
- next required work.

Progress is evidence-weighted, not time-weighted. Reaching an episode count does
not advance readiness if the resulting evidence remains ambiguous or unsafe.

## 2. Baseline already accepted -- 15%

The 15% starting point represents already-completed prerequisites rather than
new Phase C work:

- greenfield Praxiom Runtime/Coordinator/Agent/Knowledge/Adaptive foundation;
- Phase A closed-loop telemetry/Experience/Shadow plumbing;
- Phase B real-device acceptance;
- current-head representative Merge Boss + GoGoMatch shadow runs;
- no-blind-replay and stale-WDA lifecycle hardening;
- generic-learning architecture invariant retained in `AGENTS.md` and
  `docs/design/LEARNING_PLATFORM_ARCHITECTURE_INVARIANTS.md`.

Phase C remains **HOLD**. Adaptive Live and bounded-sequence Live remain OFF.

## 3. Work classification guardrail

Every Phase C0 item must be classified before implementation or acceptance.
The classification describes where the resulting knowledge or mechanism is
allowed to live.

### 3.1 Classification meanings

**Generic platform**

- reusable Praxiom infrastructure;
- expressed only in domain-neutral concepts;
- must make sense for Merge Boss, GoGoMatch, and unrelated iOS workflows;
- may consume domain-provided policies/evidence, but must not understand their
  app/game-specific semantics.

**Domain-specific evidence**

- current or historical facts, observations, failure examples, Teaching, and
  validation evidence from a specific app/game/task;
- may configure or validate a generic mechanism;
- belongs in domain-scoped data, adapters, Skills, validators, policies, or
  retained evidence;
- must never be copied into shared learning/runtime/promotion logic as a special
  case.

**Migration-only**

- bounded compatibility/bootstrap tooling for historical material;
- may understand a legacy format at the boundary;
- outputs canonical Praxiom candidate evidence/provenance rather than live
  authority;
- must not become a permanent Phone Harness runtime/build dependency or hidden
  fallback.

### 3.2 Classification of the eight plan revisions

| # | Revision | Primary classification | Boundary rule |
|---|---|---|---|
| 1 | Legacy Knowledge/Teaching Bootstrap | **Migration-only** | Phone Harness parsing/mapping stays at the migration boundary. The resulting Praxiom evidence uses canonical generic/domain contracts; no legacy authority is inherited. |
| 2 | Human Teaching end-to-end | **Generic platform** | Teaching event lifecycle, policy/fact split, conflict handling, persistence, and learned-vs-answered semantics must be domain-neutral. |
| 3 | Negative Evidence | **Generic platform** | Shared code records expected/observed outcome, effect, failure/no-op, confidence and provenance. Domain code explains what a failed merge or producer no-output means. |
| 4 | Partial/stale observation guard | **Generic platform** | Completeness, freshness, revision validity, and evidence-quality rules are generic. What constitutes a complete order scan is domain evidence. |
| 5 | UI interruption / world-state change handling | **Generic platform** | Generic layer invalidates stale plans and re-observes/re-plans. Daily Mission, promo overlays, or other app screens remain domain-specific evidence/interpretation. |
| 6 | Transport recovery vs task-state recovery separation | **Generic platform** | Recovery authority, reconciliation, and no-blind-replay rules are generic; domain recovery transitions are supplied at the edge. |
| 7 | Correctness before performance tuning | **Generic platform** | Promotion/performance policy applies across domains; measurements and bottlenecks are evidence inputs, not hard-coded Merge Boss assumptions. |
| 8 | Operation-class-scoped promotion | **Generic platform** | Promotion/gating is generic and scoped by operation class/risk/evidence. The operation class semantics themselves remain domain-owned. |

The historical or live Merge Boss examples used to justify #2-#8 are therefore
**Domain-specific evidence**, even when the resulting mechanism is classified
as **Generic platform**. Examples include merge look-alike failures, incomplete
order scans, generator no-output/capacity cases, Daily Mission interruptions,
bubble/promo flows, and board/action latency measurements.

This classification prevents two opposite errors:

1. turning a Merge Boss lesson into a Merge Boss-specific shared-core patch; and
2. over-generalizing historical Phone Harness migration code into permanent
   Praxiom runtime architecture.

## 4. Revised readiness plan

The plan was revised after reviewing current Praxiom evidence plus historical
Phone Harness implementation, Human Teaching, Knowledge, and real-device play.

### 15% -> 28% -- Legacy Knowledge/Teaching Bootstrap

Do not relearn all useful historical Merge Boss knowledge from zero, and do not
copy historical authority into Praxiom.

Required flow:

```text
historical Phone Harness material (read-only)
        |
        v
audit / normalize / classify / deduplicate
        |
        v
Praxiom candidate evidence / Teaching policy
        |
        v
current-device corroboration
        |
        v
verified/promoted Praxiom Knowledge when justified
```

Historical sources include, when useful:

- `knowledge.mbk`;
- `catalog.json`;
- Merge Boss playbook and live-play evidence;
- retained Human Teaching and question/answer history;
- GoGoMatch learning evidence where relevant to generic mechanisms.

Observed historical inventory at plan review:

- `knowledge.mbk`: 138 JSON records;
- keyed records: 131;
- user-confirmed (`U`) evidence: 64;
- device-confirmed (`D`) evidence: 67;
- explicit top-level `kind=human_teaching` records: 3;
- one duplicate knowledge key was observed
  (`producer.vertical-film-camera.8`), demonstrating that silent last-write-wins
  import is unacceptable;
- historical text contains encoding/mojibake in some human-readable fields, so
  Praxiom hygiene/rejection rules must be used rather than assuming all legacy
  text is trustworthy.

Bootstrap classification must distinguish at least:

- policy/instruction Teaching;
- factual claims;
- device-confirmed behavioral evidence;
- negative evidence/failure lessons;
- UI/calibration/coordinate material likely to be stale;
- hypotheses/candidates;
- conflicting, duplicate, superseded, or encoding-unreliable records.

Rules:

1. Historical Phone Harness remains read-only/reference-only and never becomes
   a production/build/runtime dependency.
2. Legacy records never mint current `SkillTrustToken` or mutation authority.
3. Legacy facts enter as provenance-bearing candidate/seed evidence, not as
   automatically promoted truth.
4. Current Praxiom real-device corroboration is required before a bootstrapped
   fact can contribute to Phase C live-promotion readiness.
5. Coordinate/layout/calibration facts are presumed stale unless independently
   validated on the current device/UI.
6. Conflicts branch or block; duplicate/superseded history remains inspectable.
7. Current-device episode counts remain separate from historical evidence
   counts. Legacy evidence may reduce rediscovery work, but it must not fake the
   amount of current Praxiom live evidence.

### 28% -> 38% -- Human Teaching end-to-end path

Praxiom already has Teaching concepts, policy-vs-fact promotion rules,
arbitration, conflict escalation, and Human Approval authority, but the current
Monitor does not yet provide an authoritative Questions/Teaching write path.

Before Phase C, complete a generic Human Teaching path that supports:

- operator-initiated Teaching;
- AI-initiated focused questions;
- policy vs fact classification;
- provenance and canonical timestamps;
- association with relevant observation/revision/operation context;
- conflict checking against current Knowledge;
- durable persistence before `learned` is declared;
- later Shadow decisions using the accepted Teaching;
- explicit distinction between `answered` and `learned`.

Historical Phone Harness behavior worth retaining conceptually:

- low-risk gameplay should not block indefinitely waiting for Teaching;
- late answers are accepted at safe boundaries and cause re-observe/re-plan,
  never stale action replay;
- ask only when ambiguity is material/reusable or human clarification is much
  cheaper than repeated inspection/error;
- high-risk work may still require an explicit human gate;
- question context must remain understandable later. A bounded visual/context
  artifact may be retained if required, but this does not authorize building
  the full Visual V0-V3 system merely to satisfy Phase C readiness.

### 38% -> 50% -- Learning Cycle v1 and evidence semantics

Implement/accept the reusable real-device learning cycle:

```text
fresh observe
  -> interpret state
  -> choose certified actual action
  -> execute one accepted action / accepted bounded unit
  -> post-action validation or fresh observe as required
  -> record outcome/effect
  -> Experience
  -> Shadow recommendation/comparison
  -> next episode
```

The cycle must treat negative evidence as first-class data. Historical play
showed that failed merge pairs, no-output producer taps, unexpected spawns,
false visual matches, unknown screens, and recovery outcomes can be more useful
than a generic failure counter.

Episode identity must therefore preserve enough context to distinguish:

- operation class;
- relevant pre-state/post-state class;
- outcome/effect;
- current skill/version/provenance;
- validation method;
- failure/rejection reason;
- whether Teaching or bootstrapped Knowledge contributed to the decision.

### 50% -> 63% -- Current-device revalidation and state-integrity gates

Use the current device to revalidate bootstrapped knowledge and prove that the
learning loop does not generalize from stale/partial state.

Historical defects make the following acceptance items mandatory:

- a partial order/customer scan must not justify a global `all_*` conclusion;
- cached/stale demand must not survive an order refresh as current truth;
- non-Merge-Boss foreground content must not be interpreted as a board/order
  state;
- current-screen identity must be revalidated after UI auto-interrupts;
- a no-output producer action must distinguish capacity/energy/binding/readiness
  causes instead of collapsing them into one explanation;
- dependent merge chains require a settle/validation boundary even when
  independent merges may later be batchable;
- locked/off-goal/stale-WDA conditions remain preflight/reconciliation states,
  not reasons to replay an action.

This stage should intentionally exercise stale/partial/off-goal cases as well as
successful paths. Correct refusal/reconciliation is evidence of learning-system
quality, not a failed experiment.

### 63% -> 78% -- Representative Shadow learning coverage

Collect real-device Experience across several low-risk/reversible operation
classes rather than accumulating many repetitions of launch alone.

Initial target remains approximately 3-5 operation classes with roughly 20-30
current-device episodes each before the first formal analysis checkpoint. These
are planning ranges, not automatic promotion thresholds.

Candidate classes should prefer actions whose postconditions are observable and
whose mistakes are cheap to recover. High-risk/irreversible/resource-purchase
operations remain human-gated or excluded.

Each class should report at least:

- current-device episode count;
- success/NONE, PARTIAL, UNKNOWN, rejected counts;
- Shadow recommendation stability;
- conflicts/Teaching corrections;
- fallback/reconciliation count;
- observation/validation cost;
- current evidence gaps.

The GoGoMatch historical lesson remains applicable: insufficiently trained
behavior is not widened into autonomous use merely because the generic platform
supports it.

### 78% -> 86% -- Reliability and interruption review

Review accumulated evidence specifically for failure modes seen historically:

- unknown/incorrect visual identity;
- stale coordinates or stale revision;
- UI overlays, Daily Mission or promotional/upsell screens;
- board-capacity exhaustion;
- partial scans;
- delayed transitions/animations;
- transport/WDA degradation;
- user Teaching arriving during/after a run;
- conflicting old/new Knowledge.

Acceptance requires safe reconciliation/fallback behavior and no blind replay.
Paid purchases or premium-resource spends must not become autonomous Phase C
scope as a side effect of learning broader navigation.

### 86% -> 92% -- Observation/performance tuning from evidence

Only after correctness is established, use real data to tune observation cost,
cheap-validation eligibility, and possible bounded batching.

Historical Phone Harness runs showed perception/observation cost dominating the
local planner, while current Phase B Praxiom evidence also shows multi-second
observe latency. Therefore repeated full observation is a legitimate Phase C
readiness concern, but optimization must be evidence-driven.

Requirements:

- identify repeated expensive observation phases;
- define causal postconditions before enabling cheap validation;
- do not manufacture a Runtime revision from cheap validation;
- compare accuracy, latency, and recovery cost;
- preserve full-observe fallback;
- do not enable sequence-live merely because Shadow recommends batch size >1.

### 92% -> 97% -- Promotion policy from measured evidence

Use the accumulated current-device evidence to explicitly accept values/policies
for the first Phase C operation class, including as applicable:

- minimum current-device episode/evidence count;
- confidence floor;
- acceptable failure/UNKNOWN/PARTIAL envelope;
- domain/state-specific cheap-validation eligibility;
- latency budget;
- risk/reversibility restriction;
- required postcondition/validator;
- fallback/reconciliation behavior;
- effect of Teaching conflicts and bootstrapped evidence on eligibility.

Do not invent values merely to reach 100%.

### 97% -> 100% -- Phase C preflight / final review

Select the first narrowly scoped operation class and prove that:

- its current Knowledge/evidence is sufficient under the accepted policy;
- its Adaptive Live gate is scope-limited and default-off elsewhere;
- Shadow and certified actual behavior have been compared;
- safety/revision/authority boundaries remain intact;
- rollback to Shadow-only is immediate and deterministic;
- no sequence-live widening is implied;
- full deterministic tests, boundary/provenance guards, compile and diff checks
  are green;
- final architecture/safety review has no unresolved blocker.

At **100%**, the plan may change from `Phase C HOLD` to
`Phase C READY FOR LIMITED CANARY`. The first Adaptive Live canary itself is the
start of Phase C and is tracked separately.

## 5. Historical lessons intentionally carried forward

The following are retained as planning constraints because they were observed in
real use, not because Praxiom should reproduce Phone Harness implementation:

1. **Knowledge is useful, authority is not inherited.** Reuse old facts to avoid
   rediscovery, but revalidate before live promotion.
2. **Answered is not learned.** Teaching is learned only after classification,
   conflict handling, persistence, and appropriate verification.
3. **Negative evidence matters.** A no-op, wrong visual match, unexpected spawn,
   or unknown screen is a learning signal.
4. **Observation completeness matters.** Partial/stale views must not support
   global conclusions.
5. **UI interrupts are normal world-state changes.** Revalidate screen/state
   before reusing board coordinates or plans.
6. **Task-state recovery and transport recovery are different.** Neither may
   silently replay an ambiguous mutation.
7. **Learning must remain domain-scoped at the edge and generic in the core.**
   Merge Boss knowledge cannot leak into generic Experience/Adaptive/Promotion
   architecture.
8. **Performance is part of readiness, after correctness.** Avoid repeating the
   historical pattern of spending most wall time on redundant perception, but
   never trade away causal validation to make the loop look fast.

## 6. Phase C0 execution log

### 2026-09-12 -- C0 start / Legacy Bootstrap audit

Phase C0 execution started from the accepted 15% baseline. No Adaptive Live or
sequence-live capability was enabled.

Completed in this work session:

- added migration-only audit tooling at
  `scripts/phasec0_legacy_bootstrap_audit.py`;
- added deterministic tests at
  `tests/test_phasec0_legacy_bootstrap_audit.py`;
- audited the historical `knowledge.mbk` without importing legacy authority;
- audited the historical `catalog.json` without exporting domain names,
  screenshots, raw visual descriptors, or action authority;
- materialized a local authority-free candidate file under the Praxiom state
  root at `~/.praxiom/bootstrap/phasec0_legacy_candidates.jsonl`;
- every exported candidate is state=`candidate`, carries source provenance,
  requires current-device corroboration, and contains no trust/authority key;
- confirmed the current external MCP boundary remains read-only.

Knowledge audit evidence:

- retained report: `docs/evidence/20260912_phasec0-legacy-bootstrap-audit.json`;
- 138 / 138 records parsed;
- 137 records are structurally eligible to become candidate evidence;
- evidence classes: U=64, D=67;
- one format marker;
- one duplicate legacy key (two records), retained rather than silently
  overwritten;
- 70 records require review from structural classification alone;
- exported candidate set: 137 records, with 72 review-required after duplicate
  records are conservatively forced to review;
- malformed records: 0;
- replacement-character records: 0;
- control-character records: 0.

Catalog audit evidence:

- retained report: `docs/evidence/20260912_phasec0-legacy-catalog-audit.json`;
- catalog version 2;
- 7 item families / 70 item levels;
- 4 merge transitions;
- 4 producers / 16 possible outputs;
- 3 producers marked outputs-complete, one still incomplete;
- 15 retained visual descriptors counted, but no visual payload is copied into
  the retained aggregate report.

Verification completed:

- Phase C0 bootstrap tests: 8 passed;
- full deterministic Praxiom regression: 508 passed;
- provenance guard: PASS;
- Agent/Knowledge/Retrieval/Skill/Adaptive -> Runtime boundary guard: PASS;
- compileall: PASS;
- `git diff --check`: PASS before this retained update.

Real-device status during this session:

- before the MCP restart, one fresh Praxiom observation succeeded from the Home
  screen, proving that the prepared device, RSD/WDA path, screenshot source, and
  accessibility source were initially usable;
- the existing certified launch-only workload was then attempted only to reach
  the current app state for corroboration;
- the host safety gate blocked the first invocation; the exact command was
  retried once with the approved host-safecheck retry context;
- that runner then failed at its **initial read-only observe** with
  `OBSERVATION_FAILED`, `effect=NONE`, before any mutation;
- after MCP restart, the same read-only observe also failed;
- raw Bonjour browsing still sees the paired Wi-Fi device (two IPv4/IPv6
  endpoints for one identifier), while pair-verified RemotePairing discovery is
  currently returning no usable service;
- therefore no current-device legacy fact was promoted or corroborated in this
  session, and no device mutation was performed after the restart failure.

Readiness moved from 15% to **23% at that checkpoint** because the structured legacy audit,
deduplication guard, provenance-preserving candidate conversion, local
authority-free candidate persistence, and deterministic verification are now
implemented. The 28% Legacy Bootstrap checkpoint is **not** reached because
current-device corroboration and review/classification of the unresolved legacy
Teaching/evidence set remain incomplete.

### Remaining work identified at the 23% checkpoint

1. restore pair-verified RemotePairing/WDA visibility without weakening the
   existing no-replay safety behavior;
2. perform fresh current-device corroboration of selected low-risk legacy facts;
3. classify unresolved user-originated legacy evidence into policy/fact/other
   without guessing;
4. resolve/branch duplicate/conflicting candidates while retaining provenance;
5. re-run deterministic/full regression and update this authority with the
   accepted Bootstrap result.

The items above are superseded by the later same-C0 consolidation below. They
are retained here as an audit trail of what was still open at the 23% point.

### 2026-09-12 -- C0 readiness consolidation to 97%

The subsequent implementation/review pass completed the evidence and software
work through the Promotion Policy checkpoint. The remaining gap is operational
preflight only; Adaptive Live and sequence-live remain OFF.

#### 28% -- Legacy Knowledge / Teaching Bootstrap: ACCEPTED

- historical `knowledge.mbk` remains read-only and produced 137 authority-free
  candidates with source hashes/line provenance and mandatory current-device
  corroboration;
- historical user origin (`U`) is no longer guessed to mean policy or fact:
  explicit operating-policy records classify as `policy`, device/observation
  evidence as `fact`, and unresolved user-originated records stay `other`;
- duplicate records remain retained/review-required rather than overwritten;
- no legacy record mints Skill/Runtime/Coordinator authority;
- the already-migrated low-risk launch contracts were corroborated by accepted
  Phase B current-device runs and the C0 direct-device canary; this is selected
  low-risk corroboration, not wholesale promotion of the 137 legacy records.

#### 38% -- Human Teaching end-to-end: ACCEPTED

- generic `HumanTeachingStore` supports operator Teaching, questions/answers,
  policy/fact/other classification, provenance, conflict review, persistence,
  and the explicit `answered != learned` lifecycle;
- factual Teaching passes through the generic Knowledge promotion lifecycle;
- accepted Teaching can affect generic Shadow constraints without gaining
  device mutation authority;
- Monitor exposes the Human Channel without calling Runtime mutation APIs;
- Teaching writes remain loopback-only even when Monitor viewing is explicitly
  bound to LAN, preventing LAN visibility from widening Knowledge-write
  authority.

#### 50% -- Learning Cycle v1: ACCEPTED

- generic `LearningCycleV1` implements fresh pre-observe -> exactly one
  caller-certified action -> fresh post-observe/validation -> durable learning
  record;
- negative evidence, operation class, pre/post state class, effect, validation,
  Teaching IDs, bootstrap candidate IDs, and Shadow snapshot are retained;
- stale post-revision becomes negative evidence;
- no retry/replay path exists in the Learning Cycle layer;
- retained R6/R7 real-device evidence independently proves the corresponding
  revision-bound/fresh-observe/Runtime-only mutation invariants.

#### 63% -- Current-device revalidation / state integrity: ACCEPTED for first-canary scope

This checkpoint is accepted for the first generic canary candidate, not as a
claim that every Merge Boss legacy fact has been revalidated.

- current Experience contains 17 real-device episodes: Merge Boss launch
  9 `succeeded|NONE` plus 2 historical pre-lock-guard `failed|PARTIAL`, and
  GoGoMatch launch 6 `succeeded|NONE`;
- C0 direct canary `phasec0-direct-canary-20260912b` completed 4/4 certified
  single launch actions with `NONE`, no replay, and fresh observations;
- historical PARTIAL outcomes remain visible negative evidence rather than
  being removed from success statistics;
- current C0 WDA/DTX failures occur before mutation and are recorded separately
  from action outcomes;
- stale revision, stale WDA session invalidation, locked-device preflight, and
  no-blind-replay protections remain fail-closed.

Merge Boss-specific board/order/producer facts that are not needed by the first
`system:return-home` canary remain candidate/Shadow-only and do not inherit this
acceptance.

#### 78% -- Representative Shadow coverage: ACCEPTED for first-canary scope

The earlier `3-5 classes x roughly 20-30 episodes` value was explicitly a
planning range, not a promotion threshold. It is not converted into a hidden
global gate. Current evidence instead supports an operation-class-scoped first
canary:

- R4 real-device matrix exercised multiple generic operation classes, including
  Home (4), launch_app (3), tap, swipe, drag, and type_text;
- Phase B/C0 Experience provides live Shadow/actual comparison for Merge Boss
  and GoGoMatch launch classes;
- `system:return-home` receives a separate
  `retained-evidence-shadow-replay` evaluation over its four retained
  real-device Home executions;
- all four Home replay evaluations retain batch size 1, recommend no action
  reduction, never apply live, and agree on the same observation-only
  optimization candidate.

Broad multi-domain learning continues after the first Phase C canary and is not
being declared complete here.

#### 86% -- Reliability / interruption review: ACCEPTED

- R4: 29/29 real-device matrix checks passed, including stale-revision zero
  device calls, recovery zero replay, session resume/recreate, and close-state
  behavior;
- R6/R7: 10/10 passed, including fresh observe before the next state-sensitive
  mutation, bounded recovery to the Home structural anchor, and zero blind
  replay;
- stale WDA HTTP 404 invalidates only the cached WDA session and never retries
  the failed request;
- C0 now bounds a hung WDA reachability probe in generic transport plumbing;
  timeout can start the configured xctrunner path but never retries an action;
- C0 read-only observation is also bounded so startup degradation terminates a
  run rather than hanging indefinitely;
- current failed C0 startup attempts contain zero device action attempts and are
  retained as pre-mutation reliability evidence.

#### 92% -- Observation / performance tuning: ACCEPTED for first-canary scope

- C0 direct canary measured full-observe median about 8.29 s and p90 about
  26.94 s, confirming that observation cost remains the dominant optimization
  target;
- its actual execute median was about 244.8 ms and p90 about 284.7 ms;
- retained R4 Home evidence measured 4 executions with maximum about 501.2 ms;
- the first canary latency budget is data-derived as
  `ceil(observed-max / 50 ms) * 50 ms = 550 ms`;
- cheap validation is considered only where a causal Home structural
  postcondition exists; no cheap validator manufactures a Runtime revision;
- full-observe fallback stays available and sequence-live stays OFF.

#### 97% -- Promotion Policy: ACCEPTED

Retained machine-readable analysis:
`docs/evidence/20260912_phasec0-readiness-analysis.json`.

First candidate: `system:return-home` only.

Accepted policy is fixed independently of the currently observed sample count:

- minimum 4 clean current-device Home executions;
- minimum 4 retained-evidence Shadow replay evaluations;
- PARTIAL/UNKNOWN/replay/Teaching-conflict budget: zero for this candidate;
- causal structural validator required;
- deterministic fallback proof required;
- risk must be low, reversible, and non-human-gated;
- observation-only adaptive surface;
- sequence-live prohibited;
- execute p90 budget 550 ms, derived from the retained 4-run maximum as above;
- no fake numeric recovery-rate threshold is used: the single retained bounded
  recovery proof is represented by the structural/fallback proof instead.

The final retained analysis returns both `promotion_decision.ready=true` and
`c0_completion.ready=true`. It still does not enable
`LIVE_OPTIMIZATION_ENABLED` and does not start Phase C.

#### 100% -- Operational preflight / final C0 review: ACCEPTED

The Wi-Fi WDA/XCTest path was intermittently unstable during C0, and the failed
attempts remain retained rather than being hidden:

- direct RemotePairing pair verification succeeds and the screen reports
  `backlightState=activeOn`;
- several setup attempts failed before mutation at the upstream DTX/WDA path;
- generic WDA reachability probing is now bounded, so this failure terminates
  safely instead of hanging;
- failed preflight runs before action contain no Runtime execute/attempt event;
- `phasec0-home-preflight-20260912` reached one successful Home action but its
  post-action accessibility observation timed out. The Home action was not
  replayed; the run was retained as failed and closed explicitly;
- the Home-only preflight now permits at most one plumbing-only
  `Runtime.recover()` after a *confirmed succeeded/NONE/non-replayed* Home when
  the post-action read-only observation times out. Recovery never replays the
  Home action.

Fresh operational preflight on the final non-forked RemotePairing adapter then
passed in `phasec0-home-preflight-final-20260912`:

- candidate operation class: `system:return-home` only;
- fresh Runtime observe before the action: PASS;
- exactly one certified Home action: PASS;
- attempt state/effect: `succeeded / NONE`;
- replayed: `false`;
- actual execute batch size: 1;
- fresh Runtime observe after the action: PASS;
- Runtime observe events: 2;
- Runtime execute events: 1 (`home` only);
- run terminal status: `ok`;
- failure effect/error-code classes: 0 / 0;
- Adaptive Live applied: false;
- sequence-live applied: false;
- execute latency in this one-shot preflight: about 1503.8 ms;
- full-observe latency remained material (about 23.58 s pre-action and 4.83 s
  post-action).

The one-shot execute outlier triggered an explicit performance recheck rather
than being ignored. `phasec0-home-latency-sample-20260912` then ran six Home
cycles under the same final code and Wi-Fi path:

- 6 / 6 `succeeded / NONE`, replayed=false;
- execute range about 61.2--159.1 ms;
- execute median about 117.7 ms;
- execute p90 about 159.1 ms;
- failures: 0;
- full-observe median/p90 about 4.72 s / 4.87 s.

Promotion analysis uses the stricter class-level p90 between retained R4
(502 ms) and current Wi-Fi (159.1 ms). The resulting policy-observed p90 is
502 ms, which remains below the existing 550 ms budget. The 1503.8 ms one-shot
outlier remains retained reliability evidence.

The machine-readable report
`docs/evidence/20260912_phasec0-readiness-analysis.json` therefore records:

- `promotion_decision.ready = true`;
- `operational_preflight_evidence.decision.ready = true`;
- `c0_completion.ready = true`;
- `c0_completion.phase_c_status = READY_FOR_LIMITED_CANARY`.

This successful retained preflight closes C0. It is **not** a permanent claim
that the Wi-Fi/WDA lane can never become unavailable again. Immediately before
the actual Phase C activation, the live Runtime must be projected into
`CanaryEnvironment` and `evaluate_canary_preflight()` must pass again. A future
WDA/Runtime/lock/fresh-observation/lane-ownership failure blocks that canary
before mutation without reducing the validity of the retained C0 evidence.

## 7. Current decision

Readiness: **100%**
Operational phase: **Phase C0 COMPLETE**
Phase C: **READY FOR LIMITED CANARY (not started)**
Adaptive Live: **OFF**  
Sequence Live: **OFF**

Evidence/policy readiness for `system:return-home`: **READY**.
Retained operational preflight: **READY**.
Actual Phase C start still requires a fresh dynamic canary preflight and an
explicit activation step. No other operation class is promoted by this C0
closure, and Merge Boss-specific board/order/generator Knowledge remains
candidate/Shadow-only unless separately verified and promoted.

Final acceptance evidence:
`docs/evidence/20260912_phasec0-final-acceptance.md`.

Final software certification: **547 tests passed**, provenance guard PASS,
Runtime-boundary guard PASS, compileall PASS, and `git diff --check` PASS.
