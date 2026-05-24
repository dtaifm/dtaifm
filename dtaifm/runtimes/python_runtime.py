from datetime import datetime
from typing import Optional

from dtaifm.core.rule import Rule, Condition
from dtaifm.core.result import ConditionEvaluation, ExecutionResult, RuleExecutionTrace
from dtaifm.domains.base import Domain


class PythonRuntime:
    """
    Deterministic execution engine for approved rule sets.

    Only accepts rules that have already passed the Validator. When a Domain is
    provided, the runtime performs a defense-in-depth check that every rule's
    actions belong to the domain's action vocabulary, refusing to execute any
    rule that contains an out-of-domain action — even if it somehow slipped past
    validation.

    Emits a per-rule trace describing exactly why each rule fired or was skipped.
    """

    def __init__(self, approved_rules: list[Rule], domain: Optional[Domain] = None) -> None:
        self._rules = list(approved_rules)
        self._domain = domain

    def fire(self, event_device: str, event_type: str, state: dict) -> ExecutionResult:
        result = ExecutionResult()
        current_time = state.get("time")
        if current_time is None:
            current_time = datetime.now()
        current_mode: str = state.get("mode", "normal")

        for rule in self._rules:
            trace = RuleExecutionTrace(rule_id=rule.id)

            # Defense-in-depth: refuse rules with actions outside the active domain.
            if self._domain is not None and not self._rule_in_domain(rule):
                trace.reason = (
                    f"rule contains action outside domain '{self._domain.id}' "
                    f"(allowed action kinds: {sorted(self._domain.action_kinds)})"
                )
                result.skipped_rules.append(rule.id)
                result.trace.append(trace)
                continue

            if rule.trigger.device != event_device or rule.trigger.event != event_type:
                trace.reason = (
                    f"trigger did not match (rule expects {rule.trigger.device}.{rule.trigger.event})"
                )
                result.skipped_rules.append(rule.id)
                result.trace.append(trace)
                continue

            trace.matched_trigger = True

            condition_failure: str | None = None
            for condition in rule.conditions:
                passed = self._evaluate(condition, state, current_time, current_mode)
                trace.conditions_evaluated.append(
                    ConditionEvaluation(
                        type=condition.type,
                        parameters=dict(condition.parameters),
                        passed=passed,
                    )
                )
                if not passed:
                    condition_failure = condition.type
                    break

            if condition_failure is not None:
                trace.reason = f"condition '{condition_failure}' failed"
                result.skipped_rules.append(rule.id)
                result.trace.append(trace)
                continue

            for action in rule.actions:
                result.actions_taken.append({
                    "rule_id": rule.id,
                    "device": action.device,
                    "action": action.action,
                    "parameters": dict(action.parameters),
                })
                result.state_delta[action.device] = action.action

            trace.fired = True
            trace.reason = "trigger matched and all conditions passed"
            result.triggered_rule_ids.append(rule.id)
            result.trace.append(trace)

        return result

    def _rule_in_domain(self, rule: Rule) -> bool:
        if self._domain is None:
            return True
        return all(a.action in self._domain.action_kinds for a in rule.actions)

    def _evaluate(
        self,
        condition: Condition,
        state: dict,
        current_time: datetime,
        current_mode: str,
    ) -> bool:
        if condition.type == "time_range":
            start: int = condition.parameters.get("start_hour", 0)
            end: int = condition.parameters.get("end_hour", 24)
            hour = current_time.hour if isinstance(current_time, datetime) else int(current_time)
            if start > end:
                return hour >= start or hour < end
            return start <= hour < end

        if condition.type == "mode_not":
            return current_mode != condition.parameters.get("mode")

        if condition.type == "mode_is":
            return current_mode == condition.parameters.get("mode")

        if condition.type == "device_state":
            device = condition.parameters.get("device")
            expected = condition.parameters.get("state")
            return state.get(device) == expected

        return True
