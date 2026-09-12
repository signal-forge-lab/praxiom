# Praxiom R4 + R5 — Final completion

- Date: 2026-09-05 JST
- Sensitivity: **PUBLIC**
- Scope: R4 + R5 only; **R6 not started**

## 1. Final certification verdict

Final independent combined certification:

```text
run-69fb4ebb-a06a-427a-a530-05b6de142a74
workflow: adversarial-verification
candidate: completed
verifier: completed
synthesis: completed
verdict: PASS
```

The synthesis found no blocking correctness, architecture, safety, privacy,
provenance, evidence, Phone Harness separation, or R6 finding. Two
non-blocking documentation nits were subsequently corrected in commit
`2cdb797` and the deterministic/provenance gates remained green.

## 2. Final live gates

Canonical live-gate record:

`docs/evidence/20260905_r4-r5-final-live-gate.md`

Final results:

- deterministic suite: **146/146 PASS**;
- provenance guard: **PASS**;
- USB preprobe: `device_count=1`, `pymobiledevice3 11.3.0`;
- final canonical real-device matrix: **29/29 PASS**;
- `aborted=false`, `failed_steps=[]`, exit 0;
- direct stale-plumbing recovery:
  `DEGRADED/UNAVAILABLE -> recover() -> READY`;
- `replayed-executes=0`;
- exactly three honest `environment-not-exercised` cells remain:
  hotplug, naturally occurring ambiguity, physical disconnect;
- LOCKDOWN and Wi-Fi: target-scope non-requirements;
- Phone Harness production/build/runtime dependency/execution edge: **0**.

## 3. Certification repair commits

Relevant repair/closure sequence:

```text
0cd1c81  fix: address R4 R5 certification blockers
08e3f49  docs: align R4 repair behavior descriptions
d2505f2  fix: classify upstream WDA EOF ambiguity
971a696  R4 R5: close certification repair evidence
2d0e675  docs: close final certification evidence nits
ed0206c  R4 R5: record final live certification gates
2cdb797  docs: resolve final certification nits
```

Earlier accepted R4/R5 checkpoints remain in ancestry, including
`3ddf03e` (R4 acceptance) and `f4e3da7` (R5 XMind separation gate).

## 4. XMind final closure

Before final certification, live Workboard reads re-verified:

- Praxiom topic `f142a304-8ceb-4c6b-a279-555792c8f882`:
  labels `active`, `Praxiom`; active path is
  `praxiom.ios_runtime -> unmodified upstream pymobiledevice3 -> WDA/CoreDevice -> iPhone`;
- Phone Harness topic `c3e6b2b5-411d-440e-a8f2-04d3cee51419`:
  labels `historical`, `superseded`, `reference-only`; not on the active
  production/build/runtime path.

After the independent final certification returned PASS, the planned final
migration relationship was written:

```text
title: R5_COMPLETE · superseded by Praxiom · 2026-09-05
source: Phone Harness topic c3e6b2b5-411d-440e-a8f2-04d3cee51419
target: Praxiom topic f142a304-8ceb-4c6b-a279-555792c8f882
operation_id: 117ec2b8-c32a-48df-b95f-29224bb7bc2c
relationship_id: 2b014c82-a51c-4876-a0aa-bd74625de0e9
changed=true
verified=true
verification_scope=semantic
```

This satisfies the intentionally deferred `R5_COMPLETE` marker without
claiming completion before certification.

## 5. Final status

- **R4: 20/20 PASS**
- **R5: 7/7 PASS**
- **Combined R4/R5: COMPLETE**
- Final independent certification: **PASS**
- XMind migration marker: **R5_COMPLETE verified**
- Remote push: **not performed**
- R6+: **not started**

