# Verifalia API: Authentication

## Overview

Verifalia REST API v2.4 supports HTTP Basic Authentication and Bearer Token Authentication over HTTPS.

Base API Endpoint:
```
https://api.verifalia.com/v2.4
```

---

## 1. HTTP Basic Authentication (Recommended)

Authenticate using your Verifalia account username and password (or sub-user API credentials created in the Verifalia dashboard).

### Headers:
```http
Authorization: Basic <base64(username:password)>
Content-Type: application/json
```

### Python (httpx):
```python
import httpx

client = httpx.AsyncClient(
    base_url="https://api.verifalia.com/v2.4",
    auth=(VERIFALIA_USERNAME, VERIFALIA_PASSWORD),
    timeout=httpx.Timeout(45.0, connect=10.0),
)
```

### cURL Example:
```bash
curl -u "my_username:my_password" \
  https://api.verifalia.com/v2.4/credits/balance
```

---

## 2. Bearer Token Authentication

Alternatively, generate a dedicated Bearer token in the Verifalia management portal:

### Headers:
```http
Authorization: Bearer <your_access_token>
```

---

## 3. Environment Variables

Store credentials strictly in environment variables:
* `VERIFALIA_USERNAME` — Your Verifalia account or API sub-user username
* `VERIFALIA_PASSWORD` — Your Verifalia account or API sub-user password
* `VERIFALIA_BASE_URL` — Defaults to `https://api.verifalia.com/v2.4`

Never hardcode credentials or log the `Authorization` header in application logs.
