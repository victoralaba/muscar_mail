# A10: Mishandling of Exceptional Conditions

## What it is

Errors, timeouts, resource exhaustion, and other edge cases are inevitable — this category is about what the system does when they happen. Two failure directions:

1. **Fail open** — an error in a security-relevant check (auth, authz, payment verification, rate limiting) causes the system to *proceed as if the check passed*, instead of denying by default.
2. **Fail leaky** — an unhandled exception surfaces a stack trace, internal file paths, SQL fragments, library versions, or other internals to the client, aiding an attacker's reconnaissance — or crashes in a way that causes a denial-of-service.

Both stem from the same root cause: error handling written for the happy path first, with security implications of the failure path treated as an afterthought.

## Checklist

- [ ] Every security check (auth, authz, signature verification, rate limit) fails **closed**: if the check itself throws/errors/times out, the request is denied, not allowed through.
- [ ] Unhandled exceptions return a generic error to the client (e.g. "Internal Server Error") — never a raw stack trace, DB error message, or file path — in production configuration specifically (verbose errors are fine in local dev, dangerous in prod).
- [ ] Try/except blocks around security logic don't silently swallow the exception (`except: pass`) — a swallowed exception in an authz check is functionally the same as no check at all.
- [ ] External calls (DB, third-party API, payment gateway) have explicit timeouts — a hung dependency shouldn't hang the whole request indefinitely (resource exhaustion / DoS).
- [ ] Retries on failed operations don't retry security-sensitive non-idempotent actions blindly (e.g. don't retry a payment charge without idempotency keys).
- [ ] Resource limits exist on user-controlled inputs that affect processing cost: request body size, file upload size, pagination page size, regex complexity (ReDoS), recursive/nested JSON depth, loop bounds derived from user input.
- [ ] Default/fallback values for security-relevant config are the *safe* default, not the permissive one (e.g. if a feature flag fails to load, default to "authentication required," not "authentication optional").
- [ ] Errors during multi-step operations (e.g. "create user, then send welcome email, then grant trial credits") don't leave the system in a partially-privileged inconsistent state on failure.
- [ ] Global exception handlers exist so an unexpected error anywhere in the app still returns a controlled response rather than an unhandled crash with a default framework debug page.

## Detection patterns

- Bare `except:` or `except Exception: pass` (or `catch (e) {}` in JS) around anything that determines access, especially auth/authz/signature checks.
- `DEBUG = True` (or framework equivalent) left enabled, or no explicit check that debug/verbose error pages are disabled in production.
- Auth/permission functions that return `True`/allow on an exception path rather than propagating the denial — e.g. a permission-lookup function that returns `True` if the lookup itself errors.
- No `timeout=` argument on HTTP client calls, DB connection pools, or external API calls — default (often infinite) timeouts.
- File upload or request-body handling with no explicit `MAX_CONTENT_LENGTH`/size cap.
- Regular expressions built from or applied to user input with unbounded backtracking potential (nested quantifiers like `(a+)+`) — classic ReDoS.
- A generic top-level `except Exception as e: return {"error": str(e)}` that echoes the raw exception message (which can include SQL fragments, file paths) back to the client.

## Examples

**Bad — fails open on an error in the auth check:**
```python
def check_permission(user, resource):
    try:
        return permission_service.has_access(user, resource)
    except Exception:
        return True   # "if we can't tell, let them through" — backwards
```

**Good — fails closed:**
```python
def check_permission(user, resource):
    try:
        return permission_service.has_access(user, resource)
    except Exception:
        logger.error("permission_check_failed", extra={"user_id": user.id, "resource": resource})
        return False   # deny by default when the check itself is broken
```

**Bad — leaky error response:**
```python
@app.exception_handler(Exception)
def handle_error(request, exc):
    return JSONResponse({"error": str(exc), "trace": traceback.format_exc()}, status_code=500)
```

**Good — generic response to the client, full detail only in server-side logs:**
```python
@app.exception_handler(Exception)
def handle_error(request, exc):
    error_id = uuid4()
    logger.error("unhandled_exception", extra={"error_id": str(error_id)}, exc_info=exc)
    return JSONResponse({"error": "Internal server error", "error_id": str(error_id)}, status_code=500)
```
The `error_id` lets you correlate a user's bug report with the detailed server-side log without exposing internals.

**Bad — no timeout, dependency hang becomes a DoS:**
```python
response = httpx.get(third_party_url)
```

**Good:**
```python
response = httpx.get(third_party_url, timeout=5.0)
```

## Remediation steps

1. Audit every security-relevant check (auth, authz, signature/webhook verification, rate limiting) for its behavior on exception — flip any "fail open" to "fail closed."
2. Add a global exception handler that returns a generic message to clients and logs full detail (with a correlation ID) server-side only.
3. Confirm debug/verbose error modes are explicitly disabled based on environment, not left to a default that happens to be safe.
4. Add explicit timeouts to every external call (DB, HTTP client, cache) and explicit size limits on user-controlled inputs (uploads, body size, pagination).
5. Replace bare `except: pass` around security logic with handling that logs and denies.
6. For multi-step operations with security implications, make partial-failure states safe (e.g. don't grant elevated privileges until *all* steps of an onboarding flow succeed).

## Stack notes

- **Python/FastAPI**: use `app.exception_handler` for a global catch-all; set `httpx`/`requests` timeouts explicitly since neither has a safe default; validate upload sizes via `Content-Length` checks and streaming limits, not just after reading the whole body into memory.
- **SvelteKit**: server-side (`+page.server.ts`/`+server.ts`) errors thrown without using SvelteKit's `error()` helper can leak stack traces in dev-adjacent configurations — use `error(status, message)` for expected failures and let unexpected ones hit a hardened top-level error page in production builds.
- **General**: this category is the one most likely to be "correct until it isn't" — code often works fine until the exact failure condition (timeout, malformed input, dependency outage) occurs in production, so treat the failure path as a first-class part of the design, not a leftover.
