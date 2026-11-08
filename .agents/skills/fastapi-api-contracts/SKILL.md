---
name: fastapi-api-contracts
description: >
  Design, implement, and enforce FastAPI API routes, request/response contracts,
  and client trust boundaries with rigorous discipline. Use this skill for any task
  involving route design, request validation, response shaping, authentication,
  authorization, idempotency, rate limiting, contract versioning, WebSocket/SSE
  event contracts, or any concern about what the API exposes, accepts, or guarantees.
  Triggers include: "design this endpoint", "validate this input", "secure this route",
  "add auth to this", "design the response shape", "version this API", "add rate limiting",
  "design the websocket events", "this endpoint accepts too much", "the client is sending
  wrong data", "how should I structure this contract", or any request where the boundary
  between client and server is being defined or enforced. ALWAYS treat the client as
  untrusted. ALWAYS validate at every boundary. NEVER expose internal state.
---

# FastAPI API Routes and Contracts Skill

> Also read `references/principles.md`. The laws there apply directly: conservation
> (what goes in must be accounted for), invariants (contracts that must always hold),
> and causality (a broken contract is always the server's fault, never the client's).

---

## Prime Directive: The Client Is Adversarial

This is not paranoia. It is the correct mental model.

The client is any system that sends data to your API. It may be:
- Your own frontend, operated by a legitimate user
- Your own frontend, operated by a malicious user
- A third-party integration, misconfigured
- An automated script probing your API
- A malicious actor with full knowledge of your API schema

**The server must behave correctly regardless of which of these is true.**

This means:
```
Every input is assumed malicious until proven valid
Every claim the client makes (identity, permissions, data shape) is verified server-side
Every response exposes only what is explicitly intended — nothing more
The server never trusts that the client sent what it claims to have sent
The server never trusts that the client is who it claims to be
The server never trusts that the client's data is consistent with its own prior state
```

A route that assumes the client sends correct data is a vulnerability.
A route that assumes the client is authenticated because it has a token is a vulnerability.
A route that returns more data than requested because it's "harmless" is a vulnerability.

---

## Prime Directive: Validation Is Not Pydantic Passing

Pydantic validation is type checking. It is necessary but not sufficient.

**True validation means:**
```
Type valid       → Pydantic handles this
Format valid     → Pydantic handles this (regex, min/max)
Semantically valid → You handle this (does this UUID exist? does this state transition make sense?)
Contextually valid → You handle this (does this user own this resource? is this action permitted now?)
Temporally valid  → You handle this (is this request within its valid time window?)
```

A request that passes Pydantic validation and fails semantic validation must be
rejected with the same discipline as a malformed request. The only difference is
the error code and message.

---

## Phase 1: Route Design

### 1.1 Route Anatomy

Every route has seven concerns. All seven must be explicitly addressed.

```
1. Identity      — What resource or action does this route represent?
2. Method        — Does the HTTP method match the semantics of the operation?
3. Auth          — What authentication is required?
4. Permission    — What authorization is required beyond authentication?
5. Input         — What does this route accept, and what does it reject?
6. Output        — What does this route return, always, in every case?
7. Side effects  — What does this route change, and is that change safe to repeat?
```

None of these can be implicit. An implicit concern is an unhandled concern.

### 1.2 HTTP Method Semantics

Use HTTP methods for what they mean. Misuse creates client confusion and
breaks caching, idempotency, and retry behavior.

| Method | Semantics | Idempotent | Safe | Body |
|--------|-----------|------------|------|------|
| GET | Retrieve a resource or collection | Yes | Yes | No |
| POST | Create a resource or trigger an action | No | No | Yes |
| PUT | Replace a resource entirely | Yes | No | Yes |
| PATCH | Partially update a resource | No* | No | Yes |
| DELETE | Remove a resource | Yes | No | No |

*PATCH is idempotent in practice if implemented correctly — same patch applied
twice produces the same result. Design it that way.

**Rules:**
- GET never mutates state — ever. No GET endpoints that create, update, or delete.
- POST for resource creation returns 201 with the created resource in the body
- DELETE returns 204 with no body
- PUT requires the full resource shape — partial data on a PUT is a logic bug
- PATCH uses `exclude_unset=True` on the request model — fields not sent are not changed

### 1.3 URL Design

