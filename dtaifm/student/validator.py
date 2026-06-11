from typing import Optional

from dtaifm.core.constraint import Constraint
from dtaifm.core.rule import Rule
from dtaifm.core.ruleset import RuleSet
from dtaifm.core.result import ConstraintViolation, ValidationResult, RuleSetValidationResult
from dtaifm.domains.base import Domain
from dtaifm.student.generic_evaluators import GENERIC_EVALUATORS


class Validator:
    """
    The deterministic student. Validates every proposed rule against every constraint.

    No rule reaches the runtime without passing this gate. When a Domain is
    provided, the validator additionally rejects any rule that uses triggers,
    conditions, or actions outside the domain's vocabulary, and dispatches
    domain-specific constraint types to the evaluators the domain registered.
    """

    DOMAIN_PSEUDO_CONSTRAINT_ID = "__domain__"

    def __init__(self, constraints: list[Constraint], domain: Optional[Domain] = None) -> None:
        self._constraints = {c.id: c for c in constraints}
        self._domain = domain

    def validate_rule(self, rule: Rule) -> ValidationResult:
        violations: list[ConstraintViolation] = []

        if self._domain is not None:
            v = self._check_domain_compatibility(rule)
            if v is not None:
                violations.append(v)

        for constraint in self._constraints.values():
            v = self._check(rule, constraint)
            if v is not None:
                violations.append(v)

        return ValidationResult(rule_id=rule.id, is_valid=not violations, violations=violations)

    def validate_ruleset(self, ruleset: RuleSet) -> RuleSetValidationResult:
        result = RuleSetValidationResult()
        for rule in ruleset:
            vr = self.validate_rule(rule)
            if vr.is_valid:
                result.approved.append(rule.id)
            else:
                result.rejected.append(vr)
        return result

    # ------------------------------------------------------------------
    # Domain compatibility
    # ------------------------------------------------------------------

    def _check_domain_compatibility(self, rule: Rule) -> ConstraintViolation | None:
        d = self._domain
        if d is None:
            return None
        if rule.trigger.event not in d.trigger_events:
            return self._domain_violation(
                f"Rule '{rule.id}' uses trigger event '{rule.trigger.event}' which is not in domain "
                f"'{d.id}' (allowed: {sorted(d.trigger_events)})"
            )
        for c in rule.conditions:
            if c.type not in d.condition_types:
                return self._domain_violation(
                    f"Rule '{rule.id}' uses condition type '{c.type}' which is not in domain "
                    f"'{d.id}' (allowed: {sorted(d.condition_types)})"
                )
        for a in rule.actions:
            if a.action not in d.action_kinds:
                return self._domain_violation(
                    f"Rule '{rule.id}' uses action kind '{a.action}' which is not in domain "
                    f"'{d.id}' (allowed: {sorted(d.action_kinds)})"
                )
        return None

    def _domain_violation(self, reason: str) -> ConstraintViolation:
        return ConstraintViolation(
            constraint_id=self.DOMAIN_PSEUDO_CONSTRAINT_ID,
            constraint_description=f"Domain '{self._domain.id}' vocabulary check",
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Per-constraint dispatch
    # ------------------------------------------------------------------

    def _check(self, rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
        # Domain-provided evaluators take priority over built-ins so a domain
        # can override a generic type if it ever needs to.
        if self._domain is not None:
            extra = self._domain.extra_constraint_evaluators.get(constraint.type)
            if extra is not None:
                return extra(rule, constraint)

        builtin = {
            "absolute_prohibition": self._check_absolute_prohibition,
            "mutual_exclusion": self._check_mutual_exclusion,
            "temporal_restriction": self._check_temporal_restriction,
            "mode_override": self._check_mode_override,
            "metadata_requirement": self._check_metadata_requirement,
            **GENERIC_EVALUATORS,
        }
        handler = builtin.get(constraint.type)
        if handler is None:
            raise ValueError(
                f"Unknown constraint type '{constraint.type}' for constraint '{constraint.id}'. "
                f"Either use a built-in type or register a domain evaluator."
            )
        return handler(rule, constraint)

    # ------------------------------------------------------------------
    # Built-in evaluators
    # ------------------------------------------------------------------

    def _check_absolute_prohibition(self, rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
        applies_to: list[str] = constraint.parameters.get("applies_to", [])
        prohibited_action: str = constraint.parameters.get("action", "")
        for action in rule.actions:
            if action.device in applies_to and action.action == prohibited_action:
                return ConstraintViolation(
                    constraint_id=constraint.id,
                    constraint_description=constraint.description,
                    reason=(
                        f"Rule '{rule.id}' performs prohibited action '{prohibited_action}' "
                        f"on device '{action.device}'."
                    ),
                )
        return None

    def _check_mutual_exclusion(self, rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
        devices: list[str] = constraint.parameters.get("applies_to", [])
        activating = {
            a.device
            for a in rule.actions
            if a.action in ("turn_on", "activate", "enable")
        }
        conflicting = activating.intersection(devices)
        if len(conflicting) == len(devices) and len(devices) > 1:
            return ConstraintViolation(
                constraint_id=constraint.id,
                constraint_description=constraint.description,
                reason=(
                    f"Rule '{rule.id}' activates mutually exclusive devices simultaneously: "
                    f"{sorted(conflicting)}."
                ),
            )
        return None

    def _check_temporal_restriction(self, rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
        applies_to: list[str] = constraint.parameters.get("applies_to", [])
        restricted_trigger: str = constraint.parameters.get("trigger", "")
        for action in rule.actions:
            if action.device not in applies_to:
                continue
            if restricted_trigger and rule.trigger.event != restricted_trigger:
                continue
            has_time_condition = any(c.type == "time_range" for c in rule.conditions)
            if not has_time_condition:
                return ConstraintViolation(
                    constraint_id=constraint.id,
                    constraint_description=constraint.description,
                    reason=(
                        f"Rule '{rule.id}' controls '{action.device}' via '{restricted_trigger}' "
                        f"without a time_range condition."
                    ),
                )
        return None

    def _check_mode_override(self, rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
        overriding_mode: str = constraint.parameters.get("overriding_mode", "security")
        # Accept both legacy "comfort_devices" (smart_home) and generic "applies_to".
        target_devices: list[str] = (
            constraint.parameters.get("applies_to")
            or constraint.parameters.get("comfort_devices", [])
        )
        if not any(a.device in target_devices for a in rule.actions):
            return None
        has_mode_check = any(
            c.type == "mode_not" and c.parameters.get("mode") == overriding_mode
            for c in rule.conditions
        )
        if not has_mode_check:
            return ConstraintViolation(
                constraint_id=constraint.id,
                constraint_description=constraint.description,
                reason=(
                    f"Rule '{rule.id}' controls override-restricted device(s) without checking "
                    f"for '{overriding_mode}' mode override."
                ),
            )
        return None

    def _check_metadata_requirement(self, rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
        required_fields: list[str] = constraint.parameters.get("required_fields", [])
        for field_name in required_fields:
            if field_name == "satisfies_constraints" and not rule.satisfies_constraints:
                return ConstraintViolation(
                    constraint_id=constraint.id,
                    constraint_description=constraint.description,
                    reason=f"Rule '{rule.id}' does not declare which constraints it satisfies.",
                )
        return None
