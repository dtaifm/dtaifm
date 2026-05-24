# Audit bundles

> Auditability means you can prove later what was proposed, what was rejected, what executed, and why.

An **audit bundle** (`.dtaifm-review.json`) is a self-contained record of a single review. Given a bundle from six months ago, anyone can replay it on a fresh checkout and confirm — cryptographically — that the same inputs produce the same outputs.

## Producing a bundle

```bash
dtaifm review constraints.yaml rules.yaml --state state.json --bundle review.json
```

The bundle is written alongside whatever output `review` already produces; the existing text/JSON output shape is unchanged.

## Bundle structure

```
bundle_version       0.1
framework_version    0.1.0
schema_version       0.1
created_at           2026-05-24T12:00:00+00:00
domain               {id, version}
proposals            [{proposal_id, proposed_by, created_at, rule_ids}]
inputs
  constraints        {source, hash, content}
  rules              {source, hash, content}
  state              {source, hash, content}
validation           {hash, result}
execution            {hash, result}
```

Every `hash` is `sha256:<hex>` over the canonical-JSON form of the corresponding `content` / `result`. Canonical JSON sorts keys, uses compact separators, and is therefore identical for equivalent YAML and JSON inputs.

## Inspecting a bundle

```bash
dtaifm inspect review.json           # human-readable summary
dtaifm inspect review.json --json    # machine-readable
```

`inspect` is pure read — it does not execute anything.

## Replaying a bundle

```bash
dtaifm replay review.json            # exit 0 on success, exit 1 on mismatch
dtaifm replay review.json --json
```

Replay performs three layered checks:

1. **Input integrity.** Recompute the hash of each embedded `inputs.<kind>.content`. If it doesn't match the stored `inputs.<kind>.hash`, the bundle has been tampered with at the source level.
2. **Stored-result integrity.** Verify the stored `validation.hash` matches `sha256_of(validation.result)`, and likewise for execution. Catches naive tampering of the recorded outcomes without re-running.
3. **Recomputed-result match.** Re-run validation and execution from the embedded inputs and compare against the stored hashes. Catches framework non-determinism or domain semantic drift.

A domain-version mismatch becomes a **warning** rather than a failure when results still match (a non-breaking domain change). Replay never invokes a teacher or provider adapter — it's a pure deterministic verification.

## Public Python API

The CLI is a thin wrapper over three functions:

```python
from dtaifm import review, replay, inspect_bundle

bundle = review(
    constraints_path="constraints.yaml",
    rules_path="rules.yaml",
    state_path="state.json",
    domain_id="smart_home",
    bundle_path="review.json",   # optional
)

result = replay("review.json")    # accepts dict or path
assert result.success
assert result.inputs_intact
assert result.validation_matches
assert result.execution_matches

summary = inspect_bundle("review.json")
```

## Reproducibility notes

- The state file's `time` field is required for deterministic replay. If a state file lacks `time`, the framework injects wall-clock time when writing the bundle (so the bundle still replays exactly) — but the original state file is the right place to fix it.
- Bundle hashes are content-based, not file-format-based: the same constraints expressed as YAML and JSON produce identical hashes.
- A bundle from a future framework version may fail replay on an older install if the validator or runtime semantics changed. The `framework_version` and `domain.version` in the bundle make such cases diagnosable.

## When to use bundles

- After every production review (treat them like git commits for AI proposals).
- Before deploying a revised rule set: build a bundle, sign or store it, then deploy. Six months later, you can prove which rules were active and why.
- In CI: a regression suite can `dtaifm replay` a known-good bundle to detect accidental framework or domain-pack breakage.