```
/resources                          → collection
/resources/{id}                     → single resource
/resources/{id}/sub-resources       → nested collection owned by resource
/resources/{id}/actions/action-name → action that doesn't fit CRUD (use POST)

# Good
POST   /migrations/{id}/actions/execute
POST   /users/{id}/actions/deactivate
POST   /invoices/{id}/actions/send

# Bad — verb in URL
POST   /execute-migration/{id}
GET    /get-user/{id}
POST   /deactivate-user/{id}
```

**Rules:**
- Lowercase, hyphen-separated path segments
- Nouns for resources, never verbs (except `/actions/` sub-resource for non-CRUD operations)
- No trailing slashes
- IDs are always UUIDs — never sequential integers exposed in URLs
  (sequential integers reveal resource count and enable enumeration attacks)
- Nested routes maximum two levels deep — beyond that, flatten with query params

### 1.4 Complete Route Template

Every route must be written to this template. No exceptions.

```python
@router.post(
    "/resources",
    response_model=ResourceResponse,      # always explicit
    status_code=status.HTTP_201_CREATED,  # always explicit
    summary="Create a resource",          # OpenAPI docs
    description="...",                    # OpenAPI docs
    responses={                           # document all error responses
        409: {"model": ErrorResponse, "description": "Resource already exists"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def create_resource(
    body: ResourceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),         # authentication
    _: None = Depends(require_permission("resource:create")),  # authorization
) -> ResourceResponse:
    return await resource_service.create(
        db,
        user_id=current_user.id,
        data=body,
    )
```

---

## Phase 2: Request Validation

### 2.1 Pydantic Schema Design for Untrusted Input

Every request schema is a security boundary. Design it as one.

```python
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic import ConfigDict
import re

class ResourceCreateRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,   # strip leading/trailing whitespace
        str_max_length=10_000,       # global max string length — prevents payload bloat
    )

    # Every string field has explicit bounds — no unbounded strings
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Resource name",
    )

    # Enum fields use Python enums — never raw strings for controlled vocabularies
    status: ResourceStatus = Field(
        default=ResourceStatus.DRAFT,
        description="Initial status",
    )

    # Numeric fields have explicit bounds — no unbounded numbers
    priority: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Priority 0-100",
    )

    # List fields have max length — prevents unbounded array attacks
    tags: list[str] = Field(
        default_factory=list,
        max_length=20,               # max 20 tags
    )

    # Each tag also constrained
    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: list[str]) -> list[str]:
        for tag in tags:
            if len(tag) > 50:
                raise ValueError("Each tag must be 50 characters or fewer")
            if not re.match(r'^[a-z0-9\-]+$', tag):
                raise ValueError("Tags must be lowercase alphanumeric with hyphens only")
        return list(set(tags))  # deduplicate

    # Cross-field validation — semantic consistency
    @model_validator(mode="after")
    def validate_consistency(self) -> "ResourceCreateRequest":
        if self.status == ResourceStatus.PUBLISHED and not self.name:
            raise ValueError("Published resources must have a name")
        return self
```

### 2.2 The Threat Surface of Each Input Type

Every input type has a specific attack surface. Know it.

#### String Inputs
```python
# Threats: SQL injection (mitigated by ORM), XSS (mitigate at output),
#          path traversal, command injection, oversized payloads, Unicode abuse

name: str = Field(..., min_length=1, max_length=255)

# For fields that will be used in file paths or shell commands — extra validation
@field_validator("filename")
@classmethod
def validate_filename(cls, v: str) -> str:
    # No path traversal
    if ".." in v or "/" in v or "\\" in v:
        raise ValueError("Invalid filename")
    # No null bytes
    if "\x00" in v:
        raise ValueError("Invalid filename")
    # Explicit allowlist of characters
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', v):
        raise ValueError("Filename must be alphanumeric with underscores, hyphens, dots")
    return v
```

#### Numeric Inputs
```python
# Threats: integer overflow, negative values where nonsensical,
#          values that trigger expensive operations (page_size=999999)

page_size: int = Field(default=20, ge=1, le=100)   # hard cap on page size
amount: Decimal = Field(..., gt=Decimal("0"), max_digits=10, decimal_places=2)
```

