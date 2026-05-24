"""File loaders and writers for constraints, rule sets, and runtime state."""

import json
from pathlib import Path
from typing import Any

import yaml

from dtaifm.core.constraint import Constraint
from dtaifm.core.rule import Rule
from dtaifm.core.ruleset import RuleSet
from dtaifm.schema import check_schema_version
from dtaifm.serialize import ruleset_to_dict


def _read(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"{path}: invalid YAML - {exc}") from exc
    if suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON - {exc}") from exc
    raise ValueError(f"Unsupported file extension '{path.suffix}' (expected .yaml/.yml/.json)")


def load_constraints(path: Path) -> list[Constraint]:
    data = _read(path)
    check_schema_version(data, path)
    if "constraints" not in data:
        raise ValueError(f"{path}: top-level 'constraints' key is required")
    if not isinstance(data["constraints"], list):
        raise ValueError(f"{path}: 'constraints' must be a list")
    try:
        return [Constraint.from_dict(c) for c in data["constraints"]]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{path}: malformed constraint - {exc}") from exc


def load_ruleset(path: Path) -> RuleSet:
    data = _read(path)
    check_schema_version(data, path)
    if "rules" not in data:
        raise ValueError(f"{path}: top-level 'rules' key is required")
    if not isinstance(data["rules"], list):
        raise ValueError(f"{path}: 'rules' must be a list")
    try:
        rules = [Rule.from_dict(r) for r in data["rules"]]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{path}: malformed rule - {exc}") from exc
    return RuleSet(rules=rules, source=str(path))


def load_state(path: Path) -> dict:
    data = _read(path)
    check_schema_version(data, path)
    if "event" not in data or not isinstance(data["event"], dict):
        raise ValueError(f"{path}: state must contain an 'event' object")
    event = data["event"]
    if "device" not in event or "type" not in event:
        raise ValueError(f"{path}: 'event' must include 'device' and 'type'")
    return data


def write_ruleset(ruleset: RuleSet, path: Path) -> None:
    """Write a RuleSet to YAML or JSON, choosing the format by file extension."""
    payload = ruleset_to_dict(ruleset)
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
    elif suffix == ".json":
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported output extension '{path.suffix}' (expected .yaml/.yml/.json)")
