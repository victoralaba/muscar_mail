# API8:2023 — Security Misconfiguration

A broad catch-all for insecure defaults, incomplete/rushed configuration, and unnecessary exposure — usually not a code-logic bug, but a deployment/config one. Individually small, cumulatively serious.

## Detection checklist

- [ ] Do error responses in production include stack traces, SQL, internal file paths, or library versions?
- [ ] Is CORS configured with `Access-Control-Allow-Origin: *` (or a reflected origin) alongside `Access-Control-Allow-Credentials: true` — a combination that allows any site to make authenticated requests?
- [ ] Are debug/dev modes, admin interfaces, or example endpoints (Django admin, Swagger/OpenAPI UI, GraphQL introspection, framework debug toolbar) reachable in production without auth?
- [ ] Are default credentials (admin/admin, default DB passwords) still in place anywhere, including in staging environments reachable from the internet?
- [ ] Are security headers present: `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` where applicable, and is HTTPS enforced (no plain HTTP fallback)?
- [ ] Do unnecessary HTTP methods work on endpoints (`TRACE`, `OPTIONS` returning verbose info, `PUT`/`DELETE` enabled where only `GET`/`POST` are intended)?
- [ ] Are cloud storage buckets / file storage set to public when they shouldn't be?
- [ ] Is there a consistent, minimal error-response format applied at the framework level, or does it depend on each handler remembering to sanitize errors?
- [ ] Are dependencies/libraries patched, or is the app running known-vulnerable versions (check lockfile against advisories if this is in scope)?

## Common broken pattern

```
app.debug = True   # left on in production — verbose tracebacks leak internals
CORS(app, resources={r"/api/*": {"origins": "*"}})  # combined with cookie-based auth
```

## Prevention pattern

- Generic, sanitized error responses in production; log the detailed error server-side only:
```
@app.errorhandler(Exception)
def handle_error(e):
    log.exception(e)  # full detail in logs, not in response
    return {"error": "internal_server_error"}, 500
```
- Explicit CORS allowlist of known frontend origins, never `*` combined with credentials:
```
CORS(app, origins=["https://app.example.com"], supports_credentials=True)
```
- Security headers set at a middleware/proxy layer so they apply uniformly, not per-handler.
- Separate configuration per environment (dev/staging/prod) with production defaulting to the strictest settings, and debug/introspection endpoints disabled or auth-gated outside dev.
- Automated dependency scanning in CI (even a basic `pip-audit`/`npm audit` step) rather than relying on manual review to catch known-vulnerable packages.

## Notes for review

- This category rewards checking actual response headers and error bodies against a running instance (or config files) rather than just reading application logic — many of these are infra/config, not code.
- Flag combinations, not just individual settings: wildcard CORS alone is often fine for public read-only APIs; wildcard CORS *with* credentialed/cookie auth is the actual vulnerability.
