"""Audit report formatting for validation, execution, and combined review results.

Text formatters are for humans; JSON formatters are for tests, CI, and downstream tooling.
Both convey the same facts: no information is hidden in either form.
"""

from dtaifm.core.constraint import Constraint
from dtaifm.core.result import ExecutionResult, RuleSetValidationResult
from dtaifm.core.ruleset import RuleSet
from dtaifm.schema import SCHEMA_VERSION


# ----------------------------------------------------------------------
# Validation report
# ----------------------------------------------------------------------

def format_validation_text(
    ruleset: RuleSet,
    validation: RuleSetValidationResult,
    constraints: list[Constraint],
) -> str:
    lines = [
        "Validation Report",
        "=" * 50,
        f"Constraints: {len(constraints)}",
        f"Rules:       {len(ruleset)}",
        f"Approved:    {len(validation.approved)}",
        f"Rejected:    {len(validation.rejected)}",
        "",
    ]
    approved_ids = set(validation.approved)
    rejected_by_id = {vr.rule_id: vr for vr in validation.rejected}
    for rule in ruleset:
        if rule.id in approved_ids:
            lines.append(f"  APPROVED  [{rule.id}]  {rule.name}")
        else:
            vr = rejected_by_id[rule.id]
            lines.append(f"  REJECTED  [{rule.id}]  {rule.name}")
            for v in vr.violations:
                lines.append(f"            ! [{v.constraint_id}] {v.reason}")
    return "\n".join(lines)


def format_validation_json(
    ruleset: RuleSet,
    validation: RuleSetValidationResult,
    constraints: list[Constraint],
) -> dict:
    approved_ids = set(validation.approved)
    rejected_by_id = {vr.rule_id: vr for vr in validation.rejected}
    rules_payload = []
    for rule in ruleset:
        if rule.id in approved_ids:
            rules_payload.append({
                "id": rule.id,
                "name": rule.name,
                "status": "approved",
                "violations": [],
            })
        else:
            vr = rejected_by_id[rule.id]
            rules_payload.append({
                "id": rule.id,
                "name": rule.name,
                "status": "rejected",
                "violations": [
                    {
                        "constraint_id": v.constraint_id,
                        "constraint_description": v.constraint_description,
                        "reason": v.reason,
                    }
                    for v in vr.violations
                ],
            })
    return {
        "constraint_count": len(constraints),
        "rule_count": len(ruleset),
        "approved_count": len(validation.approved),
        "rejected_count": len(validation.rejected),
        "all_approved": validation.all_approved,
        "rules": rules_payload,
    }


# ----------------------------------------------------------------------
# Execution report
# ----------------------------------------------------------------------

def format_execution_text(
    execution: ExecutionResult,
    event_device: str,
    event_type: str,
) -> str:
    lines = [
        "Execution Trace",
        "=" * 50,
        f"Event:        {event_device}.{event_type}",
        f"Rules fired:  {len(execution.triggered_rule_ids)}",
        "",
    ]
    for t in execution.trace:
        marker = "FIRED   " if t.fired else "SKIPPED "
        lines.append(f"  {marker} [{t.rule_id}]  {t.reason}")
        for cond in t.conditions_evaluated:
            status = "ok" if cond.passed else "FAIL"
            lines.append(f"             - {cond.type} {dict(cond.parameters)} -> {status}")

    if execution.actions_taken:
        lines.append("")
        lines.append("Actions:")
        for action in execution.actions_taken:
            params = action.get("parameters") or {}
            extra = f"  {params}" if params else ""
            lines.append(
                f"  -> [{action['rule_id']}] {action['device']}: {action['action']}{extra}"
            )
    return "\n".join(lines)


def format_execution_json(
    execution: ExecutionResult,
    event_device: str,
    event_type: str,
) -> dict:
    return {
        "event": {"device": event_device, "type": event_type},
        "triggered_rule_ids": list(execution.triggered_rule_ids),
        "skipped_rule_ids": list(execution.skipped_rules),
        "actions_taken": list(execution.actions_taken),
        "state_delta": dict(execution.state_delta),
        "trace": [
            {
                "rule_id": t.rule_id,
                "matched_trigger": t.matched_trigger,
                "fired": t.fired,
                "reason": t.reason,
                "conditions_evaluated": [
                    {"type": c.type, "parameters": dict(c.parameters), "passed": c.passed}
                    for c in t.conditions_evaluated
                ],
            }
            for t in execution.trace
        ],
    }


# ----------------------------------------------------------------------
# Review (combined) report
# ----------------------------------------------------------------------

def extract_proposals(ruleset: RuleSet) -> list[dict]:
    """Group rules by proposal_id, emitting one provenance entry per distinct proposal.

    Rules without a proposal_id are grouped under the literal '<unknown>'.
    """
    by_id: dict[str, dict] = {}
    for rule in ruleset:
        pid = rule.proposal_id or "<unknown>"
        if pid not in by_id:
            by_id[pid] = {
                "proposal_id": pid,
                "proposed_by": rule.proposed_by,
                "created_at": rule.created_at,
                "rule_ids": [],
            }
        by_id[pid]["rule_ids"].append(rule.id)
    return list(by_id.values())


def format_review_json(
    ruleset: RuleSet,
    constraints: list[Constraint],
    validation: RuleSetValidationResult,
    execution: ExecutionResult,
    event_device: str,
    event_type: str,
    state: dict,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "proposals": extract_proposals(ruleset),
        "state": {
            "event": {"device": event_device, "type": event_type},
            "time": state.get("time"),
            "mode": state.get("mode", "normal"),
            "devices": state.get("devices", {}),
        },
        "validation": format_validation_json(ruleset, validation, constraints),
        "execution": format_execution_json(execution, event_device, event_type),
    }


def format_review_text(
    ruleset: RuleSet,
    constraints: list[Constraint],
    validation: RuleSetValidationResult,
    execution: ExecutionResult,
    event_device: str,
    event_type: str,
    state: dict,
) -> str:
    lines = [
        "dtaifm Review Report",
        "=" * 50,
        f"Schema version: {SCHEMA_VERSION}",
        "",
        "Proposals:",
    ]
    proposals = extract_proposals(ruleset)
    if not proposals:
        lines.append("  (none)")
    for p in proposals:
        lines.append(
            f"  - proposal_id={p['proposal_id']}  proposed_by={p['proposed_by'] or '(none)'}  "
            f"created_at={p['created_at'] or '(none)'}  rules={len(p['rule_ids'])}"
        )
        for rid in p["rule_ids"]:
            lines.append(f"      * {rid}")
    lines.append("")
    lines.append("State:")
    lines.append(f"  event: {event_device}.{event_type}")
    if state.get("time"):
        lines.append(f"  time:  {state.get('time')}")
    lines.append(f"  mode:  {state.get('mode', 'normal')}")
    lines.append("")
    lines.append(format_validation_text(ruleset, validation, constraints))
    lines.append("")
    lines.append(format_execution_text(execution, event_device, event_type))
    return "\n".join(lines)
