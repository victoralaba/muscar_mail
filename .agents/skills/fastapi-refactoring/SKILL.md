---
name: fastapi-refactoring
description: >
  Refactor existing FastAPI backend code with surgical precision and full completion
  discipline. Use this skill for any task involving restructuring, reorganizing, cleaning,
  improving, or fixing existing backend code without changing its external behavior — unless
  the refactor explicitly includes a contract change. Triggers include: "refactor this",
  "clean this up", "fix the structure", "move this to the right layer", "this is a mess",
  "restructure this service", "fix the N+1", "improve this query", "rename this", "split
  this", "consolidate these", "make this follow the architecture", "the logic is in the
  wrong place", "simplify this", or any request where existing code is being changed rather
  than new code being added. ALWAYS diagnose before touching code. ALWAYS deliver complete
  files, never diffs or partial replacements. ALWAYS verify behavior is preserved unless
  a deliberate behavior change is part of the brief.
---

# FastAPI Refactoring Skill

> Also read `references/principles.md` before any refactoring session. The laws there
> define what "better structure" actually means — not convention, not preference.

---

## Prime Directive: Refactoring Is Not Rewriting

These are different operations with different rules.

```
Refactoring  → behavior preserved, structure improved
Rewriting    → behavior may change, structure rebuilt from scratch
```

Conflating them is the most common refactoring failure. Before touching anything:

**State explicitly which operation is being performed.**

If a "refactor" request also changes behavior (fixes a bug, adds validation, changes
a response shape), that must be called out and treated as two separate operations:
first the structural refactor, then the behavioral change — or clearly labeled as
a combined operation with both concerns fully addressed.

---

## Prime Directive: No Half Refactoring

A refactor is complete when **every file touched is in a better state than it started**
and **nothing that was working before is broken.** The completion contract:

```
For every refactoring task:
  ✓ Every layer the refactor touches is fully updated — no partial migrations
    where half the code uses the old pattern and half uses the new
  ✓ Every call site of a renamed/moved/changed function is updated
  ✓ Every import is corrected — no dangling imports to moved modules
  ✓ Every Alembic migration is written if the DB schema changes
  ✓ Every test reference to moved/renamed code is updated (if tests exist)
  ✓ Every place the old pattern existed is replaced — no stragglers
  ✓ The system boots and functions after the refactor — no "this should work"
```

A refactor that fixes one file and leaves five callers broken is not a refactor.
It is sabotage.

---

## Phase 1: Pre-Refactor Diagnosis (Mandatory)

**Do not write a single line of refactored code before this phase is complete.**

The diagnosis is the most important output of a refactoring session. Code without
diagnosis is guessing.

### 1.1 Understand What Exists

Before proposing any change, map the current state:

```
What does this code currently do?
  → What is its external behavior (inputs, outputs, side effects)?
  → What invariants does it currently maintain (even accidentally)?
  → What does it currently get right, even if the structure is bad?

What are its structural problems?
  → Which of the five problem types does this fall into? (see 1.2)
  → How deep does the problem go — surface or systemic?
  → What is coupled to the bad structure that will break if moved?

What are the risks?
  → What will break if this is changed carelessly?
  → Are there implicit behaviors the code relies on that aren't obvious?
  → Are there callers outside this file that depend on the current shape?
```

### 1.2 Classify the Problem Type

Every refactoring task maps to one or more of these five problem types.
Classify before acting — the problem type determines the refactoring strategy.

| Type | Description | Signal |
|------|-------------|--------|
| **Layer Violation** | Logic in the wrong layer | SQL in routes, HTTP exceptions in services, business logic in repos |
| **Structural Bloat** | A unit doing too many jobs | Service method over 40 lines, route file over 200 lines, god class |
| **Contract Rot** | Inconsistent or implicit API contracts | Mixed error shapes, undocumented edge cases, Optional fields that are required |
| **Performance Debt** | Correct but expensive patterns | N+1 queries, sequential awaits, sync I/O in async context, missing indexes |
| **Schema Drift** | Code shape diverged from data shape | ORM model doesn't match DB, Pydantic schema doesn't match ORM, stale migrations |

### 1.3 Measure the Blast Radius

Before moving anything, map everything that depends on it:

```
Files that import the target module/function/class:
  → List them all — do not assume

Functions that call the target:
  → List every call site

DB columns/tables affected:
  → List every model, migration, and query that references them

API contracts affected:
  → List every endpoint whose request or response shape changes
  → List every consumer (frontend, external client) that will be affected
```

