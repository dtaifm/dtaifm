---
name: Bug report
about: Report something that does not work as documented
labels: bug
---

## What happened

A clear, short description of the bug.

## What you expected to happen

A clear, short description of the expected behavior.

## Reproduction

Minimal command sequence or code snippet:

```bash
# example
dtaifm review constraints.yaml rules.yaml --state state.json
```

If the bug involves YAML/JSON files, please attach minimal versions.

## Environment

- dtaifm version: (output of `python -c "import dtaifm; print(dtaifm.__version__)"`)
- Python version: (output of `python --version`)
- OS:
- Optional extras installed: (e.g. `dtaifm[anthropic]`, none)

## Trust-boundary impact

Does the bug let AI output reach the runtime without passing the validator? Does it let `dtaifm replay` accept a tampered bundle? If so, please flag explicitly — these are security-adjacent.
