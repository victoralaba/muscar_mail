# API6:2023 — Unrestricted Access to Sensitive Business Flows

The endpoint is technically working as designed and correctly authorized — the problem is the *business process* itself can be automated/scripted at scale in a way that harms the business: buying out limited stock with bots, mass-creating accounts to farm promo codes, scraping the entire catalog, spamming a "contact seller" flow, holding all available appointment slots without completing booking.

This is distinct from API4: API4 is about infrastructure exhaustion (CPU/bandwidth); API6 is about abuse of a legitimate, correctly-functioning feature at the business-logic level.

## Detection checklist

- [ ] Are there flows where completing the action provides value **disproportionate to the effort**, inviting automation: limited-inventory purchases, coupon/promo redemption, referral bonuses, waitlist/appointment holds, gift card balance checks?
- [ ] Can an account be created (and the sensitive flow triggered) faster than a human could plausibly do it, with no CAPTCHA, device fingerprinting, or velocity checks?
- [ ] Do "hold" actions (reserve item, hold appointment slot) have a way to be abandoned/repeated indefinitely without cost or cooldown, effectively denying the resource to real users?
- [ ] Is there any per-account or per-device velocity limiting on flows that have real-world value (distinct from generic API4 rate limiting, which is about request volume, not business value per request)?
- [ ] Can the flow be triggered without ever completing the "human" part of the intended journey (e.g., calling checkout API directly, skipping the UI steps a human would go through)?

## Prevention pattern

There's no single code snippet for this category — it's business-logic-specific — but the levers are consistent:

- **Velocity/behavioral limits** tied to the business action, not just request count: e.g., max N coupon redemptions per account per day, max M holds per user before requiring completion or cooldown.
- **Friction where it matters**: CAPTCHA or proof-of-work on high-value, bot-attractive flows (account creation before a limited drop, checkout for scarce inventory) — not on every endpoint, just the ones with asymmetric value.
- **Detect non-human patterns**: request timing too fast/regular for a human, missing normal client fingerprints/headers a real browser would send, sequential/enumerated inputs.
- **Expire holds**: any "reserve without paying" action needs an expiry + release-back-to-pool, so it can't be abused to lock out real customers indefinitely.
- **Server-side enforcement of the intended flow order**: if checkout requires cart → address → payment, don't let payment be called directly with a fabricated cart reference — verify the prior steps actually happened for this session.

## Notes for review

- This category requires understanding what the business actually cares about — flag it in terms of business impact ("bots could buy out the entire launch-day inventory in seconds") not just "no rate limit."
- Don't confuse with API4: if the fix would be "add a rate limit," that's often API4. If the fix requires understanding what makes the *feature* valuable to abuse, it's API6.