If the blast radius is large, the refactor must be staged. See Phase 3.

### 1.4 Define the Target State

Before writing code, describe the target state precisely:

```
After this refactor:
  → What layer owns what logic?
  → What does the file/module/function structure look like?
  → What does the public interface (function signatures, API contracts) look like?
  → What is removed, what is moved, what is renamed, what is split?
  → What stays exactly the same (behavior preservation guarantee)?
```

This is the specification. The refactored code is the proof.

---

## Phase 2: Refactoring Strategies by Problem Type

### 2.1 Layer Violation Refactoring

**Pattern:** Logic found in the wrong layer. Most common: business logic in routes,
raw SQL in services, HTTP exceptions raised from service or repo layer.

**Strategy: Extract and Relocate**

Step 1 — Identify every piece of logic that doesn't belong in its current layer.
Step 2 — Determine which layer it belongs in.
Step 3 — Extract it to the correct layer with the correct interface.
Step 4 — Replace the original with a call to the new location.
Step 5 — Verify the original layer now contains only its own concerns.

```python
# Before — business logic in route layer
@router.post("/users/{id}/activate")
async def activate_user(id: UUID, db: AsyncSession = Depends(get_db)):
    user = await db.execute(select(User).where(User.id == id))
    user = user.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    if user.is_active:
        raise HTTPException(status_code=409, detail="Already active")
    if user.banned:
        raise HTTPException(status_code=403, detail="User is banned")
    user.is_active = True
    user.activated_at = datetime.utcnow()
    await db.commit()
    return {"status": "activated"}

# After — route translates HTTP, service owns logic
@router.post("/users/{id}/activate", response_model=UserResponse, status_code=200)
async def activate_user(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
) -> UserResponse:
    return await user_service.activate(db, user_id=id)

# service layer
class UserService:
    async def activate(self, db: AsyncSession, user_id: UUID) -> UserResponse:
        user = await user_repo.get_or_raise(db, id=user_id)

        # invariant checks belong here, not in route
        if user.is_active:
            raise UserAlreadyActiveError(user_id=user_id)
        if user.banned:
            raise UserBannedError(user_id=user_id)

        user.is_active = True
        user.activated_at = datetime.utcnow()
        await db.flush()
        return UserResponse.model_validate(user)

# exception handler maps domain errors to HTTP — registered at app level
@app.exception_handler(UserAlreadyActiveError)
async def handle_already_active(request: Request, exc: UserAlreadyActiveError):
    return JSONResponse(status_code=409, content=ErrorResponse(...).model_dump())
```

**Checklist after layer violation refactor:**
```
[ ] Route contains no SQL, no db.execute(), no ORM model instantiation
[ ] Route contains no business logic conditionals
[ ] Service contains no HTTPException, no Request, no Response
[ ] Service contains no raw SQL (text() queries belong in repo)
[ ] Repository contains no business logic
[ ] Repository contains no Pydantic schemas
[ ] Domain exceptions are defined, raised in service, handled at app level
```

---

### 2.2 Structural Bloat Refactoring

**Pattern:** A single unit (file, class, function) doing too many jobs.
Signal: service method over ~40 lines, service class over ~300 lines, function
with more than 3 levels of nesting, function name containing "and".

**Strategy: Decompose by Responsibility**

The Single Responsibility Principle applied precisely: a unit should have one reason
to change. If a service method changes when the notification logic changes AND when
the DB schema changes AND when the business rule changes — it has three jobs.

**Decomposing a fat service method:**

```python
# Before — one method doing orchestration + validation + DB + notifications + response
async def create_order(self, db, user_id, data):
    # 40+ lines of mixed concerns

# After — decomposed by responsibility
async def create_order(self, db: AsyncSession, user_id: UUID, data: OrderCreateRequest) -> OrderResponse:
    # Orchestration only — each sub-method has one job
    await self._validate_order_constraints(db, user_id, data)
    inventory = await self._reserve_inventory(db, data.items)
    order = await order_repo.create(db, user_id=user_id, data=data, inventory=inventory)
    await self._trigger_order_events(order)
    return OrderResponse.model_validate(order)

async def _validate_order_constraints(self, db, user_id, data):
    # validation only — raises domain exceptions on failure
    ...

async def _reserve_inventory(self, db, items):
    # inventory reservation only — returns reserved inventory or raises
    ...

async def _trigger_order_events(self, order):
    # side effects only — notifications, tasks, events
    ...
```

