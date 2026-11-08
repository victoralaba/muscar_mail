# A01: Broken Access Control (incl. SSRF)

## What it is

Restrictions on what an authenticated (or anonymous) user is allowed to do are not properly enforced — a user can act on, or view, resources or actions outside their intended permissions. This includes vertical (regular user reaching admin function), horizontal (user A reading/editing user B's data), and missing-check (endpoint has no check at all) failures. Server-Side Request Forgery (SSRF) — where the server is tricked into making a request to an attacker-chosen destination — is grouped here because it's fundamentally the server failing to restrict what it's willing to do on the caller's behalf.

## Checklist

- [ ] Every state-changing endpoint (POST/PUT/PATCH/DELETE) checks the caller is authenticated, not just that a token is present but valid
- [ ] Every endpoint that reads/writes a specific resource (by ID) checks the caller *owns or is permitted* that specific resource — not just "is logged in" (horizontal access control)
- [ ] Admin/privileged endpoints check role/permission server-side, not just hide the UI button client-side
- [ ] Access control is enforced centrally (middleware/dependency/decorator) rather than copy-pasted per route — copy-pasted checks are the ones that get forgotten on the next new route
- [ ] IDs in URLs/bodies are not trusted as sole authorization (no "if you know the UUID you can access it")
- [ ] CORS config doesn't allow `*` origin alongside credentials
- [ ] Directory listing is disabled; no path traversal via user-supplied file paths (`../../etc/passwd`)
- [ ] Any server-initiated outbound request (webhooks, "fetch URL", image-by-URL, PDF-from-URL, import-from-URL features) validates and restricts the target: blocks internal/private IP ranges, blocks `localhost`/`169.254.169.254` (cloud metadata endpoint), restricts scheme (no `file://`, `gopher://`), ideally uses an allowlist of destinations rather than a denylist
- [ ] JWTs/session tokens are validated for signature, expiry, and audience — not just decoded and trusted
- [ ] Rate limiting exists on sensitive actions to prevent enumeration/brute force of access-controlled resources
- [ ] Default deny: new routes/resources are inaccessible until a check is explicitly added, not accessible until someone remembers to lock them down

## Detection patterns

Language-agnostic smells:
- A route/handler function with no auth/permission check before it touches the DB or filesystem
- A resource lookup by ID (`get_by_id`, `find(id)`, `SELECT ... WHERE id = ?`) with no accompanying `WHERE owner_id = current_user.id` or equivalent ownership filter
- Client-side-only role checks (`if (user.role === 'admin') showButton()`) with no matching server check
- `fetch(user_supplied_url)`, `requests.get(url)`, `urlopen(url)`, `axios.get(url)` where `url` (or its host) comes from user input, with no allowlist/denylist
- Hardcoded `Access-Control-Allow-Origin: *` combined with `Access-Control-Allow-Credentials: true`

Stack-specific:
- **FastAPI**: routes without a `Depends(get_current_user)` (or equivalent) where they should have one; a dependency that checks auth but not ownership of the path/body-supplied resource ID
- **SvelteKit**: `+page.server.ts`/`+server.ts` load/actions that read `params`/`locals` without checking `locals.user` owns the resource; client-only guards in `+layout.svelte` with no matching `hooks.server.ts` check
- **SQL**: queries filtered only by the target's primary key, missing a tenant/owner column in the `WHERE` clause
- **Cloud/infra**: S3 buckets or storage without explicit private ACL; IAM policies with wildcard `Resource: "*"` or `Action: "*"`

## Bad vs good examples

**Python/FastAPI — horizontal access control**
```python
# Bad: any authenticated user can fetch any invoice by ID
@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, user: User = Depends(get_current_user)):
    return db.query(Invoice).filter(Invoice.id == invoice_id).first()

# Good: scoped to the caller
@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, user: User = Depends(get_current_user)):
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id, Invoice.owner_id == user.id
    ).first()
    if not invoice:
        raise HTTPException(status_code=404)  # 404, not 403 — don't confirm existence
    return invoice
```

**SSRF — server-side URL fetch**
```python
# Bad
resp = requests.get(request_body.image_url)

# Good — resolve, then check the resolved IP isn't private/link-local, restrict scheme, use an allowlist if the use case allows it
from ipaddress import ip_address
import socket

def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    ip = ip_address(socket.gethostbyname(parsed.hostname))
    return not (ip.is_private or ip.is_loopback or ip.is_link_local)
```

**SvelteKit — server-side ownership check**
```ts
// Bad
export const load: PageServerLoad = async ({ params }) => {
  return { doc: await db.doc.findUnique({ where: { id: params.id } }) };
};

// Good
export const load: PageServerLoad = async ({ params, locals }) => {
  const doc = await db.doc.findUnique({ where: { id: params.id } });
  if (!doc || doc.ownerId !== locals.user?.id) throw error(404);
  return { doc };
};
```

## Remediation (priority order)

1. Add a centralized authorization layer (middleware/dependency) so no route can accidentally skip it — make the secure path the path of least resistance.
2. Fix horizontal access control first — it's usually the most common and most exploitable (enumerate an ID, get someone else's data).
3. For SSRF-capable features, move to an allowlist of permitted destinations if the use case allows it; otherwise block private/loopback/link-local ranges and the cloud metadata IP explicitly.
4. Return 404 (not 403) for resources the caller isn't permitted to see, to avoid confirming existence to an attacker probing IDs.
5. Add rate limiting to any endpoint that could be used to enumerate valid IDs/resources.
6. Add automated tests: one authenticated-as-wrong-user test per resource-scoped endpoint.
