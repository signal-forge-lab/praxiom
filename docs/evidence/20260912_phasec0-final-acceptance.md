# Praxiom Phase C0 Final Acceptance — 2026-09-12

Decision: **ACCEPTED / 100% / READY FOR PHASE C LIMITED CANARY**

This acceptance closes Phase C0 only. It does **not** start Phase C, enable
Adaptive Live, or enable sequence-live.

## Accepted first Phase C candidate

- operation class: `system:return-home`;
- adaptive surface: `observation-only`;
- risk: low;
- reversibility: reversible;
- human gate: false;
- sequence-live: prohibited;
- global live optimization: still OFF.

The candidate is generic system navigation. No Merge Boss-specific board,
generator, order, item-family, energy, or UI semantic is promoted by this
acceptance.

## Retained real-device proof

Final operational preflight run:
`phasec0-home-preflight-final-20260912`.

Observed result:

- fresh pre-action Runtime observation: PASS;
- exactly one certified `home` action: PASS;
- attempt state/effect: `succeeded / NONE`;
- replayed: `false`;
- actual execute batch size: 1;
- fresh post-action Runtime observation: PASS;
- Runtime observe events: 2;
- Runtime execute events: 1 (`home` only);
- terminal status: `ok`;
- failure effect/error-code classes: 0 / 0;
- Adaptive Live applied: false;
- sequence-live applied: false;
- execute latency in this one-shot preflight: approximately 1503.8 ms;
- pre/post full-observe latency: approximately 23.58 s / 4.83 s.

The one-shot execute value above is retained as an outlier rather than hidden.
To avoid setting or rejecting a class-level p90 budget from one sample, the
same final code then ran `phasec0-home-latency-sample-20260912` in one WDA
session:

- 6 / 6 Home attempts `succeeded / NONE`;
- replayed: false for all six;
- failures: 0;
- execute range: approximately 61.2--159.1 ms;
- execute median: approximately 117.7 ms;
- execute p90: approximately 159.1 ms;
- full-observe median/p90: approximately 4.72 s / 4.87 s.

The promotion analysis takes the stricter class-level p90 between retained R4
(502 ms) and the current Wi-Fi six-run sample (159.1 ms), so the policy-observed
p90 remains 502 ms and stays below the accepted 550 ms budget. The 1503.8 ms
single-run outlier remains reliability evidence and is not used to lower or
erase the class-level threshold.

Earlier failed C0 startup/read attempts remain retained as negative reliability
evidence. In particular, `phasec0-home-preflight-20260912` successfully executed
Home once but failed its post-action accessibility observation. The action was
not replayed. C0 subsequently added a bounded, plumbing-only `Runtime.recover()`
option after a confirmed successful/non-replayed action; it may retry only the
read-only observation, never the action.

## Evidence and policy proof

Machine-readable authority:
`docs/evidence/20260912_phasec0-readiness-analysis.json`.

Final analysis records:

- `promotion_decision.ready = true`;
- `operational_preflight_evidence.decision.ready = true`;
- `c0_completion.ready = true`;
- `c0_completion.phase_c_status = READY_FOR_LIMITED_CANARY`.

Retained supporting device evidence includes R4 29/29 PASS, R6/R7 10/10 PASS,
four retained Home executions, a causal Home structural postcondition,
zero-blind-replay proof, deterministic fallback proof, and four stable
retained-evidence Shadow evaluations.

## Legacy / Teaching / Learning closure

Legacy Phone Harness material remains seed evidence only. The final bootstrap
contains 137 authority-free candidates, all still requiring current-device
corroboration; none inherit legacy trust or live authority.

Generic Human Teaching now preserves `answered != learned`, policy/fact/other,
conflict review, provenance and fact promotion through the normal Knowledge
lifecycle. Only already-learned Teaching can constrain Shadow behavior.

Learning Cycle v1 records fresh pre-observation, exactly one caller-certified
action, fresh post-observation/validation, negative evidence, Teaching/bootstrap
links and Shadow state. It contains no mutation retry/replay path.

## Final software certification

Final verification on the accepted tree:

- deterministic/full test suite: **547 passed**;
- provenance guard: **PASS**;
- Agent/Knowledge/Retrieval/Skill/Adaptive -> Runtime boundary guard: **PASS**;
- `compileall`: **PASS**;
- `git diff --check`: **PASS**.

The boundary guard explicitly caught and rejected an intermediate attempt to
place WDA-specific terminology inside the generic Adaptive layer. The final
implementation uses domain-neutral `CanaryEnvironment` fields such as
`device_channel_ready` and retains device-specific details below the Runtime
boundary.

The RemotePairing XCTest compatibility seam also calls the pinned upstream
`XCUITestService.run()` directly rather than carrying a copied/forked run body;
only the empirically required provider capability exchange is scoped off for
the RemotePairing marker and restored in `finally`.

## Phase C entry condition

Phase C has not started. Immediately before the real Limited Canary activation,
the current live environment must be projected into `CanaryEnvironment` and
`evaluate_canary_preflight()` must pass again. Runtime/device-channel/fresh-
observation/lane-ownership/lock/environment failures block activation before
mutation. A transient future availability failure does not erase this retained
C0 acceptance, but it prevents the canary from starting until the live
preflight passes.

