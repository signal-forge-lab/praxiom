# R10 domain migration provenance repair — 2026-09-09

## Purpose

This record closes the independent-review finding that the original R10 domain
modules cited roadmap/freeze documents as if those documents were per-behavior
domain evidence. R10's frozen rule is stricter: only behavior supported by
accepted current or historical evidence may become a runnable migrated domain
contract.

This is an evidence correction, not a Phone Harness source migration. Historical
Phone Harness material remains read-only/reference-only and is not a Praxiom
runtime/build dependency.

## Merge Boss accepted runnable set

| Praxiom behavior | Decision | Direct evidence |
|---|---|---|
| `mergeboss:launch` | migrated | Current Praxiom physical live evidence: `docs/evidence/20260908_r10-bounded-real-workflow.md` records the successful revision-bound Merge Boss `launch_app` lane. |
| `mergeboss:open-level-board` | migrated | Historical Phone Harness `docs/game-operations/aliexpress-merge-boss/playbook.md` §2A records goal-directed recovery to fresh Merge Boss board truth. |
| `mergeboss:spawn-generator-item` | migrated | Historical playbook §6 plus `knowledge.mbk` producer records and `evidence/20260901-live-play-energy-loop.md` record select/activate producer output and energy/capacity effects. |
| `mergeboss:merge-board-items` | migrated | Historical playbook §5 and `knowledge.mbk` merge records establish same-identity/level merge semantics; `evidence/20260901-live-play-energy-loop.md` contains live verified merge chains. |
| `mergeboss:deliver-customer-order` | migrated | Historical playbook §§4/7 and `knowledge.mbk` `order.complete` / end-to-end target-order evidence establish order completion and consumption semantics. |

Historical source root for the three referenced Merge Boss artifacts:

```text
<legacy-reference-root>\docs\game-operations\aliexpress-merge-boss\
```

The prior `purchase-generator-part` and `speedup-generator-cooldown` records are
now `deferred`: retained evidence does not establish those contracts. The
historical playbook instead explicitly keeps paid cash/diamond and purchase
paths outside normal autonomous play.

## GoGoMatch accepted runnable set

| Praxiom behavior | Decision | Direct evidence |
|---|---|---|
| `gogomatch:launch-game` | migrated | Current Praxiom physical live evidence: `docs/evidence/20260908_r10-bounded-real-workflow.md` records the successful revision-bound GoGoMatch `launch_app` lane. |
| `gogomatch:swap-tiles` | migrated | Historical Phone Harness `docs/game-operations/gogomatch/20260831-level-3193-learning.md` records that a move is an adjacent swap that must create a match and records the observed match-style board. |

Historical GoGoMatch source root:

```text
<legacy-reference-root>\docs\game-operations\gogomatch\
```

The following contracts are deliberately `deferred`, not runnable migrated
behaviors:

- `select_level`: the retained run does not establish the level-selection flow.
- `start_level`: the retained evidence begins after level entry and does not
  establish start/stamina semantics.
- `use_booster`: the historical evidence explicitly says no booster was
  intentionally selected.
- `claim_rewards`: the historical level was not cleared, so victory reward
  claim semantics were not observed.
- `buy_extra_moves`: a paid/resource-consuming continuation offer was observed,
  but no purchase was executed; transaction/postcondition semantics therefore
  remain unestablished.

This correction follows the historical Human Teaching policy in the same
GoGoMatch evidence: insufficiently trained behavior must not be promoted into
the autonomous skill envelope.

## Acceptance impact

R10-B/R10-C score behavior count, not a required minimum number of migrated
domain commands. Their frozen bar is evidence integrity, deterministic
contracts, revision binding, risk classification, no hidden legacy path, and
no blind replay. Reducing the runnable set to evidence-supported behavior makes
that bar stricter without weakening any safety criterion.
