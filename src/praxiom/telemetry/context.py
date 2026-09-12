"""RunContext: configurable external state root and per-run directory layout.

Phase A durable telemetry (D1=A) stores one directory per run:

.. code-block:: text

    <state-root>/runs/<run_id>/
        events.jsonl                 # append-only observational journal
        summary.json                 # derived cache, never authority
        learning_snapshot.json       # derived cache, never authority
        coordinator-ledger.db        # only when Coordinator durability is on
        artifacts/                   # reserved for future visual references

The state root must be configurable and outside the repository by default:
it resolves from the ``PRAXIOM_STATE_ROOT`` environment variable when set,
otherwise ``~/.praxiom``. Tests always pass temporary directories. The
default is computed from the home directory, never from this checkout, so a
repository copy of the package cannot accidentally journal inside the repo.

``RunContext`` is a passive value object: it creates directories and hands
out paths only. It never writes journal events, never touches the Runtime or
Coordinator, and carries no mutation authority.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

__all__ = ["STATE_ROOT_ENV", "RunContext", "default_run_id", "resolve_state_root", "utc_now_iso"]

STATE_ROOT_ENV = "PRAXIOM_STATE_ROOT"


def resolve_state_root(environ: dict[str, str] | None = None) -> Path:
    """Resolve the telemetry state root.

    ``PRAXIOM_STATE_ROOT`` wins when set (expanded ``~`` allowed); otherwise
    ``~/.praxiom``. The default is always outside any repository checkout.
    """
    source = environ if environ is not None else os.environ
    configured = source.get(STATE_ROOT_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".praxiom"


def utc_now_iso(now: datetime | None = None) -> str:
    """Deterministic-format UTC timestamp, e.g. ``2026-09-09T12:00:00.000Z``."""
    value = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def default_run_id(now: datetime | None = None) -> str:
    """Sortable run id: ``run-<UTC compact stamp>-<8 hex>`` (token-safe)."""
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return "run-{}-{}".format(stamp.strftime("%Y%m%dT%H%M%SZ"), uuid.uuid4().hex[:8])


@dataclass(frozen=True)
class RunContext:
    """Paths for one run's durable telemetry directory layout."""

    state_root: Path
    run_id: str
    created_utc: str

    @classmethod
    def create(
        cls,
        *,
        state_root: Path | str | None = None,
        run_id: str | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> "RunContext":
        """Create (or re-open for crash recovery) one run directory.

        Re-creating a context for an existing ``run_id`` is intentionally
        idempotent: the journal, not the context, decides how the existing
        ``events.jsonl`` is interpreted (torn tails are preserved, see
        ``RunJournal``).
        """
        now_fn = now or (lambda: datetime.now(timezone.utc))
        root = Path(state_root) if state_root is not None else resolve_state_root()
        ctx = cls(
            state_root=root,
            run_id=run_id or default_run_id(now_fn()),
            created_utc=utc_now_iso(now_fn()),
        )
        ctx.run_dir.mkdir(parents=True, exist_ok=True)
        ctx.artifacts_dir.mkdir(parents=True, exist_ok=True)
        return ctx

    @property
    def run_dir(self) -> Path:
        return self.state_root / "runs" / self.run_id

    @property
    def events_path(self) -> Path:
        return self.run_dir / "events.jsonl"

    @property
    def summary_path(self) -> Path:
        return self.run_dir / "summary.json"

    @property
    def learning_snapshot_path(self) -> Path:
        return self.run_dir / "learning_snapshot.json"

    @property
    def artifacts_dir(self) -> Path:
        return self.run_dir / "artifacts"

    @property
    def ledger_path(self) -> Path:
        """Run-scoped Coordinator attempt-ledger path (A2 primitive).

        Pass this as ``ExecutionCoordinator(ledger_path=...)`` to keep the
        durable safety/restart ledger inside the run directory. The file is
        created by the Coordinator when durability is enabled, never here.
        """
        return self.run_dir / "coordinator-ledger.db"

    def open_journal(self, **kwargs) -> "RunJournal":  # noqa: F821 - forward ref
        """Open the run journal (imported lazily to keep this module passive)."""
        from praxiom.telemetry.journal import RunJournal

        return RunJournal(self, **kwargs)
