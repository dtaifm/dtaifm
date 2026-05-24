---
name: Feature request
about: Suggest an idea for dtaifm
labels: enhancement
---

## Problem

What problem are you trying to solve? Who benefits from solving it?

## Proposed solution

What would the change look like from the user's perspective? Sketch a CLI invocation, a Python API call, or a config snippet.

## Architectural fit

dtaifm has a few load-bearing rules:

- AI output is an artifact, not an action.
- Provider adapters are translators, not trusted components.
- Domains define what is possible; teachers only propose within that boundary.
- Provider dependencies stay optional.

How does this proposal fit those rules? If it changes the boundary, please call that out.

## Alternatives considered

What else did you consider, and why does this proposal win?
