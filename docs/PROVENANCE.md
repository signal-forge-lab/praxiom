# Provenance — Praxiom

Date: 2026-09-01; product/package rename completed 2026-09-03
Scope: R3-00 bootstrap (Goal `goal-adaptive-agent-r3-greenfield-native-ios-runtime-v0-20260901`)

## Greenfield boundary

This repository is a greenfield implementation. Phone Harness
(`phone-harness-windows/phone-harness`) is **historical/reference material
only**: it is never a production, build, or runtime dependency of this
repository. No Phone Harness package, module, subprocess, MCP server/hop,
adapter, or fallback is imported, copied, renamed-port, or called here.
Requirements are implemented from the independently specified Native iOS
Runtime contract (R2) and the greenfield architecture roadmap, not from
Phone Harness source.

Enforcement: `scripts/check_provenance.py` scans the production inputs
(`src/` and `pyproject.toml`) for any Phone Harness import/name/dependency and
exits non-zero on a hit. Documentation paths (`docs/`, `README.md`) are
intentionally excluded from the scan because they must state the prohibition.
The deterministic test command (`python -m pytest -q`, see README) runs this
check as part of the suite. During R3-00 the guard proved itself by catching
and rejecting one docstring mention of the harness name inside `src/`; the
source was rewritten instead of weakening the guard.

## Dependency baseline

- Runtime dependency: `pymobiledevice3`, unmodified **upstream**
  `doronz88/pymobiledevice3`, pinned at commit
  `ec4ac06a850a6a884ca778350621f354faf347c6` (the exact commit audited by the
  R1 upstream audit).
- Declared in `pyproject.toml` as
  `pymobiledevice3 @ git+https://github.com/doronz88/pymobiledevice3@ec4ac06a850a6a884ca778350621f354faf347c6`.
- The local downstream fork (signal-forge-lab, commit `d73fa942...`, including
  its `wda_ext.py` extensions) is **not** the dependency baseline and must not
  be used or imported.
- Do not silently advance the pin. Any pin change requires the documented R1
  gate: reproduce the failure, identify the upstream change that fixes it,
  update the pin explicitly, rerun all deterministic tests and attached-device
  smoke, and record the new exact SHA.

## Installed dependency evidence (2026-09-01, this host, repo venv `.venv`)

- Interpreter: CPython 3.12.10 (`platform.platform()`:
  `Windows-11-10.0.26200-SP0`).
- Install command: `.venv\Scripts\python -m pip install -e ".[dev]"` —
  completed successfully.

`pip show pymobiledevice3`:

```text
Name: pymobiledevice3
Version: 11.3.0
Summary: Pure python3 implementation for working with iDevices (iPhone, etc...)
Home-page: https://github.com/doronz88/pymobiledevice3
License-Expression: GPL-3.0-or-later
Location: repository-local `.venv\Lib\site-packages`
Required-by: praxiom
```

`pip freeze` (relevant lines):

```text
pymobiledevice3 @ git+https://github.com/doronz88/pymobiledevice3@ec4ac06a850a6a884ca778350621f354faf347c6
pytest==9.1.1
```

Resolved source URL / commit proof —
`.venv\Lib\site-packages\pymobiledevice3-11.3.0.dist-info\direct_url.json`:

```json
{"url": "https://github.com/doronz88/pymobiledevice3", "vcs_info": {"commit_id": "ec4ac06a850a6a884ca778350621f354faf347c6", "requested_revision": "ec4ac06a850a6a884ca778350621f354faf347c6", "vcs": "git"}}
```

The installed package lives inside this repository's own venv
(`.venv\Lib\site-packages\pymobiledevice3\`), not under any downstream-fork
path, and resolves exactly to the pinned upstream commit.

Known transitive-dependency note: `xonsh` (pulled in by `pymobiledevice3`)
ships a pytest11 plugin that builds an interactive `prompt_toolkit` shell and
crashes under non-console pytest runs (`NoConsoleScreenBufferError`). The
repository disables exactly that plugin via `addopts = "-p no:xonsh"` in
`pyproject.toml`; `xonsh` is irrelevant to the runtime library path. This is
repo-local composition config, not an upstream patch.

## License

GPL-3.0-or-later. `LICENSE` contains the canonical GPLv3 text fetched from
https://www.gnu.org/licenses/gpl-3.0.txt (35,149 bytes) via Python
`urllib`. Chosen because `pymobiledevice3` is GPL-3.0-or-later
(greenfield roadmap §4 dependency/licensing policy).
