# Governing Principles

> muscar_mail: custom, zero-dependency, stateless Model Context Protocol (MCP) engine and FastAPI service for email verification using Verifalia API.
> Core domains: email validation (deliverability, risk, disposable & role detection), MCP server engine (stateless JSON-RPC 2.0 at `POST /mcp/v1/`), quota & credit management (free tier 25-email batch cap), and provider adapter.
> Built for Python 3.14 and designed for serverless / Render free-tier deployment. This file constrains every backend decision.

---

## muscar_mail First Principles

### 1. Stateless and Serverless by Design
The engine must have zero persistent session state. Every MCP invocation (`POST /mcp/v1/`) and REST request must be completely self-contained. Render free-tier instances sleep after inactivity and wake on demand; the application must never rely on persistent in-memory session caches, stateful WebSockets, or background connection pools that prevent clean sleep/wake cycles.

### 2. Zero-Dependency Protocol Core
Model Context Protocol integration must not pull in heavy external SDKs or complex session middleware. MCP over HTTP is pure JSON-RPC 2.0. The protocol engine is implemented with native FastAPI and Pydantic models, eliminating framework bloat.

### 3. Providers Are Adapters, Never the Core Domain
Verifalia is an upstream verification provider, not the domain interface. Internal schemas and AI-agent facing contracts speak `muscar_mail` language. Upstream API endpoints, authentication headers, raw parameter naming, and quirks live strictly in the adapter layer. Swapping or adding an email verification provider must never break client or MCP contracts.

### 4. Strict Quota and Batch Guardrails (≤25 Emails)
The Verifalia free tier grants 25 daily verification credits. The service strictly enforces a maximum of 25 emails per batch request. Any request attempting to verify more than 25 emails is rejected immediately at the Pydantic validation boundary with HTTP 422 before any outbound network call is made.

### 5. Immediate Synchronous Resolution (`waitTime`)
Small batches (1–25 emails) must be resolved within the initial HTTP request. We leverage Verifalia's synchronous waiting capabilities (`?waitTime=30000`) on `POST /v2.4/email-validations` so that AI agents and clients receive complete deliverability outcomes in seconds without the complexity of polling loops.

### 6. Token Efficiency for LLM Agents
Verifalia's raw response contains deeply nested DNS records, SMTP transaction logs, and syntax breakdown metadata. When serving AI agents over MCP, the output is distilled into a compact, high-signal JSON schema (`email`, `classification`, `status`, `is_deliverable`, `is_disposable`, `is_role_account`, `is_free_email`) to conserve context tokens.

### 7. Deterministic Core, Flexible Interfaces
The same email address evaluated under the same provider conditions produces the exact same result regardless of whether called via REST (`/api/v1/verify`) or MCP (`POST /mcp/v1/`). Business rules and validation thresholds are unified in the service layer.

### 8. Defaults That Prevent Footguns
System defaults bias toward safety, credit preservation, and least surprise. Default to `Safe` deduplication (so duplicate emails in a batch consume only 1 credit), explicit error messaging, strict validation, and zero accidental credit leakage.

### 9. Secure and Fail-Closed Credentials Management
Credentials (`VERIFALIA_USERNAME`, `VERIFALIA_PASSWORD`) are loaded strictly from environment variables. Plaintext credentials must never be committed, logged, or surfaced in error traces. Missing or invalid credentials fail immediately and closed.

### 10. Instrumentation and Observable State
Observability, execution timings, provider HTTP status codes, and batch metrics are first-class outputs. Logs capture diagnostic context without ever leaking confidential payloads or authentication tokens.

---

## muscar_mail Constraints

There is no robust verification system without constraints. Constraints are deliberate calculations that protect credit quotas, serverless reliability, contract integrity, and agent usability.

### Email validation and batching constraints

- Maximum 25 emails per batch: batches with 0 or >25 emails are rejected at input validation.
- Input sanitization: email strings are trimmed of whitespace and filtered for emptiness prior to validation.
- Safe deduplication: duplicate emails within the same batch are deduplicated for billing purposes (`Safe` deduplication).
- Quality default: validation quality defaults to `Standard` (1 credit per unique email).

### MCP engine and stateless protocol constraints

