"""Phase A observational run telemetry (design decision D1=A).

This package is the per-run durable telemetry journal lane: an append-only,
schema-versioned, privacy-safe JSONL event journal plus derived (never
authoritative) summary and learning-snapshot projections.

Authority rules enforced by construction:

- observational only: nothing here imports or calls the Native iOS Runtime,
  the Coordinator, or any Skill/Adaptive component; this package can never
  mutate device state and never gains mutation authority;
- the journal is never a safety authority: journal write failures raise and
  never invent success; authoritative safety state remains
  Skill lifecycle -> Coordinator (durable attempt ledger) -> Runtime
  revision check -> Runtime execute;
- privacy is a fail-safe allowlist: envelope and payload fields are
  bounded, token-shaped, and allowlisted; anything else is dropped or
  replaced by a truncated SHA-256 fingerprint, so raw secrets, device
  identifiers, IP addresses, bundle identifiers, screen text, action
  payloads, or trust-token authority have no path onto disk.

Modules:

- ``context``   — configurable external state root + per-run directory layout
- ``journal``   — append-only per-run JSONL journal (crash/restart tolerant)
- ``bridges``   — correlation primitives for Runtime Trace records and
                  Coordinator attempts/executions (duck-typed, no wiring)
- ``summary``   — rough per-run improvement report + learning snapshot

Integration note: production wiring (calling these primitives from the live
SkillExecutor/Coordinator/Domain paths) is owned by the single integration
owner, not by this package.
"""

from praxiom.telemetry.context import (
    STATE_ROOT_ENV,
    RunContext,
    resolve_state_root,
)
from praxiom.telemetry.journal import (
    ALLOWED_EVENT_TYPES,
    ALLOWED_PHASES,
    ALLOWED_PAYLOAD_KEYS,
    ALLOWED_VISUAL_HINTS,
    JOURNAL_SCHEMA_VERSION,
    JournalClosedError,
    JournalStats,
    JournalWriteError,
    RunJournal,
    fingerprint_revision,
    sanitize_payload,
)
from praxiom.telemetry.bridges import (
    record_attempt,
    record_execution,
    record_runtime_trace,
    record_trace_record,
)
from praxiom.telemetry.summary import build_learning_snapshot, build_summary
from praxiom.telemetry.phaseb_report import (
    PHASEB_REPORT_SCHEMA_VERSION,
    build_phaseb_report,
)

__all__ = [
    "ALLOWED_EVENT_TYPES",
    "ALLOWED_PHASES",
    "ALLOWED_PAYLOAD_KEYS",
    "ALLOWED_VISUAL_HINTS",
    "JOURNAL_SCHEMA_VERSION",
    "JournalClosedError",
    "JournalStats",
    "JournalWriteError",
    "PHASEB_REPORT_SCHEMA_VERSION",
    "RunContext",
    "RunJournal",
    "STATE_ROOT_ENV",
    "build_learning_snapshot",
    "build_phaseb_report",
    "build_summary",
    "fingerprint_revision",
    "record_attempt",
    "record_execution",
    "record_runtime_trace",
    "record_trace_record",
    "resolve_state_root",
    "sanitize_payload",
]
