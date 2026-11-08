---
name: fastapi-security
description: >
  Implement, audit, and enforce security practices in FastAPI backend systems with
  rigorous discipline. Use this skill for any task involving password handling,
  authentication, JWT design, authorization, secrets management, transport security,
  CORS, security headers, OWASP compliance, logging, PII handling, data protection,
  or any concern about the security posture of a FastAPI backend. Triggers include:
  "hash this password", "implement auth", "set up JWT", "secure this endpoint",
  "add CORS", "handle secrets", "what should I log", "is this secure", "OWASP",
  "rate limit this", "prevent brute force", "encrypt this", "store PII safely",
  "audit this", "add security headers", or any request where data, credentials,
  or access control are involved. ALWAYS treat the client as adversarial. ALWAYS
  assume breach is possible and design accordingly. NEVER store, log, or transmit
  secrets in plaintext.
---

# FastAPI Security Skill

> Also read `references/principles.md`. Security is applied physics: every
> vulnerability is a conservation failure (energy/information goes somewhere
> unintended), every attack is a system behaving exactly as designed but not
> as intended. The laws constrain what is permissible.

---

## Prime Directive: The Client Is Adversarial

Every system that sends data to your API is a potential attacker. This includes:
- Your own frontend operated by a legitimate user
- Your own frontend operated by a malicious user
- Automated scripts with full knowledge of your API schema
- Third-party integrations, misconfigured or compromised
- Malicious actors probing your API

**The server must behave correctly regardless of which of these is true.**

```
Every input is assumed malicious until validated
Every identity claim is verified server-side — never trusted from the client
Every response exposes only what is explicitly intended
Every error message is audited for information disclosure
Every secret is treated as already compromised if mishandled once
```

---

## Prime Directive: Defense in Depth

No single security control is sufficient. Security is layered. If one layer
fails, the next must hold.

```
Layer 1: Transport     — TLS, HSTS, secure headers
Layer 2: Perimeter     — Rate limiting, CORS, input size limits
Layer 3: Authentication — Identity verification, token validation
Layer 4: Authorization  — Permission checks, ownership checks
Layer 5: Validation    — Input sanitization, semantic checks
Layer 6: Data          — Encryption at rest, PII minimization
Layer 7: Audit         — Logging, anomaly detection, breach response
```

A gap at any layer is a vulnerability. Designing only for layer 3 is not security.

---

## Prime Directive: Assume Breach

Design every system as if an attacker will eventually get in. The question is
not "can we prevent all breaches" but "if breached, what can the attacker get,
and how quickly can we detect and respond?"

```
Minimize blast radius  — least privilege, data minimization
Maximize detectability — structured audit logs, anomaly alerting
Enable rapid response  — token revocation, account lockout, key rotation
```

---

## Phase 1: Password Security

### 1.1 Argon2id — The Only Acceptable Algorithm

**Use Argon2id. Not bcrypt. Not scrypt. Not MD5. Not SHA-256. Not PBKDF2.**

Argon2id is the winner of the Password Hashing Competition (2015) and the
current OWASP recommendation. It provides memory-hardness (defeats GPU/ASIC
attacks) and side-channel resistance simultaneously.

Bcrypt is the historical default in many frameworks. It is not broken but it
is outdated — its 72-byte password limit, lack of memory-hardness, and
inability to scale to modern hardware make it inferior. Do not use it for
new systems.

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Global hasher instance — parameters set once, used everywhere
# OWASP minimum parameters for Argon2id:
#   time_cost=2, memory_cost=19456 (19 MB), parallelism=1
# These are minimums — increase memory_cost as hardware allows
ph = PasswordHasher(
    time_cost=3,           # number of iterations
    memory_cost=65536,     # 64 MB — increase if server RAM allows
    parallelism=4,         # number of parallel threads
    hash_len=32,           # output hash length in bytes
    salt_len=16,           # salt length in bytes
    encoding="utf-8",
)

def hash_password(plaintext: str) -> str:
    """Hash a password. Returns the full encoded hash string."""
    # argon2-cffi generates a unique salt per call automatically
    return ph.hash(plaintext)

def verify_password(plaintext: str, hashed: str) -> bool:
    """
    Verify a password against its hash.
    Always runs in constant time — never short-circuits on mismatch.
    Returns True if valid, False if invalid.
    Never raises — all exceptions are caught and return False.
    """
    try:
        return ph.verify(hashed, plaintext)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError):
        # Malformed hash — treat as invalid, log anomaly
        logger.warning("Malformed password hash encountered during verification")
        return False

