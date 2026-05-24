"""
Smart home demo — dtaifm end-to-end walkthrough.

Flow:
  YAML constraints
    -> MockTeacher proposes candidate rules
    -> Validator approves or rejects each rule against constraints
    -> PythonRuntime executes only the approved rules
"""

from datetime import datetime
from pathlib import Path

import yaml

from dtaifm.core.constraint import Constraint
from dtaifm.core.rule import Rule
from dtaifm.runtimes.python_runtime import PythonRuntime
from dtaifm.student.validator import Validator
from dtaifm.teacher.contract import PromptContext, TeacherRequest
from dtaifm.teacher.mock_teacher import MockTeacher


def load_constraints(path: Path) -> list[Constraint]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return [Constraint.from_dict(c) for c in data["constraints"]]


def section(title: str) -> None:
    print(f"\n{'-' * 50}")
    print(f"  {title}")
    print(f"{'-' * 50}")


def main() -> None:
    print("=== dtaifm Smart Home Demo ===")
    print("AI proposes. The deterministic layer disposes.\n")

    # 1. Load hard constraints from YAML
    section("1. Constraints (defined by humans)")
    constraints_path = Path(__file__).parent / "constraints.yaml"
    constraints = load_constraints(constraints_path)
    for c in constraints:
        print(f"  [{c.id}]  {c.description}")

    # 2. Teacher proposes candidate rules
    section("2. Teacher proposes rules (AI / mock)")
    teacher = MockTeacher()
    request = TeacherRequest(constraints=constraints, context=PromptContext(domain="smart_home"))
    proposed = teacher.propose(request).ruleset
    print(f"  {len(proposed)} rule(s) proposed:")
    for rule in proposed:
        print(f"  [{rule.id}]  {rule.name}")

    # 3. Validator approves or rejects — deterministic gate
    section("3. Validator reviews each rule (deterministic)")
    validator = Validator(constraints)
    validation = validator.validate_ruleset(proposed)

    approved_ids = set(validation.approved)
    approved_rules: list[Rule] = [r for r in proposed if r.id in approved_ids]

    for rule in proposed:
        if rule.id in approved_ids:
            print(f"  APPROVED  [{rule.id}]  {rule.name}")
        else:
            vr = next(v for v in validation.rejected if v.rule_id == rule.id)
            print(f"  REJECTED  [{rule.id}]  {rule.name}")
            for violation in vr.violations:
                print(f"            ! [{violation.constraint_id}] {violation.reason}")

    # 4. Runtime executes approved rules against live events
    section("4. Runtime executes approved rules (deterministic)")
    runtime = PythonRuntime(approved_rules)

    scenarios = [
        {
            "label": "motion_detected at 23:00 - normal mode",
            "event_device": "motion_sensor",
            "event_type": "motion_detected",
            "state": {"time": datetime(2024, 1, 1, 23, 0), "mode": "normal", "ac": "off", "heating": "off"},
        },
        {
            "label": "motion_detected at 23:00 - security mode",
            "event_device": "motion_sensor",
            "event_type": "motion_detected",
            "state": {"time": datetime(2024, 1, 1, 23, 0), "mode": "security", "ac": "off", "heating": "off"},
        },
        {
            "label": "motion_detected at 14:00 - normal mode (outside night hours)",
            "event_device": "motion_sensor",
            "event_type": "motion_detected",
            "state": {"time": datetime(2024, 1, 1, 14, 0), "mode": "normal", "ac": "off", "heating": "off"},
        },
        {
            "label": "temperature_below_threshold - AC off, normal mode",
            "event_device": "thermostat",
            "event_type": "temperature_below_threshold",
            "state": {"time": datetime(2024, 1, 1, 20, 0), "mode": "normal", "ac": "off", "heating": "off"},
        },
    ]

    for scenario in scenarios:
        print(f"\n  Event: {scenario['label']}")
        result = runtime.fire(scenario["event_device"], scenario["event_type"], scenario["state"])
        if result.triggered_rule_ids:
            for action in result.actions_taken:
                params = action.get("parameters") or {}
                extra_str = f"  {params}" if params else ""
                print(f"    -> [{action['rule_id']}] {action['device']}: {action['action']}{extra_str}")
        else:
            print("    -> (no rules triggered)")


if __name__ == "__main__":
    main()
