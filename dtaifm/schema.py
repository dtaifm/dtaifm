"""Schema versioning and JSON Schema definitions for dtaifm portable artifacts.

The principle: AI output is an artifact, not an action. Every constraints, rules,
and state file declares its schema_version so the deterministic layer can refuse
to interpret a file from an incompatible producer.
"""

from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.1"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"0.1"})


class SchemaVersionError(ValueError):
    """Raised when a file is missing schema_version or declares an unsupported one."""


def check_schema_version(data: Any, path: Path) -> None:
    if not isinstance(data, dict):
        raise SchemaVersionError(f"{path}: top-level value must be a mapping")
    if "schema_version" not in data:
        raise SchemaVersionError(
            f"{path}: missing required 'schema_version' field "
            f"(supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)})"
        )
    version = data["schema_version"]
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaVersionError(
            f"{path}: unsupported schema_version '{version}' "
            f"(supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)})"
        )


# ----------------------------------------------------------------------
# JSON Schemas (Draft 2020-12)
# ----------------------------------------------------------------------

_META = "https://json-schema.org/draft/2020-12/schema"


CONSTRAINTS_SCHEMA: dict = {
    "$schema": _META,
    "title": "dtaifm Constraints File",
    "type": "object",
    "required": ["schema_version", "constraints"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "constraints": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "description", "type"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "description": {"type": "string"},
                    "type": {
                        "enum": [
                            "absolute_prohibition",
                            "mutual_exclusion",
                            "temporal_restriction",
                            "mode_override",
                            "metadata_requirement",
                        ]
                    },
                },
                "additionalProperties": True,
            },
        },
    },
    "additionalProperties": False,
}


RULES_SCHEMA: dict = {
    "$schema": _META,
    "title": "dtaifm Rules File",
    "type": "object",
    "required": ["schema_version", "rules"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "name", "trigger", "actions"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "name": {"type": "string"},
                    "trigger": {
                        "type": "object",
                        "required": ["device", "event"],
                        "properties": {
                            "device": {"type": "string"},
                            "event": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    "conditions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {"type": {"type": "string"}},
                            "additionalProperties": True,
                        },
                    },
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["device", "action"],
                            "properties": {
                                "device": {"type": "string"},
                                "action": {"type": "string"},
                            },
                            "additionalProperties": True,
                        },
                    },
                    "satisfies_constraints": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "explanation": {"type": "string"},
                    # Provenance — populated by the propose command; optional on hand-written rules.
                    "proposed_by": {"type": "string"},
                    "proposal_id": {"type": "string"},
                    "created_at": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
    },
    "additionalProperties": False,
}


STATE_SCHEMA: dict = {
    "$schema": _META,
    "title": "dtaifm State File",
    "type": "object",
    "required": ["schema_version", "event"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "event": {
            "type": "object",
            "required": ["device", "type"],
            "properties": {
                "device": {"type": "string"},
                "type": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "time": {"type": "string"},
        "mode": {"type": "string"},
        "devices": {"type": "object"},
    },
    "additionalProperties": False,
}


SCHEMAS: dict[str, dict] = {
    "constraints": CONSTRAINTS_SCHEMA,
    "rules": RULES_SCHEMA,
    "state": STATE_SCHEMA,
}
