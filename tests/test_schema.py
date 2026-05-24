"""Tests for schema versioning + JSON Schema artifacts."""

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from dtaifm.cli import main
from dtaifm.io import load_constraints, load_ruleset, load_state
from dtaifm.schema import (
    CONSTRAINTS_SCHEMA,
    RULES_SCHEMA,
    SCHEMA_VERSION,
    SCHEMAS,
    STATE_SCHEMA,
    SchemaVersionError,
    check_schema_version,
)


EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "smart_rules"


# ----------------------------------------------------------------------
# Schema constants
# ----------------------------------------------------------------------

def test_schema_version_is_pinned():
    assert SCHEMA_VERSION == "0.1"


@pytest.mark.parametrize("schema", [CONSTRAINTS_SCHEMA, RULES_SCHEMA, STATE_SCHEMA])
def test_schemas_are_valid_json_schema(schema):
    jsonschema.Draft202012Validator.check_schema(schema)


def test_constraints_example_validates_against_schema():
    data = yaml.safe_load((EXAMPLES / "constraints.yaml").read_text(encoding="utf-8"))
    jsonschema.validate(data, CONSTRAINTS_SCHEMA)


def test_rules_example_validates_against_schema():
    data = yaml.safe_load((EXAMPLES / "rules.yaml").read_text(encoding="utf-8"))
    jsonschema.validate(data, RULES_SCHEMA)


def test_state_example_validates_against_schema():
    data = json.loads((EXAMPLES / "state.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, STATE_SCHEMA)


def test_constraints_missing_version_fails_schema():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"constraints": []}, CONSTRAINTS_SCHEMA)


def test_constraints_wrong_version_fails_schema():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"schema_version": "9.9", "constraints": []}, CONSTRAINTS_SCHEMA)


# ----------------------------------------------------------------------
# Loader version check
# ----------------------------------------------------------------------

def test_loader_rejects_file_missing_schema_version(tmp_path):
    p = tmp_path / "constraints.yaml"
    p.write_text("constraints: []\n")
    with pytest.raises(SchemaVersionError, match="missing required 'schema_version'"):
        load_constraints(p)


def test_loader_rejects_unsupported_schema_version(tmp_path):
    p = tmp_path / "constraints.yaml"
    p.write_text('schema_version: "9.9"\nconstraints: []\n')
    with pytest.raises(SchemaVersionError, match="unsupported schema_version '9.9'"):
        load_constraints(p)


def test_loader_rejects_ruleset_missing_schema_version(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text("rules: []\n")
    with pytest.raises(SchemaVersionError):
        load_ruleset(p)


def test_loader_rejects_state_missing_schema_version(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"event": {"device": "d", "type": "e"}}))
    with pytest.raises(SchemaVersionError):
        load_state(p)


def test_check_schema_version_accepts_supported():
    check_schema_version({"schema_version": SCHEMA_VERSION}, Path("dummy"))


# ----------------------------------------------------------------------
# `dtaifm schema` CLI
# ----------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["constraints", "rules", "state"])
def test_schema_command_emits_valid_json_schema(kind, capsys):
    exit_code = main(["schema", kind])
    assert exit_code == 0
    out = capsys.readouterr().out
    schema = json.loads(out)
    assert schema["$schema"].startswith("https://json-schema.org/")
    jsonschema.Draft202012Validator.check_schema(schema)


def test_schema_command_kind_matches_module_constant(capsys):
    main(["schema", "rules"])
    out = capsys.readouterr().out
    assert json.loads(out) == SCHEMAS["rules"]


def test_schema_command_rejects_unknown_kind(capsys):
    # argparse rejects invalid choice with exit 2 and message on stderr
    with pytest.raises(SystemExit) as exc:
        main(["schema", "nonsense"])
    assert exc.value.code == 2


def test_validate_cli_reports_clear_error_on_unsupported_version(tmp_path, capsys):
    bad = tmp_path / "rules.yaml"
    bad.write_text('schema_version: "9.9"\nrules: []\n')
    exit_code = main(["validate", str(EXAMPLES / "constraints.yaml"), str(bad)])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "unsupported schema_version" in err
