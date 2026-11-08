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
   - Modifies domain routes/schemas → Must update API/MCP contracts and verify Pydantic models.
   - Modifies Verifalia integration / upstream calls → Must enforce bounded `waitTime=30000`, safe deduplication, and max 25 email boundary.
   - Modifies Redis caching / quota tracking → Must maintain midnight-UTC TTL alignment and fail-open resilience.

---

### 2. The Decision Order

When evaluating trade-offs, adhere strictly to the **muscar_mail Decision Order** ([`principles.md`](.agents/references/principles.md)):

1. **Protect quota correctness and external credit safety first**:
   * Enforce ≤25 emails before any outbound network call.
   * Apply `Safe` batch deduplication so repeated emails within a batch consume only 1 credit.
   * Check Redis cache to serve identical batches at 0 credit cost.
2. **Protect statelessness and serverless contract integrity second**:
   * Never introduce stateful in-memory sessions, persistent connection locks, or SSE dependencies that break when Render sleeps.
   * Every request must be independently processable.
3. **Protect token efficiency and agent usability third**:
   * Distill Verifalia's verbose DNS, MX, and SMTP logs into a compact, high-signal JSON summary (`email`, `classification`, `status`, `is_deliverable`, `is_disposable`, `is_role_account`, `is_free_email`).
4. **Protect reliability and operability fourth**:
   * Deterministic JSON-RPC 2.0 error contracts.
   * Constant-time comparison for API keys (`secrets.compare_digest`).
   * Bounded external timeouts (`waitTime=30000` ceiling).
   * Structured JSON logging via `structlog`; telemetry via `sentry-sdk`.
5. **Optimize latency and cost fifth**:
   * Multiplexed HTTP/2 calls via `httpx2`.
   * Atomic Redis counters with midnight UTC TTL.
6. **Optimize local developer convenience last**:
   * No speculative code, no premature abstractions, no unneeded frameworks.

---

### 3. Algorithmic & Systems Design Evaluation

Evaluate code changes against standard engineering and algorithmic design principles:
- **Asymptotic Complexity & Scaling** (`principles.md` §11, §12): Watch for nested loops causing $O(n^2)$ scans or unindexed lookups.
- **Fail Fast & Input Validation** (`principles.md` §52): Reject invalid payloads (batches > 25 emails, invalid email strings) at the Pydantic schema/route boundary before calling upstream APIs.
- **Deduplication & Set Operations** (`principles.md` §1): Leverage `Safe` deduplication and canonical lowercase email set operations to conserve credits.
- **Idempotency** (`principles.md` §24): Ensure retries of batch verification produce identical, safe outcomes via deterministic batch hashing (`cache:batch:<sha256>`).
- **Bulkheading & Isolation** (`principles.md` §2, §59): Upstream verification provider integrations (Verifalia) must remain isolated behind adapters in `domains/verification/service.py`. Core schemas and MCP handlers never import provider SDKs or speak raw provider schemas directly.

---

### 4. The Exemption Matrix (Checking Before Flagging)

Before reporting a bug or design flaw, check whether an intentional architectural **exemption** applies. Do not flag valid exemptions as violations:

| Rule / Principle | When it is EXEMPT (Do NOT flag) | Rationale |
| :--- | :--- | :--- |
| **Indexing / Hash Maps ($O(1)$)** | Small email batch lists ($N \le 25$) using simple set or linear operations ($O(n)$). | Linear scans on small slices have contiguous memory locality, lower constant overhead, and zero hashing penalty. |
| **Async Network Dispatch** | Healthcheck endpoint (`GET /health`) must remain zero-network and instantaneous (<5ms). | Health probes must never be blocked by external provider timeouts or downstream network calls. |
| **DRY / Deduplication** | Upstream provider adapter isolation. | Upstream mapping logic stays encapsulated in the adapter rather than leaked into shared cross-domain utilities. |
| **Fail-Open Resilience** | Redis cache operations (batch retrieval or quota tracking). | Redis is strictly an optional, fail-open cache. Redis connection failures must log warnings and continue verification without crashing the service. |
| **Elegance / DRY Abstractions** | Explicit, repetitive JSON-RPC 2.0 error mapping (-32700, -32600, -32601, -32602, -32603) and Pydantic field validators. | Legibility, strict protocol compliance, and explicit audit trails take precedence over terse abstractions. |
| **Precomputation / Dynamic TTL** | Daily quota key expiration (`quota:daily:YYYY-MM-DD`). | Cannot use hardcoded 24h TTL; must be resolved dynamically against Verifalia's `freeCreditsResetOn` (00:00:00 UTC). |

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
     Principle/Constraint: [Exact principle or rule name, e.g. "principles.md §4 (Max 25 emails per batch)"]
     Scenario: [Exact condition, input, or environment where this fails or breaks]
     Problem: [One sentence explaining the defect]
     Fix: [One sentence concrete code change to resolve it]
     Touches: [file:line_range]

[2]. [ACTION VERB] ...

---

## Verification Tasks ([V])
(Confirm fixes were applied correctly by code tracing or inspection.)

[N+1]. Verify [fix] by tracing [call path / logic flow] in [file:function]
       Check: [Exact condition to confirm, e.g., assert 422 returned on batch size > 25]
       Method: [Code inspection / AST trace]

---

## Validation Tasks ([T])
(Prove the fix holds under real execution — tests, dry-runs, linter.)

[N+V+1]. [Run / Assert / Execute] [command or test scenario]
         Command: [e.g. `pytest tests/test_verification.py -k test_batch_limit_exceeded`]
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
