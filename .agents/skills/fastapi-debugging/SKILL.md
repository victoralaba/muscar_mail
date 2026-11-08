---
name: fastapi-debugging
description: >
  Debug FastAPI backend systems with rigorous diagnostic discipline. Use this skill
  for any task involving finding, understanding, or fixing broken, incorrect, slow,
  or unstable behavior in a FastAPI codebase. Triggers include: "this is broken",
  "getting an error", "this crashes", "wrong output", "unexpected behavior", "this
  is slow", "race condition", "deadlock", "query hanging", "migration failed",
  "constraint violation", "frontend not getting the right data", "this works sometimes",
  "500 error", "422 error", any stack trace or error message, any description of
  behavior that doesn't match expectation. ALWAYS diagnose before fixing. ALWAYS
  identify root cause before touching code. NEVER fix symptoms. NEVER change working
  code while fixing broken code.
---

# FastAPI Debugging Skill

> Also read `references/principles.md`. Physical and mathematical laws apply to
> debugging — causality, conservation, invariants. A system does exactly what it
> is told. The bug is always explainable.

---

## Prime Directive: Fix the Cause, Not the Symptom

The most common debugging failure: a model sees an error, finds a line that looks
wrong, changes it, and the error goes away. That is not debugging. That is
symptom suppression.

**A bug is not fixed until:**
1. The root cause is identified and stated explicitly
2. The mechanism by which the cause produces the symptom is understood
3. The fix addresses the cause, not the symptom
4. No working code was changed in the process

A fix that makes the error disappear without understanding why is a liability.
It will resurface, mutated, at the worst possible time.

---

## Prime Directive: Do Not Guess

Guessing is the enemy of debugging. Every hypothesis must be:

```
Stated     → "I believe the cause is X"
Reasoned   → "because Y implies Z, and Z matches the observed symptom"
Testable   → "to confirm: check W, or add log at line L, or run query Q"
Verified   → confirmed or eliminated before the fix is written
```

If the evidence does not yet point to a root cause, say so. Request more
information. Do not fill the gap with a guess dressed as a diagnosis.

---

## Prime Directive: Minimum Viable Change

Every fix touches the minimum code necessary to address the root cause.

```
❌ Fixing the bug AND refactoring the surrounding code
❌ Fixing the bug AND adding unrelated validation
❌ Fixing the bug AND "cleaning up while I'm here"
❌ Changing working code because it "looks suspicious"
```

If working code needs to be changed for unrelated reasons, that is a separate
task. Flag it, do not do it inline. A debugging session that changes more code
than necessary is a debugging session that may introduce new bugs.

---

## Phase 1: Bug Classification (Always First)

Every bug maps to one of six types. Classify before anything else.
The type determines the diagnostic strategy.

| Type | Description | Primary Signal |
|------|-------------|----------------|
| **Runtime Error** | Code throws an exception | Stack trace, 500 response, crash log |
| **Logic Bug** | Code runs but produces wrong output | Wrong response body, wrong DB state, wrong behavior |
| **Performance Bug** | Code is correct but too slow | High latency, timeouts, DB query time, CPU/memory spike |
| **Concurrency Bug** | Behavior is non-deterministic or order-dependent | "Works sometimes", race conditions, deadlocks, lost updates |
| **Data Bug** | DB state is wrong, inconsistent, or violates constraints | Constraint errors, wrong query results, stale data, migration failures |
| **Integration Bug** | Two components interact incorrectly | Layer mismatch, wrong API contract, frontend/backend disagreement, task not firing |

A bug can be multiple types simultaneously. Classify all that apply.
Each type gets its own diagnostic pass.

---

## Phase 2: Diagnostic Strategy by Bug Type

### 2.1 Runtime Error Debugging

**Signal:** Stack trace, exception, 500 response, process crash.

**Decision Tree:**

