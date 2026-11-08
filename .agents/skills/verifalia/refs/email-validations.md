# Verifalia API: Email Validations (Submission)

## Overview

Submits one or more email addresses for verification. Supports both asynchronous background processing and synchronous execution via the `waitTime` query parameter.

**Endpoint**: `POST /v2.4/email-validations`  
**Query Parameters**:
* `waitTime` (integer, milliseconds): Number of milliseconds to hold the HTTP connection waiting for job completion (up to `30000` = 30 seconds). When set to e.g. `30000`, small batches (1–25 emails) return directly with HTTP 200 OK once complete, avoiding separate polling.

---

## Request Headers

```http
POST /v2.4/email-validations?waitTime=30000 HTTP/1.1
Host: api.verifalia.com
Authorization: Basic <base64(username:password)>
Content-Type: application/json
Accept: application/json
```

---

## Request Body Schema

```json
{
  "entries": [
    {
      "inputData": "user1@example.com"
    },
    {
      "inputData": "user2@domain.org",
      "custom": "internal-user-id-42"
    }
  ],
  "quality": "Standard",
  "deduplication": "Safe"
}
```

### Fields:
* `entries` (array of objects, required): List of email entries to validate.
  * `inputData` (string, required): The email address or contact string to validate.
  * `custom` (string, optional): Arbitrary metadata echoed back in the response.
* `quality` (string, optional): Validation quality level:
  * `Standard` (default): Fast and accurate, balanced credit consumption (1 credit/email).
  * `High`: Additional verification steps.
  * `Low`: Surface check only.
* `deduplication` (string, optional): How duplicate emails in the same batch are handled:
  * `Off`: Every entry is validated and billed.
  * `Safe` (recommended): Duplicates within the batch are validated once and billed once.

---

## Synchronous vs Asynchronous Response

### Case 1: Completed within `waitTime` (HTTP 200 OK)
When verification finishes before `waitTime` expires:
```json
{
  "overview": {
    "id": "e7c2a715-9c86-4fbf-9b97-8c312fbdfb33",
    "status": "Completed",
    "createdOn": "2026-11-08T14:20:00Z",
    "completedOn": "2026-11-08T14:20:03Z",
    "submitted": 2,
    "completed": 2
  },
  "entries": [
    {
      "index": 0,
      "inputData": "user1@example.com",
      "classification": "Deliverable",
      "status": "Success",
      "emailAddress": "user1@example.com",
      "emailAddressLocalPart": "user1",
      "emailAddressDomainPart": "example.com",
      "isDisposableEmailAddress": false,
      "isRoleAccount": false,
      "isFreeEmailAddress": false,
      "isSuccess": true
    }
  ]
}
```

### Case 2: In-Progress / Timeout (HTTP 202 Accepted)
If the verification takes longer than `waitTime`:
* Returns HTTP `202 Accepted`.
* Header `Location: /v2.4/email-validations/{id}`.
* Body contains `"status": "InQueue"` or `"status": "InProgress"`.
* Requires polling `GET /v2.4/email-validations/{id}` until `"status": "Completed"`.
