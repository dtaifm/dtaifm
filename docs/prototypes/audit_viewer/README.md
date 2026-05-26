# Audit-viewer prototype (Phase 0)

**Status: design prototype for [issue #17](https://github.com/dtaifm/dtaifm/issues/17). Not a shipped feature, not a supported UI surface, not part of any release.**

This proves the *shape* of a read-only audit viewer without committing dtaifm to a UI architecture. It renders a `.dtaifm-review.json` audit bundle as a single static HTML page so you can see the audit story — proposals, approved vs rejected rules, violation reasons, the execution trace, hashes, and replay status — at a glance.

## What's here

- `sample-review.dtaifm-review.json` — a checked-in sample bundle produced by `dtaifm demo smart_home` (2 approved rules, 1 rejected with a violation, one fired rule).
- `generate_report.py` — a **standard-library-only** generator that turns a bundle into `audit-report.html`. Its only dtaifm dependency is the read-only `replay()` call used to show verification status (and it degrades gracefully if dtaifm isn't importable).
- `audit-report.html` — the generated page (open it in any browser).

## Regenerate

```bash
python generate_report.py                       # uses the checked-in sample -> audit-report.html
python generate_report.py other.json out.html   # any bundle
```

## Hard boundaries (what this prototype is NOT)

- No teacher calls, no API keys.
- No mutation, no live config writes, no "deploy" controls.
- No CLI command, no new package/runtime dependency, no JavaScript.
- It only *visualizes* a deterministic artifact. **The viewer must never become an execution surface** — that principle is the whole point of #17.

If this shape is approved, the likely first real step (per #17) is a `dtaifm inspect --html` static report generator; a local `dtaifm ui` viewer and any authoring workflows would come much later, if ever.
