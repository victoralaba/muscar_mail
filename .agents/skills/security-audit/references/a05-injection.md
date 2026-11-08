# A05: Injection

## What it is

Untrusted input is sent to an interpreter (SQL engine, shell, template engine, browser DOM, ORM query builder, LDAP, XML parser) in a way that lets it change the interpreter's intended behavior instead of being treated as inert data. Covers SQL injection, Cross-Site Scripting (XSS), command injection, template injection, NoSQL injection, and similar.

## Checklist

- [ ] All SQL is parameterized (placeholders/bound params) — no string concatenation or f-strings building queries from user input
- [ ] ORM raw-query/raw-SQL escape hatches are avoided, or parameterized when used
- [ ] All output rendered into HTML is escaped by default (template engine auto-escaping on); any "render raw HTML" API (`dangerouslySetInnerHTML`, `{@html ...}`, `| safe`) is used only on content that's been sanitized or is fully trusted, never on raw user input
- [ ] No shell commands are built by string-concatenating user input; subprocess calls use argument arrays, not `shell=True` with interpolated strings
- [ ] User input isn't passed to `eval`/`exec`/`Function()`/dynamic template compilation
- [ ] File paths built from user input are validated/sanitized against path traversal (`..`, absolute paths, null bytes)
- [ ] Content-Security-Policy is set to reduce XSS blast radius even if an escaping bug slips through
- [ ] Input validation happens server-side regardless of client-side validation (client-side is UX, not security)
- [ ] NoSQL queries don't accept operator objects from user input unfiltered (e.g., MongoDB `$where`, `$gt` injection via JSON body)
- [ ] LDAP/XML/XPath queries built from user input are parameterized or the input is escaped for that specific syntax

## Detection patterns

Language-agnostic:
- String concatenation or f-string/template-literal building a query string: `f"SELECT * FROM x WHERE id = {id}"`, `` `SELECT * FROM x WHERE id = ${id}` ``
- `shell=True` (Python subprocess) or unescaped string passed to `exec`/`system`/`popen` with interpolated variables
- `dangerouslySetInnerHTML`, `{@html ...}` (Svelte), `v-html` (Vue), `.innerHTML =` assigned from anything traceable to user input
- `eval(`, `new Function(`, `exec(` fed by request data

Stack-specific:
- **FastAPI/SQLAlchemy**: `db.execute(text(f"..."))` with f-string interpolation instead of bound `:param` placeholders; `.filter(text(...))` with raw strings
- **Svelte/SvelteKit**: `{@html userContent}` without a sanitizer (DOMPurify or equivalent) run first; API routes (`+server.ts`) building shell commands or file paths from `params`/request body
- **SQL directly**: dynamic table/column names built from user input (can't be parameterized — must be strictly allowlisted against known-safe identifiers)
- **Shell/CI scripts**: user-controlled input (PR titles, branch names, issue content) interpolated directly into a shell step in CI — a classic and frequently-exploited injection vector

## Bad vs good examples

**SQL injection (Python)**
```python
# Bad
cursor.execute(f"SELECT * FROM users WHERE email = '{email}'")

# Good
cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
# or with SQLAlchemy Core:
db.execute(text("SELECT * FROM users WHERE email = :email"), {"email": email})
```

**XSS (Svelte)**
```svelte
<!-- Bad -->
{@html userComment}

<!-- Good — let Svelte's default escaping handle it -->
{userComment}

<!-- If raw HTML is genuinely needed (rich text), sanitize first -->
{@html DOMPurify.sanitize(userComment)}
```

**Command injection (Python)**
```python
# Bad
subprocess.run(f"convert {filename} out.png", shell=True)

# Good — argument array, no shell interpretation
subprocess.run(["convert", filename, "out.png"])
```

**NoSQL injection**
```js
// Bad — a JSON body like {"password": {"$ne": null}} bypasses the check
db.users.findOne({ username, password: req.body.password });

// Good — coerce/validate types before using in a query; reject non-string password values
if (typeof req.body.password !== "string") throw new Error("invalid");
```

## Remediation (priority order)

1. Fix SQL injection first — it's usually the highest-impact (full DB read/write) and easiest to find via grep for string-built queries.
2. Turn on/verify template auto-escaping is active project-wide; audit every raw-HTML escape hatch individually.
3. Replace `shell=True`/string-built shell commands with argument arrays.
4. Add a CSP header as defense-in-depth for XSS.
5. Add input validation (type/shape checking, e.g. Pydantic models / Zod schemas) at every boundary so malformed operator-injection payloads (NoSQL) are rejected before reaching the query layer.
6. Add a linter rule (bandit, eslint-plugin-security) to catch these patterns automatically in CI going forward.
