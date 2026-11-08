---
name: code-comments-and-docstrings
description: >
  Write, preserve, update, and delete code comments and docstrings with surgical
  precision across any programming language. Use this skill for any task where
  comments are involved — writing new code, modifying existing code, reviewing
  code, or refactoring. Triggers include: "add comments", "document this",
  "write docstrings", "explain this code", "update the comments", or any task
  where existing comments may become outdated due to code changes. NEVER delete
  existing comments without explicit reason. NEVER add comments that describe
  what the code does. ALWAYS update comments when the code they describe changes.
  ALWAYS preserve the developer's mental model encoded in existing comments.
---

# Code Comments and Docstrings Skill

---

## Prime Directive: Comments Encode Mental Models

Comments are not documentation for the code. They are documentation for the
**human reasoning** that produced the code.

Code describes *what* the machine does. Comments describe *why a human made
this decision* — the constraint, the tradeoff, the non-obvious invariant, the
failure mode that was considered, the thing that will break if someone changes
this without understanding it.

A comment that restates the code is noise. A comment that explains the decision
behind the code is signal. Every comment must be signal.

---

## Prime Directive: Existing Comments Are Sacred

When modifying existing code:

```
Existing comment is still accurate   → preserve it exactly
Existing comment is now misleading   → update it to match the new reality
Existing comment refers to deleted code → delete it with the code
Existing comment is noise (restates code) → delete it — it was wrong to begin with
```

**Never silently delete a comment.** If a comment disappears without explanation,
the mental model it encoded is lost. If a comment must go, the reason must be
clear — the code itself now makes the point, or the decision no longer applies.

**Never rewrite a comment's meaning** without understanding what it was
communicating. A comment that says "this must run before X or Y will deadlock"
is not a candidate for rewording into something gentler. It says what it says
for a reason.

---

## Phase 1: The Comment Filter

Before writing any comment, pass it through this filter. If it fails, do not
write it.

### The Three Questions

**1. Does this tell the reader something the code cannot?**

If the answer is in the code — the function name, the type signature, the
variable name — the comment is redundant. Delete it or don't write it.

```
# Bad — code already says this
user_count = len(users)  # get the count of users

# Good — code does not say this
user_count = len(users)  # includes soft-deleted records — caller must filter if needed
```

**2. Would removing this comment cost a future reader real understanding?**

If a reader could figure this out in under 30 seconds by reading the surrounding
code, the comment is not earning its place. If it would take minutes, domain
knowledge, or a wrong assumption — the comment is necessary.

**3. Is this comment still true?**

A comment that was true when written but is now wrong is worse than no comment.
It actively misleads. If code changes and a comment does not, the comment must
be updated before the change ships.

---

## Phase 2: What Warrants a Comment

### Warranted: The Why Behind a Non-Obvious Decision

When the code makes a choice that looks wrong, inefficient, or unusual — but
is correct for a reason that isn't visible in the code itself.

```python
# We sort before hashing because the hash must be order-independent.
# Changing this breaks existing stored hashes in production.
canonical = ",".join(sorted(values))
```

```go
// Use int32 here not int64 — the wire protocol specifies 32-bit signed.
// Changing to int64 silently truncates on the receiving end.
var sequenceID int32
```

```typescript
// Delay is intentional — the DOM needs one tick to render before we measure.
// requestAnimationFrame alone is not sufficient here; tested on Safari 16.
await new Promise(resolve => setTimeout(resolve, 0))
```

### Warranted: Invariants That Must Hold

When a piece of code only works correctly if a condition is always true —
and that condition is not enforced by the type system or a visible assertion.

```python
# items must be sorted by created_at ascending before reaching this point.
# The linked-list insertion logic below assumes sorted order.
# If order is wrong, parent_id assignments will be silently incorrect.
for item in items:
    ...
```

```rust
// SAFETY: ptr is guaranteed non-null by the allocator contract above.
// The only caller (create_buffer) checks null before returning.
unsafe { ptr.as_ref() }
```

### Warranted: What Will Break If This Changes

When a piece of code has a hidden dependency — something that will silently
fail if someone modifies this line without knowing the constraint.

```python
# Do not change the column order here — the migration script in
# migrations/0042_reorder_columns.py references positions, not names.
columns = ["id", "created_at", "user_id", "status"]
```

```typescript
// This key must match the value set in the auth middleware.
// Mismatch causes silent auth bypass — no error is thrown.
const USER_CONTEXT_KEY = "authenticated_user"
```

### Warranted: Workarounds and Known Defects

