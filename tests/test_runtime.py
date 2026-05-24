from datetime import datetime
from dtaifm.core.rule import Action, Condition, Rule, Trigger
from dtaifm.runtimes.python_runtime import PythonRuntime


def night_light_rule() -> Rule:
    return Rule(
        id="r_night_light",
        name="Night Light",
        trigger=Trigger(device="motion_sensor", event="motion_detected"),
        conditions=[
            Condition(type="time_range", parameters={"start_hour": 22, "end_hour": 6}),
            Condition(type="mode_not", parameters={"mode": "security"}),
        ],
        actions=[Action(device="hallway_light", action="turn_on", parameters={"duration": 300})],
        satisfies_constraints=["motion_light_hours", "security_override"],
        explanation="Night light, blocked in security mode.",
    )


# ------------------------------------------------------------------
# Time-range conditions
# ------------------------------------------------------------------

def test_rule_fires_during_night_hours():
    runtime = PythonRuntime([night_light_rule()])
    state = {"time": datetime(2024, 1, 1, 23, 0), "mode": "normal"}
    result = runtime.fire("motion_sensor", "motion_detected", state)
    assert "r_night_light" in result.triggered_rule_ids


def test_rule_fires_in_early_morning_night_hours():
    runtime = PythonRuntime([night_light_rule()])
    state = {"time": datetime(2024, 1, 1, 3, 0), "mode": "normal"}
    result = runtime.fire("motion_sensor", "motion_detected", state)
    assert "r_night_light" in result.triggered_rule_ids


def test_rule_does_not_fire_outside_night_hours():
    runtime = PythonRuntime([night_light_rule()])
    state = {"time": datetime(2024, 1, 1, 14, 0), "mode": "normal"}
    result = runtime.fire("motion_sensor", "motion_detected", state)
    assert "r_night_light" not in result.triggered_rule_ids


def test_rule_does_not_fire_exactly_at_end_of_night_hours():
    # end_hour=6 means the window closes at 06:00 exactly
    runtime = PythonRuntime([night_light_rule()])
    state = {"time": datetime(2024, 1, 1, 6, 0), "mode": "normal"}
    result = runtime.fire("motion_sensor", "motion_detected", state)
    assert "r_night_light" not in result.triggered_rule_ids


# ------------------------------------------------------------------
# Mode conditions
# ------------------------------------------------------------------

def test_rule_blocked_in_security_mode():
    runtime = PythonRuntime([night_light_rule()])
    state = {"time": datetime(2024, 1, 1, 23, 0), "mode": "security"}
    result = runtime.fire("motion_sensor", "motion_detected", state)
    assert "r_night_light" not in result.triggered_rule_ids


# ------------------------------------------------------------------
# Device-state conditions
# ------------------------------------------------------------------

def test_heating_rule_blocked_when_ac_on():
    rule = Rule(
        id="r_heating",
        name="Heating Rule",
        trigger=Trigger(device="thermostat", event="temperature_below_threshold"),
        conditions=[
            Condition(type="device_state", parameters={"device": "ac", "state": "off"}),
            Condition(type="mode_not", parameters={"mode": "security"}),
        ],
        actions=[Action(device="heating", action="turn_on")],
        satisfies_constraints=["no_hvac_conflict", "security_override"],
        explanation="Safe heating rule.",
    )
    runtime = PythonRuntime([rule])
    state = {"time": datetime(2024, 1, 1, 20, 0), "mode": "normal", "ac": "turn_on"}
    result = runtime.fire("thermostat", "temperature_below_threshold", state)
    assert "r_heating" not in result.triggered_rule_ids


def test_heating_rule_fires_when_ac_off():
    rule = Rule(
        id="r_heating",
        name="Heating Rule",
        trigger=Trigger(device="thermostat", event="temperature_below_threshold"),
        conditions=[
            Condition(type="device_state", parameters={"device": "ac", "state": "off"}),
            Condition(type="mode_not", parameters={"mode": "security"}),
        ],
        actions=[Action(device="heating", action="turn_on")],
        satisfies_constraints=["no_hvac_conflict", "security_override"],
        explanation="Safe heating rule.",
    )
    runtime = PythonRuntime([rule])
    state = {"time": datetime(2024, 1, 1, 20, 0), "mode": "normal", "ac": "off"}
    result = runtime.fire("thermostat", "temperature_below_threshold", state)
    assert "r_heating" in result.triggered_rule_ids


# ------------------------------------------------------------------
# Action output and state delta
# ------------------------------------------------------------------

def test_execution_result_contains_action_details():
    runtime = PythonRuntime([night_light_rule()])
    state = {"time": datetime(2024, 1, 1, 23, 0), "mode": "normal"}
    result = runtime.fire("motion_sensor", "motion_detected", state)
    assert len(result.actions_taken) == 1
    action = result.actions_taken[0]
    assert action["device"] == "hallway_light"
    assert action["action"] == "turn_on"
    assert result.state_delta["hallway_light"] == "turn_on"


# ------------------------------------------------------------------
# Event matching
# ------------------------------------------------------------------

def test_wrong_event_type_does_not_trigger():
    runtime = PythonRuntime([night_light_rule()])
    state = {"time": datetime(2024, 1, 1, 23, 0), "mode": "normal"}
    result = runtime.fire("motion_sensor", "motion_cleared", state)
    assert result.triggered_rule_ids == []


def test_wrong_device_does_not_trigger():
    runtime = PythonRuntime([night_light_rule()])
    state = {"time": datetime(2024, 1, 1, 23, 0), "mode": "normal"}
    result = runtime.fire("door_sensor", "motion_detected", state)
    assert result.triggered_rule_ids == []
