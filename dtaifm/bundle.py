"""Audit bundle: portable, replayable record of a single review.

A bundle (.dtaifm-review.json) embeds the constraints, rules, and state used
for a review along with hashes of each input and of the resulting validation
and execution. Given a bundle, anyone can replay the review on a fresh checkout
and confirm — cryptographically — that the same inputs produce the same outputs.

Auditability means you can prove later what was proposed, what was rejected,
what executed, and why.

This module also exposes the public Python API for `review`, `replay`, and
`inspect_bundle`. The CLI is a thin wrapper over these functions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

from dtaifm.audit import (
    extract_proposals,
    format_execution_json,
    format_validation_json,
)
from dtaifm.core.constraint import Constraint
from dtaifm.core.rule import Rule
from dtaifm.core.ruleset import RuleSet
from dtaifm.domains.base import Domain
from dtaifm.domains.registry import UnknownDomainError, get_domain
from dtaifm.io import load_constraints, load_ruleset, load_state
from dtaifm.runtimes.python_runtime import PythonRuntime
from dtaifm.schema import SCHEMA_VERSION
from dtaifm.serialize import ruleset_to_dict
from dtaifm.student.validator import Validator

# Framework version: __version__ is set in dtaifm/__init__.py before this module loads.
from dtaifm import __version__ as FRAMEWORK_VERSION


BUNDLE_VERSION = "0.1"
BundleArg = Union[dict, str, Path]


# ----------------------------------------------------------------------
# Canonical JSON + hashing
# ----------------------------------------------------------------------

def canonical_json(data: Any) -> str:
    """Deterministic JSON serialization — keys sorted, no whitespace.

    Two values that compare equal as Python objects produce the same string.
    Two files with the same logical content (YAML vs JSON, different key order,
    different indentation) parse to equal values and therefore hash identically.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of(data: Any) -> str:
    """SHA-256 of canonical_json(data). Format: ``sha256:<hex>``."""
    return "sha256:" + hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# Replay result
# ----------------------------------------------------------------------

@dataclass
class ReplayResult:
    success: bool
    inputs_intact: bool
    validation_matches: bool
    execution_matches: bool
    domain_version_matches: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------
# Bundle I/O
# ----------------------------------------------------------------------

