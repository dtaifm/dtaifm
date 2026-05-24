# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities via GitHub Security Advisories on this repository (the "Security" tab → "Report a vulnerability"). We aim to acknowledge reports within 7 days.

If you cannot use GitHub Security Advisories, open a minimal public issue requesting a private channel — do not include exploit details in the public issue.

## Scope

dtaifm is deterministic-first middleware. The framework's value depends on the trust boundary between proposing teachers and the deterministic validator + runtime. Reports that demonstrate ways to bypass the validator, execute rules without validator approval, or tamper with audit bundles without detection are of highest interest.

Out of scope:

- Issues that require an attacker to already control the constraint file (constraints are trusted human input).
- Issues in third-party teacher provider services (Anthropic, Ollama, Lemonade); please report those upstream.

## Supported versions

The project is pre-1.0. Only the latest `main` branch receives security fixes.

## Security model summary

- Constraints are trusted input. Loading a malicious constraints file with `metadata_requirement: required_fields: [satisfies_constraints]` removed will of course skip that check; that is by design.
- Rules from any teacher (mock, cloud, local) are untrusted until the validator approves them.
- The runtime refuses to execute actions outside the active domain even if a rule somehow bypassed validation (defense-in-depth).
- Audit bundles use canonical-JSON SHA-256 hashes. Replay verifies input integrity, stored-result integrity, and recomputed-result match.
