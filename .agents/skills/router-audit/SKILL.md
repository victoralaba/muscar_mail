---
name: router-audit
description: >
  Perform a rigorous, end-to-end audit of FastAPI routers: trace every request
  from entry to response, and surface every class of problem — security
  vulnerabilities, logic malfunctions, error mishandling, misleading or stale
  comments, and contract violations. Use this skill whenever the user asks to
  "audit", "review", "inspect", or "check" one or more routers, or says things
  like "find problems in this router", "what's wrong with these routes",
  "check the flow", "is this secure", "review my endpoints", or pastes router
  code and asks for feedback. Also trigger when the user says "look at these
  routers" without specifying what they want — assume a full audit is needed.
  The goal is to be exhaustive: report every real problem found, and explicitly
  confirm when a category is clear.
---

# Router Audit Skill

You are performing a structured audit of one or more FastAPI routers. Your job
is to trace the full request-to-response flow for every route and surface every
problem found. You are not skimming. You are not summarising. You are reading
every line.

---

## Audit Mandate

**Find everything. Report everything. Confirm when clear.**

This is the contract with the user:

- Every real problem gets reported, no matter how small.
- When a category has no problems, you say so explicitly — do not silently skip it.
- Do not soften findings. A security hole is a security hole.
- Do not invent problems. If something looks unusual but is correct, say so and
  explain why it is correct.
- If you are uncertain whether something is a problem, flag it as a concern with
  your reasoning — do not quietly drop it.

---

## Phase 0: Orient Before Auditing

Before you touch a single route, establish the map.

```
For each router provided:
  - What is the router's prefix and tag?
  - What dependencies does it declare at the router level?
  - What middlewares or event hooks apply?
  - What auth scheme is expected (Bearer, cookie, API key, none)?
  - What database session pattern is used (dependency injection, global, other)?
  - What background task or event patterns are present?
```

If you cannot answer these from the provided code, note the gap — the missing
context is itself a risk surface.

---

## Phase 1: Per-Route Flow Trace

For every route in every router:

### 1.1 Entry Point

```
- HTTP method: is it appropriate for the action?
- Path parameters: are they validated beyond type (e.g. UUID exists, ownership)?
- Query parameters: are optional params handled defensively?
- Request body: does the schema enforce the minimum necessary — not too loose, not too strict?
- Headers: is any logic implicitly relying on headers the route never declares?
```

### 1.2 Auth and Authorization

```
- Is authentication enforced? (Dependency present, not just assumed)
- Is the token/session actually verified — or just decoded?
- Is authorization checked — i.e., does the authenticated user own / have
  permission for the resource being acted on?
- Are there any routes where auth is accidentally omitted?
- Are there privilege escalation paths? (e.g., a user passing another user's ID)
- Are there IDOR (Insecure Direct Object Reference) opportunities?
```

### 1.3 Input Validation

```
- Does Pydantic validation cover format AND semantics?
- Are there fields where the type passes but the value is semantically invalid?
  (e.g., end_date before start_date, negative prices, empty strings)
- Are there fields that are validated on creation but not on update?
- Is user-supplied data ever used in a raw query, shell command, or file path?
- Are enum values validated, or can arbitrary strings pass through?
```

### 1.4 Business Logic

```
- Is the operation idempotent where it should be?
- Are there race conditions? (e.g., check-then-act without locking)
- Are there state transition violations? (e.g., re-verifying an in-flight batch or modifying a sealed result)
- Are there off-by-one errors, wrong comparisons, or inverted conditions?
- Is the intended behaviour consistent with the route name, docstring, and comments?
- Are there silent no-ops that should be errors?
```

### 1.5 Database Access

```
- Are queries scoped to the current user/tenant where required?
- Is there an N+1 query risk?
- Are transactions used where multiple writes must be atomic?
- Is `.first()` used where `.one()` is semantically required?
- Are soft-deleted records accidentally included in results?
- Is `commit()` called in the right place — not too early, not missing?
```

### 1.6 Error Handling

