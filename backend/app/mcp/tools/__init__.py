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
from app.mcp.tools.knowledge_tools import SearchRegulationsTool, ListRegulationsTool
from app.mcp.tools.yearly_schedule_tools import (
    GetYearlyScheduleTool,
    GetYearlyTaskDetailTool,
    ConfirmYearlyTaskTool,
    SkipYearlyTaskTool,
    CompleteYearlyTaskTool,
)


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

    # Knowledge tools
    tool_registry.register(SearchRegulationsTool())
    tool_registry.register(ListRegulationsTool())

    # Yearly schedule tools
    tool_registry.register(GetYearlyScheduleTool())
    tool_registry.register(GetYearlyTaskDetailTool())
    tool_registry.register(ConfirmYearlyTaskTool())
    tool_registry.register(SkipYearlyTaskTool())
    tool_registry.register(CompleteYearlyTaskTool())


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
    'SearchRegulationsTool',
    'ListRegulationsTool',
    'GetYearlyScheduleTool',
    'GetYearlyTaskDetailTool',
    'ConfirmYearlyTaskTool',
    'SkipYearlyTaskTool',
    'CompleteYearlyTaskTool',
    'register_all_tools',
]
