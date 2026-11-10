---
title: Key-based multi-account routing and quota isolation
author: Victor
date: 2026-11-10
branch: main
id: l-42af536c
scope: repo
status: active
src: agent
touches:
  - ".env.example"
  - core/config.py
  - domains/mcp/handlers.py
  - domains/mcp/routes.py
  - domains/verification/cache.py
  - domains/verification/routes.py
  - domains/verification/service.py
  - main.py
  - shared/security.py
---

Multi-tenant Verifalia account support uses key-based routing: each account defines its own credentials and authorized API keys via VERIFALIA_ADDITIONAL_ACCOUNTS. AuthenticatedAccount subclasses str so it drop-in replaces raw key strings across route dependencies while carrying account identity. Daily quota Redis keys are namespaced per account as quota:daily:{account_id}:{date} to protect independent 25-credit free tiers, while batch cache remains shared globally.
