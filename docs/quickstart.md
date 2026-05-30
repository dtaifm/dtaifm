# Quickstart

Five minutes from `pip install` to your first review.

## Install (recommended)

```bash
pip install dtaifm
```

Confirm:

```bash
dtaifm --help                   # CLI is on PATH (or use `python -m dtaifm`)
```

### Alternate source installs

Use these when you want to contribute, run the test suite, or pin to a specific git revision instead of a PyPI release:

```bash
# Latest main from GitHub
pip install git+https://github.com/dtaifm/dtaifm.git

# Pinned to a tag
pip install git+https://github.com/dtaifm/dtaifm.git@v0.1.0

# Editable clone with the dev extras (pytest, ruff, jsonschema, build)
git clone https://github.com/dtaifm/dtaifm
cd dtaifm
pip install -e ".[dev]"
pytest                          # 327 tests, fully offline
```

## Run the built-in smart home demo

```bash
python examples/smart_rules/demo.py
```

Expected: three rules are proposed, the validator approves two and rejects one (`r_auto_unlock_door` — it violates `no_auto_unlock` and `rule_must_explain`), and the runtime fires the approved night-light rule against a simulated motion event.

## Run the same flow through the CLI

```bash
# Audit the rule file (exit 1 because one rule is unsafe)
dtaifm validate examples/smart_rules/constraints.yaml examples/smart_rules/rules.yaml

# Validate + execute against an event
dtaifm run examples/smart_rules/constraints.yaml examples/smart_rules/rules.yaml \
  --state examples/smart_rules/state.json

# Combined audit (validation + execution trace + final actions)
dtaifm review examples/smart_rules/constraints.yaml examples/smart_rules/rules.yaml \
  --state examples/smart_rules/state.json
```

## Generate, audit, and replay an audit bundle

```bash
dtaifm review examples/smart_rules/constraints.yaml examples/smart_rules/rules.yaml \
  --state examples/smart_rules/state.json --bundle review.json

dtaifm inspect review.json     # read-only summary
dtaifm replay  review.json     # verifies the bundle reproduces exactly
```

## Try the second built-in domain

```bash
dtaifm review --domain network_automation \
  examples/network_automation/constraints.yaml examples/network_automation/rules.yaml \
  --state examples/network_automation/state.json
```

## Use a local teacher

No API key required:

```bash
# Ollama (default: http://localhost:11434)
dtaifm propose examples/smart_rules/constraints.yaml --teacher ollama --out proposed.yaml

# Lemonade on a remote workstation
dtaifm propose examples/smart_rules/constraints.yaml \
  --teacher lemonade \
  --teacher-base-url http://192.0.2.10:13305 \
  --model Qwen3-0.6B-GGUF \
  --out proposed.yaml
```

Diagnose your local setup:

```bash
dtaifm teachers --check
```

## Next

- [concepts.md](concepts.md) — the framework's architecture and trust boundary.
- [domains.md](domains.md) — how domain packs work; how to build your own.
- [local-teachers.md](local-teachers.md) — Ollama and Lemonade in depth.
- [audit-bundles.md](audit-bundles.md) — replayable audit artifacts.
- [reproposal-loop.md](reproposal-loop.md) — letting teachers learn from the validator.