#### UUID Inputs
```python
# Threats: enumeration (use UUIDs, not integers), injection via malformed UUIDs
# Pydantic handles UUID format validation — but existence must be checked server-side

resource_id: UUID  # Pydantic validates format

# In service layer — existence check is mandatory, never assume UUID exists
resource = await resource_repo.get_or_raise(db, id=resource_id)
# get_or_raise raises ResourceNotFoundError if not found — never returns None silently
```

#### File/Blob Inputs
```python
# Threats: oversized uploads, wrong MIME type, malicious file content,
#          filename path traversal, zip bombs

@router.post("/uploads")
async def upload_file(
    file: UploadFile,
    current_user: User = Depends(require_auth),
):
    # Size check before reading content
    MAX_SIZE = 10 * 1024 * 1024  # 10MB
    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        raise FileTooLargeError(max_bytes=MAX_SIZE)

    # MIME type validation — do not trust Content-Type header
    import magic
    detected_mime = magic.from_buffer(content, mime=True)
    ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
    if detected_mime not in ALLOWED_MIMES:
        raise InvalidFileTypeError(detected=detected_mime, allowed=ALLOWED_MIMES)

    # Sanitize filename — never use client-provided filename directly
    safe_filename = f"{uuid4()}{Path(file.filename).suffix.lower()}"
```

#### Query Parameters
```python
# Threats: parameter pollution, injection, type coercion abuse,
#          logic bypass via unexpected values

# All query params must be typed — FastAPI coerces, which is a feature and a risk
@router.get("/resources")
async def list_resources(
    status: ResourceStatus | None = Query(default=None),  # enum — rejects unknown values
    search: str | None = Query(default=None, max_length=100),
    created_after: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    ...
```

### 2.3 Semantic Validation (Beyond Pydantic)

Semantic validation happens in the service layer. It must happen before any mutation.

```python
class ResourceService:
    async def create(self, db, user_id, data: ResourceCreateRequest) -> ResourceResponse:

        # 1. Ownership check — does this user have the right to create here?
        workspace = await workspace_repo.get_or_raise(db, id=data.workspace_id)
        if workspace.owner_id != user_id:
            raise InsufficientPermissionError(action="create_resource", resource="workspace")

        # 2. Uniqueness check — does this violate a business uniqueness rule?
        existing = await resource_repo.get_by_name(db, workspace_id=data.workspace_id, name=data.name)
        if existing:
            raise ResourceConflictError(name=data.name, workspace_id=data.workspace_id)

        # 3. State machine check — is this a valid starting state?
        if data.status not in ResourceStatus.valid_initial_states():
            raise InvalidStateTransitionError(from_state=None, to_state=data.status)

        # 4. Quota check — does this user have capacity?
        count = await resource_repo.count_by_user(db, user_id=user_id)
        quota = await quota_service.get(db, user_id=user_id)
        if count >= quota.max_resources:
            raise QuotaExceededError(current=count, max=quota.max_resources)

        # Only after all validation passes — mutate
        return await resource_repo.create(db, user_id=user_id, data=data)
```

---

## Phase 3: Authentication and Authorization

### 3.1 Authentication Contract

Authentication answers: **who is this?**

```python
# JWT authentication dependency — validates token, returns user
async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError:
        raise TokenInvalidError()

    user_id = payload.get("sub")
    if not user_id:
        raise TokenInvalidError()

    # Always verify the user still exists and is active — never trust token alone
    user = await user_repo.get(db, id=UUID(user_id))
    if not user:
        raise TokenInvalidError()
    if not user.is_active:
        raise UserInactiveError()
    if user.banned:
        raise UserBannedError()

    # Verify token was not revoked (if token revocation is implemented)
    if await token_repo.is_revoked(db, jti=payload.get("jti")):
        raise TokenRevokedError()

    return user

# Optional auth — for endpoints that behave differently for authed vs anon users
async def optional_auth(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    # ... same validation as require_auth, returns None instead of raising
```

**Rules:**
- Never trust the token payload without verifying the user exists and is active
- Always check token expiry
- Always check token revocation if your system supports it
- A valid token for a deleted or banned user must be rejected
- Tokens must have short expiry (15–60 minutes for access tokens)
- Refresh tokens must be single-use and stored server-side

### 3.2 Authorization Contract

Authorization answers: **what is this user allowed to do?**

Authorization is not authentication. A valid, active user may still be forbidden.

