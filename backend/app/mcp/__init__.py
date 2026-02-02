# app/mcp/__init__.py
"""
MCP (Model Context Protocol) Module
===================================
Hệ thống MCP cho phép AI agents tự động discover và gọi các tools
một cách có cấu trúc, thay vì hardcode intent mapping.

Components:
- ToolRegistry: Quản lý và expose các tools
- ProviderRegistry: Quản lý các data providers (APIs, databases, RAG)
- AgentOrchestrator: Điều phối việc xử lý requests
- PromptManager: Quản lý system prompts có version control
"""

from app.mcp.core.tool_registry import ToolRegistry, tool_registry
from app.mcp.core.provider_registry import ProviderRegistry, provider_registry
from app.mcp.core.agent import AgentOrchestrator

__all__ = [
    'ToolRegistry',
    'tool_registry',
    'ProviderRegistry',
    'provider_registry',
    'AgentOrchestrator',
]
