---
name: domain-spec-documentation
description: >
  Generate precise, mental-model-building specification documentation for backend
  domains. Use this skill whenever a domain's behaviors, design choices, state
  machines, side effects, use cases, constraints, or non-goals need to be documented
  for any consumer — human or AI agent. Triggers include: "document this domain's
  behavior", "write the spec for X", "explain how X works", "document the design
  decisions", "why does X work this way", "document the side effects", "what are
  the use cases for X", "document the state machine", or any request where the
  goal is understanding a domain deeply rather than implementing against its routes.
  Output is always domain-scoped. Always written in domain language — precise but
  never a code dump.
---

# Domain Spec Documentation Skill

> This skill produces the mental model document for a domain. Its job is to
> make the domain fully understood — its purpose, its rules, its states, its
> limits, and the reasoning behind its design — without describing implementation.
>
> Pair with `fastapi-api-documentation/SKILL.md` for the technical contract.
> The two documents live together in the domain's folder:
> `docs/[domain]/api.md` and `docs/[domain]/spec.md`

---

## Prime Directive: Build the Mental Model

This document does not describe routes. It does not document request fields.
It builds the mental model of the domain — the understanding that makes every
route, every constraint, and every design choice make sense.

A reader who finishes this document should be able to:
- Explain what this domain is responsible for and why it exists
- Predict how the domain behaves in any scenario without consulting the API doc
- Understand why the domain is designed the way it is
- Know exactly what the domain will and will not do
- Make correct implementation decisions without guessing

**If the API doc tells you what the domain exposes, this document tells you
why it works that way and what it means.**

---

## Prime Directive: Domain Language, Not Implementation Language

Write at the domain level. Reference domain terms, field names, state names,
and entity relationships precisely — but never describe implementation detail.

```
Implementation language (wrong):
  "The series_id column is a non-nullable UUID foreign key referencing
   the migration_series table with ON DELETE CASCADE."

Domain language (correct):
  "A migration belongs to exactly one series and cannot exist without one.
   When a series is deleted, all its migrations are deleted with it."
```

Both statements are precise. Only one builds mental model.
Only one is readable by a human and an AI agent equally.

---

## Prime Directive: Consumers Are Both Human and AI

Every sentence must be unambiguous enough for an AI agent to act on it
correctly, and clear enough for a human to internalize it without effort.

This means:
- No vague language ("usually", "typically", "in most cases") — if there
  is an exception, state it explicitly
- No implicit assumptions — if something must always be true, say "always"
- No undefined terms — every domain term used is defined in the Glossary
- No orphaned rules — every rule states what it governs and why it exists

---

## Phase 1: Document Structure

Every domain spec file follows this structure, in this order.

```
# [Domain Name] — Domain Specification

## Purpose
## Core Concepts
## Entities
## Behaviors
## State Machines  (if the domain has stateful entities)
## Use Cases
## Design Decisions
## Constraints and Non-Goals
## Side Effects
## Glossary
## Changelog
```

Sections with no content for a given domain are omitted — but their absence
must be intentional, not an oversight. If a domain has no state machines,
that is because its entities are stateless — note it in Behaviors.

---

## Phase 2: Section Specifications

### 2.1 Purpose

Three to five sentences. Answers:
- What problem does this domain solve?
- What would break or be impossible without it?
- Where does this domain sit in the larger system?

No design decisions here. No behaviors. Just the fundamental reason this
domain exists.

```markdown
## Purpose

The Migrations domain is responsible for managing the complete lifecycle of
database migration scripts — from authoring to execution to rollback. It
exists because schema changes to a connected database must be versioned,
ordered, and reversible. Without this domain, there is no controlled path
from one database schema to another. It sits between the user's intent
(change this database) and the connected database (apply this change safely).
```

### 2.2 Core Concepts

The two to five foundational ideas the entire domain is built on. These are
the concepts every other section assumes the reader understands. Each concept
gets a short paragraph — enough to define it precisely and explain why it
matters.

