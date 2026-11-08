import json
from typing import Any, Dict, List, Union
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from core.logging import get_logger
from domains.mcp.handlers import MCPHandler, mcp_handler
from domains.mcp.protocol import (
    JSONRPCError,
    JSONRPCErrorCode,
    JSONRPCRequest,
    JSONRPCResponse,
)
from shared.security import verify_mcp_api_key

logger = get_logger("muscar_mail.mcp.routes")

router = APIRouter(prefix="/mcp/v1", tags=["mcp"])


def get_mcp_handler() -> MCPHandler:
    """Dependency provider returning singleton MCPHandler instance."""
    return mcp_handler


@router.post(
    "",
    response_model=Union[JSONRPCResponse, List[JSONRPCResponse]],
    include_in_schema=False,
)
@router.post(
    "/",
    response_model=Union[JSONRPCResponse, List[JSONRPCResponse]],
    status_code=status.HTTP_200_OK,
    summary="Stateless MCP JSON-RPC 2.0 endpoint",
    description=(
        "Executes stateless Model Context Protocol (MCP) JSON-RPC 2.0 operations over pure HTTP. "
        "Supports initialize, ping, tools/list, and tools/call."
    ),
)
async def mcp_endpoint(
    request: Request,
    api_key: str = Depends(verify_mcp_api_key),
    handler: MCPHandler = Depends(get_mcp_handler),
) -> Union[JSONRPCResponse, List[JSONRPCResponse]]:
    """Receives and dispatches stateless JSON-RPC 2.0 requests with strict error mapping."""
    raw_body = await request.body()

    # 1. Parse JSON syntax (Invariant INV-MCP-ERR: -32700 Parse Error)
    try:
        raw_data = json.loads(raw_body)
    except Exception as exc:
        logger.warning("JSON-RPC parse error on incoming payload.", error=str(exc))
        return JSONRPCResponse(
            id=None,
            error=JSONRPCError(
                code=JSONRPCErrorCode.PARSE_ERROR,
                message="Parse error: Invalid JSON syntax.",
            ),
        )

    # 2. Handle batch JSON-RPC request if passed as array
    if isinstance(raw_data, list):
        if not raw_data:
            return JSONRPCResponse(
                id=None,
                error=JSONRPCError(
                    code=JSONRPCErrorCode.INVALID_REQUEST,
                    message="Invalid Request: Batch request cannot be empty.",
                ),
            )
        batch_responses: List[JSONRPCResponse] = []
        for item in raw_data:
            resp = await _process_single_rpc_item(item, handler)
            batch_responses.append(resp)
        return batch_responses

    # 3. Handle single JSON-RPC request
    return await _process_single_rpc_item(raw_data, handler)


async def _process_single_rpc_item(item: Any, handler: MCPHandler) -> JSONRPCResponse:
    """Validates and dispatches a single JSON-RPC request object."""
    if not isinstance(item, dict):
        return JSONRPCResponse(
            id=None,
            error=JSONRPCError(
                code=JSONRPCErrorCode.INVALID_REQUEST,
                message="Invalid Request: Top-level payload must be a JSON object.",
            ),
        )

    req_id = item.get("id")
    # Sanitize id per JSON-RPC 2.0: id must be string, integer, or null if detection failed
    valid_id = req_id if (isinstance(req_id, (str, int)) and not isinstance(req_id, bool)) else None

    # Validate JSON-RPC 2.0 structure
    try:
        rpc_request = JSONRPCRequest.model_validate(item)
    except Exception as exc:
        logger.warning("Invalid JSON-RPC request structure.", error=str(exc), payload=item)
        return JSONRPCResponse(
            id=valid_id,
            error=JSONRPCError(
                code=JSONRPCErrorCode.INVALID_REQUEST,
                message=f"Invalid Request: Malformed JSON-RPC 2.0 request: {str(exc)}",
            ),
        )

    return await handler.handle_request(rpc_request)
