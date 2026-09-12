"""Phase C0 migration-only audit for historical knowledge JSONL.

This tool is intentionally outside ``src/``. It may understand the shape of
historical records, but it never creates Runtime/Skill authority and it never
writes to the Praxiom state root. Its output is an aggregate audit suitable for
review before any candidate-evidence import is designed or enabled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


@dataclass(frozen=True, kw_only=True)
class AuditReport:
    schema_version: int
    source_sha256: str
    total_lines: int
    parsed_records: int
    malformed_records: int
    format_markers: int
    keyed_records: int
    duplicate_key_count: int
    duplicate_record_count: int
    duplicate_key_hashes: tuple[str, ...]
    evidence_classes: dict[str, int]
    record_classes: dict[str, int]
    status_values: dict[str, int]
    top_level_kinds: dict[str, int]
    replacement_character_records: int
    control_character_records: int
    candidate_eligible_records: int
    review_required_records: int


@dataclass(frozen=True, kw_only=True)
class LegacyCandidate:
    schema_version: int
    candidate_id: str
    source_sha256: str
    source_line: int
    source_record_hash: str
    source_class: str
    evidence_class: str
    semantic_class: str
    teaching_kind: str
    state: str
    provenance: tuple[str, ...]
    requires_current_device_corroboration: bool
    review_required: bool
    duplicate_group: str | None
    claim: str


@dataclass(frozen=True, kw_only=True)
class CatalogAuditReport:
    schema_version: int
    source_sha256: str
    catalog_version: int | str | None
    item_families: int
    complete_item_families: int
    item_levels: int
    merge_transitions: int
    producers: int
    producers_with_complete_outputs: int
    possible_outputs: int
    visual_descriptors: int
    replacement_character_values: int
    control_character_values: int


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_strings(key)
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


def _has_bad_control(value: Any) -> bool:
    for text in _iter_strings(value):
        if any(ord(ch) < 0x20 and ch not in ("\n", "\r", "\t") for ch in text):
            return True
    return False


def _count_replacement_values(value: Any) -> int:
    return sum(1 for text in _iter_strings(value) if "\ufffd" in text)


def _count_control_values(value: Any) -> int:
    return sum(
        1
        for text in _iter_strings(value)
        if any(ord(ch) < 0x20 and ch not in ("\n", "\r", "\t") for ch in text)
    )


def _count_key_recursive(value: Any, key_name: str) -> int:
    if isinstance(value, dict):
        count = int(key_name in value)
        return count + sum(_count_key_recursive(item, key_name) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_count_key_recursive(item, key_name) for item in value)
    return 0


def _record_class(record: dict[str, Any]) -> str:
    """Classify only from explicit historical structure, never inferred meaning."""
    if record.get("fmt"):
        return "format_marker"
    kind = record.get("kind")
    if kind == "human_teaching":
        return "human_teaching"
    if kind == "operating_policy":
        return "operating_policy"
    if kind == "implementation_learning":
        return "implementation_learning"
    evidence = record.get("e")
    if evidence == "U":
        return "user_evidence_unresolved"
    if evidence == "D":
        return "device_evidence"
    if evidence == "H":
        return "hypothesis_evidence"
    return "unclassified"


def _canonical_claim(record: dict[str, Any]) -> str:
    fact = record.get("fact")
    if isinstance(fact, str) and fact.strip():
        return " ".join(fact.split())
    if isinstance(record.get("k"), str) and "v" in record:
        payload = {"key": record["k"], "value": record["v"]}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # Retain only the historical record itself as a canonical claim when the
    # older format has no explicit fact/key-value shape. This stays local.
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _teaching_kind(record: dict[str, Any], cls: str) -> str:
    if cls == "operating_policy":
        return "policy"
    if cls in {"human_teaching", "user_evidence_unresolved"}:
        return "unclassified"
    return "none"


def _semantic_class(record: dict[str, Any], cls: str) -> str:
    """Conservative policy/fact/other split using explicit structure only.

    Historical ``U`` means user-originated provenance, not semantic type.  It
    therefore stays ``other`` until an explicit review says otherwise.  Device
    evidence and explicit observation records are safe to classify as facts;
    explicit operating-policy records are policies.  Everything else remains
    ``other`` rather than guessing from free-form claim text.
    """
    if cls == "operating_policy":
        return "policy"
    if cls == "device_evidence" or record.get("kind") == "observation":
        return "fact"
    return "other"


def _status_value(record: dict[str, Any]) -> str:
    if isinstance(record.get("status"), str):
        return record["status"]
    value = record.get("v")
    if isinstance(value, dict) and isinstance(value.get("status"), str):
        return value["status"]
    return "none"


def audit_jsonl(path: Path) -> AuditReport:
    path = Path(path)
    evidence_classes: Counter[str] = Counter()
    record_classes: Counter[str] = Counter()
    status_values: Counter[str] = Counter()
    top_level_kinds: Counter[str] = Counter()
    key_lines: dict[str, list[int]] = defaultdict(list)
    parsed_records = 0
    malformed_records = 0
    format_markers = 0
    replacement_character_records = 0
    control_character_records = 0
    candidate_eligible_records = 0
    review_required_records = 0

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for lineno, text in enumerate(lines, start=1):
        if not text.strip():
            continue
        try:
            record = json.loads(text)
        except json.JSONDecodeError:
            malformed_records += 1
            continue
        if not isinstance(record, dict):
            malformed_records += 1
            continue
        parsed_records += 1
        cls = _record_class(record)
        record_classes[cls] += 1
        status_values[_status_value(record)] += 1

        kind = record.get("kind")
        if isinstance(kind, str):
            top_level_kinds[kind] += 1
        evidence = record.get("e")
        if isinstance(evidence, str):
            evidence_classes[evidence] += 1
        key = record.get("k")
        if isinstance(key, str) and key:
            key_lines[key].append(lineno)

        strings = tuple(_iter_strings(record))
        if any("\ufffd" in item for item in strings):
            replacement_character_records += 1
        if _has_bad_control(record):
            control_character_records += 1

        if cls == "format_marker":
            format_markers += 1
            continue
        # Historical records may seed candidate evidence, but user-originated
        # evidence remains review-required until policy-vs-fact is explicit.
        candidate_eligible_records += 1
        if cls in {
            "human_teaching",
            "operating_policy",
            "implementation_learning",
            "user_evidence_unresolved",
            "unclassified",
        }:
            review_required_records += 1

    duplicate_keys = {key: locs for key, locs in key_lines.items() if len(locs) > 1}
    duplicate_record_count = sum(len(locs) for locs in duplicate_keys.values())
    duplicate_hashes = tuple(sorted(_stable_hash(key) for key in duplicate_keys))

    return AuditReport(
        schema_version=SCHEMA_VERSION,
        source_sha256=_source_sha256(path),
        total_lines=len(lines),
        parsed_records=parsed_records,
        malformed_records=malformed_records,
        format_markers=format_markers,
        keyed_records=sum(1 for locs in key_lines.values() for _ in locs),
        duplicate_key_count=len(duplicate_keys),
        duplicate_record_count=duplicate_record_count,
        duplicate_key_hashes=duplicate_hashes,
        evidence_classes=dict(sorted(evidence_classes.items())),
        record_classes=dict(sorted(record_classes.items())),
        status_values=dict(sorted(status_values.items())),
        top_level_kinds=dict(sorted(top_level_kinds.items())),
        replacement_character_records=replacement_character_records,
        control_character_records=control_character_records,
        candidate_eligible_records=candidate_eligible_records,
        review_required_records=review_required_records,
    )


def audit_catalog_json(path: Path) -> CatalogAuditReport:
    """Aggregate the historical catalog without exporting domain names/content."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise ValueError("catalog-root-must-be-object")
    families = data.get("item_families", [])
    transitions = data.get("merge_transitions", [])
    producers = data.get("producers", [])
    if not isinstance(families, list):
        raise ValueError("catalog-item-families-must-be-list")
    if not isinstance(transitions, list):
        raise ValueError("catalog-merge-transitions-must-be-list")
    if not isinstance(producers, list):
        raise ValueError("catalog-producers-must-be-list")

    complete_families = 0
    item_levels = 0
    for family in families:
        if not isinstance(family, dict):
            continue
        if family.get("complete") is True:
            complete_families += 1
        levels = family.get("levels", [])
        if isinstance(levels, list):
            item_levels += len(levels)

    complete_producers = 0
    possible_outputs = 0
    for producer in producers:
        if not isinstance(producer, dict):
            continue
        if producer.get("outputs_complete") is True:
            complete_producers += 1
        outputs = producer.get("possible_outputs", [])
        if isinstance(outputs, list):
            possible_outputs += len(outputs)

    return CatalogAuditReport(
        schema_version=SCHEMA_VERSION,
        source_sha256=_source_sha256(path),
        catalog_version=data.get("version"),
        item_families=len(families),
        complete_item_families=complete_families,
        item_levels=item_levels,
        merge_transitions=len(transitions),
        producers=len(producers),
        producers_with_complete_outputs=complete_producers,
        possible_outputs=possible_outputs,
        visual_descriptors=_count_key_recursive(data, "visual_descriptor"),
        replacement_character_values=_count_replacement_values(data),
        control_character_values=_count_control_values(data),
    )


