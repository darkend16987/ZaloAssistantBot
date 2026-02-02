# app/mcp/tools/task_tools.py
"""
Task Management Tools
=====================
MCP tools cho việc quản lý tasks từ 1Office.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from app.mcp.core.base_tool import BaseTool, ToolParameter, ToolResult, ParameterType
from app.mcp.core.provider_registry import provider_registry
from app.mcp.providers.oneoffice_provider import OneOfficeProvider
from app.core.constants import STATUS_MAP
from app.core.logging import logger


def get_oneoffice_provider() -> OneOfficeProvider:
    """Get OneOffice provider from registry"""
    provider = provider_registry.get("oneoffice")
    if not provider:
        raise RuntimeError("OneOffice provider not initialized")
    return provider


class GetTasksTool(BaseTool):
    """Tool để lấy danh sách tất cả công việc"""

    @property
    def name(self) -> str:
        return "get_tasks"

    @property
    def description(self) -> str:
        return """Lấy danh sách tất cả công việc của người dùng.
Sử dụng khi người dùng hỏi: "tôi có việc gì", "công việc của tôi", "xem tasks", "list việc"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return []  # No parameters needed

    @property
    def category(self) -> str:
        return "tasks"

    async def execute(self, **kwargs) -> ToolResult:
        try:
            provider = get_oneoffice_provider()
            tasks_data = await provider.get_tasks()

            if tasks_data is None:
                return ToolResult(
                    success=False,
                    error="Không thể kết nối đến hệ thống 1Office"
                )

            formatted = provider.format_tasks_for_display(
                tasks_data,
                title="Đây là các công việc của bạn:"
            )

            task_ids = [t['ID'] for t in tasks_data.get('data', [])]

            return ToolResult(
                success=True,
                data=formatted,
                metadata={"task_ids": task_ids, "total": tasks_data.get('total_item', 0)}
            )

        except Exception as e:
            logger.error(f"GetTasksTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class GetTasksByStatusTool(BaseTool):
    """Tool để lấy công việc theo trạng thái"""

    @property
    def name(self) -> str:
        return "get_tasks_by_status"

    @property
    def description(self) -> str:
        return """Lấy danh sách công việc theo trạng thái cụ thể.
Sử dụng khi người dùng hỏi: "việc đã hoàn thành", "việc đang làm", "việc tạm dừng"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="status",
                type=ParameterType.STRING,
                description="Trạng thái công việc: COMPLETED (hoàn thành), DOING (đang làm), PAUSE (tạm dừng), PENDING (chờ xử lý), CANCEL (hủy)",
                required=True,
                enum=["COMPLETED", "DOING", "PAUSE", "PENDING", "CANCEL"]
            )
        ]

    @property
    def category(self) -> str:
        return "tasks"

    async def execute(self, status: str, **kwargs) -> ToolResult:
        try:
            provider = get_oneoffice_provider()
            api_status = STATUS_MAP.get(status, status)

            tasks_data = await provider.get_tasks(status=[api_status])

            if tasks_data is None:
                return ToolResult(
                    success=False,
                    error="Không thể kết nối đến hệ thống 1Office"
                )

            formatted = provider.format_tasks_for_display(
                tasks_data,
                title=f"Công việc có trạng thái *{api_status}*:"
            )

            task_ids = [t['ID'] for t in tasks_data.get('data', [])]

            return ToolResult(
                success=True,
                data=formatted,
                metadata={"task_ids": task_ids, "status": status}
            )

        except Exception as e:
            logger.error(f"GetTasksByStatusTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class GetDailyReportTool(BaseTool):
    """Tool để lấy báo cáo công việc trong ngày"""

    @property
    def name(self) -> str:
        return "get_daily_report"

    @property
    def description(self) -> str:
        return """Lấy báo cáo công việc cần làm trong ngày hôm nay.
Sử dụng khi người dùng hỏi: "hôm nay có việc gì", "báo cáo ngày", "công việc hôm nay"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return []

    @property
    def category(self) -> str:
        return "tasks"

    async def execute(self, **kwargs) -> ToolResult:
        try:
            provider = get_oneoffice_provider()
            today_str = datetime.now().strftime('%d/%m/%Y')

            tasks_data = await provider.get_tasks(
                status=["DOING", "PENDING", "COMPLETED"],
                date_from=today_str,
                date_to=today_str
            )

            if tasks_data is None:
                return ToolResult(
                    success=False,
                    error="Không thể kết nối đến hệ thống 1Office"
                )

            formatted = provider.format_tasks_for_display(
                tasks_data,
                title=f"☀️ Báo cáo công việc ngày {today_str}:"
            )

            task_ids = [t['ID'] for t in tasks_data.get('data', [])]

            return ToolResult(
                success=True,
                data=formatted,
                metadata={"task_ids": task_ids, "date": today_str}
            )

        except Exception as e:
            logger.error(f"GetDailyReportTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class GetWeeklyReportTool(BaseTool):
    """Tool để lấy báo cáo công việc trong tuần"""

    @property
    def name(self) -> str:
        return "get_weekly_report"

    @property
    def description(self) -> str:
        return """Lấy báo cáo công việc từ đầu tuần đến hiện tại.
Sử dụng khi người dùng hỏi: "báo cáo tuần", "công việc tuần này", "weekly report"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return []

    @property
    def category(self) -> str:
        return "tasks"

    async def execute(self, **kwargs) -> ToolResult:
        try:
            provider = get_oneoffice_provider()
            start_of_week = datetime.now() - timedelta(days=datetime.now().weekday())
            start_str = start_of_week.strftime('%d/%m/%Y')

            tasks_data = await provider.get_tasks(
                status=["DOING", "PENDING", "COMPLETED"],
                date_from=start_str
            )

            if tasks_data is None:
                return ToolResult(
                    success=False,
                    error="Không thể kết nối đến hệ thống 1Office"
                )

            formatted = provider.format_tasks_for_display(
                tasks_data,
                title=f"📊 Báo cáo công việc từ đầu tuần ({start_str}):"
            )

            task_ids = [t['ID'] for t in tasks_data.get('data', [])]

            return ToolResult(
                success=True,
                data=formatted,
                metadata={"task_ids": task_ids, "week_start": start_str}
            )

        except Exception as e:
            logger.error(f"GetWeeklyReportTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class CreateTaskTool(BaseTool):
    """Tool để tạo công việc mới"""

    @property
    def name(self) -> str:
        return "create_task"

    @property
    def description(self) -> str:
        return """Tạo công việc mới trong hệ thống.
Sử dụng khi người dùng nói: "tạo task", "tạo việc", "thêm công việc", "add task"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="title",
                type=ParameterType.STRING,
                description="Tên/tiêu đề công việc",
                required=True
            ),
            ToolParameter(
                name="end_plan",
                type=ParameterType.STRING,
                description="Deadline công việc (định dạng dd/mm/YYYY)",
                required=True
            ),
            ToolParameter(
                name="time_end_plan",
                type=ParameterType.STRING,
                description="Giờ deadline (định dạng HH:MM), optional",
                required=False
            ),
            ToolParameter(
                name="priority",
                type=ParameterType.STRING,
                description="Độ ưu tiên: Cao, Trung bình, Bình thường, Thấp",
                required=False,
                enum=["Cao", "Trung bình", "Bình thường", "Thấp"]
            ),
            ToolParameter(
                name="assignee",
                type=ParameterType.STRING,
                description="Tên người được giao việc (nếu không có sẽ dùng default)",
                required=False
            )
        ]

    @property
    def category(self) -> str:
        return "tasks"

    async def execute(
        self,
        title: str,
        end_plan: str,
        time_end_plan: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        try:
            provider = get_oneoffice_provider()

            new_id, error = await provider.create_task(
                title=title,
                end_plan=end_plan,
                time_end_plan=time_end_plan,
                priority=priority,
                assignee=assignee
            )

            if error:
                return ToolResult(
                    success=False,
                    error=f"Lỗi khi tạo task: {error}"
                )

            time_str = f" lúc {time_end_plan}" if time_end_plan else ""
            message = f"✅ Đã tạo công việc:\n\n🔹 *{title}*\n  _Hạn chót: {end_plan}{time_str}_\n  `(ID: {new_id})`"

            return ToolResult(
                success=True,
                data=message,
                metadata={"new_task_id": new_id, "title": title}
            )

        except Exception as e:
            logger.error(f"CreateTaskTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class UpdateTaskStatusTool(BaseTool):
    """Tool để cập nhật trạng thái công việc"""

    @property
    def name(self) -> str:
        return "update_task_status"

    @property
    def description(self) -> str:
        return """Cập nhật trạng thái của công việc.
Sử dụng khi người dùng nói: "hoàn thành task", "done task", "tạm dừng việc", "hủy task"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="task_id",
                type=ParameterType.INTEGER,
                description="ID của công việc cần cập nhật",
                required=True
            ),
            ToolParameter(
                name="new_status",
                type=ParameterType.STRING,
                description="Trạng thái mới: COMPLETED, DOING, PAUSE, PENDING, CANCEL",
                required=True,
                enum=["COMPLETED", "DOING", "PAUSE", "PENDING", "CANCEL"]
            )
        ]

    @property
    def category(self) -> str:
        return "tasks"

    async def execute(
        self,
        task_id: int,
        new_status: str,
        **kwargs
    ) -> ToolResult:
        try:
            provider = get_oneoffice_provider()

            # Verify task exists
            tasks_data = await provider.get_tasks(include_all_statuses=True)
            if not tasks_data or not provider.validate_task_id(tasks_data, task_id):
                return ToolResult(
                    success=False,
                    error=f"Không tìm thấy công việc có ID {task_id}"
                )

            task_info = provider.get_task_by_id(tasks_data, task_id)
            task_title = task_info.get('title', f'ID {task_id}') if task_info else f'ID {task_id}'

            success = await provider.update_task_status(task_id, new_status)

            if not success:
                return ToolResult(
                    success=False,
                    error=f"Lỗi khi cập nhật trạng thái cho task {task_id}"
                )

            api_status = STATUS_MAP.get(new_status, new_status)
            message = f"✅ Đã chuyển công việc '{task_title}' sang trạng thái *{api_status}*"

            return ToolResult(
                success=True,
                data=message,
                metadata={"task_id": task_id, "new_status": new_status}
            )

        except Exception as e:
            logger.error(f"UpdateTaskStatusTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class SetDeadlineTool(BaseTool):
    """Tool để đặt deadline mới cho công việc"""

    @property
    def name(self) -> str:
        return "set_deadline"

    @property
    def description(self) -> str:
        return """Đặt deadline mới cho công việc.
Sử dụng khi người dùng nói: "đổi deadline", "set deadline", "chuyển deadline"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="task_id",
                type=ParameterType.INTEGER,
                description="ID của công việc",
                required=True
            ),
            ToolParameter(
                name="new_deadline",
                type=ParameterType.STRING,
                description="Deadline mới (định dạng dd/mm/YYYY)",
                required=True
            )
        ]

    @property
    def category(self) -> str:
        return "tasks"

    async def execute(
        self,
        task_id: int,
        new_deadline: str,
        **kwargs
    ) -> ToolResult:
        try:
            provider = get_oneoffice_provider()

            # Verify task exists
            tasks_data = await provider.get_tasks(include_all_statuses=True)
            if not tasks_data or not provider.validate_task_id(tasks_data, task_id):
                return ToolResult(
                    success=False,
                    error=f"Không tìm thấy công việc có ID {task_id}"
                )

            task_info = provider.get_task_by_id(tasks_data, task_id)
            task_title = task_info.get('title', f'ID {task_id}') if task_info else f'ID {task_id}'

            success = await provider.update_task(task_id, end_plan=new_deadline)

            if not success:
                return ToolResult(
                    success=False,
                    error=f"Lỗi khi cập nhật deadline cho task {task_id}"
                )

            message = f"✅ Đã đặt lại deadline cho '{task_title}' thành *{new_deadline}*"

            return ToolResult(
                success=True,
                data=message,
                metadata={"task_id": task_id, "new_deadline": new_deadline}
            )

        except Exception as e:
            logger.error(f"SetDeadlineTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class ExtendDeadlineTool(BaseTool):
    """Tool để gia hạn deadline"""

    @property
    def name(self) -> str:
        return "extend_deadline"

    @property
    def description(self) -> str:
        return """Gia hạn deadline công việc thêm một số ngày.
Sử dụng khi người dùng nói: "gia hạn", "thêm 3 ngày", "lùi deadline"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="task_id",
                type=ParameterType.INTEGER,
                description="ID của công việc",
                required=True
            ),
            ToolParameter(
                name="days",
                type=ParameterType.INTEGER,
                description="Số ngày cần gia hạn",
                required=True
            )
        ]

    @property
    def category(self) -> str:
        return "tasks"

    async def execute(
        self,
        task_id: int,
        days: int,
        **kwargs
    ) -> ToolResult:
        try:
            provider = get_oneoffice_provider()

            # Get current task info
            tasks_data = await provider.get_tasks(include_all_statuses=True)
            if not tasks_data:
                return ToolResult(
                    success=False,
                    error="Không thể kết nối đến hệ thống"
                )

            task_info = provider.get_task_by_id(tasks_data, task_id)
            if not task_info:
                return ToolResult(
                    success=False,
                    error=f"Không tìm thấy công việc có ID {task_id}"
                )

            current_deadline = task_info.get('end_plan')
            if not current_deadline:
                return ToolResult(
                    success=False,
                    error="Công việc này chưa có deadline để gia hạn"
                )

            # Calculate new deadline
            old_date = datetime.strptime(current_deadline, '%d/%m/%Y')
            new_date = old_date + timedelta(days=days)
            new_deadline = new_date.strftime('%d/%m/%Y')

            success = await provider.update_task(task_id, end_plan=new_deadline)

            if not success:
                return ToolResult(
                    success=False,
                    error=f"Lỗi khi gia hạn deadline cho task {task_id}"
                )

            message = f"✅ Đã gia hạn '{task_info['title']}' thêm {days} ngày, deadline mới là *{new_deadline}*"

            return ToolResult(
                success=True,
                data=message,
                metadata={"task_id": task_id, "old_deadline": current_deadline, "new_deadline": new_deadline}
            )

        except ValueError as e:
            return ToolResult(success=False, error="Lỗi định dạng ngày tháng")
        except Exception as e:
            logger.error(f"ExtendDeadlineTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))


class RenameTaskTool(BaseTool):
    """Tool để đổi tên công việc"""

    @property
    def name(self) -> str:
        return "rename_task"

    @property
    def description(self) -> str:
        return """Đổi tên/tiêu đề của công việc.
Sử dụng khi người dùng nói: "đổi tên task", "rename task", "sửa tên việc"."""

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="task_id",
                type=ParameterType.INTEGER,
                description="ID của công việc",
                required=True
            ),
            ToolParameter(
                name="new_title",
                type=ParameterType.STRING,
                description="Tên mới cho công việc",
                required=True
            )
        ]

    @property
    def category(self) -> str:
        return "tasks"

    async def execute(
        self,
        task_id: int,
        new_title: str,
        **kwargs
    ) -> ToolResult:
        try:
            provider = get_oneoffice_provider()

            # Verify task exists
            tasks_data = await provider.get_tasks(include_all_statuses=True)
            if not tasks_data or not provider.validate_task_id(tasks_data, task_id):
                return ToolResult(
                    success=False,
                    error=f"Không tìm thấy công việc có ID {task_id}"
                )

            success = await provider.update_task(task_id, title=new_title)

            if not success:
                return ToolResult(
                    success=False,
                    error=f"Lỗi khi đổi tên task {task_id}"
                )

            message = f"✅ Đã đổi tên công việc ID {task_id} thành *'{new_title}'*"

            return ToolResult(
                success=True,
                data=message,
                metadata={"task_id": task_id, "new_title": new_title}
            )

        except Exception as e:
            logger.error(f"RenameTaskTool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))