```markdown
## Core Concepts

**Series**
A series is an ordered sequence of migrations that share a common purpose or
target. Migrations within a series are always executed in order and never
independently reordered. A series is the unit of intent — it represents a
coherent set of changes to a database schema.

**Linked Order**
Migrations within a series are ordered by a linked-list relationship, not by
timestamps or manual numbering. Each migration knows only its predecessor.
This design means order is always unambiguous and cannot be corrupted by
concurrent inserts or clock skew. The backend owns and assigns order — the
frontend never sets or infers it.

**Execution**
Execution is the act of running a migration's SQL against a connected database.
It is irreversible at the database level — the migration record can be marked
rolled back, but the database changes must be undone by running the rollback SQL.
Execution is always single-migration, always explicit, and always guarded against
duplication.
```

### 2.3 Entities

The domain's primary entities — what they are, what they contain (at the
domain level), and how they relate to each other. This is not a schema dump.
It is a description of what each entity represents and what it carries.

```markdown
## Entities

**Migration**
A migration is a named, versioned unit of change — a pair of SQL statements
(forward and optional rollback) attached to a position in a series. It carries
its own status, its relationship to its predecessor, and a reference to the
series it belongs to. A migration without a series cannot exist.

**Series**
A series is a named container for an ordered set of migrations against a
specific connected database. It carries no SQL of its own — only metadata
about the sequence. Deleting a series deletes all its migrations.

**Relationships**
- A migration belongs to exactly one series. This is permanent — a migration
  cannot be moved between series.
- A migration has at most one predecessor (the migration before it in the series).
- The first migration in a series has no predecessor.
- The most recent migration in a series has no successor — it is the tail.
```

### 2.4 Behaviors

How the domain behaves — the rules it enforces, the guarantees it makes,
and the conditions it responds to. This section describes what the domain
does, not how it does it.

Behaviors are written as declarative statements. Each behavior is a rule
the domain always follows.

```markdown
## Behaviors

**Ordering**
The backend assigns execution order at creation time. Order cannot be set,
overridden, or suggested by the frontend. A new migration is always appended
to the tail of its series — insertion in the middle or beginning is not
supported. If a specific position is needed, the series must be reconstructed.

**Status Progression**
A migration's status moves forward — it never moves backward except via
explicit rollback. A completed migration cannot be re-executed. A failed
migration can be retried. A rolled-back migration can be re-executed from
the pending state.

**Rollback Availability**
Rollback is only available if the migration was created with rollback SQL.
A migration created without rollback SQL is permanently forward-only. The
frontend must communicate this constraint to users before execution.

**Duplicate Execution Prevention**
The backend guarantees a migration cannot be executed twice concurrently.
If an execution is already in progress, a second request for the same migration
is rejected. The frontend should disable execution controls while status is
`running`.

**Series Integrity**
The order of a series is always consistent. Deleting a migration from the
middle of a series is not supported — only the tail migration can be deleted,
and only if it has never been executed. This preserves the integrity of the
execution history.
```

### 2.5 State Machines

For every stateful entity in the domain, document its state machine in
context — what each state means, what causes each transition, and which
states are terminal.

States and transitions are described in domain language. Diagrams use
plain-text notation readable by both humans and AI agents.

```markdown
## State Machines

### Migration Status

A migration's status represents where it is in its lifecycle. Status is
the frontend's primary signal for what actions are available and what
happened during execution.

**States**

| State | Meaning |
|-------|---------|
| `pending` | Created, not yet executed. All actions available. |
| `running` | Execution is in progress. No actions available. |
| `completed` | Executed successfully. Only rollback available (if rollback SQL exists). |
| `failed` | Execution attempted but the SQL produced an error. Retry available. |
| `rolled_back` | Rollback SQL was executed. Re-execution available. |

**Transitions**

\`\`\`
pending ──[execute]──────────────► running
running ──[execution succeeds]──► completed
running ──[execution fails]─────► failed
completed ──[rollback]──────────► rolled_back
failed ──[retry]────────────────► running
rolled_back ──[execute]─────────► running
\`\`\`

**Terminal States**
There are no permanent terminal states. `completed` is stable but not terminal —
it can transition to `rolled_back`. `failed` is recoverable via retry.

**What the Frontend Should Know**
- A migration in `running` state must have all action controls disabled.
- A migration in `completed` state with no rollback SQL has no available actions.
- A migration in `failed` state carries an error message — surface it to the user.
- Status is always authoritative from the server. Do not derive or predict it.
```

