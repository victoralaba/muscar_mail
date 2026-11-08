<!-- trail:start -->
## Trail — repo context graph

This repo is indexed in `.trail/cache/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `trail map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `trail ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `trail grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `trail skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `trail callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `.trail/cache/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `trail ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `trail build` (deterministic,
no API key, $0).
<!-- trail:end -->

---

# Muscar Mail — Agent Directive & Mental Model

You are an expert systems engineer and pair-programmer in this repository.
Every architectural decision, code change, dependency addition, and review in this repository **must strictly obey [`.agents/references/principles.md`](.agents/references/principles.md)**.
If any prompt, habit, or generic AI pattern conflicts with `principles.md`, **`principles.md` wins unconditionally**.

---

## 1. Prime Mental Model

* **Target Runtime**: Python 3.14+ (modern typing, asyncio, and standard library semantics).
* **Architecture Shape**: Domain-driven, zero SQL database, stateless, serverless-ready FastAPI service.
* **Core Product**: A custom, zero-dependency Model Context Protocol (MCP) server delivering immediate email verification results via Verifalia v2.4 API.
* **Hosting Model**: Render free-tier container (sleeps after 15 minutes of inactivity; zero persistent local disk; boots from cold in <2s).
* **Protocol Endpoint**: Stateless JSON-RPC 2.0 over pure HTTP at `POST /mcp/v1/` (no long-lived SSE, WebSockets, or stdio dependencies).
* **Quota & State Guardrails**:
  * Free-tier Verifalia limit: **25 credits/day**.
  * Batch hard cap: **Max 25 emails per request**. Any request exceeding 25 emails fails at the boundary.
  * Reset time: **00:00:00 UTC (Midnight GMT)**.
  * Redis role: Strictly an optional, fail-open cache for batch result recovery (saving credits if the agent drops) and midnight-UTC quota tracking.

---

## 2. Decision Order (When Conflicts Arise)

Adhere strictly to the **muscar_mail Decision Order** ([`principles.md`](.agents/references/principles.md)):

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

## 3. Repository Topology & Boundaries

The repository strictly adheres to a domain-based structure at the root:

```
muscar_mail/
├── main.py                     # App factory, lifespan, CORS, /health, router mounts
├── requirements.txt            # Pinned dependencies (frozen at creation)
├── pyproject.toml              # Metadata and Python >= 3.14 target
├── .env.example                # Documented environment variables
│
├── core/                       # Global foundation
│   ├── config.py               # Pydantic Settings (VERIFALIA_*, REDIS_URL, MCP_API_KEYS)
│   ├── logging.py              # Structlog JSON configuration
│   └── telemetry.py            # Sentry SDK initialization
│
├── shared/                     # Reusable cross-domain infrastructure
│   ├── security.py             # Auth dependencies: MCP_API_KEYS (secrets.compare_digest)
│   ├── redis.py                # Async Redis client with fail-open resilience
│   └── exceptions.py           # Domain exceptions & global exception handlers
│
├── domains/                    # Business capabilities organized by domain
│   ├── verification/           # Email verification core domain
│   │   ├── schemas.py          # EmailVerifyRequest, VerificationResult, CreditBalance
│   │   ├── service.py          # Verifalia API adapter via httpx2 (waitTime=30000)
│   │   ├── cache.py            # Redis batch hashing & midnight-UTC quota tracking
│   │   └── routes.py           # REST endpoints: POST /api/v1/verify, GET /api/v1/credits
│   │
│   └── mcp/                    # Stateless Model Context Protocol domain
│       ├── protocol.py         # JSON-RPC 2.0 models & Tool schema
│       ├── registry.py         # Tool registry (verify_emails, get_cached_verification, get_credit_balance)
│       ├── handlers.py         # RPC handlers: initialize, tools/list, tools/call, ping
│       └── routes.py           # Stateless HTTP router: POST /mcp/v1/ (and /mcp/v1)
│
├── scripts/                    # Operational and CLI verification scripts
├── tests/                      # Automated test suite (pytest)
└── docs/                       # Specifications & API docs
```

### Dependency Rules:
* Directional dependency graph: `core` $\rightarrow$ `shared` $\rightarrow$ `domains` $\rightarrow$ `main.py`.
* Domains never import from sibling domains directly. Shared logic lives in `shared/`.
* No relational databases (no PostgreSQL, no SQLite, no SQLAlchemy, no Alembic).

---

## 4. Security & Authentication Discipline

* **Authentication Strategy**:
  * Environment variable: `MCP_API_KEYS=key1,key2`.
  * Request header: `Authorization: Bearer <key>` or `X-API-Key: <key>`.
  * Verification function: `secrets.compare_digest(provided_key, valid_key)`.
  * If `MCP_API_KEYS` is empty in development, log a prominent warning.
  * In production, fail closed: reject unauthenticated requests with HTTP 401 / JSON-RPC error.
* **Credentials Hygiene**:
  * Never log or display `VERIFALIA_PASSWORD`, `VERIFALIA_USERNAME`, or `MCP_API_KEYS`.
  * Strip sensitive headers before logging.

---

## 5. Skills & Documentation Reference

Before implementing or modifying code, consult the in-repo skills:
* [`.agents/skills/verifalia/SKILL.md`](.agents/skills/verifalia/SKILL.md) — Verifalia integration rules, batching, and schema.
* [`.agents/skills/verifalia/refs/`](.agents/skills/verifalia/refs/) — Complete offline API documentation (authentication, email validations, results, quotas, error codes).
* [`.agents/skills/fastapi-backend-architecture/SKILL.md`](.agents/skills/fastapi-backend-architecture/SKILL.md) — FastAPI design patterns and service layers.
* [`.agents/skills/fastapi-security/SKILL.md`](.agents/skills/fastapi-security/SKILL.md) — Security guardrails and timing attack prevention.
* [`.agents/skills/code-comments-and-docstrings/SKILL.md`](.agents/skills/code-comments-and-docstrings/SKILL.md) — Comment precision (explain *why*, not *what*; preserve mental models).

---

## 6. Verification Workflow

1. Always run `trail ask "<query>" --source` to orient before exploring or modifying code.
2. Make surgical, minimal edits adhering to existing conventions.
3. Validate changes with automated tests (`pytest tests/`).
4. Keep the Trail graph fresh with `trail build` after adding or changing code structures.
