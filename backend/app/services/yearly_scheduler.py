# app/services/yearly_scheduler.py
"""
Yearly Task Scheduler
=====================
Service quản lý lịch công việc theo năm (Q1-Q4).
Hỗ trợ:
- Ngày cố định (fixed): "15/01"
- Ngày tương đối (relative): "trước Tết 30 ngày"

Tính năng:
- Load lịch từ JSON files theo quý
- Tính ngày thực tế từ anchor (Tết, Trung Thu, Quốc Khánh...)
- Đăng ký APScheduler jobs cho từng task
- Theo dõi trạng thái task qua state.json
"""

import json
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from app.core.logging import logger
from app.core.settings import settings

# Directory chứa schedule files
SCHEDULES_DIR = Path(__file__).parent.parent / "data" / "schedules"
STATE_FILE = SCHEDULES_DIR / "state.json"


# ==========================================
# LUNAR CALENDAR - Vietnamese Anchors
# ==========================================

# Ngày Tết Nguyên Đán (Mùng 1 Tết) - Dương lịch cho từng năm
# Có thể hardcode hoặc dùng lunardate library
# Hardcode cho 2025-2030 để không phụ thuộc external library
TET_NGUYEN_DAN_DATES = {
    2025: date(2025, 1, 29),
    2026: date(2026, 2, 17),
    2027: date(2027, 2, 6),
    2028: date(2028, 1, 26),
    2029: date(2029, 2, 13),
    2030: date(2030, 2, 3),
}

# Tết Trung Thu (15/8 Âm lịch) - Dương lịch
TET_TRUNG_THU_DATES = {
    2025: date(2025, 10, 6),
    2026: date(2026, 9, 25),
    2027: date(2027, 10, 15),
    2028: date(2028, 10, 3),
    2029: date(2029, 9, 22),
    2030: date(2030, 10, 11),
}

# Giỗ Tổ Hùng Vương (10/3 Âm lịch) - Dương lịch
GIO_TO_HUNG_VUONG_DATES = {
    2025: date(2025, 4, 7),
    2026: date(2026, 3, 28),
    2027: date(2027, 4, 16),
    2028: date(2028, 4, 4),
    2029: date(2029, 4, 23),
    2030: date(2030, 4, 13),
}

# Các anchor cố định (Dương lịch) - chỉ cần ngày/tháng
FIXED_ANCHORS = {
    "tet_duong_lich": (1, 1),       # Tết Dương lịch
    "quoc_te_phu_nu": (3, 8),       # Ngày Quốc tế Phụ nữ
    "giai_phong": (4, 30),          # Ngày Giải phóng miền Nam
    "quoc_te_lao_dong": (5, 1),     # Ngày Quốc tế Lao động
    "quoc_khanh": (9, 2),           # Quốc Khánh
    "phu_nu_vn": (10, 20),          # Ngày Phụ nữ Việt Nam
    "nha_giao": (11, 20),           # Ngày Nhà giáo Việt Nam
    "noel": (12, 25),               # Giáng sinh
}

# Các anchor Âm lịch (tra bảng)
LUNAR_ANCHOR_TABLES = {
    "tet_nguyen_dan": TET_NGUYEN_DAN_DATES,
    "tet_trung_thu": TET_TRUNG_THU_DATES,
    "gio_to_hung_vuong": GIO_TO_HUNG_VUONG_DATES,
}


def resolve_anchor_date(anchor: str, year: int) -> Optional[date]:
    """
    Tính ngày Dương lịch thực tế cho một anchor.

    Args:
        anchor: Tên anchor (tet_nguyen_dan, quoc_khanh, tet_trung_thu, ...)
        year: Năm cần tính

    Returns:
        date hoặc None nếu không tìm thấy
    """
    # Kiểm tra anchor Âm lịch
    if anchor in LUNAR_ANCHOR_TABLES:
        table = LUNAR_ANCHOR_TABLES[anchor]
        if year in table:
            return table[year]
        # Thử dùng lunardate nếu không có trong bảng
        try:
            from lunardate import LunarDate
            if anchor == "tet_nguyen_dan":
                return LunarDate(year, 1, 1).toSolarDate()
            elif anchor == "tet_trung_thu":
                return LunarDate(year, 8, 15).toSolarDate()
            elif anchor == "gio_to_hung_vuong":
                return LunarDate(year, 3, 10).toSolarDate()
        except ImportError:
            logger.warning(f"lunardate not installed, no data for {anchor} year {year}")
            return None
        except Exception as e:
            logger.error(f"Error calculating lunar date for {anchor}/{year}: {e}")
            return None

    # Kiểm tra anchor Dương lịch
    if anchor in FIXED_ANCHORS:
        month, day = FIXED_ANCHORS[anchor]
        return date(year, month, day)

    logger.warning(f"Unknown anchor: {anchor}")
    return None


