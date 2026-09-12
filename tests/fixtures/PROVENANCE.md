# Fixture provenance — native-ios-runtime-v0.json

- **Source (read-only authority document):**
  `<legacy-reference-root>\docs\design\fixtures\native-ios-runtime-v0.json`
- **Copied to:** `tests/fixtures/native-ios-runtime-v0.json` — verbatim byte-for-byte
  copy of the fixture artifact (JSON only; no Phone Harness source, test utility,
  or other file was copied or referenced).
- **Goal:** `goal-adaptive-agent-r3-greenfield-native-ios-runtime-v0-20260901`
  (slice R3-07 — contract fixture runner).
- **Copied date:** 2026-09-01.
- **Normative role:** `tests/test_acceptance.py` loads this copy and drives the
  deterministic acceptance tests for scenarios R2-A01 through R2-A10 against the
  real public runtime with a fake transport. Scenario R2-A11 (attached physical
  iPhone) is out of scope for the no-device suite; it belongs to the separate
  attached-device smoke (R3-08).
- The original under the Phone Harness tree remains the read-only authority;
  this copy exists only so the new repo is self-contained.