def needs_rehash(hashed: str) -> bool:
    """
    Check if a stored hash was created with outdated parameters.
    Call after successful verification — if True, rehash and update.
    This enables transparent parameter upgrades without forcing password resets.
    """
    return ph.check_needs_rehash(hashed)
```

### 1.2 Password Validation Rules

```python
from pydantic import BaseModel, Field, field_validator
import re

class PasswordSetRequest(BaseModel):
    password: str = Field(..., min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        errors = []

        if not re.search(r'[A-Z]', v):
            errors.append("at least one uppercase letter")
        if not re.search(r'[a-z]', v):
            errors.append("at least one lowercase letter")
        if not re.search(r'\d', v):
            errors.append("at least one digit")
        if not re.search(r'[^a-zA-Z0-9]', v):
            errors.append("at least one special character")

        if errors:
            raise ValueError(f"Password must contain: {', '.join(errors)}")

        # Check against common passwords list
        if v.lower() in COMMON_PASSWORDS:
            raise ValueError("Password is too common")

        return v
```

**Rules:**
- Minimum 12 characters, maximum 128
- Maximum exists to prevent DoS via bcrypt's O(n) behavior — also applies to Argon2
- Check against a common passwords list (haveibeenpwned API or local list)
- Never enforce complexity rules that reduce entropy (e.g., "exactly one special character")
- Never truncate passwords — hash the full input up to the maximum
- Never log passwords — not on error, not in debug mode, not ever

### 1.3 Password Handling in the Auth Flow

```python
class AuthService:
    async def login(self, db: AsyncSession, data: LoginRequest) -> TokenPair:
        user = await user_repo.get_by_email(db, email=data.email)

        # CRITICAL: Always run password verification even if user not found.
        # This prevents timing attacks that enumerate valid email addresses
        # by measuring response time differences.
        dummy_hash = "$argon2id$v=19$m=65536,t=3,p=4$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        password_hash = user.password_hash if user else dummy_hash
        is_valid = verify_password(data.password, password_hash)

        if not user or not is_valid:
            # Same error regardless of which check failed — no user enumeration
            await self._record_failed_attempt(db, email=data.email)
            raise InvalidCredentialsError()

        if not user.is_active:
            raise UserInactiveError()

        # Transparent rehash — if parameters are outdated, upgrade silently
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(data.password)
            await db.flush()

        # Record successful login
        await self._record_successful_login(db, user=user)

        return await self._issue_token_pair(db, user=user)

    async def _record_failed_attempt(self, db, email: str) -> None:
        # Increment failed attempt counter — used for account lockout
        await auth_event_repo.record(db, event="login_failed", email=email)
        count = await auth_event_repo.count_recent(db, email=email, window_minutes=15)
        if count >= 5:
            # Lock account — require email verification to unlock
            user = await user_repo.get_by_email(db, email=email)
            if user:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
                await db.flush()
```

### 1.4 Password Reset Security

```python
async def request_password_reset(self, db, email: str) -> None:
    user = await user_repo.get_by_email(db, email=email)

    # Always return success — never confirm whether email is registered
    # Timing attack: run the same work regardless of whether user exists
    token = secrets.token_urlsafe(32)  # 256 bits of entropy
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    if user:
        await password_reset_repo.create(db,
            user_id=user.id,
            token_hash=hash_password(token),  # store hash, not plaintext
            expires_at=expires_at,
        )
        await email_service.send_password_reset(user.email, token=token)

    # Return success regardless — caller never knows if email existed

async def reset_password(self, db, token: str, new_password: str) -> None:
    # Cannot look up reset record by plaintext token — it's stored hashed
    # Must verify all recent unexpired tokens (bounded by expiry window)
    reset_record = await password_reset_repo.find_valid(db, token=token)
    if not reset_record:
        raise InvalidResetTokenError()

    # Single use — invalidate immediately after use
    await password_reset_repo.invalidate(db, id=reset_record.id)

    user = await user_repo.get_or_raise(db, id=reset_record.user_id)
    user.password_hash = hash_password(new_password)

    # Invalidate all existing sessions — password change = full re-auth
    await session_repo.invalidate_all(db, user_id=user.id)
    await db.flush()
```

---

## Phase 2: JWT Security

### 2.1 Algorithm Selection

**Use RS256 (asymmetric) for distributed systems. Use HS256 (symmetric) only
for single-service systems where the signing and verification happen in the
same process.**

```
RS256 (RSA + SHA-256):
  ✓ Private key signs — kept secret on auth server
  ✓ Public key verifies — can be distributed safely
  ✓ Other services can verify without access to signing key
  ✓ Compromise of verification key does not enable token forgery
  ✗ Slower than HS256
  ✗ More complex key management

HS256 (HMAC + SHA-256):
  ✓ Simple — one key signs and verifies
  ✓ Fast
  ✗ Every service that verifies must have the secret key
  ✗ Compromise of any service exposes the signing key
  ✗ "alg: none" attack surface if library doesn't reject it explicitly

Never use: RS512 is fine but overkill. Never use: alg: none. Never use:
HS256 in a microservices architecture where multiple services verify tokens.
```

```python
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

# RS256 implementation
class JWTService:
    def __init__(self, private_key_pem: bytes, public_key_pem: bytes):
        self._private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=None,
            backend=default_backend(),
        )
        self._public_key = serialization.load_pem_public_key(
            public_key_pem,
            backend=default_backend(),
        )

    def issue_access_token(self, user_id: UUID, scopes: list[str]) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),        # subject — user identifier
            "iat": now,                  # issued at
            "exp": now + timedelta(minutes=15),  # expiry — short
            "jti": str(uuid4()),         # JWT ID — for revocation
            "type": "access",            # token type — prevent refresh token used as access
            "scopes": scopes,            # permissions
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    def verify_access_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],    # explicit — never ["RS256", "none"]
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "require": ["sub", "exp", "jti", "type"],  # required claims
                },
            )
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError()
        except jwt.InvalidTokenError as e:
            raise TokenInvalidError()

        # Explicit type check — prevent refresh token used as access token
        if payload.get("type") != "access":
            raise TokenInvalidError()

        return payload
