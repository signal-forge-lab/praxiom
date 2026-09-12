# Praxiom Post-R10 Phase A — Design Freeze

Date: 2026-09-09

Status: **FROZEN / IMPLEMENTATION AUTHORITY**

Sensitivity: **PUBLIC**

## Scope

This freeze authorizes the pre-real-device Phase A work for the post-R10 learning/telemetry loop. It does not reopen certified R0-R10 authority and does not start Visual Flight Recorder V0-V3 implementation itself.

Authoritative design documents:

- `docs/design/20260909_post-r10-phase-a_closed-loop-telemetry_design-decisions.md`
- `docs/design/20260909_post-r10-phase-a_closed-loop-telemetry_orchestrator_handoff.md`
- `docs/design/20260909_post-r10-phase-a_closed-loop-telemetry_orchestrator_prompt.md`

## Frozen decisions

The user approved all recommended options on 2026-09-09:

1. **D1=A — durable telemetry:** append-only per-run JSONL journal.
2. **D2=A — activation:** shadow-first adaptive/learning recommendations; live control remains feature-gated until real-device baseline evidence supports promotion.
3. **D3=A — bounded sequence execution:** add an explicit internal sequence path (`run_sequence` / `execute_sequence` or equivalent final names) rather than changing the semantics of the existing certified single-action path.
4. **D4=A — Visual Flight Recorder compatibility:** Phase A adds only correlation/timestamp/artifact-reference hooks. V0-V3 remain a separate read-only track and receive no device-mutation authority.
5. **D5=A — Wi-Fi Runtime:** add an in-process RemotePairing/userspace RSD path so a Wi-Fi-only paired device can reach the existing Runtime/WDA stack without reintroducing external `tunneld` as a production dependency.

## Non-negotiable authority constraints

- Native iOS Runtime public surface remains exactly: `status`, `observe`, `execute`, `invalidate`, `recover`, `close`.
- No Phone Harness production/build/runtime dependency or fallback.
- No second device-mutation authority.
- No stale-revision mutation and no blind replay after PARTIAL/UNKNOWN effect.
- Learning/adaptive logic must not outrank lifecycle, revision, risk, reversibility, human-gate, validation, or safety floors.
- Visual hooks are read-only references/correlation only; Phase A does not implement recorder capture pipelines.
- No remote push unless separately authorized.

## Wi-Fi finding carried into Phase A

Current host observation on 2026-09-09:

- usbmux-visible devices: 0;
- the paired iPhone is visible over Bonjour/Remote Pairing on Wi-Fi;
- current Praxiom `IosTransport` is usbmux-gated before opening `PreferredRsdTunnel`;
- the current upstream/pinned userspace tunnel path also attempts usbmux first, so Wi-Fi-only Runtime establishment fails despite successful discovery.

Therefore Phase A must treat this as a Runtime transport/discovery defect, not as evidence that Wi-Fi pairing itself is absent. D5=A is the frozen repair direction.

## Visual Flight Recorder forward-compatibility contract

Phase A telemetry/event records must be able to correlate future visual evidence without embedding media payloads. The design should retain stable identifiers/timestamps sufficient for later V0-V3 to attach:

- rolling low-FPS video references;
- pre/post-action frame references;
- short clips around large animation/frame-diff windows;
- representative multi-frame sets;
- AI retrieval references for selected visual artifacts.

Media remains external to the telemetry journal and is referenced by artifact identifiers/metadata only.

## Implementation gate

The design-choice gate is satisfied. The orchestrator may proceed with current-state audit, design conformance checks, implementation, deterministic tests, full regression, review/repair, and Phase A acceptance.

If current repository evidence proves a frozen choice unsafe or technically impossible, the run must stop with the concrete conflict and return to the user for a new design decision. It must not silently choose another option.
