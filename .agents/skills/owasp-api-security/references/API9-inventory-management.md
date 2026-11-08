# API9:2023 — Improper Inventory Management

Attack surface grows through APIs the security/dev team has lost track of: old versions kept alive after a new one ships, staging/beta environments with weaker controls exposed to the internet, undocumented internal endpoints, or third-party/partner-facing APIs no one is actively monitoring.

## Detection checklist

- [ ] Are there multiple live API versions (`/v1/`, `/v2/`) where the old one has weaker auth/validation than the current one, kept around for "just in case" without an active deprecation plan?
- [ ] Do staging/dev/QA environments run with production data or production-adjacent access, while having weaker auth (default creds, disabled rate limits, verbose debugging) than prod?
- [ ] Is there an authoritative, current list of all endpoints/services and their exposure (public/internal/partner-only), or does that knowledge live only in individual engineers' heads?
- [ ] Are there endpoints reachable that aren't in the OpenAPI/API docs at all — added ad hoc, forgotten, or intentionally undocumented ("we don't advertise it so it's fine")?
- [ ] Do partner/third-party-facing API keys or integrations get the same security review as first-party ones, or are they assumed trustworthy by default?
- [ ] Is there a process for decommissioning an endpoint/version — removing it from routing, revoking its credentials — or does "deprecated" just mean "not in the docs anymore" while the route still works?

## This category is largely process, not code

Unlike most of the other nine, API9 usually isn't fixed with a code snippet — it's fixed with inventory and process:

- **Maintain a live API inventory**: every environment (prod, staging, internal), every version, who owns it, what data it touches, and its actual exposure (public internet / internal network / partner-only). Generate this from routing config or an API gateway where possible rather than a manually-maintained doc that drifts.
- **Version deprecation has an end date**: when `/v2/` ships, `/v1/` gets a sunset date, and is actually removed — not left running indefinitely "just in case," accumulating security debt as it falls further behind the current version's protections.
- **Non-prod environments get prod-equivalent controls** if they touch anything sensitive, or get sanitized/synthetic data if they don't — not full auth left disabled "because it's just staging."
- **Every exposed endpoint appears in the API spec** (OpenAPI/etc.), including internal ones — undocumented-on-purpose is not a security control, it just means the next security review misses it too.
- **Third-party/partner API integrations go through the same review as internal ones**, including what data they can reach and whether their credentials are scoped minimally.

## What to actually check in a review

If you're reviewing code/infra rather than running a process audit, look for signals: hardcoded old API version routes still mounted in the router, feature flags implying a deprecated path is still live, staging config that looks materially weaker than prod's, or route definitions with no matching entry in the API documentation/spec file.
