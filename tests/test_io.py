import json
from pathlib import Path

import pytest

from dtaifm.io import load_constraints, load_ruleset, load_state
from dtaifm.core.constraint import ConstraintType


EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "smart_rules"


def test_load_constraints_yaml():
    constraints = load_constraints(EXAMPLES / "constraints.yaml")
    assert len(constraints) == 5
    ids = {c.id for c in constraints}
    assert {"no_auto_unlock", "no_hvac_conflict", "motion_light_hours", "security_override", "rule_must_explain"} == ids


def test_load_ruleset_yaml():
    ruleset = load_ruleset(EXAMPLES / "rules.yaml")
    assert len(ruleset) == 3
    ids = {r.id for r in ruleset}
    assert {"r_motion_night_light", "r_auto_unlock_door", "r_heating_cold"} == ids


def test_load_ruleset_preserves_satisfies_constraints():
    ruleset = load_ruleset(EXAMPLES / "rules.yaml")
    by_id = {r.id: r for r in ruleset}
    assert by_id["r_motion_night_light"].satisfies_constraints == [
        "motion_light_hours",
        "security_override",
    ]
    assert by_id["r_auto_unlock_door"].satisfies_constraints == []


def test_load_state_json():
    state = load_state(EXAMPLES / "state.json")
    assert state["event"] == {"device": "motion_sensor", "type": "motion_detected"}
    assert state["mode"] == "normal"
    assert state["devices"]["ac"] == "off"


def test_load_ruleset_from_json(tmp_path):
    payload = {
        "schema_version": "0.1",
        "rules": [
            {
                "id": "r_x",
                "name": "X",
                "trigger": {"device": "d", "event": "e"},
                "conditions": [],
                "actions": [{"device": "x", "action": "turn_on"}],
                "satisfies_constraints": ["c"],
                "explanation": "",
            }
        ],
    }
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(payload))
    ruleset = load_ruleset(p)
    assert len(ruleset) == 1
    assert next(iter(ruleset)).id == "r_x"


def test_unsupported_extension(tmp_path):
    p = tmp_path / "rules.txt"
    p.write_text("nothing")
    with pytest.raises(ValueError, match="Unsupported file extension"):
        load_ruleset(p)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_ruleset(tmp_path / "does_not_exist.yaml")


def test_malformed_yaml_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("rules: [unterminated")
    with pytest.raises(ValueError, match="invalid YAML"):
        load_ruleset(p)


def test_malformed_json_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_state(p)


def test_missing_rules_key_raises(tmp_path):
    p = tmp_path / "no_rules.yaml"
    p.write_text('schema_version: "0.1"\nconstraints: []\n')
    with pytest.raises(ValueError, match="'rules' key is required"):
        load_ruleset(p)


def test_state_without_event_raises(tmp_path):
    p = tmp_path / "no_event.json"
    p.write_text(json.dumps({"schema_version": "0.1", "mode": "normal"}))
    with pytest.raises(ValueError, match="'event' object"):
        load_state(p)


def test_state_event_missing_fields_raises(tmp_path):
    p = tmp_path / "bad_event.json"
    p.write_text(json.dumps({"schema_version": "0.1", "event": {"device": "x"}}))
    with pytest.raises(ValueError, match="'device' and 'type'"):
        load_state(p)


def test_constraint_types_round_trip():
    constraints = load_constraints(EXAMPLES / "constraints.yaml")
    by_id = {c.id: c for c in constraints}
    assert by_id["no_auto_unlock"].type == ConstraintType.ABSOLUTE_PROHIBITION
    assert by_id["no_hvac_conflict"].type == ConstraintType.MUTUAL_EXCLUSION
    assert by_id["motion_light_hours"].type == ConstraintType.TEMPORAL_RESTRICTION
    assert by_id["security_override"].type == ConstraintType.MODE_OVERRIDE
    assert by_id["rule_must_explain"].type == ConstraintType.METADATA_REQUIREMENT
