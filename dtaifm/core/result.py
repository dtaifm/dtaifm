from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConstraintViolation:
    constraint_id: str
    constraint_description: str
    reason: str


@dataclass
class ValidationResult:
    rule_id: str
    is_valid: bool
    violations: list[ConstraintViolation] = field(default_factory=list)

    @property
    def is_rejected(self) -> bool:
        return not self.is_valid


@dataclass
class RuleSetValidationResult:
    approved: list[str] = field(default_factory=list)
    rejected: list[ValidationResult] = field(default_factory=list)

    @property
    def all_approved(self) -> bool:
        return len(self.rejected) == 0


@dataclass
class ConditionEvaluation:
    type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    passed: bool = False


@dataclass
class RuleExecutionTrace:
    rule_id: str
    matched_trigger: bool = False
    conditions_evaluated: list[ConditionEvaluation] = field(default_factory=list)
    fired: bool = False
    reason: str = ""


@dataclass
class ExecutionResult:
    triggered_rule_ids: list[str] = field(default_factory=list)
    actions_taken: list[dict] = field(default_factory=list)
    state_delta: dict = field(default_factory=dict)
    skipped_rules: list[str] = field(default_factory=list)
    trace: list[RuleExecutionTrace] = field(default_factory=list)