```python
# Permission-based authorization dependency
def require_permission(permission: str):
    async def check_permission(
        current_user: User = Depends(require_auth),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        has_permission = await permission_service.check(
            db,
            user_id=current_user.id,
            permission=permission,
        )
        if not has_permission:
            raise InsufficientPermissionError(
                user_id=current_user.id,
                permission=permission,
            )
    return check_permission

# Resource-level authorization — ownership check
def require_resource_ownership(resource_type: str):
    async def check_ownership(
        resource_id: UUID,
        current_user: User = Depends(require_auth),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        owned = await ownership_service.check(
            db,
            user_id=current_user.id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if not owned:
            # Return 404, not 403 — do not confirm the resource exists to unauthorized users
            raise ResourceNotFoundError(resource_type=resource_type, resource_id=resource_id)
    return check_ownership
```

**The 404 vs 403 rule:**

When an unauthorized user requests a resource they don't own:
- Return **404**, not **403**
- 403 confirms the resource exists — that is information disclosure
- 404 reveals nothing about whether the resource exists

This applies to all resource-level authorization checks. Route-level permission
checks (e.g., "only admins can access /admin") may return 403.

### 3.3 Authorization Layers

Authorization must be checked at multiple layers. Checking at only one is insufficient.

```
Layer 1: Route layer    — coarse permission check (dependency injection)
Layer 2: Service layer  — ownership and business rule checks
Layer 3: DB layer       — row-level security (optional, for multi-tenant systems)
```

```python
# Layer 1 — route: does this user have the permission class?
@router.delete(
    "/resources/{id}",
    dependencies=[Depends(require_permission("resource:delete"))],
)

# Layer 2 — service: does this user own this specific resource?
async def delete(self, db, user_id, resource_id):
    resource = await resource_repo.get_or_raise(db, id=resource_id)
    if resource.owner_id != user_id:
        raise ResourceNotFoundError(...)  # 404, not 403

# Layer 3 — DB: row-level security policy (PostgreSQL)
# CREATE POLICY resource_isolation ON resources
#   USING (owner_id = current_setting('app.current_user_id')::uuid);
```

---

## Phase 4: Response Contract

### 4.1 What the Response Must Guarantee

A response contract is a promise. Once made, it cannot be broken without versioning.

```
Every response guarantees:
  → The shape is always identical for a given status code
  → Fields that are present are always present (no conditional field omission)
  → Field types never change
  → Null is distinct from absent — be explicit about which you use
  → Error responses always use the canonical ErrorResponse envelope
  → Timestamps are always UTC ISO 8601
  → UUIDs are always strings in the response (not raw UUID objects)
  → Monetary values are always strings or integers (never floats)
```

### 4.2 What the Response Must Never Expose

Every response is an information disclosure decision. Be deliberate.

```python
# Never expose:
#   Internal IDs (auto-increment integers — reveal count and enable enumeration)
#   Password hashes — ever, under any circumstance
#   Raw tokens or secrets
#   Internal error messages in production (stack traces, SQL errors, file paths)
#   Fields from related models the user didn't request
#   System metadata (server version, internal service names, infrastructure details)
#   Other users' data, even partial
#   Soft-deleted records

# Explicit response schema — only what is intentionally exposed
class UserResponse(BaseModel):
    id: UUID                    # ✓ public identifier
    email: str                  # ✓ user's own email
    display_name: str           # ✓ public name
    created_at: datetime        # ✓ public metadata
    # password_hash: str        # ✗ never
    # internal_flags: dict      # ✗ never
    # billing_customer_id: str  # ✗ internal reference
    # last_login_ip: str        # ✗ sensitive

    model_config = ConfigDict(from_attributes=True)
```

### 4.3 Error Response Contract

All errors across the entire API use one shape. No exceptions.

