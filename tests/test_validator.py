import pytest
from dtaifm.core.constraint import Constraint, ConstraintType
from dtaifm.core.rule import Action, Condition, Rule, Trigger
from dtaifm.domains.base import Domain
from dtaifm.student.validator import Validator


@pytest.fixture
def base_constraints() -> list[Constraint]:
    return [
        Constraint(
            id="no_auto_unlock",
            description="Never unlock doors automatically.",
            type=ConstraintType.ABSOLUTE_PROHIBITION,
            parameters={"applies_to": ["front_door", "back_door"], "action": "unlock"},
        ),
        Constraint(
            id="no_hvac_conflict",
            description="Do not turn heating and AC on at the same time.",
            type=ConstraintType.MUTUAL_EXCLUSION,
            parameters={"applies_to": ["heating", "ac"]},
        ),
        Constraint(
            id="motion_light_hours",
            description="Lights may turn on from motion only during configured night hours.",
            type=ConstraintType.TEMPORAL_RESTRICTION,
            parameters={"applies_to": ["hallway_light"], "trigger": "motion_detected"},
        ),
        Constraint(
            id="security_override",
            description="Security mode overrides comfort automation.",
            type=ConstraintType.MODE_OVERRIDE,
            parameters={
                "overriding_mode": "security",
                "comfort_devices": ["heating", "ac", "hallway_light"],
            },
        ),
        Constraint(
            id="rule_must_explain",
            description="Every generated rule must explain which constraint it satisfies.",
            type=ConstraintType.METADATA_REQUIREMENT,
            parameters={"required_fields": ["satisfies_constraints"]},
        ),
    ]


# ------------------------------------------------------------------
# Accepted rule: motion light with all required conditions
# ------------------------------------------------------------------

def test_valid_night_light_rule_is_approved(base_constraints):
    rule = Rule(
        id="r_valid_light",
        name="Valid Night Light",
        trigger=Trigger(device="motion_sensor", event="motion_detected"),
        conditions=[
            Condition(type="time_range", parameters={"start_hour": 22, "end_hour": 6}),
            Condition(type="mode_not", parameters={"mode": "security"}),
        ],
        actions=[Action(device="hallway_light", action="turn_on")],
        satisfies_constraints=["motion_light_hours", "security_override"],
        explanation="Night-only motion light, blocked in security mode.",
    )
    validator = Validator(base_constraints)
    result = validator.validate_rule(rule)
    assert result.is_valid
    assert result.violations == []


# ------------------------------------------------------------------
# Rejected rule: auto-unlock violates two constraints
# ------------------------------------------------------------------

def test_auto_unlock_rule_is_rejected(base_constraints):
    rule = Rule(
        id="r_auto_unlock",
        name="Auto Unlock (UNSAFE)",
        trigger=Trigger(device="arrival_sensor", event="user_arrived"),
        conditions=[],
        actions=[Action(device="front_door", action="unlock")],
        satisfies_constraints=[],
        explanation="",
    )
    validator = Validator(base_constraints)
    result = validator.validate_rule(rule)
    assert result.is_rejected
    violated_ids = {v.constraint_id for v in result.violations}
    assert "no_auto_unlock" in violated_ids
    assert "rule_must_explain" in violated_ids


# ------------------------------------------------------------------
# Rejected rule: simultaneous HVAC devices
# ------------------------------------------------------------------

def test_hvac_conflict_is_rejected(base_constraints):
    rule = Rule(
        id="r_hvac_both",
        name="Both HVAC (UNSAFE)",
        trigger=Trigger(device="thermostat", event="temperature_below_threshold"),
        conditions=[Condition(type="mode_not", parameters={"mode": "security"})],
        actions=[
            Action(device="heating", action="turn_on"),
            Action(device="ac", action="turn_on"),
        ],
        satisfies_constraints=["some_constraint"],
        explanation="Turns on both heating and AC.",
    )
    validator = Validator(base_constraints)
    result = validator.validate_rule(rule)
    assert result.is_rejected
    violated_ids = {v.constraint_id for v in result.violations}
    assert "no_hvac_conflict" in violated_ids


# ------------------------------------------------------------------
# Rejected rule: motion light without time_range condition
# ------------------------------------------------------------------

