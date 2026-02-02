# app/mcp/providers/birthday_provider.py
"""
Birthday Provider
=================
Provider kết nối với Google Apps Script để lấy dữ liệu sinh nhật.
"""

import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime
import random

from app.mcp.core.base_provider import BaseProvider, ProviderConfig, ProviderStatus
from app.core.settings import settings
from app.core.logging import logger


# Birthday message templates
BIRTHDAY_TEMPLATES = [
    """🎉 CHÚC MỪNG SINH NHẬT 🎉

Chúc mừng sinh nhật [list] ([count] người)! 🎂

Chúc các bạn một ngày sinh nhật thật vui vẻ, hạnh phúc và tràn đầy niềm vui!

Năm mới tuổi, chúc các bạn:
✨ Sức khỏe dồi dào
✨ Công việc thuận lợi
✨ Hạnh phúc viên mãn

Happy Birthday! 🎈🎁""",

    """🎂 HAPPY BIRTHDAY! 🎂

Gửi lời chúc mừng sinh nhật tới [list]! ([count] người)

Chúc các bạn:
🌟 Tuổi mới - Thành công mới
🌟 Luôn khỏe mạnh, vui vẻ
🌟 Mọi điều tốt đẹp nhất sẽ đến

Have a wonderful birthday! 🎉🎈""",

    """🎈 SINH NHẬT VUI VẺ! 🎈

Hôm nay là ngày đặc biệt của [list]! ([count] người) 🎂

Team xin gửi những lời chúc tốt đẹp nhất:
💫 Chúc bạn luôn tỏa sáng
💫 Đạt được mọi mục tiêu
💫 Hạnh phúc mỗi ngày

Cheers to you! 🥳🎁""",
]


class BirthdayProvider(BaseProvider):
    """
    Provider cho Birthday data từ Google Sheets.

    Kết nối với Google Apps Script để:
    - Lấy danh sách sinh nhật tuần này/tuần sau
    - Format message chúc mừng
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="birthday"))
        self._apps_script_url: Optional[str] = None

    @property
    def name(self) -> str:
        return "birthday"

    async def initialize(self) -> None:
        """Initialize provider"""
        self._apps_script_url = settings.GOOGLE_APPS_SCRIPT_URL
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )

        if not self._apps_script_url:
            logger.warning("GOOGLE_APPS_SCRIPT_URL not configured")
            self._status = ProviderStatus.UNAVAILABLE
        else:
            self._status = ProviderStatus.HEALTHY
            logger.info("Birthday provider initialized")

    async def health_check(self) -> ProviderStatus:
        """Check Google Apps Script connectivity"""
        if not self._apps_script_url:
            self._status = ProviderStatus.UNAVAILABLE
            return self._status

        try:
            session = await self.get_http_session()
            async with session.get(
                self._apps_script_url,
                params={"week": "this"},
                timeout=5
            ) as response:
                if response.status == 200:
                    self._status = ProviderStatus.HEALTHY
                else:
                    self._status = ProviderStatus.DEGRADED
        except Exception as e:
            logger.error(f"Birthday health check failed: {e}")
            self._status = ProviderStatus.UNAVAILABLE

        return self._status

    async def get_birthdays(
        self,
        week: str = "next"
    ) -> Optional[Dict[str, Any]]:
        """
        Lấy danh sách sinh nhật.

        Args:
            week: "this" for current week, "next" for next week

        Returns:
            Dict with 'employees' list and week range info
        """
        if not self._apps_script_url:
            return {"error": "Apps Script URL not configured"}

        try:
            session = await self.get_http_session()
            async with session.get(
                self._apps_script_url,
                params={"week": week}
            ) as response:
                response.raise_for_status()
                return await response.json(content_type=None)
        except Exception as e:
            logger.error(f"Error fetching birthdays: {e}", exc_info=True)
            return {"error": str(e)}

    def format_birthday_list(
        self,
        birthday_data: Dict[str, Any],
        week_label: str = "TUẦN SAU"
    ) -> str:
        """
        Format danh sách sinh nhật thành message.

        Args:
            birthday_data: Data from get_birthdays()
            week_label: Label for the week (TUẦN NÀY, TUẦN SAU)

        Returns:
            Formatted message string
        """
        employees = birthday_data.get('employees', [])

        if not employees:
            return f"Không có ai sinh nhật trong {week_label.lower()}."

        week_range = birthday_data.get('nextWeekRange', {})
        start = week_range.get('start', '')
        end = week_range.get('end', '')

        message = f"🎂 *SINH NHẬT {week_label}* ({start} - {end})\n\n"

        for emp in employees:
            name = emp.get('name', 'N/A')
            birth_date = emp.get('birthDate', 'N/A')
            day_of_week = emp.get('dayOfWeek', '')
            department = emp.get('department', '')
            age = emp.get('age', '')

            age_str = f" - {age} tuổi" if age else ""
            dept_str = f" ({department})" if department else ""

            message += f"🎈 *{name}*{dept_str}\n"
            message += f"   📅 {day_of_week}, {birth_date}{age_str}\n\n"

        return message

    def format_public_announcement(
        self,
        birthday_data: Dict[str, Any]
    ) -> str:
        """
        Format thông báo chúc mừng public.

        Args:
            birthday_data: Data from get_birthdays()

        Returns:
            Public announcement message
        """
        employees = birthday_data.get('employees', [])

        if not employees:
            return "Không có ai sinh nhật để chúc mừng."

        # Get names list
        names = [emp.get('name', 'N/A') for emp in employees]
        count = len(names)

        if count == 1:
            names_str = names[0]
        elif count == 2:
            names_str = f"{names[0]} và {names[1]}"
        else:
            names_str = ", ".join(names[:-1]) + f" và {names[-1]}"

        # Choose random template
        template = random.choice(BIRTHDAY_TEMPLATES)

        # Replace placeholders
        message = template.replace("[list]", names_str)
        message = message.replace("[count]", str(count))

        return message

    def get_combined_birthday_message(
        self,
        birthday_data: Dict[str, Any],
        week: str = "next"
    ) -> str:
        """
        Get combined birthday list and public announcement.

        Args:
            birthday_data: Data from get_birthdays()
            week: "this" or "next"

        Returns:
            Combined message with list and announcement template
        """
        week_label = "TUẦN NÀY" if week == "this" else "TUẦN SAU"

        list_message = self.format_birthday_list(birthday_data, week_label)
        public_message = self.format_public_announcement(birthday_data)

        return f"{list_message}\n---\n\n📝 *Mẫu tin nhắn chúc mừng gợi ý:*\n\n{public_message}"
