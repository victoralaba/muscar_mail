---
name: fastapi-backend-architecture
description: >
  Design, implement, and review FastAPI backend systems with rigorous architectural
  discipline. Use this skill for any backend task involving API design, service layer
  structure, database access patterns, error contracts, async logic, background tasks,
  domain modeling, or codebase organization. Triggers include: "design an endpoint",
  "how should I structure this", "build this API feature", "review this backend logic",
  "add a service", "refactor this layer", "design the schema", "task queue", "background
  job", or any request where FastAPI, Pydantic, SQLAlchemy, Alembic, or Celery are
  involved. ALWAYS use this skill before writing any backend code — diagnosis and
  architecture precede implementation unconditionally.
---

# FastAPI Backend Architecture Skill

> Before reading further, also read `references/principles.md` — it contains the
> mathematical and physical laws that govern architectural decisions in this codebase.
> These are not suggestions. They constrain every decision made in this skill.

---

## Prime Directive: No Half Implementation

This is the single rule that overrides everything else.

**A task is either complete or it is not started.**

Half implementation is worse than no implementation — it creates false confidence,
hidden bugs, and debt that compounds. Every output from this skill must satisfy the
**Completion Contract**:

```
For every feature, endpoint, or system designed:
  ✓ Every layer touched is fully implemented (route → service → repo → schema → DB)
  ✓ Every error path is handled, not commented "TODO: handle error"
  ✓ Every Pydantic model is complete — no `...` placeholders, no Optional fields
    that are actually required
  ✓ Every DB operation has its transaction boundary defined
  ✓ Every async operation has its await, its timeout, and its failure mode
  ✓ If a migration is needed, it is written — not mentioned
  ✓ If a Celery task is registered, it is registered — not described
```

If any layer is incomplete, the output is rejected and restarted. Partial outputs
with "you can fill in the rest" annotations are forbidden.

---

## Phase 1: Architectural Diagnosis (Always First)

**Never write code before completing this phase.**

### 1.1 Domain Identification

Map the request to its domain boundaries:

```
What domain does this belong to?
  → What entities are involved?
  → What invariants must hold across those entities?
  → What are the domain events (things that happen, not just state changes)?
  → What other domains does this touch? Are those dependencies clean?
```

If a feature crosses more than two domain boundaries, that is an architectural signal —
either the domains are wrong, or the feature needs to be decomposed.

### 1.2 Layer Mapping

Before writing code, explicitly name which layers will be touched:

```
[ ] Route layer       — HTTP shape, request parsing, response serialization
[ ] Service layer     — Business logic, orchestration, domain rules
[ ] Repository layer  — Data access, query logic, transaction ownership
[ ] Schema layer      — Pydantic models for I/O, ORM models for persistence
[ ] DB layer          — Migration, index, constraint definitions
[ ] Task layer        — Celery tasks, beat schedules, retry policies
[ ] Event layer       — Webhooks, SSE, WebSocket event definitions
```

Every checked layer must be fully implemented in the output. Unchecked layers must be
explicitly confirmed as unaffected — not assumed.

### 1.3 Contract Definition

Define the API contract in full before implementation:

```
Endpoint: METHOD /path/{param}
Request:  body shape, query params, path params, auth requirements
Response: 200 shape, all error shapes (4xx, 5xx), edge case responses
Side effects: what DB writes happen, what tasks are enqueued, what events fire
Idempotency: is this endpoint idempotent? If not, why not? What guards re-execution?
```

This contract is the specification. The code is the proof.

---

## Phase 2: Structural Architecture

### 2.1 Layer Definitions and Responsibilities

Each layer has exactly one job. Violation of this is architectural debt.

#### Route Layer (`routers/`)
**Job:** Translate HTTP into function calls. Nothing else.

