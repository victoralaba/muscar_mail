---
name: verifalia
description: >
  Email validation service integration using Verifalia v2.4+ API. Use this skill
  for any task involving email verification, credit balances, batch email validation,
  Verifalia API contracts, synchronous waitTime behavior, response parsing (classification,
  disposable, role accounts), and MCP tool exposure. Triggers include: "verifalia",
  "verify email", "validate email", "email validation", "deliverability check",
  "disposable email check", "credit balance". ALWAYS enforce the 25-email batch cap.
---

# Verifalia Email Validation Skill

> Read this skill fully before writing or updating any Verifalia-related code.
> For exact API endpoints, request/response bodies, and schemas, read the relevant file in `refs/`.

---

## Prime Directives

1. **Strict 25-Email Cap**: The free tier grants 25 validations/day. Never allow a batch larger than 25 emails. Reject at the Pydantic boundary with HTTP 422 before calling Verifalia.
2. **Immediate Synchronous Results via `waitTime`**: Small batches (1–25 emails) take 1–5 seconds. Always specify `?waitTime=30000` (up to 30s) on `POST /v2.4/email-validations` so Verifalia completes the job within the initial HTTP request.
3. **Stateless Operation**: Do not store job IDs in local disk or memory cache. The client or AI agent gets the result in the HTTP response.
4. **Token-Efficient LLM Schema**: Strip verbose DNS and SMTP handshake records before returning data to LLM agents. Surface only key decision fields.

---

## Reference Documentation Index

Read the relevant reference from `refs/` as needed:

| Topic | Reference File | What It Covers |
| :--- | :--- | :--- |
| **Authentication** | [`refs/authentication.md`](refs/authentication.md) | HTTP Basic Auth, Bearer tokens, headers, required permissions |
| **Email Validations** | [`refs/email-validations.md`](refs/email-validations.md) | `POST /v2.4/email-validations`, `waitTime`, batch payloads, quality levels |
| **Result Schema** | [`refs/result-schema.md`](refs/result-schema.md) | `Deliverable`, `Undeliverable`, `Risky`, `Unknown`, `isDisposableEmailAddress`, etc. |
| **Polling & Status** | [`refs/polling-and-status.md`](refs/polling-and-status.md) | `GET /v2.4/email-validations/{id}`, HTTP 202 vs 200, progress monitoring |
| **Credits & Quotas** | [`refs/credits-and-quotas.md`](refs/credits-and-quotas.md) | `GET /v2.4/credits/balance`, daily quota limits, credit tracking |
| **Error Handling** | [`refs/error-codes.md`](refs/error-codes.md) | HTTP 400, 401, 402 (payment required/insufficient credits), 429, 500 error formats |

---

## Architecture & Integration Pattern

All calls to Verifalia are encapsulated in `app/services/verifalia.py`:

```
Client / AI Agent
       │ (JSON-RPC 2.0 or REST)
       ▼
app/mcp/router.py (POST /mcp/v1/)  OR  app/api/v1/routes.py (POST /api/v1/verify)
       │
       ▼
app/services/verifalia.py (VerifaliaService)
       │ HTTP Basic Auth + waitTime=30000
       ▼
https://api.verifalia.com/v2.4/email-validations
```

### Response Distillation Model

Verifalia's raw entry is transformed into this compact structure:

```json
{
  "email": "user@example.com",
  "classification": "Deliverable",
  "status": "Success",
  "is_deliverable": true,
  "is_disposable": false,
  "is_role_account": false,
  "is_free_email": false
}
```
