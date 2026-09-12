# Praxiom — Current Program Status

Updated: 2026-09-12

## Critical path

```text
R1 upstream audit / pin gate            COMPLETE / retained authority
R2 Native iOS Runtime contract          COMPLETE / retained authority
R3 Native iOS Runtime v0                33/33 COMPLETE
R4 real-device acceptance               20/20 PASS
R5 separation / provenance closure       7/7 PASS
R6 Agent Foundation                     44/44 ACCEPTED
R7 Retrieval + Post-Action Safety       31/31 ACCEPTED
R8 Capability Discovery / Skill Foundry 47/47 ACCEPTED
R9 Adaptive Execution Performance       47/47 ACCEPTED
                                        ----------------
R8+R9 Adaptive Skill Platform           94/94 CERTIFIED
                                        ↓
R10 Domain Migration & Final Acceptance 35/35 CERTIFIED
                                        (post-review Goal Certification complete)
                                        ↓
Post-R10 Phase A                        COMPLETE
Post-R10 Phase B                        COMPLETE
Phase C0 / Phase C Readiness            100% COMPLETE
                                        ↓
Phase C Limited Adaptive Live           ACTIVE / bounded canaries only
```

Separate track:

```text
Visual Flight Recorder V0–V3            29 points — independent read-only track
```

Visual work is not a prerequisite for R10 and must not gain device-mutation authority.

## Current Phase C boundary

Accepted operation-class canaries in the 2026-09-12 development snapshot:

- `system:return-home`
- `system:launch-application`
- `mergeboss:open-level-board`

The Merge Boss board-entry canary uses current-device visual evidence and a
fresh post-action board check. The accepted scope does not include generator
production, merge execution, order delivery, or unrestricted autonomous
gameplay. Action batching remains one operation at a time and Sequence Live is
off.

Latest retained deterministic suite at this snapshot: **600/600 PASS**, with
Runtime-boundary guard, provenance guard, compile check, and diff check green.
The canonical current Phase C summary is `docs/evidence/PHASE_C_PROGRESS.md`.

## Latest certified adaptive-platform state

- R8: 47/47 ACCEPTED
- R9: 47/47 ACCEPTED
- Combined: 94/94 CERTIFIED
- Independent final review: APPROVED
- Goal Reviewer: GOAL_PASS
- Final Judge: PASS
- unresolved: []
- errors: []
- last retained deterministic suite at R8/R9 close: 306/306 PASS
- latest retained R8/R9 software checkpoint: `25d59d7d832b430556e56141198e03e8afd77c62`
- docs successor at prior Goal close: `2a632d98e4a2887cb3aeebcd5cf43528a37bf5e9`

A new Goal must fresh-verify current HEAD rather than assuming these hashes remain current.

## Current architectural invariants

- Native iOS Runtime public surface remains six operations: `status`, `observe`, `execute`, `invalidate`, `recover`, `close`.
- Device mutation above Runtime is mediated through Coordinator and revision-bound execution.
- Phone Harness remains historical/reference only, never production/build/runtime dependency or fallback.
- No internal MCP device chain.
- No direct WDA/CoreDevice/AppService/usbmux/pymobiledevice3 dependency above Runtime.
- No blind replay after unknown/partial effect.
- No state-sensitive mutation from stale revision.
- Skill/adaptive confidence/performance never outranks lifecycle/safety/revision/human-gate authority.
- No remote push unless explicitly requested.

## R10 Domain Migration & Final Acceptance status

- R10-A (Domain adapter seam and authority isolation): 7/7 ACCEPTED
- R10-B (Merge Boss migration): 6/6 ACCEPTED; 5 evidence-supported runnable behaviors, unsupported purchase/cooldown contracts deferred
- R10-C (GoGoMatch migration): 6/6 ACCEPTED; 2 evidence-supported runnable behaviors (`launch-game`, `swap-tiles`), unsupported level/booster/reward/purchase contracts deferred
- R10-D (Compatibility, provenance, and migration closure): 4/4 ACCEPTED
- R10-E (Bounded real-workflow evidence): 5/5 PASS on 2026-09-09 (single attached iPhone; sequential Merge Boss -> GoGoMatch bounded live run passed with fresh revision observation, `effect=NONE`, no replay, postcondition checks green, and Runtime closed cleanly)
- R10-F (Full regression, safety, and performance gates): 4/4 ACCEPTED; F4 corrected by `docs/evidence/20260909_r10-independent-review-repair.md` using the authoritative R9 deterministic baseline and unchanged R9 safe path
- R10-G (R10 acceptance package and program closure): 3/3 ACCEPTED
- Final post-review acceptance / certification score: 35/35 CERTIFIED
- Full deterministic suite on the live-evidence source HEAD: 359 passed (guards green)
- Boundary guard: PASS (generic core domain-neutral; domain adapter seam isolated)
- Provenance guard: PASS (zero Phone Harness; upstream pin intact)
- Six-operation Runtime surface: INTACT (`status`, `observe`, `execute`, `invalidate`, `recover`, `close`)
- Domain-specific review (R10-G2): APPROVED after 4 finding repairs
- Acceptance package: `docs/evidence/20260908_r10-acceptance.md`
- Fresh final verification: `docs/evidence/20260909_r10-final-verification.md` (current HEAD-bound: 359/359 + boundary/provenance/compile/diff checks PASS)
- Design freeze: `docs/evidence/r10-design-freeze.md`
- R10 live blocker: RESOLVED on 2026-09-09 (`device_count=1`); privacy-safe closure is appended to `docs/evidence/20260908_r10-bounded-real-workflow.md`
- Prior runtime-owned Goal Reviewer / Final Judge: completed on pre-review HEAD `6a4bf06` (`run-e90f257e-6c9c-4ed8-bdf6-6f1d6df758eb`: approved / pass); retained as historical certification provenance only after the independent-review repair
- Current post-review Goal Certification: **CERTIFIED** on source HEAD `ea3a03e3f502d4ae423f65ae46bfe744c4e917b1` by durable Run `run-a762ab46-75db-44f1-b7d3-c8c16857d696`; Goal Reviewer `approved`, `findings=[]`, `blockers=[]`; Final Judge `PASS`, `unresolved=[]`; final artifact `points=35`, `certified=true`
- Independent-review repair authority: `docs/evidence/20260909_r10-independent-review-repair.md`
- Domain per-behavior provenance authority: `docs/evidence/20260909_r10-domain-provenance-repair.md`

Authoritative orchestration materials:

- `docs/design/20260908_r10_domain-migration-final-acceptance_orchestrator_handoff.md`
- `docs/design/20260908_r10_domain-migration-final-acceptance_orchestrator_prompt.md`
- `docs/design/20260907_r8plus_execution_plan.md`

## Canonical completion evidence by era

- R3: `docs/evidence/20260901_r3-native-ios-runtime-v0-completion.md` + `20260903_r3-08-attached-device-pass.md`
- R4/R5: `docs/evidence/20260905_r4-r5-final-completion.md`
- R6/R7: `docs/evidence/20260907_r6-r7_current-head_software-certification.md`
- R8/R9: `docs/evidence/20260907_adaptive-skill-platform-certification-packet.md`
- R10: `docs/evidence/20260908_r10-acceptance.md` + `docs/evidence/20260908_r10-bounded-real-workflow.md`
- provenance/upstream pin: `docs/PROVENANCE.md`

Historical completion documents preserve the state that was true when they were written; their statements such as “R6 not started” must not be rewritten merely because later milestones are now complete.

