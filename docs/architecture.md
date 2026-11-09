# muscar_mail — Architecture & Systems Specification

## 1. Prime Mental Model & System Topology

**muscar_mail** is an ultra-lean, stateless Model Context Protocol (MCP) server and REST API for high-confidence email deliverability verification powered by the Verifalia v2.4 API.

```
muscar_mail/
├── main.py                     # App factory, lifespan, CORS, /health, router mounts
├── requirements.txt            # Pinned dependencies (frozen at creation)
├── pyproject.toml              # Metadata and Python >= 3.14 target
├── .python-version             # Pinned 3.14.4 runtime for Render buildpacks
├── .env.example                # Documented environment variables
│
├── core/                       # Global foundation
│   ├── config.py               # Pydantic Settings (VERIFALIA_*, REDIS_URL, MCP_API_KEYS)
│   ├── logging.py              # Structlog JSON configuration & secret redaction
│   └── telemetry.py            # Sentry SDK initialization (fail-open)
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

---

## 2. Invariants & Guarantees

| Invariant | Guarantee | Enforcement Mechanism |
|---|---|---|
| **INV-BOOT-FAST** | Application boots from cold in <2 seconds. | Zero synchronous blocking I/O, zero database migrations, lazy network connection pools. |
| **INV-HEALTH-ZERO-NET** | `GET /health` responds instantaneously (<5ms) with HTTP 200 without network dispatch. | Pure in-memory status check (`{"status": "healthy", ...}`); zero Verifalia or Redis calls. |
| **INV-CLEAN-LIFESPAN** | Sockets and Redis connection pools release cleanly on SIGTERM/sleep. | `asynccontextmanager` lifespan invoking `verifalia_service.close()` and `redis_client.close()`. |
| **INV-QUOTA-1** | Hard batch size ceiling: maximum 25 emails per batch request. | Rejected at schema/route boundary before calling upstream APIs or Redis. |
| **INV-CREDIT-1** | Zero-credit batch hash recovery. | Inputs hashed deterministically (`cache:batch:<sha256>`) in Redis to serve identical requests at 0 cost. |
| **INV-DEDUPE-1** | Repeated emails within a batch consume only 1 credit. | `Safe` canonical email deduplication applied prior to quota calculation. |
| **INV-MIDNIGHT-UTC** | Free-tier daily quota expires exactly at midnight GMT. | Daily Redis key (`quota:daily:YYYY-MM-DD`) TTL dynamically calculated to `00:00:00 UTC`. |
| **INV-RESIL-1** | Fail-open Redis resilience. | Redis failures, timeouts, or connection drops never crash the service; logs warnings and falls open to direct verification. |

---

## 3. Serverless Lifecycle on Render

Render free-tier web services put idle containers to sleep after 15 minutes of inactivity. To operate reliably without state corruption:

1. **Stateless Request Processing**: Every incoming HTTP request (REST or MCP JSON-RPC) is independently processable. There are no stateful WebSockets, persistent SSE streams, or in-memory session tables.
2. **Graceful Teardown**: When Render sends `SIGTERM` to initiate container sleep, FastAPI's `lifespan` context manager traps the signal, drains pending requests, and closes the `httpx2` HTTP/2 client session and Redis connection pool cleanly.
3. **Instant Wake-Up**: Upon the next incoming request, the container boots from cold in under 2 seconds.
