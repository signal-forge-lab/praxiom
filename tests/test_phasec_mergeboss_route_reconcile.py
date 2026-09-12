import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "phasec_mergeboss_route_reconcile.py"
SPEC = importlib.util.spec_from_file_location("phasec_mergeboss_route_reconcile", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_projection_is_read_only_and_identity_free(monkeypatch):
    monkeypatch.setattr(MODULE, "_home_anchor", lambda _obs: (False, 0))
    monkeypatch.setattr(
        MODULE,
        "_project_target",
        lambda _obs, *, target_kind, labels, contains=False: SimpleNamespace(
            target_kind=target_kind,
            count=0,
            bindable_count=0,
            semantic_cluster_count=0,
            bindable_button_count=0,
            roles=(),
            matched_fields=(),
        ),
    )
    result = MODULE._bounded_projection(
        SimpleNamespace(elements=()),
        foreground_expected_app=True,
    )
    assert result["mutation_count"] == 0
    assert result["foreground_expected_app"] is True
    assert result["privacy"]["bundle_id_persisted"] is False
