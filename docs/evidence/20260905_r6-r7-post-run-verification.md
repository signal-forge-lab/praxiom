# R6+R7 Post-Run Verification

- Date: 2026-09-05 JST
- Sensitivity: PUBLIC
- Formal Plan-and-Run: `run-ce6fc4bf-3da8-4861-af2a-c4e9df592353`
- Workflow: `praxiom-r6-r7-safe-agent-foundation`

## Formal runtime outcome

The original durable workflow reached terminal process status `completed`, but
its formal outcome is `partial`:

```text
outcome.status = partial
unresolved = ["design-freeze"]
errors = [{ task: "design-freeze", message: "max-tokens" }]
```

The runtime-owned Certification chain nevertheless completed:

```text
goal-reviewer      = needs-repair
goal-repair        = completed
goal-rereviewer    = approved
goal-final-judge   = pass
judge unresolved  = []
```

The repair Agent implemented the R6/R7 deterministic foundation and retained
the 44/44 + 31/31 acceptance evidence. A formal `resume-run` was then executed
as `run-db45a8f8-e020-40fc-86e4-6c3dd0352cf3`. That resume successfully
re-ran the original failed `design-freeze` and foundation phases, but its
`r6-experience-knowledge` task later hit `max-tokens`; its Goal Reviewer was
`approved` with no findings, while the Final Judge correctly refused formal
closure because the resumed workflow itself did not finish cleanly.

## Fresh deterministic verification after terminal run

Executed from the Praxiom repository root after the DSH run terminated:

```text
.venv\Scripts\python -m pytest -q
=> 194 passed

.venv\Scripts\python scripts\check_provenance.py
=> OK: no Phone Harness import/name/dependency in production paths (src/, pyproject.toml).

.venv\Scripts\python scripts\check_agent_boundaries.py
=> OK: agent/knowledge/retrieval respect the Runtime boundary.
```

These checks confirm the current deterministic implementation is green. The
increase to 194 includes the formal resume's shared-contract fixtures and R6
authority/execution refinements. The production Agent boundary remains
unchanged: device mutation still enters only through the six-operation Runtime
port.

## Real-device closure

Fresh probe after reconnecting the iPhone:

```text
.venv\Scripts\python scripts\r6_r7_device_matrix.py preprobe
=> device_count = 1
=> runner_present = true
```

The previously expired free-development runner profile was reprovisioned,
re-signed, reinstalled, and explicitly trusted on-device. Installation
completed successfully and the refreshed signed runner launches normally.

After trust was granted, direct Runtime observation succeeded with both
`screenshot` and `accessibility` sources. The bounded matrix then completed:

```text
device_count = 1
runner_present = true
steps_total = 10
steps_passed = 10
failed_steps = []
result = PASS
```

The matrix used only reversible Home/Settings operations and recorded no raw
screen/user/device payloads. It observed exactly two Runtime executes for the
two intended live mutations and retained `replayed=false` for both attempts.
The physical blocker is closed. The remaining step is formal DSH `resume-run`
from the failed resume snapshot until the same Goal reaches a clean terminal
certification; no new Plan-and-Run is required.

## Scope status

- R6 deterministic acceptance: 44/44 retained.
- R7 deterministic acceptance: 31/31 retained.
- Combined deterministic implementation: 75/75 retained.
- Full pytest: 194/194 PASS.
- Provenance guard: PASS.
- Agent architecture-boundary guard: PASS.
- Hardware matrix: **10/10 PASS** (`device_count=1`, runner present).
- Original formal durable outcome: PARTIAL.
- First formal resume outcome: FAILED due orchestration `max-tokens` in
  `r6-experience-knowledge`; reviewer approved current implementation.
- Remote push: not performed.
- R8+: not started.
