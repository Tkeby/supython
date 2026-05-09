# Security policy

## Reporting a vulnerability

**Please do not file a public GitHub issue for security reports.**

Use GitHub's private vulnerability reporting:
<https://github.com/Tkeby/supython/security/advisories/new>

If that channel is unavailable, email `tsegaw.kebede09@gmail.com` with the
subject prefix `[supython security]`.

A report should include:

- Affected version (`supython --version` or the `supython` package version).
- A minimal reproduction or proof of concept.
- Impact assessment (data exposure, privilege escalation, RCE, DoS, etc.).
- Suggested remediation, if any.

## Response

- Acknowledgement within 5 business days.
- Initial triage and severity assessment within 10 business days.
- Coordinated disclosure: a fix lands in the next patch release; a CVE is
  requested when warranted; reporters are credited unless they ask not to be.

## Scope

In scope:

- The `supython` Python package (auth, JWT issuance, RLS helpers, storage,
  realtime, jobs, CLI, admin API).
- The bundled admin SPA (`src/supython/admin/static/`).
- Default configuration shipped via `supython init`.

Out of scope:

- Third-party dependencies (report upstream — we will track and re-release).
- Self-hosted deployments where the operator has misconfigured Postgres,
  PostgREST, or RLS policies in ways that diverge from the defaults.
- Known limitations explicitly documented in `docs/PROJECT.md`.
