# A07: Authentication Failures

## What it is

Weaknesses in how the system establishes and maintains a user's identity — password handling, session/token management, multi-factor auth, credential recovery — that let an attacker impersonate a legitimate user without needing to break access control logic (that's A01) or crypto primitives directly (that's A04, though the two overlap on password storage).

## Checklist

- [ ] Passwords are hashed with argon2id/bcrypt (see A04) with a per-password salt (handled automatically by these libraries)
- [ ] No maximum password length that's suspiciously short (a cap under ~64 chars often signals the password is being handled unsafely upstream); a sane minimum length is enforced (12+ recommended)
- [ ] Login endpoint has rate limiting / lockout / backoff to resist brute force and credential stuffing
- [ ] Login error messages don't distinguish "wrong password" from "user doesn't exist" (prevents user enumeration)
- [ ] Session tokens/JWTs are generated with sufficient entropy (see A04), transmitted only over HTTPS, and stored appropriately (`HttpOnly`, `Secure`, `SameSite` cookies — not `localStorage` for session tokens if avoidable, since that's readable by any XSS)
- [ ] Sessions/tokens expire (both idle timeout and absolute max lifetime); logout actually invalidates the session server-side, not just clears the client cookie
- [ ] Password reset tokens are single-use, short-lived, and invalidate the old session on successful reset
- [ ] Password reset flow doesn't leak whether an email/account exists (same response either way)
- [ ] MFA is available for sensitive accounts/actions, and MFA bypass isn't possible via a parallel unauthenticated flow
- [ ] Credential changes (password/email change) require re-authentication or the current password, not just an active session
- [ ] No hardcoded/default credentials anywhere in the codebase or deploy config

## Detection patterns

Language-agnostic:
- Login handler with no rate limiting / attempt counting
- Different error messages or response codes/timings for "user not found" vs "wrong password"
- Session/JWT stored in `localStorage`/`sessionStorage` (readable by JS, i.e. any XSS = full session theft) instead of an `HttpOnly` cookie
- No expiry claim (`exp`) on issued JWTs, or expiry checked only client-side
- Password reset token that's short, sequential, or reused after being consumed

Stack-specific:
- **FastAPI**: manually rolled JWT handling without checking `exp`/`nbf`; session cookie set without `httponly=True, secure=True, samesite="lax"/"strict"`
- **SvelteKit**: auth token read from a store/localStorage in a component instead of validated server-side in `hooks.server.ts`; `locals.user` set from a client-supplied header without verifying a signed cookie/token first
- **OAuth/social login**: `state` parameter not validated (CSRF on the OAuth flow); redirect URI not strictly validated against an allowlist (open redirect enabling token theft)

## Bad vs good examples

**Rate limiting login**
```python
# Bad — unlimited attempts
@router.post("/login")
def login(creds: LoginRequest):
    user = authenticate(creds.email, creds.password)
    ...

# Good — pair with a rate limiter (per-IP and per-account) at the middleware/dependency level
@router.post("/login")
@limiter.limit("5/minute")
def login(creds: LoginRequest):
    user = authenticate(creds.email, creds.password)
    ...
```

**User enumeration via error messages**
```python
# Bad
if not user:
    raise HTTPException(400, "No account with that email")
if not verify_password(user, password):
    raise HTTPException(400, "Incorrect password")

# Good — identical response either way
if not user or not verify_password(user, password):
    raise HTTPException(400, "Invalid email or password")
```

**Session cookie flags**
```python
# Bad
response.set_cookie("session", token)

# Good
response.set_cookie(
    "session", token,
    httponly=True, secure=True, samesite="lax", max_age=3600,
)
```

## Remediation (priority order)

1. Add rate limiting/lockout to login and password-reset endpoints — this is the most commonly automated attack (credential stuffing).
2. Unify error messages/timing for auth failures to prevent enumeration.
3. Move session tokens out of `localStorage` into `HttpOnly` cookies if currently otherwise.
4. Ensure server-side session invalidation on logout, not just client-side cookie clearing.
5. Verify password reset tokens are single-use and short-lived; add invalidation of active sessions on password change.
6. Add MFA for high-value accounts/actions if not present.
