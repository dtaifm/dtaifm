# Domains

A **domain pack** declares what is possible in a given system: its allowed trigger events, condition types, action verbs, and any domain-specific constraint evaluators. Teachers propose only within that boundary; the validator and runtime both refuse out-of-vocabulary rules.

## Built-in domains

| Domain id | What it covers |
|---|---|
| `smart_home` (default) | Residential automation: lights, HVAC, locks, sensors. |
| `network_automation` | Router/switch config, BGP, maintenance windows. Adds three custom evaluators: `companion_action_required`, `action_target_limit`, `mode_required`. |

Every CLI command takes `--domain`:

```bash
dtaifm validate --domain network_automation \
  examples/network_automation/constraints.yaml examples/network_automation/rules.yaml
```

## What a Domain contains

```python
@dataclass
class Domain:
    id: str
    version: str
    description: str = ""
    trigger_events: frozenset[str]           # allowed trigger event names
    condition_types: frozenset[str]          # known condition type names
    action_kinds: frozenset[str]             # allowed action verbs
    extra_constraint_evaluators: dict        # type-name -> evaluator function
    state_schema: dict                       # optional state shape hint
```

The validator dispatches on `constraint.type`. Domain-registered evaluators are consulted first; the framework's five built-in evaluators are the fallback. This is how `network_automation` extends the framework without modifying core code.

## Building your own domain pack

Start from the template at `examples/custom_domain_template/`. It contains a tiny `support` domain with a single custom evaluator, plus example constraints, rules, and a test stub.

A minimal domain pack looks like this:

```python
from dtaifm.domains.base import Domain
from dtaifm.domains.registry import register_domain

MY_DOMAIN = Domain(
    id="my_domain",
    version="0.1",
    trigger_events=frozenset({"event_a", "event_b"}),
    condition_types=frozenset({"time_range", "mode_not", "mode_is", "device_state"}),
    action_kinds=frozenset({"notify", "escalate"}),
    extra_constraint_evaluators={
        # "my_custom_type": my_evaluator,
    },
)
register_domain(MY_DOMAIN)
```

To make it visible to the CLI the domain must be registered before resolution. There are three ways:

- **Built-in packs** are auto-imported by `dtaifm/domains/__init__.py`.
- **Installed third-party packs** are auto-discovered from the `dtaifm.domains` entry-point group — advertise your `Domain` (or a zero-argument callable returning one) in your package metadata, and every domain-resolving command picks it up with no flag:

  ```toml
  # pyproject.toml of your domain package
  [project.entry-points."dtaifm.domains"]
  my_domain = "my_pkg.domain:MY_DOMAIN"
  ```

- **Local or not-yet-installed packs** can be loaded ad hoc with `--domain-module`, which imports the named module (so its `register_domain(...)` runs) before resolving the domain:

  ```bash
  dtaifm validate --domain my_domain --domain-module my_pkg.domain \
    constraints.yaml rules.yaml
  ```

  `--domain-module` is accepted by every domain-resolving command (`validate`, `run`, `review`, `propose`, `prompt`, `feedback`, `repropose`, `demo`, and `replay`). A broken entry point is reported as a warning and skipped, never fatal.

## Generic policy constraint types

Before writing a custom evaluator, check whether one of the five generic constraint types already expresses your policy. They are domain-neutral framework built-ins — usable from any `constraints.yaml` with no code:

```yaml
constraints:
  - id: read_only_mode
    description: "Only non-mutating actions are allowed."
    type: action_allowlist
    allowed_actions: [notify, monitor, flag]

  - id: no_score_tuning_on_thin_evidence
    description: "Score tuning requires a minimum sample size."
    type: parameter_threshold
    action: tune_min_score
    parameter: sample_size
    min: 30

  - id: pause_requires_evidence
    description: "Pausing a source must cite the failing signal."
    type: requires
    if_action: pause_discovery
    requires_condition: evidence
```

