# app/mcp/providers/oneoffice_provider.py
"""
OneOffice Provider
==================
Provider kết nối với 1Office API để quản lý tasks.
"""

import json
import aiohttp
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from app.mcp.core.base_provider import BaseProvider, ProviderConfig, ProviderStatus
from app.core.settings import settings
from app.core.logging import logger
from app.core.constants import STATUS_MAP, PRIORITY_MAP


class OneOfficeProvider(BaseProvider):
    """
    Provider cho 1Office API.

    Cung cấp các methods để:
    - Lấy danh sách tasks
    - Tạo task mới
    - Cập nhật task
    - Xóa task
    """

    BASE_URL = "https://innojsc.1office.vn/api/work/normal"

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="oneoffice"))
        self._token: Optional[str] = None

    @property
    def name(self) -> str:
        return "oneoffice"

    async def initialize(self) -> None:
        """Initialize provider with API token"""
        self._token = settings.ONEOFFICE_TOKEN.get_secret_value()
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )

        # Verify connection
        status = await self.health_check()
        if status == ProviderStatus.HEALTHY:
            logger.info("OneOffice provider initialized successfully")
        else:
            logger.warning("OneOffice provider initialized but health check failed")

    async def health_check(self) -> ProviderStatus:
        """Check 1Office API connectivity"""
        try:
            session = await self.get_http_session()
            params = {
                "access_token": self._token,
                "filters": json.dumps([{"assign_ids": settings.DEFAULT_ASSIGNEE, "status": ["DOING"]}])
            }

            async with session.get(f"{self.BASE_URL}/gets", params=params, timeout=5) as response:
                if response.status == 200:
                    self._status = ProviderStatus.HEALTHY
                else:
                    self._status = ProviderStatus.DEGRADED

        except Exception as e:
            logger.error(f"OneOffice health check failed: {e}")
            self._status = ProviderStatus.UNAVAILABLE

        return self._status

    # === Task Operations ===

    async def get_tasks(
        self,
        status: Optional[List[str]] = None,
        assignee: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        include_all_statuses: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Lấy danh sách tasks từ 1Office.

        Args:
            status: List status codes (DOING, COMPLETED, PAUSE, PENDING, CANCEL)
            assignee: Filter by assignee name
            date_from: Start date filter (dd/mm/YYYY)
            date_to: End date filter (dd/mm/YYYY)
            include_all_statuses: If True, include all statuses

        Returns:
            Dict with 'data' (list of tasks) and 'total_item'
        """
        filters: Dict[str, Any] = {
            "assign_ids": assignee or settings.DEFAULT_ASSIGNEE
        }

        if status:
            filters["status"] = status
        elif include_all_statuses:
            filters["status"] = ["DOING", "PENDING", "COMPLETED", "CANCEL", "PAUSE"]
        else:
            filters["status"] = ["DOING", "PAUSE", "PENDING"]

        if date_from:
            filters["end_plan_from"] = date_from
        if date_to:
            filters["end_plan_to"] = date_to

        params = {
            "access_token": self._token,
            "filters": json.dumps([filters])
        }

        try:
            session = await self.get_http_session()
            async with session.get(f"{self.BASE_URL}/gets", params=params) as response:
                response.raise_for_status()
                return await response.json(content_type=None)
        except Exception as e:
            logger.error(f"Error getting tasks: {e}", exc_info=True)
            return None

    async def create_task(
        self,
        title: str,
        end_plan: str,
        assignee: Optional[str] = None,
        time_end_plan: Optional[str] = None,
        priority: Optional[str] = None,
        auto_start: bool = True
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Tạo task mới.

        Args:
            title: Task title
            end_plan: Deadline (dd/mm/YYYY)
            assignee: Assignee name (default: settings.DEFAULT_ASSIGNEE)
            time_end_plan: Deadline time (HH:MM)
            priority: Priority level (Cao, Trung bình, Bình thường, Thấp)
            auto_start: Whether to auto-start the task

        Returns:
            Tuple (new_task_id, error_message)
        """
        assignee_name = assignee or settings.DEFAULT_ASSIGNEE

        payload = {
            'title': title,
            'assign_ids': assignee_name,
            'owner_ids': settings.DEFAULT_ASSIGNEE,
            'end_plan': end_plan,
            'progress_type': 'PERCENT'
        }

        if time_end_plan:
            payload['time_end_plan'] = time_end_plan
        if priority:
            # Convert priority name to API value if needed
            priority_value = PRIORITY_MAP.get(priority.lower(), priority)
            payload['priority'] = priority_value

        params = {"access_token": self._token}

        try:
            session = await self.get_http_session()

            # Step 1: Create task
            async with session.post(
                f"{self.BASE_URL}/insert",
                params=params,
                data=payload
            ) as response:
                response.raise_for_status()
                resp_json = await response.json(content_type=None)

                if resp_json.get("error"):
                    return None, resp_json.get("message")

                new_task_id = resp_json.get("newPost", {}).get("ID")
                if not new_task_id:
                    return None, "Could not retrieve ID of new task"

            # Step 2: Auto-start if requested
            if auto_start and new_task_id:
                update_payload = {
                    'ID': new_task_id,
                    'status': 'Đang thực hiện',
                    'start_plan': datetime.now().strftime('%d/%m/%Y')
                }

                async with session.post(
                    f"{self.BASE_URL}/update",
                    params=params,
                    data=update_payload
                ) as update_res:
                    update_res.raise_for_status()
                    update_json = await update_res.json(content_type=None)

                    if update_json.get("error"):
                        return new_task_id, "Created but failed to activate"

            return new_task_id, None

        except Exception as e:
            logger.error(f"Error creating task: {e}", exc_info=True)
            return None, f"System error: {str(e)}"

    async def update_task(
        self,
        task_id: int,
        **updates
    ) -> bool:
        """
        Cập nhật task.

        Args:
            task_id: Task ID to update
            **updates: Fields to update (status, end_plan, title, percent, etc.)

        Returns:
            True if successful
        """
        payload = {'ID': task_id, **updates}
        params = {"access_token": self._token}

        try:
            session = await self.get_http_session()
            async with session.post(
                f"{self.BASE_URL}/update",
                params=params,
                data=payload
            ) as response:
                response.raise_for_status()
                resp_json = await response.json(content_type=None)
                return not resp_json.get("error")
        except Exception as e:
            logger.error(f"Error updating task {task_id}: {e}", exc_info=True)
            return False

    async def update_task_status(
        self,
        task_id: int,
        new_status: str,
        complete_if_done: bool = True
    ) -> bool:
        """
        Cập nhật trạng thái task.

        Args:
            task_id: Task ID
            new_status: New status code (DOING, COMPLETED, PAUSE, PENDING, CANCEL)
            complete_if_done: If COMPLETED, set percent to 100 and end date

        Returns:
            True if successful
        """
        # Map status key to API value
        api_status = STATUS_MAP.get(new_status, new_status)

        payload: Dict[str, Any] = {'status': api_status}

        if new_status == "COMPLETED" and complete_if_done:
            payload['percent'] = 100
            payload['end'] = datetime.now().strftime('%d/%m/%Y')

        return await self.update_task(task_id, **payload)

    async def batch_update_tasks(
        self,
        task_updates: List[Tuple[int, Dict]]
    ) -> List[bool]:
        """
        Cập nhật nhiều tasks cùng lúc.

        Args:
            task_updates: List of (task_id, payload) tuples

        Returns:
            List of success booleans
        """
        import asyncio
        coroutines = [
            self.update_task(task_id, **payload)
            for task_id, payload in task_updates
        ]
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        return [
            r if isinstance(r, bool) else False
            for r in results
        ]

    # === Helper Methods ===

    def format_tasks_for_display(
        self,
        tasks_data: Dict[str, Any],
        title: str = "Các công việc của bạn:"
    ) -> str:
        """
        Format tasks data thành message đẹp để hiển thị.
        """
        from collections import defaultdict
        from app.core.constants import DISPLAY_STATUS_MAP

        if not tasks_data or tasks_data.get("total_item", 0) == 0:
            return "🎉 Tuyệt vời! Bạn không có công việc nào khớp với tiêu chí."

        tasks = tasks_data.get("data", [])
        tasks_by_status = defaultdict(list)

        for task in tasks:
            api_status = task.get('status', 'Không xác định')
            if "Quá hạn" in task.get('deadline_list', ''):
                tasks_by_status["Quá hạn"].append(task)
            elif "Còn 0 ngày" in task.get('deadline_list', ''):
                tasks_by_status["Đến hạn hôm nay"].append(task)
            else:
                display_category = DISPLAY_STATUS_MAP.get(api_status, api_status)
                tasks_by_status[display_category].append(task)

        status_order = ["Quá hạn", "Đến hạn hôm nay", "Đang thực hiện", "Tạm dừng", "Đang chờ", "Hoàn thành", "Hủy"]
        message = f"*{title}*\n\n"
        found_tasks = False

        for status in status_order:
            if status in tasks_by_status:
                found_tasks = True
                message += f"--- *{status.upper()}* ---\n"
                sorted_tasks = sorted(
                    tasks_by_status[status],
                    key=lambda t: t.get('end_plan', '9999-99-99')
                )
                for task in sorted_tasks:
                    emoji = "🔴" if status == "Quá hạn" else "🟠" if status == "Đến hạn hôm nay" else "🟢" if task.get('status') == "Hoàn thành" else "🔵"
                    end_time_str = f" {task.get('time_end_plan', '')}" if task.get('is_assign_hour') == 'Có' and task.get('time_end_plan') else ""
                    deadline_info = task.get('deadline_list', '')
                    message += f"{emoji} *{task['title'].strip()}*\n  _Hạn chót: {task.get('end_plan', 'N/A')}{end_time_str}_ | _{deadline_info}_\n  `ID: {task['ID']}`\n\n"

        if not found_tasks:
            return "🎉 Bạn không có việc nào để xem."

        return message

    def get_task_by_id(self, tasks_data: Dict, task_id: int) -> Optional[Dict]:
        """Get a specific task by ID from tasks data"""
        if not tasks_data:
            return None
        # Convert task_id to int for comparison (API may return string or int)
        task_id_int = int(task_id)
        for task in tasks_data.get("data", []):
            # Compare as int to handle both string and int IDs from API
            try:
                if int(task.get("ID", 0)) == task_id_int:
                    return task
            except (ValueError, TypeError):
                continue
        return None

    def validate_task_id(self, tasks_data: Dict, task_id: int) -> bool:
        """Check if task ID exists in tasks data"""
        return self.get_task_by_id(tasks_data, task_id) is not None
