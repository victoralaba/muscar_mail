# A09: Security Logging and Alerting Failures

## What it is

Even a well-defended system gets probed and occasionally breached. This category is about whether anyone would *know*: are security-relevant events (logins, failed logins, permission denials, password/email changes, admin actions, payment events) logged with enough detail to reconstruct what happened, and is anything actually watching those logs for signs of attack? A perfect audit trail nobody reads is only half the fix.

## Checklist

- [ ] Authentication events are logged: successful login, failed login (with reason category, not raw password), logout, password reset request/completion, MFA enrollment/failure.
- [ ] Authorization failures (403s, denied access attempts) are logged, especially repeated denials from the same user/IP (signals probing).
- [ ] Sensitive state changes are logged: role changes, permission grants, payment/financial actions, data export/deletion.
- [ ] Logs include enough context to investigate: timestamp, actor (user ID, not just session token), source IP, action, target resource — without over-logging PII/secrets (see below).
- [ ] Logs are never missing entirely for an entire class of action because "it seemed unimportant at the time" — err toward logging security-relevant events even if unsure.
- [ ] Logs are protected from tampering/deletion by the very users they might incriminate (write to an append-only store or a separate logging service, not a table the compromised app account can freely DELETE from).
- [ ] Some form of alerting/monitoring exists for high-signal events (repeated failed logins, privilege escalation, mass data export) rather than logs that are only ever read after the fact during an incident.
- [ ] Logs exclude secrets, passwords, full credit card numbers, session tokens, and other sensitive fields (log the *event*, not the *payload* verbatim) — see A04 for what counts as sensitive.
- [ ] Log format is structured (JSON or similar), not free-text string concatenation, so it's actually queryable during an incident.
- [ ] Clock sync (NTP) across services so correlating events across a distributed system is possible.

## Detection patterns

- Auth/authz code paths (login handlers, permission-check middleware, password reset flows) with no corresponding `logger.info`/`logger.warning` call on failure.
- `logger.info(f"User {user} logged in with password {password}")` — logging the secret itself, not just the event.
- Bare `except: pass` or `except Exception: pass` around security-relevant operations — swallows the failure silently instead of logging it (also see A10).
- Logs written to a table/file the application's own runtime credentials can freely modify or delete (no separation between "app can write" and "app can also delete/edit its own history").
- No log entries at all around auth/permission code when grepping the codebase for `log`/`logger`/`logging` near those functions.
- Generic catch-all error logs ("something went wrong") that don't distinguish a security-relevant failure (auth denial) from a benign one (validation error on a form field).

## Examples

**Bad — no logging on auth failure:**
```python
def login(username, password):
    user = get_user(username)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return create_session(user)
```

**Good — structured logging on both outcomes, no secrets logged:**
```python
def login(username, password, request):
    user = get_user(username)
    if not user or not verify_password(password, user.password_hash):
        logger.warning("login_failed", extra={
            "username_attempted": username,   # ok to log the attempted username
            "source_ip": request.client.host,
            "reason": "invalid_credentials",
        })
        raise HTTPException(401, "Invalid credentials")
    logger.info("login_success", extra={"user_id": user.id, "source_ip": request.client.host})
    return create_session(user)
```

**Bad — logging secrets:**
```python
logger.info(f"Password reset requested for {email} with token {reset_token}")
```
A leaked/misconfigured log sink now hands out valid reset tokens.

**Good — log the event, not the secret:**
```python
logger.info("password_reset_requested", extra={"user_id": user.id})
```

## Remediation steps

1. Enumerate the security-relevant events for the app (auth, authz denials, privileged actions, data export) and confirm each has a log call on both success and failure paths.
2. Adopt structured logging (JSON) with a consistent event-name/field schema so logs are queryable during an incident, not just human-readable prose.
3. Route logs to a destination the application's own compromised credentials can't delete or rewrite (separate log-shipping service, write-only sink, or a managed logging platform).
4. Add basic alerting for high-signal patterns: N failed logins from one account/IP in a window, a permission-denied burst, an unusual admin action outside business hours — doesn't need to be sophisticated to be useful.
5. Scrub log statements for secrets/PII — passwords, tokens, full card numbers, session IDs — replace with a redacted placeholder or a non-reversible identifier.
6. Sync clocks (NTP) across all services so timestamps can be correlated during investigation.

## Stack notes

- **Python/FastAPI**: use `logging` with a structured formatter (or a library like `structlog`) rather than bare `print()`; attach request context (user ID, IP) via middleware so every log line in a request has it.
- **Frontend**: security-relevant events that originate client-side (e.g. "user disabled MFA prompt," suspicious client-side navigation) still need to be reported to the server to be logged centrally — client-only console logs are invisible to the team and to attackers-covering-tracks alike, in the wrong direction.
- **General**: logging infrastructure is often the first thing skipped under deadline pressure on solo/small-team projects — treat "log the security-relevant path" as part of the definition of done for auth/permission code, not a follow-up task.