When code exists to work around a bug, limitation, or known deficiency in
a dependency, language, or platform — and could be mistaken for unnecessary
code.

```python
# Workaround for SQLAlchemy asyncio bug: session.get() does not respect
# with_for_update() in async mode. Using execute(select(...)) instead.
# Remove when SQLAlchemy > 2.0.25 is stable in this project.
result = await db.execute(select(Model).where(...).with_for_update())
```

```go
// strconv.Atoi silently wraps on 32-bit systems for values > MaxInt32.
// ParseInt with bitSize=64 is explicit and safe across architectures.
val, err := strconv.ParseInt(input, 10, 64)
```

### Warranted: Non-Obvious Performance Decisions

When code is written in a way that looks inefficient but is deliberately
optimized — or looks optimized but has a subtle cost.

```python
# Precompute outside the loop — re-evaluating settings.pattern on each
# iteration caused a 40ms regression on large datasets. Profiled 2024-11.
pattern = re.compile(settings.pattern)
for record in records:
    if pattern.match(record.value):
        ...
```

### Warranted: Security-Critical Behavior

When code implements a security invariant that must not be broken — and the
consequence of breaking it is not obvious from the code.

```python
# Always run hash verification even when user is not found.
# Skipping this leaks valid emails via response time difference (timing attack).
hash_to_check = user.password_hash if user else DUMMY_HASH
is_valid = verify(plaintext, hash_to_check)
```

### Warranted: Docstrings on Public Interfaces

Public functions, methods, and classes that form an interface boundary —
whether consumed by other developers, other modules, or external callers —
warrant a docstring. Internal implementation details do not.

The docstring communicates the contract: what goes in, what comes out, what
can go wrong, and any constraint the caller must satisfy.

---

## Phase 3: What Does Not Warrant a Comment

These patterns produce noise. Delete them when found. Do not write them.

### The Restatement

```python
# Bad
user = get_user(user_id)  # get the user by user_id
total = price * quantity   # calculate total

# The code says this. The comment adds nothing.
```

### The Type Annotation in Prose

```typescript
// Bad
// name is a string
// count is a number
const name: string = getUserName()
const count: number = getTotal()

// The type system says this.
```

### The Step-by-Step Narration

```python
# Bad
# Step 1: fetch the user
user = await user_repo.get(db, id=user_id)
# Step 2: check if user exists
if not user:
    raise NotFoundError()
# Step 3: return the user
return user

# The code is the steps. Comments between every line are an insult to the reader.
```

### The Outdated Comment

```python
# Bad — code was changed, comment was not updated
# Returns a list of active users
async def get_users(db, include_deleted: bool = False):
    # Now returns all users, not just active ones — comment is wrong
    return await db.execute(select(User))
```

An outdated comment is not a harmless artifact. It is an active lie. Update
or delete it when the code changes.

### The Commented-Out Code

```python
# Bad
# old_result = legacy_compute(data)
result = new_compute(data)
```

Commented-out code is not a comment. It is dead code with extra steps. It
belongs in version control history, not in the file. Delete it.

### The Obvious Todo With No Action

```python
# Bad
# TODO: fix this later
# TODO: optimize
# TODO: handle error
```

A TODO without a specific action, owner, or ticket reference is decoration.
If a TODO is worth keeping, it must say what specifically needs doing and why
it was deferred.

```python
# Acceptable TODO
# TODO: replace with streaming once httpx 0.26 is stable in this project.
# Blocking read here causes memory spike on responses > 100MB.
```

---

## Phase 4: Docstring Standard

Docstrings document the **contract** of a public interface. They are written
for the caller, not the implementer.

### What a Docstring Communicates

```
What this does        — one sentence, the job, not the implementation
Parameters            — only non-obvious ones; obvious names need no description
Returns               — what comes back and in what form
Raises                — what exceptions and under what conditions
Constraints           — what the caller must ensure (preconditions)
Side effects          — what this changes beyond the return value
```

A docstring that describes implementation detail is wrong. The implementation
can change — the contract is what the caller depends on.

### Docstring Length Rule

**One sentence for the summary. Two to four sentences maximum for the body.**
If a docstring needs more than four sentences, the function has too many
responsibilities — split it, don't document it into submission.

### Language-Specific Format (Apply the Standard, Not the Verbosity)

The standard is language-agnostic. Adapt the syntax to the language.