**Decomposing a fat file:**

```
Before:
  services/user_service.py  — 800 lines covering auth, profile, billing, notifications

After:
  services/user/
    auth_service.py         — login, logout, token refresh, password reset
    profile_service.py      — profile read/update, avatar, preferences
    billing_service.py      — subscription, payment methods, invoices
    notification_service.py — user-scoped notification preferences and delivery
```

**Rules for decomposition:**
- Split along domain responsibility, not technical similarity
- Each new unit must be independently coherent — not half a concept
- Every existing call site must be updated to the new location
- No circular imports introduced by the split

---

### 2.3 Contract Rot Refactoring

**Pattern:** API contracts that are inconsistent, implicit, or have drifted from
their original intent. Symptoms: mixed error shapes across endpoints, Optional
fields that are always present, response schemas that include internal fields,
undocumented edge case behaviors.

**Strategy: Explicit Contract Enforcement**

Step 1 — Audit every endpoint for response shape, error shape, status codes.
Step 2 — Define the canonical contract (use the ErrorResponse envelope from the
architecture skill as the standard).
Step 3 — Bring every endpoint into conformance — no exceptions.
Step 4 — If a contract change is breaking, version it (see 2.5).

```python
# Before — inconsistent error shapes across the codebase
# endpoint A returns:  {"detail": "not found"}
# endpoint B returns:  {"error": "User not found", "code": 404}
# endpoint C returns:  {"message": "conflict", "field": "email"}

# After — single canonical error envelope everywhere
class ErrorDetail(BaseModel):
    code: str       # snake_case machine-readable: "user_not_found"
    message: str    # human-readable
    field: str | None = None
    meta: dict | None = None

class ErrorResponse(BaseModel):
    error: ErrorDetail

# Registered once at app level — not per-route
@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=ErrorDetail(
            code=exc.code,
            message=exc.message,
            field=getattr(exc, "field", None),
            meta=getattr(exc, "meta", None),
        )).model_dump(),
    )
```

**Schema contract audit checklist:**
```
[ ] Every endpoint has an explicit response_model on its decorator
[ ] Every response model uses from_attributes=True
[ ] No ORM model returned directly as a response
[ ] No internal fields (passwords, tokens, internal IDs) in response schemas
[ ] Every Optional field in a response is genuinely optional
[ ] Every error response uses the canonical ErrorResponse envelope
[ ] No endpoint returns a bare dict — always a typed Pydantic model
```

---

### 2.4 Performance Debt Refactoring

**Pattern:** Code that is logically correct but structurally expensive at scale.
This includes N+1 query patterns, missing indexes, sequential awaits on independent
operations, sync I/O blocking the async event loop, and unbounded queries.

**This refactor type requires measuring before and after.** Do not claim performance
improvement without identifying the specific bottleneck.

#### N+1 Elimination

```python
# Before — N+1: 1 query for projects + N queries for members
projects = await project_repo.get_all(db, user_id=user_id)
for project in projects:
    project.members = await member_repo.get_by_project(db, project_id=project.id)

# After option A — ORM eager loading
result = await db.execute(
    select(Project)
    .options(selectinload(Project.members))
    .where(Project.user_id == user_id)
)
projects = result.scalars().all()

# After option B — DB-level aggregation (preferred for complex shapes)
result = await db.execute(text("""
    SELECT
        p.*,
        jsonb_agg(
            jsonb_build_object('id', m.id, 'role', m.role, 'user_id', m.user_id)
            ORDER BY m.created_at
        ) FILTER (WHERE m.id IS NOT NULL) AS members
    FROM projects p
    LEFT JOIN project_members m ON m.project_id = p.id
    WHERE p.user_id = :user_id
    GROUP BY p.id
"""), {"user_id": str(user_id)})
```

Choose option B when:
- The relationship has more than ~3 fields needed
- The relationship needs ordering, filtering, or aggregation
- The result shape is non-trivial (nested objects, computed fields)

#### Sequential Await Elimination

```python
# Before — sequential: total time = A + B + C
user = await user_repo.get(db, id=user_id)
settings = await settings_repo.get(db, user_id=user_id)
permissions = await permission_repo.get(db, user_id=user_id)

# After — concurrent: total time = max(A, B, C)
user, settings, permissions = await asyncio.gather(
    user_repo.get(db, id=user_id),
    settings_repo.get(db, user_id=user_id),
    permission_repo.get(db, user_id=user_id),
)
```

