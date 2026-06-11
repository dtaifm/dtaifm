"""Generic, domain-neutral constraint evaluators.

These cover the policy shapes most domain packs otherwise re-implement as
custom evaluators — allowlists, denylists, companion requirements, mutual
exclusion, and numeric bounds. They follow the same signature as every other
evaluator: (Rule, Constraint) -> ConstraintViolation | None. Domain-registered
evaluators still take priority, so a domain can override any of these types.
"""

from dtaifm.core.constraint import Constraint
from dtaifm.core.result import ConstraintViolation
from dtaifm.core.rule import Rule


def _violation(constraint: Constraint, reason: str) -> ConstraintViolation:
    return ConstraintViolation(
        constraint_id=constraint.id,
        constraint_description=constraint.description,
        reason=reason,
    )


def action_allowlist(rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
    """Every rule action must be drawn from `allowed_actions`.

    Optional `applies_to` restricts the check to actions on the listed devices.
    """
    allowed: list[str] = constraint.parameters.get("allowed_actions", [])
    applies_to: list[str] = constraint.parameters.get("applies_to", [])
    if not allowed:
        return None
    for a in rule.actions:
        if applies_to and a.device not in applies_to:
            continue
        if a.action not in allowed:
            return _violation(
                constraint,
                f"Rule '{rule.id}' uses action '{a.action}' on device '{a.device}' "
                f"which is not in the allowlist {sorted(allowed)}.",
            )
    return None


def action_denylist(rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
    """No rule action may appear in `denied_actions`.

    Optional `applies_to` restricts the check to actions on the listed devices.
    """
    denied: list[str] = constraint.parameters.get("denied_actions", [])
    applies_to: list[str] = constraint.parameters.get("applies_to", [])
    for a in rule.actions:
        if applies_to and a.device not in applies_to:
            continue
        if a.action in denied:
            return _violation(
                constraint,
                f"Rule '{rule.id}' performs denied action '{a.action}' on device '{a.device}'.",
            )
    return None


def requires(rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
    """A rule performing `if_action` must also carry `requires_action` and/or a
    condition of type `requires_condition` (optionally with matching
    `condition_parameters`)."""
    if_action: str = constraint.parameters.get("if_action", "")
    requires_action: str = constraint.parameters.get("requires_action", "")
    requires_condition: str = constraint.parameters.get("requires_condition", "")
    condition_parameters: dict = constraint.parameters.get("condition_parameters", {})
    if not if_action or not (requires_action or requires_condition):
        return None
    rule_action_kinds = {a.action for a in rule.actions}
    if if_action not in rule_action_kinds:
        return None
    if requires_action and requires_action not in rule_action_kinds:
        return _violation(
            constraint,
            f"Rule '{rule.id}' performs '{if_action}' without the required "
            f"companion action '{requires_action}'.",
        )
    if requires_condition:
        satisfied = any(
            c.type == requires_condition
            and all(c.parameters.get(k) == v for k, v in condition_parameters.items())
            for c in rule.conditions
        )
        if not satisfied:
            detail = f" with parameters {condition_parameters}" if condition_parameters else ""
            return _violation(
                constraint,
                f"Rule '{rule.id}' performs '{if_action}' without the required "
                f"condition '{requires_condition}'{detail}.",
            )
    return None


def mutually_exclusive_actions(rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
    """A single rule may not combine two or more of the listed `actions`."""
    exclusive: list[str] = constraint.parameters.get("actions", [])
    present = sorted({a.action for a in rule.actions}.intersection(exclusive))
    if len(present) > 1:
        return _violation(
            constraint,
            f"Rule '{rule.id}' combines mutually exclusive actions: {present}.",
        )
    return None


def parameter_threshold(rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
    """A numeric parameter on a matching action (`action:`) or condition
    (`condition:`) must satisfy `min`/`max`.

    Fail-closed: when a bound is declared, a matching action/condition whose
    parameter is missing or non-numeric is rejected — a rule may not dodge a
    limit by omitting the value it is limited on.
    """
    action_kind: str = constraint.parameters.get("action", "")
    condition_type: str = constraint.parameters.get("condition", "")
    parameter: str = constraint.parameters.get("parameter", "")
    minimum = constraint.parameters.get("min")
    maximum = constraint.parameters.get("max")
    if not parameter or (minimum is None and maximum is None) or not (action_kind or condition_type):
        return None
    if action_kind:
        targets = [("action", a.action, a.parameters) for a in rule.actions if a.action == action_kind]
    else:
        targets = [("condition", c.type, c.parameters) for c in rule.conditions if c.type == condition_type]
    for kind, name, params in targets:
        value = params.get(parameter)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return _violation(
                constraint,
                f"Rule '{rule.id}' {kind} '{name}' must declare a numeric "
                f"'{parameter}' (got {value!r}).",
            )
        if minimum is not None and value < minimum:
            return _violation(
                constraint,
                f"Rule '{rule.id}' {kind} '{name}' has '{parameter}'={value}, "
                f"below the minimum {minimum}.",
            )
        if maximum is not None and value > maximum:
            return _violation(
                constraint,
                f"Rule '{rule.id}' {kind} '{name}' has '{parameter}'={value}, "
                f"above the maximum {maximum}.",
            )
    return None


GENERIC_EVALUATORS = {
    "action_allowlist": action_allowlist,
    "action_denylist": action_denylist,
    "requires": requires,
    "mutually_exclusive_actions": mutually_exclusive_actions,
    "parameter_threshold": parameter_threshold,
}