- Protocol path is strictly `POST /mcp/v1/` (with trailing slash redirect/alias at `/mcp/v1`).
- Implements the Model Context Protocol over HTTP via standard JSON-RPC 2.0 (`jsonrpc: "2.0"`, `id`, `method`, `params`).
- Methods supported: `initialize`, `notifications/initialized`, `ping`, `tools/list`, and `tools/call`.
- Standard JSON-RPC error codes are enforced (-32700 for parse error, -32600 for invalid request, -32601 for method not found, -32602 for invalid params, -32603 for internal error).
- Zero in-memory session tracking: no session IDs or cookies required; every request is independently executable.
- Tool responses strictly adhere to MCP content schema: `content: [{"type": "text", "text": "..."}]`, `isError: bool`.

### Upstream Verifalia provider constraints

- Upstream communication is strictly isolated in `app/services/verifalia.py`.
- Requests pass `?waitTime=30000` to allow Verifalia to return completed results synchronously in HTTP 200.
- Bounded polling fallback: if Verifalia returns HTTP 202 Accepted, the service polls `GET /v2.4/email-validations/{id}?waitTime=5000` up to a strict ceiling of 3 attempts before returning a 504 Gateway Timeout. Unbounded polling is prohibited.
- Credit monitoring: remaining daily free credits and reset timestamps are queryable via `GET /v2.4/credits/balance` through tool `get_credit_balance`.

### Error handling and quota protection constraints

- HTTP 402 (Payment Required) from Verifalia indicates exhausted daily credits; it is explicitly mapped to `InsufficientCreditsError` with clear quota guidance.
- HTTP 401 (Unauthorized) is mapped to `AuthenticationError` without leaking credentials.
- HTTP 429 (Too Many Requests) is surfaced cleanly to prevent cascading retries.
- Upstream network errors (DNS resolution, timeout) are mapped to 503 Service Unavailable or 504 Gateway Timeout.

### Runtime and deployment constraints

- Python 3.14 target: code must be fully compatible with Python 3.14 syntax, typing, and standard library behaviors.
- Fast cold starts: initialization must take < 2 seconds to support sleeping serverless containers.
- Dedicated healthcheck: `GET /health` must return `200 OK` instantaneously without upstream network calls.

### Testing and contract constraints

- Route and MCP contracts are enforced with automated tests covering initialization, tool listing, tool invocation, batch boundaries (>25 emails), auth failures, and credit exhaustion.
- Tests must execute cleanly in Python 3.14 without relying on deprecated loop management.

---

## Decision Order

When trade-offs conflict, muscar_mail decisions are made in this strict order:

1. **Protect quota correctness and external credit safety first.**
   - Never allow batch overruns (> 25 emails) or duplicate validations that deplete free tier credits.
   - Enforce batch validation boundaries before making outbound network requests.

2. **Protect statelessness and serverless contract integrity second.**
   - Never introduce stateful in-memory sessions, persistent connection locks, or SSE dependencies that break on Render free-tier sleep cycles.
   - Every request must be independently processable.

3. **Protect token efficiency and agent usability third.**
   - Shape responses compactly for LLM context windows rather than dumping raw provider payloads.

4. **Protect reliability and operability fourth.**
   - Deterministic error contracts, bounded timeouts (waitTime ceiling), clear failure messages, and correlation logging without leaking secrets.

5. **Optimize latency and cost fifth.**
   - Deduplication, efficient JSON serialization, and optimal connection pooling.

6. **Optimize local developer convenience last.**
   - Internal neatness never supersedes statelessness or quota guarantees.

Tie-breaker rule: when two options appear equivalent, choose the option that reduces irreversible risk (e.g. quota consumption) and increases inspectability of system behavior.

---

## Mathematical Rules

### 1. Deduplication (Set Theory)

Never store or process the same piece of data twice. If something already exists, reference it — don't copy it. Duplicates waste memory and processing time.

### 2. Lazy Evaluation (Deferred Computation)

Don't calculate something until you actually need the result. Doing work upfront that might never be used is pure waste.

### 3. Memoization (Caching Known Results)

If you've already solved a problem once, remember the answer. Never solve the same problem twice — look it up instead.

### 4. Divide and Conquer

Break large problems into smaller independent pieces and solve each piece separately. Smaller problems are faster to solve and easier to parallelize.

### 5. Amortization (Spreading Cost)

Spread expensive operations over time instead of doing them all at once. A little cost paid regularly is better than one massive cost paid suddenly.

### 6. Approximation (Good Enough is Often Perfect)

You don't always need the exact answer. A result that is 99% accurate but 10x faster is often the better engineering choice.

### 7. Compression (Information Density)

Represent the same information using fewer bits. Less data to move means faster transmission and lower memory usage.