```
1. Read the full stack trace — bottom to top
   → Bottom: where the exception was raised (the source)
   → Top: where it entered the request pipeline (the entry point)
   → Middle: the call chain (the path)

2. Locate the first frame inside application code (not library code)
   → That frame is the proximate cause
   → The root cause may be higher up the call chain

3. Classify the exception type:
   → AttributeError / KeyError / TypeError
       → Data shape mismatch — something is None, missing, or wrong type
       → Check: what is the actual value vs. expected value at that line?

   → IntegrityError / UniqueViolation / ForeignKeyViolation
       → DB constraint violated — application logic did not guard it
       → Check: what invariant was supposed to prevent this?
       → Check: is the guard missing, wrong, or racing?

   → OperationalError / TimeoutError / ConnectionRefusedError
       → Infrastructure — DB connection pool, network, service unavailable
       → Check: connection pool exhaustion, DB overload, config error

   → ValidationError (Pydantic)
       → Input or output shape mismatch
       → Check: request body vs schema, ORM model vs response schema

   → HTTPException (unexpected)
       → Business logic raising HTTP exception from wrong layer
       → Check: is this raised from a service or repo? Should be domain exception.

   → RecursionError / MemoryError
       → Structural — circular dependency, unbounded recursion, memory leak
       → Check: call graph for cycles, loop for missing termination condition

4. State the root cause before writing a fix
```

**Runtime error output format:**

```
Exception:    [type and message]
Location:     [file, function, line]
Proximate cause: [what failed at that exact line]
Root cause:   [why that value/state/condition existed]
Call chain:   [how execution arrived there]
Fix:          [minimum change to address root cause]
Verification: [how to confirm the fix is correct]
```

**Common FastAPI runtime errors and their actual causes:**

```python
# 422 Unprocessable Entity
# Symptom: FastAPI returns 422 with validation errors
# Actual causes (in order of frequency):
#   1. Request body field name mismatch (camelCase vs snake_case)
#   2. Wrong content-type header (missing application/json)
#   3. Optional field being sent as null when schema expects the field absent
#   4. UUID sent as string without proper UUID format
#   5. Nested model not matching inner schema

# Diagnosis — read the 422 detail body:
# {"detail": [{"loc": ["body", "field_name"], "msg": "...", "type": "..."}]}
# loc tells you exactly which field failed and where in the hierarchy

# ---

# MissingGreenlet / greenlet_spawn error
# Symptom: "greenlet_spawn has not been called; Can't call await_only() here"
# Root cause: SQLAlchemy async session accessed outside async context,
#             or lazy-loaded relationship accessed after session closed
# Fix: use selectinload/joinedload at query time, or access within session scope

# ---

# DetachedInstanceError
# Symptom: "Instance <Model> is not bound to a Session"
# Root cause: ORM object returned from repo, session closed, then attribute accessed
# Fix: eager-load all needed relationships before session closes,
#      or use model_validate() to detach into Pydantic before returning

# ---

# Task received non-serializable argument
# Symptom: Celery task fails on dispatch with kombu serialization error
# Root cause: ORM object, Pydantic model, or UUID passed as task argument
# Fix: serialize to primitives before dispatch — str(uuid), model.model_dump()
```

---

### 2.2 Logic Bug Debugging

**Signal:** No crash. Wrong output, wrong DB state, wrong behavior.

This is the hardest bug type because the system believes it is correct.

**Strategy: Trace the Data**

Logic bugs are always a discrepancy between what the code computes and what it
should compute. Find where the divergence begins.

```
1. Define the expected behavior precisely
   → "Given input X, the output should be Y"
   → "After operation Z, the DB state should be W"
   → Be exact — vague expected behavior produces vague diagnoses

2. Trace the actual execution path
   → Start at the entry point (route)
   → Follow the data through each layer
   → At each layer, ask: is the data correct here?
   → The layer where data becomes wrong is the proximate cause

3. At the layer where data diverges:
   → What transformation happened?
   → Was it wrong logic, wrong data input, or a wrong assumption?

4. Trace back to find why that layer received wrong input
   → The root cause is usually higher up
```

**Common logic bug patterns in FastAPI:**

```python
# Wrong: Pydantic model_dump() includes None fields, corrupting partial updates
async def update_user(db, id, data: UserUpdateRequest):
    user = await user_repo.get_or_raise(db, id=id)
    # Wrong — overwrites fields not included in the request with None
    for field, value in data.model_dump().items():
        setattr(user, field, value)

# Correct — exclude_unset drops fields the client didn't send
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

# ---

# Wrong: service returns stale data because flush() not called before read
async def create_and_return(db, data):
    obj = await repo.create(db, data)  # adds to session, not yet in DB
    count = await repo.count(db)       # reads from DB — doesn't see new obj
    return obj, count

# Correct — flush before reading
    obj = await repo.create(db, data)
    await db.flush()                   # pushes to DB within transaction
    count = await repo.count(db)       # now sees the new obj
    return obj, count

# ---

# Wrong: timezone-naive datetime comparison
if record.created_at > datetime.utcnow():  # naive vs naive — works accidentally

# Breaks when: DB stores UTC, application compares with local time
# Correct — always timezone-aware
from datetime import timezone
if record.created_at > datetime.now(timezone.utc):

# ---

# Wrong: list mutation inside a loop changes iteration
items = await repo.get_all(db)
for item in items:
    if item.should_delete:
        items.remove(item)  # mutates list during iteration — skips items

# Correct
items = [item for item in items if not item.should_delete]
```