def resolve_task_date(time_config: Dict[str, Any], year: int) -> Optional[date]:
    """
    Tính ngày thực tế cho một task dựa trên config.

    Args:
        time_config: {"type": "fixed", "date": "15/01"} hoặc
                     {"type": "relative", "anchor": "tet_nguyen_dan", "offset_days": -30}
        year: Năm cần tính

    Returns:
        date hoặc None
    """
    if time_config["type"] == "fixed":
        try:
            day_month = time_config["date"]  # "15/01"
            day, month = day_month.split("/")
            return date(year, int(month), int(day))
        except (ValueError, KeyError) as e:
            logger.error(f"Invalid fixed date: {time_config}, error: {e}")
            return None

    elif time_config["type"] == "relative":
        anchor = time_config.get("anchor")
        offset_days = time_config.get("offset_days", 0)

        anchor_date = resolve_anchor_date(anchor, year)
        if anchor_date is None:
            return None

        return anchor_date + timedelta(days=offset_days)

    return None


# ==========================================
# STATE MANAGEMENT
# ==========================================

def load_state() -> Dict[str, Any]:
    """Load trạng thái các yearly tasks từ state.json"""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading yearly tasks state: {e}")
    return {}


def save_state(state: Dict[str, Any]) -> None:
    """Lưu trạng thái các yearly tasks"""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error saving yearly tasks state: {e}")


def get_task_state(task_id: str) -> Dict[str, Any]:
    """Lấy trạng thái của một task"""
    state = load_state()
    return state.get(task_id, {
        "status": "pending",
        "oneoffice_task_id": None,
        "notified_at": None,
        "created_at": None,
        "completed_at": None,
        "skipped_at": None,
    })


def update_task_state(task_id: str, updates: Dict[str, Any]) -> None:
    """Cập nhật trạng thái một task"""
    state = load_state()
    if task_id not in state:
        state[task_id] = {
            "status": "pending",
            "oneoffice_task_id": None,
            "notified_at": None,
            "created_at": None,
            "completed_at": None,
            "skipped_at": None,
        }
    state[task_id].update(updates)
    save_state(state)


# ==========================================
# SCHEDULE LOADING
# ==========================================

def load_quarter_schedule(quarter: str) -> Optional[Dict[str, Any]]:
    """
    Load lịch công việc cho một quý.

    Args:
        quarter: "Q1", "Q2", "Q3", hoặc "Q4"

    Returns:
        Dict với danh sách tasks hoặc None
    """
    file_path = SCHEDULES_DIR / f"{quarter}.json"
    try:
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading schedule {quarter}: {e}")
    return None


def load_all_schedules() -> Dict[str, Any]:
    """Load tất cả lịch Q1-Q4"""
    schedules = {}
    for q in ["Q1", "Q2", "Q3", "Q4"]:
        data = load_quarter_schedule(q)
        if data:
            schedules[q] = data
    return schedules


def get_all_tasks_with_dates(year: int = None) -> List[Dict[str, Any]]:
    """
    Lấy tất cả tasks với ngày thực tế đã tính.

    Returns:
        List of task dicts, mỗi task có thêm 'resolved_date' và 'resolved_deadline'
    """
    if year is None:
        year = datetime.now().year

    schedules = load_all_schedules()
    state = load_state()
    result = []

    for quarter, schedule in schedules.items():
        for task in schedule.get("tasks", []):
            task_copy = task.copy()
            task_copy["quarter"] = quarter

            # Resolve dates
            task_copy["resolved_date"] = resolve_task_date(task["time"], year)
            task_copy["resolved_deadline"] = resolve_task_date(task["deadline"], year)

            # Add remind date
            remind_before = task["time"].get("remind_before_days", 0)
            if task_copy["resolved_date"] and remind_before:
                task_copy["resolved_remind_date"] = (
                    task_copy["resolved_date"] - timedelta(days=remind_before)
                )
            else:
                task_copy["resolved_remind_date"] = task_copy["resolved_date"]

            # Add state
            task_state = state.get(task["id"], {"status": "pending"})
            task_copy["state"] = task_state

            result.append(task_copy)

    # Sort by resolved_date
    result.sort(key=lambda t: t.get("resolved_date") or date.max)
    return result