### 8. Elimination of Redundancy

Any step in a process that doesn't change the output should be removed. Every unnecessary instruction is time stolen from the user.

### 9. Indexing (Pre-organized Lookup)

Organize your data in advance so that finding things later is instant. Searching through everything every time is exponentially expensive.

### 10. Locality of Reference

Keep data that is used together stored together. Accessing nearby memory is dramatically faster than jumping around randomly.

### 11. Asymptotic Complexity (Big-O Thinking)

The way your algorithm scales matters more than how fast it runs today. An algorithm that gets exponentially slower as data grows will eventually destroy performance no matter how fast the hardware is.

### 12. Logarithmic Reduction

Instead of checking every item one by one, structure your search so that each step cuts the remaining work in half. Doubling your data should add only one extra step, not double the work.

### 13. Sparse Representation

If most of your data is empty or zero, don't store the empty parts. Only store what actually has a value and reconstruct the rest on demand.

### 14. Probability and Sampling

You often don't need to analyze all the data — a well-chosen sample gives you the same answer. Bloom filters, HyperLogLog, and probabilistic counters are built on this idea.

### 15. Modular Arithmetic (Hashing)

Map large, complex keys to small fixed-size buckets using a formula. This turns expensive searches into instant direct lookups.

### 16. Graph Shortest Path

When navigating dependencies, execution order, or network hops, always find the minimum-cost route. Traversing unnecessary nodes wastes time.

### 17. Matrix Sparsity

When representing relationships between many things, most pairs have no relationship. Store only the connections that exist, not all the ones that don't.

### 18. Fixed-Point Convergence

Instead of recalculating something from scratch every time, start from the last known result and iterate toward the answer. Convergence is almost always faster than starting over.

### 19. Normalization

Store each fact in exactly one place. If a piece of data lives in five places and one changes, you now have four lies in your system. One source of truth always wins.

### 20. Order of Operations

The sequence in which you perform steps drastically affects performance. Filter before sorting, sort before joining, and join before aggregating — always reduce the dataset as early as possible.

### 21. Symmetry Breaking

When two paths are equivalent, pick one rule and always follow it. Indecision and branching at runtime wastes cycles. Conventions eliminate choices.

### 22. Dimensional Reduction

If you can solve a problem in fewer dimensions without losing meaningful information, do it. Strip every axis of complexity that doesn't affect the answer.

### 23. Monotonic Functions

Design systems where things only move in one direction — version numbers only go up, logs only append, states only forward. Reversibility is expensive.

### 24. Idempotency

Performing the same operation twice should produce the same result as doing it once. This makes retries safe, caching trivial, and systems predictable.

### 25. Invariant Preservation

Define rules that must always be true and enforce them at the boundary, not scattered throughout the code. Checking invariants deep inside logic multiplies cost.

---

## Physics-Inspired Rules

### 26. Conservation of Energy (Do Less Work)

Every operation costs energy — CPU cycles, memory reads, network bytes. Treat computation like a limited resource and spend it wisely.

### 27. Least Action Principle

Nature always takes the path requiring the least effort. Your code should too — always find the shortest logical path to the result.

### 28. Entropy (Disorder Costs)

Disorganized systems degrade over time and become expensive to operate. Structured, clean data and code stays fast longer.

### 29. Parallelism (Force Multiplication)

Just as physical forces can act simultaneously, independent tasks should run at the same time, not one after another.

### 30. Pipeline Principle (Assembly Line)

While one task is being processed, the next one should already be loading. Never let a worker sit idle waiting for the previous step to finish.

### 31. Resonance / Batching

Group similar operations together and execute them at the same time. Context-switching between different types of work is expensive — batch work by type.

### 32. Thermal Throttling (Avoid Overload)

A system pushed past its limits slows everything down to protect itself. Design so that peak load never saturates the system — leave headroom.

### 33. Signal-to-Noise Ratio

Only transmit and process what is meaningful. Every byte of irrelevant data you send or store dilutes performance and wastes capacity.

### 34. Impedance Matching (Eliminate Bottlenecks)

A system is only as fast as its slowest part. Find the constraint — the narrowest pipe — and widen it before optimizing anything else.

### 35. Gravity (Pull, Don't Push)

Bring computation close to the data, not the other way around. Moving large data across a network is expensive — move the logic instead.

### 36. Newton's First Law (Inertia)

A system at rest tends to stay at rest. Don't wake up processes, threads, or services unless there is actual work to do. Idle spinning wastes everything.

