from __future__ import annotations

from praxiom.domain.adapter import behavior_to_candidate
from praxiom.domain.system import LAUNCH_APPLICATION, RETURN_HOME, get_behavior
from praxiom.skill.gates import GATE_ORDER, run_gates


def test_system_return_home_is_low_risk_revision_bound_and_gate_clean():
    assert RETURN_HOME.behavior_id == "system:return-home"
    assert RETURN_HOME.domain == "system"
    assert RETURN_HOME.risk == "low"
    assert RETURN_HOME.reversibility == "reversible"
    assert RETURN_HOME.human_gate is False
    assert RETURN_HOME.ops == frozenset({"home"})
    candidate = behavior_to_candidate(RETURN_HOME)
    result = run_gates(candidate)
    assert result.passed is True
    assert result.evaluated == GATE_ORDER


def test_system_behavior_lookup_is_exact():
    assert get_behavior("system:return-home") is RETURN_HOME
    assert get_behavior("system:launch-application") is LAUNCH_APPLICATION


def test_system_launch_application_is_generic_low_risk_and_gate_clean():
    assert LAUNCH_APPLICATION.behavior_id == "system:launch-application"
    assert LAUNCH_APPLICATION.domain == "system"
    assert LAUNCH_APPLICATION.inputs == ("bundle-id", "expected-application-identity")
    assert LAUNCH_APPLICATION.risk == "low"
    assert LAUNCH_APPLICATION.reversibility == "reversible"
    assert LAUNCH_APPLICATION.human_gate is False
    assert LAUNCH_APPLICATION.ops == frozenset({"launch_app"})
    candidate = behavior_to_candidate(LAUNCH_APPLICATION)
    result = run_gates(candidate)
    assert result.passed is True
    assert result.evaluated == GATE_ORDER

