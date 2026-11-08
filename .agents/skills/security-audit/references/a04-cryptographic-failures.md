# A04: Cryptographic Failures

## What it is

Sensitive data is exposed because it wasn't encrypted when it should have been, was encrypted with a weak/broken algorithm, or the keys used to protect it were poorly managed (hardcoded, reused, never rotated, too short). This covers data at rest, data in transit, and password/secret storage specifically.

## Checklist

- [ ] Sensitive data at rest (PII, tokens, financial data) is encrypted using a current, vetted algorithm (AES-256-GCM, not DES/3DES/RC4)
- [ ] All data in transit uses TLS; no plaintext HTTP for anything carrying credentials or sensitive data; TLS certificate verification is never disabled (`verify=False`, `rejectUnauthorized: false`)
- [ ] Passwords are hashed with a purpose-built slow hash (argon2id, bcrypt, scrypt) — never plain SHA-256/MD5, never encrypted-and-decryptable
- [ ] No custom/homegrown crypto — use vetted libraries only
- [ ] Keys and secrets are not hardcoded in source, not committed to version control, not baked into container images
- [ ] Keys are generated with a cryptographically secure RNG (language's `secrets`/`crypto.randomBytes`, never `random`/`Math.random` for anything security-relevant)
- [ ] Key rotation is possible without a full redeploy/re-encryption disaster (versioned keys, KMS-backed)
- [ ] Sensitive data isn't unnecessarily retained (don't store what you don't need; don't log secrets — see A09)
- [ ] Random tokens (session IDs, password-reset tokens, API keys) are long enough and generated securely, not predictable (sequential IDs, timestamp-based)
- [ ] Encryption is authenticated (AES-GCM, not AES-CBC without a MAC) to prevent tampering, not just confidentiality

## Detection patterns

Language-agnostic:
- Grep for `md5(`, `sha1(` used in a password/security context (fine for non-security checksums, not fine for passwords)
- Grep for `verify=False`, `rejectUnauthorized: false`, `InsecureSkipVerify: true`, `ssl._create_unverified_context`
- Hardcoded strings that look like keys/secrets (`AKIA...`, `-----BEGIN PRIVATE KEY-----`, long hex/base64 constants assigned to vars named `key`/`secret`/`token`)
- `random.random()`, `Math.random()`, or non-CSPRNG used to generate anything named token/key/secret/nonce
- HTTP (not HTTPS) URLs hardcoded for API calls that carry credentials

Stack-specific:
- **Python**: `hashlib.md5`/`hashlib.sha1` for password hashing instead of `passlib`/`argon2-cffi`/`bcrypt`; `random` module instead of `secrets` for tokens
- **JS/TS**: `crypto.createHash('md5')` for passwords; `Math.random()` for anything security-relevant instead of `crypto.randomBytes`/`crypto.getRandomValues`
- **Env/config**: `.env` files committed to git with real secrets (check `git log` for historical commits too — removing from HEAD doesn't remove from history); secrets passed as plain environment variables in a way that's visible in process listings or CI logs

## Bad vs good examples

**Password hashing (Python)**
```python
# Bad
import hashlib
hashed = hashlib.sha256(password.encode()).hexdigest()

# Good
from argon2 import PasswordHasher
ph = PasswordHasher()
hashed = ph.hash(password)
# verify: ph.verify(hashed, password)  — raises on mismatch, handles timing safely
```

**Secure token generation**
```python
# Bad
import random
reset_token = str(random.randint(100000, 999999))

# Good
import secrets
reset_token = secrets.token_urlsafe(32)
```
```ts
// Bad
const token = Math.random().toString(36).slice(2);

// Good
const token = crypto.randomUUID(); // or crypto.getRandomValues for raw bytes
```

**TLS verification**
```python
# Bad — disables the entire point of TLS
requests.get(url, verify=False)

# Good — fix the actual cert problem (correct CA bundle, valid cert) instead of disabling verification
requests.get(url)
```

## Remediation (priority order)

1. Fix any disabled TLS verification immediately — this is Critical severity, full MITM exposure.
2. Move any hardcoded secret out of source into a secrets manager or env var injected at runtime; rotate the exposed secret (assume it's compromised the moment it was committed).
3. Replace fast hashes (MD5/SHA-*) used for passwords with argon2id/bcrypt.
4. Replace non-CSPRNG randomness used for tokens/keys with the language's secure RNG.
5. Add `git-secrets`/`gitleaks`/similar to CI to catch future secret commits.
6. Set up a KMS or secrets manager for anything beyond a single-developer hobby project, so rotation doesn't require a redeploy.
