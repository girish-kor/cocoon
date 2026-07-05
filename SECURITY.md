# Security Policy

Cocoon touches two sensitive things: **broker credentials** and **code that can place
real orders**. Please treat both accordingly.

## Reporting a vulnerability

Do **not** open a public issue for security problems. Instead, report privately via
[GitHub Security Advisories](../../security/advisories/new) (Security → Report a
vulnerability). We aim to acknowledge within 72 hours.

Please include: affected version/commit, reproduction steps, impact, and any suggested fix.

## Credential handling (how Cocoon is designed)

- `mt5.password` is a **guarded secret**. It must never appear in any YAML config file —
  only in `.env` or the environment. The config loader enforces this and exits with code
  `11` (`secret in config file`) if a secret leaks into YAML.
- `.env` and `.env.*` are git-ignored by default; only `.env.example` is committed. **Never
  commit a real `.env`.** Copy `.env.example` to `.env` and fill in local values.
- If you believe you have committed a credential, rotate it immediately (change your MT5
  password), then scrub history.

## Capital-safety reminder

The risk, order, and bridge code is **untested against historical tick data or a real
terminal**. A security or correctness bug here can move real money. Never point Cocoon at a
funded account without your own validation, process supervision, and kill-switch. See the
[warning in the README](README.md#a-warning-worth-repeating).

## Supported versions

Cocoon is pre-1.0 reference software; only the latest `main` is supported.
