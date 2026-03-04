# app/mcp/tools/yearly_schedule_tools.py
"""
Yearly Schedule Tools
=====================
MCP tools cho việc quản lý lịch công việc theo năm.
"""

from typing import List, Optional
from app.mcp.core.base_tool import BaseTool, ToolParameter, ToolResult, ParameterType
from app.mcp.core.provider_registry import provider_registry
from app.mcp.providers.yearly_schedule_provider import YearlyScheduleProvider
from app.core.logging import logger


def get_yearly_provider() -> YearlyScheduleProvider:
    """Get YearlySchedule provider from registry"""
    provider = provider_registry.get("yearly_schedule")
    if not provider:
        raise RuntimeError("YearlySchedule provider not initialized")
    return provider


class GetYearlyScheduleTool(BaseTool):
    """Tool để xem lịch công việc theo năm"""

    @property
    def name(self) -> str:
        return "get_yearly_schedule"

    @property
    def description(self) -> str:
        return """Xem tổng quan lịch công việc theo năm hoặc các việc sắp tới.
Sử dụng khi người dùng hỏi: "lịch năm nay", "công việc theo quý", "lịch công việc năm",
"có việc gì sắp tới theo lịch không", "xem lịch yearly", "lịch Q1", "lịch quý"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="view",
                type=ParameterType.STRING,
                description="Chế độ xem: 'overview' (tổng quan cả năm), 'upcoming' (việc sắp tới), 'anchors' (các mốc thời gian)",
                required=False,
                enum=["overview", "upcoming", "anchors"]
            ),
            ToolParameter(
                name="days",
                type=ParameterType.INTEGER,
                description="Số ngày tới để tìm việc (chỉ dùng với view=upcoming, mặc định 14)",
                required=False,
            ),
        ]

    @property
    def category(self) -> str:
        return "yearly_schedule"

    async def execute(self, view: str = "upcoming", days: int = 14, **kwargs) -> ToolResult:
        try:
            provider = get_yearly_provider()

            if view == "overview":
                data = provider.get_schedule_overview()
            elif view == "anchors":
                data = provider.get_available_anchors()
            else:
                days = int(days) if days else 14
                data = provider.get_upcoming_formatted(days=days)

            return ToolResult(success=True, data=data)

        except Exception as e:
            logger.error(f"GetYearlyScheduleTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class GetYearlyTaskDetailTool(BaseTool):
    """Tool để xem chi tiết một yearly task"""

    @property
    def name(self) -> str:
        return "get_yearly_task_detail"

    @property
    def description(self) -> str:
        return """Xem chi tiết một công việc trong lịch năm.
Sử dụng khi người dùng hỏi về chi tiết một yearly task cụ thể, ví dụ: "xem chi tiết Q1-002"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="task_id",
                type=ParameterType.STRING,
                description="ID của yearly task (ví dụ: Q1-001, Q2-003)",
                required=True,
            ),
        ]

    @property
    def category(self) -> str:
        return "yearly_schedule"

    async def execute(self, task_id: str, **kwargs) -> ToolResult:
        try:
            provider = get_yearly_provider()
            data = provider.get_task_detail_formatted(task_id)
            return ToolResult(success=True, data=data)

        except Exception as e:
            logger.error(f"GetYearlyTaskDetailTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class ConfirmYearlyTaskTool(BaseTool):
    """Tool để xác nhận tạo yearly task lên 1Office"""

    @property
    def name(self) -> str:
        return "confirm_yearly_task"

    @property
    def description(self) -> str:
        return """Xác nhận và tạo một công việc theo lịch năm lên hệ thống 1Office.
Sử dụng khi người dùng xác nhận muốn tạo một yearly task, ví dụ:
"xác nhận tạo Q1-002", "tạo yearly task Q1-001", "xác nhận", "tạo đi".

Nếu user nói "xác nhận" mà không nêu ID, hãy tìm trong lịch sử hội thoại
xem yearly task nào đang chờ xác nhận."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="task_id",
                type=ParameterType.STRING,
                description="ID của yearly task cần tạo (ví dụ: Q1-001, Q2-003)",
                required=True,
            ),
        ]

    @property
    def category(self) -> str:
        return "yearly_schedule"

    async def execute(self, task_id: str, **kwargs) -> ToolResult:
        try:
            provider = get_yearly_provider()
            result = await provider.confirm_and_create_task(task_id)

            if result["success"]:
                return ToolResult(
                    success=True,
                    data=f"✅ {result['message']}",
                    metadata={
                        "yearly_task_id": task_id,
                        "oneoffice_task_id": result.get("oneoffice_task_id"),
                    }
                )
            else:
                return ToolResult(success=False, error=result["message"])

        except Exception as e:
            logger.error(f"ConfirmYearlyTaskTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class SkipYearlyTaskTool(BaseTool):
    """Tool để bỏ qua yearly task"""

    @property
    def name(self) -> str:
        return "skip_yearly_task"

    @property
    def description(self) -> str:
        return """Bỏ qua một công việc trong lịch năm, không tạo trên 1Office.
Sử dụng khi người dùng nói: "bỏ qua Q1-002", "skip yearly task", "không tạo"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="task_id",
                type=ParameterType.STRING,
                description="ID của yearly task cần bỏ qua (ví dụ: Q1-001)",
                required=True,
            ),
        ]

    @property
    def category(self) -> str:
        return "yearly_schedule"

    async def execute(self, task_id: str, **kwargs) -> ToolResult:
        try:
            provider = get_yearly_provider()
            result = provider.skip_task(task_id)

            if result["success"]:
                return ToolResult(
                    success=True,
                    data=f"⏭️ {result['message']}",
                    metadata={"yearly_task_id": task_id}
                )
            else:
                return ToolResult(success=False, error=result["message"])

        except Exception as e:
            logger.error(f"SkipYearlyTaskTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class CompleteYearlyTaskTool(BaseTool):
    """Tool để đánh dấu yearly task đã hoàn thành"""

    @property
    def name(self) -> str:
        return "complete_yearly_task"

    @property
    def description(self) -> str:
        return """Đánh dấu một công việc theo lịch năm đã hoàn thành.
Sử dụng khi người dùng nói yearly task đã xong: "Q1-002 đã xong", "hoàn thành yearly task"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="task_id",
                type=ParameterType.STRING,
                description="ID của yearly task (ví dụ: Q1-001)",
                required=True,
            ),
        ]

    @property
    def category(self) -> str:
        return "yearly_schedule"

    async def execute(self, task_id: str, **kwargs) -> ToolResult:
        try:
            provider = get_yearly_provider()
            result = provider.mark_task_completed(task_id)

            if result["success"]:
                return ToolResult(
                    success=True,
                    data=f"🏁 {result['message']}",
                    metadata={"yearly_task_id": task_id}
                )
            else:
                return ToolResult(success=False, error=result["message"])

        except Exception as e:
            logger.error(f"CompleteYearlyTaskTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
