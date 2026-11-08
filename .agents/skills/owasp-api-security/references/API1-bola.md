# API1:2023 — Broken Object Level Authorization (BOLA)

Also known as IDOR (Insecure Direct Object Reference). The most common and highest-impact API vulnerability: an endpoint accepts an object ID (in the URL path, query string, or body) and returns/modifies/deletes that object without verifying the authenticated caller actually owns or is permitted to access it.

## Detection checklist

Ask this for **every** endpoint that takes an ID: `GET /orders/{id}`, `PUT /users/{id}`, `DELETE /invoices/{id}`, `POST /accounts/{id}/transfer`, etc.

- [ ] Does the handler fetch the object by ID and return/modify it **without** a `WHERE owner_id = current_user.id` (or equivalent) check?
- [ ] Is the ownership check performed in application code but on a stale/cached object, or after a separate unauthenticated lookup?
- [ ] Are IDs sequential integers (easy to enumerate) rather than UUIDs — not a fix by itself, but raises exploitability?
- [ ] Do nested resources (`/orgs/{org_id}/projects/{project_id}`) check that `project_id` actually belongs to `org_id`, or just that the user can access *some* project?
- [ ] Are admin/support "view any record" endpoints reachable by non-admin roles because the authz check was only added to the "normal" endpoint?
- [ ] Do batch/bulk endpoints (`POST /invoices/bulk-delete` with an array of IDs) check ownership on **every** ID in the array, or only the first / none?

## Common broken pattern

```
GET /api/orders/{order_id}
handler:
    order = db.get(Order, order_id)
    return order   # <-- no check that order.user_id == current_user.id
```

## Prevention pattern

Scope the query itself to the authenticated principal — don't fetch-then-check, filter-then-fetch so a mismatched ID returns 404, not 403 (403 confirms the object exists, which is its own minor leak):

```
GET /api/orders/{order_id}
handler:
    order = db.get(Order, order_id, filter=Order.user_id == current_user.id)
    if not order:
        return 404
    return order
```

For nested resources, chain the ownership check through the full path, not just the leaf:

```
project = db.get(Project, project_id,
                  filter=(Project.id == project_id) &
                         (Project.org_id == org_id) &
                         (Project.org.members.any(user_id == current_user.id)))
```

For bulk operations, filter the whole ID set through the same ownership scope and only act on the intersection — don't loop with per-item try/except that silently skips failures without telling the caller.

## Notes for review

- Centralize ownership-scoping logic (a repository method, a query helper, a decorator) rather than repeating raw `WHERE` clauses per handler — inconsistent copies are how this regresses.
- Row-level security at the database layer (e.g., Postgres RLS) is a strong defense-in-depth layer for this category specifically, since it holds even if application code forgets the check.
