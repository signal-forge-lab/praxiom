"""R6-C Knowledge Hygiene (generic pipeline over synthetic fixtures)."""
from __future__ import annotations

import hashlib
import unicodedata

__all__ = ["normalize_claim", "mojibake_score", "claim_key",
           "find_duplicates", "find_conflicts"]


def mojibake_score(text: str) -> float:
    """Fraction of replacement/lone-surrogate/control signals in text."""
    if not text:
        return 0.0
    bad = text.count("\ufffd")
    bad += sum(1 for ch in text if 0xD800 <= ord(ch) <= 0xDFFF)
    bad += sum(1 for ch in text if ord(ch) < 0x20 and ch not in ("\n", "\t"))
    return bad / max(1, len(text))


def normalize_claim(text: str) -> str:
    """NFKC + strip + collapse whitespace; retains provenance elsewhere."""
    normed = unicodedata.normalize("NFKC", text).strip()
    return " ".join(normed.split())


def claim_key(text: str) -> str:
    return hashlib.sha256(normalize_claim(text).lower().encode()).hexdigest()[:16]


def find_duplicates(claims: list[str]) -> list[list[int]]:
    groups: dict[str, list[int]] = {}
    for i, c in enumerate(claims):
        groups.setdefault(claim_key(c), []).append(i)
    return [v for v in groups.values() if len(v) > 1]


def find_conflicts(pairs: list[tuple[str, str]],
                   conflict_keys: set[frozenset[str]]) -> list[tuple[str, str]]:
    """Conflict detection over normalized claim keys (never silent overwrite)."""
    out = []
    for a, b in pairs:
        if frozenset({claim_key(a), claim_key(b)}) in conflict_keys:
            out.append((a, b))
    return out
