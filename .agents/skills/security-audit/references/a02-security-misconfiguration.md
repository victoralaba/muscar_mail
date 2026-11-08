# A02: Security Misconfiguration

## What it is

The application, framework, server, or cloud environment is running with insecure defaults, unnecessary features enabled, permissive cloud/IAM permissions, or verbose errors/debug info exposed — not because of a code-level bug, but because of *how the thing is configured and deployed*.

## Checklist

- [ ] Debug mode / stack traces are disabled in production (framework debug flag, `DEBUG=False`, no `--reload` in prod)
- [ ] Default credentials (admin/admin, default DB passwords) are changed or disabled
- [ ] Unnecessary services, ports, endpoints, and sample apps are removed or disabled (no `/admin` demo panel left reachable)
- [ ] Security headers are set: `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options`/`frame-ancestors`, `Strict-Transport-Security`, `Referrer-Policy`
- [ ] CORS is scoped to actual known origins, not `*`
- [ ] Cloud storage (S3/GCS buckets, blob storage) defaults to private; public access is explicit and reviewed
- [ ] IAM roles/service accounts follow least privilege — no wildcard `*:*` policies for convenience
- [ ] Error responses returned to the client don't leak stack traces, SQL, internal paths, or library versions
- [ ] Software/framework/runtime versions are current — not running an EOL version with known unpatched misconfig-adjacent issues
- [ ] Environment-specific config (dev/staging/prod) is cleanly separated — no dev-only bypass flags reachable in prod
- [ ] Directory listing disabled on static file servers
- [ ] `.env`, `.git`, config files, and backups are not served by the web server / not in the deploy artifact's public root

## Detection patterns

Language-agnostic:
- Grep for `debug=True`, `DEBUG = True`, `app.debug`, `NODE_ENV` not set to `production`
- Grep for `Access-Control-Allow-Origin: *`
- Missing security-header middleware in the app's setup/init code
- `.env` files, `*.pem`, `id_rsa`, or credential-looking files inside a directory served statically (`static/`, `public/`, build output root)
- Dockerfiles running as `root` with no `USER` directive
- IaC (Terraform/CloudFormation) with `0.0.0.0/0` ingress rules on non-web ports, or `PublicAccessBlockConfiguration` disabled on S3

Stack-specific:
- **FastAPI/uvicorn**: `uvicorn.run(..., reload=True)` in a prod entrypoint; `CORSMiddleware(allow_origins=["*"], allow_credentials=True)`; no `TrustedHostMiddleware`
- **SvelteKit**: `vite.config` exposing dev server to `0.0.0.0` in prod; server-only env vars (no `PUBLIC_` prefix) accidentally referenced in `+page.svelte` (client bundle) instead of `+page.server.ts`
- **Docker/CI**: base images not pinned to a digest, `latest` tag in prod builds; secrets passed as `ARG`/build args (which land in image history) instead of runtime secrets

## Bad vs good examples

**FastAPI CORS + headers**
```python
# Bad
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)

# Good
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response
```

**Dockerfile — not running as root**
```dockerfile
# Bad
FROM python:3.12
COPY . .
CMD ["uvicorn", "app:app"]

# Good
FROM python:3.12-slim
RUN useradd -m appuser
COPY --chown=appuser . .
USER appuser
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**SvelteKit env var exposure**
```ts
// Bad — non-PUBLIC_ env var referenced in a component that ships to the client
<script>
  import { DATABASE_URL } from '$env/static/private'; // will fail to build, but a copy-paste of the value directly is the real-world version of this mistake
</script>

// Good — private vars only touched in +page.server.ts / +server.ts, only PUBLIC_-prefixed vars reach the client
```

## Remediation (priority order)

1. Turn off debug/verbose error output in every environment reachable from the internet; route real errors to server-side logs instead (see A09/A10).
2. Lock down CORS to explicit origins.
3. Add the standard security header set via middleware, once, centrally.
4. Audit cloud storage and IAM for public/wildcard access; move to least privilege.
5. Add a config-drift check to CI: fail the build if `DEBUG`/`reload` flags are true in the prod config, or if `.env`-like files are present in the build's public output.
6. Pin base images and dependency versions; don't deploy on `latest`.
