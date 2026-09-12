# Praxiom Phase C Progress

Status: **ACTIVE — Canary 1 ACCEPTED / expansion review**

Phase C0 is accepted at 100%. Phase C starts with exactly one accepted
operation class and does not imply broad Adaptive Live enablement.

## Canary 1 scope

- operation class: `system:return-home`;
- adaptive surface: observation-only;
- allowed live change: immediate post-Home `full-observe` may be replaced by
  an accepted causal cheap validator;
- the cheap validator never creates a Runtime revision;
- every later mutation still requires a fresh full Runtime observation;
- mutation remains Skill -> Coordinator -> Runtime only;
- sequence-live: OFF;
- action batching/reduction: prohibited;
- Human Gate bypass: prohibited;
- failure/ambiguity: full-observe fallback or pre-mutation refusal;
- action retry/replay: prohibited.

## Acceptance path

1. deterministic runner/gate/fallback tests;
2. dynamic live environment preflight;
3. 1-iteration attached-device canary;
4. small repeated stability canary with full-observe corroboration of every
   cheap validation before any later mutation;
5. latency/failure/replay/fallback review;
6. accept, hold, or roll back Canary 1 before considering another operation
   class.

The global `LIVE_OPTIMIZATION_ENABLED` constant remains false. Phase C uses a
locally enabled `LiveOptimizationGate` only inside this explicitly scoped
canary runner.

For attached-device runs where the normal read-only MCP must be stopped to
preserve one WDA/mutation lane, the canary runner supports
`--monitor-frame-projection`. Its Runtime then publishes fresh screenshots to
the same one-frame Monitor store used by the MCP. This preserves live Monitor
visibility without creating a second device authority or a second WDA owner.

## 2026-09-12 — Canary 1 acceptance

Accepted operation class: `system:return-home`.

Retained live runs:

- `phasec-home-live-canary-20260912a` — 1 iteration;
- `phasec-home-live-stability-20260912a` — 5 iterations.

Combined result:

- 6 / 6 certified Home attempts: `succeeded / NONE`;
- replayed actions: 0;
- action batch size: 1 only;
- sequence-live applications: 0;
- observation-only Live applications: 6 / 6;
- causal cheap validators sufficient: 6 / 6;
- cheap-validator structural icon count: 259 on every sample;
- later/full-observe corroboration: 6 / 6 matched the Home structural anchor;
- full-observe fallbacks: 0;
- failure effect/error-code classes: 0;
- stability-run execute median/p90: about 224.5 / 230.0 ms;
- stability-run full-observe median/p90: about 4.38 / 5.00 s;
- cheap-validator latency range across the six live samples: about
  3.59--3.70 s.

The live decision is retained in the run journal as
`policy_recommendation=cheap-validate`, `actual_policy=cheap-validate-live`,
and `validation.performed` with `observe_mode=cheap_validate`. The final
stability summary reports `cheap_validate=5` plus one explicit final full
audit. The initial one-iteration run predates that extra telemetry event but
retains the same live policy decision and successful full audit.

Decision: **Canary 1 ACCEPTED**. This acceptance is operation-class scoped. It
does not turn on the global live constant and does not authorize any other
behavior.

Machine-readable acceptance summary:
`docs/evidence/20260912_phasec-home-live-canary-acceptance.json`.

## Expansion review

`mergeboss:launch` and `gogomatch:launch-game` remain **HOLD for Adaptive
Live** even though retained current-device success evidence exists. The first
Phase C surface requires a causal cheap postcondition validator; a running
process or historical launch success alone is not sufficient proof that the
requested application is the current foreground state.

Before either launch class can become a Phase C candidate, provide and verify
a generic foreground/application-state causal validator that:

- is read-only;
- does not author a Runtime revision;
- does not depend on Merge Boss or GoGoMatch semantics;
- distinguishes foreground success from merely-running process state;
- fails closed to full observe;
- preserves zero action replay and sequence-live OFF.

