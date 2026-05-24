## Summary

What does this PR change and why?

## Architectural checklist

- [ ] No AI output reaches the runtime without passing the validator
- [ ] No provider adapter validates or executes anything
- [ ] No new core dependency on a provider SDK (extras only)
- [ ] Tests pass offline with no API key (`pytest`)
- [ ] If a new teacher adapter: tests use an injected fake client / mocked SDK
- [ ] If a new domain pack: tests cover both happy-path and a deliberate rejection
- [ ] If touching the public API: docs in `docs/` and the README are updated
- [ ] CHANGELOG.md updated under the appropriate section

## Testing

How did you verify this change? Commands run, scenarios exercised.

## Related issues

Closes #...
