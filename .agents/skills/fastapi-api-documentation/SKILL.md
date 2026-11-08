---
name: fastapi-api-documentation
description: >
  Generate precise, frontend-ready API documentation for FastAPI backends organized
  by domain. Use this skill whenever documentation is needed for frontend-backend
  contract communication, route implementation, or change tracking. Triggers include:
  "document this domain", "write the API docs", "what are the routes for X", "generate
  docs for the frontend", "document the changes", "update the API docs", "what changed
  in this domain", or any request where a frontend developer needs to know what a
  backend domain exposes, expects, or guarantees. Output is always domain-scoped,
  never a dump of all routes across all domains.
---

# FastAPI API Documentation Skill

> This skill produces documentation for frontend consumption. Every output
> must be precise enough that a frontend developer implementing against it
> never needs to ask a follow-up question about the contract.

---

## Prime Directive: The Document Is a Contract

API documentation is not a description of code. It is a **binding contract**
between backend and frontend. Every field, every status code, every error code
documented here is a promise the backend makes to the frontend.

```
If it is documented → the frontend can depend on it
If it is not documented → the frontend must not assume it
If it changes without a changelog entry → the frontend is broken by surprise
```

The document must be complete enough that the frontend never needs to read
backend source code to implement against it. If the frontend must read source
code, the documentation has failed.

---

## Prime Directive: Domain Scope Is Absolute

Each documentation file covers exactly one domain. Never mix domains.

A domain is a bounded set of related concerns — Migrations, Notifications,
Auth, Billing, Users, etc. Routes that belong to a domain are documented
together. Routes that belong to another domain are not mentioned, even if
they are related.

If a route in domain A depends on a contract from domain B, reference domain
B's documentation by name — do not reproduce domain B's contract inline.

---

## Phase 1: Document Structure

Every domain documentation file follows this structure, in this order.
No sections are optional. No sections are reordered.

```
# [Domain Name] API

## Overview
## Base URL
## Authentication
## Headers
## Routes
  ### [METHOD] [path]  (one section per route)
## Error Codes
## Changelog
```

---

## Phase 2: Section Specifications

### 2.1 Overview

Two to four sentences. Covers:
- What this domain is responsible for
- What the frontend uses it for
- Any domain-level constraint the frontend must know

```markdown
## Overview

The Migrations domain manages the full lifecycle of database migration scripts
within a series. The frontend uses this domain to create, order, execute, and
track migrations tied to a connected database. All migrations belong to a series
and follow a linked-list ordering — order is determined by the backend, not
the frontend.
```

### 2.2 Base URL

```markdown
## Base URL

\`\`\`
/api/v1/migrations
\`\`\`

All routes in this document are relative to this base. Prefix with the
API host for absolute URLs.
```

### 2.3 Authentication

Document the auth requirement at domain level, then note per-route exceptions.

```markdown
## Authentication

All routes in this domain require a valid Bearer token in the Authorization header.

\`\`\`
Authorization: Bearer <access_token>
\`\`\`

Unauthenticated requests return `401 Unauthorized`. Expired tokens return
`401` with code `token_expired`. Routes that deviate from this requirement
note it explicitly in their own section.
```

### 2.4 Headers

Document headers that apply across the domain. Per-route headers are
documented in the route section.

```markdown
## Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <token>` — see Authentication |
| `Content-Type` | Yes (mutations) | `application/json` for POST, PUT, PATCH |
| `Idempotency-Key` | Conditional | UUID. Required for POST /execute. Prevents duplicate execution on retry. |
| `Accept` | No | Defaults to `application/json` |
```

### 2.5 Routes

This is the core section. Each route gets its own subsection.
One route = one `###` heading. No combining routes into a single section.

**Route section structure:**

```
### [METHOD] [path]

[One sentence: what this route does and why the backend exposes it this way]

**Request**
**Response**
**Status Codes**
**Error Codes**
```

#### Route Description

One sentence. Covers what it does and why the backend exposes it this way —
enough for the frontend to understand intent without reading source code.
No side effects. No behavioral deep-dives (those belong in the behavior doc).