```

### 2.2 Token Pair: Access + Refresh

```python
class JWTService:
    def issue_token_pair(self, user_id: UUID, scopes: list[str]) -> TokenPair:
        access_token = self.issue_access_token(user_id, scopes)
        refresh_token = self.issue_refresh_token(user_id)
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=900,  # 15 minutes in seconds
        )

    def issue_refresh_token(self, user_id: UUID) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(days=30),  # longer lived
            "jti": str(uuid4()),
            "type": "refresh",               # explicit type
            "family": str(uuid4()),          # token family for rotation detection
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")
```

**Token lifetime rules:**
```
Access token:  15 minutes maximum — short, cannot be revoked individually
Refresh token: 7–30 days — stored server-side hash, single-use, rotated on use
```

### 2.3 Refresh Token Rotation and Reuse Detection

```python
async def refresh(self, db: AsyncSession, refresh_token: str) -> TokenPair:
    payload = jwt_service.verify_refresh_token(refresh_token)

    jti = payload["jti"]
    family = payload["family"]
    user_id = UUID(payload["sub"])

    # Check if this refresh token has already been used
    token_record = await refresh_token_repo.get(db, jti=jti)

    if token_record is None:
        # Token not in DB at all — either expired+cleaned or never issued
        raise TokenInvalidError()

    if token_record.used:
        # REUSE DETECTED — this token was already rotated
        # An attacker may have stolen a refresh token.
        # Invalidate the entire token family — force re-login for all sessions
        # in this family to protect the legitimate user.
        await refresh_token_repo.invalidate_family(db, family=family)
        logger.warning("Refresh token reuse detected", extra={
            "user_id": str(user_id),
            "jti": jti,
            "family": family,
        })
        raise TokenRevokedError()

    # Mark old token as used
    await refresh_token_repo.mark_used(db, jti=jti)

    # Issue new token pair — new jti, same family
    new_pair = jwt_service.issue_token_pair(user_id, scopes=token_record.scopes)

    # Store new refresh token
    new_payload = jwt_service.decode_refresh_token(new_pair.refresh_token)
    await refresh_token_repo.create(db,
        jti=new_payload["jti"],
        family=family,        # preserve family for future reuse detection
        user_id=user_id,
        scopes=token_record.scopes,
        expires_at=datetime.fromtimestamp(new_payload["exp"], tz=timezone.utc),
    )

    return new_pair
```

### 2.4 Token Storage and Transmission Rules

```
Access token storage (client side):
  ✓ Memory only (JavaScript variable) — disappears on tab close
  ✓ If persistence needed: sessionStorage
  ✗ localStorage — persists across sessions, XSS accessible
  ✗ Non-HttpOnly cookies — XSS accessible

