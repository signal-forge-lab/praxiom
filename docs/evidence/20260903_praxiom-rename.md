# Praxiom repository/package rename evidence

Date: 2026-09-03

This record covers the controlled rename checkpoint that was intentionally
deferred until the R3-08 real-device gate passed.

## Naming result

- Product / OSS: **Praxiom**
- Distribution: `praxiom`
- Python package: `praxiom`
- Native iOS Runtime module: `praxiom.ios_runtime`
- Repository directory: `products/praxiom` (**completed**)
- Historical Goal ID remains unchanged:
  `goal-adaptive-agent-r3-greenfield-native-ios-runtime-v0-20260901`

No compatibility package or import alias was added solely for the rename.

## Package migration

Tracked production source moved from:

```text
src/adaptive_agent/
```

to:

```text
src/praxiom/
```

All production/test imports were updated to `praxiom.*`, the distribution name
in `pyproject.toml` was changed to `praxiom`, and the owned XCUITest task name
was changed to `praxiom-wda-xctrunner`.

The old editable distribution was uninstalled before reinstalling the new
distribution. Generated old `adaptive_agent` source caches / egg metadata were
removed. Verification:

```text
PRAXIOM_IMPORT=PASS
OLD_IMPORT_PRESENT=False
DIST=0.1.0
```

## Deterministic regression

After the package rename and editable reinstall:

```text
130 passed
provenance guard: PASS
git diff --check: PASS
```

The provenance guard continues to report zero Phone Harness references in
production inputs.

## Real-device regression after package rename

The same attached USB iPhone and upstream-only WDA path were exercised again
using imports from `praxiom.ios_runtime`:

```text
observe -> Home -> fresh observe -> launch Settings -> fresh observe -> close
```

Result:

```text
home completed_actions=1
launch completed_actions=1
revision changed after Home=true
revision changed after launch=true
trace errors=0
```

This proves the package/module rename did not change the accepted R3 runtime
behavior.

## Repository-directory migration

The outer checkout was then renamed from `products/adaptive-agent` to
`products/praxiom`. The same `.git` directory/history remained intact; HEAD
stayed on commit `ce08f61` after the filesystem rename.

Because an editable Python install records its source path, `praxiom` was
temporarily not importable immediately after the directory move. Re-running
the repository-local editable install from `products/praxiom` repaired that
expected path metadata. Final verification from the new repository path:

```text
PRAXIOM_IMPORT=PASS
OLD_IMPORT_PRESENT=False
DIST=0.1.0
130 passed
provenance guard=PASS
```

The real-device bounded regression was then repeated from the final repository
path with `praxiom.ios_runtime`:

```text
home completed_actions=1
launch completed_actions=1
revision changed after Home=true
revision changed after launch=true
trace errors=0
```

The repository and package rename is therefore complete; no compatibility
layer or legacy import remains.