---

### 2.3 Performance Bug Debugging

**Signal:** High latency, timeouts, DB query time, memory growth, CPU spike.

**Do not optimize without measuring.** Every performance fix must identify the
bottleneck by measurement, not intuition.

**Diagnostic Decision Tree:**

```
1. Where is the time being spent?
   → Add timing at the boundary of each layer:
     - Total request time (middleware or route decorator)
     - DB query time (SQLAlchemy event listeners or EXPLAIN ANALYZE)
     - External call time (httpx, Redis, etc.)
     - Service logic time (the remainder)

2. Is it the DB?
   → Run EXPLAIN ANALYZE on the slow query
   → Look for: Sequential Scan on large table, Nested Loop with high rows,
     Sort without index, Hash Join with large memory estimate
   → Fix: add index, rewrite query, use aggregation, paginate

3. Is it N+1?
   → Count the number of DB queries per request
   → If queries = 1 + N (where N = result set size), it is N+1
   → Fix: eager load or DB-level aggregation (see refactoring skill 2.4)

4. Is it sequential awaits on independent operations?
   → Profile: are independent async calls awaited one after another?
   → Fix: asyncio.gather()

5. Is it sync I/O blocking the event loop?
   → Symptom: single slow request blocks all other requests
   → Check: any requests/urllib/boto3/psycopg2 (sync) inside async functions
   → Fix: replace with async equivalents or run_in_executor

6. Is it memory?
   → Check: unbounded query results (no LIMIT), large object kept in memory,
     session not closed, connection pool leak
   → Fix: paginate queries, stream large results, close sessions explicitly
```

**EXPLAIN ANALYZE interpretation:**

```sql
-- Run this on any slow query
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders
WHERE user_id = 'uuid-here'
ORDER BY created_at DESC;

-- Red flags in output:
-- "Seq Scan" on table with > 10k rows → missing index
-- "rows=10000" with "actual rows=1" → bad statistics, run ANALYZE
-- "Nested Loop" with large outer rows → N+1 at DB level
-- "Sort" with "Sort Method: external merge" → spilling to disk, add index
-- Buffers: "read=10000" → cold cache, consider pg_prewarm or query restructure
```

---

### 2.4 Concurrency Bug Debugging

**Signal:** "Works sometimes", "intermittent failure", "data is wrong under load",
race conditions, deadlocks, lost updates, duplicate inserts.

These are the most dangerous bugs. They are often invisible in development and
catastrophic in production.

**Diagnostic Framework:**

```
1. Is it a race condition?
   → Two operations interleave and produce wrong state
   → Signal: wrong result only under concurrent load
   → Reproduce: run the same operation N times concurrently (asyncio.gather
     with 10-50 coroutines hitting the same endpoint)

2. Is it a lost update?
   → Two transactions read the same value, both modify it, last write wins
   → Signal: counter is wrong, balance is wrong, status reverted
   → Reproduce: concurrent updates to the same record

3. Is it a deadlock?
   → Two transactions each hold a lock the other needs
   → Signal: "deadlock detected" in DB logs, requests hang then fail
   → Reproduce: concurrent operations that update multiple tables in
     different orders

4. Is it an async ordering assumption?
   → Code assumes async operations complete in a specific order
   → Signal: intermittent failure depending on timing
   → Check: any logic that depends on the order of concurrent tasks
```

**Fixes by concurrency bug type:**

