# A08: Software or Data Integrity Failures

## What it is

Code or data is trusted without verifying it hasn't been tampered with — insecure CI/CD pipelines that can be modified by unauthorized parties, auto-update mechanisms that don't verify what they're installing, and insecure deserialization of data from an untrusted source. Where A03 is about what you *choose* to pull in, A08 is about *trusting it/what happens to it* once it's in your pipeline or your data flow.

## Checklist

- [ ] CI/CD pipeline configuration changes require review (protected branches, required PR approval before workflow files can change)
- [ ] CI runners don't execute untrusted code with access to production secrets (e.g., a PR from a fork triggering a workflow that has access to deploy keys)
- [ ] Auto-update / self-update mechanisms verify a signature or checksum of the update before applying it
- [ ] Deserialization of data from an untrusted source uses a safe format/mode — no `pickle.loads`, `yaml.load` (unsafe loader), Java `ObjectInputStream`, or PHP `unserialize` on attacker-influenced bytes
- [ ] Build artifacts are reproducible/verifiable — what's deployed matches what was reviewed and built by CI, not hand-uploaded
- [ ] Webhooks/callbacks from third parties verify a signature (HMAC) before the payload is trusted, not just "it came from the right IP" or "it hit the right URL"
- [ ] Feature flags / remote config fetched at runtime are fetched over an authenticated channel and validated before being applied

## Detection patterns

Language-agnostic:
- Deserialization of a byte stream/string from user input or an external API using a format that supports arbitrary object reconstruction (pickle, unsafe YAML, PHP serialize) rather than a data-only format (JSON) or a safe/restricted loader
- A webhook handler with no signature verification step (`X-Hub-Signature`, `Stripe-Signature`, etc.) before processing the payload
- CI workflow files that run on `pull_request_target` (has access to secrets) while also checking out and executing the PR's own code — a well-known compromise pattern
- Update-checker code that downloads and executes/installs a binary/script with no signature or checksum check

Stack-specific:
- **Python**: `pickle.load`/`pickle.loads` on any data that could originate from a client or external system; `yaml.load(data)` instead of `yaml.safe_load(data)`
- **CI (GitHub Actions)**: `pull_request_target` trigger combined with `actions/checkout` of the PR head and a subsequent build/run step
- **Webhooks (FastAPI/SvelteKit endpoints)**: an endpoint that receives Stripe/GitHub/etc. events and processes them without calling the provider's signature-verification helper first

## Bad vs good examples

**Unsafe deserialization**
```python
# Bad — pickle can execute arbitrary code on load
data = pickle.loads(request_body)

# Good — use a data-only format
data = json.loads(request_body)
```
```python
# Bad
config = yaml.load(untrusted_yaml)

# Good
config = yaml.safe_load(untrusted_yaml)
```

**Webhook signature verification**
```python
# Bad — trusts the payload just because it hit the endpoint
@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    event = await request.json()
    handle_event(event)

# Good
@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers["stripe-signature"]
    event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)  # raises on mismatch
    handle_event(event)
```

**CI pipeline trust boundary**
```yaml
# Bad — PR-controlled code runs with access to repo secrets
on: pull_request_target
jobs:
  build:
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: npm install && npm run build   # attacker-controlled package.json/scripts run with secrets in scope

# Good — use `pull_request` (no secrets) for untrusted code, or explicitly avoid executing PR code in a secrets-bearing context
on: pull_request
```

## Remediation (priority order)

1. Replace any `pickle`/unsafe-YAML/equivalent deserialization of external data with a safe format or safe loader — this is often remotely-exploitable RCE.
2. Add signature verification to every webhook handler before the payload is trusted.
3. Audit CI workflows for `pull_request_target` + untrusted-code-execution combinations; separate "needs secrets" from "runs untrusted code."
4. Protect the branch containing workflow files with required review.
5. Add checksum/signature verification to any auto-update mechanism.
