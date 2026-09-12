# R6+R7 Safe Agent Foundation — Combined Acceptance — 75/75 + device gate PASS

- Date: 2026-09-05 · Sensitivity: PUBLIC
- Combined: R6 44/44 + R7 31/31 = **75/75 accepted (deterministic)**
- Current suite after formal-resume refinements: **194/194 PASS**;
  provenance PASS; architecture-boundary PASS + fail-closed regression PASS.
- Reviews: independent R6 PASS, independent R7 PASS, combined adversarial
  review PASS (no hidden bypass, stale-revision, replay, lease/cancel race,
  unsafe loop, lifecycle corruption, semantic authority leak, validator
  false-green, privacy leak, historical-product regression, domain leak, R8+
  scope — none found).
- Device gate: one USB iPhone recognized; refreshed signed WDA runner installed
  and trusted; bounded single-lane hardware matrix **10/10 PASS** (see
  `20260905_r6-r7-safe-agent-foundation-device-matrix.json`). Runtime-only
  mutation, revision invalidation, fresh-observe sequencing, durable Attempt
  linkage, bounded recovery, cancel/deadline guards, zero blind replay, and
  shutdown ownership release all passed on real hardware.
- R8+ not started; no push performed.