```python
# Correct — route layer does HTTP translation only
@router.post("/migrations", response_model=MigrationResponse, status_code=201)
async def create_migration(
    body: MigrationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
) -> MigrationResponse:
    return await migration_service.create(db, user_id=current_user.id, data=body)

# Wrong — business logic in route layer
@router.post("/migrations")
async def create_migration(body: MigrationCreateRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Migration).where(...))  # ← belongs in repo
    if existing.scalar():                                       # ← belongs in service
        raise HTTPException(...)                               # ← belongs in service
    migration = Migration(**body.dict())                       # ← belongs in service
    db.add(migration)
    await db.commit()
    return migration
```

**Rules:**
- No raw SQLAlchemy in routes
- No business logic conditionals in routes
- No direct model instantiation in routes
- HTTPException raised here only for auth/permission failures that are purely HTTP concerns

#### Service Layer (`services/`)
**Job:** Own business logic, enforce invariants, orchestrate repositories.

```python
class MigrationService:
    async def create(
        self,
        db: AsyncSession,
        user_id: UUID,
        data: MigrationCreateRequest,
    ) -> MigrationResponse:
        # 1. Enforce invariants
        await self._assert_no_duplicate(db, user_id, data.name)

        # 2. Resolve dependencies (linked-list insertion, series assignment, etc.)
        parent = await migration_repo.get_tail(db, series_id=data.series_id)

        # 3. Delegate persistence
        migration = await migration_repo.create(db, user_id=user_id, data=data, parent=parent)

        # 4. Fire side effects
        await notification_service.notify(db, event=MigrationCreated(migration_id=migration.id))

        # 5. Return response shape
        return MigrationResponse.model_validate(migration)
```

**Rules:**
- No HTTP concepts (no HTTPException, no Request, no Response)
- No raw SQL
- Raises domain exceptions (`MigrationConflictError`, `SeriesNotFoundError`) — not HTTP ones
- Transaction boundaries owned here unless a repo method explicitly claims them
- All side effects (tasks, events, notifications) triggered from service layer

#### Repository Layer (`repositories/`)
**Job:** Own all database access. Return domain objects, not raw rows.

```python
class MigrationRepository:
    async def get_tail(self, db: AsyncSession, series_id: UUID) -> Migration | None:
        result = await db.execute(
            select(Migration)
            .where(Migration.series_id == series_id, Migration.next_id.is_(None))
            .with_for_update()  # lock tail during linked-list insertion
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        user_id: UUID,
        data: MigrationCreateRequest,
        parent: Migration | None,
    ) -> Migration:
        migration = Migration(
            user_id=user_id,
            series_id=data.series_id or uuid4(),
            parent_id=parent.id if parent else None,
            **data.model_dump(exclude={"series_id"}),
        )
        db.add(migration)
        if parent:
            parent.next_id = migration.id
        await db.flush()  # flush, not commit — service owns the commit
        return migration
```

**Rules:**
- No business logic
- No Pydantic request/response models — only ORM models in, ORM models out
- `flush()` not `commit()` unless the repo explicitly owns the transaction
- Complex queries get explicit comments explaining the why, not just the what
- N+1 patterns are forbidden — use `joinedload`, `selectinload`, or `jsonb_agg` aggregation

#### Schema Layer (`schemas/`)
**Job:** Define I/O contracts precisely.

```python
# Separate Request, Response, and Internal schemas — never share them
class MigrationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    series_id: UUID | None = None
    sql_up: str = Field(..., min_length=1)
    sql_down: str | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

class MigrationResponse(BaseModel):
    id: UUID
    name: str
    series_id: UUID
    parent_id: UUID | None
    execution_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Never expose ORM models directly as response shapes
# Never reuse request models as response models
```

**Rules:**
- Request schemas validate and sanitize input — use `Field()` constraints aggressively
- Response schemas are explicit — no `model = orm_model` shortcut
- Internal schemas (service-to-service) are separate from API-facing schemas
- `model_config = ConfigDict(from_attributes=True)` on all response schemas that map from ORM

---

### 2.2 Dependency Injection Pattern

```python
# db.py — single source of truth for session lifecycle
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# Service instantiation — use module-level singletons, not per-request construction
migration_service = MigrationService(repo=migration_repo)

# Route dependency injection
@router.get("/migrations/{id}")
async def get_migration(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auth),
) -> MigrationResponse:
    return await migration_service.get_by_id(db, id=id, user_id=current_user.id)
```

