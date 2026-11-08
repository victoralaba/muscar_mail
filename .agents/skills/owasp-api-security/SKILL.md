---
name: owasp-api-security
description: Audit API code for vulnerabilities and generate secure API code following the OWASP API Security Top 10 (2023). Use this skill whenever the user asks to review, audit, pentest, or "check the security of" an API or endpoint; whenever they're designing or writing new API endpoints, authorization logic, authentication flows, rate limiting, webhook/URL-fetching code, or third-party API integrations; or whenever they mention terms like BOLA, IDOR, mass assignment, broken auth, rate limiting, SSRF, API inventory, shadow API, or "is this endpoint secure." Applies to any API framework or language (FastAPI, Express, Django REST, Spring, Go, etc.) — not tied to one stack. Trigger even if the user doesn't say "OWASP" explicitly; any request to secure, review, or design an API endpoint should consult this skill.
---

# OWASP API Security Top 10 (2023)

Framework-agnostic skill for two workflows: **auditing** existing API code for vulnerabilities, and **generating** new API code that avoids them. Covers the 10 categories in the 2023 OWASP API Security Top 10.

## When to use which mode

- **Audit mode**: user shares/points to existing endpoint code, asks for a review, pentest-style read, or "is this safe?" → go through the checklist below, flag findings by category, cite the specific line/pattern, and point to the relevant `references/APIx-*.md` for the fix.
- **Generate mode**: user is writing a new endpoint, auth flow, upload handler, webhook, admin panel, etc. → apply the relevant categories' prevention patterns proactively before the user has to ask; don't wait for a vulnerability to exist first.
- Most real tasks are both: reviewing code often means rewriting it securely too.

## The 10 categories — quick triage table

| # | Category | One-line smell | Reference |
|---|----------|-----------------|-----------|
| API1 | Broken Object Level Authorization (BOLA) | Object ID in URL/body used without checking caller owns/can access it | `references/API1-bola.md` |
| API2 | Broken Authentication | Weak/missing token validation, guessable creds, no MFA on sensitive ops | `references/API2-broken-authentication.md` |
| API3 | Broken Object Property Level Authorization | Response leaks extra fields; request accepts fields it shouldn't (mass assignment) | `references/API3-property-level-authz.md` |
| API4 | Unrestricted Resource Consumption | No pagination/size/rate/timeout limits; unbounded loops on user input | `references/API4-resource-consumption.md` |
| API5 | Broken Function Level Authorization | Role/privilege check missing or role read from client-controlled data | `references/API5-function-level-authz.md` |
| API6 | Unrestricted Access to Sensitive Business Flows | Legit feature (checkout, booking, coupon redemption) abusable by automation/scripting | `references/API6-business-flows.md` |
| API7 | Server-Side Request Forgery (SSRF) | API fetches a URL supplied or influenced by the user | `references/API7-ssrf.md` |
| API8 | Security Misconfiguration | Verbose errors, default creds, permissive CORS, missing security headers, debug mode on | `references/API8-misconfiguration.md` |
| API9 | Improper Inventory Management | Old/beta/undocumented versions still live; no API inventory or deprecation policy | `references/API9-inventory-management.md` |
| API10 | Unsafe Consumption of APIs | Third-party API responses trusted without validation, size limits, or timeouts | `references/API10-unsafe-consumption.md` |

Read only the reference file(s) relevant to the code in front of you — don't load all 10 for a single-endpoint review.

## Audit workflow

1. **Map the surface**: list every endpoint/route in scope, its method, auth requirement, and what object(s)/resource(s) it touches.
2. **Walk the table above per endpoint.** For each row, ask the one-line smell question against the actual code — not the docs, the code.
3. **For each hit**: open the matching reference file, confirm against its detection checklist, then report:
   - Category + severity (rough: BOLA/broken auth/SSRF = high; misconfig/inventory = medium-high; resource consumption = context-dependent)
   - Exact location (file:line or function name)
   - Why it's exploitable (one sentence, concrete — not generic OWASP boilerplate)
   - The fix, using the reference's prevention pattern adapted to the actual language/framework in front of you
4. **Don't pad the report.** Only list categories that actually apply to the code shown; a clean finding ("API4: rate limiting present via X") is fine to skip entirely rather than narrate.
5. If the codebase has a known stack (check for `fastapi-*` skills or framework hints in the code), prefer that framework's idiomatic fix over generic pseudocode.

## Generate workflow

1. Identify what's being built: CRUD endpoint, auth flow, file upload, webhook receiver, admin function, bulk/business-critical action, third-party integration, etc.
2. Cross-reference against the triage table — most new endpoints touch at least API1, API2, API4, and API5 by default; SSRF (API7) and API10 only apply if the code fetches external URLs or consumes external APIs.
3. Bake in the relevant prevention patterns from the start (ownership checks, explicit response schemas, rate limits, role checks server-side, URL allowlisting) rather than writing the naive version and retrofitting.
4. Don't over-engineer: don't add SSRF allowlisting to an endpoint that never fetches a URL, don't add business-flow throttling to an internal admin tool with no public exposure. Match controls to actual exposure.

## Severity framing

When reporting findings, don't just cite the category name — say what an attacker actually gets (data of other users, account takeover, service outage, internal network access, etc.). OWASP category labels are for organizing the report, not for explaining risk to a reader.