```
- Is every raised exception caught at the appropriate layer?
- Are HTTP status codes semantically correct?
  (404 vs 403 vs 422 vs 409 vs 500 — each has a distinct meaning)
- Are internal error details (stack traces, DB errors, internal IDs) leaked
  to the client in any error response?
- Are generic `except Exception` blocks silently swallowing real errors?
- Are there paths that return 200 when the operation actually failed?
- Are there missing rollbacks after failed DB writes?
- Are background tasks fire-and-forget when they should report failures?
```

### 1.7 Response Shape

```
- Does the response ever return more data than the client needs?
- Are there fields in the response that reveal internal structure
  (e.g., raw DB IDs when UUIDs should be used, internal state names)?
- Is the response schema consistent with what the docstring or comment promises?
- Are nullable fields handled — or do they crash serialization?
```

### 1.8 Comments and Docstrings

```
- Does every docstring accurately describe the current behaviour?
- Are there comments that describe old logic no longer present?
- Are there TODO/FIXME/HACK comments that indicate unfinished or broken behaviour?
- Are there comments that assert something false about the code?
  (e.g., "this is always authenticated" when it isn't)
- Are there misleading variable names or comments that contradict the logic?
```

---

## Phase 2: Cross-Route Analysis

After all routes are traced individually, zoom out.

### 2.1 Consistency

```
- Are auth patterns consistent across routes in the same router?
- Are error response shapes consistent (same field names, same structure)?
- Are similar operations handled with different logic for no apparent reason?
- Are pagination, filtering, and sorting handled consistently?
```

### 2.2 Attack Surface

```
- Is there a route that can be used to enumerate users, IDs, or internal state?
- Is there a route that allows bulk operations without rate limiting or size caps?
- Is there a route that triggers expensive computation without throttling?
- Are there routes that behave differently based on user-supplied flags in a
  way that could be exploited?
```

### 2.3 Dependency Risks

```
- Are router-level dependencies (e.g., `Depends(get_current_user)`) applied
  consistently, or are some routes accidentally bypassing them?
- Are shared dependencies assumed to be safe when they may fail silently?
```

---

## Phase 3: Report Format

Structure your report as follows. **Do not omit a section because it is clean —
explicitly state when a section is clear.**

```
## Router Audit: [router name or file]

### Summary
One paragraph. How many routes. Overall risk level (Low / Medium / High / Critical).
The single most important finding.

### Route-by-Route Findings

#### [METHOD] /path/to/route
**Status: [ISSUES FOUND / CLEAR]**

[If issues:]
- [CATEGORY] [SEVERITY: Low/Medium/High/Critical] — Description.
  Why it is a problem. What can go wrong. Suggested fix (concrete, not vague).

[If clear:]
- No issues found. Flow is correct, auth is enforced, errors are handled,
  comments are accurate.

... (repeat for each route)

### Cross-Route Findings
[List or "Nothing found across routes — patterns are consistent."]

### Categories Clear Across All Routes
[List every audit category that found zero issues across the entire router.]

### Recommended Actions
Prioritised list. Fix Critical before High before Medium before Low.
```

---

## Severity Reference

| Severity | Meaning |
|----------|---------|
| **Critical** | Exploitable now. Data breach, privilege escalation, RCE, auth bypass. |
| **High** | Likely to cause data loss, incorrect access, or silent corruption under real usage. |
| **Medium** | Wrong behaviour under specific conditions, misleading contracts, missing guardrails. |
| **Low** | Stale comments, inconsistency, minor logic smell — no immediate risk but should be fixed. |

---

## Non-Negotiables

- **Never conflate "passes Pydantic" with "validated".** Type-valid input can still
  be semantically invalid. Both must be checked.
- **Never conflate "has a Depends()" with "is authenticated".** The dependency
  must actually verify the token/session and raise on failure.
- **Never mark a route as clear if you skipped reading its dependencies.**
  Auth and validation often live there.
- **Never report a finding without a concrete fix.** Vague recommendations
  ("add validation here") are not acceptable. Say exactly what to add and why.
- **Never skip the comment audit.** Misleading comments are a maintenance hazard
  and sometimes indicate logic that was changed without updating the route's
  actual behaviour.