Only parallelize operations that are genuinely independent. If B depends on A's
result, they cannot be gathered — that is not sequential debt, it is a dependency.

#### Sync I/O in Async Context

```python
# Before — blocks the event loop
import requests

async def fetch_external_data(url: str) -> dict:
    response = requests.get(url)  # sync — freezes the entire event loop
    return response.json()

# After — non-blocking
import httpx

async def fetch_external_data(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()

# For CPU-bound work — offload to executor
import asyncio
from concurrent.futures import ProcessPoolExecutor

async def hash_large_file(content: bytes) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _compute_hash, content)

def _compute_hash(content: bytes) -> str:
    # CPU-bound — runs in separate process, doesn't block event loop
    import hashlib
    return hashlib.sha256(content).hexdigest()
```

#### Index Debt

When refactoring queries, audit and define missing indexes:

```python
# In the ORM model — define indexes at schema time
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    __table_args__ = (
        # every FK gets an index
        Index("ix_orders_user_id", "user_id"),
        # composite for common filter + sort pattern
        Index("ix_orders_user_status_created", "user_id", "status", "created_at"),
        # partial index for active orders only
        Index("ix_orders_active", "user_id", postgresql_where=text("status != 'completed'")),
    )
```

Write the Alembic migration. Do not describe it.

---

### 2.5 Schema Drift Refactoring

**Pattern:** The code model has diverged from the database model, or the API contract
has diverged from the code model. Symptoms: fields in ORM models that don't exist in
the DB, Pydantic schemas with different field names than ORM models, stale Alembic
migrations, silent data truncation or coercion.

**This is the highest-risk refactor type.** Schema drift means production data may
already be inconsistent. Diagnose data state before migrating.

**Strategy: Align Layer by Layer, Bottom Up**

```
Order: DB schema → ORM model → Pydantic schema → API contract
Never top-down. The DB is the source of truth.
```

Step 1 — Run `alembic check` or compare `alembic current` vs `alembic heads`.
         If migrations are out of sync, resolve that first — nothing else.

Step 2 — Compare ORM model field definitions against actual DB columns.
         Every mismatch is a bug, not a style issue.

Step 3 — Compare Pydantic response schemas against ORM model fields.
         Flag every field that is Optional in Pydantic but NOT NULL in the DB,
         and every field present in ORM but absent from response schema.

Step 4 — Write a migration for every DB change. No exceptions.

```python
# Alembic migration for a schema drift fix — always explicit, never autogenerate blindly
def upgrade() -> None:
    # Rename column — two steps: add new, backfill, drop old
    op.add_column("migrations", sa.Column("parent_id", sa.UUID(), nullable=True))

    # Backfill from old column
    op.execute("""
        UPDATE migrations
        SET parent_id = (
            SELECT id FROM migrations m2
            WHERE m2.order_index = migrations.order_index - 1
            AND m2.series_id = migrations.series_id
        )
    """)

    # Now safe to drop old column
    op.drop_column("migrations", "order_index")

def downgrade() -> None:
    op.add_column("migrations", sa.Column("order_index", sa.Integer(), nullable=True))
    # Downgrade must be complete — no "downgrade not supported"
    op.execute("""
        UPDATE migrations SET order_index = (
            SELECT COUNT(*) FROM migrations m2
            WHERE m2.series_id = migrations.series_id
            AND m2.created_at <= migrations.created_at
        )
    """)
    op.drop_column("migrations", "parent_id")
```

**Schema drift checklist:**
```
[ ] alembic current matches alembic heads
[ ] Every ORM column has a matching DB column with matching type and nullability
[ ] Every NOT NULL DB column is non-Optional in the ORM model
[ ] Every non-Optional ORM field is non-Optional in the Pydantic response schema
[ ] No field renamed in code without a corresponding DB migration
[ ] downgrade() implemented fully in every migration — not left empty
```

---

## Phase 3: Staged Refactoring for Large Blast Radius

When a refactor touches more than ~5 files or changes an API contract consumed by
external clients, execute in stages. Never attempt a large refactor as a single
atomic change.

### The Strangler Fig Pattern

Introduce the new structure alongside the old. Migrate callers one by one.
Remove the old structure only when it has zero callers.

```
Stage 1: Build new alongside old
  → New service/repo/schema exists, old still works
  → Nothing breaks yet

Stage 2: Migrate callers
  → Move each call site from old to new, one at a time
  → Each migration is a complete, shippable change

Stage 3: Delete the old
  → Only when zero callers remain
  → Delete is a single, clean commit
```

