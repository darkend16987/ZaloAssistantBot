# app/mcp/tools/birthday_tools.py
"""
Birthday Tools
==============
MCP tools cho việc quản lý thông tin sinh nhật.
"""

from typing import List, Optional

from app.mcp.core.base_tool import BaseTool, ToolParameter, ToolResult, ParameterType
from app.mcp.core.provider_registry import provider_registry
from app.mcp.providers.birthday_provider import BirthdayProvider
from app.core.logging import logger


def get_birthday_provider() -> BirthdayProvider:
    """Get Birthday provider from registry"""
    provider = provider_registry.get("birthday")
    if not provider:
        raise RuntimeError("Birthday provider not initialized")
    return provider


class GetBirthdaysTool(BaseTool):
    """Tool để lấy thông tin sinh nhật"""

    @property
    def name(self) -> str:
        return "get_birthdays"

    @property
    def description(self) -> str:
        return """Lấy danh sách sinh nhật của nhân viên trong tuần này hoặc tuần sau.
Sử dụng khi người dùng hỏi: "sinh nhật tuần này", "ai sinh nhật tuần sau", "birthday"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="week",
                type=ParameterType.STRING,
                description="Tuần cần xem: 'this' (tuần này) hoặc 'next' (tuần sau)",
                required=False,
                default="next",
                enum=["this", "next"]
            )
        ]

    @property
    def category(self) -> str:
        return "birthdays"

    async def execute(
        self,
        week: str = "next",
        **kwargs
    ) -> ToolResult:
        try:
            provider = get_birthday_provider()

            birthday_data = await provider.get_birthdays(week=week)

            if not birthday_data or birthday_data.get('error'):
                error_msg = birthday_data.get('error', 'Unknown error') if birthday_data else 'Connection failed'
                return ToolResult(
                    success=False,
                    error=f"Không thể lấy dữ liệu sinh nhật: {error_msg}"
                )

            employees = birthday_data.get('employees', [])

            if not employees:
                week_label = "tuần này" if week == "this" else "tuần sau"
                return ToolResult(
                    success=True,
                    data=f"Không có ai sinh nhật trong {week_label}.",
                    metadata={"count": 0, "week": week}
                )

            # Get combined message
            message = provider.get_combined_birthday_message(birthday_data, week)

            return ToolResult(
                success=True,
                data=message,
                metadata={
                    "count": len(employees),
                    "week": week,
                    "employees": [e.get('name') for e in employees]
                }
            )

        except Exception as e:
            logger.error(f"GetBirthdaysTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
