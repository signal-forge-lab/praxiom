# DSH Orchestrator Prompt — Praxiom R8 + R9 Adaptive Skill Platform

Use DSH Plan-and-Run for the existing Praxiom repository.

Read and obey as primary authority:

1. `docs/design/20260907_r8-r9_adaptive-skill-platform_orchestrator_handoff.md`
2. `docs/design/20260907_r8plus_execution_plan.md`
3. current source/tests and the latest retained R6/R7 certification evidence

Goal: design, implement, test, review, repair, re-review, and formally certify
Praxiom R8 Capability Discovery / Skill Foundry (47) + R9 Adaptive Execution
Performance (47) as one internally gated **Adaptive Skill Platform (94)** Goal.

Do not merely create a plan. Carry the Goal through implementation and final
certification unless a genuine external/physical/credential blocker prevents it.

Required constraints:

- first prove current committed R6/R7 baseline is formally green;
- one design owner freezes shared contracts before parallel production edits;
- R8 independently accepted before R9 production optimization authority;
- preserve the six-operation Native iOS Runtime boundary;
- Agent/Skill/Retrieval code cannot directly use pymobiledevice3, WDA,
  CoreDevice, AppService, usbmux, Phone Harness, subprocess/MCP device bridges;
- generated/procedural code is untrusted and sandboxed until Skill Gates pass;
- no blind replay after PARTIAL/UNKNOWN/unrecognized effect;
- no stale-revision state-sensitive mutation;
- performance optimization always falls back to the R7-safe baseline;
- no R10 domain migration and no Visual V0–V3 implementation in this Goal;
- no remote push.

Use bounded parallel lanes after design freeze, independent non-author reviews,
repair/retest/re-review loops, runtime-owned Goal Reviewer, and runtime-owned
Final Judge. Retain machine-readable evidence and a human-readable completion
record. Completion requires R8 47/47 + R9 47/47 = 94/94, all tests/guards green,
`unresolved=[]`, `errors=[]`, Reviewer approved, Final Judge PASS.

