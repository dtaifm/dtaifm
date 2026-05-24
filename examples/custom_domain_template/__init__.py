"""Custom domain template — a starting point for your own dtaifm domain pack.

Copy this directory, rename `SUPPORT_DOMAIN` to your domain, and adapt the
constraints.yaml / rules.yaml / state.json fixtures alongside it.

This template defines a tiny ``support`` domain with three trigger events,
three action verbs, and one domain-specific constraint evaluator
(``escalation_requires_assignment``). It does NOT auto-register the domain into
the global registry — see the README for how to do that so the dtaifm CLI can
target it via ``--domain support``.

The architectural contract you inherit by following this template:

- The runtime never runs your action verbs unless the validator approves the
  rule. Your evaluator helps the validator make that decision.
- The framework never trusts your teacher's output — only validator-approved
  rules reach execution.
- Your domain's vocabulary (triggers / conditions / actions) is enforced by
  both the validator and the runtime.
"""

from dtaifm.core.constraint import Constraint
from dtaifm.core.result import ConstraintViolation
from dtaifm.core.rule import Rule
from dtaifm.domains.base import Domain


def escalation_requires_assignment(rule: Rule, constraint: Constraint) -> ConstraintViolation | None:
    """A rule that performs ``escalate`` must also perform ``assign_engineer``.

    This is the smallest possible custom evaluator: it inspects a rule's
    actions and returns a ConstraintViolation if the pairing is missing.
    """
    actions = {a.action for a in rule.actions}
    if "escalate" in actions and "assign_engineer" not in actions:
        return ConstraintViolation(
            constraint_id=constraint.id,
            constraint_description=constraint.description,
            reason=(
                f"Rule '{rule.id}' escalates without an accompanying "
                f"'assign_engineer' action."
            ),
        )
    return None


SUPPORT_DOMAIN = Domain(
    id="support",
    version="0.1",
    description="Customer support ticket automation — minimal template.",
    trigger_events=frozenset({
        "ticket_opened",
        "ticket_updated",
        "ticket_escalated",
    }),
    condition_types=frozenset({
        "time_range",
        "mode_not",
        "mode_is",
        "device_state",
    }),
    action_kinds=frozenset({
        "notify_team",
        "assign_engineer",
        "escalate",
    }),
    extra_constraint_evaluators={
        "escalation_requires_assignment": escalation_requires_assignment,
    },
)
