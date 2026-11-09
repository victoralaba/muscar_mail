# muscar_mail — API Contracts & Protocol Specifications

## 1. Authentication & Security

All non-health endpoints (`POST /api/v1/*`, `GET /api/v1/*`, and `POST /mcp/v1/*`) enforce authentication using constant-time digest comparison (`secrets.compare_digest`).

Clients must provide an authorized key via either header:
- `Authorization: Bearer <api_key>`
- `X-API-Key: <api_key>`

Unauthenticated requests receive HTTP 401 Unauthorized (`{"error": "Unauthorized: Missing or invalid API key."}`) or JSON-RPC 2.0 error code `-32600`.

---

## 2. Stateless MCP JSON-RPC 2.0 (`POST /mcp/v1/`)

The Model Context Protocol endpoint operates over pure HTTP POST. Trailing slash and non-trailing slash routes (`/mcp/v1/` and `/mcp/v1`) are both supported.

### Supported Protocol Revisions
- **`2026-07-28`** (Default / Modern Specification)
- **`2025-11-25`** (Negotiable)
- **`2024-11-05`** (Negotiable / Legacy)

Every response includes the `MCP-Protocol-Version: 2026-07-28` HTTP header.

---

### Methods

#### `initialize`
Negotiates protocol version and returns server capabilities.

- **Request**:
  ```json
  {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2026-07-28",
      "capabilities": {},
      "clientInfo": {
        "name": "agent-client",
        "version": "1.0.0"
      }
    }
  }
  ```
- **Response**:
  ```json
  {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
      "protocolVersion": "2026-07-28",
      "capabilities": { "tools": {} },
      "serverInfo": {
        "name": "muscar-mail",
        "version": "1.0.0"
      }
    }
  }
  ```

#### `ping`
Heartbeat check returning an empty JSON-RPC result.

- **Request**: `{"jsonrpc": "2.0", "id": 2, "method": "ping"}`
- **Response**: `{"jsonrpc": "2.0", "id": 2, "result": {}}`

#### `tools/list`
Returns the tool catalog for AI agents.

- **Request**: `{"jsonrpc": "2.0", "id": 3, "method": "tools/list"}`
- **Response**:
  ```json
  {
    "jsonrpc": "2.0",
    "id": 3,
    "result": {
      "tools": [
        {
          "name": "verify_emails",
          "description": "Verifies deliverability for a batch of 1 to 25 emails synchronously via Verifalia v2.4 API.",
          "inputSchema": {
            "type": "object",
            "properties": {
              "emails": {
                "type": "array",
                "items": { "type": "string" },
                "minItems": 1,
                "maxItems": 25,
                "description": "Batch of 1 to 25 email addresses to verify."
              }
            },
            "required": ["emails"]
          }
        },
        {
          "name": "get_cached_verification",
          "description": "Queries zero-credit Redis cache for previously verified email batch.",
          "inputSchema": { ... }
        },
        {
          "name": "get_credit_balance",
          "description": "Queries current Verifalia credit balance and midnight-UTC reset timestamp.",
          "inputSchema": { "type": "object", "properties": {} }
        }
      ]
    }
  }
  ```

#### `tools/call`
Executes an MCP tool.

- **Verify Emails Request**:
  ```json
  {
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "verify_emails",
      "arguments": {
        "emails": ["user@example.com"]
      }
    }
  }
  ```
- **Tool Result Response**:
  ```json
  {
    "jsonrpc": "2.0",
    "id": 4,
    "result": {
      "content": [
        {
          "type": "text",
          "text": "{\"submitted\": 1, \"completed\": 1, \"cached\": false, \"results\": [{\"email\": \"user@example.com\", \"classification\": \"Deliverable\", \"status\": \"Success\", \"is_deliverable\": true, \"is_disposable\": false, \"is_role_account\": false, \"is_free_email\": false}]}"
        }
      ],
      "isError": false
    }
  }
  ```

---

### JSON-RPC 2.0 Error Codes

| Code | Message | Cause |
|---|---|---|
| `-32700` | Parse error | Request body is not valid JSON. |
| `-32600` | Invalid Request | Payload violates JSON-RPC 2.0 structure. |
| `-32601` | Method not found | Method is not recognized. |
| `-32602` | Invalid params | Tool arguments missing or invalid (e.g. batch > 25 emails). |
| `-32603` | Internal error | Uncaught server exception. |
| `-32002` | Insufficient credits | Daily free-tier quota (25/day) exhausted. |
| `-32022` | Unsupported protocol version | Client requested an unsupported protocol version. |

---

## 3. REST API Contracts

### `GET /health`
- **Summary**: Instantaneous zero-network container health probe (< 5ms).
- **Auth**: None required.
- **Response**: HTTP 200 OK
  ```json
  {
    "status": "healthy",
    "app": "muscar-mail",
    "version": "1.0.0",
    "protocol_version": "2026-07-28"
  }
  ```

### `POST /api/v1/verify`
- **Summary**: Verifies deliverability for 1 to 25 emails.
- **Auth**: Required (`Bearer` or `X-API-Key`).
- **Request Body**:
  ```json
  {
    "emails": ["alice@gmail.com", "bob@example.com"]
  }
  ```
- **Response**: HTTP 200 OK
  ```json
  {
    "submitted": 2,
    "completed": 2,
    "cached": false,
    "results": [
      {
        "email": "alice@gmail.com",
        "classification": "Deliverable",
        "status": "Success",
        "is_deliverable": true,
        "is_disposable": false,
        "is_role_account": false,
        "is_free_email": true
      },
      {
        "email": "bob@example.com",
        "classification": "Deliverable",
        "status": "Success",
        "is_deliverable": true,
        "is_disposable": false,
        "is_role_account": false,
        "is_free_email": false
      }
    ]
  }
  ```
- **Error Responses**:
  - `401 Unauthorized`: Missing or invalid API key.
  - `402 Payment Required`: Daily 25-credit quota reached (resets at `00:00:00 UTC`).
  - `422 Unprocessable Entity`: Batch contains 0 emails, > 25 emails, or invalid format.
  - `502 Bad Gateway`: Upstream Verifalia API error or timeout.

### `GET /api/v1/credits`
- **Summary**: Inspects current credit pack and daily free credit balance.
- **Auth**: Required (`Bearer` or `X-API-Key`).
- **Response**: HTTP 200 OK
  ```json
  {
    "credit_packs": 150.0,
    "free_credits": 25.0,
    "free_credits_reset_on": "2026-11-10T00:00:00Z"
  }
  ```
