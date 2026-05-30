"""Tests for the strict provider response parser."""

import pytest

from dtaifm.schema import SCHEMA_VERSION
from dtaifm.teacher.parser import (
    KNOWN_CONDITION_TYPES,
    ProviderResponseError,
    parse_provider_payload,
    parse_provider_text,
)


def _valid_rule() -> dict:
    return {
        "id": "r1",
        "name": "Rule One",
        "trigger": {"device": "motion_sensor", "event": "motion_detected"},
        "conditions": [
            {"type": "time_range", "start_hour": 22, "end_hour": 6},
            {"type": "mode_not", "mode": "security"},
        ],
        "actions": [{"device": "hallway_light", "action": "turn_on"}],
        "satisfies_constraints": ["motion_light_hours"],
        "rationale": "Because the constraint requires night-only operation.",
        "explanation": "Night-only motion light.",
    }


def _valid_payload() -> dict:
    return {"schema_version": SCHEMA_VERSION, "rules": [_valid_rule()]}


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------

def test_parser_accepts_valid_payload():
    ruleset = parse_provider_payload(_valid_payload(), source="test")
    assert len(ruleset) == 1
    rule = next(iter(ruleset))
    assert rule.id == "r1"
    assert rule.satisfies_constraints == ["motion_light_hours"]
    assert rule.rationale.startswith("Because")


# ----------------------------------------------------------------------
# Shape / schema_version failures
# ----------------------------------------------------------------------

def test_parser_rejects_non_object_payload():
    with pytest.raises(ProviderResponseError, match="must be a JSON object"):
        parse_provider_payload(["not", "an", "object"], source="test")


def test_parser_rejects_missing_schema_version():
    payload = _valid_payload()
    del payload["schema_version"]
    with pytest.raises(ProviderResponseError, match="missing 'schema_version'"):
        parse_provider_payload(payload, source="test")


def test_parser_rejects_wrong_schema_version():
    payload = _valid_payload()
    payload["schema_version"] = "9.9"
    with pytest.raises(ProviderResponseError, match="schema_version is '9.9'"):
        parse_provider_payload(payload, source="test")


def test_parser_rejects_non_list_rules():
    payload = {"schema_version": SCHEMA_VERSION, "rules": "not a list"}
    with pytest.raises(ProviderResponseError, match="'rules' must be a list"):
        parse_provider_payload(payload, source="test")


# ----------------------------------------------------------------------
# Required field failures
# ----------------------------------------------------------------------

@pytest.mark.parametrize("missing_field", [
    "id", "name", "trigger", "actions", "satisfies_constraints", "rationale",
])
def test_parser_rejects_missing_required_rule_field(missing_field):
    rule = _valid_rule()
    del rule[missing_field]
    payload = {"schema_version": SCHEMA_VERSION, "rules": [rule]}
    with pytest.raises(ProviderResponseError, match=f"missing required field '{missing_field}'"):
        parse_provider_payload(payload, source="test")


def test_parser_rejects_empty_satisfies_constraints():
    rule = _valid_rule()
    rule["satisfies_constraints"] = []
    payload = {"schema_version": SCHEMA_VERSION, "rules": [rule]}
    with pytest.raises(ProviderResponseError, match="non-empty list"):
        parse_provider_payload(payload, source="test")


def test_parser_rejects_empty_rationale():
    rule = _valid_rule()
    rule["rationale"] = "   "
    payload = {"schema_version": SCHEMA_VERSION, "rules": [rule]}
    with pytest.raises(ProviderResponseError, match="rationale.*non-empty"):
        parse_provider_payload(payload, source="test")


# ----------------------------------------------------------------------
# Trigger / actions / conditions structural failures
# ----------------------------------------------------------------------

def test_parser_rejects_trigger_missing_device():
    rule = _valid_rule()
    rule["trigger"] = {"event": "motion_detected"}
    payload = {"schema_version": SCHEMA_VERSION, "rules": [rule]}
    with pytest.raises(ProviderResponseError, match="'trigger' must be an object with 'device' and 'event'"):
        parse_provider_payload(payload, source="test")


