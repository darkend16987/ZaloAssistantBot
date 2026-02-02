# app/mcp/core/mcp_server.py
"""
MCP Server
==========
Server component để expose tools theo chuẩn MCP (Model Context Protocol).
Cho phép bất kỳ MCP-compatible client nào connect và sử dụng tools.

Hỗ trợ:
- Tool discovery (list available tools)
- Tool execution
- Context management
- Session handling
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import json

from app.mcp.core.tool_registry import ToolRegistry, tool_registry
from app.mcp.core.provider_registry import ProviderRegistry, provider_registry
from app.mcp.core.base_tool import ToolResult
from app.core.logging import logger


@dataclass
class MCPRequest:
    """Incoming request from MCP client"""
    method: str  # tools/list, tools/call, etc.
    params: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None


@dataclass
class MCPResponse:
    """Response to MCP client"""
    result: Any = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        response = {"jsonrpc": "2.0", "id": self.id}
        if self.error:
            response["error"] = self.error
        else:
            response["result"] = self.result
        return response


class MCPServer:
    """
    MCP Server implementation.

    Implements core MCP protocol methods:
    - tools/list: List available tools
    - tools/call: Execute a tool

    Future extensions:
    - resources/list: List available resources
    - prompts/list: List available prompts
    - sampling: Support for sampling

    Usage:
        server = MCPServer()
        await server.initialize()

        # Handle incoming request
        response = await server.handle_request(request)

        # Or use directly
        tools = await server.list_tools()
        result = await server.call_tool("get_tasks", {"status": "DOING"})
    """

    def __init__(
        self,
        tool_registry: ToolRegistry = tool_registry,
        provider_registry: ProviderRegistry = provider_registry,
        name: str = "zalo-assistant-mcp"
    ):
        self.name = name
        self.version = "1.0.0"
        self._tool_registry = tool_registry
        self._provider_registry = provider_registry
        self._initialized = False
        self._context: Dict[str, Any] = {}
        self._handlers: Dict[str, Callable] = {}
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup method handlers"""
        self._handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "providers/list": self._handle_providers_list,
            "providers/status": self._handle_providers_status,
            "health": self._handle_health,
        }

    async def initialize(self) -> None:
        """Initialize server and all providers"""
        if self._initialized:
            return

        logger.info(f"Initializing MCP Server: {self.name}")

        # Initialize providers
        await self._provider_registry.initialize_all()

        self._initialized = True
        logger.info(f"MCP Server initialized with {len(self._tool_registry)} tools")

    async def shutdown(self) -> None:
        """Shutdown server and cleanup"""
        logger.info(f"Shutting down MCP Server: {self.name}")
        await self._provider_registry.shutdown_all()
        self._initialized = False

    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """
        Handle incoming MCP request.

        Args:
            request: MCPRequest object

        Returns:
            MCPResponse with result or error
        """
        handler = self._handlers.get(request.method)
        if not handler:
            return MCPResponse(
                id=request.id,
                error={
                    "code": -32601,
                    "message": f"Method not found: {request.method}"
                }
            )

        try:
            result = await handler(request.params)
            return MCPResponse(id=request.id, result=result)
        except Exception as e:
            logger.error(f"Error handling request {request.method}: {e}")
            return MCPResponse(
                id=request.id,
                error={
                    "code": -32000,
                    "message": str(e)
                }
            )

    async def _handle_initialize(self, params: Dict) -> Dict:
        """Handle initialize request"""
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": self.name,
                "version": self.version
            },
            "capabilities": {
                "tools": {"listChanged": True},
                "providers": True
            }
        }

    async def _handle_tools_list(self, params: Dict) -> Dict:
        """Handle tools/list request"""
        tools = self._tool_registry.to_mcp_tools()
        return {"tools": tools}

    async def _handle_tools_call(self, params: Dict) -> Dict:
        """Handle tools/call request"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not tool_name:
            raise ValueError("Tool name is required")

        result = await self._tool_registry.execute(tool_name, **arguments)

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result.to_dict(), ensure_ascii=False)
                }
            ],
            "isError": not result.success
        }

    async def _handle_providers_list(self, params: Dict) -> Dict:
        """Handle providers/list request"""
        providers = []
        for provider in self._provider_registry.get_all():
            providers.append({
                "name": provider.name,
                "status": provider.status.value,
                "available": provider.is_available
            })
        return {"providers": providers}

    async def _handle_providers_status(self, params: Dict) -> Dict:
        """Handle providers/status request"""
        statuses = await self._provider_registry.health_check_all()
        return {
            "statuses": {name: status.value for name, status in statuses.items()}
        }

    async def _handle_health(self, params: Dict) -> Dict:
        """Handle health check request"""
        provider_statuses = await self._provider_registry.health_check_all()
        healthy_count = sum(1 for s in provider_statuses.values() if s.value == "healthy")

        return {
            "status": "healthy" if healthy_count == len(provider_statuses) else "degraded",
            "tools_count": len(self._tool_registry),
            "providers": {name: s.value for name, s in provider_statuses.items()}
        }

    # --- Convenience methods ---

    async def list_tools(self) -> List[Dict]:
        """List all available tools"""
        result = await self._handle_tools_list({})
        return result["tools"]

    async def call_tool(self, name: str, arguments: Dict = None) -> ToolResult:
        """
        Call a tool directly.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            ToolResult from tool execution
        """
        return await self._tool_registry.execute(name, **(arguments or {}))

    def get_tool_schemas(self) -> List[Dict]:
        """Get tool schemas for LLM function calling"""
        return self._tool_registry.to_gemini_tools()

    def set_context(self, key: str, value: Any) -> None:
        """Set context value for tools"""
        self._context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get context value"""
        return self._context.get(key, default)

    @property
    def is_initialized(self) -> bool:
        return self._initialized


# Global MCP server instance
mcp_server = MCPServer()
