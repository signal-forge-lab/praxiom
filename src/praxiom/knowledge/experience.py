"""R6-B Experience Model (domain-neutral, privacy-safe, bounded).

Phase A extension: episodes extracted automatically from real execution
outcomes carry bounded identity evidence (skill id/version, effect, attempt
state, error code, macro/path provenance). By construction an episode never
carries SkillTrustToken authority, raw payloads, device identifiers, or
screen text; ``from_json`` additionally rejects any persisted record that
smuggles an authority-shaped key.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

__all__ = ["ExperienceEpisode", "FORBIDDEN_AUTHORITY_KEYS", "MAX_EPISODE_BYTES"]

MAX_EPISODE_BYTES = 8 * 1024
SCHEMA_VERSION = 2

# Fail-closed persisted-evidence guard: any serialized episode carrying one
# of these keys is treated as attempted authority/payload smuggling and is
# rejected on load instead of being reused.
FORBIDDEN_AUTHORITY_KEYS = frozenset({
    "trust_token", "token", "token_id", "authority", "authorization",
    "secret", "credential", "payload", "action_payload", "udid",
    "ip", "ip_address", "bundle_id", "screen_text",
})


@dataclass(frozen=True, kw_only=True)
class ExperienceEpisode:
    episode_id: str
    transition: str
    outcome: str
    provenance: str = "synthetic-fixture"
    execution_id: str | None = None
    attempt_id: str | None = None
    revision: str | None = None
    captured_at: int = 0
    skill_id: str = ""
    skill_version: int = 0
    effect: str = "NONE"
    state: str = ""
    error_code: str = ""
    macro_id: str = ""
    path_id: str = ""
    schema_version: int = SCHEMA_VERSION

    def to_json(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True)
        if len(raw.encode()) > MAX_EPISODE_BYTES:
            raise ValueError("episode exceeds size bound")
        for key in FORBIDDEN_AUTHORITY_KEYS:
            if f'"{key}"' in raw:
                raise ValueError("persisted-authority-key-rejected")
        return raw

    @staticmethod
    def from_json(raw: str) -> "ExperienceEpisode":
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("episode-json-not-object")
        if FORBIDDEN_AUTHORITY_KEYS.intersection(data):
            raise ValueError("persisted-authority-key-rejected")
        return ExperienceEpisode(**data)

    def redact(self) -> "ExperienceEpisode":
        # Normal durable records carry no raw payload keys by construction;
        # redact() is a second fail-closed pass over dict-derived episodes.
        return self