```markdown
### POST /

Creates a new migration and appends it to the tail of its series;
the backend assigns position automatically to preserve series integrity.
```

#### Request Block

Document every field the frontend can or must send. Distinguish required
from optional. Document the type, constraints, and what happens if omitted.

```markdown
**Request**

Body: `application/json`

| Field | Type | Required | Constraints | Notes |
|-------|------|----------|-------------|-------|
| `name` | string | Yes | 1–255 chars | Unique within the series |
| `series_id` | UUID string | No | Valid UUID v4 | If omitted, a new series is created |
| `sql_up` | string | Yes | Min 1 char | The migration SQL to execute |
| `sql_down` | string | No | — | Rollback SQL. Omitting disables rollback. |

**Example**

\`\`\`json
{
  "name": "add_users_table",
  "series_id": "550e8400-e29b-41d4-a716-446655440000",
  "sql_up": "CREATE TABLE users (id UUID PRIMARY KEY);",
  "sql_down": "DROP TABLE users;"
}
\`\`\`
```

#### Response Block

Document every field the frontend will receive. Note fields that may be
absent vs. null. Note computed fields the frontend should use rather than
derive itself.

```markdown
**Response**

\`\`\`json
{
  "id": "uuid",
  "name": "add_users_table",
  "series_id": "uuid",
  "parent_id": "uuid | null",
  "execution_order": 3,
  "status": "pending",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
\`\`\`

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID string | Stable identifier. Use this for all subsequent operations. |
| `parent_id` | UUID string \| null | null if this is the first in its series |
| `execution_order` | integer | Backend-assigned. Do not derive from list position. |
| `status` | enum string | One of: `pending`, `running`, `completed`, `failed`, `rolled_back` |
| `created_at` | ISO 8601 UTC | Timezone always UTC. |
```

#### Status Codes

Document every status code this specific route can return — success and
failure. Do not list codes that this route cannot return.

```markdown
**Status Codes**

| Code | When |
|------|------|
| `201 Created` | Migration created successfully |
| `400 Bad Request` | Request body malformed or field constraint violated |
| `401 Unauthorized` | Missing, expired, or invalid token |
| `409 Conflict` | A migration with this name already exists in the series |
| `422 Unprocessable Entity` | Pydantic validation failure — see error detail for field |
| `500 Internal Server Error` | Unexpected server error |
```

#### Error Codes

Document the machine-readable `code` field the frontend receives inside
the error envelope for this route. These are the codes the frontend should
switch on — not the HTTP status codes.

```markdown
**Error Codes**

All errors use this envelope:

\`\`\`json
{
  "error": {
    "code": "migration_conflict",
    "message": "A migration with this name already exists in this series",
    "field": null,
    "meta": { "conflicting_id": "uuid" }
  }
}
\`\`\`

| Code | HTTP | `field` | `meta` | When |
|------|------|---------|--------|------|
| `validation_error` | 422 | The failing field name | — | A field failed type or constraint validation |
| `migration_conflict` | 409 | null | `conflicting_id` | Name already exists in this series |
| `series_not_found` | 404 | null | `series_id` | Provided series_id does not exist |
| `token_expired` | 401 | null | — | Access token has expired — refresh and retry |
| `token_invalid` | 401 | null | — | Token malformed, revoked, or for wrong type |
| `internal_error` | 500 | null | — | Unexpected error — do not retry automatically |
```

### 2.6 Domain-Level Error Codes

After all routes, document error codes that can appear on any route in
this domain — auth errors, rate limits, common validation failures.

```markdown
## Error Codes

### Domain-Wide Codes

These codes may appear on any route in this domain.

| Code | HTTP | When |
|------|------|------|
| `token_expired` | 401 | Access token expired. Refresh and retry once. |
| `token_invalid` | 401 | Token malformed, revoked, or wrong type. Re-authenticate. |
| `rate_limit_exceeded` | 429 | Too many requests. Respect `Retry-After` header. |
| `internal_error` | 500 | Unexpected server error. Do not retry automatically. |
```

