---
name: plan-creator
description: >
  Generate precise, rigorous, production-grade engineering plans. Supports two
  distinct modalities: (1) BUILD PLANS (greenfield systems or new capabilities from
  conception to production readiness, driven by system invariants, state machines,
  failure topologies, and capability milestones) and (2) FIX PLANS (atomic, actionable
  remediation task lists derived from audits, code reviews, or defect lists, enforcing
  the N problems -> N+2 tasks contract). Use whenever the user asks to plan, design,
  generate tasks, build a roadmap, or turn issues into actionable work.
---

# Plan Creator Skill: Build vs. Fix

An engineering plan is never a file tree or a naive list of filenames to create.
This skill operates in two distinct, unambiguous modes:
1. **THE BUILD PLAN**: Designing and executing a capability, system, or service from conception to production readiness.
2. **THE FIX PLAN**: Translating identified bugs, security audit findings, or architectural defects into atomic remediation tasks.

---

# PART I: THE BUILD PLAN (Greenfield & Subsystems)

When designing a new service, capability, or domain from scratch, the plan must answer:
*What must never happen? How does state transition? How does it survive failure?*

## 1. Prime Invariants & Guarantees ("Must-Never-Happen" Scenarios)

The foundation of every sound engineering plan rests on identifying and documenting crucial system invariants. Initial focus is **always** on defining the "must-never-happen" scenarios. This establishes the boundaries that maintain data integrity and operational stability.

Every Build Plan must open with an Invariant Table addressing:
- **Resource & Quota Limits**: e.g., exceeding daily credit limits or rate boundaries.
- **Boot & Availability**: e.g., unhandled server errors or crash-loops on cold startup.
- **Credential Hygiene**: e.g., plaintext credential leaks in logs, telemetry, or error traces.
- **Execution Ceilings**: e.g., unbounded agent lifespans, infinite polling, or hanging sockets.
- **State Loss**: e.g., credit or data loss during network interruptions or dropped client connections.

```markdown
### Prime Invariants (The Non-Negotiables)
| Invariant | Guarantee | Enforcement Mechanism | Failure Consequence |
|---|---|---|---|
| Quota Ceiling | Never exceed N units/day | Boundary check + atomic counter | Block outbound calls |
| Zero Loss on Drop | Disconnected clients can recover results | Idempotent canonical cache | Return cached at 0 cost |
```

---

## 2. End-to-End Request Flow & State Machines

A Build Plan must trace the complete request lifecycle across all boundaries:
1. **Ingress Authentication**: Constant-time key comparison, token parsing, and role verification.
2. **Validation & Canonicalization**: Input sanitization, length boundaries, sorting, and deduplication.
3. **Quota & Rate Management**: Local counter verification, atomic claims, and credit availability checks before making external calls.
4. **Upstream Communication & Orchestration**: Protocol handling (e.g. HTTP/2, synchronous wait parameters, timeout ceilings, and bounded retry ladders).
5. **Response Distillation**: Stripping raw upstream blobs into compact, high-signal models tailored for downstream consumers / LLM agent context windows.
6. **Cache & State Persistence**: Writing results to cache/storage with exact TTL calculations (e.g. midnight-UTC synchronization).
7. **Egress Envelope Construction**: Shaping standardized responses or JSON-RPC 2.0 envelopes with strict status mapping.

Include a directed Mermaid flowchart documenting all state transitions, branch conditions, and terminal states.

---

## 3. Failure Modes & Mitigations Matrix

Failure is not an afterthought; it dictates the architecture. Every Build Plan must explicitly map potential failure scenarios and their technical mitigations:

| Failure Scenario | Hazard | Technical Mitigation | Fallback Behavior |
|---|---|---|---|
| **Client Disconnection** | Agent drops mid-flight; expensive credits/compute spent | Hash input payload (SHA-256); complete execution in background; persist in cache | Client retries payload; cache hit returns result at 0 cost |
| **Upstream Latency / Hang** | Upstream provider stalls | Strict socket & connection timeout budgets | Bounded polling ladder (e.g. max 3 attempts) or clean 504 Gateway Timeout |
| **Storage / Cache Down** | Redis or cache provider unavailable | Fail-open resilience pattern | Log warning; bypass cache; proceed directly to upstream |
| **Quota Depleted** | Free or paid tier exhausted | Catch upstream 402 / quota responses; lock local counter | Surface clean agent explanation with reset countdown |
| **Cold Starts (<2s budget)** | Container sleeping on serverless/free tier | Zero synchronous blocking I/O during boot; lazy connection pools | Instantaneous `/health` response (<1ms) |

