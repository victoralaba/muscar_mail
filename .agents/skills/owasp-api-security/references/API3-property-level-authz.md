# API3:2023 — Broken Object Property Level Authorization

Combines two older categories (excessive data exposure + mass assignment). Two directions of the same root cause: the API doesn't control *which fields* of an object are exposed in responses or writable in requests, at the field level rather than the object level.

## Detection checklist

**Excessive data exposure (read direction)**
- [ ] Does the handler serialize the full ORM/DB model (`return user.__dict__` / `return jsonify(user)`) and rely on the frontend to just not display sensitive fields?
- [ ] Do internal fields (password hash, internal flags, other users' PII, cost/margin data) exist on the same model as public-facing fields, serialized together?
- [ ] Does a list/search endpoint return more per-item detail than the single-item endpoint intends to expose?

**Mass assignment (write direction)**
- [ ] Does the handler bind the full request body directly onto a model/struct (`user.update(**request.json)` / `Model(**body)`) without an explicit allowlist?
- [ ] Can a client set fields it shouldn't control: `is_admin`, `role`, `account_balance`, `verified`, `owner_id`, `price`, `status`?
- [ ] Are "internal-only" fields protected only by not being in the frontend form, rather than being rejected server-side?

## Common broken pattern

```
# Read: serializes everything on the model
return jsonify(user.__dict__)

# Write: binds whatever the client sends
user.update(**request.json)
db.commit()
```

## Prevention pattern

Use explicit, separate schemas per direction and per audience — never reuse the internal DB model as the wire format:

```
# Read: explicit output schema, per audience if needed
class UserPublicOut(Schema):
    id: str
    display_name: str
    # no email, no password_hash, no internal flags

return UserPublicOut.from_orm(user)

# Write: explicit input schema — only these fields are bindable
class UserUpdateIn(Schema):
    display_name: str
    bio: str | None
    # no role, no is_admin, no balance

data = UserUpdateIn.parse(request.json)   # unknown/extra fields rejected, not silently dropped
user.update(**data.dict())
```

Prefer schema libraries that reject unknown fields by default (or configure them to) rather than silently ignoring extras — silent-drop can hide the bug in testing while still being probed in production.

For different audiences of the same object (owner view vs. public view vs. admin view), use distinct output schemas rather than one schema with optional fields toggled by role checks scattered through serialization code.

## Notes for review

- This is the category most often caused by convenience (`**request.json`, auto-serializing ORM objects) rather than a deliberate design choice — look specifically for shortcuts that skip explicit schemas.
- Sensitive-field allowlists should live in one place per model, not be re-derived per endpoint.