### 2.6 Use Cases

The concrete scenarios this domain is built to serve. Each use case describes
a real user or system goal and how the domain fulfills it. No routes. No fields.
Just the narrative of what happens and why the domain handles it the way it does.

```markdown
## Use Cases

**Authoring a migration**
A developer writes a migration to add a table to their connected database.
They provide the forward SQL and optionally the rollback SQL. The backend
assigns it a position in the series. The developer does not need to know
or manage the position — the series always stays consistent.

**Executing in order**
A developer wants to bring a database schema up to date. They execute
migrations one at a time, in the order the series defines. The backend
enforces that each migration can only execute after its predecessor
completed. This prevents schema drift from out-of-order execution.

**Recovering from a failure**
An execution fails because the SQL contains an error. The migration moves
to `failed` status and captures the error message. The developer reads the
error, edits the SQL in a new migration (or fixes the database state manually),
and retries. The series remains intact — no surgery on the existing record.

**Undoing a change**
A developer realizes a migration introduced a problem. If the migration was
created with rollback SQL, they execute the rollback. The database change is
reversed, and the migration returns to a state where it can be re-executed
after the problem is fixed.
```

### 2.7 Design Decisions

The explicit choices made in how this domain is designed — with the reason
for each choice. This section is written so that a future developer (or AI
agent) understands why the domain is the way it is and does not accidentally
undo a deliberate decision.

Each decision follows this format:
- **Decision:** What was decided
- **Why:** The reasoning
- **Tradeoff:** What this costs or rules out

```markdown
## Design Decisions

**The backend owns execution order**
- Decision: The frontend cannot set or suggest the position of a migration
  in a series. The backend assigns it at creation time.
- Why: Allowing the frontend to set order creates a race condition — two
  concurrent creates could claim the same position, corrupting the series.
  Centralizing order assignment makes the series always consistent.
- Tradeoff: The frontend cannot insert a migration in the middle of an
  existing series. Reordering requires reconstructing the series.

**Linked-list ordering instead of an index field**
- Decision: Migrations reference their predecessor rather than carrying an
  integer position.
- Why: Integer positions require renumbering on insert or delete, which is
  an expensive and race-prone operation on large series. A linked list makes
  insert and delete O(1) with no renumbering.
- Tradeoff: Computing the full ordered sequence requires traversal. The backend
  always returns migrations pre-ordered — the frontend should never sort them.

**No mid-series deletion**
- Decision: Only the tail migration of a series can be deleted, and only if
  it has never been executed.
- Why: Deleting a migration from the middle of a series would leave a gap in
  the execution history. That history is the audit trail of how a database
  reached its current schema. Gaps in the trail make recovery from failure
  ambiguous.
- Tradeoff: Correcting a mistake in the middle of a series requires appending
  a new migration that undoes the mistake, not editing the original.
```

### 2.8 Constraints and Non-Goals

What the domain explicitly does not do, and what invariants always hold.
These exist to prevent scope creep, misuse, and incorrect assumptions.

```markdown
## Constraints and Non-Goals

**Constraints — invariants that always hold**
- A migration always belongs to exactly one series. This cannot change.
- Execution order within a series is always consistent and always assigned
  by the backend.
- A migration that has been executed cannot be edited. The SQL is immutable
  after execution.
- Execution is always against a specific connected database — migrations
  are not database-agnostic.

**Non-Goals — what this domain does not do**
- This domain does not validate that the migration SQL is syntactically
  correct before execution. Validation is the responsibility of the database
  at execution time.
- This domain does not manage database connections. Connection management
  belongs to the Connections domain.
- This domain does not support branching series — a series is always linear.
  Branching schema strategies must be modeled as separate series.
- This domain does not automatically execute migrations. Execution is always
  an explicit user action. There is no auto-run, no scheduled execution.
```

