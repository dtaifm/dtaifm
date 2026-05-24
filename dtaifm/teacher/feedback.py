"""Deterministic feedback artifact built from validation failures.

The feedback file is a portable record of what the validator rejected and why.
It carries the domain vocabulary alongside each rejected rule so that a teacher
(local or cloud) has everything it needs to produce a compliant revision.

The deterministic layer may teach the teacher, but it never lets the teacher
grade itself: build_feedback runs the validator only — no runtime, no execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dtaifm.core.constraint import Constraint
from dtaifm.core.ruleset import RuleSet
from dtaifm.domains.base import Domain
from dtaifm.schema import SCHEMA_VERSION
from dtaifm.student.validator import Validator


@dataclass
class RuleViolation:
    constraint_id: str
    constraint_description: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "constraint_id": self.constraint_id,
            "constraint_description": self.constraint_description,
            "reason": self.reason,
        }


@dataclass
class RejectedRuleRecord:
    rule_id: str
    name: str
    violations: list[RuleViolation]
    allowed_triggers: list[str]
    allowed_conditions: list[str]
    allowed_actions: list[str]

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "violations": [v.to_dict() for v in self.violations],
            "allowed_triggers": list(self.allowed_triggers),
            "allowed_conditions": list(self.allowed_conditions),
            "allowed_actions": list(self.allowed_actions),
        }


@dataclass
class TeacherFeedback:
    """Portable feedback artifact derived from a validator pass."""

    schema_version: str
    domain: dict
    rejected_rules: list[RejectedRuleRecord] = field(default_factory=list)
    approved_rule_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "domain": dict(self.domain),
            "approved_rule_ids": list(self.approved_rule_ids),
            "rejected_rules": [r.to_dict() for r in self.rejected_rules],
        }

    @property
    def has_rejections(self) -> bool:
        return bool(self.rejected_rules)


def build_feedback(
    ruleset: RuleSet,
    constraints: list[Constraint],
    domain: Domain,
) -> TeacherFeedback:
    """Validate `ruleset` against `constraints` under `domain` and emit feedback.

    Pure validation: no runtime is instantiated, no events fire, no actions execute.
    """
    validator = Validator(constraints, domain=domain)
    result = validator.validate_ruleset(ruleset)

    rule_by_id = {r.id: r for r in ruleset}
    allowed_triggers = sorted(domain.trigger_events)
    allowed_conditions = sorted(domain.condition_types)
    allowed_actions = sorted(domain.action_kinds)

    rejected_records: list[RejectedRuleRecord] = []
    for vr in result.rejected:
        rule = rule_by_id.get(vr.rule_id)
        rejected_records.append(RejectedRuleRecord(
            rule_id=vr.rule_id,
            name=rule.name if rule is not None else "",
            violations=[
                RuleViolation(
                    constraint_id=v.constraint_id,
                    constraint_description=v.constraint_description,
                    reason=v.reason,
                )
                for v in vr.violations
            ],
            allowed_triggers=allowed_triggers,
            allowed_conditions=allowed_conditions,
            allowed_actions=allowed_actions,
        ))

    return TeacherFeedback(
        schema_version=SCHEMA_VERSION,
        domain={"id": domain.id, "version": domain.version},
        rejected_rules=rejected_records,
        approved_rule_ids=list(result.approved),
    )
