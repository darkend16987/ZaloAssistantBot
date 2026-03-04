# app/services/scheduler_tasks.py
import httpx
from datetime import datetime, timedelta
from typing import Dict, Optional
import aiohttp

from app.core.settings import settings
from app.core.logging import logger
from app.services import oneoffice, zalo
from app.services.task_flows import format_tasks_message
# from app.services.birthday_templates import format_public_birthday_message

# We need a shared session or create new ones.
# Since these are async tasks run by scheduler, passing a session is tricky unless scheduler Context has it.
# We will create ephemeral sessions or use a global one if initialized.
# Ideally, the scheduler setup should pass the session.
# For simplicity in this refactor, I will accept an optional session or create one.

from app.mcp.core.provider_registry import provider_registry

async def send_birthday_notifications():
    logger.info("🎂 Scheduler (Birthday): Checking for next week's birthdays...")
    
    # Get birthday provider from registry
    birthday_provider = provider_registry.get("birthday")
    if not birthday_provider:
        logger.error("❌ Birthday provider not found or not initialized.")
        return

    # Fetch next week's birthdays
    birthday_data = await birthday_provider.get_birthdays(week="next")
    
    if not birthday_data or birthday_data.get('error'):
        logger.error(f"❌ Failed to get birthday data: {birthday_data.get('error') if birthday_data else 'Unknown error'}")
        return
    
    employees = birthday_data.get('employees', [])
    if not employees:
        logger.info("ℹ️ No birthdays next week.")
        return
    
    # Generate combined message (Internal List + Public Draft)
    message = birthday_provider.get_combined_birthday_message(birthday_data, week="next")
    
    if message:
        await zalo.send_zalo_message(message, settings.MY_ZALO_ID)
        logger.info(f"✅ Sent birthday notification for {len(employees)} employees.")

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


# ==========================================
# YEARLY TASK SCHEDULER NOTIFICATIONS
# ==========================================

async def check_yearly_task_notifications():
    """
    Kiểm tra và gửi notification cho các yearly tasks cần nhắc hôm nay.
    Chạy mỗi ngày lúc 8:30 sáng.
    """
    from app.services.yearly_scheduler import get_tasks_needing_notification
    from app.core.sessions import add_to_conversation_history

    logger.info("📅 Scheduler (Yearly): Checking for tasks needing notification...")

    tasks = get_tasks_needing_notification()
    if not tasks:
        logger.info("📅 Scheduler (Yearly): No tasks need notification today.")
        return

    yearly_provider = provider_registry.get("yearly_schedule")

    for task in tasks:
        rd = task.get("resolved_date")
        dl = task.get("resolved_deadline")

        date_str = rd.strftime("%d/%m/%Y") if rd else "N/A"
        dl_str = dl.strftime("%d/%m/%Y") if dl else "N/A"

        from datetime import date as date_type
        days_left = (rd - date_type.today()).days if rd else 0

        msg = (
            f"📋 *Đã đến lịch công việc theo năm:*\n\n"
            f"📌 *{task['title']}*\n"
            f"📝 {task.get('description', '')}\n"
            f"📆 Ngày thực hiện: {date_str} (còn {days_left} ngày)\n"
            f"⏰ Deadline: {dl_str}\n"
        )

        assignees = task.get("assignees", [])
        if assignees:
            msg += f"👤 Người thực hiện: {', '.join(assignees)}\n"

        template = task.get("template", {})
        if template.get("content"):
            msg += f"\n📄 Nội dung: {template['content']}\n"
        if template.get("link"):
            msg += f"🔗 Tài liệu: {template['link']}\n"

        msg += (
            f"\n🆔 ID: `{task['id']}`\n"
            f"\n👉 Trả lời *xác nhận tạo {task['id']}* để tạo công việc trên 1Office"
            f"\n👉 Hoặc *bỏ qua {task['id']}* để bỏ qua"
        )

        await zalo.send_zalo_message(msg, settings.MY_ZALO_ID)

        add_to_conversation_history(
            user_id=settings.MY_ZALO_ID,
            user_message="[Hệ thống nhắc lịch công việc năm]",
            assistant_response=msg,
        )

        if yearly_provider:
            yearly_provider.mark_task_notified(task["id"])

        logger.info(f"📅 Scheduler (Yearly): Sent notification for {task['id']}: {task['title']}")

    logger.info(f"📅 Scheduler (Yearly): Notified {len(tasks)} tasks.")


async def check_yearly_deadline_reminders():
    """
    Kiểm tra yearly tasks sắp đến deadline (đã tạo trên 1Office).
    Chạy mỗi ngày lúc 15:00.
    """
    from app.services.yearly_scheduler import get_tasks_near_deadline

    logger.info("📅 Scheduler (Yearly Deadline): Checking for approaching deadlines...")

    tasks = get_tasks_near_deadline(hours=48)
    if not tasks:
        logger.info("📅 Scheduler (Yearly Deadline): No yearly tasks near deadline.")
        return

    for task in tasks:
        dl = task.get("resolved_deadline")
        dl_str = dl.strftime("%d/%m/%Y") if dl else "N/A"
        state = task.get("state", {})
        oo_id = state.get("oneoffice_task_id", "N/A")

        from datetime import date as date_type
        days_left = (dl - date_type.today()).days if dl else 0

        msg = (
            f"⚠️ *Nhắc deadline công việc theo lịch năm:*\n\n"
            f"📌 *{task['title']}*\n"
            f"⏰ Deadline: {dl_str} (còn {days_left} ngày)\n"
            f"🔹 1Office ID: `{oo_id}`\n"
            f"🆔 Yearly ID: `{task['id']}`\n"
            f"\n👉 Trả lời *hoàn thành {task['id']}* nếu đã xong"
        )

        await zalo.send_zalo_message(msg, settings.MY_ZALO_ID)
        logger.info(f"📅 Scheduler (Yearly Deadline): Reminder for {task['id']}: {task['title']}")
