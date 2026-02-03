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


# Birthday message templates - Full 9 forms
BIRTHDAY_TEMPLATES = [
    # Form0
    """❤ Hi cả nhà ❤
Mọi người có biết gì không? Tuần này chúng ta sẽ có cơ hội để tổ chức và chúc mừng sinh nhật 🎂 đến rất nhiều INNOer đó, cụ tỉ thì như sau:
[list]
Mọi người nhớ dành những lời chúc tốt đẹp nhất cho các bạn nha. Chúc các bạn có một ngày sinh nhật thật nhiều niềm vui và tuổi mới nhiều thành công hơn nữa nhé ⭐⭐⭐.

#INNO, #happy_birthday, #hpbd""",

    # Form1
    """❤ HAPPY BIRTHDAY – CHÚC CÁC BẠN TUỔI MỚI RỰC RỠ, THÀNH CÔNG & HẠNH PHÚC!
Thay mặt đại gia đình INNO, xin gửi lời chúc mừng sinh nhật đến [count] "ngôi sao" của tuần này:
[list]
Cảm ơn các bạn đã đồng hành và phát triển cùng INNO. Mong rằng tuổi mới sẽ là hành trình mới với nhiều dấu ấn đẹp và cơ hội tuyệt vời hơn nữa ❤

#INNO, #happy_birthday, #hpbd""",

    # Form2
    """Hi cả nhà,
Tuần này chúng ta tiếp tục được gửi những lời chúc mừng sinh nhật tốt đẹp nhất đến [count] bạn INNOer, cụ thể như sau:
[list]
Xin chúc mừng tất cả các bạn, chúc các bạn sẽ có một sinh nhật thật ý nghĩa, thật nhiều niềm vui và có nhiều thành công hơn nữa trong tương lai nhé ❤

#INNO, #happy_birthday, #hpbd""",

    # Form3
    """⭐ Hi cả nhà ❤
Tuần này đại gia đình INNO hân hoan chúc mừng sinh nhật [count] INNOer
[list]
Nhân dịp sinh nhật các bạn, các chị công đoàn và phòng nhân sự công ty xin được gửi những lời chúc tốt đẹp nhất đến các bạn, chúc các bạn sẽ có thật nhiều sức khỏe, thật nhiều niềm vui cùng INNO cũng như đạt được nhiều thành công hơn nữa trong cuộc sống nhé.

#INNO, #happy_birthday, #hpbd""",

    # Form4
    """⭐ Hi mọi người,
Chúng ta hãy cùng gửi những lời chúc tốt đẹp nhất dành cho các INNOer có sinh nhật trong tuần này. Chi tiết như sau
[list]
Cảm ơn các bạn đã luôn đồng hành và phát triển cùng đại gia đình INNO. Chúc các bạn sẽ có một tuổi mới với thật nhiều sức khỏe, thật nhiều thành công hơn nữa nhé. ❤🎂❤

#INNO, #happy_birthday, #hpbd""",

    # Form5
    """❤ HAPPY BIRTHDAY
Tuần này chúng ta hãy cùng gửi những lời chúc tốt đẹp nhất đến các INNOer có "sinh thần" trong tuần, cụ thể như sau:
[list]
Xin chúc mừng sinh nhật các anh chị em, chúc mọi người đón tuổi mới với thật nhiều niềm vui mới, thắng lợi mới cùng INNO nhé! ❤

#INNO, #happy_birthday, #hpbd""",

    # Form6
    """🎂 Cả nhà ơi, hãy cùng chúc mừng các bạn có sinh nhật trong tuần này nhé.
[list]
❤ Xin chúc các anh chị, các bạn sẽ có một ngày sinh nhật thật vui vẻ, tuổi mới nhiều sức khỏe và thành công hơn nữa nhé.

#INNO, #happy_birthday, #hpbd""",

    # Form7
    """🎉 Loa loa loa 🎉,
Chúc mừng tuổi mới của các bạn có sinh nhật trong tuần này nha 🎂
[list]
Cảm ơn các bạn đã đồng hành và phát triển cùng INNO. Mong rằng tuổi mới sẽ là hành trình mới với nhiều dấu ấn đẹp và cơ hội tuyệt vời hơn nữa ❤

#INNO, #happy_birthday, #hpbd""",

    # Form8
    """❤ Hi cả nhà ❤
Mọi người có biết gì không? Tuần này chúng ta có sinh nhật của rất nhiều INNOer đó. Hãy cùng gửi những lời chúc tốt đẹp nhất dành đến cho
[list]
Chúc các bạn có một ngày sinh nhật thật nhiều niềm vui và tuổi mới nhiều thành công hơn nữa nhé.

#INNO, #happy_birthday, #hpbd"""
]