---

## Phase 3: API Contract Design

### 3.1 Error Envelope

Every error response across the entire API must use the same shape:

```python
class ErrorDetail(BaseModel):
    code: str          # machine-readable, snake_case: "migration_not_found"
    message: str       # human-readable
    field: str | None  # for validation errors, which field failed
    meta: dict | None  # optional context (e.g., conflicting resource ID)

class ErrorResponse(BaseModel):
    error: ErrorDetail

# Usage
raise HTTPException(
    status_code=404,
    detail=ErrorResponse(error=ErrorDetail(
        code="migration_not_found",
        message=f"Migration {id} does not exist",
        field=None,
        meta={"requested_id": str(id)},
    )).model_dump(),
)
```

**HTTP status code semantics — enforce strictly:**

| Status | Meaning | When |
|--------|---------|------|
| 200 | OK | Successful GET, PUT, PATCH |
| 201 | Created | Successful POST that creates a resource |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Malformed input, validation failure |
| 401 | Unauthorized | Missing or invalid auth |
| 403 | Forbidden | Valid auth, insufficient permission |
| 404 | Not Found | Resource does not exist |
| 409 | Conflict | State conflict (duplicate, wrong state machine transition) |
| 422 | Unprocessable | Pydantic validation failure (FastAPI default) |
| 429 | Too Many Requests | Rate limit hit |
| 500 | Internal Error | Unhandled exception — never intentionally raised |

### 3.2 Pagination Contract

All list endpoints must paginate. No exceptions.

```python
class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, params: PaginationParams) -> Self:
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            pages=ceil(total / params.page_size),
        )
```

### 3.3 Versioning

- URL versioning: `/api/v1/`, `/api/v2/` — not header-based
- Breaking changes require a new version prefix
- Old versions remain alive with deprecation headers until explicitly sunset
- Never mutate an existing response schema in a breaking way — add fields, don't remove or rename

---

## Phase 4: Async and Performance Constraints

### 4.1 Async Rules

```python
# All DB operations must be async — no sync SQLAlchemy in async routes
# Wrong
def get_user(db: Session, id: UUID) -> User:
    return db.query(User).filter(User.id == id).first()

# Correct
async def get_user(db: AsyncSession, id: UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == id))
    return result.scalar_one_or_none()
```

**Rules:**
- Never call blocking I/O inside an async function without `run_in_executor`
- Never use `time.sleep` — use `asyncio.sleep`
- CPU-bound work (hashing, compression, parsing) belongs in a Celery task or `run_in_executor`
- `asyncio.gather()` for concurrent independent async calls — never await them sequentially

```python
# Wrong — sequential awaits when operations are independent
user = await user_repo.get(db, id=user_id)
settings = await settings_repo.get(db, user_id=user_id)

# Correct — concurrent
user, settings = await asyncio.gather(
    user_repo.get(db, id=user_id),
    settings_repo.get(db, user_id=user_id),
)
```

### 4.2 Database Performance Constraints

**N+1 is forbidden.** Every relationship traversal must be pre-loaded or aggregated.

```python
# Wrong — N+1: loads migrations, then queries columns for each
migrations = await migration_repo.get_all(db, series_id=series_id)
for m in migrations:
    columns = await column_repo.get_by_migration(db, migration_id=m.id)

# Correct — single query with joinedload
result = await db.execute(
    select(Migration)
    .options(selectinload(Migration.columns))
    .where(Migration.series_id == series_id)
)

# Correct — aggregation at DB level for complex shapes
result = await db.execute(text("""
    SELECT m.*, jsonb_agg(c.*) AS columns
    FROM migrations m
    LEFT JOIN migration_columns c ON c.migration_id = m.id
    WHERE m.series_id = :series_id
    GROUP BY m.id
"""), {"series_id": str(series_id)})
```

**Index strategy — define at design time, not after complaints:**
- Every foreign key gets an index
- Every column used in `WHERE`, `ORDER BY`, or `GROUP BY` at scale gets an index
- Composite indexes for multi-column filters — column order matters (high-selectivity first)
- Partial indexes for soft-deleted records: `WHERE deleted_at IS NULL`