---

## 4. Hard Technical Decisions & Upstream Quirks

Document the deliberate architectural choices and upstream provider peculiarities:
- **Upstream Quirks**: Idiosyncrasies of third-party APIs (e.g. `waitTime` parameters, HTTP 202 vs 200, GMT/UTC midnight reset times, non-standard error codes).
- **Security Boundaries**: Constant-time comparison (`secrets.compare_digest`), secrets handling, transport encryption.
- **Resource Management Under Load**: Connection pool limits, concurrency controls, backpressure, and memory bounds.

---

## 5. Capability Milestones (Not File Lists!)

Break the build into capability-driven milestones. Each milestone represents a functioning, verifiable slice of capability:
- **Milestone 1: Invariant Gates, Auth & Observability** (Security boundary, settings, structured logging, telemetry)
- **Milestone 2: Upstream Adapter & Domain Engine** (Provider client, protocol negotiation, response distillation)
- **Milestone 3: Quota Guard & Recovery Layer** (Caching, deduplication, atomic counters, fail-open resilience)
- **Milestone 4: Protocol & API Surfaces** (Stateless MCP engine, REST routes, tool schemas)
- **Milestone 5: Production Hardening & Chaos Verification** (Edge-case tests, failure injection, documentation)

Each milestone must specify:
- **Goal**: What capability is unlocked.
- **Deliverables**: Concrete components built.
- **Acceptance Criteria**: Verifiable checks that prove the milestone is complete.

---

# PART II: THE FIX PLAN (Audit & Remediation)

When remediating a set of identified problems from a code review or audit, follow the atomic contract:

## The Core Contract: N Problems → At Least N+2 Tasks

Given N problems:
- **N tasks** — one per problem, each naming exactly what to do and where.
- **+1 or more** — verification tasks (confirm the fixes work correctly via code-level inspection).
- **+1 or more** — validation tasks (prove the fixes hold under real or simulated execution).

### Dependency Ordering
1. Schema / model changes first (downstream layers depend on these).
2. Database / migration changes second.
3. Service logic third.
4. Router / API contract changes fourth.
5. Auth / security fixes (flagged clearly).
6. Comment / docstring corrections last.

### Task Format
```markdown
[N]. [ACTION VERB] [specific thing] in [specific file or function]
     Problem: [one sentence — what is wrong]
     Fix: [one sentence — what change resolves it]
     Touches: [file(s) or function(s)]
```

### Action Verb Rules
Never use "Fix", "Update", "Improve", or "Handle" alone.
Use concrete verbs:
- `Add`, `Remove`, `Replace`, `Rename`, `Move`, `Extract`
- `Enforce`, `Validate`, `Reject`, `Guard`, `Restrict`, `Limit`
- `Wrap`, `Unwrap`, `Flatten`, `Normalize`, `Default`
- `Raise`, `Catch`, `Propagate`, `Suppress`

---

# PART III: SUMMARY DECISION MATRIX

| Dimension | The Build Plan | The Fix Plan |
|---|---|---|
| **Trigger** | "Build this system", "Design this capability", "Plan from scratch to production" | "Fix these issues", "Turn audit into tasks", "I have N problems" |
| **Starting Point** | Invariants ("Must-Never-Happen") & State Machines | List of identified flaws or audit findings |
| **Core Structure** | Flowcharts, Invariants, Failure Topologies, Capability Milestones | Atomic numbered task list (N fixes + V verifications + T validations) |
| **Antipattern** | Dumping a directory file list without explaining state or failure | Grouping multiple bugs into vague "refactor" tasks |
| **Output Goal** | Production-ready, resilient architecture | Zero-regression remediation |