def get_upcoming_tasks(days: int = 14, year: int = None) -> List[Dict[str, Any]]:
    """
    Lấy các tasks sắp tới trong N ngày.

    Args:
        days: Số ngày tới để tìm
        year: Năm (mặc định: năm hiện tại)

    Returns:
        List of upcoming tasks
    """
    today = date.today()
    cutoff = today + timedelta(days=days)
    all_tasks = get_all_tasks_with_dates(year)

    return [
        t for t in all_tasks
        if t.get("resolved_date")
        and today <= t["resolved_date"] <= cutoff
        and t["state"].get("status") in ("pending", "notified")
    ]


def get_tasks_needing_notification(year: int = None) -> List[Dict[str, Any]]:
    """
    Lấy các tasks cần gửi notification hôm nay.

    Một task cần notification khi:
    - resolved_remind_date <= today
    - status == "pending" (chưa gửi notification)
    """
    today = date.today()
    all_tasks = get_all_tasks_with_dates(year)

    return [
        t for t in all_tasks
        if t.get("resolved_remind_date")
        and t["resolved_remind_date"] <= today
        and t.get("resolved_date") and t["resolved_date"] >= today
        and t["state"].get("status") == "pending"
    ]


def get_tasks_near_deadline(hours: int = 24, year: int = None) -> List[Dict[str, Any]]:
    """
    Lấy các tasks sắp đến deadline (đã tạo trên 1Office).

    Args:
        hours: Số giờ trước deadline
        year: Năm
    """
    today = date.today()
    cutoff_date = today + timedelta(days=hours // 24 + 1)
    all_tasks = get_all_tasks_with_dates(year)

    return [
        t for t in all_tasks
        if t.get("resolved_deadline")
        and today <= t["resolved_deadline"] <= cutoff_date
        and t["state"].get("status") == "created"
    ]


# ==========================================
# SCHEDULER REGISTRATION
# ==========================================

async def register_yearly_jobs(scheduler, app_session=None) -> int:
    """
    Đăng ký APScheduler jobs cho yearly tasks.
    Gọi 1 lần khi startup.

    Đăng ký 2 loại job hàng ngày:
    1. Check tasks cần notification (8:30 sáng)
    2. Check tasks gần deadline (15:00 chiều)

    Args:
        scheduler: APScheduler AsyncIOScheduler instance
        app_session: aiohttp ClientSession

    Returns:
        Số jobs đã đăng ký
    """
    from app.services.scheduler_tasks import (
        check_yearly_task_notifications,
        check_yearly_deadline_reminders,
    )

    # Job 1: Kiểm tra tasks cần gửi notification - mỗi ngày lúc 8:30
    scheduler.add_job(
        check_yearly_task_notifications,
        'cron',
        hour=8, minute=30,
        misfire_grace_time=600,
        id='yearly_task_notifications',
        replace_existing=True,
    )

    # Job 2: Kiểm tra tasks gần deadline - mỗi ngày lúc 15:00
    scheduler.add_job(
        check_yearly_deadline_reminders,
        'cron',
        hour=15, minute=0,
        misfire_grace_time=600,
        id='yearly_deadline_reminders',
        replace_existing=True,
    )

    # Load và log thông tin
    all_tasks = get_all_tasks_with_dates()
    upcoming = get_upcoming_tasks(days=30)

    logger.info(f"📅 Yearly Scheduler: Loaded {len(all_tasks)} tasks total")
    logger.info(f"📅 Yearly Scheduler: {len(upcoming)} tasks upcoming in next 30 days")

    for task in upcoming:
        rd = task.get('resolved_date')
        logger.info(f"  📌 {task['id']}: {task['title']} → {rd.strftime('%d/%m/%Y') if rd else 'N/A'}")

    return 2  # Number of scheduler jobs registered