### 2.7 Changelog

Every time this document is updated, a changelog entry is added at the top
of this section. Entries are in reverse chronological order — newest first.

```markdown
## Changelog

### 2025-01-20

**Changed**
- `POST /` response: `order_index` field removed. Replaced by `execution_order`.
- `GET /{id}` response: `parent_id` field added (UUID string | null).

**Frontend Migration**
- Replace all reads of `response.order_index` with `response.execution_order`.
- `parent_id` is now available — no need to derive from list position.
- Any frontend code sorting by `order_index` must switch to `execution_order`.

---

### 2025-01-10

**Added**
- `POST /execute` endpoint — executes a migration against the connected database.
- `Idempotency-Key` header documented — required for POST /execute.

**Changed**
- `status` field on migration response now includes `rolled_back` as a valid value.

**Frontend Migration**
- Handle `rolled_back` in any status display or state machine on the frontend.
- Pass `Idempotency-Key` on all POST /execute calls to prevent duplicate execution.
```

---

## Phase 3: Changelog Generation Rules

When asked to document a change, produce a changelog entry using this process.

### 3.1 Change Classification

Every change is one of:

| Type | Meaning |
|------|---------|
| **Added** | New route, new field, new error code, new header |
| **Changed** | Existing field renamed, type changed, constraint changed, status code changed |
| **Removed** | Route removed, field removed, error code removed |
| **Deprecated** | Route or field still works but will be removed — note the sunset |
| **Fixed** | Documented behavior was wrong — this corrects the documentation |

### 3.2 Breaking vs Non-Breaking

Every change entry must be labeled breaking or non-breaking.

```
Breaking (frontend must act):
  → Field removed from response
  → Field renamed
  → Field type changed
  → Required field added to request
  → Status code changed
  → Error code renamed
  → Route URL changed
  → HTTP method changed

Non-breaking (frontend may act):
  → Optional field added to response
  → Optional field added to request
  → New route added
  → New error code added
  → Constraint relaxed (max_length increased)
```

### 3.3 Changelog Entry Format

```markdown
### [YYYY-MM-DD] [BREAKING | NON-BREAKING]

**[Added | Changed | Removed | Deprecated | Fixed]**
- [Domain] [Route]: [What changed, precisely. Field names in backticks.]

**Frontend Migration**
- [Exactly what the frontend must change to stay compatible.]
- [One action per bullet. Specific — not "update the integration".]
```

### 3.4 Changelog File for Updates

When explicitly instructed to write a changelog file, produce it at the path
specified by the user. The file covers only the changes in this update session.

```markdown
# [Domain] API — Change Report
**Date:** YYYY-MM-DD
**Breaking:** Yes / No

## What Changed

### Added
...

### Changed
...

### Removed
...

## Frontend Migration Guide

### Required Changes (Breaking)
...

### Recommended Changes (Non-Breaking)
...

## Affected Routes

| Route | Change Type | Breaking |
|-------|-------------|----------|
| `POST /migrations` | Response field renamed | Yes |
| `GET /migrations/{id}` | Response field added | No |
```

---

## Phase 4: Pagination Documentation

Any route that returns a collection must document its pagination contract.

```markdown
**Pagination**

Query parameters:

| Parameter | Type | Default | Max | Notes |
|-----------|------|---------|-----|-------|
| `page` | integer | 1 | — | 1-indexed |
| `page_size` | integer | 20 | 100 | Values above 100 return 400 |

Response envelope for paginated routes:

\`\`\`json
{
  "items": [...],
  "total": 84,
  "page": 1,
  "page_size": 20,
  "pages": 5
}
\`\`\`

`total` is the count of all matching records, not just the current page.
`pages` is derived — do not compute it on the frontend, use the value from the response.
```

---

## Phase 5: Real-Time Domain Documentation

When the domain being documented is a real-time domain (WebSocket, SSE, pub/sub),
the structure adapts. Real-time domains replace the Routes section with
Connection, Events, and Protocol sections.

### 5.1 Real-Time Document Structure

