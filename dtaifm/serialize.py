"""Serialize core types back to plain dicts for YAML/JSON writing.

Round-trips: load_ruleset(path) -> RuleSet -> ruleset_to_dict(rs) -> file -> load again.
"""

from dtaifm.core.rule import Rule
from dtaifm.core.ruleset import RuleSet
from dtaifm.schema import SCHEMA_VERSION


def rule_to_dict(rule: Rule) -> dict:
    payload: dict = {
        "id": rule.id,
        "name": rule.name,
        "trigger": {"device": rule.trigger.device, "event": rule.trigger.event},
        "conditions": [
            {"type": c.type, **c.parameters} for c in rule.conditions
        ],
        "actions": [
            {"device": a.device, "action": a.action, **a.parameters} for a in rule.actions
        ],
        "satisfies_constraints": list(rule.satisfies_constraints),
        "explanation": rule.explanation,
    }
    # Provenance fields are written only when populated, so hand-written rules stay clean.
    if rule.proposed_by:
        payload["proposed_by"] = rule.proposed_by
    if rule.proposal_id:
        payload["proposal_id"] = rule.proposal_id
    if rule.created_at:
        payload["created_at"] = rule.created_at
    if rule.rationale:
        payload["rationale"] = rule.rationale
    return payload


def ruleset_to_dict(ruleset: RuleSet) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "rules": [rule_to_dict(r) for r in ruleset],
    }