### 37. Newton's Third Law (Every Action Has a Reaction)

Every network call, every lock, every write has a cost that comes back to you. Design with the assumption that every action will have a measurable counter-effect.

### 38. Pressure Equalization

Work should flow toward where there is capacity, not pile up behind a single point. Load balancing is just pressure seeking equilibrium.

### 39. Capacitance (Buffering)

Absorb sudden bursts by storing them temporarily instead of processing them instantly. Queues and buffers are the electrical capacitors of software.

### 40. Resistance (Latency Is Friction)

Every layer you add — a proxy, a wrapper, a middleware — adds resistance. Each one slows the signal down. Only add layers that earn their cost.

### 41. Superposition (Concurrent Non-Interference)

Independent operations should be able to run simultaneously without affecting each other. Shared mutable state is what prevents superposition and destroys concurrency.

### 42. Wave Interference (Avoiding Thundering Herd)

When many things are synchronized to wake up at the same moment, they collide and destroy performance. Introduce random jitter to desynchronize them.

### 43. Diffusion (Data Locality Over Time)

Frequently accessed data naturally migrates toward faster storage layers — CPU cache, RAM, SSD. Design your access patterns to work with this, not against it.

### 44. Half-Life (Data Expiry)

Not all data stays relevant forever. Stale data that is never evicted wastes space and eventually serves wrong answers. Everything cached should have a decay rule.

### 45. Phase Transitions (Know Your Thresholds)

Systems don't degrade gradually — they collapse suddenly at a threshold, just like water turning to ice. Know your limits before you hit them, not after.

### 46. Bernoulli's Principle (Fast Paths Stay Open)

The more you narrow a pipeline for critical fast paths, the more pressure builds. Keep your hot paths wide, clean, and unobstructed by secondary logic.

### 47. Refraction (Context Switching)

When a signal crosses boundaries — threads, processes, machines — it bends and slows. Minimize the number of context switches your hot path crosses.

### 48. Quantum Tunneling (Zero-Copy)

The fastest way to move data is to not move it at all. Pass a pointer, a reference, a handle. Let the reader come to the data instead of shipping the data to the reader.

### 49. Doppler Effect (Backpressure)

If a consumer is slower than a producer, the gap grows. The system must signal the producer to slow down before the buffer overflows. Backpressure is how fast systems stay stable.

### 50. Second Law of Thermodynamics (Complexity Only Grows)

Left unattended, systems become more complex, slower, and more disordered over time. Performance must be actively maintained — it does not preserve itself.

---

## Systems & Architecture Rules

### 51. Separation of Concerns

Fast paths and slow paths should never share the same code, thread, or process. Mixing them forces the fast path to inherit the cost of the slow one.

### 52. Fail Fast

Detect and reject bad input at the earliest possible moment. The deeper an error travels into a system before being caught, the more work gets thrown away.

### 53. Precomputation

Anything that can be calculated at build time or startup should never be calculated at runtime. Move work left in time whenever possible.

### 54. Pull Over Push

Let consumers request data when they are ready rather than having producers force it on them. Push overwhelms slow consumers; pull naturally regulates flow.

### 55. Immutability

Data that cannot change can be safely shared, cached, and parallelized without locks. Mutability is the root cause of most concurrency overhead.

### 56. Statelessness

A component that holds no state can be replicated infinitely and horizontally. State is what makes scaling hard. Eliminate it where you can, isolate it where you can't.

### 57. Event-Driven Over Polling

Never check whether something has happened — wait to be told. Polling burns CPU continuously; events wake the system only when there is real work.

### 58. Tiered Storage

Not all data deserves the same speed of storage. Put hot data in fast memory, warm data on fast disk, cold data in cheap storage. Paying for speed you don't need is waste.

### 59. Bulkhead Pattern

Isolate failures so they cannot cascade. A slow or broken subsystem should never be able to drag down unrelated parts of the system.

### 60. Mechanical Sympathy

Understand the hardware your software runs on. Code written with awareness of CPU cache lines, branch predictors, and memory buses outperforms code that ignores them, even if both are logically identical.

---

## The Unified Philosophy

Performance is not a feature you add — it is a property you preserve.
Every decision you make either spends or saves compute, memory, and time.
The rules above are simply ways of seeing where that spending is happening so you can stop paying for things you don't need.

The Master Rule: Everything is a trade-off between time, space, and complexity.
Every optimization rule above trades one of these for another.
Understanding which resource is your actual bottleneck tells you which rules to apply first.
