from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConstraintType(str, Enum):
    """Well-known constraint types handled by the framework's built-in evaluators.

    Domain packs may register additional constraint types (e.g.
    ``companion_action_required``) by attaching evaluators to a Domain.
    ``Constraint.type`` is a plain string so unknown-to-the-enum types are also
    valid as long as some evaluator (built-in or domain-provided) handles them.
    """

    ABSOLUTE_PROHIBITION = "absolute_prohibition"
    MUTUAL_EXCLUSION = "mutual_exclusion"
    TEMPORAL_RESTRICTION = "temporal_restriction"
    MODE_OVERRIDE = "mode_override"
    METADATA_REQUIREMENT = "metadata_requirement"


@dataclass
class Constraint:
    id: str
    description: str
    type: str
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Constraint":
        return cls(
            id=data["id"],
            description=data["description"],
            # Plain string — well-known names match ConstraintType values; domain-specific
            # constraint types (companion_action_required, etc.) are accepted as-is.
            type=data["type"],
            parameters={k: v for k, v in data.items() if k not in ("id", "description", "type")},
        )