```
# [Domain Name] Real-Time API

## Overview
## Connection
## Authentication
## Event Envelope
## Server → Client Events
  ### [event.name]  (one section per event type)
## Client → Server Messages  (if bidirectional)
  ### [message.name]
## Reconnection and Resumption
## Error Codes
## Changelog
```

### 5.2 Connection Section

```markdown
## Connection

**SSE**
\`\`\`
GET /api/v1/events/stream
\`\`\`

**WebSocket**
\`\`\`
WS /api/v1/ws?token=<access_token>
\`\`\`

Authentication for WebSocket is via query parameter token — the Authorization
header is not available during the WebSocket handshake.
```

### 5.3 Event Envelope

```markdown
## Event Envelope

All server-sent events share this envelope:

\`\`\`json
{
  "event": "migration.completed",
  "data": { ... },
  "id": "uuid",
  "timestamp": "2025-01-15T10:30:00Z"
}
\`\`\`

| Field | Type | Notes |
|-------|------|-------|
| `event` | string | Dot-namespaced event type. Used to route to handler. |
| `data` | object | Event-specific payload — documented per event below. |
| `id` | UUID string | Unique event ID. Use with `Last-Event-ID` for SSE resumption. |
| `timestamp` | ISO 8601 UTC | When the event was emitted server-side. |
```

### 5.4 Event Section

```markdown
### migration.completed

Emitted when a migration finishes executing — successfully or not.
The frontend uses this to update migration status without polling.

**Payload**

\`\`\`json
{
  "migration_id": "uuid",
  "series_id": "uuid",
  "status": "completed",
  "execution_time_ms": 312,
  "error": null
}
\`\`\`

| Field | Type | Notes |
|-------|------|-------|
| `status` | enum string | `completed` or `failed` |
| `execution_time_ms` | integer | Wall time of the SQL execution |
| `error` | string \| null | null on success. Error message on failure — display to user. |
```

### 5.5 Reconnection and Resumption

```markdown
## Reconnection and Resumption

**SSE:** Send the `Last-Event-ID` header with the last received event `id`
on reconnect. The server will replay events missed since that ID.
If `Last-Event-ID` is absent or unknown, the stream starts from current.

**WebSocket:** No resumption — reconnect and re-subscribe. The server does
not replay missed events for WebSocket connections.

Both: implement exponential backoff starting at 1s, capped at 30s.
Do not reconnect immediately on close — the server may be restarting.
```

---

## Phase 6: Documentation Quality Checklist

Run before any documentation output is delivered.

```
Structure
[ ] All sections present in correct order
[ ] One domain per document — no cross-domain route inclusions
[ ] One route per ### heading — no combined route sections

Routes
[ ] Every route has a one-sentence description covering what and why
[ ] Request documents every field: type, required, constraints, notes
[ ] Request includes a complete JSON example
[ ] Response documents every field with type and notes
[ ] Response example is present and matches the field table
[ ] Status codes listed are only those this specific route can return
[ ] Error codes table covers all machine-readable codes for this route

Contracts
[ ] field values for error codes documented where applicable
[ ] meta content documented for error codes that include it
[ ] Pagination documented for all collection routes
[ ] Idempotency requirements documented where applicable
[ ] Header requirements documented at domain and route level

Real-time (if applicable)
[ ] Event envelope documented once at domain level
[ ] Every event has payload documented field by field
[ ] Reconnection and resumption behavior documented

Changelog
[ ] Every change classified (Added / Changed / Removed / Deprecated / Fixed)
[ ] Every change labeled breaking or non-breaking
[ ] Frontend migration notes present for every breaking change
[ ] Migration notes are specific actions, not general guidance
[ ] Entries in reverse chronological order
```

---

## Reference Files

`fastapi-api-contracts/SKILL.md` — The backend contract rules this documentation
describes. When a documented behavior seems inconsistent, the contract skill
defines what the backend actually guarantees.

`fastapi-backend-architecture/SKILL.md` — Domain boundaries and layer definitions.
Use this to confirm which routes belong to which domain when scope is ambiguous.