def save_bundle(bundle: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")


def load_bundle(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_bundle_arg(arg: BundleArg) -> dict:
    if isinstance(arg, dict):
        return arg
    return load_bundle(Path(arg))


# ----------------------------------------------------------------------
# Bundle assembly
# ----------------------------------------------------------------------

def build_bundle(
    *,
    domain: Domain,
    constraints_path: Path,
    rules_path: Path,
    state_path: Path,
    constraints: list[Constraint],
    ruleset: RuleSet,
    state_data: dict,
    validation,
    execution,
    event_device: str,
    event_type: str,
) -> dict:
    constraints_canonical = _constraints_to_canonical(constraints)
    rules_canonical = ruleset_to_dict(ruleset)

    validation_json = format_validation_json(ruleset, validation, constraints)
    execution_json = format_execution_json(execution, event_device, event_type)

    return {
        "bundle_version": BUNDLE_VERSION,
        "framework_version": FRAMEWORK_VERSION,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "domain": {"id": domain.id, "version": domain.version},
        "proposals": extract_proposals(ruleset),
        "inputs": {
            "constraints": {
                "source": str(constraints_path),
                "hash": sha256_of(constraints_canonical),
                "content": constraints_canonical,
            },
            "rules": {
                "source": str(rules_path),
                "hash": sha256_of(rules_canonical),
                "content": rules_canonical,
            },
            "state": {
                "source": str(state_path),
                "hash": sha256_of(state_data),
                "content": state_data,
            },
        },
        "validation": {
            "hash": sha256_of(validation_json),
            "result": validation_json,
        },
        "execution": {
            "hash": sha256_of(execution_json),
            "result": execution_json,
        },
    }


def _constraints_to_canonical(constraints: list[Constraint]) -> list[dict]:
    out: list[dict] = []
    for c in constraints:
        d: dict = {"id": c.id, "description": c.description, "type": c.type}
        d.update(c.parameters)
        out.append(d)
    return out


# ----------------------------------------------------------------------
# Public API: review
# ----------------------------------------------------------------------

def review(
    *,
    constraints_path: Union[str, Path],
    rules_path: Union[str, Path],
    state_path: Union[str, Path],
    domain_id: str = "smart_home",
    bundle_path: Union[str, Path, None] = None,
) -> dict:
    """Run a review (validate + execute) and return the bundle dict.

    If ``bundle_path`` is given, also writes the bundle to that path.
    Replay-determinism guarantee: if the state file lacks a `time` field, the
    framework's wall-clock time is injected into the embedded state so that
    replay reproduces the original execution.
    """
    domain = get_domain(domain_id)
    constraints = load_constraints(Path(constraints_path))
    ruleset = load_ruleset(Path(rules_path))
    state_data = load_state(Path(state_path))
    state_data = _ensure_time(state_data)

    validation, execution, event_device, event_type = _compute_results(
        constraints=constraints, ruleset=ruleset, state_data=state_data, domain=domain,
    )

    bundle = build_bundle(
        domain=domain,
        constraints_path=Path(constraints_path),
        rules_path=Path(rules_path),
        state_path=Path(state_path),
        constraints=constraints,
        ruleset=ruleset,
        state_data=state_data,
        validation=validation,
        execution=execution,
        event_device=event_device,
        event_type=event_type,
    )

    if bundle_path is not None:
        save_bundle(bundle, Path(bundle_path))

    return bundle


# ----------------------------------------------------------------------
# Public API: replay
# ----------------------------------------------------------------------

def replay(bundle_or_path: BundleArg) -> ReplayResult:
    """Recompute the review from a bundle and verify hashes match.

    Detects:
      (1) tampered embedded inputs (input hash != recomputed input hash)
      (2) tampered stored results (stored result hash != recomputed-from-stored-content)
      (3) framework non-determinism or semantic drift (recompute from inputs and
          compare to stored result hash)

    A domain version mismatch is a warning, not a failure: if the recomputed
    results still match (3), the domain change was non-breaking for this bundle.
    """
    bundle = _load_bundle_arg(bundle_or_path)
    issues: list[str] = []
    warnings: list[str] = []

    # (1) Embedded input integrity
    inputs_intact = True
    for kind in ("constraints", "rules", "state"):
        input_block = bundle["inputs"][kind]
        recomputed = sha256_of(input_block["content"])
        if recomputed != input_block["hash"]:
            inputs_intact = False
            issues.append(
                f"Input '{kind}' hash mismatch — bundle says {input_block['hash']}, "
                f"embedded content hashes to {recomputed}: the bundle has been tampered with."
            )

    # (2) Stored result self-consistency
    for kind in ("validation", "execution"):
        stored_hash = bundle[kind]["hash"]
        recomputed_stored = sha256_of(bundle[kind]["result"])
        if recomputed_stored != stored_hash:
            issues.append(
                f"Stored {kind} result has been modified — recorded hash {stored_hash} "
                f"does not match the embedded result ({recomputed_stored})."
            )

    # Resolve domain (cannot proceed past this without it)
    domain_id = bundle["domain"]["id"]
    bundle_domain_version = bundle["domain"]["version"]
    try:
        domain = get_domain(domain_id)
    except UnknownDomainError as exc:
        issues.append(f"Domain '{domain_id}' is not registered ({exc}).")
        return ReplayResult(
            success=False,
            inputs_intact=inputs_intact,
            validation_matches=False,
            execution_matches=False,
            domain_version_matches=False,
            issues=issues,
            warnings=warnings,
        )

    domain_version_matches = (domain.version == bundle_domain_version)
    if not domain_version_matches:
        warnings.append(
            f"Domain '{domain_id}' version differs: bundle was created against "
            f"v{bundle_domain_version}; currently registered v{domain.version}. "
            f"Replay continues; if results still match, the change was non-breaking."
        )

    # (3) Recompute from embedded inputs and compare against stored hashes
    constraints = [Constraint.from_dict(c) for c in bundle["inputs"]["constraints"]["content"]]
    rules_payload = bundle["inputs"]["rules"]["content"]
    ruleset = RuleSet(rules=[Rule.from_dict(r) for r in rules_payload["rules"]], source="bundle")
    state_data = bundle["inputs"]["state"]["content"]

    validation, execution, event_device, event_type = _compute_results(
        constraints=constraints, ruleset=ruleset, state_data=state_data, domain=domain,
    )

    new_validation_json = format_validation_json(ruleset, validation, constraints)
    new_validation_hash = sha256_of(new_validation_json)
    validation_matches = (new_validation_hash == bundle["validation"]["hash"])
    if not validation_matches:
        issues.append(
            f"Replayed validation hash {new_validation_hash} does not match bundle "
            f"({bundle['validation']['hash']}). Either inputs differ from the original "
            f"or the framework/domain semantics have changed."
        )

    new_execution_json = format_execution_json(execution, event_device, event_type)
    new_execution_hash = sha256_of(new_execution_json)
    execution_matches = (new_execution_hash == bundle["execution"]["hash"])
    if not execution_matches:
        issues.append(
            f"Replayed execution hash {new_execution_hash} does not match bundle "
            f"({bundle['execution']['hash']})."
        )

    success = inputs_intact and validation_matches and execution_matches and not issues
    return ReplayResult(
        success=success,
        inputs_intact=inputs_intact,
        validation_matches=validation_matches,
        execution_matches=execution_matches,
        domain_version_matches=domain_version_matches,
        issues=issues,
        warnings=warnings,
    )


# ----------------------------------------------------------------------
# Public API: inspect_bundle
# ----------------------------------------------------------------------

def inspect_bundle(bundle_or_path: BundleArg) -> dict:
    """Return a structured human-readable summary of a bundle. No execution."""
    bundle = _load_bundle_arg(bundle_or_path)
    val_result = bundle["validation"]["result"]
    exec_result = bundle["execution"]["result"]
    return {
        "bundle_version": bundle.get("bundle_version"),
        "framework_version": bundle.get("framework_version"),
        "schema_version": bundle.get("schema_version"),
        "created_at": bundle.get("created_at"),
        "domain": dict(bundle["domain"]),
        "proposals": list(bundle.get("proposals", [])),
        "input_hashes": {
            kind: bundle["inputs"][kind]["hash"]
            for kind in ("constraints", "rules", "state")
        },
        "input_sources": {
            kind: bundle["inputs"][kind].get("source")
            for kind in ("constraints", "rules", "state")
        },
        "validation_summary": {
            "hash": bundle["validation"]["hash"],
            "approved_count": val_result.get("approved_count"),
            "rejected_count": val_result.get("rejected_count"),
            "all_approved": val_result.get("all_approved"),
        },
        "execution_summary": {
            "hash": bundle["execution"]["hash"],
            "event": dict(exec_result["event"]),
            "triggered_rule_ids": list(exec_result.get("triggered_rule_ids", [])),
            "actions_taken": list(exec_result.get("actions_taken", [])),
        },
    }


# ----------------------------------------------------------------------
# Text renderers (used by the CLI for human display)
# ----------------------------------------------------------------------

def format_inspect_text(summary: dict) -> str:
    lines = [
        "dtaifm Bundle Inspect",
        "=" * 50,
        f"Bundle version:    {summary['bundle_version']}",
        f"Framework version: {summary['framework_version']}",
        f"Schema version:    {summary['schema_version']}",
        f"Created at:        {summary['created_at']}",
        "",
        f"Domain: {summary['domain']['id']} v{summary['domain']['version']}",
        "",
        "Proposals:",
    ]
    if not summary["proposals"]:
        lines.append("  (none)")
    for p in summary["proposals"]:
        lines.append(
            f"  - proposal_id={p['proposal_id']}  proposed_by={p['proposed_by'] or '(none)'}  "
            f"rules={len(p['rule_ids'])}"
        )
    lines.append("")
    lines.append("Input hashes (tamper detection):")
    for kind in ("constraints", "rules", "state"):
        src = summary["input_sources"].get(kind) or "(embedded)"
        lines.append(f"  {kind:11}  {summary['input_hashes'][kind]}")
        lines.append(f"              source: {src}")
    lines.append("")
    vs = summary["validation_summary"]
    lines.append(
        f"Validation: {vs['approved_count']} approved, {vs['rejected_count']} rejected  "
        f"(all_approved={vs['all_approved']})"
    )
    lines.append(f"  hash: {vs['hash']}")
    lines.append("")
    es = summary["execution_summary"]
    lines.append(f"Execution event: {es['event']['device']}.{es['event']['type']}")
    lines.append(f"  triggered: {es['triggered_rule_ids']}")
    lines.append(f"  hash: {es['hash']}")
    return "\n".join(lines)


def format_replay_text(result: ReplayResult, bundle_source: str = "") -> str:
    lines = [
        "dtaifm Replay Report",
        "=" * 50,
    ]
    if bundle_source:
        lines.append(f"Bundle: {bundle_source}")
    lines.extend([
        "",
        f"  Inputs intact:           {'OK' if result.inputs_intact else 'FAILED'}",
        f"  Validation matches:      {'OK' if result.validation_matches else 'FAILED'}",
        f"  Execution matches:       {'OK' if result.execution_matches else 'FAILED'}",
        f"  Domain version matches:  {'OK' if result.domain_version_matches else 'DIFFERS'}",
        "",
    ])
    if result.warnings:
        lines.append("Warnings:")
        for w in result.warnings:
            lines.append(f"  ! {w}")
        lines.append("")
    if result.issues:
        lines.append("Issues:")
        for i in result.issues:
            lines.append(f"  X {i}")
        lines.append("")
    lines.append(
        "Result: PASSED — deterministic replay confirmed."
        if result.success
        else "Result: FAILED — bundle could not be reproduced."
    )
    return "\n".join(lines)


# ----------------------------------------------------------------------
# internals
# ----------------------------------------------------------------------

def _ensure_time(state_data: dict) -> dict:
    if "time" in state_data and state_data["time"]:
        return state_data
    return {
        **state_data,
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _compute_results(*, constraints, ruleset, state_data, domain):
    validator = Validator(constraints, domain=domain)
    validation = validator.validate_ruleset(ruleset)
    approved_ids = set(validation.approved)
    approved_rules = [r for r in ruleset if r.id in approved_ids]

    event = state_data["event"]
    runtime_state = {
        "time": _parse_time(state_data.get("time")),
        "mode": state_data.get("mode", "normal"),
        **state_data.get("devices", {}),
    }
    runtime = PythonRuntime(approved_rules, domain=domain)
    execution = runtime.fire(event["device"], event["type"], runtime_state)
    return validation, execution, event["device"], event["type"]


def _parse_time(value) -> datetime:
    if value is None:
        return datetime.now()
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
