# API2:2023 — Broken Authentication

Flaws in how the API establishes and verifies identity: token issuance, token validation, credential handling, session/refresh logic. Lets an attacker impersonate a legitimate user or system.

## Detection checklist

- [ ] Are JWTs verified with a fixed algorithm and key, or does the code trust the `alg` header from the token itself (`alg: none` / algorithm-confusion attacks)?
- [ ] Are tokens checked for expiry (`exp`) and, where relevant, not-before (`nbf`) server-side, not just on the client?
- [ ] Can access tokens be used indefinitely (no expiry, or absurdly long expiry like 1 year)?
- [ ] Are refresh tokens single-use / rotated, or can a leaked refresh token be replayed forever?
- [ ] Is there a revocation path (logout invalidates tokens, password change invalidates existing sessions)?
- [ ] Are API keys/secrets passed in URLs (logged by proxies/browsers) instead of headers?
- [ ] Is credential stuffing/brute force mitigated — rate limiting, account lockout, or CAPTCHA on login/password-reset/OTP endpoints specifically (separate from general API4 rate limiting)?
- [ ] Are password reset / OTP flows using short-lived, single-use, sufficiently random tokens — not predictable or reusable?
- [ ] Do internal service-to-service calls skip auth entirely because "it's internal" (no network segmentation to back that assumption)?
- [ ] Are credentials/secrets hardcoded, committed, or logged (including in error messages or request logs)?

## Common broken pattern

```
decode_token(token, verify=False)   # or algorithm read from token header
# or
if token in DB and not check_expiry:
    ...
```

## Prevention pattern

- Verify JWTs with an explicit, server-controlled algorithm and key/secret — never trust `alg` from the token: `jwt.decode(token, key, algorithms=["RS256"])` (pin the list).
- Short-lived access tokens (minutes–hours) + rotating refresh tokens with reuse detection (if a used-up refresh token is presented again, revoke the whole token family — it means it was stolen).
- Rate-limit and lock out auth endpoints (login, OTP verify, password reset) independent of general API rate limits — these need tighter, per-account or per-IP thresholds.
- Store secrets in a secrets manager or env config, never in code or logs; scrub tokens/passwords from log output and error traces.
- For service-to-service calls, use mutual TLS or signed service tokens, not implicit network trust.

## Notes for review

- Algorithm-confusion (RS256→HS256 downgrade) is a classic, high-impact bug — specifically check that the verification key type matches the expected algorithm and that the algorithm list passed to the verifier is hardcoded, not derived from the token.
- "We use a library for this" isn't a pass — check the library is actually configured correctly (many JWT libraries default to permissive behavior for backward compatibility).