**Python**
```python
async def transfer_funds(
    db: AsyncSession,
    from_account_id: UUID,
    to_account_id: UUID,
    amount: Decimal,
) -> TransferResult:
    """
    Transfer funds between two accounts atomically.

    Acquires row-level locks in consistent UUID order to prevent deadlock
    under concurrent transfers. Raises InsufficientFundsError if from_account
    balance is below amount at lock time — not at call time.
    """
```

**TypeScript / JavaScript**
```typescript
/**
 * Transfer funds between two accounts atomically.
 *
 * Acquires row-level locks in consistent UUID order to prevent deadlock
 * under concurrent transfers. Throws InsufficientFundsError if balance
 * is below amount at lock time — not at call time.
 */
async function transferFunds(
  fromAccountId: string,
  toAccountId: string,
  amount: bigint,
): Promise<TransferResult>
```

**Go**
```go
// TransferFunds moves funds between two accounts atomically.
//
// Acquires row-level locks in consistent ID order to prevent deadlock
// under concurrent transfers. Returns ErrInsufficientFunds if balance
// is below amount at lock time — not at call time.
func TransferFunds(ctx context.Context, from, to uuid.UUID, amount int64) (*TransferResult, error)
```

**Rust**
```rust
/// Transfer funds between two accounts atomically.
///
/// Acquires row-level locks in consistent UUID order to prevent deadlock
/// under concurrent transfers. Returns `Err(InsufficientFunds)` if balance
/// is below `amount` at lock time — not at call time.
pub async fn transfer_funds(
    from: Uuid,
    to: Uuid,
    amount: u64,
) -> Result<TransferResult, TransferError>
```

---

## Phase 5: Comment Maintenance Rules

These rules apply every time existing code is modified.

### Rule 1: Touch the Code, Check the Comments

Every function, block, or module modified must have its comments reviewed.
If a comment is now inaccurate — even partially — it must be updated before
the change ships. An inaccurate comment is a bug.

### Rule 2: The Comment Travels With Its Code

If a block of code moves to a different file, function, or module, its
comments move with it. Comments do not stay behind as orphans. Comments
do not get dropped during moves. If the comment no longer applies in the
new location, it gets updated — not deleted silently.

### Rule 3: Deletions Are Explicit

If removing a comment:
- Because the code now makes the point: fine — the code is now
  self-documenting on this point
- Because the decision no longer applies: fine — note in the commit
  why the constraint was lifted
- Because it "looks cleaner": not acceptable — clean is not a reason
  to lose encoded knowledge

### Rule 4: Refactoring Does Not Erase Comments

A structural refactor does not give license to discard comments. The mental
model encoded in a comment survives a rename, a split, a layer move. Carry
it forward.

---

## Phase 6: Comment Density by Context

Not all code has the same comment density. Match density to context.

### High Density (More Comments Warranted)
- Security-critical code — auth, encryption, token handling
- Concurrency logic — locks, atomic operations, race condition guards
- Workarounds and known defects
- Complex algorithms with non-obvious correctness proofs
- Public API interfaces and library code
- Code with external invariants (wire protocol, DB constraint, platform quirk)

### Medium Density (Selective Comments)
- Service layer business logic — comment the non-obvious rules only
- Database queries with complex joins or aggregations — comment the why
- Configuration and initialization code — comment non-obvious settings

### Low Density (Minimal Comments)
- Simple CRUD operations — code is self-explanatory
- Type definitions and data models — names carry the meaning
- Standard library usage — no comment needed on well-known patterns
- Test code — test names and assertions document intent

### No Comments Needed
- Getters and setters
- Trivial transformations
- Code where the function name is the comment

---

## Phase 7: Comment Quality Checklist

Run this on every comment before it ships — whether writing new or
reviewing existing.

```
Signal test
[ ] Does this tell the reader something the code cannot?
[ ] Would removing this cost a future reader real understanding?
[ ] Is this still true given the current state of the code?

Content test
[ ] Does this explain WHY, not WHAT?
[ ] Is it four sentences or fewer?
[ ] Does it communicate one clear idea — not a paragraph of hedging?
[ ] Is it precise enough to be actionable — not vague enough to be useless?

Maintenance test
[ ] If the code this describes changes, will this comment be obviously wrong?
    (Good — it means it will be caught and updated)
[ ] Does this comment travel with its code if the code moves?
[ ] Is any commented-out code present? (Delete it)
[ ] Are there outdated TODOs? (Update or delete them)

Noise test
[ ] Does this restate what the code says? (Delete it)
[ ] Does this describe a type the type system already declares? (Delete it)
[ ] Is this a step-by-step narration of sequential lines? (Delete it)
[ ] Was this generated to look thorough rather than to communicate? (Delete it)
```