```python
class ErrorDetail(BaseModel):
    code: str           # snake_case, machine-readable: "resource_not_found"
    message: str        # human-readable, safe to display
    field: str | None = None    # for validation errors: which field failed
    meta: dict | None = None    # optional safe context

class ErrorResponse(BaseModel):
    error: ErrorDetail

# Domain exception → HTTP response mapping — registered once at app level
ERROR_MAP: dict[type[DomainError], int] = {
    ResourceNotFoundError:       404,
    ResourceConflictError:       409,
    InsufficientPermissionError: 403,
    TokenExpiredError:           401,
    TokenInvalidError:           401,
    QuotaExceededError:          429,
    InvalidStateTransitionError: 422,
}

@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status_code = ERROR_MAP.get(type(exc), 500)
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=ErrorDetail(
            code=exc.code,
            message=exc.message,
            field=getattr(exc, "field", None),
            meta=exc.safe_meta(),  # only safe, non-sensitive context
        )).model_dump(mode="json"),
    )

# Never expose raw Python exceptions
@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Log the real error internally
    logger.error("Unhandled exception", exc_info=exc, extra={"path": request.url.path})
    # Return nothing useful to the client
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error=ErrorDetail(
            code="internal_error",
            message="An internal error occurred",
        )).model_dump(mode="json"),
    )
```

### 4.4 Sensitive Data in Error Messages

Error messages are part of the response contract. They are also an information
disclosure surface.

```python
# Wrong — confirms resource exists, reveals internal structure
raise HTTPException(404, detail="Migration with ID abc123 not found in series xyz")

# Wrong — reveals DB structure
raise HTTPException(500, detail="column 'order_index' does not exist")

# Wrong — reveals business logic
raise HTTPException(403, detail="User does not have 'admin' role")

# Correct — safe, non-leaking messages
raise ResourceNotFoundError()         # message: "Resource not found"
raise InsufficientPermissionError()   # message: "Insufficient permissions"
# Internal details logged server-side, never sent to client
```

---

## Phase 5: Idempotency

### 5.1 When Idempotency Is Required

Any operation where executing it twice would cause harm must be idempotent.

```
Required for:
  → Payment processing
  → Resource creation (to handle network retry)
  → Email/notification sending
  → Any operation with external side effects
  → Any operation the client may retry on timeout

Not required for:
  → Pure reads (GET is inherently idempotent)
  → Operations explicitly designed to be additive (append to log)
```

### 5.2 Idempotency Key Pattern

```python
# Client sends Idempotency-Key header with a UUID they generate
# Server stores the result of the first execution
# Subsequent requests with the same key return the stored result

@router.post("/payments", response_model=PaymentResponse, status_code=201)
async def create_payment(
    body: PaymentCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
) -> PaymentResponse:
    return await payment_service.create_idempotent(
        db,
        user_id=current_user.id,
        data=body,
        idempotency_key=idempotency_key,
    )

class PaymentService:
    async def create_idempotent(self, db, user_id, data, idempotency_key) -> PaymentResponse:
        # Check if this key was already processed
        cached = await idempotency_repo.get(db, key=idempotency_key, user_id=user_id)
        if cached:
            # Return the original result — do not re-execute
            return PaymentResponse.model_validate_json(cached.response_body)

        # Execute the operation
        result = await self._create_payment(db, user_id=user_id, data=data)

        # Store the result against the key
        await idempotency_repo.store(
            db,
            key=idempotency_key,
            user_id=user_id,
            response_body=result.model_dump_json(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

        return result
```

**Rules:**
- Idempotency keys are scoped to the user — one user's key cannot replay another user's operation
- Keys expire — 24 hours is standard
- If the first request is still in-flight when the second arrives, return 409 Conflict
- The stored result is returned verbatim — do not re-execute business logic

---

## Phase 6: Rate Limiting and Abuse Surface

### 6.1 Every Endpoint Has an Abuse Profile

Before implementing an endpoint, state its abuse profile explicitly:

```
What does this endpoint cost per request?
  → DB queries: N
  → External calls: N
  → CPU work: low/medium/high

What happens if called 1000 times per second?
  → DB connection pool exhausted?
  → External rate limit hit?
  → Service degraded for other users?

What information does repeated calling reveal?
  → Existence of resources (enumeration)?
  → Valid vs invalid credentials (timing attack)?
  → Business data (scraping)?
```

### 6.2 Rate Limiting by Endpoint Class

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Authentication endpoints — strict (prevent brute force)
@router.post("/auth/login")
@limiter.limit("5/minute")
async def login(...): ...

@router.post("/auth/password-reset")
@limiter.limit("3/hour")
async def request_password_reset(...): ...

# Resource creation — moderate
@router.post("/resources")
@limiter.limit("60/minute")
async def create_resource(...): ...

# Read endpoints — generous but bounded
@router.get("/resources")
@limiter.limit("300/minute")
async def list_resources(...): ...

