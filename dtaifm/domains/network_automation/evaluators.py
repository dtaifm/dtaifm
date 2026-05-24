"""Domain-specific constraint evaluators for the network_automation pack.

These follow the same signature as the validator's built-in evaluators:
(Rule, Constraint) -> ConstraintViolation | None. They are plugged into the
domain via extra_constraint_evaluators, keyed by constraint `type`.
"""

from dtaifm.core.constraint import Constraint
from dtaifm.core.result import ConstraintViolation
from dtaifm.core.rule import Rule


def companion_action_required(rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
    """A rule that performs `if_action` must also perform `requires_action`."""
    if_action: str = constraint.parameters.get("if_action", "")
    requires_action: str = constraint.parameters.get("requires_action", "")
    if not if_action or not requires_action:
        return None
    rule_action_kinds = {a.action for a in rule.actions}
    if if_action in rule_action_kinds and requires_action not in rule_action_kinds:
        return ConstraintViolation(
            constraint_id=constraint.id,
            constraint_description=constraint.description,
            reason=(
                f"Rule '{rule.id}' performs '{if_action}' but is missing the required "
                f"companion action '{requires_action}'."
            ),
        )
    return None


def action_target_limit(rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
    """A rule may not apply `action_type` to more than `max_devices` distinct devices."""
    action_type: str = constraint.parameters.get("action_type", "")
    max_devices: int = int(constraint.parameters.get("max_devices", 1))
    if not action_type:
        return None
    affected_devices = {a.device for a in rule.actions if a.action == action_type}
    if len(affected_devices) > max_devices:
        return ConstraintViolation(
            constraint_id=constraint.id,
            constraint_description=constraint.description,
            reason=(
                f"Rule '{rule.id}' applies '{action_type}' to {len(affected_devices)} "
                f"devices ({sorted(affected_devices)}); max allowed is {max_devices}."
            ),
        )
    return None


def mode_required(rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
    """A rule that targets `applies_to` devices must declare a `mode_is: required_mode` guard."""
    required_mode: str = constraint.parameters.get("required_mode", "")
    applies_to: list[str] = constraint.parameters.get("applies_to", [])
    if not required_mode:
        return None
    targets_restricted = any(a.device in applies_to for a in rule.actions)
    if not targets_restricted:
        return None
    has_mode_check = any(
        c.type == "mode_is" and c.parameters.get("mode") == required_mode
        for c in rule.conditions
    )
    if not has_mode_check:
        return ConstraintViolation(
            constraint_id=constraint.id,
            constraint_description=constraint.description,
            reason=(
                f"Rule '{rule.id}' targets restricted device(s) without a "
                f"'mode_is: {required_mode}' guard."
            ),
        )
    return None