Refresh token storage (client side):
  ✓ HttpOnly, Secure, SameSite=Strict cookie — inaccessible to JavaScript
  ✗ localStorage — XSS steals it permanently
  ✗ sessionStorage — loses it on tab close (poor UX)

Transmission:
  ✓ Authorization: Bearer {token} header
  ✗ URL query parameter — logged in server logs, browser history, referrer headers
  ✗ Request body — not idiomatic, harder to intercept in middleware
```

### 2.5 JWT Claims Validation Checklist

Every token verification must check all of these. Missing any one is a vulnerability.

```python
def verify_token(self, token: str, expected_type: str) -> dict:
    payload = jwt.decode(...)   # handles exp, iat, signature

    # Additional checks jwt.decode does NOT handle automatically:

    # 1. Token type — prevents cross-type token use
    if payload.get("type") != expected_type:
        raise TokenInvalidError()

    # 2. Subject exists and is active — token may be valid but user deleted/banned
    user = await user_repo.get(db, id=UUID(payload["sub"]))
    if not user or not user.is_active or user.banned:
        raise TokenInvalidError()

    # 3. Token not revoked — jti checked against revocation store
    if await revocation_repo.is_revoked(db, jti=payload["jti"]):
        raise TokenRevokedError()

    # 4. Issued-at not in the future — clock skew attack
    now = datetime.now(timezone.utc).timestamp()
    if payload["iat"] > now + 30:  # 30 second tolerance
        raise TokenInvalidError()

    return payload
```

---

## Phase 3: Transport Security

### 3.1 Security Headers

Every response must include these headers. Register them once at middleware level.

```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Prevent browsers from MIME-sniffing the content type
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking — refuse to be embedded in iframes
        response.headers["X-Frame-Options"] = "DENY"

        # Force HTTPS for 1 year, include subdomains
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # Control what browser features are accessible
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        # Prevent referrer leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy — restrict resource loading
        # Tighten this per application — this is a safe starting default
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none';"
        )

        # Remove server fingerprinting
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)

        return response

# Register in app setup
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
```

### 3.2 CORS Configuration

CORS is a browser security feature. It does not protect server-to-server requests.
Configure it correctly — overly permissive CORS is a real vulnerability for
browser-based clients.

```python
from fastapi.middleware.cors import CORSMiddleware

# Development
if settings.ENV == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

# Production
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,   # explicit list — never ["*"]
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        max_age=600,  # preflight cache — 10 minutes
    )
```

**CORS rules:**
- Never use `allow_origins=["*"]` with `allow_credentials=True` — browsers reject this
- Never use `allow_origins=["*"]` in production — too permissive
- Explicit origin list — if a new frontend domain needs access, it must be added explicitly
- `allow_credentials=True` only if cookies or Authorization headers are used

---

## Phase 4: Secrets Management

### 4.1 What Counts as a Secret

```
Secrets:
  Database credentials (URL, password)
  JWT signing keys (private key, HMAC secret)
  API keys for third-party services
  Encryption keys
  SMTP credentials
  OAuth client secrets
  Redis/broker passwords
  Any token or key that grants access to a resource

Not secrets (but still not in code):
  Feature flags
  Configuration values that vary by environment
  Allowed origins lists
```

### 4.2 Secret Handling Rules

```
✓ Secrets come from environment variables or a secrets manager (Vault, AWS SSM)
✓ Secrets are loaded once at startup into a settings object
✓ Secrets are never logged — not on startup, not on error, not in debug mode
✓ Secrets are never returned in API responses
✓ Secrets are never committed to version control — ever
✓ .env files are in .gitignore — always
✓ Production secrets are different from development secrets — always
✓ Secrets are rotated on suspected compromise — immediately
✓ Minimum secret length: 32 bytes / 256 bits for symmetric keys

✗ Never hardcode secrets in source code
✗ Never log the settings object (it contains secrets)
✗ Never pass secrets as command-line arguments (visible in process list)
✗ Never store secrets in the database
✗ Never put secrets in Docker image layers
```

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # JWT
    JWT_PRIVATE_KEY: str    # PEM-encoded RSA private key
    JWT_PUBLIC_KEY: str     # PEM-encoded RSA public key

    # Application
    SECRET_KEY: str         # for signing cookies, CSRF tokens, etc.
    ENV: str = "production"
    ALLOWED_HOSTS: list[str]
    ALLOWED_ORIGINS: list[str]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __repr__(self) -> str:
        # Never expose secret values in repr/str
        return f"Settings(ENV={self.ENV}, ALLOWED_HOSTS={self.ALLOWED_HOSTS})"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

### 4.3 Secret Rotation

```
JWT keys:
  → Generate new key pair
  → Add new public key to verification set (support both old and new during rotation)
  → Update signing to use new private key
  → After all tokens signed with old key expire — remove old public key