### 2.9 Side Effects

What happens in other domains or systems as a result of actions in this domain.
Written from the perspective of the observer — what a frontend developer,
system integrator, or AI agent should expect to happen outside this domain
when something happens inside it.

```markdown
## Side Effects

**On migration created**
A notification is dispatched to the user confirming the migration was added
to the series. No other domains are affected at creation time.

**On execution started**
The connected database enters a locked state for the duration of the execution.
Other operations against that database connection may be queued or rejected
until execution completes. The real-time domain emits a `migration.started`
event — the frontend should update status immediately without waiting for
`migration.completed`.

**On execution completed**
The connected database's schema has changed. Any cached schema introspection
in the Schema domain is invalidated. A `migration.completed` event is emitted
via the real-time domain. A notification is dispatched to the user.

**On execution failed**
No database changes were applied — the backend wraps execution in a transaction
and rolls back on failure. The error is captured on the migration record.
A `migration.failed` event is emitted. A notification is dispatched.

**On series deleted**
All migrations in the series are deleted. This is irreversible. No events
are emitted per migration — a single `series.deleted` event covers the
operation. The frontend must not assume individual `migration.deleted` events
will fire.
```

### 2.10 Glossary

Every domain-specific term used in this document, defined precisely.
The glossary is the authoritative reference for this domain's vocabulary.
If a term appears in this document, it appears in the glossary.

```markdown
## Glossary

**Series** — An ordered, named sequence of migrations sharing a common purpose.
The unit of intent for a schema change campaign.

**Migration** — A named, versioned unit of change consisting of forward SQL
and optional rollback SQL, belonging to exactly one series.

**Tail** — The most recent migration in a series — the one with no successor.
New migrations are always appended to the tail.

**Execution** — The act of running a migration's forward SQL against a
connected database. Irreversible at the database level.

**Rollback** — The act of running a migration's rollback SQL to undo a
completed execution. Only available if rollback SQL was provided at creation.

**Execution Order** — The backend-assigned position of a migration within
its series. Always derived from the linked-list relationship — never set
directly.

**Connected Database** — A database connection registered in the Connections
domain. Migrations execute against a connected database, not against the
application's own database.
```

### 2.11 Changelog

Every update to this document gets a changelog entry. Entries are reverse
chronological — newest first. Because this document describes behavior and
design rather than technical contracts, changelog entries focus on conceptual
changes — a rule that changed, a design decision that was revised, a use case
that was added, a non-goal that was clarified.

```markdown
## Changelog

### 2025-01-20

**Changed**
- Design Decisions: Updated "Linked-list ordering" decision to reflect that
  `order_index` was replaced by predecessor reference. Previous entries
  referencing `order_index` in this document are updated.
- State Machines: `rolled_back` state added to Migration Status. Transition
  from `completed` to `rolled_back` via rollback action documented.

**Impact**
- Any mental model built on migrations having a numeric position field is
  now incorrect. Position is relational, not numeric.
- `rolled_back` is a valid stable state — do not treat it as an error state.

---

### 2025-01-10

**Added**
- Use Cases: "Recovering from a failure" use case added.
- Side Effects: Real-time events (`migration.started`, `migration.completed`,
  `migration.failed`) documented under Side Effects.

**Impact**
- AI agents and frontend implementations should now handle `migration.started`
  as the trigger for optimistic UI updates, not `migration.completed`.
```

---

## Phase 3: Writing Standards

### 3.1 Precision Rules

Every behavioral statement must be unambiguous. Test each statement
against these:

```
Can an AI agent act on this without asking a follow-up question?
  → If no — it is too vague. Rewrite.

Can a human misread this and reach a different conclusion?
  → If yes — it is ambiguous. Rewrite.

Does this statement have exceptions not mentioned here?
  → If yes — state them, or state "always" only when truly always.
```

### 3.2 Language Rules

