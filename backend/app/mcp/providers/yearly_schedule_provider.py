# app/mcp/providers/yearly_schedule_provider.py
"""
Yearly Schedule Provider
========================
Provider cho dữ liệu lịch công việc theo năm.
Cung cấp khả năng truy vấn và quản lý trạng thái yearly tasks
cho MCP tools.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, date

from app.mcp.core.base_provider import BaseProvider, ProviderConfig, ProviderStatus
from app.core.logging import logger
from app.services.yearly_scheduler import (
    load_all_schedules,
    get_all_tasks_with_dates,
    get_upcoming_tasks,
    get_task_state,
    update_task_state,
    resolve_anchor_date,
    FIXED_ANCHORS,
    LUNAR_ANCHOR_TABLES,
)


class YearlyScheduleProvider(BaseProvider):
    """
    Provider cho lịch công việc theo năm.

    Cung cấp:
    - Truy vấn lịch theo quý
    - Xem tasks sắp tới
    - Xác nhận tạo task lên 1Office
    - Bỏ qua task
    - Xem trạng thái tổng quan
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="yearly_schedule"))

    @property
    def name(self) -> str:
        return "yearly_schedule"

    async def initialize(self) -> None:
        """Initialize: load schedules và verify"""
        try:
            schedules = load_all_schedules()
            total_tasks = sum(
                len(s.get("tasks", [])) for s in schedules.values()
            )
            logger.info(
                f"YearlyScheduleProvider: Loaded {len(schedules)} quarters, "
                f"{total_tasks} tasks total"
            )
            self._status = ProviderStatus.HEALTHY
        except Exception as e:
            logger.error(f"YearlyScheduleProvider init error: {e}")
            self._status = ProviderStatus.UNAVAILABLE

    async def health_check(self) -> ProviderStatus:
        """Verify schedule files accessible"""
        try:
            schedules = load_all_schedules()
            if schedules:
                self._status = ProviderStatus.HEALTHY
            else:
                self._status = ProviderStatus.DEGRADED
        except Exception:
            self._status = ProviderStatus.UNAVAILABLE
        return self._status

    # === Query Methods ===

    def get_schedule_overview(self, year: int = None) -> str:
        """Tổng quan lịch cả năm, format cho hiển thị"""
        if year is None:
            year = datetime.now().year

        all_tasks = get_all_tasks_with_dates(year)
        if not all_tasks:
            return f"Chưa có lịch công việc nào cho năm {year}."

        lines = [f"📅 *LỊCH CÔNG VIỆC NĂM {year}*\n"]
        current_quarter = None

        for task in all_tasks:
            q = task.get("quarter", "")
            if q != current_quarter:
                current_quarter = q
                lines.append(f"\n--- *{q}* ---")

            rd = task.get("resolved_date")
            dl = task.get("resolved_deadline")
            status = task["state"].get("status", "pending")

            status_emoji = {
                "pending": "⏳",
                "notified": "🔔",
                "created": "✅",
                "completed": "🏁",
                "skipped": "⏭️",
            }.get(status, "❓")

            date_str = rd.strftime("%d/%m") if rd else "N/A"
            dl_str = dl.strftime("%d/%m") if dl else "N/A"

            lines.append(
                f"{status_emoji} *{task['title']}*\n"
                f"  📆 Ngày: {date_str} | Deadline: {dl_str}\n"
                f"  `{task['id']}`"
            )

        # Summary
        total = len(all_tasks)
        pending = sum(1 for t in all_tasks if t["state"].get("status") == "pending")
        created = sum(1 for t in all_tasks if t["state"].get("status") == "created")
        completed = sum(1 for t in all_tasks if t["state"].get("status") == "completed")

        lines.append(
            f"\n📊 *Tổng: {total}* | "
            f"Chờ: {pending} | Đã tạo: {created} | Hoàn thành: {completed}"
        )

        return "\n".join(lines)

    def get_upcoming_formatted(self, days: int = 14) -> str:
        """Lấy tasks sắp tới, format cho hiển thị"""
        tasks = get_upcoming_tasks(days=days)

        if not tasks:
            return f"Không có công việc theo lịch năm nào trong {days} ngày tới."

        lines = [f"📋 *Công việc theo lịch năm sắp tới ({days} ngày)*\n"]

        for task in tasks:
            rd = task.get("resolved_date")
            dl = task.get("resolved_deadline")

            date_str = rd.strftime("%d/%m/%Y") if rd else "N/A"
            dl_str = dl.strftime("%d/%m/%Y") if dl else "N/A"

            # Tính còn bao nhiêu ngày
            if rd:
                days_left = (rd - date.today()).days
                if days_left == 0:
                    time_str = "HÔM NAY"
                elif days_left == 1:
                    time_str = "NGÀY MAI"
                else:
                    time_str = f"còn {days_left} ngày"
            else:
                time_str = ""

            lines.append(
                f"📌 *{task['title']}* ({time_str})\n"
                f"  {task.get('description', '')}\n"
                f"  📆 Ngày: {date_str} | Deadline: {dl_str}\n"
                f"  `{task['id']}`"
            )

        return "\n".join(lines)

    def get_task_detail(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết một task theo ID"""
        all_tasks = get_all_tasks_with_dates()
        for task in all_tasks:
            if task["id"] == task_id:
                return task
        return None

    def get_task_detail_formatted(self, task_id: str) -> str:
        """Lấy chi tiết task, format cho hiển thị"""
        task = self.get_task_detail(task_id)
        if not task:
            return f"Không tìm thấy công việc với ID: {task_id}"

        rd = task.get("resolved_date")
        dl = task.get("resolved_deadline")
        state = task.get("state", {})

        lines = [
            f"📋 *Chi tiết: {task['title']}*\n",
            f"🆔 ID: `{task['id']}`",
            f"📝 Mô tả: {task.get('description', 'N/A')}",
            f"📆 Ngày thực hiện: {rd.strftime('%d/%m/%Y') if rd else 'N/A'}",
            f"⏰ Deadline: {dl.strftime('%d/%m/%Y') if dl else 'N/A'}",
        ]

        # Assignees
        assignees = task.get("assignees", [])
        if assignees:
            lines.append(f"👤 Người thực hiện: {', '.join(assignees)}")

        # Template
        template = task.get("template", {})
        if template.get("content"):
            lines.append(f"\n📄 *Nội dung mẫu:*\n{template['content']}")
        if template.get("link"):
            lines.append(f"🔗 Link: {template['link']}")

        # State
        status = state.get("status", "pending")
        status_label = {
            "pending": "Chờ xử lý",
            "notified": "Đã thông báo",
            "created": "Đã tạo trên 1Office",
            "completed": "Hoàn thành",
            "skipped": "Đã bỏ qua",
        }.get(status, status)
        lines.append(f"\n📊 Trạng thái: *{status_label}*")

        if state.get("oneoffice_task_id"):
            lines.append(f"🔹 1Office ID: `{state['oneoffice_task_id']}`")

        return "\n".join(lines)

    # === Action Methods ===

    async def confirm_and_create_task(self, task_id: str) -> Dict[str, Any]:
        """
        Xác nhận và tạo task lên 1Office.

        Returns:
            {"success": bool, "message": str, "oneoffice_task_id": int|None}
        """
        task = self.get_task_detail(task_id)
        if not task:
            return {"success": False, "message": f"Không tìm thấy task {task_id}"}

        state = task.get("state", {})
        if state.get("status") in ("created", "completed"):
            oo_id = state.get("oneoffice_task_id", "N/A")
            return {
                "success": False,
                "message": f"Task {task_id} đã được tạo trước đó (1Office ID: {oo_id})"
            }

        # Create task via OneOffice provider
        from app.mcp.core.provider_registry import provider_registry
        oneoffice = provider_registry.get("oneoffice")
        if not oneoffice or not oneoffice.is_available:
            return {"success": False, "message": "1Office không khả dụng"}

        # Prepare deadline
        dl = task.get("resolved_deadline")
        if not dl:
            return {"success": False, "message": "Không xác định được deadline"}

        deadline_str = dl.strftime("%d/%m/%Y")

        # Determine assignee
        assignees = task.get("assignees", [])
        assignee = assignees[0] if assignees else None

        # Create on 1Office
        new_id, error = await oneoffice.create_task(
            title=task["title"],
            end_plan=deadline_str,
            assignee=assignee,
        )

        if error:
            return {"success": False, "message": f"Lỗi tạo task: {error}"}

        # Update state
        update_task_state(task_id, {
            "status": "created",
            "oneoffice_task_id": new_id,
            "created_at": datetime.now().isoformat(),
        })

        return {
            "success": True,
            "message": f"Đã tạo '{task['title']}' trên 1Office (ID: {new_id}), deadline: {deadline_str}",
            "oneoffice_task_id": new_id,
        }

    def skip_task(self, task_id: str) -> Dict[str, Any]:
        """Bỏ qua một yearly task"""
        task = self.get_task_detail(task_id)
        if not task:
            return {"success": False, "message": f"Không tìm thấy task {task_id}"}

        update_task_state(task_id, {
            "status": "skipped",
            "skipped_at": datetime.now().isoformat(),
        })

        return {
            "success": True,
            "message": f"Đã bỏ qua '{task['title']}'"
        }

    def mark_task_notified(self, task_id: str) -> None:
        """Đánh dấu task đã gửi notification"""
        update_task_state(task_id, {
            "status": "notified",
            "notified_at": datetime.now().isoformat(),
        })

    def mark_task_completed(self, task_id: str) -> Dict[str, Any]:
        """Đánh dấu yearly task hoàn thành"""
        task = self.get_task_detail(task_id)
        if not task:
            return {"success": False, "message": f"Không tìm thấy task {task_id}"}

        update_task_state(task_id, {
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
        })

        return {
            "success": True,
            "message": f"Đã đánh dấu '{task['title']}' hoàn thành"
        }

    def get_available_anchors(self) -> str:
        """Liệt kê các anchor có sẵn"""
        year = datetime.now().year
        lines = [f"🗓️ *Các mốc thời gian hỗ trợ (năm {year})*\n"]

        lines.append("*Âm lịch (tính tự động):*")
        for anchor, table in LUNAR_ANCHOR_TABLES.items():
            d = table.get(year)
            label = anchor.replace("_", " ").title()
            date_str = d.strftime("%d/%m/%Y") if d else "N/A"
            lines.append(f"  • `{anchor}` → {label} → {date_str}")

        lines.append("\n*Dương lịch (cố định):*")
        for anchor, (month, day) in FIXED_ANCHORS.items():
            label = anchor.replace("_", " ").title()
            lines.append(f"  • `{anchor}` → {label} → {day:02d}/{month:02d}")

        return "\n".join(lines)