def build_candidates(path: Path) -> tuple[LegacyCandidate, ...]:
    """Build authority-free local candidate evidence from historical JSONL.

    This does not run Knowledge promotion, create a trust token, or change any
    live execution setting. Every candidate requires current-device
    corroboration before it may contribute to Phase C promotion readiness.
    """
    path = Path(path)
    source_sha = _source_sha256(path)
    parsed: list[tuple[int, dict[str, Any], str]] = []
    key_lines: dict[str, list[int]] = defaultdict(list)

    for lineno, text in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        if not text.strip():
            continue
        try:
            record = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        cls = _record_class(record)
        if cls == "format_marker":
            continue
        parsed.append((lineno, record, cls))
        key = record.get("k")
        if isinstance(key, str) and key:
            key_lines[key].append(lineno)

    duplicate_keys = {key for key, locs in key_lines.items() if len(locs) > 1}
    out: list[LegacyCandidate] = []
    for lineno, record, cls in parsed:
        canonical_record = json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        record_hash = hashlib.sha256(canonical_record.encode("utf-8")).hexdigest()
        key = record.get("k") if isinstance(record.get("k"), str) else None
        duplicate_group = _stable_hash(key) if key in duplicate_keys else None
        teaching_kind = _teaching_kind(record, cls)
        review_required = cls in {
            "human_teaching",
            "operating_policy",
            "implementation_learning",
            "user_evidence_unresolved",
            "unclassified",
        } or duplicate_group is not None
        evidence = record.get("e")
        evidence_class = evidence if isinstance(evidence, str) else "legacy"
        candidate_id = "legacy-" + _stable_hash(f"{source_sha}:{lineno}:{record_hash}")
        out.append(
            LegacyCandidate(
                schema_version=SCHEMA_VERSION,
                candidate_id=candidate_id,
                source_sha256=source_sha,
                source_line=lineno,
                source_record_hash=record_hash,
                source_class=cls,
                evidence_class=evidence_class,
                semantic_class=_semantic_class(record, cls),
                teaching_kind=teaching_kind,
                state="candidate",
                provenance=(
                    f"legacy-source-sha256:{source_sha}",
                    f"legacy-source-line:{lineno}",
                    f"legacy-record-sha256:{record_hash}",
                ),
                requires_current_device_corroboration=True,
                review_required=review_required,
                duplicate_group=duplicate_group,
                claim=_canonical_claim(record),
            )
        )
    return tuple(out)


def write_candidates(path: Path, output: Path) -> int:
    candidates = build_candidates(path)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for candidate in candidates:
            handle.write(
                json.dumps(asdict(candidate), ensure_ascii=False, sort_keys=True) + "\n"
            )
    return len(candidates)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("knowledge_jsonl", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--catalog-json", type=Path)
    parser.add_argument("--catalog-output", type=Path)
    parser.add_argument(
        "--candidate-output",
        type=Path,
        help="Optional local candidate JSONL. Never interpreted as live authority.",
    )
    args = parser.parse_args()

    report = audit_jsonl(args.knowledge_jsonl)
    rendered = json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    if args.candidate_output:
        write_candidates(args.knowledge_jsonl, args.candidate_output)
    if args.catalog_json:
        catalog = audit_catalog_json(args.catalog_json)
        catalog_rendered = json.dumps(
            asdict(catalog), ensure_ascii=False, indent=2, sort_keys=True
        )
        if args.catalog_output:
            args.catalog_output.parent.mkdir(parents=True, exist_ok=True)
            args.catalog_output.write_text(catalog_rendered + "\n", encoding="utf-8")
        else:
            print(catalog_rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