```python
# Race condition fix — optimistic locking
class Order(Base):
    version: Mapped[int] = mapped_column(default=0, nullable=False)

async def update_order_status(db, order_id, new_status, expected_version):
    result = await db.execute(
        update(Order)
        .where(Order.id == order_id, Order.version == expected_version)
        .values(status=new_status, version=Order.version + 1)
        .returning(Order)
    )
    updated = result.scalar_one_or_none()
    if not updated:
        # Another transaction modified this row — retry or raise conflict
        raise OptimisticLockError(order_id=order_id)

# ---

# Lost update fix — pessimistic locking (SELECT FOR UPDATE)
async def increment_counter(db, resource_id):
    # Lock the row before reading — no other transaction can modify until commit
    result = await db.execute(
        select(Resource)
        .where(Resource.id == resource_id)
        .with_for_update()  # acquires row-level lock
    )
    resource = result.scalar_one()
    resource.counter += 1
    await db.flush()
    # Lock released on commit (managed by get_db dependency)

# ---

# Deadlock fix — consistent lock ordering
# If operation A locks table_1 then table_2, operation B must do the same
# Never: A locks (table_1, table_2), B locks (table_2, table_1)

async def transfer_funds(db, from_id, to_id, amount):
    # Always lock in consistent UUID order to prevent deadlock
    first_id, second_id = sorted([from_id, to_id])
    first = await db.execute(
        select(Account).where(Account.id == first_id).with_for_update()
    )
    second = await db.execute(
        select(Account).where(Account.id == second_id).with_for_update()
    )
    # Now safe to modify both

# ---

# Async ordering fix — do not assume gather() order implies execution order
results = await asyncio.gather(create_user(db), create_profile(db))
# Wrong assumption: create_user always completes before create_profile
# If create_profile depends on user existing — do not gather, await sequentially
```

---

### 2.5 Data Bug Debugging

**Signal:** Constraint violations, wrong query results, stale data, migration
failures, DB state inconsistency.

**Diagnostic Process:**

```
1. What is the actual DB state?
   → Query directly — never trust application-layer assumptions about DB state
   → SELECT the affected rows with all relevant columns
   → Check: does the data match what the application believes?

2. When did the DB state become wrong?
   → Check created_at / updated_at timestamps
   → Check migration history: SELECT * FROM alembic_version
   → Check if a specific migration introduced the drift

3. Is it a migration problem?
   → alembic current — what version is the DB at?
   → alembic heads — what version should it be at?
   → alembic history — what migrations exist?
   → If out of sync: never run alembic upgrade blindly on production
     first inspect the migration SQL with alembic upgrade --sql

4. Is it a constraint violation?
   → Read the full IntegrityError message — it names the constraint
   → Find the constraint definition in the ORM model or migration
   → Determine: is the constraint correct and the data wrong,
     or is the constraint wrong and needs to be relaxed?
   → Never drop a constraint to fix a data bug — fix the data or the logic

5. Is it stale data?
   → Caching layer returning old data?
   → SQLAlchemy session identity map returning cached ORM object?
   → Fix: db.expire(obj) or db.refresh(obj) to force re-read from DB
```

**Migration failure debugging:**

```python
# Alembic migration fails mid-run — DB is in partial state
# Never re-run the migration — it will fail again or corrupt further

# Step 1: Check what the migration did before failing
# alembic upgrade --sql > migration.sql  (preview the SQL)

# Step 2: Inspect current DB state
# SELECT column_name, data_type FROM information_schema.columns
# WHERE table_name = 'affected_table';

# Step 3: If migration is partially applied:
# Write a repair migration that picks up from the failure point
def upgrade():
    # Check if column already exists before adding (idempotent repair)
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [c['name'] for c in inspector.get_columns('table_name')]
    if 'new_column' not in columns:
        op.add_column('table_name', sa.Column('new_column', sa.String()))

# Step 4: All future migrations must be written to be re-runnable
# after a partial failure — use IF EXISTS / IF NOT EXISTS guards
```

---

### 2.6 Integration Bug Debugging

**Signal:** Two components interact incorrectly — layer mismatch, wrong API
contract shape, frontend not receiving expected data, Celery task not firing,
WebSocket event not emitted, SSE stream dropping events.

**Diagnostic: Define the Contract at the Boundary**

Integration bugs live at boundaries. Debug the boundary, not the internals.

