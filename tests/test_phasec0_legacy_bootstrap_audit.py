from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "phasec0_legacy_bootstrap_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("phasec0_legacy_bootstrap_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_audit_is_aggregate_and_flags_duplicate_and_review_required(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "legacy.mbk"
    records = [
        {"kind": "human_teaching", "topic": "safe", "fact": "operator said x", "status": "promoted"},
        {"e": "U", "k": "rule.alpha", "v": {"rule": "x"}},
        {"e": "D", "k": "fact.beta", "v": {"value": 1}},
        {"e": "D", "k": "fact.beta", "v": {"value": 2}},
        {"fmt": "MBK1"},
    ]
    source.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    report = module.audit_jsonl(source)

    assert report.total_lines == 5
    assert report.parsed_records == 5
    assert report.malformed_records == 0
    assert report.format_markers == 1
    assert report.keyed_records == 3
    assert report.duplicate_key_count == 1
    assert report.duplicate_record_count == 2
    assert len(report.duplicate_key_hashes) == 1
    assert report.record_classes["human_teaching"] == 1
    assert report.record_classes["user_evidence_unresolved"] == 1
    assert report.record_classes["device_evidence"] == 2
    assert report.candidate_eligible_records == 4
    assert report.review_required_records == 2


def test_audit_never_infers_user_evidence_as_fact_or_policy(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "legacy.mbk"
    source.write_text(
        json.dumps({"e": "U", "k": "some.rule", "v": "value"}) + "\n",
        encoding="utf-8",
    )

    report = module.audit_jsonl(source)

    assert report.record_classes == {"user_evidence_unresolved": 1}
    assert report.review_required_records == 1


def test_audit_tolerates_malformed_lines_without_promoting_them(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "legacy.mbk"
    source.write_text(
        '{"e":"D","k":"ok","v":1}\n' + "not-json\n",
        encoding="utf-8",
    )

    report = module.audit_jsonl(source)

    assert report.parsed_records == 1
    assert report.malformed_records == 1
    assert report.candidate_eligible_records == 1


def test_audit_hashes_duplicate_keys_instead_of_exporting_names(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "legacy.mbk"
    source.write_text(
        '\n'.join([
            json.dumps({"e": "D", "k": "private-looking-key", "v": 1}),
            json.dumps({"e": "D", "k": "private-looking-key", "v": 2}),
        ]) + "\n",
        encoding="utf-8",
    )

    report = module.audit_jsonl(source)
    rendered = json.dumps(report.__dict__, sort_keys=True)

    assert "private-looking-key" not in rendered
    assert report.duplicate_key_count == 1
    assert len(report.duplicate_key_hashes[0]) == 16


def test_candidates_never_inherit_authority_and_require_current_device(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "legacy.mbk"
    source.write_text(
        "\n".join([
            json.dumps({"e": "D", "k": "fact.one", "v": {"value": 1}}),
            json.dumps({"kind": "human_teaching", "fact": "operator says x"}),
        ]) + "\n",
        encoding="utf-8",
    )

    candidates = module.build_candidates(source)

    assert len(candidates) == 2
    for candidate in candidates:
        assert candidate.state == "candidate"
        assert candidate.requires_current_device_corroboration is True
        assert "trust" not in candidate.__dict__
        assert "authority" not in candidate.__dict__
        assert len(candidate.provenance) == 3
        assert candidate.candidate_id.startswith("legacy-")
    assert candidates[0].review_required is False
    assert candidates[0].semantic_class == "fact"
    assert candidates[1].review_required is True
    assert candidates[1].semantic_class == "other"
    assert candidates[1].teaching_kind == "unclassified"


def test_semantic_class_does_not_guess_user_originated_meaning(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "legacy.mbk"
    source.write_text(
        "\n".join([
            json.dumps({"e": "U", "k": "looks.like.rule", "v": {"rule": "x"}}),
            json.dumps({"kind": "operating_policy", "fact": "do x"}),
            json.dumps({"e": "D", "k": "observed.fact", "v": 1}),
        ]) + "\n",
        encoding="utf-8",
    )

    candidates = module.build_candidates(source)

    assert [item.semantic_class for item in candidates] == ["other", "policy", "fact"]


def test_duplicate_candidates_are_preserved_and_forced_to_review(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "legacy.mbk"
    source.write_text(
        "\n".join([
            json.dumps({"e": "D", "k": "same", "v": 1}),
            json.dumps({"e": "D", "k": "same", "v": 2}),
        ]) + "\n",
        encoding="utf-8",
    )

    candidates = module.build_candidates(source)

    assert len(candidates) == 2
    assert candidates[0].duplicate_group == candidates[1].duplicate_group
    assert candidates[0].review_required is True
    assert candidates[1].review_required is True
    assert candidates[0].candidate_id != candidates[1].candidate_id


def test_candidate_file_round_trip_is_deterministic(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "legacy.mbk"
    output_a = tmp_path / "a.jsonl"
    output_b = tmp_path / "b.jsonl"
    source.write_text(
        json.dumps({"e": "D", "k": "stable", "v": [1, 2, 3]}) + "\n",
        encoding="utf-8",
    )

    assert module.write_candidates(source, output_a) == 1
    assert module.write_candidates(source, output_b) == 1
    assert output_a.read_bytes() == output_b.read_bytes()


def test_catalog_audit_exports_only_aggregate_shape(tmp_path: Path):
    module = _load_module()
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "version": 2,
                "item_families": [
                    {
                        "family_id": "private-family-name",
                        "complete": True,
                        "levels": [
                            {"level": 1, "identity": "private-one"},
                            {
                                "level": 2,
                                "identity": "private-two",
                                "visual_descriptor": {"data": "secret-image-shape"},
                            },
                        ],
                    }
                ],
                "merge_transitions": [{"from": "private-one", "to": "private-two"}],
                "producers": [
                    {
                        "identity": "private-producer",
                        "outputs_complete": True,
                        "possible_outputs": [{"identity": "private-one"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = module.audit_catalog_json(catalog)
    rendered = json.dumps(report.__dict__, sort_keys=True)

    assert report.catalog_version == 2
    assert report.item_families == 1
    assert report.complete_item_families == 1
    assert report.item_levels == 2
    assert report.merge_transitions == 1
    assert report.producers == 1
    assert report.producers_with_complete_outputs == 1
    assert report.possible_outputs == 1
    assert report.visual_descriptors == 1
    assert "private-family-name" not in rendered
    assert "private-producer" not in rendered
    assert "secret-image-shape" not in rendered
