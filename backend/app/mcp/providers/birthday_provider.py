# app/mcp/providers/birthday_provider.py
"""
Birthday Provider
=================
Provider kết nối với 1Office API để lấy dữ liệu sinh nhật nhân viên.
"""

import aiohttp
import json
import urllib.parse
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
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
BIRTHDAY_STATE_FILE = "backend/data/birthday_state.json"

# Vietnamese day of week mapping
WEEKDAY_NAMES = {
    0: "Thứ Hai",
    1: "Thứ Ba",
    2: "Thứ Tư",
    3: "Thứ Năm",
    4: "Thứ Sáu",
    5: "Thứ Bảy",
    6: "Chủ Nhật"
}


def _load_last_template_index() -> int:
    """Load last used template index from state file"""
    import os
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

    new_index = last_index
    while new_index == last_index:
        new_index = random.randint(0, num_templates - 1)

    _save_last_template_index(new_index)
    return new_index


def _get_week_range(week: str = "this") -> tuple:
    """
    Calculate week date range.

    Args:
        week: "this" for current week, "next" for next week, "next_next" for week after next

    Returns:
        Tuple of (start_date, end_date) as datetime objects
    """
    today = datetime.now()

    # Find Monday of current week
    days_since_monday = today.weekday()
    monday = today - timedelta(days=days_since_monday)

    if week == "next":
        monday = monday + timedelta(weeks=1)
    elif week == "next_next":
        monday = monday + timedelta(weeks=2)

    sunday = monday + timedelta(days=6)

    return monday, sunday


def _format_date_for_api(dt: datetime) -> str:
    """Format datetime to dd/MM/yyyy for 1Office API"""
    return dt.strftime("%d/%m/%Y")


