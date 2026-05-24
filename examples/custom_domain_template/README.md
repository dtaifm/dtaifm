# Custom domain template

A minimal, self-contained domain pack you can copy and adapt to your own system.

## What's in the box

| File | Purpose |
|---|---|
| `__init__.py` | Defines `SUPPORT_DOMAIN` (a `Domain`) and one custom evaluator (`escalation_requires_assignment`). |
| `constraints.yaml` | Two constraints — one custom, one standard (`rule_must_explain`). |
| `rules.yaml` | Two example rules that satisfy both constraints. |
| `state.json` | A sample event so you can try `dtaifm run` end-to-end. |
| `test_my_domain.py` | Test stub showing how to verify a domain's vocabulary, evaluator, and examples. |

## Try it locally

The template defines but does not auto-register the domain. Register it from a small Python entry point and call the CLI:

```python
# my_app.py
import sys
import importlib.util
from pathlib import Path

from dtaifm.cli import main
from dtaifm.domains.registry import register_domain

template_init = Path("examples/custom_domain_template/__init__.py")
spec = importlib.util.spec_from_file_location("support_template", template_init)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
register_domain(mod.SUPPORT_DOMAIN)

sys.exit(main(sys.argv[1:]))
```

Then:

```bash
python my_app.py validate --domain support \
  examples/custom_domain_template/constraints.yaml \
  examples/custom_domain_template/rules.yaml

python my_app.py review --domain support \
  examples/custom_domain_template/constraints.yaml \
  examples/custom_domain_template/rules.yaml \
  --state examples/custom_domain_template/state.json
```

## Adapt it to your own domain

1. Rename the directory and the `SUPPORT_DOMAIN` constant.
2. Edit the `trigger_events`, `condition_types`, and `action_kinds` sets to match your system's vocabulary.
3. Replace `escalation_requires_assignment` with the custom evaluators you actually need. The signature is `(rule, constraint) -> ConstraintViolation | None`. Return `None` when the rule satisfies the constraint; return a `ConstraintViolation` with a human-readable `reason` otherwise.
4. Update `constraints.yaml` so each constraint's `type` matches either a built-in name (`absolute_prohibition`, `mutual_exclusion`, `temporal_restriction`, `mode_override`, `metadata_requirement`) or one of your custom evaluator keys.
5. Update `rules.yaml` with rules a reasonable teacher might produce. Include at least one rule that exercises each custom evaluator (both passing and failing paths in your tests).
6. Update `test_my_domain.py` so each evaluator has explicit pass/fail tests.

## Architectural contract you inherit

By following this template you keep the framework's invariants intact:

- The validator (with your domain attached) refuses any rule that uses a trigger event, condition type, or action verb outside your domain's vocabulary.
- The runtime double-checks domain action vocabulary at execution time (defense-in-depth).
- Your custom evaluators run during validation only — they never execute actions, never call out to networks, and never modify the validator's dispatch beyond returning a `ConstraintViolation`.

See [../../docs/domains.md](../../docs/domains.md) for the full architectural reference.

## Running the test stub

```bash
pytest examples/custom_domain_template/test_my_domain.py
```

The stub is excluded from the main suite's auto-discovery so it does not pollute the global domain registry during normal `pytest` runs.
