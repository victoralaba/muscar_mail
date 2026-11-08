# A03: Software Supply Chain Failures

## What it is

Risk introduced through what the project pulls in and how it's built — vulnerable or malicious dependencies, compromised build pipelines, typosquatted or hijacked packages, and unverified artifacts. Unlike A08 (Integrity Failures), which is about trusting *data* once it's inside your system, A03 is about trusting *code and packages you didn't write* before and during the build.

## Checklist

- [ ] Dependencies are pinned (lockfile committed: `poetry.lock`/`uv.lock`/`requirements.txt` with hashes, `package-lock.json`/`pnpm-lock.yaml`), not left floating on version ranges alone
- [ ] Automated dependency vulnerability scanning runs in CI (`pip-audit`, `npm audit`, `safety`, GitHub Dependabot/Renovate)
- [ ] No dependency is pulled from an unpinned/untrusted source (random GitHub URL, unpinned git branch, private registry without integrity checks)
- [ ] New/unusual dependencies are sanity-checked before adding (download count, maintenance activity, matches the expected name — not a typosquat like `reqeusts` vs `requests`)
- [ ] Unused dependencies are removed periodically — smaller surface area
- [ ] Build pipeline (CI) runs with least-privilege credentials, not a broad admin token
- [ ] Build/CI scripts are reviewed like code — a malicious `postinstall`/`build` script in a dependency can run arbitrary code at install time
- [ ] Published packages (if the project publishes one) use provenance/signing where the registry supports it (npm provenance, sigstore)
- [ ] Third-party scripts loaded at runtime (CDN `<script src>`, analytics tags) use Subresource Integrity (`integrity="sha384-..."`) or are self-hosted
- [ ] `.dockerignore`/`.gitignore` prevents secrets and unnecessary files from entering build context/images

## Detection patterns

Language-agnostic:
- No lockfile present, or lockfile not committed to version control
- CI config with no vulnerability-scan step
- `<script src="https://...">` tags with no `integrity` attribute pulling from a third-party CDN
- Dependency version specifiers using `*`, `latest`, or unbounded ranges (`^0.0.0`, no upper bound) in a way that allows silent major-version jumps

Stack-specific:
- **Python**: `pip install` without `--require-hashes` in CI; `requirements.txt` with no version pins at all (`flask` instead of `flask==3.0.3`)
- **Node/npm/pnpm**: `package.json` deps on `git+https://...#branch` (mutable ref, not a commit SHA); postinstall scripts in `node_modules` not reviewed
- **Docker**: `FROM someimage:latest` instead of a pinned tag/digest; multi-stage builds copying more than needed from the build stage into the final image
- **CI (GitHub Actions etc.)**: third-party actions referenced by tag (`uses: someaction/foo@v1`) instead of a pinned commit SHA — tags are mutable and can be repointed by a compromised maintainer account

## Bad vs good examples

**Python dependency pinning**
```
# Bad (requirements.txt)
fastapi
requests

# Good
fastapi==0.115.0
requests==2.32.3
# and: pip install --require-hashes -r requirements.txt in CI, using a hash-pinned lockfile
```

**GitHub Actions — pinning third-party actions**
```yaml
# Bad — mutable tag, maintainer account compromise = supply chain compromise
- uses: some-third-party/action@v2

# Good — pinned to a commit SHA, comment notes the version for readability
- uses: some-third-party/action@a1b2c3d4e5f6...  # v2.3.1
```

**CDN script with Subresource Integrity**
```html
<!-- Bad -->
<script src="https://cdn.example.com/lib.js"></script>

<!-- Good -->
<script src="https://cdn.example.com/lib.js"
        integrity="sha384-<hash>"
        crossorigin="anonymous"></script>
```

## Remediation (priority order)

1. Commit a lockfile if one doesn't exist; pin all direct and transitive versions.
2. Add automated vulnerability scanning to CI, failing the build on high/critical findings.
3. Pin third-party CI actions/build steps to commit SHAs, not tags.
4. Add SRI hashes to any third-party script tag, or self-host the script.
5. Set up dependency update automation (Renovate/Dependabot) so patches land quickly instead of accumulating.
6. Review any dependency with install/build-time scripts before first adding it.