The expansion boundary is now stricter than the original domain-launch
shorthand. Phase B/C0 used the same AliExpress application bundle for both
`mergeboss:launch` and `gogomatch:launch-game`. A foreground application match
can therefore prove only the generic OS-level postcondition "the requested
application is foreground"; it cannot prove that a Merge Boss or GoGoMatch
game-specific surface has been reached. Phase C consequently introduces the
generic candidate `system:launch-application` for this validator. The two
domain-specific launch behaviors remain HOLD until their own additional
postconditions are proven by domain evidence.

### Foreground validator probe status

A Domain-specific evidence probe now exists at
`scripts/phasec_foreground_validator_probe.py`. It keeps all application name,
bundle identifier and raw accessibility XML values in-process only; retained
evidence contains structural counts and boolean expected-app matches only.

The first attached-device probe attempt
`phasec-foreground-validator-probe-20260912a` did **not** reach a mutation. It
failed during read-only RemotePairing Bonjour endpoint discovery with
`exactly-one-remote-paired-device-required`, matching the previously observed
intermittent Bonjour visibility issue. No launch or Home action was sent.

The local RemotePairing record was inspected for a safe endpoint fallback. It
contains pairing cryptographic material only and no reusable host/port, so no
address guessing or machine-specific endpoint persistence was introduced.
Retry the probe only when normal RemotePairing discovery is visible again.

The foreground check has now been factored into the generic read-only helper
`praxiom.ios_runtime.foreground`. The shared helper accepts an expected
application identity only in-process and returns bounded structural evidence
(`application_node_count`, boolean match, matched attribute-key names). It
never returns or persists the expected identity, raw XML, bundle identifiers,
screen text, coordinates, or device identifiers. The Merge Boss probe only
supplies its domain-specific expected identity at the integration edge.

The attached-device probe now executes `system:launch-application`, not a
Merge Boss/GoGoMatch behavior. AliExpress is only the current physical test
application supplied to that generic behavior and validator; its identity is
not encoded in the shared system-domain contract.

Successful foreground probes durably persist only
`foreground_validator_report.json` under the run directory. The report keeps
structural counts, boolean expected-app matches, matched attribute-key names,
latency, replay/success state, and bounded run-summary fields. It explicitly
does not persist the expected app identity, bundle identifier, raw XML,
screen text, coordinates, or device identifiers. This durable projection is
the only probe payload eligible for later promotion analysis.

When RemotePairing/device-service discovery is unavailable, the foreground
probe now returns a structured `blocked` result with `mutation_count=0` rather
than raising through the CLI. This availability failure does not revoke the
accepted Home canary and does not grant launch classes any Adaptive Live
authority.

## 2026-09-12 — Canary 2 acceptance

Accepted operation class: `system:launch-application`.

The accepted validator evidence uses the final `activeAppInfo` implementation,
not the earlier accessibility-XML probe. Retained evidence:

- `phasec-foreground-validator-stability-20260912b` — 5 clean validator
  iterations under the final code;
- `phasec-launch-application-live-canary-20260912a` — one Adaptive Live
  application of the observation-only recommendation.

Validator stability result:

- 5 / 5 launch attempts `succeeded / NONE / replayed=false`;
- expected foreground bundle matched 5 / 5;
- foreground PID present 5 / 5;
- independent full-observe corroboration matched 5 / 5;
- Home cleanup succeeded 5 / 5 with structural icon count 259;
- validator fallbacks: 0;
- cheap-validator median/p90: about 1184 / 1210 ms;
- full-observe median/p90 in the same run: about 4811 / 24931 ms;
- offline generic Shadow re-evaluation: 5 / 5 `cheap-validate`, observation
  reduction only, zero action reduction.

Live canary result:

- promotion readiness: READY with 5 current-device success/NONE samples,
  causal validator 5 / 5, Shadow evaluations 5 / 5, replay 0 and deterministic
  fallback proof;
