---
name: security-audit
description: Audit code for security vulnerabilities and guide secure code generation, mapped to 10 OWASP-style risk categories (Access Control, Misconfiguration, Supply Chain, Cryptographic Failures, Injection, Insecure Design, Authentication, Integrity Failures, Logging Failures, Exceptional Conditions). Language-agnostic — any stack. Use whenever the user asks to "audit", "review", or "check" code for security, asks "is this secure", mentions OWASP, requests a security-focused code review, or writes code touching auth, user input, secrets, dependencies, crypto, error handling, or logging — even without saying "security". Covers both reviewing existing code and writing new code securely.
---

# Security Audit

A vulnerability-taxonomy-driven skill for two jobs: **auditing** existing code for security flaws, and **preventing** flaws while writing new code. Both jobs are grounded in the same 10 categories — the difference is direction (finding vs. avoiding).

This skill is deliberately language- and framework-agnostic. The checklists, detection patterns, and remediation steps in `references/` describe the underlying flaw and give pseudocode plus real-language snippets, so they apply whether the code is Python, TypeScript, Svelte, Go, Rust, PHP, Java, or anything else.

## The 10 categories

| Code | Category | Core question |
|---|---|---|
| A01 | Broken Access Control | Can a user do or see something they shouldn't — including making the server fetch attacker-controlled URLs (SSRF)? |
| A02 | Security Misconfiguration | Are defaults, permissions, or error output leaking more than they should? |
| A03 | Software Supply Chain Failures | Can a dependency, build step, or package registry compromise the app? |
| A04 | Cryptographic Failures | Is sensitive data weakly encrypted, unencrypted, or protected by mismanaged keys? |
| A05 | Injection | Does untrusted input reach an interpreter (SQL, shell, HTML/DOM, template, LDAP, etc.) without neutralization? |
| A06 | Insecure Design | Is the flaw architectural — missing threat modeling, absent security requirements — rather than a coding bug? |
| A07 | Authentication Failures | Can identity, passwords, or sessions be bypassed, guessed, fixated, or hijacked? |
| A08 | Software or Data Integrity Failures | Does the system trust unsigned/unverified code, updates, or deserialized data? |
| A09 | Security Logging and Alerting Failures | Would an attack go undetected because it isn't logged or nobody is watching? |
| A10 | Mishandling of Exceptional Conditions | Do errors, timeouts, or edge cases fail open, crash unsafely, or leak internals? |

Each row links to `references/<code>-<slug>.md`, which is a deep-dive: a checklist, detection patterns (things to grep for or watch for while reading), bad-vs-good code examples, remediation steps, and notes on how the flaw shows up differently across stacks (backend, frontend, infra/CI).

## Reference files

- `references/a01-broken-access-control.md`
- `references/a02-security-misconfiguration.md`
- `references/a03-software-supply-chain-failures.md`
- `references/a04-cryptographic-failures.md`
- `references/a05-injection.md`
- `references/a06-insecure-design.md`
- `references/a07-authentication-failures.md`
- `references/a08-software-data-integrity-failures.md`
- `references/a09-security-logging-alerting-failures.md`
- `references/a10-mishandling-exceptional-conditions.md`

Don't load all ten into context up front. Load the ones relevant to the task at hand — see the two workflows below for how to pick.

## Workflow A: Auditing existing code

1. **Scope the surface.** Identify what you're actually looking at: is it an API layer, a frontend component, build/CI config, a dependency manifest, an auth module? This tells you which categories are even in play — a static marketing page won't have A07 (auth) issues, a lockfile review won't have A05 (injection) issues.
2. **Read the code fully before flagging anything.** Don't pattern-match on a single line out of context (e.g. a raw SQL string might already be parameterized two lines up). Understand data flow: where untrusted input enters, and everywhere it goes.
3. **Walk the categories that apply**, loading each relevant reference file and using its detection patterns as a checklist. For a typical backend route, that's usually A01, A02, A04, A05, A07, A09, A10 at minimum. For a dependency/CI review, that's A03 and A08. For frontend components, that's A01 (client-side authz assumptions), A05 (XSS/DOM injection), A02 (leaked config/secrets in client bundles).
4. **Report findings by severity, not by category order.** For each finding: what the flaw is, exactly where (file/line or function), the concrete exploit scenario (not just "this is bad practice"), and the fix. Don't pad the report with theoretical issues that don't apply to this codebase's actual attack surface.
5. **Explicitly confirm what's clean.** If you checked a category and found nothing, say so — silence reads as "not checked," not "checked and fine."
6. **Never fabricate findings.** If input validation happens somewhere you haven't seen (e.g. a shared middleware), say you couldn't confirm it rather than assuming either way.

## Workflow B: Writing new code securely

1. **Before writing security-sensitive code** (auth, input handling, file I/O, external requests, crypto, deserialization, error handling), load the relevant reference file(s) first — treat them as the spec, not an afterthought checklist run after the fact.
2. **Default to the secure option even if the user didn't ask for it**: parameterized queries over string concatenation, framework-provided escaping over manual escaping, allowlists over denylists, constant-time comparison for secrets, structured logging that excludes sensitive fields. Mention briefly why, don't lecture.
3. **Treat all external input as hostile** — request bodies, query params, headers, cookies, file uploads, webhook payloads, env vars set by a deploy pipeline you don't control, and responses from third-party APIs.
4. **When a shortcut would introduce a known flaw** (e.g. disabling TLS verification "for now", storing a password in plaintext "temporarily"), say so plainly and offer the secure alternative — don't silently comply and don't silently refuse; explain the trade-off in one line and proceed with the secure version unless the user overrides explicitly.
5. **Match existing project conventions** where they're already secure (e.g. an existing parameterized-query pattern, an existing auth middleware) rather than inventing a parallel approach.

## Severity framing

When reporting findings, use this rough calibration rather than inventing ad hoc severity labels:

- **Critical** — remotely exploitable, no auth required, leads to data breach / full compromise / RCE (e.g. unauthenticated SQLi, hardcoded prod secrets, SSRF reaching internal metadata endpoints).
- **High** — exploitable with some precondition (authenticated user, specific config), still leads to serious impact (privilege escalation, stored XSS, broken object-level authorization).
- **Medium** — requires more specific conditions or has partial impact (verbose error messages, missing rate limiting, weak-but-not-broken crypto).
- **Low** — defense-in-depth gaps, best-practice deviations with limited standalone impact (missing security headers, overly long token lifetimes).

## What this skill does not replace

This skill supports manual review and generation-time hardening. It is not a substitute for automated SAST/dependency scanning tools, a formal penetration test, or a professional security audit before handling regulated data (PCI, HIPAA, etc.). Say so if the user's ask implies they need one of those.
