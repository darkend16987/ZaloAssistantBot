# app/mcp/core/tool_registry.py
"""
Tool Registry
=============
Central registry để quản lý tất cả MCP tools.
Tools được đăng ký tại đây và có thể được discover bởi LLM.

Features:
- Dynamic tool registration
- Category-based grouping
- Export to Gemini/MCP format
- Tool discovery for agents
"""

from typing import Dict, List, Optional, Type, Callable, Any
from app.mcp.core.base_tool import BaseTool, ToolResult
from app.core.logging import logger


class ToolRegistry:
    """
    Central registry cho MCP tools.

    Usage:
        # Register a tool class
        tool_registry.register(GetTasksTool())

        # Or use decorator
        @tool_registry.tool
        class CreateTaskTool(BaseTool):
            ...

        # Get tool by name
        tool = tool_registry.get("get_tasks")

        # Execute tool
        result = await tool_registry.execute("get_tasks", status="DOING")

        # Get all tools for Gemini
        gemini_tools = tool_registry.to_gemini_tools()
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._categories: Dict[str, List[str]] = {}
        self._enabled_tools: set = set()

    def register(self, tool: BaseTool, enabled: bool = True) -> None:
        """
        Register a tool instance.

        Args:
            tool: BaseTool instance to register
            enabled: Whether tool is enabled by default
        """
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' is being re-registered")

        self._tools[tool.name] = tool

        # Add to category
        category = tool.category
        if category not in self._categories:
            self._categories[category] = []
        if tool.name not in self._categories[category]:
            self._categories[category].append(tool.name)

        # Enable/disable
        if enabled:
            self._enabled_tools.add(tool.name)

        logger.info(f"Registered tool: {tool.name} [category={category}]")

    def tool(self, cls: Type[BaseTool]) -> Type[BaseTool]:
        """
        Decorator để register tool class.

        Usage:
            @tool_registry.tool
            class MyTool(BaseTool):
                ...
        """
        instance = cls()
        self.register(instance)
        return cls

    def unregister(self, tool_name: str) -> bool:
        """Remove a tool from registry"""
        if tool_name in self._tools:
            tool = self._tools.pop(tool_name)
            self._enabled_tools.discard(tool_name)
            if tool.category in self._categories:
                self._categories[tool.category] = [
                    t for t in self._categories[tool.category]
                    if t != tool_name
                ]
            logger.info(f"Unregistered tool: {tool_name}")
            return True
        return False

    def get(self, tool_name: str) -> Optional[BaseTool]:
        """Get tool by name"""
        return self._tools.get(tool_name)

    def get_all(self, enabled_only: bool = True) -> List[BaseTool]:
        """Get all registered tools"""
        if enabled_only:
            return [t for t in self._tools.values() if t.name in self._enabled_tools]
        return list(self._tools.values())

    def get_by_category(self, category: str) -> List[BaseTool]:
        """Get tools by category"""
        tool_names = self._categories.get(category, [])
        return [self._tools[name] for name in tool_names if name in self._tools]

    def enable(self, tool_name: str) -> bool:
        """Enable a tool"""
        if tool_name in self._tools:
            self._enabled_tools.add(tool_name)
            return True
        return False

    def disable(self, tool_name: str) -> bool:
        """Disable a tool"""
        self._enabled_tools.discard(tool_name)
        return tool_name in self._tools

    def is_enabled(self, tool_name: str) -> bool:
        """Check if tool is enabled"""
        return tool_name in self._enabled_tools

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            **kwargs: Parameters to pass to the tool

        Returns:
            ToolResult from tool execution
        """
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found"
            )

        if not self.is_enabled(tool_name):
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' is disabled"
            )

        logger.debug(f"Executing tool: {tool_name} with params: {kwargs}")
        result = await tool.safe_execute(**kwargs)
        logger.debug(f"Tool result: success={result.success}")

        return result

    def to_gemini_tools(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """
        Export all tools in Gemini function calling format.

        Returns:
            List of function definitions for Gemini API
        """
        tools = self.get_all(enabled_only=enabled_only)
        return [tool.to_gemini_function() for tool in tools]

    def to_mcp_tools(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """
        Export all tools in MCP schema format.

        Returns:
            List of tool definitions in MCP format
        """
        tools = self.get_all(enabled_only=enabled_only)
        return [tool.to_mcp_schema() for tool in tools]

    def get_tool_descriptions(self) -> str:
        """
        Generate human-readable descriptions of all tools.
        Useful for including in system prompts.
        """
        lines = ["Available tools:"]
        for tool in self.get_all():
            params = ", ".join([p.name for p in tool.parameters])
            lines.append(f"- {tool.name}({params}): {tool.description}")
        return "\n".join(lines)

    @property
    def categories(self) -> List[str]:
        """List all tool categories"""
        return list(self._categories.keys())

    @property
    def count(self) -> int:
        """Number of registered tools"""
        return len(self._tools)

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def __len__(self) -> int:
        return self.count

    def __repr__(self) -> str:
        return f"<ToolRegistry: {self.count} tools, {len(self.categories)} categories>"


# Global singleton instance
tool_registry = ToolRegistry()
