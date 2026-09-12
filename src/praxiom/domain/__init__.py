"""Declarative shared domain adapter seam (public surface).

Domain behaviors are pure data; device mutation stays behind the
registry-owned skill lifecycle and the six-operation Runtime boundary.
"""
from praxiom.domain.adapter import DomainBehavior, behavior_to_candidate

__all__ = ["DomainBehavior", "behavior_to_candidate"]
