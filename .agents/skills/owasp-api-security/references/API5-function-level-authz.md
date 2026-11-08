# API5:2023 — Broken Function Level Authorization

Where API1 is about *which object* a user can access, API5 is about *which function/endpoint* — a low-privilege (or unauthenticated) user reaching an action meant only for admins or a different role, usually because the check is missing, client-controlled, or inconsistently applied.

## Detection checklist

- [ ] Do admin endpoints (`POST /admin/users/{id}/promote`, `DELETE /admin/*`) check the caller's role server-side, or just live at a URL the frontend doesn't link to ("security by obscurity")?
- [ ] Is the role/permission read from a client-supplied value (JWT claim the client can influence, request body field, header) rather than looked up server-side from a trusted source?
- [ ] Are role checks applied consistently across HTTP methods on the same resource — e.g., `GET /users/{id}` checked, but `DELETE /users/{id}` on the same route group not?
- [ ] Do newer endpoints added to an existing router inherit the group's auth middleware, or can one be added without it by mistake?
- [ ] Is there a default-allow pattern (endpoint is accessible unless explicitly restricted) instead of default-deny (must explicitly grant access)?
- [ ] Are internal/debug/test endpoints (`/internal/*`, `/debug/*`, `/__admin`) reachable in production without the same authz as everything else?

## Common broken pattern

```
@app.delete("/admin/users/{user_id}")
def delete_user(user_id: str, current_user = Depends(get_current_user)):
    db.delete(User, user_id)   # any authenticated user can call this — no role check
```

Or, worse, trusting a client-controlled role claim:
```
if request.json.get("role") == "admin":   # client sets this in the request body
    allow_action()
```

## Prevention pattern

Default-deny, checked server-side from a trusted source (DB lookup or a signed/verified claim the client cannot forge), and applied at the router/middleware level so new routes inherit it:

```
@app.delete("/admin/users/{user_id}")
def delete_user(user_id: str, current_user = Depends(require_role("admin"))):
    db.delete(User, user_id)
```

```
def require_role(role: str):
    def dependency(current_user = Depends(get_current_user)):
        if role not in current_user.roles:   # roles loaded from DB/session, not from the request
            raise HTTPException(403)
        return current_user
    return dependency
```

Group routes so the sensitive prefix (`/admin/*`) carries the auth dependency at the router level, not per-handler — one handler forgetting the decorator shouldn't be possible.

## Notes for review

- Check every HTTP method on a resource, not just the one the user pointed you at — GET being protected doesn't mean DELETE is.
- "It's not in the API docs / frontend doesn't call it" is not a control — verify the actual server-side check exists.
