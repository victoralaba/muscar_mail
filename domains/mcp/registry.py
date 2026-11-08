from typing import Dict, List, Optional
from domains.mcp.protocol import Tool


class ToolRegistry:
    """Registry maintaining the formal tool catalog and JSON schemas for MCP tools/list."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Registers the 3 core muscar_mail email verification tools."""
        self.register(
            Tool(
                name="verify_emails",
                description=(
                    "Validates a batch of 1 to 25 email addresses synchronously using Verifalia v2.4 API. "
                    "Automatically checks zero-credit cache first to recover results at 0 credit cost and "
                    "enforces daily free-tier quota limits (resetting at 00:00:00 UTC)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "emails": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "maxItems": 25,
                            "description": "List of 1 to 25 email addresses to verify.",
                        }
                    },
                    "required": ["emails"],
                },
            )
        )

        self.register(
            Tool(
                name="get_cached_verification",
                description=(
                    "Retrieves previously cached verification results for a batch of emails at zero credit cost "
                    "without contacting Verifalia. Returns null if batch is not cached."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "emails": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "maxItems": 25,
                            "description": "List of email addresses previously verified.",
                        }
                    },
                    "required": ["emails"],
                },
            )
        )

        self.register(
            Tool(
                name="get_credit_balance",
                description=(
                    "Queries current Verifalia credit balance (paid credit packs and free daily credits) "
                    "and returns the exact ISO 8601 UTC reset schedule (00:00:00 UTC)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            )
        )

    def register(self, tool: Tool) -> None:
        """Registers a tool in the catalog."""
        self._tools[tool.name] = tool

    def get_tools(self) -> List[Tool]:
        """Returns all registered tool definitions."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Optional[Tool]:
        """Returns a registered tool by name or None."""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Checks if a tool is registered."""
        return name in self._tools


# Global singleton instance
tool_registry = ToolRegistry()