class BirthdayProvider(BaseProvider):
    """
    Provider cho Birthday data từ 1Office API.

    Sử dụng API: /api/personnel/profile/gets
    Filter theo:
    - birthday_now trong khoảng tuần
    - job_status = "Đang làm việc"
    """

    # 1Office API endpoint
    API_BASE_URL = "https://innojsc.1office.vn/api/personnel/profile/gets"

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="birthday"))
        self._access_token: Optional[str] = None

    @property
    def name(self) -> str:
        return "birthday"

    async def initialize(self) -> None:
        """Initialize provider with 1Office Personnel token"""
        # Use ONEOFFICE_PERSONNEL_TOKEN for personnel API (different from work API token)
        # Fall back to ONEOFFICE_TOKEN if personnel token not set
        personnel_token = settings.ONEOFFICE_PERSONNEL_TOKEN.get_secret_value() if settings.ONEOFFICE_PERSONNEL_TOKEN else ""
        if personnel_token:
            self._access_token = personnel_token
            logger.info("Birthday provider using ONEOFFICE_PERSONNEL_TOKEN")
        else:
            self._access_token = settings.ONEOFFICE_TOKEN.get_secret_value() if settings.ONEOFFICE_TOKEN else None
            logger.info("Birthday provider using ONEOFFICE_TOKEN (fallback)")

        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )

        if not self._access_token:
            logger.warning("No token configured for Birthday provider")
            self._status = ProviderStatus.UNAVAILABLE
        else:
            self._status = ProviderStatus.HEALTHY
            logger.info("Birthday provider initialized with 1Office API")

    async def health_check(self) -> ProviderStatus:
        """Check 1Office API connectivity"""
        if not self._access_token:
            self._status = ProviderStatus.UNAVAILABLE
            return self._status

        try:
            session = await self.get_http_session()
            async with session.get(
                self.API_BASE_URL,
                params={"access_token": self._access_token},
                timeout=aiohttp.ClientTimeout(total=5)
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
        week: str = "this"
    ) -> Optional[Dict[str, Any]]:
        """
        Lấy danh sách sinh nhật từ 1Office API.

        Approach: Fetch all employees, then filter client-side by:
        - job_status = "Đang làm việc"
        - birthday_now within week range

        Args:
            week: "this" for current week, "next" for next week, "next_next" for week after next

        Returns:
            Dict with 'employees' list and week range info
        """
        if not self._access_token:
            return {"error": "1Office token not configured"}

        try:
            # Calculate week range
            start_date, end_date = _get_week_range(week)

            # Build URL directly with raw JSON filters (not URL-encoded)
            # Format: filters=[{"job_status":["WORKING","LEAVING"]}]
            filters_json = '[{"job_status":["WORKING","LEAVING"]}]'
            url = f"{self.API_BASE_URL}?access_token={self._access_token}&filters={filters_json}"

            logger.info(f"Birthday API URL: {url}")

            session = await self.get_http_session()
            async with session.get(url) as response:
                # Check content type before parsing
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' not in content_type:
                    # API returned HTML instead of JSON - log the response for debugging
                    html_content = await response.text()
                    logger.error(f"Birthday API returned HTML instead of JSON. Content-Type: {content_type}")
                    logger.error(f"HTML response (first 500 chars): {html_content[:500]}")
                    return {"error": f"API returned HTML instead of JSON. Check token/permissions."}

                response.raise_for_status()
                api_data = await response.json()

                if api_data.get("error") == True:
                    return {"error": api_data.get("message", "API error")}

                # Filter and transform on client-side
                # Valid job statuses: WORKING='Đang làm việc', LEAVING='Nghỉ thai sản'
                valid_job_statuses = ["Đang làm việc", "Nghỉ thai sản"]
                employees = []
                for person in api_data.get("data", []):
                    # Skip if not a valid working status
                    job_status = person.get("job_status", "")
                    if job_status not in valid_job_statuses:
                        continue

                    # Parse birthday_now (dd/MM/yyyy format)
                    birthday_str = person.get("birthday_now", "")
                    if not birthday_str:
                        continue

                    try:
                        birthday_date = datetime.strptime(birthday_str, "%d/%m/%Y")
                    except ValueError:
                        continue

                    # Check if birthday is within week range
                    # Compare only month and day (birthday_now already has current year)
                    if not (start_date.date() <= birthday_date.date() <= end_date.date()):
                        continue

                    day_of_week = WEEKDAY_NAMES.get(birthday_date.weekday(), "")

                    employees.append({
                        "name": person.get("name", "N/A"),
                        "birthDate": birthday_str,
                        "dayOfWeek": day_of_week,
                        "department": person.get("department_id", ""),
                        "code": person.get("code", ""),
                        "job_status": job_status
                    })

                # Sort by birthday date
                def sort_key(emp):
                    try:
                        return datetime.strptime(emp["birthDate"], "%d/%m/%Y")
                    except (ValueError, KeyError):
                        return datetime.max

                employees.sort(key=sort_key)

                logger.info(f"Birthday API: Found {len(employees)} employees with birthday in {week} week ({_format_date_for_api(start_date)} - {_format_date_for_api(end_date)})")

                return {
                    "employees": employees,
                    "weekRange": {
                        "start": _format_date_for_api(start_date),
                        "end": _format_date_for_api(end_date)
                    },
                    "week": week,
                    "total": len(employees)
                }

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error fetching birthdays: {e}")
            return {"error": f"Connection error: {str(e)}"}
        except Exception as e:
            logger.error(f"Error fetching birthdays: {e}", exc_info=True)
            return {"error": str(e)}

    def format_birthday_list(
        self,
        birthday_data: Dict[str, Any],
        week_label: str = "TUẦN NÀY"
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

        week_range = birthday_data.get('weekRange', {})
        start = week_range.get('start', '')
        end = week_range.get('end', '')

        message = f"🎂 *SINH NHẬT {week_label}* ({start} - {end})\n\n"

        for emp in employees:
            name = emp.get('name', 'N/A')
            birth_date = emp.get('birthDate', 'N/A')
            day_of_week = emp.get('dayOfWeek', '')
            department = emp.get('department', '')

            dept_str = f" ({department})" if department else ""

            message += f"🎈 *{name}*{dept_str}\n"
            message += f"   📅 {day_of_week}, {birth_date}\n\n"

        message += f"*Tổng cộng: {len(employees)} người*"
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
        week: str = "this"
    ) -> str:
        """
        Get combined birthday list and public announcement.

        Args:
            birthday_data: Data from get_birthdays()
            week: "this", "next", or "next_next"

        Returns:
            Combined message with list and announcement template
        """
        week_labels = {
            "this": "TUẦN NÀY",
            "next": "TUẦN SAU",
            "next_next": "TUẦN SAU NỮA"
        }
        week_label = week_labels.get(week, "TUẦN NÀY")

        list_message = self.format_birthday_list(birthday_data, week_label)
        public_message = self.format_public_announcement(birthday_data)

        return f"{list_message}\n---\n\n📝 *Mẫu tin nhắn chúc mừng gợi ý:*\n\n{public_message}"