def test_parser_rejects_empty_actions_list():
    rule = _valid_rule()
    rule["actions"] = []
    payload = {"schema_version": SCHEMA_VERSION, "rules": [rule]}
    with pytest.raises(ProviderResponseError, match="'actions' must be a non-empty list"):
        parse_provider_payload(payload, source="test")


def test_parser_rejects_action_missing_action_key():
    rule = _valid_rule()
    rule["actions"] = [{"device": "light"}]
    payload = {"schema_version": SCHEMA_VERSION, "rules": [rule]}
    with pytest.raises(ProviderResponseError, match="must have 'device' and 'action'"):
        parse_provider_payload(payload, source="test")


def test_parser_accepts_arbitrary_condition_type():
    # Domain-agnostic vocabulary: a custom domain's condition type (e.g. host_class
    # for ttek2_crawler_gate) must parse. Whether it is legal for the active domain
    # is the Validator's job, not the parser's. (BUG-1 / #21)
    rule = _valid_rule()
    rule["conditions"] = [{"type": "host_class", "class": "search_engine"}]
    payload = {"schema_version": SCHEMA_VERSION, "rules": [rule]}
    rs = parse_provider_payload(payload, source="test")
    assert [c.type for c in next(iter(rs)).conditions] == ["host_class"]


def test_parser_does_not_hardcode_trigger_or_action_vocabulary():
    # Triggers and actions are shape-only too: a custom domain's trigger event and
    # action kind must parse. Domain vocabulary is enforced by the Validator. (#21)
    rule = _valid_rule()
    rule["trigger"] = {"device": "crawler_gate", "event": "crawl_requested"}
    rule["actions"] = [{"device": "crawler_gate", "action": "allow_with_rate_limit"}]
    payload = {"schema_version": SCHEMA_VERSION, "rules": [rule]}
    parsed = next(iter(parse_provider_payload(payload, source="test")))
    assert parsed.trigger.event == "crawl_requested"
    assert parsed.actions[0].action == "allow_with_rate_limit"


def test_parser_accepts_all_known_condition_types():
    rule = _valid_rule()
    rule["conditions"] = [
        {"type": "time_range", "start_hour": 1, "end_hour": 2},
        {"type": "mode_not", "mode": "x"},
        {"type": "mode_is", "mode": "y"},
        {"type": "device_state", "device": "d", "state": "off"},
    ]
    payload = {"schema_version": SCHEMA_VERSION, "rules": [rule]}
    rs = parse_provider_payload(payload, source="test")
    parsed = next(iter(rs))
    assert {c.type for c in parsed.conditions} == KNOWN_CONDITION_TYPES


def test_parser_includes_rule_index_in_error_location():
    rule_a = _valid_rule()
    rule_b = _valid_rule()
    rule_b["id"] = "r2"
    del rule_b["rationale"]
    payload = {"schema_version": SCHEMA_VERSION, "rules": [rule_a, rule_b]}
    with pytest.raises(ProviderResponseError, match=r"rule\[1\] missing required field 'rationale'"):
        parse_provider_payload(payload, source="test")


# ----------------------------------------------------------------------
# Text extraction (narration outside the JSON is tolerated)
# ----------------------------------------------------------------------

def test_parse_provider_text_extracts_fenced_json():
    text = (
        "Sure, here are my proposed rules:\n\n"
        "```json\n"
        '{"schema_version": "0.1", "rules": []}\n'
        "```\n\n"
        "Let me know if you need adjustments."
    )
    rs = parse_provider_text(text, source="test")
    assert len(rs) == 0


def test_parse_provider_text_extracts_bare_json():
    text = (
        "Sure, here are my proposed rules: "
        '{"schema_version": "0.1", "rules": []} '
        "Let me know if you need adjustments."
    )
    rs = parse_provider_text(text, source="test")
    assert len(rs) == 0


def test_parse_provider_text_rejects_when_no_json_present():
    with pytest.raises(ProviderResponseError, match="contains no JSON object"):
        parse_provider_text("I refuse to comply.", source="test")
