# API4:2023 — Unrestricted Resource Consumption

No limits on how much of the API's resources (CPU, memory, disk, bandwidth, third-party API spend, database load) a single client or request can consume — enabling denial-of-service or cost-exhaustion attacks, sometimes without any "hacking" at all.

## Detection checklist

- [ ] Is there rate limiting per client/IP/API-key on the endpoint, or can it be called unlimited times per second?
- [ ] Do list/search endpoints have a max page size, or can a client request `?limit=999999999`?
- [ ] Are file/payload uploads size-capped before being read into memory in full?
- [ ] Do endpoints that trigger expensive work (report generation, image processing, search, ML inference, sending emails/SMS) have per-user or global concurrency limits?
- [ ] Are outbound calls (DB queries, third-party APIs) given timeouts, or can a slow dependency hold a connection/worker open indefinitely?
- [ ] Is there a cap on array/batch sizes in request bodies (`ids: [...]` with 100,000 entries)?
- [ ] Are expensive operations that cost real money per call (SMS, email, LLM tokens, third-party lookups) rate-limited specifically, separate from general request rate limits?
- [ ] Does pagination use offset-based queries that get slower (not just bigger) as the offset grows, without a sane upper bound?

## Common broken pattern

```
@app.get("/search")
def search(query: str, limit: int = 20):
    results = db.query(Item).filter(...).limit(limit).all()  # client controls limit, no max
    return results
```

## Prevention pattern

```
MAX_LIMIT = 100

@app.get("/search")
@rate_limit("60/minute", key="user_id")
def search(query: str, limit: int = 20):
    limit = min(limit, MAX_LIMIT)
    results = db.query(Item).filter(...).limit(limit).all()
    return results
```

- Enforce rate limits at the gateway/middleware layer where possible (per API key or authenticated user, not just per IP — IPs are shared/spoofable) so every endpoint inherits a sane default rather than opting in individually.
- Set explicit timeouts on every outbound call (DB, HTTP client, queue) — an unbounded call is an unbounded resource hold.
- Cap request body size at the framework/proxy level (e.g., `client_max_body_size` in nginx, `MAX_CONTENT_LENGTH` in Flask) in addition to any application-level file-size checks.
- For expensive/costly operations, use a stricter limit than the general API rate limit, and consider a queue with backpressure rather than synchronous processing.

## Notes for review

- This category is easy to under-rate because it's not "hacking" in the exploit sense — but unbounded pagination or unbounded batch size on a production endpoint is a real outage/cost risk and worth flagging even without a PoC.
- Don't over-apply: an internal admin-only endpoint behind VPN with a handful of trusted callers doesn't need the same rate-limit rigor as a public one — match the control to actual exposure.
