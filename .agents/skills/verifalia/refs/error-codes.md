# Verifalia API: Error Handling & Status Codes

## Overview

Verifalia uses standard HTTP response status codes along with a JSON error body when errors occur.

---

## 1. HTTP Status Codes

| Status Code | Reason | Cause & Solution |
| :--- | :--- | :--- |
| **`200 OK`** | Success | Request succeeded and job is completed (with `waitTime`). |
| **`202 Accepted`** | Asynchronous | Job submitted but still processing; poll status endpoint. |
| **`400 Bad Request`** | Malformed Input | Invalid JSON, empty entries array, or unparseable field. |
| **`401 Unauthorized`** | Auth Failed | Missing or invalid username/password in `Authorization` header. |
| **`402 Payment Required`** | Out of Credits | Credit balance exhausted (daily 25 credits consumed). |
| **`403 Forbidden`** | Permission Denied | Account lacks permissions (e.g. `credits:read`). |
| **`404 Not Found`** | Resource Missing | Job ID does not exist or has expired. |
| **`429 Too Many Requests`** | Rate Limited | Too many concurrent requests; back off. |
| **`500 Internal Error`** | Server Fault | Verifalia internal error. Retry with backoff. |

---

## 2. Error Response Body Format

```json
{
  "error": {
    "code": "InsufficientCredits",
    "message": "The account does not have enough credits to complete the requested operation."
  }
}
```

---

## 3. Exception Handling in muscar_mail

The service layer wraps `httpx.HTTPStatusError` into domain-specific exceptions:

```python
class VerifaliaError(Exception):
    """Base error for Verifalia interactions."""
    def __init__(self, message: str, status_code: int = 500, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}

class InsufficientCreditsError(VerifaliaError):
    """Raised when 402 Payment Required is returned."""
    def __init__(self, message: str = "Daily free credits or balance exhausted."):
        super().__init__(message, status_code=402)

class AuthenticationError(VerifaliaError):
    """Raised when 401 Unauthorized is returned."""
    def __init__(self, message: str = "Invalid Verifalia credentials."):
        super().__init__(message, status_code=401)
```