Database credentials:
  → Change in database
  → Update in secrets manager
  → Restart application (new connections use new credentials)
  → Verify old credentials rejected

API keys:
  → Issue new key in third-party service
  → Update in secrets manager
  → Deploy
  → Revoke old key in third-party service
```

---

## Phase 5: OWASP Top 10 Applied to FastAPI

### A01: Broken Access Control

The most common vulnerability. Every route that accesses a resource must verify
the requesting user owns or has permission to access that specific resource.

```python
# Wrong — fetches any resource by ID regardless of ownership
@router.get("/documents/{id}")
async def get_document(id: UUID, db=Depends(get_db), user=Depends(require_auth)):
    return await document_repo.get(db, id=id)  # any user gets any document

# Correct — ownership verified
@router.get("/documents/{id}")
async def get_document(id: UUID, db=Depends(get_db), user=Depends(require_auth)):
    document = await document_repo.get(db, id=id)
    if not document or document.owner_id != user.id:
        raise ResourceNotFoundError()  # 404 — not 403, do not confirm existence
    return DocumentResponse.model_validate(document)
```

**Access control checklist:**
```
[ ] Every resource endpoint verifies ownership in service layer
[ ] Admin-only endpoints have explicit admin permission check
[ ] Horizontal privilege escalation impossible (user A cannot access user B's data)
[ ] Vertical privilege escalation impossible (user cannot elevate to admin)
[ ] Unauthorized resource access returns 404, not 403
[ ] Sequential integer IDs not used in URLs (UUIDs prevent enumeration)
[ ] Soft-deleted records excluded from all queries by default
```

### A02: Cryptographic Failures

```python
# Wrong — MD5, SHA-1, SHA-256 for passwords (fast hashes, crackable)
import hashlib
hashed = hashlib.sha256(password.encode()).hexdigest()  # never

# Wrong — bcrypt (outdated, 72-byte limit, no memory hardness)
import bcrypt
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())  # do not use for new systems

# Correct — Argon2id (see Phase 1)
hashed = hash_password(password)

# Wrong — storing encryption key in the database alongside encrypted data
# Correct — encryption key in secrets manager, separate from data