# Expensive operations — strict
@router.post("/exports")
@limiter.limit("10/hour")
async def export_data(...): ...
```

### 6.3 Timing Attack Prevention

Some endpoints leak information through their response time.

```python
# Wrong — response time reveals whether email exists
async def login(data: LoginRequest, db):
    user = await user_repo.get_by_email(db, email=data.email)
    if not user:
        raise InvalidCredentialsError()  # fast response
    if not verify_password(data.password, user.password_hash):
        raise InvalidCredentialsError()  # slow response (bcrypt)
    # Attacker can enumerate valid emails by measuring response time

# Correct — constant-time response regardless of whether user exists
async def login(data: LoginRequest, db):
    user = await user_repo.get_by_email(db, email=data.email)
    # Always run password verification — use dummy hash if user not found
    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    is_valid = verify_password(data.password, password_hash)
    if not user or not is_valid:
        raise InvalidCredentialsError()  # same code path, same time cost
```

### 6.4 Enumeration Prevention

```python
# Wrong — sequential integer IDs enable enumeration
GET /users/1    → 200
GET /users/2    → 200
GET /users/3    → 404   # attacker now knows there are 2 users

# Correct — UUIDs prevent enumeration
GET /users/550e8400-e29b-41d4-a716-446655440000  → 200 or 404
# 404 reveals nothing about the dataset size or structure

# Wrong — different responses for "not found" vs "not yours"
GET /resources/uuid-owned-by-other  → 403  # confirms resource exists
GET /resources/uuid-that-doesnt-exist → 404

# Correct — always 404 for resources the user cannot access
GET /resources/uuid-owned-by-other  → 404  # reveals nothing
GET /resources/uuid-that-doesnt-exist → 404
```

---

## Phase 7: Contract Evolution and Versioning

### 7.1 Breaking vs Non-Breaking Changes

Know the difference before making any contract change.

**Non-breaking (safe to ship without versioning):**
```
✓ Adding a new optional field to a response
✓ Adding a new optional field to a request
✓ Adding a new endpoint
✓ Adding a new error code the client wasn't handling
✓ Widening a constraint (max_length 100 → 200)
```

**Breaking (requires a new API version):**
```
✗ Removing a field from a response
✗ Renaming a field
✗ Changing a field's type
✗ Making an optional field required
✗ Narrowing a constraint (max_length 200 → 100)
✗ Changing an endpoint's URL
✗ Changing an HTTP method
✗ Changing a status code
✗ Removing an endpoint
✗ Changing error code semantics
```

### 7.2 Versioning Implementation

```python
# URL versioning — the only acceptable pattern
# /api/v1/resources  →  /api/v2/resources

# Router structure
api_v1 = APIRouter(prefix="/api/v1")
api_v2 = APIRouter(prefix="/api/v2")

api_v1.include_router(resources_v1_router, prefix="/resources")
api_v2.include_router(resources_v2_router, prefix="/resources")

# Old version runs fully — not a stub, not a redirect
# Deprecation headers signal sunset without breaking the contract
@router.get("/resources/{id}")
async def get_resource_v1(id: UUID, response: Response, ...):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-06-01"                    # ISO 8601 date
    response.headers["Link"] = f'</api/v2/resources/{id}>; rel="successor-version"'
    # Full implementation — not forwarded to v2
    return await resource_service_v1.get(db, id=id)
```

### 7.3 Deprecation Process

```
Step 1: Ship v2 endpoint
Step 2: Add deprecation headers to v1 (do NOT remove v1 yet)
Step 3: Communicate sunset date to all known consumers
Step 4: Monitor v1 traffic — do not sunset while traffic exists
Step 5: After sunset date and zero traffic — remove v1
```

Never skip steps. Never sunset early. A broken client is always the server's fault.

---

## Phase 8: WebSocket and SSE Contracts

### 8.1 WebSocket Event Contract

WebSocket connections carry typed events. Every event has an explicit contract.

```python
# Event envelope — all WebSocket messages use this shape
class WSEventEnvelope(BaseModel):
    event: str          # snake_case event name: "migration.completed"
    data: dict          # event payload
    id: str             # unique event ID for deduplication
    timestamp: datetime # UTC

# Event definitions — explicit, not ad-hoc
class MigrationCompletedEvent(BaseModel):
    migration_id: UUID
    series_id: UUID
    execution_time_ms: int
    status: MigrationStatus

