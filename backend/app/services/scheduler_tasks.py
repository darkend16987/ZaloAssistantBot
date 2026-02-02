# app/services/scheduler_tasks.py
import httpx
from datetime import datetime, timedelta
from typing import Dict, Optional
import aiohttp

from app.core.settings import settings
from app.core.logging import logger
from app.services import oneoffice, zalo
from app.services.task_flows import format_tasks_message
from app.services.birthday_templates import format_public_birthday_message

# We need a shared session or create new ones.
# Since these are async tasks run by scheduler, passing a session is tricky unless scheduler Context has it.
# We will create ephemeral sessions or use a global one if initialized.
# Ideally, the scheduler setup should pass the session.
# For simplicity in this refactor, I will accept an optional session or create one.

async def fetch_birthdays_from_sheets(week: str = "next") -> Optional[Dict]:
    """Calls Google Apps Script to get birthdays. week can be 'this' or 'next'."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            url = f"{settings.GOOGLE_APPS_SCRIPT_URL}?week={week}"
            response = await client.get(
                url,
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Fetched birthdays from Google Sheets: {len(data.get('employees', []))} people")
                return data
            else:
                logger.error(f"❌ Error calling Google Sheets API: {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"❌ Unknown error fetching birthdays: {e}")
        return None

def format_birthday_message(birthday_data: Dict) -> str:
    employees = birthday_data.get('employees', [])
    if not employees: return ""
    
    next_week_range = birthday_data.get('nextWeekRange', {})
    start = next_week_range.get('start', '')
    end = next_week_range.get('end', '')
    
    message = f"🎂 *THÔNG BÁO SINH NHẬT TUẦN SAU*\n📅 Từ {start} đến {end}\n" + "=" * 40 + "\n\n"
    
    grouped = {}
    for emp in employees:
        grouped.setdefault(emp['birthDate'], []).append(emp)
    
    for date_str in sorted(grouped.keys(), key=lambda d: datetime.strptime(d, '%d/%m/%Y')):
        day_emps = grouped[date_str]
        day_of_week = day_emps[0]['dayOfWeek']
        message += f"📌 *{day_of_week}, {date_str}:*\n"
        for emp in day_emps:
            message += f"   🎉 {emp['name']} ({emp['department']}) - {emp.get('age', '?')} tuổi\n"
        message += "\n"
    
    message += "=" * 40 + "\n" + f"📊 Tổng cộng: *{len(employees)} nhân viên*\n💡 Nhớ chuẩn bị quà hoặc gửi lời chúc nhé!"
    return message

async def send_birthday_notifications():
    logger.info("🎂 Scheduler (Birthday): Checking for next week's birthdays...")
    birthday_data = await fetch_birthdays_from_sheets()
    if not birthday_data or birthday_data.get('error'): return
    
    employees = birthday_data.get('employees', [])
    if not employees:
        logger.info("ℹ️ No birthdays next week.")
        return
    
    # 1. Send Admin / Internal Report (existing)
    message = format_birthday_message(birthday_data)
    if message:
        await zalo.send_zalo_message(message, settings.MY_ZALO_ID)

    # 2. Send Public Announcement Draft (new)
    public_message = format_public_birthday_message(birthday_data)
    if public_message:
        # Add a prefix to explain what this is
        wrapper_msg = f"📝 *DRAFT CONTENT FOR PUBLIC POST:*\n(Copy & Paste below)\n\n{public_message}"
        await zalo.send_zalo_message(wrapper_msg, settings.MY_ZALO_ID)

async def getattr_session(app_ref=None):
    # This acts as a bridge to get session from app if provided, or create new
    if app_ref and hasattr(app_ref, 'aiohttp_session'):
        return app_ref.aiohttp_session
    return aiohttp.ClientSession()

async def send_daily_briefing(app_session=None):
    logger.info("Scheduler (Daily Briefing): Sending daily tasks report...")
    today_str = datetime.now().strftime('%d/%m/%Y')
    filters = {
        "assign_ids": settings.DEFAULT_ASSIGNEE_ID,
        "status": ["DOING", "PENDING"],
        "end_plan_from": today_str,
        "end_plan_to": today_str
    }
    
    # Handle session lifecycle locally if not provided
    is_local_session = app_session is None
    session = app_session if not is_local_session else aiohttp.ClientSession()
    
    try:
        tasks_data = await oneoffice.get_tasks_data(session, filters_override=filters)
        if tasks_data and tasks_data.get("total_item", 0) > 0:
            message = format_tasks_message(tasks_data, title=f"☀️ Alo, ông có đống việc này phải xong trong hôm nay ({today_str}) này:")
            await zalo.send_zalo_message(message, settings.MY_ZALO_ID)
        else:
            logger.info("Scheduler (Daily Briefing): No tasks due today.")
    finally:
        if is_local_session: await session.close()

async def send_general_task_update(app_session=None):
    logger.info("Scheduler (General Update): Sending periodic report...")
    filters = {"assign_ids": settings.DEFAULT_ASSIGNEE_ID, "status": ["DOING", "PENDING"]}
    
    is_local_session = app_session is None
    session = app_session if not is_local_session else aiohttp.ClientSession()
    
    try:
        tasks_data = await oneoffice.get_tasks_data(session, filters_override=filters)
        if tasks_data and tasks_data.get("total_item", 0) > 0:
            message = format_tasks_message(tasks_data, title=f"📢 Alo bro, đây là tình hình công việc hiện tại của ông:") + "\n\nCần tôi hỗ trợ gì không?"
            await zalo.send_zalo_message(message, settings.MY_ZALO_ID)
        else:
            logger.info("Scheduler (General Update): No active tasks.")
    finally:
        if is_local_session: await session.close()

async def send_daily_wrap_up(app_session=None):
    logger.info("Scheduler (Daily Wrap-up): Sending end-of-day report...")
    filters = {"assign_ids": settings.DEFAULT_ASSIGNEE_ID, "status": ["DOING", "PENDING"]}
    
    is_local_session = app_session is None
    session = app_session if not is_local_session else aiohttp.ClientSession()
    
    try:
        tasks_data = await oneoffice.get_tasks_data(session, filters_override=filters)
        if tasks_data and tasks_data.get("total_item", 0) > 0:
            message = format_tasks_message(tasks_data, title="🌙 Ơn zời, hết ngày rồi, Đây là chỗ việc còn lại:") + "\n\nBro xem có cái nào đã xong mà chưa đổi stt không?"
            await zalo.send_zalo_message(message, settings.MY_ZALO_ID)
        else:
            logger.info("Scheduler (Daily Wrap-up): No active tasks.")
    finally:
        if is_local_session: await session.close()

async def check_deadline_reminders(app_session=None):
    logger.info("Scheduler (Urgent Reminder): Scanning for urgent tasks...")
    filters = {"assign_ids": settings.DEFAULT_ASSIGNEE_ID, "status": ["DOING", "PENDING"]}
    
    is_local_session = app_session is None
    session = app_session if not is_local_session else aiohttp.ClientSession()
    
    try:
        tasks_data = await oneoffice.get_tasks_data(session, filters_override=filters)
        tasks = tasks_data.get("data", []) if tasks_data else []
        if not tasks: return

        now = datetime.now()
        reminder_window = now + timedelta(minutes=30)
        tasks_to_remind = []

        for task in tasks:
            time_end_plan_str = task.get('time_end_plan')
            if not time_end_plan_str: continue 
            end_plan_str = task.get('end_plan', '')
            full_deadline_str = f"{end_plan_str} {time_end_plan_str}".strip()

            try:
                deadline_dt = datetime.strptime(full_deadline_str, '%d/%m/%Y %H:%M:%S')
            except ValueError:
                try:
                    deadline_dt = datetime.strptime(full_deadline_str, '%d/%m/%Y %H:%M')
                except ValueError: continue

            if now <= deadline_dt <= reminder_window:
                tasks_to_remind.append(task)

        if not tasks_to_remind: return

        tasks_to_remind.sort(key=lambda t: t.get('time_end_plan', ''))
        msg = "⏰ *Cảnh báo! Alo Alo, Các việc sau sắp phải xong rồi nhé:* \n"
        for task in tasks_to_remind:
            msg += f"\n- *{task.get('title', 'No Title')}*\n  _Hạn chót: {task.get('end_plan')} {task.get('time_end_plan')}_"
        
        await zalo.send_zalo_message(msg, settings.MY_ZALO_ID)
        logger.info(f"Scheduler (Urgent Reminder): Sent warnings for {len(tasks_to_remind)} tasks.")
    finally:
        if is_local_session: await session.close()
