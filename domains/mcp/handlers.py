import json
from typing import Any, Dict, List, Optional
from core.config import get_settings
from core.logging import get_logger
from domains.mcp.protocol import (
    InitializeResult,
    JSONRPCError,
    JSONRPCErrorCode,
    JSONRPCRequest,
    JSONRPCResponse,
    ServerInfo,
    TextContent,
    ToolCallResult,
    ToolsListResult,
)
from domains.mcp.registry import ToolRegistry, tool_registry
from domains.verification.cache import VerificationCache, verification_cache
from domains.verification.service import VerifaliaService, verifalia_service
from shared.exceptions import (
    AuthenticationError,
    BatchLimitExceededError,
    InsufficientCreditsError,
    MuscarMailError,
    UpstreamProviderError,
    UpstreamTimeoutError,
)

logger = get_logger("muscar_mail.mcp")


class MCPHandler:
    """Dispatches JSON-RPC 2.0 requests to corresponding MCP lifecycle and tool handlers.

    Enforces Invariants:
    - INV-MCP-STATE: Fully stateless execution over HTTP.
    - INV-MCP-ERR: Deterministic JSON-RPC 2.0 error mapping (-32700 .. -32603, -32002).
    - INV-MCP-TOKEN: Distilled, token-efficient JSON output wrapped in TextContent envelopes.
    - INV-MCP-BATCH: Hard boundary enforcement (1 <= N <= 25) before upstream dispatch.
    """

    def __init__(
        self,
        service: Optional[VerifaliaService] = None,
        cache: Optional[VerificationCache] = None,
        registry: Optional[ToolRegistry] = None,
    ):
        self._custom_service = service
        self._custom_cache = cache
        self._custom_registry = registry

    @property
    def _service(self) -> VerifaliaService:
        return self._custom_service or verifalia_service

    @property
    def _cache(self) -> VerificationCache:
        return self._custom_cache or verification_cache

    @property
    def _registry(self) -> ToolRegistry:
        return self._custom_registry or tool_registry

    async def handle_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """Top-level dispatcher routing incoming JSON-RPC methods."""
        req_id = request.id

        try:
            method = request.method
            params = request.params or {}

            if method == "initialize":
                res_or_err = self._handle_initialize(params)
                if isinstance(res_or_err, JSONRPCError):
                    return JSONRPCResponse(id=req_id, error=res_or_err)
                return JSONRPCResponse(id=req_id, result=res_or_err)

            elif method in ("server/discover", "discover"):
                settings = get_settings()
                return JSONRPCResponse(
                    id=req_id,
                    result={
                        "serverInfo": {
                            "name": settings.MCP_SERVER_NAME,
                            "version": settings.MCP_SERVER_VERSION,
                        },
                        "supportedProtocolVersions": settings.SUPPORTED_MCP_PROTOCOL_VERSIONS,
                        "protocolVersion": settings.MCP_PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                    },
                )

            elif method == "notifications/initialized":
                # Notification ack
                return JSONRPCResponse(id=req_id, result={})

            elif method == "ping":
                return JSONRPCResponse(id=req_id, result={})

            elif method == "tools/list":
                result = self._handle_tools_list()
                return JSONRPCResponse(id=req_id, result=result)

            elif method == "tools/call":
                tool_result = await self._handle_tool_call(params)
                return JSONRPCResponse(id=req_id, result=tool_result.model_dump())

            else:
                return JSONRPCResponse(
                    id=req_id,
                    error=JSONRPCError(
                        code=JSONRPCErrorCode.METHOD_NOT_FOUND,
                        message=f"Method '{method}' not found.",
                    ),
                )

        except Exception as exc:
            logger.error("Unhandled exception processing MCP request.", method=request.method, error=str(exc))
            return JSONRPCResponse(
                id=req_id,
                error=JSONRPCError(
                    code=JSONRPCErrorCode.INTERNAL_ERROR,
                    message=f"Internal server error: {str(exc)}",
                ),
            )

    def _handle_initialize(self, params: Dict[str, Any]) -> Union[Dict[str, Any], JSONRPCError]:
        """Handles initialize handshake negotiating protocol version and returning capabilities."""
        settings = get_settings()
        client_version = params.get("protocolVersion")

        # Negotiate protocol version dynamically
        if client_version:
            if client_version in settings.SUPPORTED_MCP_PROTOCOL_VERSIONS:
                negotiated_version = client_version
            else:
                return JSONRPCError(
                    code=JSONRPCErrorCode.UNSUPPORTED_PROTOCOL_VERSION,
                    message="Unsupported protocol version",
                    data={
                        "supported": settings.SUPPORTED_MCP_PROTOCOL_VERSIONS,
                        "requested": client_version,
                    },
                )
        else:
            # Default to latest version if omitted by client
            negotiated_version = settings.MCP_PROTOCOL_VERSION

        res = InitializeResult(
            protocolVersion=negotiated_version,
            capabilities={"tools": {}},
            serverInfo=ServerInfo(
                name=settings.MCP_SERVER_NAME,
                version=settings.MCP_SERVER_VERSION,
            ),
        )
        return res.model_dump()

    def _handle_tools_list(self) -> Dict[str, Any]:
        """Handles tools/list returning the registered tool catalog."""
        res = ToolsListResult(tools=self._registry.get_tools())
        return res.model_dump()

    async def _handle_tool_call(self, params: Dict[str, Any]) -> ToolCallResult:
        """Validates and executes an MCP tool call."""
        name = params.get("name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}

        if not isinstance(name, str) or not self._registry.has_tool(name):
            valid_tools = ", ".join(t.name for t in self._registry.get_tools())
            return ToolCallResult(
                content=[TextContent(text=f"Unknown tool '{name}'. Registered tools: {valid_tools}")],
                isError=True,
            )

        if not isinstance(arguments, dict):
            return ToolCallResult(
                content=[TextContent(text="Invalid parameters: 'arguments' must be a JSON object.")],
                isError=True,
            )

        # Dispatch based on tool name
        if name == "verify_emails":
            return await self._call_verify_emails(arguments)
        elif name == "get_cached_verification":
            return await self._call_get_cached_verification(arguments)
        elif name == "get_credit_balance":
            return await self._call_get_credit_balance()
        else:
            return ToolCallResult(
                content=[TextContent(text=f"Handler for tool '{name}' is not implemented.")],
                isError=True,
            )

    async def _call_verify_emails(self, arguments: Dict[str, Any]) -> ToolCallResult:
        """Executes the verify_emails tool with boundary validation and zero-credit cache checks."""
        emails_param = arguments.get("emails")

        if not isinstance(emails_param, list):
            return ToolCallResult(
                content=[TextContent(text="Invalid parameters: 'emails' must be an array of strings.")],
                isError=True,
            )

        if len(emails_param) == 0:
            return ToolCallResult(
                content=[TextContent(text="Invalid parameters: 'emails' array cannot be empty.")],
                isError=True,
            )

        if len(emails_param) > 25:
            return ToolCallResult(
                content=[
                    TextContent(
                        text=f"Batch size of {len(emails_param)} exceeds maximum allowed limit of 25 emails per request."
                    )
                ],
                isError=True,
            )

        # Validate entries are valid non-empty strings
        cleaned_emails: List[str] = []
        for idx, item in enumerate(emails_param):
            if not isinstance(item, str) or not item.strip():
                return ToolCallResult(
                    content=[TextContent(text=f"Invalid email at index {idx}: must be a non-empty string.")],
                    isError=True,
                )
            cleaned_emails.append(item.strip())

        # 1. Zero-credit cache recovery check
        cached_result = await self._cache.get_cached_batch(cleaned_emails)
        if cached_result is not None:
            return ToolCallResult(
                content=[TextContent(text=cached_result.model_dump_json(indent=2))],
                isError=False,
            )

        # 2. Daily quota boundary check (Safe deduplication canonical count)
        canonical_count = len(VerificationCache.get_canonical_emails(cleaned_emails))
        if not await self._cache.is_daily_quota_available(canonical_count):
            return ToolCallResult(
                content=[
                    TextContent(
                        text=(
                            "Daily verification quota reached (max 25 credits/day). "
                            "Resets automatically at 00:00:00 UTC."
                        )
                    )
                ],
                isError=True,
            )

        # 3. Synchronous upstream verification call
        try:
            result = await self._service.verify_emails(emails=cleaned_emails)
            # 4. Cache persistence & quota tracking
            await self._cache.cache_batch(emails=cleaned_emails, response=result)
            await self._cache.increment_daily_quota(amount=canonical_count)

            return ToolCallResult(
                content=[TextContent(text=result.model_dump_json(indent=2))],
                isError=False,
            )

        except AuthenticationError as exc:
            return ToolCallResult(
                content=[TextContent(text=f"Upstream authentication failed: {exc.message}")],
                isError=True,
            )
        except InsufficientCreditsError as exc:
            return ToolCallResult(
                content=[TextContent(text=f"Verification failed: {exc.message}")],
                isError=True,
            )
        except UpstreamTimeoutError as exc:
            return ToolCallResult(
                content=[TextContent(text=f"Verification timed out: {exc.message}")],
                isError=True,
            )
        except UpstreamProviderError as exc:
            return ToolCallResult(
                content=[TextContent(text=f"Upstream provider error: {exc.message}")],
                isError=True,
            )
        except Exception as exc:
            logger.error("Unexpected error during verify_emails tool execution.", error=str(exc))
            return ToolCallResult(
                content=[TextContent(text=f"Internal error executing verify_emails: {str(exc)}")],
                isError=True,
            )

    async def _call_get_cached_verification(self, arguments: Dict[str, Any]) -> ToolCallResult:
        """Executes get_cached_verification tool at zero credit cost."""
        emails_param = arguments.get("emails")

        if not isinstance(emails_param, list):
            return ToolCallResult(
                content=[TextContent(text="Invalid parameters: 'emails' must be an array of strings.")],
                isError=True,
            )

        if len(emails_param) == 0:
            return ToolCallResult(
                content=[TextContent(text="Invalid parameters: 'emails' array cannot be empty.")],
                isError=True,
            )

        if len(emails_param) > 25:
            return ToolCallResult(
                content=[
                    TextContent(
                        text=f"Batch size of {len(emails_param)} exceeds maximum allowed limit of 25 emails per request."
                    )
                ],
                isError=True,
            )

        cleaned_emails: List[str] = []
        for idx, item in enumerate(emails_param):
            if not isinstance(item, str) or not item.strip():
                return ToolCallResult(
                    content=[TextContent(text=f"Invalid email at index {idx}: must be a non-empty string.")],
                    isError=True,
                )
            cleaned_emails.append(item.strip())

        cached_result = await self._cache.get_cached_batch(cleaned_emails)

        if cached_result is not None:
            return ToolCallResult(
                content=[TextContent(text=cached_result.model_dump_json(indent=2))],
                isError=False,
            )
        else:
            return ToolCallResult(
                content=[TextContent(text="null")],
                isError=False,
            )

    async def _call_get_credit_balance(self) -> ToolCallResult:
        """Executes get_credit_balance tool."""
        try:
            balance = await self._service.get_credit_balance()
            return ToolCallResult(
                content=[TextContent(text=balance.model_dump_json(indent=2))],
                isError=False,
            )
        except Exception as exc:
            logger.error("Failed to query credit balance for MCP tool.", error=str(exc))
            return ToolCallResult(
                content=[TextContent(text=f"Failed to query credit balance: {str(exc)}")],
                isError=True,
            )


# Global singleton instance
mcp_handler = MCPHandler()