```
Use "always" only when the statement has zero exceptions.
Use "never" only when the statement has zero exceptions.
Use "must" for hard requirements — violation is a bug or an error.
Use "should" for strong recommendations — violation is a design smell.
Use "may" for optional behaviors — the domain permits but does not require.

Avoid: "typically", "usually", "in most cases", "generally"
  → These hide exceptions. State the exception or remove the hedge.

Avoid: passive voice for behavioral rules
  → "Migrations are ordered by the backend" is weaker than
     "The backend assigns execution order — the frontend never sets it."

Avoid: jargon not defined in the Glossary
  → If a term is precise enough to use, it is precise enough to define.
```

### 3.3 Length Rules

```
Purpose:            3–5 sentences
Core Concepts:      1 short paragraph per concept (3–5 sentences)
Entities:           1 short paragraph per entity + relationships section
Behaviors:          1–4 sentences per rule, as many rules as the domain has
State machine:      Table + diagram + "what the frontend should know" section
Use Cases:          1 short paragraph per use case (3–5 sentences)
Design Decisions:   3-part format (Decision / Why / Tradeoff) per decision
Constraints:        Bullet list — one constraint per bullet, one sentence each
Side Effects:       1–3 sentences per trigger event
Glossary:           One sentence per term — precise, not verbose
```

No section should be longer than it needs to be to be precise.
Padding is not thoroughness. Brevity that loses precision is a bug.
Length that adds precision is correct.

---

## Phase 4: Folder Convention

Domain documents live together. The folder structure for any domain:

```
docs/
  [domain-name]/
    api.md      ← Technical contract (routes, request/response, error codes)
    spec.md     ← This document (behaviors, design, state machines, use cases)
  updates/
    YYYY-MM-DD-[domain-name]-[brief-description].md  ← Change reports
```

When told to write a file, write to the path explicitly given.
When told to update a document, update it in place and add a changelog entry.
When told to document a change, produce a file in `docs/updates/`.

---

## Phase 5: Documentation Quality Checklist

```
Structure
[ ] All applicable sections present in correct order
[ ] Sections with no content are intentionally absent — not overlooked
[ ] Domain folder convention followed (api.md + spec.md together)

Purpose and Concepts
[ ] Purpose answers: what problem, what breaks without it, where it sits
[ ] Every core concept defined precisely enough to act on
[ ] No implementation detail in Purpose or Core Concepts

Entities
[ ] Every domain entity described at the domain level
[ ] Relationships between entities stated explicitly
[ ] No schema or field-level detail

Behaviors
[ ] Every behavioral rule is a declarative statement — no hedging
[ ] "Always" and "never" used only when truly absolute
[ ] No vague qualifiers (typically, usually, in most cases)

State Machines
[ ] Every stateful entity has a state machine section
[ ] Every state defined with its meaning
[ ] Every transition documented with its trigger
[ ] Terminal states identified (or explicitly noted as absent)
[ ] "What the frontend should know" section present

Use Cases
[ ] Each use case describes a real goal and how the domain fulfills it
[ ] No routes or field names in use cases
[ ] Covers the primary ways the domain will actually be used

Design Decisions
[ ] Every non-obvious design choice has a decision entry
[ ] Every entry has: Decision, Why, Tradeoff
[ ] Tradeoffs are honest — not minimized

Constraints and Non-Goals
[ ] Hard invariants listed under Constraints
[ ] What the domain does not do is explicit under Non-Goals
[ ] Non-goals prevent scope creep and incorrect assumptions

Side Effects
[ ] Every significant action in the domain has a side effects entry
[ ] Side effects reference other domains by name — not by implementation
[ ] Real-time events documented as side effects where applicable

Glossary
[ ] Every domain-specific term used in the document is in the Glossary
[ ] Every definition is one sentence — precise, not verbose

Changelog
[ ] Every update has a dated entry
[ ] Entries describe conceptual changes — not code changes
[ ] Impact section present — what mental models need updating
[ ] Entries in reverse chronological order
```

---

## Reference Files

`fastapi-api-documentation/SKILL.md` — The technical contract companion.
The spec document explains why the domain works the way it does.
The API document explains what the domain exposes and expects.
They are written together, live together, and are read together.

`references/principles.md` — The laws that govern domain design decisions.
When a design decision references a physical or mathematical principle,
trace it back here.