```
1. State what each side of the boundary expects
   → Side A sends: [exact shape]
   → Side B expects: [exact shape]
   → Are they identical? If not, the integration bug is the mismatch.

2. For HTTP layer ↔ service layer:
   → Is the route passing the correct types to the service?
   → Is the service returning a type the route can serialize?
   → Is HTTPException being raised from the wrong layer?

3. For service ↔ repository:
   → Is the service passing ORM objects or primitives?
   → Is the repo returning ORM objects the service assumes are loaded?
   → Are lazy-loaded relationships accessed after session close?

4. For API ↔ frontend:
   → Log the exact response body at the route boundary
   → Log the exact request body received by FastAPI
   → Never debug frontend behavior by reading backend code — read the wire

5. For service ↔ Celery task:
   → Is the task registered? (celery inspect registered)
   → Is the broker reachable?
   → Are arguments serializable? (UUID, datetime, Pydantic → must be primitives)
   → Is the task actually being called? (add log at dispatch site)
   → Is the worker running and consuming the right queue?

6. For SSE/WebSocket:
   → Is the event being emitted? (log at emit site)
   → Is the client connected and subscribed to the right channel?
   → Is there a serialization error silently dropping the event?
   → Is the connection being closed before the event fires?
```

**Common integration bug patterns:**

```python
# Wrong: route passes Pydantic model to service expecting primitives
@router.post("/items")
async def create_item(body: ItemCreateRequest, db=Depends(get_db)):
    return await item_service.create(db, body)  # service receives Pydantic model

# If service does: item_service.create(db, user_id, name, description)
# it will fail — argument count mismatch, or wrong type

# Correct — match the service's expected signature
    return await item_service.create(db, user_id=current_user.id, data=body)

# ---

# Wrong: Celery task dispatched with ORM object
order = await order_repo.get(db, id=order_id)
send_confirmation.delay(order)  # kombu cannot serialize SQLAlchemy model

# Correct — serialize before dispatch
send_confirmation.delay(
    order_id=str(order.id),
    user_email=order.user.email,
    total=str(order.total),
)

# ---

# Wrong: SSE event dropped because generator closes before yield
async def event_stream(request: Request):
    yield f"data: {json.dumps(initial_data)}\n\n"
    # generator returns — connection closes — client misses subsequent events

# Correct — keep generator alive for the duration of the connection
async def event_stream(request: Request):
    yield f"data: {json.dumps(initial_data)}\n\n"
    while True:
        if await request.is_disconnected():
            break
        event = await event_queue.get()
        yield f"data: {json.dumps(event)}\n\n"
```

---

## Phase 3: Output Format by Complexity

### Simple Bug (single cause, obvious fix, ≤ 3 lines changed)

Use the decision tree format. Fast, direct, no ceremony.

```
Bug type:     [classification]
Root cause:   [one sentence — exact cause]
Why:          [one sentence — mechanism]
Fix:          [code, minimum change]
Verify:       [one sentence — how to confirm]
```

### Complex Bug (multiple causes, systemic, > 3 files or layers involved)

Use the structured diagnosis report format.

```
## Bug Report

### Classification
[All types that apply, e.g., "Concurrency Bug + Data Bug"]

### Observed Behavior
[Exact symptom — error message, wrong output, DB state]

### Expected Behavior
[Exact expected state — precise, not vague]

### Root Cause Analysis

#### Proximate Cause
[What failed, where, at what layer]

#### Root Cause
[Why that failure occurred — the actual origin]

#### Mechanism
[How the root cause produces the observed symptom — the causal chain]

#### Contributing Factors
[Any conditions that enabled or amplified the bug]

### Evidence
[Specific code locations, query results, log lines, stack frames
 that support the diagnosis — no guesses, only evidence]

### Blast Radius
[What else might be affected by the same root cause]

### Fix

#### Minimum Change
[Exact code change — complete files, not diffs]

#### Why This Fixes It
[How the fix addresses the root cause, not just the symptom]

#### What Was Not Changed
[Explicitly state what working code was left untouched]

### Verification
[Exact steps to confirm the fix is correct — query to run,
 request to make, log to check, behavior to observe]

### Follow-up
[Any structural issues uncovered during debugging that should
 be addressed separately — logged, not fixed inline]
```

---

## Phase 4: Debugging Execution Rules

### 4.1 Information Requirements

If the provided information is insufficient to diagnose the root cause, request
the minimum additional information needed. Do not guess to fill gaps.

