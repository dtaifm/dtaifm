"""Domain pack abstraction.

A Domain defines what is possible — vocabulary plus optional domain-specific
constraint evaluators. Teachers propose only within that boundary; the validator
rejects any rule that uses out-of-vocabulary triggers, conditions, or actions.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from dtaifm.core.constraint import Constraint
from dtaifm.core.result import ConstraintViolation
from dtaifm.core.rule import Rule


# A constraint evaluator returns None for "rule satisfies constraint" or a
# ConstraintViolation describing the failure. Domains plug evaluators in via
# extra_constraint_evaluators keyed by the constraint's `type` string.
ConstraintEvaluator = Callable[[Rule, Constraint], Optional[ConstraintViolation]]


@dataclass
class Domain:
    """A domain pack registered into the framework."""

    id: str
    version: str
    description: str = ""
    trigger_events: frozenset[str] = field(default_factory=frozenset)
    condition_types: frozenset[str] = field(default_factory=frozenset)
    action_kinds: frozenset[str] = field(default_factory=frozenset)
    extra_constraint_evaluators: dict[str, ConstraintEvaluator] = field(default_factory=dict)
    state_schema: dict[str, Any] = field(default_factory=dict)
