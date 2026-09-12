# Praxiom

[English](README.md) | [日本語](README.ja.md)

> **Development snapshot - 2026-09-12.** Praxiom is under active development.
> APIs, evidence formats, and operational workflows may change without
> compatibility guarantees. This public repository starts from a sanitized
> snapshot; pre-publication local Git history is intentionally not included.

**Praxiom = Praxis + Axiom**: act in the world, learn from the result, distill
experience into durable principles, and use those principles to act better
next time.

Praxiom is a general-purpose iOS execution and learning platform built around
an independently implemented Native iOS Runtime plus generic Learning,
Experience, Shadow/Adaptive, Promotion, Telemetry, Recovery, and Human Teaching
layers. Merge Boss is a representative domain used to exercise the platform;
game-specific concepts are intentionally kept out of shared learning/runtime
infrastructure.

## Current development status

The R3-R10 critical path is complete. Post-R10 Phase A and Phase B are complete,
and **Phase C0 (Phase C Readiness) is 100% complete**.

Phase C is currently active as a limited, operation-class-by-operation-class
canary program. It is not a blanket enablement of Adaptive Live execution.

Accepted Phase C canaries in this snapshot:

- `system:return-home`
- `system:launch-application`
- `mergeboss:open-level-board`

Generator production, merge execution, order delivery, and broader autonomous
gameplay are **not** implied by those acceptances. Sequence Live remains off.

Current status and retained evidence:

- `docs/STATUS.md`
- `docs/evidence/PHASE_C_PROGRESS.md`
- `docs/evidence/20260912_phasec-home-live-canary-acceptance.json`
- `docs/evidence/20260912_phasec-launch-application-live-canary-acceptance.json`
- `docs/evidence/20260912_phasec-mergeboss-open-board-canary-acceptance.json`

The latest retained deterministic suite for this snapshot is **600/600 PASS**,
with the Runtime boundary guard, provenance guard, compile check, and diff check
green.

## Development install

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

## Deterministic tests

```powershell
python -m pytest -q
```

Run from the repository root with the repository virtual environment active.
The deterministic suite has no physical-device dependency.

## Read-only Monitor

Praxiom includes a local read-only Monitor on port `17680`. It reads the
privacy-safe RunJournal and an optional latest-frame projection. Refreshing the
Monitor does not call Runtime `observe`, `execute`, `recover`, or `invalidate`,
so it cannot rotate the active revision.

```powershell
.venv\Scripts\python -m praxiom.monitor.server
```

Open `http://127.0.0.1:17680/`. Non-loopback binding is rejected unless the
server is explicitly started with `--allow-lan`.

Current-screen bytes are sensitive and are **opt-in**. For the long-lived MCP
Runtime, Monitor Frame Projection can be enabled by restarting with:

```powershell
.\scripts\stop_praxiom_mcp.ps1
.\scripts\start_praxiom_mcp.ps1 -MonitorFrameProjection
```

The projection stores only `~/.praxiom/monitor/latest-frame.png` plus bounded
metadata and overwrites them on each observation. It is not an image history or
a Visual Flight Recorder implementation.

## Provenance

- **Phone Harness is historical/reference only.** It is not a production,
  build, or runtime dependency of this repository. Production Phone Harness
  source is not imported, copied, renamed-port, or called here.
- `scripts/check_provenance.py` enforces that boundary in production source and
  dependency declarations.
- **Active execution path:** `praxiom.ios_runtime` -> unmodified upstream
  `pymobiledevice3` -> WDA / CoreDevice / iPhone.
- `pymobiledevice3` is pinned to the audited upstream commit
  `ec4ac06a850a6a884ca778350621f354faf347c6`.
- See `docs/PROVENANCE.md` for details.

## Public snapshot policy

This public repository begins from a sanitized 2026-09-12 development snapshot.
The private pre-publication Git history is intentionally not included because
historical development material contained workstation-local paths and other
environment-specific metadata that is not needed to build, test, review, or
extend Praxiom.

Environment-specific Secure MCP Tunnel helper scripts used by one local
development setup are also excluded from the public snapshot. They are not
required by the Praxiom Runtime, deterministic test suite, or local read-only
Monitor.

## Git workflow

Public development uses `main` for the reviewed stable public state,
`develop` for integration work that is already safe to disclose, and
short-lived `feature/*` branches for individual changes. Confidentiality is
never implemented with branches: secrets and workstation-local configuration
stay outside Git, and internal-only implementation belongs in a separate
private repository.

See [Git workflow (English)](docs/GIT_WORKFLOW.md) or
[Git workflow (日本語)](docs/GIT_WORKFLOW.ja.md).

## License

GPL-3.0-or-later. See `LICENSE`.
