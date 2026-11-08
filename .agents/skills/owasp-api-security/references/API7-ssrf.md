# API7:2023 — Server-Side Request Forgery (SSRF)

Any time the API fetches a URL, and that URL (or a component of it — host, path, redirect target) is influenced by user input, an attacker can potentially make the server issue requests to internal services, cloud metadata endpoints, or arbitrary external hosts on the server's behalf.

## Detection checklist

- [ ] Does the API accept a URL/hostname from the client and fetch it (webhooks, "import from URL", avatar-from-URL, PDF/screenshot generation from a URL, link preview, XML with external entity references)?
- [ ] Is there a check against the URL scheme (rejecting `file://`, `gopher://`, `dict://`) and not just `http(s)://` prefix matching?
- [ ] Is there an allowlist of permitted hosts/domains, or is any host accepted (denylist-only approaches are bypassable via DNS rebinding, IP-literal encoding, redirects)?
- [ ] Does the fetch follow redirects? If so, is the redirect target re-validated against the same allowlist, or does the first check happen only on the original URL?
- [ ] Can the URL resolve to internal/private IP ranges (`127.0.0.1`, `169.254.169.254` cloud metadata, `10.0.0.0/8`, `192.168.0.0/16`, `::1`) — is there resolution-time validation, or only a string-based hostname check that DNS can bypass?
- [ ] Does XML parsing have external entity (XXE) expansion disabled — a related vector where the "URL fetch" is implicit in the parser rather than explicit application code?

## Common broken pattern

```
def fetch_avatar(url: str):
    response = requests.get(url)   # any URL, any scheme, follows redirects, no IP check
    return response.content
```

## Prevention pattern

Layered defense — no single check is sufficient on its own:

```
ALLOWED_SCHEMES = {"https"}
ALLOWED_HOSTS = {"cdn.trusted-partner.com"}  # allowlist, not denylist

def fetch_avatar(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("URL not permitted")

    # Resolve and check the actual IP before connecting — prevents DNS rebinding
    # and hostname tricks that pass the string check but resolve to internal IPs.
    ip = socket.gethostbyname(parsed.hostname)
    if ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_loopback:
        raise ValueError("URL resolves to a private address")

    response = requests.get(url, allow_redirects=False, timeout=5)  # no auto-redirects
    return response.content
```

- If redirects must be supported, resolve and re-validate each hop manually rather than letting the HTTP client follow them silently.
- Prefer an allowlist of specific expected hosts over a denylist of "known bad" ranges — denylists miss cases (IPv6, decimal/octal IP encodings, DNS rebinding).
- For XML parsing, disable external entity resolution at the parser level (e.g., `defusedxml` in Python, or explicit `XMLInputFactory` feature flags in Java) regardless of whether SSRF via XXE seems "in scope" — it's the same category.
- Run outbound fetches from a network-segmented egress point (proxy/sidecar) with its own firewall rules as defense-in-depth, so an application-layer bypass doesn't automatically mean internal network access.

## Notes for review

- String-based host validation alone (`if "internal" not in url`) is not sufficient — flag it even if it "technically" blocks the obvious case, since encoding/redirect/DNS tricks bypass it.
- Cloud metadata endpoints (`169.254.169.254` on AWS/GCP/Azure) are the highest-value SSRF target — explicitly check whether they're reachable from the fetch context.