```
Always useful:
  → Full stack trace (not just the last line)
  → The exact input that triggered the bug
  → The exact output or error received
  → The expected output

Often needed:
  → Relevant model definitions (ORM and Pydantic)
  → The service/repo function involved
  → DB schema for affected tables
  → Alembic migration history if data is involved
  → Celery task definition if async behavior is involved

For concurrency bugs specifically:
  → Number of concurrent requests when it fails
  → Whether it reproduces under low load
  → DB transaction isolation level
```

### 4.2 Forbidden Debugging Behaviors

```
❌ "Try adding a try/except around that" — suppression is not a fix
❌ "It might be a caching issue" — state a hypothesis with evidence
❌ "This could be related to X" — diagnose, don't speculate
❌ "Add print statements and see what happens" — give specific instrumentation
❌ Fixing code that wasn't identified as the root cause
❌ Changing working code "while I'm in here"
❌ Delivering a fix without explaining the root cause
❌ Delivering a fix for a symptom when the root cause is elsewhere
❌ "This should work" — verify it works, or state what to verify
❌ Guessing at the fix and delivering it as a diagnosis
```

### 4.3 Instrumentation Before Fixing

For any bug that cannot be diagnosed from the code alone, provide specific
instrumentation before the fix — not generic "add some logs."

```python
# Specific instrumentation for a logic bug in batch verification processing
import structlog
logger = structlog.get_logger(__name__)

async def process_verification_batch(service, emails):
    logger.debug("process_verification_batch: received batch", extra={
        "batch_size": len(emails),
        "unique_count": len(set(emails)),
    })

    result = await service.verify_emails(emails)
    logger.debug("process_verification_batch: verification completed", extra={
        "submitted": result.submitted,
        "completed": result.completed,
        "first_result_status": result.results[0].status if result.results else None,
    })
```

Instrumentation is temporary. Flag it as such. It comes out after the bug is confirmed.

---

## Phase 5: Debugging Checklist

```
Diagnosis
[ ] Bug type classified — all applicable types identified
[ ] Root cause stated explicitly — not a guess, evidence-based
[ ] Causal mechanism described — how cause produces symptom
[ ] Blast radius assessed — what else might be affected

Fix
[ ] Fix addresses root cause, not symptom
[ ] Minimum code changed — no working code touched
[ ] Complete files delivered — no diffs, no partial snippets
[ ] Fix does not introduce new behavior beyond correcting the bug

Verification
[ ] Specific verification steps provided
[ ] Edge cases considered — does the fix hold for related inputs?
[ ] If concurrency bug: fix verified under concurrent conditions, not just single-threaded

Follow-up
[ ] Any structural issues uncovered are noted separately
[ ] Any related code that has the same latent bug is flagged
[ ] Instrumentation removed or flagged for removal
```

---

## Reference Files

`references/principles.md` — Causality, conservation, invariants. A system does
exactly what it is told. Use these laws to reason about what must be true at
each point in the execution path.

`fastapi-backend-architecture/SKILL.md` — Layer definitions and contracts.
Most bugs are violations of layer boundaries or contract assumptions — knowing
the correct architecture reveals where the violation is.

`fastapi-refactoring/SKILL.md` — When debugging uncovers structural problems
that are not the immediate bug. Fix the bug first, then refactor separately.

---

## Import Deletion Safety Checklist (First-Principles Guardrail)

When cleanup/linting flags an import as "unused", do **not** delete blindly.

### 1) Side-effect imports
If an import triggers registration/bootstrapping, deleting it is dangerous.

- Celery task registration, plugin hooks, signal wiring, global registries.
- Any import that exists mainly for module-load side effects.
- Rule: if unsure, prove side effect absence before deletion.

### 2) Deferred usage patterns
A symbol can appear unused but still be operationally required.

- `TYPE_CHECKING` branches
- runtime `getattr`/dynamic lookup
- plugin discovery conventions
- decorators/metaclass hooks
- monkeypatch targets in tests

Rule: search call sites and dynamic references before deletion.

### 3) Near-field intent clues
Comments and docstrings often encode intent that static lint cannot infer.

- Adjacent TODOs / design notes
- "import required for X" comments
- module-level architecture notes

Rule: read the surrounding 20-40 lines and top-of-file docs before cleanup.

### 4) Post-change behavior checks
Even if lint passes, behavior can regress.

Minimum checks after import cleanup:
- relevant tests
- startup path validation
- key workflow smoke checks (the path touching the edited module)

Rule: no "unused import" cleanup is complete until behavior checks pass.
