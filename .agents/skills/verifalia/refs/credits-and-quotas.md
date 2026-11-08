# Verifalia API: Credits & Quotas

## Overview

Verifalia measures usage in **Credits**.
* Standard quality validation: **1 credit per validated email**.
* Free plan: **25 free credits per day** (refreshes daily).
* If deduplication is set to `Safe`, duplicates within the same batch only consume 1 credit.

---

## 1. Credit Balance Endpoint

**Endpoint**: `GET /v2.4/credits/balance`  
**Required Permission**: `credits:read` (enabled by default on primary account credentials).

### Request
```http
GET /v2.4/credits/balance HTTP/1.1
Host: api.verifalia.com
Authorization: Basic <base64(username:password)>
Accept: application/json
```

### Response (HTTP 200 OK)
```json
{
  "creditPacks": 0.0,
  "freeCredits": 25.0,
  "freeCreditsResetOn": "2026-11-09T00:00:00Z"
}
```

---

## 2. Hard Limits in muscar_mail

To protect free tier quotas and avoid unexpected 402/429 errors:
1. **Batch Size Limit**: Maximum **25 emails** per request.
2. **Quota Check Tool**: Exposed as an MCP tool `get_credit_balance` so agents can check remaining credits before dispatching validation runs.
3. **HTTP 402 Handling**: If credits are exhausted, Verifalia returns HTTP 402 (Payment Required). The service catches this and translates it into a clear agent-facing message.
