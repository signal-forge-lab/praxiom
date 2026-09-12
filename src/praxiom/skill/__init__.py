"""R8 Skill Foundry public surface (domain-neutral, gated)."""
from praxiom.skill.need import CapabilityNeed, detect_need
from praxiom.skill.candidate import ActiveSkill, SkillCandidate
from praxiom.skill.gates import GateResult, run_gates
from praxiom.skill.sandbox import SandboxPolicy, SandboxResult, run_sandboxed
from praxiom.skill.reuse import ReuseDecision, reuse_decision
from praxiom.skill.lifecycle import LifecycleState, record_success, transition
from praxiom.skill.registry import (
    HumanGateApproval, LifecycleSnapshot, SkillRegistry, SkillRegistryError, SkillTrustToken,
)
from praxiom.skill.executor import (
    SkillExecutor, SkillExecutionError, SequenceExecution, SequenceStep,
)

__all__ = [
    "CapabilityNeed", "detect_need",
    "ActiveSkill", "SkillCandidate",
    "GateResult", "run_gates",
    "SandboxPolicy", "SandboxResult", "run_sandboxed",
    "ReuseDecision", "reuse_decision",
    "LifecycleState", "record_success", "transition",
    "SkillRegistry", "SkillRegistryError", "SkillTrustToken", "HumanGateApproval",
    "LifecycleSnapshot",
    "SkillExecutor", "SkillExecutionError", "SequenceExecution", "SequenceStep",
]
