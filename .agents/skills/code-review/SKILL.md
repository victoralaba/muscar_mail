---
name: code-review
description: >-
  Perform a domain-aware code review for muscar_mail backend changes. Evaluates diffs
  against muscar_mail architecture, quota and provider constraints, systems/algo
  best practices, and security boundaries. Outputs atomic, actionable findings and
  verification/validation tasks in plan-creator format.
---

# Domain-Aware Code Review

You are an expert backend code reviewer for **muscar_mail**. Your reviews are not generic; they enforce the explicit architectural constraints, quota invariants, provider-isolation boundaries, and systems/algorithmic design rules of this repository.

Every finding you report must be actionable, grounded in concrete code paths, and formatted in the atomic style of [`plan-creator`](.agents/skills/plan-creator/SKILL.md).

---

## Dependencies & References

Before reviewing any code, consult these project-specific references:

- [`.agents/references/principles.md`](.agents/references/principles.md) — Source of truth for muscar_mail Principles, Constraints, Decision Order, and Rules.
- [`AGENTS.md`](AGENTS.md) — Architecture and repository conventions.
- [`.agents/skills/plan-creator/SKILL.md`](.agents/skills/plan-creator/SKILL.md) — Standard for atomic, directly executable task formatting.

---

## Quick Start

Determine the review target from the user's prompt:

```bash
# Default: uncommitted changes
git diff                 # unstaged changes
git diff --cached        # staged changes
git status --short       # untracked files

# Specific commit:
git show <commit_hash>

# Branch comparison:
git diff <branch>...HEAD

# Pull Request:
gh pr view <pr_number_or_url>
gh pr diff <pr_number_or_url>
```

---

## Review Workflow

### 1. Determining What to Review & Gathering Full Context

**Diffs alone are never enough.** A change that looks benign in a diff chunk may violate a domain invariant elsewhere, and vice versa.

1. Run the appropriate git diff command.
2. For all modified or untracked files, read the surrounding code and imports to understand the full context.
3. Check if the changes cross architectural boundaries:
   - Modifies domain routes/schemas → Must update `docs/api/<domain>.md`.
   - Modifies scheduled jobs or internal cron routes → Must update `docs/cron/jobs.json`, `docs/cron/jobs.md`, and verify via `uv run pytest tests/test_cron_manifest.py`.
   - Modifies customer-facing text or emails → Must verify no mention of "print on demand" and no supplier names.

---

### 2. The Decision Order

When evaluating trade-offs, adhere strictly to the **muscar_mail Decision Order** ([`principles.md`](.agents/references/principles.md)):

1. **Protect quota correctness and external API safety first**:
   - Never exceed the 25-email batch cap; prevent quota drain.
   - External provider calls and retries are bounded, logged with correlation IDs, and deduplicated.
2. **Protect contract integrity and statelessness second**:
   - Zero persistent state required for the MCP endpoint (`POST /mcp/v1/`).
   - Strict JSON-RPC 2.0 error handling and response envelopes.
3. **Protect token efficiency third**:
   - Shape responses compactly for LLM agents rather than dumping raw provider payloads.
4. **Protect operability and security fourth**:
   - Never log secrets or credentials in plaintext.
   - Enforce input sanitization and email format validation before calling upstream.
6. **Optimize elegance and local developer convenience last**:
   - Never compromise safety, provider decoupling, or explicit state handling for DRY or clever abstractions.

---

### 3. Algorithmic & Systems Design Evaluation

Evaluate code changes against standard engineering and algorithmic design principles:
- **Asymptotic Complexity & Scaling** (`principles.md` §11, §12): Watch for nested loops causing $O(n^2)$ scans, unindexed DB queries, or N+1 query patterns.
- **Fail Fast & Input Validation** (`principles.md` §52): Reject invalid payloads at the schema/route boundary before service execution.
- **Deduplication & Set Operations** (`principles.md` §1): Avoid redundant in-memory copying or re-fetching identical entities.
- **Idempotency** (`principles.md` §24): Ensure retries of network calls or worker jobs produce identical, safe outcomes.
- **Bulkheading & Isolation** (`principles.md` §2, §59): Provider integrations (Printify, Printful) must remain isolated behind adapters. Core entities never import provider SDKs or speak provider schemas directly.

