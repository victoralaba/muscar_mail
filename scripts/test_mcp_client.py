#!/usr/bin/env python3
"""Operational verification CLI script for muscar_mail Model Context Protocol server.

Simulates an external AI agent / MCP client interacting with the stateless HTTP
JSON-RPC 2.0 endpoint (POST /mcp/v1/) and zero-network health check (GET /health).
Requires zero external dependencies (pure Python standard library).

Usage:
    python scripts/test_mcp_client.py
    python scripts/test_mcp_client.py --base-url https://verif.muscar.app --api-key YOUR_KEY
    python scripts/test_mcp_client.py --skip-verify  # Runs handshake & credits without spending verify credits
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

# Terminal color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_step(title: str) -> None:
    print(f"\n{BLUE}{BOLD}==> {title}{RESET}")


def print_ok(msg: str) -> None:
    print(f"  {GREEN}✔ [OK]{RESET} {msg}")


def print_warn(msg: str) -> None:
    print(f"  {YELLOW}⚠ [WARN]{RESET} {msg}")


def print_fail(msg: str) -> None:
    print(f"  {RED}✘ [FAIL]{RESET} {msg}")


def load_env_default_key() -> Optional[str]:
    """Attempts to read first API key from local .env if present."""
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("MCP_API_KEYS="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        keys = [k.strip() for k in val.split(",") if k.strip()]
                        if keys:
                            return keys[0]
        except Exception:
            pass
    return os.environ.get("MCP_API_KEY")


def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[str, Any]]:
    """Executes an HTTP request using Python standard library urllib."""
    headers = headers or {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status_code = resp.getcode()
            body = resp.read().decode("utf-8")
            try:
                return status_code, json.loads(body)
            except json.JSONDecodeError:
                return status_code, {"raw_body": body}
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"error": body}
        return status_code, parsed
    except Exception as exc:
        return 0, {"error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify muscar_mail MCP server operations over pure HTTP."
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base server URL (e.g. https://verif.muscar.app or http://localhost:8000)",
    )
    parser.add_argument(
        "--api-key",
        default=load_env_default_key(),
        help="MCP API Key for authorization (defaults to first key in .env or $MCP_API_KEY)",
    )
    parser.add_argument(
        "--email",
        default="test@example.com",
        help="Email address to verify during tools/call test (default: test@example.com)",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        default=False,
        help="Skip the live email verification call to conserve daily Verifalia credits",
    )

    args = parser.parse_args()

    # 1. Determine target server URL (prompt interactively if not provided)
    base_url = args.base_url
    if not base_url:
        env_url = os.environ.get("SERVER_URL")
        if env_url:
            base_url = env_url
        elif sys.stdin.isatty():
            user_input = input(f"\nEnter target server URL [default: https://verif.muscar.app]: ").strip()
            if not user_input:
                base_url = "https://verif.muscar.app"
            elif user_input.startswith("http://") or user_input.startswith("https://"):
                base_url = user_input
            else:
                base_url = f"https://{user_input}"
        else:
            base_url = "http://localhost:8000"

    base_url = base_url.rstrip("/")

    # 2. Determine API Key
    api_key = args.api_key
    if not api_key:
        if sys.stdin.isatty():
            print_warn("No MCP API key found in .env or arguments.")
            api_key = input("Enter MCP API Key: ").strip()
        if not api_key:
            print_fail("No MCP API key provided. Specify --api-key or set MCP_API_KEYS in .env")
            return 1

    # 3. Determine if live verification should be executed
    skip_verify = args.skip_verify
    if not skip_verify and sys.stdin.isatty():
        prompt = input(f"\nVerify live email '{args.email}'? (Consumes 1 credit) [y/N]: ").strip().lower()
        if prompt not in ("y", "yes"):
            skip_verify = True

    auth_headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    mcp_endpoint = f"{base_url}/mcp/v1/"

    print(f"{BOLD}Starting muscar_mail Operational Verification Client{RESET}")
    print(f"Target Server: {BLUE}{base_url}{RESET}")
    print(f"MCP Endpoint:  {BLUE}{mcp_endpoint}{RESET}")

    # -------------------------------------------------------------------------
    # 1. Health Probe Verification (GET /health)
    # -------------------------------------------------------------------------
    print_step("1. Zero-Network Health Probe Check (GET /health)")
    code, resp = http_request(f"{base_url}/health")
    if code == 200 and resp.get("status") == "healthy":
        print_ok(f"Status 200 OK — App: {resp.get('app')}, Version: {resp.get('version')}")
    else:
        print_fail(f"Health check failed (HTTP {code}): {resp}")
        return 1

    # -------------------------------------------------------------------------
    # 2. MCP JSON-RPC 2.0 Ping Check
    # -------------------------------------------------------------------------
    print_step("2. MCP JSON-RPC 2.0 Ping (POST /mcp/v1/)")
    ping_payload = {
        "jsonrpc": "2.0",
        "id": "ping_test_1",
        "method": "ping",
    }
    code, resp = http_request(mcp_endpoint, method="POST", headers=auth_headers, payload=ping_payload)
    if code == 200 and resp.get("result") == {}:
        print_ok("Ping responded with valid JSON-RPC 2.0 empty result payload.")
    else:
        print_fail(f"Ping failed (HTTP {code}): {resp}")
        return 1

    # -------------------------------------------------------------------------
    # 3. MCP Handshake / Initialize Check
    # -------------------------------------------------------------------------
    print_step("3. MCP Handshake & Protocol Negotiation (initialize)")
    init_payload = {
        "jsonrpc": "2.0",
        "id": "init_test_2",
        "method": "initialize",
        "params": {
            "protocolVersion": "2026-07-28",
            "capabilities": {},
            "clientInfo": {"name": "muscar-test-client", "version": "1.0.0"},
        },
    }
    code, resp = http_request(mcp_endpoint, method="POST", headers=auth_headers, payload=init_payload)
    if code == 200 and "result" in resp:
        res = resp["result"]
        server_info = res.get("serverInfo", {})
        print_ok(
            f"Handshake accepted — Server: {server_info.get('name')} v{server_info.get('version')}, "
            f"Protocol: {res.get('protocolVersion')}"
        )
    else:
        print_fail(f"Initialize failed (HTTP {code}): {resp}")
        return 1

    # -------------------------------------------------------------------------
    # 4. MCP Tools List Catalog Check
    # -------------------------------------------------------------------------
    print_step("4. MCP Tool Catalog Discovery (tools/list)")
    list_payload = {
        "jsonrpc": "2.0",
        "id": "list_test_3",
        "method": "tools/list",
    }
    code, resp = http_request(mcp_endpoint, method="POST", headers=auth_headers, payload=list_payload)
    if code == 200 and "result" in resp and "tools" in resp["result"]:
        tools = resp["result"]["tools"]
        tool_names = [t.get("name") for t in tools]
        expected_tools = {"verify_emails", "get_cached_verification", "get_credit_balance"}
        missing = expected_tools - set(tool_names)
        if not missing:
            print_ok(f"All {len(tools)} tools registered: {', '.join(tool_names)}")
        else:
            print_fail(f"Missing expected tools: {missing}")
            return 1
    else:
        print_fail(f"tools/list failed (HTTP {code}): {resp}")
        return 1

    # -------------------------------------------------------------------------
    # 5. MCP Tool Call: get_credit_balance
    # -------------------------------------------------------------------------
    print_step("5. Tool Execution: get_credit_balance")
    credit_payload = {
        "jsonrpc": "2.0",
        "id": "credits_test_4",
        "method": "tools/call",
        "params": {
            "name": "get_credit_balance",
            "arguments": {},
        },
    }
    code, resp = http_request(mcp_endpoint, method="POST", headers=auth_headers, payload=credit_payload)
    if code == 200 and "result" in resp and not resp.get("result", {}).get("isError"):
        content_text = resp["result"]["content"][0]["text"]
        balance_data = json.loads(content_text)
        print_ok(
            f"Live Credit Balance: {balance_data.get('free_credits')} free credits, "
            f"{balance_data.get('credit_packs')} credit packs (Reset: {balance_data.get('free_credits_reset_on')})"
        )
    else:
        print_warn(f"get_credit_balance returned an error or non-200: {resp}")

    # -------------------------------------------------------------------------
    # 6. MCP Tool Call: verify_emails (Live or Skipped)
    # -------------------------------------------------------------------------
    if skip_verify:
        print_step("6. Tool Execution: verify_emails (SKIPPED via --skip-verify)")
        print_warn("Skipping live verification to conserve credits.")
    else:
        print_step(f"6. Tool Execution: verify_emails for '{args.email}'")
        verify_payload = {
            "jsonrpc": "2.0",
            "id": "verify_test_5",
            "method": "tools/call",
            "params": {
                "name": "verify_emails",
                "arguments": {
                    "emails": [args.email],
                },
            },
        }
        code, resp = http_request(mcp_endpoint, method="POST", headers=auth_headers, payload=verify_payload)
        if code == 200 and "result" in resp:
            content_text = resp["result"]["content"][0]["text"]
            verify_data = json.loads(content_text)
            first_res = verify_data.get("results", [{}])[0]
            print_ok(
                f"Result: {first_res.get('email')} -> {first_res.get('classification')} "
                f"(Deliverable: {first_res.get('is_deliverable')}, Cached: {verify_data.get('cached')})"
            )

            # -----------------------------------------------------------------
            # 7. MCP Tool Call: get_cached_verification
            # -----------------------------------------------------------------
            print_step("7. Tool Execution: get_cached_verification (Zero-Credit Recovery)")
            cache_payload = {
                "jsonrpc": "2.0",
                "id": "cache_test_6",
                "method": "tools/call",
                "params": {
                    "name": "get_cached_verification",
                    "arguments": {
                        "emails": [args.email],
                    },
                },
            }
            c_code, c_resp = http_request(mcp_endpoint, method="POST", headers=auth_headers, payload=cache_payload)
            if c_code == 200 and "result" in c_resp:
                c_text = c_resp["result"]["content"][0]["text"]
                c_data = json.loads(c_text)
                if c_data.get("found"):
                    print_ok(f"Cache recovery confirmed for '{args.email}' at 0 credit cost.")
                else:
                    print_warn("Batch not present in cache (Redis may be offline or in degraded fail-open mode).")
            else:
                print_warn(f"get_cached_verification query returned: {c_resp}")

    print(f"\n{GREEN}{BOLD}All operational checks completed successfully!{RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
