# Verifalia API: Job Status & Polling

## Overview

When a job submission does not complete within the requested `waitTime`, or when checking previously submitted jobs, query the status endpoint.

**Endpoint**: `GET /v2.4/email-validations/{job_id}`  
**Query Parameters**:
* `waitTime` (integer, optional): Wait up to 30,000ms on the poll request as well.

---

## 1. Request

```http
GET /v2.4/email-validations/e7c2a715-9c86-4fbf-9b97-8c312fbdfb33?waitTime=5000 HTTP/1.1
Host: api.verifalia.com
Authorization: Basic <base64(username:password)>
Accept: application/json
```

---

## 2. Job Overview Lifecycle States

The `overview.status` property reflects one of the following states:

| Status | Meaning | Next Step |
| :--- | :--- | :--- |
| `InQueue` | Job accepted and queued for worker execution. | Wait and poll again. |
| `InProgress` | Workers are actively validating mailbox addresses. | Wait and poll again. |
| `Completed` | All entries validated. Response includes full `entries` array. | Process results. |
| `Expired` | Job results expired from Verifalia servers (typically after 30 days). | Cannot recover. |
| `Deleted` | Explicitly deleted by client or retention policy. | Cannot recover. |

---

## 3. Polling Pattern in Python

For small batches (≤25 emails), `waitTime=30000` almost always resolves immediately on `POST`. However, if HTTP 202 is returned, poll with exponential backoff:

```python
async def poll_until_complete(
    client: httpx.AsyncClient,
    job_id: str,
    max_attempts: int = 5,
    delay_seconds: float = 2.0,
) -> dict:
    for attempt in range(max_attempts):
        response = await client.get(
            f"/email-validations/{job_id}",
            params={"waitTime": 5000},
        )
        data = response.json()
        if data.get("overview", {}).get("status") == "Completed":
            return data
        await asyncio.sleep(delay_seconds)

    raise TimeoutError(f"Validation job {job_id} did not complete in time.")
```