```python
# Stage 1 — new function exists alongside old
async def get_user_v2(db: AsyncSession, id: UUID) -> UserResponseV2:
    # new implementation
    ...

async def get_user(db: AsyncSession, id: UUID) -> UserResponse:
    # old — still works, not deleted yet
    ...

# Stage 2 — migrate one caller at a time
# Before: result = await get_user(db, id=user_id)
# After:  result = await get_user_v2(db, id=user_id)

# Stage 3 — delete get_user() only when no callers remain
```

### API Contract Versioning for Breaking Changes

When a refactor changes an API contract consumed by external clients:

```python
# Add deprecation header to old endpoint — do not remove it yet
@router.get("/v1/users/{id}")
async def get_user_v1(id: UUID, response: Response, ...):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2025-12-01"
    response.headers["Link"] = '</v2/users/{id}>; rel="successor-version"'
    # old implementation still runs fully
    ...

# New endpoint exists at new version
@router.get("/v2/users/{id}")
async def get_user_v2(id: UUID, ...):
    # new implementation
    ...
```

Rules:
- Old version runs fully until sunset date — no stub or redirect
- Sunset date must be communicated before the deprecation header is added
- New version must be live before old version is deprecated

---

## Phase 4: Refactoring Execution Standard

### 4.1 Output Format

Every refactoring output contains exactly these sections in order:

**1. Diagnosis**
- Problem type(s) identified (from 1.2 classification table)
- Current state described precisely
- Blast radius mapped (files, call sites, contracts affected)

**2. Target State**
- What the structure looks like after the refactor
- What behavior is preserved
- What behavior changes (if any) and why

**3. Execution Plan**
- Ordered list of changes
- Staged if blast radius is large
- Each step independently shippable if possible

**4. Complete Implementation**
- Every file touched is delivered in full — no diffs, no partial files, no "update X similarly"
- Every call site updated
- Every migration written
- Every import corrected

**5. Verification**
- How to confirm the refactor is correct
- What to check in the DB
- What to test manually if no automated tests exist

### 4.2 Forbidden Outputs

These outputs are rejected unconditionally:

```
❌ "Update the other endpoints similarly"
❌ "Repeat this pattern for the remaining services"
❌ "The migration is left as an exercise"
❌ "You'll need to update the imports"
❌ "This is the general approach — apply it to your codebase"
❌ Showing only the changed lines without the surrounding file context
❌ Delivering a diff instead of a complete file
❌ Leaving any file in a half-migrated state (old and new pattern mixed)
❌ Renaming a function without updating every call site
❌ Moving a module without fixing every import
```

### 4.3 Behavior Preservation Verification

After any structural refactor (not a behavioral change), verify:

```python
# The public interface must be identical before and after
# Same function signatures, same return types, same exceptions raised

# Before refactor — document the contract
# endpoint: POST /orders
# request: OrderCreateRequest
# response: 201 OrderResponse
# errors: 409 if duplicate, 404 if user not found, 400 if invalid items

# After refactor — contract must match exactly
# If it doesn't, that's a behavioral change — document and justify it
```

---

## Phase 5: Refactoring Checklist (Run Before Every Output)

```
Pre-refactor
[ ] Problem type classified (layer violation / bloat / contract rot / perf / schema drift)
[ ] Blast radius fully mapped — no assumed-safe changes
[ ] Target state defined in prose before any code written
[ ] Staged plan defined if blast radius > 5 files or breaks external contract

Implementation
[ ] Every touched file delivered in full — no partial files
[ ] Every call site of moved/renamed/changed code updated
[ ] Every import path corrected
[ ] Every Alembic migration written (not described)
[ ] Old pattern fully removed — no half-migrations

Behavior
[ ] External API contract unchanged (or change is documented and justified)
[ ] All error codes and shapes preserved
[ ] All side effects (tasks, events, notifications) still triggered
[ ] No new Optional field where DB column is NOT NULL

Code quality
[ ] Comments explain why, not what
[ ] No dead code left behind
[ ] No commented-out old implementation left "just in case"
[ ] No TODO left in refactored code
```

---

## Reference Files

`references/principles.md` — Mathematical and physical laws governing all architectural
decisions. Read before any refactoring session. They define what "better" actually
means independent of convention.

`fastapi-backend-architecture/SKILL.md` — Layer definitions, contract standards,
async rules, and performance constraints. The refactoring skill enforces these
standards — read them to know what the target state looks like.