# State file for tracking last used template
BIRTHDAY_STATE_FILE = "data/birthday_state.json"


def _load_last_template_index() -> int:
    """Load last used template index from state file"""
    import os
    import json
    try:
        if os.path.exists(BIRTHDAY_STATE_FILE):
            with open(BIRTHDAY_STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('last_template_index', -1)
    except Exception as e:
        logger.error(f"Error loading birthday state: {e}")
    return -1


def _save_last_template_index(index: int):
    """Save last used template index to state file"""
    import os
    import json
    try:
        os.makedirs(os.path.dirname(BIRTHDAY_STATE_FILE), exist_ok=True)
        with open(BIRTHDAY_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'last_template_index': index,
                'updated_at': datetime.now().isoformat()
            }, f)
    except Exception as e:
        logger.error(f"Error saving birthday state: {e}")


def get_random_template_index() -> int:
    """Get a random template index, avoiding the last used one"""
    last_index = _load_last_template_index()
    num_templates = len(BIRTHDAY_TEMPLATES)

    if num_templates <= 1:
        return 0

    # Pick a random index different from the last one
    new_index = last_index
    while new_index == last_index:
        new_index = random.randint(0, num_templates - 1)

    _save_last_template_index(new_index)
    return new_index


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
        week: str = "this"  # Changed default to "this"
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

        # Get week range - try both possible keys from Apps Script response
        week_range = birthday_data.get('weekRange') or birthday_data.get('thisWeekRange') or birthday_data.get('nextWeekRange', {})
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

        # Group employees by date
        grouped: Dict[str, List[Dict]] = {}
        for emp in employees:
            date_key = emp.get('birthDate', 'Unknown')
            if date_key not in grouped:
                grouped[date_key] = []
            grouped[date_key].append(emp)

        # Sort dates
        try:
            sorted_dates = sorted(
                grouped.keys(),
                key=lambda d: datetime.strptime(d, '%d/%m/%Y')
            )
        except Exception:
            sorted_dates = sorted(grouped.keys())

        # Build list content grouped by date
        list_content = ""
        for date_str in sorted_dates:
            day_emps = grouped[date_str]
            try:
                day_of_week = day_emps[0].get('dayOfWeek', '')
                list_content += f"📌 *{day_of_week}, {date_str}:*\n"
            except (KeyError, IndexError):
                list_content += f"📌 *{date_str}:*\n"

            for emp in day_emps:
                name = emp.get('name', 'Unknown')
                dept = emp.get('department', '')
                dept_str = f" ({dept})" if dept else ""
                list_content += f"   🎉 {name}{dept_str}\n"
            list_content += "\n"

        list_content = list_content.strip()

        # Get template (avoiding repeat of last used)
        template_idx = get_random_template_index()
        template = BIRTHDAY_TEMPLATES[template_idx]

        # Replace placeholders
        message = template.replace("[list]", list_content)
        message = message.replace("[count]", str(len(employees)))

        return message

    def get_combined_birthday_message(
        self,
        birthday_data: Dict[str, Any],
        week: str = "this"  # Changed default to "this"
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