- launch attempt: `succeeded / NONE / replayed=false`;
- cheap validator: sufficient, expected foreground matched, latency about
  1143 ms;
- `live_applied=true` with `actual_policy=cheap-validate-live`;
- later full observe independently corroborated the foreground application;
- Home cleanup: `succeeded / NONE / replayed=false`, Home anchor PASS;
- sequence-live/action reduction: 0;
- fallback/failure classes: 0.

Decision: **Canary 2 ACCEPTED** for the generic system application-launch
operation class and observation-only surface. The global live constant remains
false; this does not authorize Merge Boss or GoGoMatch domain postconditions.

The earlier run `phasec-foreground-validator-stability-20260912a` is excluded
from the acceptance population. All ten device actions in that run completed
cleanly, but the run ended with a terminal probe exception and the operator
reported possible manual device interaction. Its negative/diagnostic evidence
is retained rather than silently treated as a successful sample.

Machine-readable acceptance summary:
`docs/evidence/20260912_phasec-launch-application-live-canary-acceptance.json`.

### Next domain candidate

The next low-risk/reversible domain candidate is
`mergeboss:open-level-board`. It remains **HOLD** until current-device evidence
proves both:

1. a safe semantic target for entering/navigating to the Merge Boss board,
   without guessing coordinates or replaying navigation; and
2. a causal board-state postcondition that distinguishes a real Merge Boss
   board from AliExpress foreground state, promotional/interruption surfaces,
   or another game.

Historical Phone Harness navigation evidence may be used only as candidate
guidance. It cannot mint a current tap target or Phase C authority without
fresh Praxiom observation and validation.

## 2026-09-12 — Canary 3 acceptance

Accepted operation class: `mergeboss:open-level-board`.

The final acceptance does **not** depend on the Phone Harness runtime or its
OCR implementation. Legacy OCR was used only as a one-time migration diagnostic
to localize the otherwise accessibility-invisible `Play` control on a fresh
current-device frame. Praxiom then retained only a compact current-device RGB4
visual descriptor and normalized geometry at the Merge Boss domain probe edge;
the raw screenshot and arbitrary OCR text were discarded.

Final native run:

- `phasec-mergeboss-open-board-native-canary-20260912a`;
- AliExpress launch/foreground setup: clean;
- Account route action: `succeeded / NONE / replayed=false`;
- exact semantic Merge Boss entry action: `succeeded / NONE / replayed=false`;
- current-device Play visual binding: screen size matched, template similarity
  `1.000` against threshold `0.900`;
- Play action: `succeeded / NONE / replayed=false`;
- post-action reconciliation used observation only; the Play action was never
  replayed;
- at 1.5 seconds the board postcondition was not yet established;
- at 4.0 seconds 60 / 63 candidate cells (95.24%) matched the current-device
  7x9 board evidence, with 191 / 252 reference-color sample hits;
- board geometry revalidation: PASS;
- Home cleanup: `succeeded / NONE / replayed=false`, structural Home anchor
  PASS with icon count 259;
- action batch size: 1 only;
- sequence-live applications: 0;
- failure classes: 0.

The earlier HOLD was therefore caused by an insufficient post-action settle
window, not by an ambiguous device effect. Phase C now uses a bounded
1.5s -> 4.0s -> 8.0s observation-only reconciliation window after the single
visual Play action. No action retry is introduced.

The active visual binder is fail-closed and domain-scoped. It requires the
current 1206x2622 screen class plus a fresh visual-template match; screen-size
or template mismatch grants no tap authority. The generic Runtime, Coordinator,
Learning, Adaptive, and Safety layers contain no Merge Boss visual semantics.

Decision: **Canary 3 ACCEPTED** for `mergeboss:open-level-board` on the
current-device/current-layout evidence scope. This does not authorize generator
production, board merges, order delivery, paid-resource actions, or
sequence-live.

Machine-readable acceptance summary:
`docs/evidence/20260912_phasec-mergeboss-open-board-canary-acceptance.json`.
