# A06: Insecure Design

## What it is

A flaw that no amount of careful implementation fixes, because the architecture itself never accounted for the threat — missing threat modeling, business logic that assumes good faith, or a feature designed without considering how it could be abused. This is different from the other categories: A01–A05, A07 are usually "the design was fine, the implementation slipped"; A06 is "even a perfect implementation of this design is still exploitable."

## Checklist

- [ ] Sensitive features/flows had an explicit "how could this be abused" pass before being built, not just a happy-path design
- [ ] Business logic enforces real-world constraints server-side (can't apply a discount code twice, can't withdraw more than balance, can't skip a required approval step) — not just UI flow enforcement
- [ ] Multi-step flows (checkout, signup, password reset) can't be entered at a later step by directly calling a later-step endpoint, skipping earlier validation
- [ ] Rate limits / abuse limits exist on anything with real-world cost (email sending, SMS, expensive compute, discount/coupon application, free-tier resource creation)
- [ ] Trust boundaries are explicit: what the client is trusted to say vs what the server must independently verify (price, discount, quantity should never be trusted from the client at checkout)
- [ ] Segregation of duties / approval steps exist for high-impact actions (large transfers, permission grants, destructive operations) rather than a single click doing everything irreversibly
- [ ] The system fails toward the safe state under load/failure, not toward "allow everything" (see also A10)
- [ ] Recurring instances of the *same* access-control or validation bug across many independent endpoints is treated as a design gap (fix the pattern/framework-level default), not patched endpoint-by-endpoint forever

## Detection patterns

This category is found through reasoning about flows, not grep. Useful signals during review:
- A feature where the client sends a price, quantity-based total, or permission level that the server then trusts as-is
- A workflow where step 3's endpoint doesn't verify steps 1 and 2 actually happened (e.g., "confirm order" doesn't check "payment succeeded" independently)
- A "free trial" / "invite a friend" / coupon feature with no per-user/per-account limit
- The same class of bug (e.g., missing ownership check) appearing in 5+ unrelated endpoints — that's a sign the framework has no default-secure pattern, which is the actual (design-level) bug
- Any place a comment says "we trust the client here because..." — that assumption is the thing to threat-model

## Bad vs good examples

**Trusting client-supplied price**
```python
# Bad — client sends the price, server just charges it
@router.post("/checkout")
def checkout(item_id: int, price: float, user=Depends(get_current_user)):
    charge(user, price)

# Good — server looks up the authoritative price, ignores anything the client sent for it
@router.post("/checkout")
def checkout(item_id: int, user=Depends(get_current_user)):
    item = db.get(Item, item_id)
    charge(user, item.price)
```

**Multi-step flow — skipping steps**
```python
# Bad — /confirm-order doesn't check payment actually succeeded
@router.post("/confirm-order")
def confirm_order(order_id: int):
    mark_order_shipped(order_id)

# Good — re-verify the precondition server-side at the final step, don't trust the client got here honestly
@router.post("/confirm-order")
def confirm_order(order_id: int):
    order = db.get(Order, order_id)
    if order.payment_status != "captured":
        raise HTTPException(status_code=402, detail="Payment not completed")
    mark_order_shipped(order_id)
```

**Coupon/discount abuse**
```python
# Bad — no limit on how many times a code can be applied per account
def apply_coupon(user, code):
    discount = get_discount(code)
    apply(user, discount)

# Good
def apply_coupon(user, code):
    if CouponUse.objects.filter(user=user, code=code).exists():
        raise ValueError("Already used")
    discount = get_discount(code)
    CouponUse.objects.create(user=user, code=code)
    apply(user, discount)
```

## Remediation (priority order)

1. For any flow involving money, permissions, or resource creation: audit what the server trusts from the client, and move all authoritative values (price, role, quantity limits) to server-side lookups.
2. Add server-side re-verification at each step of multi-step flows — don't assume earlier steps happened just because a later endpoint was called.
3. Add per-user/per-account limits to anything with real-world abuse cost.
4. When the same bug recurs across many endpoints, fix it once at the framework/middleware level (see A01) instead of patching each instance — that's the actual design fix.
5. For new high-risk features, do a short threat-modeling pass before implementation: list who could misuse this and how, then design the constraint that prevents it.
