# app/mcp/tools/__init__.py
"""
MCP Tools
=========
Các tools có thể được gọi bởi AI agents.
"""

from app.mcp.tools.task_tools import (
    GetTasksTool,
    GetTasksByStatusTool,
    GetDailyReportTool,
    GetWeeklyReportTool,
    GetOverallReportTool,
    CreateTaskTool,
    UpdateTaskStatusTool,
    SetDeadlineTool,
    ExtendDeadlineTool,
    RenameTaskTool,
    CreateAndCompleteTaskTool,
)
from app.mcp.tools.birthday_tools import GetBirthdaysTool


def register_all_tools():
    """Register all tools to the global registry"""
    from app.mcp.core.tool_registry import tool_registry

    # Task tools
    tool_registry.register(GetTasksTool())
    tool_registry.register(GetTasksByStatusTool())
    tool_registry.register(GetDailyReportTool())
    tool_registry.register(GetWeeklyReportTool())
    tool_registry.register(GetOverallReportTool())
    tool_registry.register(CreateTaskTool())
    tool_registry.register(UpdateTaskStatusTool())
    tool_registry.register(SetDeadlineTool())
    tool_registry.register(ExtendDeadlineTool())
    tool_registry.register(RenameTaskTool())
    tool_registry.register(CreateAndCompleteTaskTool())

    # Birthday tools
    tool_registry.register(GetBirthdaysTool())


__all__ = [
    'GetTasksTool',
    'GetTasksByStatusTool',
    'GetDailyReportTool',
    'GetWeeklyReportTool',
    'GetOverallReportTool',
    'CreateTaskTool',
    'UpdateTaskStatusTool',
    'SetDeadlineTool',
    'ExtendDeadlineTool',
    'RenameTaskTool',
    'CreateAndCompleteTaskTool',
    'GetBirthdaysTool',
    'register_all_tools',
]
