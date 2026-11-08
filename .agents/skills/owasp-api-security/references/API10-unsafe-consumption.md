# API10:2023 — Unsafe Consumption of APIs

The mirror image of the other nine: instead of your API being attacked, your API is the client of a third-party API, and it trusts that third party's responses more than it should — no validation, no size/timeout limits, no handling for the third party being slow, malicious, or compromised.

## Detection checklist

- [ ] Is the response from a third-party API validated against an expected schema before being used, or is it trusted and passed straight through / deserialized directly into internal models?
- [ ] Are third-party API calls made over TLS with certificate validation actually enabled (not disabled "to fix an SSL error" during development and left that way)?
- [ ] Do third-party calls have timeouts and size limits, or can a slow/huge response from a compromised or misbehaving partner API hang or exhaust your service (this overlaps with API4, but the trust boundary here is specifically "you don't control the other side")?
- [ ] Is data from a third-party API sanitized before being rendered (HTML/JS injection if displayed in a browser), stored (SQL/NoSQL injection if inserted into a query), or used to construct further requests (SSRF if it contains a URL your service then fetches — overlaps with API7)?
- [ ] Are third-party API keys/credentials scoped to the minimum needed, and rotated/revocable, rather than long-lived broad-access keys?
- [ ] If a third-party API redirects, does your client follow the redirect blindly, potentially to an unexpected/attacker-influenced host?
- [ ] Is there a fallback/circuit-breaker for when the third-party API is unavailable or returns unexpected data, or does a bad response propagate directly into your application's error state or, worse, get treated as valid data?

## Common broken pattern

```
resp = requests.get(partner_api_url, verify=False)  # TLS verification disabled
data = resp.json()
db.insert(SomeModel(**data))   # third-party response bound directly onto internal model, no validation
```

## Prevention pattern

```
resp = requests.get(partner_api_url, timeout=5)  # TLS verified by default, explicit timeout
resp.raise_for_status()

if len(resp.content) > MAX_RESPONSE_SIZE:
    raise ValueError("response too large")

data = PartnerResponseSchema.parse(resp.json())  # explicit schema validation, not raw pass-through
db.insert(SomeModel(name=data.name, value=data.value))  # explicit field mapping, not **kwargs
```

- Treat every third-party response like untrusted user input: validate structure and types before use, exactly as you would request-body validation (API3's prevention pattern applies here too).
- Explicit timeouts and response-size caps on every outbound client call, not just the ones that "seem slow."
- If the third-party response contains a URL your service will subsequently fetch (webhooks-of-webhooks, "next page" links, embedded resource links), apply the same SSRF controls as API7 — a URL isn't safer for coming from a partner API.
- Keep partner API credentials scoped and stored the same way first-party secrets are (API2's guidance applies) — a partner integration is still a credential that can leak.

## Notes for review

- This category is easy to miss because it's about the direction of trust, not the direction of the request — look specifically at what happens to data *after* it comes back from an external call, not just how the call is made.
- `verify=False` (or equivalent TLS-bypass flags) left in from debugging is a very common and very serious finding in this category — always grep for it explicitly.
