# Praxiom R4 + R5 — Final live gate

- Date: 2026-09-05 JST
- Sensitivity: **PUBLIC**
- Scope: final R4/R5 certification only; **no R6 work**
- Behavioral code HEAD used for the final live run:
  `2d0e675511b25f084c64debc8082aba025e53088`

This record captures the delegator-owned live gates that the read-only DSH
review agents cannot execute themselves. The final independent reviewer should
verify these committed results and the referenced code/evidence; it does not
need to duplicate device or XMind mutation.

## 1. Deterministic repository gate

Executed from the Praxiom repo venv on the behavioral code HEAD above:

```text
.venv\Scripts\python -m pytest -q
=> 146 passed in 1.02s

.venv\Scripts\python scripts\check_provenance.py
=> OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml).
```

Canonical current test total is therefore **146/146**. Earlier 140+1, 141,
and 143 totals in temporally scoped evidence are historical checkpoints before
later certification-regression tests were added.

## 2. USB device gate and final canonical matrix

Read-only preprobe immediately before the final matrix:

```json
{
  "device_count": 1,
  "pymobiledevice3_version": "11.3.0"
}
```

Final single-device-lane command:

```text
.venv\Scripts\python scripts\r4_device_matrix.py matrix --confirm-device-run --evidence-dir docs\evidence
```

Result:

```json
{
  "aborted": false,
  "failed_steps": [],
  "steps_passed": 29,
  "steps_total": 29
}
```

The current machine evidence is
`docs/evidence/20260905_r4-device-matrix-run4.json`. The repaired R4-04 steps
record:

```text
owned-session-drop-resume:
  dropped-to=DEGRADED/UNAVAILABLE resumed-ready=True

recover-zero-replay:
  stale-before-recover=DEGRADED/UNAVAILABLE
  repaired=True
  replayed-executes=0
  reconciled-ready=True
```

This proves `recover()` itself rebuilt stale owned WDA/session plumbing before
the reconciliation `observe()`. No automatic replay occurred.

The only accepted `environment-not-exercised` cells remain exactly:

1. physical hotplug/unplug;
2. naturally occurring ambiguous in-flight effect;
3. physical disconnect/unavailability.

LOCKDOWN and Wi-Fi are target-scope non-requirements, not unresolved R4 cells.

## 3. Git identity / ancestry gate

All checks returned exit 0 on the behavioral code HEAD:

```text
git merge-base --is-ancestor 3ddf03e HEAD  => R4_ANCESTRY_OK
git merge-base --is-ancestor f4e3da7 HEAD  => R5_ANCESTRY_OK
git merge-base --is-ancestor d2505f2 HEAD  => EOF_REPAIR_ANCESTRY_OK
```

Selected committed blobs on that HEAD:

```text
src/praxiom/ios_runtime/executor.py
  c1c4096887c3bbacf71b0cf8e3d940950983edda
src/praxiom/ios_runtime/runtime.py
  bc3cda70e25a982625355e458d7e9b3d6b022808
src/praxiom/ios_runtime/transport.py
  b809de48aba8732defc2cf32dac75c6113a19da1
docs/evidence/20260905_r4-real-device-acceptance.md
  b2503d105cd903e4f5c0e8043545d762fbdb04f9
docs/evidence/20260905_r5-separation-closure.md
  ec5ef3743099fd22234ac794534a00e84ace64d2
```

## 4. XMind live read gate

The Workboard was re-read immediately before final certification.

Praxiom topic `f142a304-8ceb-4c6b-a279-555792c8f882`:

- title: `Praxiom — Target Architecture`
- labels: `active`, `Praxiom`
- active path note: `praxiom.ios_runtime -> unmodified upstream pymobiledevice3 -> WDA/CoreDevice -> iPhone`
- read operation: `725439dd-9122-4b50-bb58-8f4aaa007f1e`
- `changed=false`, `verified=true`

Phone Harness topic `c3e6b2b5-411d-440e-a8f2-04d3cee51419`:

- title: `Phone Harness — reference only / no dependency`
- labels: `historical`, `superseded`, `reference-only`
- note explicitly says it is not a Praxiom production/build/runtime dependency
  and is not on the active execution path
- read operation: `58519f21-4cde-4694-97ad-5b231c82e784`
- `changed=false`, `verified=true`

The earlier semantic write operation remains
`75389909-8403-454c-8b0a-e58bbe2c2bd0` (`changed=true`, `verified=true`).

The final `R5_COMPLETE` relationship/label is intentionally deferred until the
combined independent certification returns PASS, avoiding a false completion
claim.

## 5. Final gate state

- deterministic suite: **146/146 PASS**
- provenance guard: **PASS**
- final USB matrix: **29/29 PASS**
- stale-plumbing direct recovery: **PASS**
- replay count across recovery: **0**
- Phone Harness production/build/runtime dependency/execution edge: **0**
- XMind active/historical separation state: **verified**
- R6 work: **not started**

The remaining action after this evidence is committed is one read-only combined
R4/R5 independent certification. If it returns PASS, write the final XMind
`R5_COMPLETE` marker and record that operation; otherwise repair only the exact
new blocker and re-review.