# Sending a typed event
async def send_event(websocket: WebSocket, event_name: str, data: BaseModel):
    envelope = WSEventEnvelope(
        event=event_name,
        data=data.model_dump(mode="json"),
        id=str(uuid4()),
        timestamp=datetime.now(timezone.utc),
    )
    await websocket.send_json(envelope.model_dump(mode="json"))

# WebSocket authentication — token in query param or first message
# Never unauthenticated WebSocket connections to protected resources
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),  # token in query param
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.verify_ws_token(db, token=token)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    # ... connection handling
```

### 8.2 SSE Contract

```python
# SSE event contract — typed, not ad-hoc strings
@router.get("/events/stream")
async def event_stream(
    request: Request,
    current_user: User = Depends(require_auth),
):
    async def generate():
        # Send initial connection confirmation
        yield ServerSentEvent(
            data=json.dumps({"event": "connected", "user_id": str(current_user.id)}),
            event="connected",
            id=str(uuid4()),
        )

        # Subscribe to user-scoped event channel
        async with event_bus.subscribe(channel=f"user:{current_user.id}") as stream:
            async for event in stream:
                if await request.is_disconnected():
                    break

                # Serialize with explicit schema — never raw dict
                yield ServerSentEvent(
                    data=event.model_dump_json(),
                    event=event.event_type,
                    id=str(event.id),
                    retry=3000,   # client reconnect delay in ms
                )

    return EventSourceResponse(generate())
```

**SSE contract rules:**
- Every event has a type, an ID, and a timestamp
- Event IDs enable the client to resume from the last received event (`Last-Event-ID` header)
- Always check `request.is_disconnected()` to avoid writing to closed connections
- Events are user-scoped — never broadcast one user's events to another
- SSE streams are authenticated — the auth check runs before the generator starts

---

## Phase 9: Complete Route Contract Checklist

Run this for every route before marking it complete.

```
Route definition
[ ] HTTP method matches operation semantics
[ ] URL follows resource/noun pattern
[ ] response_model explicitly set on decorator
[ ] status_code explicitly set on decorator
[ ] All non-200 responses documented in responses={}
[ ] Summary and description set for OpenAPI

Authentication and authorization
[ ] Auth dependency injected (or explicitly absent for public routes)
[ ] Permission dependency injected where required
[ ] Resource ownership checked in service layer
[ ] 404 returned (not 403) for resources user cannot access

Request validation
[ ] All string fields have min_length and max_length
[ ] All numeric fields have ge/le bounds
[ ] All list fields have max_length
[ ] Enum fields use Python enums, not raw strings
[ ] Semantic validation in service layer (existence, ownership, state)
[ ] File uploads validated for size and MIME type

Response contract
[ ] Response schema exposes only intended fields
[ ] No internal IDs, hashes, tokens, or sensitive metadata in response
[ ] All timestamps are UTC
[ ] Monetary values are strings or integers, never floats
[ ] Error responses use canonical ErrorResponse envelope
[ ] Internal errors return generic message — real error logged server-side

Idempotency and safety
[ ] Idempotency key implemented for payment/notification/external operations
[ ] GET endpoints have no side effects
[ ] POST/PUT/PATCH endpoints are safe to retry with same data

Abuse surface
[ ] Rate limit defined and appropriate for operation cost
[ ] Timing attack surface assessed for auth endpoints
[ ] Sequential integer IDs not exposed in URLs
[ ] 404 returned for unauthorized resource access (not 403)

Contract evolution
[ ] Breaking change assessment done before any schema modification
[ ] Versioning applied if breaking change is necessary
[ ] Deprecation headers added to sunset endpoints
```

---

## Reference Files

`references/principles.md` — The laws that govern contract design. Conservation:
every input must be accounted for. Invariants: contracts that must always hold.
Causality: a broken contract is always the server's fault.

`fastapi-backend-architecture/SKILL.md` — Layer definitions and responsibilities.
This skill operates at the route and contract layer — the architecture skill defines
what happens below it.

`fastapi-refactoring/SKILL.md` — When contract rot is identified, use the refactoring
skill to address it. Diagnosis here, execution there.

`fastapi-debugging/SKILL.md` — When a contract violation produces a bug (422 errors,
auth failures, wrong response shapes), use the debugging skill to trace it.
