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

## Vocabulary enforcement

The validator's domain-compatibility check produces a synthetic `__domain__` violation when a rule uses an out-of-vocabulary trigger event, condition type, or action verb. The runtime additionally refuses to execute any approved rule whose actions aren't in the active domain (defense-in-depth — useful if a rule somehow slipped past validation).

## Reading the registry

```python
from dtaifm.domains.registry import get_domain, list_domains
list_domains()                # ['network_automation', 'smart_home']
get_domain("smart_home")      # Domain(id='smart_home', version='0.1', ...)
```