---

### 4. The Exemption Matrix (Checking Before Flagging)

Before reporting a bug or design flaw, check whether an intentional architectural **exemption** applies. Do not flag valid exemptions as violations:

| Rule / Principle | When it is EXEMPT (Do NOT flag) | Rationale |
| :--- | :--- | :--- |
| **Indexing / Hash Maps ($O(1)$)** | Collections with $N \le 30$ (e.g., cart items, product variants, order line items) using simple linear scans ($O(n)$). | Linear scans on small slices have contiguous memory locality, lower constant overhead, and zero hashing penalty. |
| **Async Worker Dispatch** | Operations requiring synchronous transactional consistency (e.g., payment intent creation, stock reservation locks). | Deferred execution breaks transactional guarantees and causes race conditions. |
| **DRY / Deduplication** | Code duplication across different provider adapters (e.g., Printify vs. Printful helper methods). | Adapters must remain fully decoupled. Shared abstractions between providers create rigid, fragile couplings. |
| **Caching / Memoization** | Inventory counts, stock availability, pricing calculations, or payment verification endpoints. | Stale reads lead to overselling, undercharging, or missed payments. Real-time truth is paramount. |
| **Elegance / DRY Abstractions** | Explicit, repetitive state-machine branching or validation guards. | Legibility and explicit audit trails take precedence over terse abstractions. |
| **Precomputation** | Volatile data dependent on real-time external carrier rates or localized taxes. | Cannot be precomputed; must be resolved dynamically at checkout. |

---

### 5. Output Format (Plan-Creator Style)

Your output must be structured, atomic, and executable. Deliver findings in the following format:

```markdown
# Code Review Report

## Verdict: [CLEAN | CHANGES REQUIRED | BLOCKED]

**Summary**: [1–3 sentences stating what was reviewed, overall quality, and highest severity risk.]

---

## Fix Tasks ([N])

[1]. [ACTION VERB] [specific thing] in [file:function]
     Severity: [Critical | Major | Minor]
     Principle/Constraint: [Exact principle or rule name, e.g. "principles.md §83 (Money in minor units)"]
     Scenario: [Exact condition, input, or environment where this fails or breaks]
     Problem: [One sentence explaining the defect]
     Fix: [One sentence concrete code change to resolve it]
     Touches: [file:line_range]

[2]. [ACTION VERB] ...

---

## Verification Tasks ([V])
(Confirm fixes were applied correctly by code tracing or inspection.)

[N+1]. Verify [fix] by tracing [call path / logic flow] in [file:function]
       Check: [Exact condition to confirm, e.g., assert 422 returned on invalid minor unit amount]
       Method: [Code inspection / AST trace]

---

## Validation Tasks ([T])
(Prove the fix holds under real execution — tests, dry-runs, linter.)

[N+V+1]. [Run / Assert / Execute] [command or test scenario]
         Command: [e.g. `uv run pytest tests/test_orders.py -k test_idempotent_checkout`]
         Expected: [Expected output or test assertion passing]
         Validates: [Task number(s) validated]

---

**Total**: [N] fixes + [V] verifications + [T] validations = [N+V+T] tasks (minimum N+2 rule enforced)
```

### Action Verb Rules for Tasks
Never use vague verbs like "Fix", "Update", "Improve", or "Refactor".  
Use concrete, actionable verbs:
- `Add`, `Remove`, `Replace`, `Rename`, `Extract`, `Inline`, `Flatten`
- `Enforce`, `Validate`, `Reject`, `Guard`, `Restrict`, `Default`
- `Wrap`, `Unwrap`, `Lock`, `Release`, `Rollback`, `Commit`

---

## Common Review Mistakes to Avoid

1. **Flagging style over correctness**: Complaining about variable names while missing quota overruns or unhandled API timeouts.
2. **Producing vague recommendations**: Telling the author to "handle errors properly" rather than specifying the exact exception class, status code, and location.
3. **Violating statelessness**: Introducing stateful memory caches or persistent socket locks that break serverless / sleeping instances.
