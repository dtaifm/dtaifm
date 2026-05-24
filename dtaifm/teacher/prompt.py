"""Shared prompt template used by all teachers in v0.1.

A future teacher can override its own `render_prompt` if it needs a different
format, but the shared template keeps `dtaifm prompt --teacher <any>` predictable.

When a Domain is attached to the request, the template renders an explicit
DOMAIN VOCABULARY section so the teacher knows what triggers/conditions/actions
are accepted. When a TeacherFeedback is attached, the template additionally
renders a REVISION REQUESTED section with the previous rules and the validator's
exact violation reasons — section markers are stable and grep-able.
"""

from dtaifm.core.constraint import Constraint
from dtaifm.domains.base import Domain
from dtaifm.teacher.contract import PromptContext, TeacherRequest
from dtaifm.teacher.feedback import TeacherFeedback


PROMPT_TEMPLATE = """\
You are a Teacher proposing candidate automation rules for a {domain_id} (v{domain_version}) system.

Your output is a portable ARTIFACT, not an action. A deterministic Validator will
review your proposal against the constraints below and REJECT any rule that violates
them. Rejected rules are never executed; they are only reported back to the human
reviewer for audit.

Schema version: {schema_version}

== DOMAIN VOCABULARY (every rule MUST use only items from these lists) ==

{vocabulary_section}

== CONSTRAINTS (every rule you propose will be checked against ALL of these) ==

{constraints_block}

== CONTEXT ==

{context_block}
{revision_section}
== REQUIREMENTS for every rule ==

- `id`: unique short identifier (e.g. "r_motion_light")
- `name`: short human-readable name
- `trigger`: object with `device` (string) and `event` (string from allowed list)
- `conditions`: list of objects with `type` (from allowed list) plus type-specific parameters
- `actions`: NON-EMPTY list of objects with `device` and `action` (from allowed list)
- `satisfies_constraints`: NON-EMPTY list of constraint IDs your rule honors
    (rules with an empty list are auto-rejected by the rule_must_explain constraint)
- `rationale`: REQUIRED short paragraph explaining WHY you chose this rule.
    This is your audit trail — write what a human reviewer needs to evaluate
    your judgment. Empty rationale will be rejected at parse time.
- `explanation`: short description of WHAT the rule does

Known condition type parameters:
- time_range:   parameters `start_hour` (0-23), `end_hour` (0-23). Supports
                overnight ranges (e.g. start=22, end=6 means 22:00-06:00).
- mode_not:     parameter `mode` (string). Passes when current mode != mode.
- mode_is:      parameter `mode` (string). Passes when current mode == mode.
- device_state: parameters `device` (string), `state` (string). Passes when
                state[device] == state.

Return the RuleSet via the submit_ruleset tool. Do NOT include narration outside
the tool call.
"""


def render_teacher_prompt(request: TeacherRequest) -> str:
    domain = request.domain
    if domain is not None:
        domain_id = domain.id
        domain_version = domain.version
        vocabulary_section = _format_vocabulary(domain)
    else:
        domain_id = request.context.domain or "general"
        domain_version = "unspecified"
        vocabulary_section = (
            "(no domain attached to this request — ask your platform team for the "
            "allowed trigger events, condition types, and action kinds)"
        )

    return PROMPT_TEMPLATE.format(
        domain_id=domain_id,
        domain_version=domain_version,
        schema_version=request.schema_version,
        vocabulary_section=vocabulary_section,
        constraints_block=_format_constraints(request.constraints),
        context_block=_format_context(request.context),
        revision_section=_format_revision_section(request.feedback, request.previous_rules),
    )


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _format_vocabulary(domain: Domain) -> str:
    parts = [
        "Allowed trigger events:",
        _bullet_list(sorted(domain.trigger_events)),
        "",
        "Allowed condition types:",
        _bullet_list(sorted(domain.condition_types)),
        "",
        "Allowed action kinds:",
        _bullet_list(sorted(domain.action_kinds)),
    ]
    return "\n".join(parts)


def _bullet_list(items: list[str]) -> str:
    if not items:
        return "  (none)"
    return "\n".join(f"  - {item}" for item in items)


def _format_constraints(constraints: list[Constraint]) -> str:
    blocks: list[str] = []
    for c in constraints:
        lines = [
            f"- [{c.id}]  type: {c.type}",
            f"    \"{c.description}\"",
        ]
        for key, value in c.parameters.items():
            lines.append(f"    {key}: {value}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks) if blocks else "(no constraints)"


def _format_context(context: PromptContext) -> str:
    lines = [f"domain: {context.domain or 'general'}"]
    for key, value in context.metadata.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _format_revision_section(
    feedback: TeacherFeedback | None,
    previous_rules: list[dict] | None,
) -> str:
    if feedback is None and not previous_rules:
        return ""

    parts = [
        "",
        "== REVISION REQUESTED ==",
        "",
        "Your previous proposal was reviewed by the deterministic Validator. The rules",
        "you proposed last time are listed below, along with the validator's exact",
        "violation reasons for each rejected rule. The violation reasons are produced",
        "by the deterministic layer and are authoritative — they are not opinions.",
        "",
        "You must return a COMPLETE revised RuleSet (via submit_ruleset) that:",
        "  1. Keeps every approved rule intact.",
        "  2. Repairs or removes each rejected rule so that all listed violations are resolved.",
        "  3. Does NOT introduce new constraint violations.",
        "",
        "YOUR PREVIOUS RULES:",
        "",
        _format_previous_rules(previous_rules),
        "",
        "REJECTED RULES (must be fixed or removed):",
        "",
        _format_rejected_rules(feedback),
        "",
    ]
    return "\n".join(parts)


def _format_previous_rules(previous_rules: list[dict] | None) -> str:
    if not previous_rules:
        return "(none)"
    lines = []
    for r in previous_rules:
        trigger = r.get("trigger") or {}
        actions = r.get("actions") or []
        actions_summary = ", ".join(
            f"{a.get('device')}.{a.get('action')}" for a in actions
        ) or "(none)"
        satisfies = r.get("satisfies_constraints") or []
        lines.append(f"- [{r.get('id')}] \"{r.get('name', '')}\"")
        lines.append(f"    trigger: {trigger.get('device')}.{trigger.get('event')}")
        lines.append(f"    actions: {actions_summary}")
        lines.append(f"    satisfies_constraints: {list(satisfies)}")
    return "\n".join(lines)


def _format_rejected_rules(feedback: TeacherFeedback | None) -> str:
    if feedback is None or not feedback.rejected_rules:
        return "(none)"
    lines = []
    for rec in feedback.rejected_rules:
        lines.append(f"- [{rec.rule_id}] \"{rec.name}\"")
        lines.append("    Violations:")
        for v in rec.violations:
            lines.append(f"      ! [{v.constraint_id}] {v.reason}")
        lines.append(f"    Allowed triggers:   {', '.join(rec.allowed_triggers)}")
        lines.append(f"    Allowed conditions: {', '.join(rec.allowed_conditions)}")
        lines.append(f"    Allowed actions:    {', '.join(rec.allowed_actions)}")
    return "\n".join(lines)