def test_motion_light_without_time_range_is_rejected(base_constraints):
    rule = Rule(
        id="r_light_no_time",
        name="Motion Light No Time Check (UNSAFE)",
        trigger=Trigger(device="motion_sensor", event="motion_detected"),
        conditions=[Condition(type="mode_not", parameters={"mode": "security"})],
        actions=[Action(device="hallway_light", action="turn_on")],
        satisfies_constraints=["some_constraint"],
        explanation="Missing time_range condition.",
    )
    validator = Validator(base_constraints)
    result = validator.validate_rule(rule)
    assert result.is_rejected
    violated_ids = {v.constraint_id for v in result.violations}
    assert "motion_light_hours" in violated_ids


# ------------------------------------------------------------------
# Rejected rule: comfort device without security mode check
# ------------------------------------------------------------------

def test_comfort_device_without_security_check_is_rejected(base_constraints):
    rule = Rule(
        id="r_comfort_no_security",
        name="Heating Without Security Check (UNSAFE)",
        trigger=Trigger(device="thermostat", event="temperature_below_threshold"),
        conditions=[Condition(type="device_state", parameters={"device": "ac", "state": "off"})],
        actions=[Action(device="heating", action="turn_on")],
        satisfies_constraints=["no_hvac_conflict"],
        explanation="Missing security mode check.",
    )
    validator = Validator(base_constraints)
    result = validator.validate_rule(rule)
    assert result.is_rejected
    violated_ids = {v.constraint_id for v in result.violations}
    assert "security_override" in violated_ids


# ------------------------------------------------------------------
# RuleSet validation: correct split of approved vs rejected
# ------------------------------------------------------------------

def test_ruleset_validation_splits_correctly(base_constraints):
    from dtaifm.core.ruleset import RuleSet

    good = Rule(
        id="r_good",
        name="Good Rule",
        trigger=Trigger(device="motion_sensor", event="motion_detected"),
        conditions=[
            Condition(type="time_range", parameters={"start_hour": 22, "end_hour": 6}),
            Condition(type="mode_not", parameters={"mode": "security"}),
        ],
        actions=[Action(device="hallway_light", action="turn_on")],
        satisfies_constraints=["motion_light_hours", "security_override"],
        explanation="Valid rule.",
    )
    bad = Rule(
        id="r_bad",
        name="Bad Rule",
        trigger=Trigger(device="arrival_sensor", event="user_arrived"),
        conditions=[],
        actions=[Action(device="front_door", action="unlock")],
        satisfies_constraints=[],
        explanation="",
    )
    ruleset = RuleSet(rules=[good, bad])
    validator = Validator(base_constraints)
    result = validator.validate_ruleset(ruleset)

    assert "r_good" in result.approved
    assert len(result.rejected) == 1
    assert result.rejected[0].rule_id == "r_bad"
    assert not result.all_approved


# ------------------------------------------------------------------
# Domain vocabulary is the validator's job, not the parser's (BUG-1 / #21)
# ------------------------------------------------------------------

def _crawler_gate_domain(condition_types) -> Domain:
    return Domain(
        id="ttek2_crawler_gate",
        version="0.1",
        trigger_events=frozenset({"crawl_requested"}),
        condition_types=frozenset(condition_types),
        action_kinds=frozenset({"allow"}),
    )


def _host_class_rule() -> Rule:
    return Rule(
        id="r_gate",
        name="Gate by host class",
        trigger=Trigger(device="crawler_gate", event="crawl_requested"),
        conditions=[Condition(type="host_class", parameters={"class": "search_engine"})],
        actions=[Action(device="crawler_gate", action="allow")],
        satisfies_constraints=["x"],
        explanation="Allow known search-engine crawlers.",
    )


def test_validator_accepts_custom_condition_when_domain_includes_it():
    # host_class is in the active domain's vocabulary -> no domain violation.
    validator = Validator(constraints=[], domain=_crawler_gate_domain({"host_class"}))
    result = validator.validate_rule(_host_class_rule())
    assert result.is_valid
    assert result.violations == []


def test_validator_rejects_condition_outside_active_domain():
    # Same rule, but the active domain does NOT declare host_class -> deterministic
    # rejection by the validator (the parser would have accepted it).
    validator = Validator(constraints=[], domain=_crawler_gate_domain({"time_range"}))
    result = validator.validate_rule(_host_class_rule())
    assert result.is_rejected
    reasons = " ".join(v.reason for v in result.violations)
    assert "host_class" in reasons
    assert any(v.constraint_id == Validator.DOMAIN_PSEUDO_CONSTRAINT_ID for v in result.violations)