### 4.3 Background Task Constraints (Celery)

```python
# Task definition — always typed, always idempotent
@celery_app.task(
    name="notifications.send_migration_alert",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,         # only ack after successful execution
    reject_on_worker_lost=True,
)
def send_migration_alert(self, migration_id: str, user_id: str) -> None:
    try:
        # implementation
    except (ConnectionError, TimeoutError) as exc:
        raise self.retry(exc=exc)
    except Exception as exc:
        # non-retryable — log, don't retry
        logger.error("send_migration_alert failed permanently", exc_info=exc)
        raise
```

**Rules:**
- Tasks must be idempotent — running twice must produce the same outcome
- Tasks receive primitive arguments only (str, int, UUID as str) — never ORM objects
- Every task has explicit `max_retries` and `default_retry_delay` — no infinite retries
- `acks_late=True` for tasks with side effects — prevents loss on worker crash
- Tasks must not block the event loop — they run in Celery workers, not FastAPI's async loop

---

## Phase 5: Implementation Execution Standard

### 5.1 The Vertical Slice Rule

Every feature is implemented as a complete vertical slice:

```
Route → Service → Repository → Schema → DB (migration if needed) → Task (if needed)
```

No horizontal slices. Do not implement "all the routes first, then all the services."
Each feature is complete before the next begins.

### 5.2 Code Completeness Checklist

Before any code output is finalized:

```
Routes
[ ] Path, method, status codes defined
[ ] Request body, query params, path params fully typed
[ ] Response model specified on decorator
[ ] Auth dependency injected where required
[ ] No business logic present

Service
[ ] All invariants enforced before any mutation
[ ] All repository calls present and awaited
[ ] All side effects (tasks, events) triggered
[ ] Domain exceptions raised (not HTTPException)
[ ] Return type matches response schema

Repository
[ ] No N+1 patterns
[ ] Appropriate locking where concurrent writes are possible
[ ] flush() not commit() unless transaction ownership is explicit
[ ] All query filters use indexed columns where scale matters

Schemas
[ ] Request schema validates and constrains all fields
[ ] Response schema maps cleanly from ORM with from_attributes=True
[ ] No shared request/response models
[ ] All Optional fields are genuinely optional (not lazily typed)

Database
[ ] Migration written if schema changes
[ ] Indexes defined for all foreign keys and filter columns
[ ] Constraints defined at DB level (not just application level)

Error Handling
[ ] All 4xx cases explicitly handled with correct status codes
[ ] Error envelope shape consistent with ErrorResponse schema
[ ] No bare `except Exception: pass`
[ ] No unhandled edge cases in service logic
```

### 5.3 Annotation Standard

Comments explain **why**, not what. The code explains what.

```python
# Wrong
# Get the migration
migration = await migration_repo.get(db, id=migration_id)

# Correct
# Lock the tail node before insertion to prevent race conditions in concurrent
# linked-list appends to the same series
tail = await migration_repo.get_tail(db, series_id=series_id, lock=True)
```

---

## Phase 6: Architectural Diagnosis Output Format

When diagnosing an existing system or reviewing a design, output follows this structure:

### 1. Layer Violation Inventory
List every place a layer is doing another layer's job. Be exact — file, function, line behavior.

### 2. Contract Gaps
List every endpoint missing error shapes, pagination, or consistent response envelopes.

### 3. Performance Risks
List every N+1, missing index, sync operation in async context, or sequential await.

### 4. Completeness Gaps
List every TODO, placeholder, unhandled exception path, or half-implemented feature.

### 5. Recommended Execution Order
Order the fixes by: (1) correctness blockers, (2) performance risks, (3) structural debt.
Each item gets: what to change, which layer, why it matters.

### 6. Implementation
Only after the diagnosis is complete — full vertical slice implementation for each fix.

---

## Reference Files

`references/principles.md` — Mathematical and physical laws governing all architectural
decisions. Read before designing any system. These constrain what is structurally
permissible, independent of framework conventions.