- **`action_allowlist`** / **`action_denylist`** — bound which action verbs rules may use, optionally per device via `applies_to`.
- **`requires`** — a rule performing `if_action` must also carry `requires_action` and/or a condition of type `requires_condition` (optionally with matching `condition_parameters`). This is the evidence-as-conditions guardrail pattern below, with no custom code.
- **`mutually_exclusive_actions`** — a single rule may not combine two or more of the listed `actions`.
- **`parameter_threshold`** — a numeric parameter on a matching action (`action:`) or condition (`condition:`) must satisfy `min`/`max`. Fail-closed: a matching rule whose parameter is missing or non-numeric is rejected, so a rule cannot dodge a limit by omitting the value it is limited on. Optional `when_action:` makes the bound action-conditional — it only applies to rules whose action set includes that action kind:

  ```yaml
  - id: downgrade_needs_streak
    description: "Downgrading discovery requires a failure streak of at least 2."
    type: parameter_threshold
    when_action: downgrade_to_no_discovery
    condition: attestation
    parameter: failure_streak
    min: 2
  ```

  Other rules may carry the same `attestation` condition with a lower streak; the bound binds only the rules that perform the downgrade. (`requires` does not need a `when_action` — its `if_action` already provides exactly this scoping.)

A domain can override any of these by registering an evaluator under the same type name — domain evaluators always take priority over built-ins.

## Fail-closed governance metadata

When a constraint or evaluator depends on governance state — an approval status, a staging flag, an evidence metric — treat the *absence* of that state as a rejection, never as the permissive default. Two rules of thumb:

- **Producers emit explicitly.** A teacher, bridge, or attestation source must write `status: staged` / `status: approved` as a real value; it must never rely on a consumer defaulting a missing field.
- **Validators reject absence.** An evaluator that reads governance metadata off a rule should return a violation when the field is missing or malformed, not skip the check.

The framework's own `parameter_threshold` is the precedent: a bounded parameter that is missing or non-numeric is a violation, because a rule may not dodge a limit by omitting the value it is limited on. Apply the same posture to your custom evaluators — defaulting a missing `approved` flag to approved is how a gate silently stops gating.

## Custom constraint evaluators

A custom evaluator is a function `(rule, constraint) -> ConstraintViolation | None`:

```python
def escalation_requires_assignment(rule, constraint):
    actions = {a.action for a in rule.actions}
    if "escalate" in actions and "assign_engineer" not in actions:
        return ConstraintViolation(
            constraint_id=constraint.id,
            constraint_description=constraint.description,
            reason=f"Rule '{rule.id}' escalates without an accompanying assign_engineer action.",
        )
    return None
```

Register it via the domain's `extra_constraint_evaluators` dict, keyed by the `type` string you'll use in constraints.yaml.

## Evidence-aware guardrails (and what an evaluator can see)

A custom evaluator receives exactly `(rule, constraint)` — and nothing else. It does **not** see the live system state, the proposal-time context, or any "evidence" the teacher reasoned over. It can only inspect the rule's own `trigger`, `conditions`, and `actions`, plus the constraint's `parameters`.

That has one important consequence: **a guardrail can only act on evidence that is encoded into the rule.** To block an action when some signal holds in the world, the teacher must record that signal as a condition in the rule, and the evaluator checks it there.

For example — "do not propose `auto_refund` when the order is flagged for review." The teacher records the evidence as a condition (here `evidence` is a condition type your domain declares in `condition_types`), and the evaluator cross-checks the action against it:

```python
def no_refund_when_flagged(rule, constraint):
    actions = {a.action for a in rule.actions}
    flagged = any(
        c.type == "evidence" and c.parameters.get("signal") == "order_flagged"
        for c in rule.conditions
    )
    if "auto_refund" in actions and flagged:
        return ConstraintViolation(
            constraint_id=constraint.id,
            constraint_description=constraint.description,
            reason=f"Rule '{rule.id}' proposes auto_refund while carrying order_flagged evidence.",
        )
    return None
```

Numeric thresholds work the same way — a "don't act on a tiny sample" guardrail reads a `sample_size` parameter off a condition and compares it.

To force the teacher to *always* declare the evidence behind a proposal — so a guardrail can rely on it being present — pair this with a `metadata_requirement` constraint. Keeping evidence inside the rule is also what keeps `dtaifm replay` deterministic: the rule is a self-contained artifact that carries its own justification, with no hidden external inputs.

## Vocabulary enforcement

The validator's domain-compatibility check produces a synthetic `__domain__` violation when a rule uses an out-of-vocabulary trigger event, condition type, or action verb. The runtime additionally refuses to execute any approved rule whose actions aren't in the active domain (defense-in-depth — useful if a rule somehow slipped past validation).

## Reading the registry

```python
from dtaifm.domains.registry import get_domain, list_domains
list_domains()                # ['network_automation', 'smart_home']
get_domain("smart_home")      # Domain(id='smart_home', version='0.1', ...)
```
