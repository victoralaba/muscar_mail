from enum import IntEnum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class JSONRPCErrorCode(IntEnum):
    """Standard JSON-RPC 2.0 error codes and muscar_mail domain extensions."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    INSUFFICIENT_CREDITS = -32002
    UNSUPPORTED_PROTOCOL_VERSION = -32022


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int = Field(..., description="A Number that indicates the error type that occurred.")
    message: str = Field(..., description="A Short description of the error.")
    data: Optional[Any] = Field(default=None, description="Additional structured information about the error.")

    model_config = ConfigDict(extra="ignore")


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 request payload."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: Optional[Union[StrictStr, StrictInt]] = Field(
        default=None,
        description="An identifier established by the Client. Omitted for notifications.",
    )
    method: str = Field(..., description="The name of the method to be invoked.")
    params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="A Structured value that holds the parameter values to be used during the invocation.",
    )

    model_config = ConfigDict(extra="ignore")


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 response payload."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: Optional[Union[StrictStr, StrictInt]] = Field(
        default=None,
        description="Matches the id of the request. Must be null if error occurred before id could be determined.",
    )
    result: Optional[Any] = Field(default=None, description="The result of the method invocation upon success.")
    error: Optional[JSONRPCError] = Field(default=None, description="Error object if method invocation failed.")

    model_config = ConfigDict(extra="ignore")


# -----------------------------------------------------------------------------
# MCP Content & Capability Models (Specification Version: 2024-11-05)
# -----------------------------------------------------------------------------

class TextContent(BaseModel):
    """MCP Text Content payload."""

    type: Literal["text"] = "text"
    text: str = Field(..., description="Text content payload.")

    model_config = ConfigDict(extra="ignore")


class ToolCallResult(BaseModel):
    """MCP tool execution response format."""

    content: List[TextContent] = Field(
        default_factory=list,
        description="List of content elements returned by the tool.",
    )
    isError: bool = Field(
        default=False,
        description="True if the tool execution resulted in an operational/domain failure.",
    )

    model_config = ConfigDict(extra="ignore")


class Tool(BaseModel):
    """MCP Tool definition exposed in tools/list."""

    name: str = Field(..., description="Unique tool identifier.")
    description: str = Field(..., description="Human- and LLM-readable purpose of the tool.")
    inputSchema: Dict[str, Any] = Field(..., description="JSON Schema object describing required parameters.")

    model_config = ConfigDict(extra="ignore")


class ToolsListResult(BaseModel):
    """Result payload for tools/list."""

    tools: List[Tool] = Field(..., description="List of registered MCP tools.")

    model_config = ConfigDict(extra="ignore")


class ServerInfo(BaseModel):
    """Server identity information."""

    name: str = Field(..., description="Name of the MCP server.")
    version: str = Field(..., description="Version of the MCP server.")

    model_config = ConfigDict(extra="ignore")


class InitializeResult(BaseModel):
    """Result payload for the MCP initialize handshake."""

    protocolVersion: str = Field(default="2024-11-05", description="Supported MCP protocol version.")
    capabilities: Dict[str, Any] = Field(
        default_factory=lambda: {"tools": {}},
        description="Server capability declarations.",
    )
    serverInfo: ServerInfo = Field(..., description="Server identity information.")

    model_config = ConfigDict(extra="ignore")