# Wrong — ECB mode for block ciphers (deterministic, reveals patterns)
# Correct — AES-GCM (authenticated encryption — both confidentiality and integrity)

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """AES-256-GCM authenticated encryption."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce — unique per encryption
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext  # prepend nonce for decryption

def decrypt(ciphertext_with_nonce: bytes, key: bytes) -> bytes:
    """AES-256-GCM authenticated decryption."""
    aesgcm = AESGCM(key)
    nonce = ciphertext_with_nonce[:12]
    ciphertext = ciphertext_with_nonce[12:]
    return aesgcm.decrypt(nonce, ciphertext, associated_data=None)
```

### A03: Injection

SQLAlchemy ORM prevents SQL injection by default. The remaining surfaces:

```python
# SQL injection surface: raw text() queries with string formatting
# Wrong
result = await db.execute(text(f"SELECT * FROM users WHERE name = '{user_input}'"))

# Correct — parameterized always
result = await db.execute(
    text("SELECT * FROM users WHERE name = :name"),
    {"name": user_input}
)

# Command injection surface: subprocess, os.system
# Wrong
import subprocess
subprocess.run(f"convert {filename} output.png", shell=True)  # shell=True is dangerous

# Correct — list arguments, never shell=True with user input
subprocess.run(["convert", safe_filename, "output.png"], shell=False)

# Template injection surface: Jinja2 with user input in template string
# Wrong
template = env.from_string(f"Hello {user_provided_template}")

# Correct — user input goes into context, never into template string
template = env.get_template("hello.html")
template.render(name=user_provided_name)

# NoSQL injection surface: MongoDB operators in JSON input
# If using MongoDB — validate that user input does not contain $ keys
def sanitize_mongo_input(data: dict) -> dict:
    return {k: v for k, v in data.items() if not k.startswith("$")}
```

### A04: Insecure Design

Security requirements defined at design time, not patched in after.

```
Every feature design must answer:
  → What happens if a malicious user calls this?
  → What is the maximum damage a single compromised account can do?
  → What data does this expose and to whom?
  → What happens if this is called 10,000 times per minute?
  → What does a failed attempt reveal?
```

### A05: Security Misconfiguration

```python
# Debug mode disabled in production — exposes stack traces and internals
if settings.ENV == "production":
    assert not settings.DEBUG, "DEBUG must be False in production"

# OpenAPI docs disabled in production (optional — assess per deployment)
app = FastAPI(
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url="/redoc" if settings.ENV != "production" else None,
    openapi_url="/openapi.json" if settings.ENV != "production" else None,
)

# Default credentials changed — no "admin/admin", no default API keys
# Database not exposed to public internet — only accessible from application tier
# Unused HTTP methods disabled
# Error responses never contain stack traces or internal paths
```

### A06: Vulnerable and Outdated Components

```bash
# Pin all dependencies — no floating versions in production
# requirements.txt or pyproject.toml with exact versions

# Audit regularly
pip audit                          # checks for known vulnerabilities
safety check                       # alternative auditor

# Automate — add to CI pipeline
# Run pip audit on every PR and block merge if critical vulnerabilities found
```

### A07: Identification and Authentication Failures

Covered in Phase 1 (passwords) and Phase 2 (JWT). Key points:

```
✓ Argon2id for password hashing
✓ Constant-time password comparison
✓ Account lockout after N failed attempts
✓ Short-lived access tokens (15 minutes)
✓ Refresh token rotation with reuse detection
✓ Token revocation on password change
✓ Token revocation on logout
✓ Multi-factor authentication for sensitive operations
✓ Secure password reset (token stored hashed, single-use, expires in 1 hour)
```

### A08: Software and Data Integrity Failures

```python
# Verify webhook signatures — never trust webhook payload without verification
import hmac
import hashlib

def verify_webhook_signature(
    payload: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    # Constant-time comparison — prevent timing attacks on signature verification
    return hmac.compare_digest(expected, received)

@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(..., alias="Stripe-Signature"),
):
    payload = await request.body()
    if not verify_webhook_signature(payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET):
        raise WebhookSignatureInvalidError()
    # Process webhook
```

### A09: Security Logging and Monitoring Failures

Covered in Phase 6. Key requirement: security events must be logged with enough
context to reconstruct an attack after the fact.

### A10: Server-Side Request Forgery (SSRF)

```python
# SSRF surface: any endpoint that fetches a URL provided by the client
# An attacker provides internal URLs to probe your infrastructure

import ipaddress
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"https"}
BLOCKED_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0",
    "169.254.169.254",  # AWS metadata service
    "metadata.google.internal",  # GCP metadata service
}

def validate_external_url(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise InvalidURLError(f"Only HTTPS URLs are permitted")

    host = parsed.hostname
    if not host:
        raise InvalidURLError("Invalid URL")

    if host.lower() in BLOCKED_HOSTS:
        raise InvalidURLError("URL points to a blocked host")

    # Block private IP ranges
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise InvalidURLError("URL points to a private network address")
    except ValueError:
        pass  # hostname, not IP — DNS resolution happens at fetch time

    return url
```

---

## Phase 6: Security Logging and Audit Trails

### 6.1 What to Log

```python
import structlog

security_logger = structlog.get_logger("security")

# Security events that must always be logged:
SECURITY_EVENTS = {
    # Authentication
    "auth.login.success":       "User authenticated successfully",
    "auth.login.failed":        "Authentication attempt failed",
    "auth.login.locked":        "Account locked after failed attempts",
    "auth.logout":              "User logged out",
    "auth.token.refreshed":     "Access token refreshed",
    "auth.token.reuse_detected":"Refresh token reuse detected — possible theft",
    "auth.password.changed":    "Password changed",
    "auth.password.reset":      "Password reset completed",
    "auth.mfa.failed":          "MFA verification failed",

    # Authorization
    "authz.denied":             "Access denied to resource",
    "authz.privilege_escalation_attempt": "User attempted unauthorized privilege escalation",

    # Data
    "data.export":              "Data export requested",
    "data.bulk_delete":         "Bulk delete operation performed",
    "data.pii_accessed":        "PII data accessed",

    # Admin
    "admin.user.created":       "Admin created user",
    "admin.user.deleted":       "Admin deleted user",
    "admin.role.changed":       "Admin changed user role",
    "admin.config.changed":     "System configuration changed",

    # Anomalies
    "anomaly.rate_limit_hit":   "Rate limit exceeded",
    "anomaly.invalid_token":    "Invalid token presented",
    "anomaly.webhook.invalid_signature": "Webhook signature verification failed",
}

def log_security_event(
    event: str,
    user_id: UUID | None = None,
    request: Request | None = None,
    **context,
) -> None:
    security_logger.info(
        event,
        user_id=str(user_id) if user_id else None,
        ip_address=request.client.host if request else None,
        user_agent=request.headers.get("User-Agent") if request else None,
        path=str(request.url.path) if request else None,
        **context,
    )
```

### 6.2 What Never to Log

```
✗ Passwords — plaintext or hashed
✗ Full JWT tokens — log only the jti claim
✗ Full credit card numbers — log only last 4 digits
✗ Full API keys — log only first 8 characters
✗ SSN, passport numbers, national ID
✗ Full session tokens
✗ Private keys or HMAC secrets
✗ The settings object (contains all secrets)
✗ Full request bodies for auth endpoints (contain passwords)
✗ Personal health information
```

### 6.3 Structured Log Format

```python
# Every security event log entry must include:
{
    "event": "auth.login.failed",           # event type
    "timestamp": "2025-01-15T10:30:00Z",   # UTC ISO 8601
    "user_id": "uuid-or-null",             # who (if known)
    "ip_address": "1.2.3.4",              # where from
    "user_agent": "Mozilla/5.0...",        # client
    "path": "/api/v1/auth/login",          # what endpoint
    "request_id": "uuid",                  # correlate with request logs
    # event-specific context:
    "email": "user@example.com",           # for login events (not password)
    "failure_reason": "invalid_credentials" # safe reason code, not detail
}
```

---

## Phase 7: Rate Limiting and Brute Force Prevention

### 7.1 Rate Limiting by Endpoint Sensitivity

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Authentication — strictest limits, brute force target
@router.post("/auth/login")
@limiter.limit("5/minute;20/hour")
async def login(...): ...

@router.post("/auth/register")
@limiter.limit("3/minute;10/hour")
async def register(...): ...

@router.post("/auth/password-reset")
@limiter.limit("3/hour")
async def request_password_reset(...): ...

# Sensitive operations
@router.post("/payments")
@limiter.limit("10/minute")
async def create_payment(...): ...

# Standard operations
@router.post("/resources")
@limiter.limit("60/minute")
async def create_resource(...): ...

# Read operations
@router.get("/resources")
@limiter.limit("300/minute")
async def list_resources(...): ...
```

### 7.2 Account Lockout

```python
class AccountLockoutService:
    MAX_ATTEMPTS = 5
    WINDOW_MINUTES = 15
    LOCKOUT_MINUTES = 30

    async def check_and_increment(self, db, identifier: str) -> None:
        """
        Check if identifier (email or IP) is locked out.
        Increment attempt counter.
        Lock if threshold exceeded.
        Raises AccountLockedError if currently locked.
        """
        lockout = await lockout_repo.get(db, identifier=identifier)

        if lockout and lockout.locked_until > datetime.now(timezone.utc):
            remaining = (lockout.locked_until - datetime.now(timezone.utc)).seconds // 60
            raise AccountLockedError(locked_until=lockout.locked_until, remaining_minutes=remaining)

        count = await attempt_repo.count_recent(
            db,
            identifier=identifier,
            window_minutes=self.WINDOW_MINUTES,
        )

        await attempt_repo.record(db, identifier=identifier)

        if count + 1 >= self.MAX_ATTEMPTS:
            locked_until = datetime.now(timezone.utc) + timedelta(minutes=self.LOCKOUT_MINUTES)
            await lockout_repo.upsert(db, identifier=identifier, locked_until=locked_until)
            log_security_event("auth.login.locked", ip_address=identifier)

    async def clear(self, db, identifier: str) -> None:
        """Clear attempts and lockout on successful authentication."""
        await attempt_repo.clear(db, identifier=identifier)
        await lockout_repo.clear(db, identifier=identifier)
```

---

## Phase 8: PII and Data Protection

### 8.1 Data Minimization

```
Collect only what is necessary for the stated purpose.
Store only as long as necessary.
Expose only what the requesting user is entitled to see.

Before adding any PII field to a schema, answer:
  → Why do we need this?
  → How long do we need it?
  → Who is allowed to see it?
  → What happens when a user requests deletion?
```

### 8.2 PII Field Handling

```python
# Encrypt PII at rest — sensitive fields encrypted in DB
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class PIIEncryptionService:
    def __init__(self, key: bytes):
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ciphertext).decode()

    def decrypt(self, encrypted: str) -> str:
        data = base64.b64decode(encrypted)
        nonce, ciphertext = data[:12], data[12:]
        return self._aesgcm.decrypt(nonce, ciphertext, None).decode()

# ORM model — PII stored encrypted
class UserProfile(Base):
    id: Mapped[UUID] = mapped_column(primary_key=True)
    # Stored as encrypted blob — decrypted in service layer only when needed
    phone_number_encrypted: Mapped[str | None] = mapped_column(nullable=True)
    national_id_encrypted: Mapped[str | None] = mapped_column(nullable=True)
```

### 8.3 Right to Deletion

```python
async def delete_user_data(self, db, user_id: UUID) -> None:
    """
    GDPR/right-to-erasure implementation.
    Hard delete PII. Anonymize records that must be retained for legal/audit reasons.
    """
    user = await user_repo.get_or_raise(db, id=user_id)

    # Anonymize audit logs — retain for compliance, remove PII
    await audit_log_repo.anonymize_user(db, user_id=user_id)

    # Hard delete PII fields
    user.email = f"deleted_{user_id}@deleted.invalid"
    user.display_name = "Deleted User"
    user.phone_number_encrypted = None
    user.national_id_encrypted = None
    user.deleted_at = datetime.now(timezone.utc)

    # Revoke all tokens
    await refresh_token_repo.invalidate_all(db, user_id=user_id)

    await db.flush()
    log_security_event("data.user.deleted", user_id=user_id)
```

---

## Phase 9: Security Checklist

Run this before any auth, data handling, or API work is marked complete.

```
Passwords
[ ] Argon2id used — not bcrypt, not any fast hash
[ ] Constant-time verification (verify_password never short-circuits)
[ ] Dummy hash used in login flow to prevent email enumeration via timing
[ ] Password reset tokens stored as hash, single-use, expire in 1 hour
[ ] Account lockout after 5 failed attempts in 15 minutes
[ ] All sessions invalidated on password change

JWT
[ ] RS256 for multi-service, HS256 only for single-service
[ ] Access tokens expire in 15 minutes or less
[ ] Refresh tokens are single-use, rotated on use
[ ] Token reuse detection invalidates entire token family
[ ] Token type claim validated explicitly (prevent cross-type use)
[ ] User existence and active status verified on every token use
[ ] Tokens revoked on logout and password change

Transport
[ ] All security headers present (HSTS, CSP, X-Frame-Options, etc.)
[ ] CORS origin list is explicit — no wildcard in production
[ ] Server version headers removed
[ ] TLS enforced — no HTTP in production

Secrets
[ ] No secrets in source code
[ ] No secrets in logs
[ ] No secrets in API responses
[ ] .env in .gitignore
[ ] Production secrets differ from development secrets

Access control
[ ] Every resource endpoint verifies ownership
[ ] 404 returned for unauthorized resource access (not 403)
[ ] UUIDs used in URLs (not sequential integers)
[ ] Soft-deleted records excluded by default

Input
[ ] All string fields bounded (min_length, max_length)
[ ] All numeric fields bounded (ge, le)
[ ] File uploads validated for size and MIME type
[ ] No raw string formatting in SQL queries
[ ] External URLs validated against SSRF blocklist

Logging
[ ] All security events logged with user_id, ip, path, timestamp
[ ] No passwords, tokens, or secrets in logs
[ ] Failed auth attempts logged
[ ] Privilege escalation attempts logged

Data
[ ] PII fields encrypted at rest
[ ] Data minimization applied — no unnecessary PII collected
[ ] Right-to-deletion implemented
[ ] Audit logs anonymized on user deletion
```

---

## Reference Files

`references/principles.md` — Security is physics. Conservation of information:
data put into a system goes somewhere. Use the laws to reason about where secrets
go, where attack surface exists, and what invariants must hold under adversarial
conditions.

`fastapi-api-contracts/SKILL.md` — API contract design with security as a
first-class concern: request validation, auth dependencies, response shaping,
error envelopes, rate limiting, and enumeration prevention.

`fastapi-backend-architecture/SKILL.md` — Layer boundaries and responsibility
separation. Security controls belong at specific layers — knowing the architecture
prevents misplacing them.

`fastapi-debugging/SKILL.md` — When a security control fails (auth bypass,
token validation error, permission check not firing), use the debugging skill
to trace the root cause without introducing new vulnerabilities in the fix.
