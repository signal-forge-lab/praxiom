# R6/R7 current-head final certification — 2026-09-07

## Scope

This record captures the completed R6/R7 certification package after the final
post-repair physical rerun and current-head Formal review.

- certification HEAD: `a3a7da027b61d94b2f2c376c4cc0c9cd20a337c6`
- physical-tested code HEAD: `c22bf0f8e964c5ed481fff990a4336e5cb475730`
- R6 points: 44
- R7 points: 31
- total: 75
- Runtime operations: `status`, `observe`, `execute`, `invalidate`, `recover`, `close`
- push performed: none
- R8+ work included in this certification: none

The certification HEAD is a docs-only successor of the physical-tested code
HEAD. Parent verification proved that the physical-tested HEAD is an ancestor of
the certification HEAD and that there are no changes under `src`, `tests`,
`scripts`, or `pyproject.toml` between those two revisions.

## Parent-observed verification

Fresh current-head verification at `a3a7da027b61d94b2f2c376c4cc0c9cd20a337c6`:

- full pytest suite: **211 passed**
- provenance guard: **PASS**
- Agent/Runtime boundary guard: **PASS**
- `git diff --check`: **PASS**
- working tree before/after: clean
- HEAD before/after: unchanged
- physical-source ancestry: **PASS**
- code diff since physical-tested HEAD: **none** for `src`, `tests`, `scripts`, and `pyproject.toml`

## Final real-device rerun

Authoritative fresh evidence:
`docs/evidence/20260907_r6-r7-safe-agent-foundation-device-matrix-post-repair.json`

The bounded single-lane Safe Agent Foundation matrix was rerun after the final
Home-transport repair with exactly one attached iPhone and the signed runner
present.

Result:

- `result = PASS`
- `device_count = 1`
- `runner_present = true`
- `steps_total = 10`
- `steps_passed = 10`
- `failed_steps = []`
- every matrix step: `ok = true`
- evidence source tree: clean
- zero blind replay preserved
- Home/Settings-only safety lane preserved
- observed Home structural anchor: **PASS**

The evidence stores the tested Git revision as two privacy-safe 20-hex parts;
concatenating them yields
`c22bf0f8e964c5ed481fff990a4336e5cb475730`.

### Final Home transport repair

The first connected post-repair matrix run exposed a real-device-only failure:
`press_button("home", session_id=...)` could return success while leaving the
foreground app unchanged. Upstream `pymobiledevice3` routes
`press_button("home")` without a session id through `/wda/homescreen`, which is
the reliable Home transition for the current device/iOS path.

Praxiom therefore changed only the Home primitive to the global upstream Home
endpoint while leaving all other session-required WDA primitives pinned to the
owned session. The focused transport tests and full suite remained green, and
the next real-device matrix passed 10/10.

## Formal workflow result

Saved workflow:
`praxiom-r6-r7-current-head-certification`

Durable current-head run:
`run-eadcae9f-868a-454a-8636-b4f3f82592ae`

The workflow was read-only, serialized (`maxConcurrency = 1`), and performed no
repository mutation, phone operation, push, or R8+ work. Parent command output
was supplied as validated evidence; child agents independently inspected source,
tests, architecture, and retained evidence.

The workflow's internal certification package completed all phases:

1. parent verification — **completed**
2. independent software / fresh-physical / architecture audits — **completed**
3. evidence synthesis — **completed**
4. independent Goal Reviewer — **completed**
5. independent Final Judge — **completed**
6. retained evidence — **completed**

Retained artifact result:

- `status = certification-run-completed`
- `verdict = CERTIFIED`
- `judgment = PASS`
- `pytestPassedCount = 211`
- blockers: `[]`
- errors: `[]`
- fresh physical evidence accepted: **true**
- physical source binding accepted: **true**

Independent Goal Reviewer:

- verdict: **approved**
- certification recommendation: **CERTIFIED**
- blockers: `[]`
- errors: `[]`

Independent Final Judge:

- judgment: **PASS**
- verdict: **CERTIFIED**
- software criteria passed: **true**
- fresh physical evidence accepted: **true**
- source binding accepted: **true**
- blockers: `[]`
- errors: `[]`
- push performed: **false**

## Verified R6/R7 repair classes

The completed package independently verified the prior deep-review fixes and the
final real-device Home correction:

1. fail-closed Execution/Attempt ID collision handling without destructive
   history overwrite;
2. stale-first batch termination before later mutation, compensation, retry, or
   replay;
3. Runtime-boundary bypass resistance for callable aliases, dynamic imports,
   `getattr`, call-expression receivers, subprocess/MCP paths, suspicious Runtime
   receivers, and Coordinator revision enforcement;
4. privacy-safe observed post-Home structural anchor validation;
5. reliable current-iOS Home transition through upstream `/wda/homescreen`.

## Architecture and scope result

The final package preserved all frozen R6/R7 boundaries:

- R6 = 44, R7 = 31, total = 75;
- exactly six Runtime operations: `status`, `observe`, `execute`, `invalidate`,
  `recover`, `close`;
- no Phone Harness/domain edge in production paths;
- semantic retrieval remains production-disabled and non-authoritative;
- lifecycle/revision rules remain authoritative over ranking;
- no R8+ implementation was included in R6/R7 certification;
- no push requirement was introduced.

## Completion status

**R6/R7 certification: COMPLETE / CERTIFIED / PASS.**

The prior physical blocker is closed by the fresh post-repair 10/10 matrix. The
prior documentation gap is closed by this record. Any later docs-only successor
HEAD must preserve the source-binding facts above; any later code change must be
verified under its applicable acceptance rules rather than inheriting this
certification automatically.
