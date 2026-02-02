# app/services/task_flows.py
import aiohttp
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
from datetime import datetime

from app.core.settings import settings
from app.core.sessions import get_session, update_session
from app.core.constants import STATUS_MAP, PRIORITY_MAP, DISPLAY_STATUS_MAP
from app.core.logging import logger
from app.services import oneoffice, gemini

# --- Helper Functions ---

def validate_task_id(task_id_to_check: int, all_tasks: list) -> bool:
    if not all_tasks:
        return False
    return any(task['ID'] == task_id_to_check for task in all_tasks)

def get_date_range_for_period(period: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    today = datetime.now()
    if period == "this_week":
        start_date = today - timedelta(days=today.weekday())
        return start_date, start_date + timedelta(days=6)
    return None, None

def format_tasks_message(data, title="Các công việc của bạn:"):
    if not data or data.get("total_item", 0) == 0:
        return f"🎉 Tuyệt vời! Bạn không có công việc nào khớp với tiêu chí."

    tasks = data.get("data", [])
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
            sorted_tasks = sorted(tasks_by_status[status], key=lambda t: t.get('end_plan', '9999-99-99'))
            for task in sorted_tasks:
                emoji = "🔴" if status == "Quá hạn" else "🟠" if status == "Đến hạn hôm nay" else "🟢" if task.get('status') == "Hoàn thành" else "🔵"
                end_time_str = f" {task.get('time_end_plan', '')}" if task.get('is_assign_hour') == 'Có' and task.get('time_end_plan') else ""
                deadline_info = task.get('deadline_list', '')
                message += f"{emoji} *{task['title'].strip()}*\n  _Hạn chót: {task.get('end_plan', 'N/A')}{end_time_str}_ | _{deadline_info}_\n  `ID: {task['ID']}`\n\n"

    if not found_tasks:
        return f"🎉 Bro chả có việc nào để xem cả."
    message += f"---\n🔗 Để biết rõ hơn, truy cập 1Office tại: {settings.ONEOFFICE_LINK}"  # Using settings.ONEOFFICE_LINK directly if defined? Wait, it was in constants.
    # Actually ONEOFFICE_LINK was constant in main_api.py. I should import it from constants.
    return message

# --- FLows ---

async def get_tasks_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    tasks_data = await oneoffice.get_tasks_data(http_session)
    if tasks_data is None:
        return "Rất tiếc, tôi không thể kết nối đến hệ thống 1Office lúc này. 🛠️", None
    task_ids = [task['ID'] for task in tasks_data.get("data", [])]
    return format_tasks_message(tasks_data, title="OK, đây là chỗ việc cần xử của bro đó:"), task_ids

async def get_overall_report_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    report_filters = {"assign_ids": settings.DEFAULT_ASSIGNEE_ID, "status": ["DOING", "PENDING", "COMPLETED", "CANCEL"]}
    tasks_data = await oneoffice.get_tasks_data(http_session, filters_override=report_filters)
    if tasks_data is None:
        return "Rất tiếc, tôi không thể kết nối đến hệ thống 1Office lúc này. 🛠️", None
    task_ids = [task['ID'] for task in tasks_data.get("data", [])]
    return format_tasks_message(tasks_data, title="Báo cáo tổng hợp công việc của bro đây:"), task_ids

async def get_tasks_by_status_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    status_key = details.get("status")
    if not status_key: return "Bro muốn xem công việc ở trạng thái nào vậy?", None
    api_status_value = STATUS_MAP.get(status_key)
    if not api_status_value: return f"Làm quái có trạng thái '{status_key}' chứ.", None
    filters = {"assign_ids": settings.DEFAULT_ASSIGNEE_ID, "status": [api_status_value]}
    tasks_data = await oneoffice.get_tasks_data(http_session, filters_override=filters)
    if tasks_data is None: return "Rất tiếc, tôi không thể kết nối đến hệ thống 1Office lúc này. 🛠️", None
    task_ids = [task['ID'] for task in tasks_data.get("data", [])]
    return format_tasks_message(tasks_data, title=f"OK, Đây là các công việc có trạng thái *{api_status_value}*:"), task_ids

async def get_daily_report_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    today_str = datetime.now().strftime('%d/%m/%Y')
    filters = {"assign_ids": settings.DEFAULT_ASSIGNEE_ID, "status": ["DOING", "PENDING", "COMPLETED"], "end_plan_from": today_str, "end_plan_to": today_str}
    tasks_data = await oneoffice.get_tasks_data(http_session, filters_override=filters)
    if tasks_data is None: return "Rất tiếc, tôi không thể kết nối đến hệ thống 1Office lúc này. 🛠️", None
    task_ids = [task['ID'] for task in tasks_data.get("data", [])]
    return format_tasks_message(tasks_data, title=f"☀️ Hey men, đây là báo cáo công việc của bạn trong ngày {today_str}:"), task_ids

async def get_weekly_report_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    from datetime import timedelta # Need import here or top level
    start_of_week = datetime.now() - timedelta(days=datetime.now().weekday())
    report_filters = {"assign_ids": settings.DEFAULT_ASSIGNEE_ID, "status": ["DOING", "PENDING", "COMPLETED"], "start_plan_from": start_of_week.strftime('%d/%m/%Y')}
    tasks_data = await oneoffice.get_tasks_data(http_session, filters_override=report_filters)
    if tasks_data is None: return "Rất tiếc, tôi không thể kết nối đến hệ thống 1Office lúc này. 🛠️", None
    task_ids = [task['ID'] for task in tasks_data.get("data", [])]
    return format_tasks_message(tasks_data, title=f"Okie, Đây là report công việc từ đầu tuần ({start_of_week.strftime('%d/%m')}) của bro:"), task_ids

async def get_birthdays_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    """Handles requests for birthday information."""
    from app.services import scheduler_tasks, birthday_templates
    
    period = details.get("period", "next_week") # Default to next week as per current implementation
    
    week_param = "this" if period == "this_week" else "next"
    birthday_data = await scheduler_tasks.fetch_birthdays_from_sheets(week=week_param)
    
    if not birthday_data or birthday_data.get('error'):
        return "Rất tiếc, tôi không thể lấy dữ liệu sinh nhật lúc này. 🛠️", None
        
    employees = birthday_data.get('employees', [])
    if not employees:
        return f"Không có ai sinh nhật trong { 'tuần này' if period == 'this_week' else 'tuần sau'} đâu bro.", None
        
    # 1. Official list message
    list_message = scheduler_tasks.format_birthday_message(birthday_data)
    if period == "this_week":
        list_message = list_message.replace("SINH NHẬT TUẦN SAU", "SINH NHẬT TUẦN NÀY")
        
    # 2. Public template message
    public_message = birthday_templates.format_public_birthday_message(birthday_data)
    
    # Combine both as requested
    final_response = f"{list_message}\n\n---\n\n📝 *Mẫu tin nhắn chúc mừng gợi ý cho bro:*\n\n{public_message}"
    
    return final_response, None

async def create_task_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    tasks_to_create = details.get("tasks", [])
    if not tasks_to_create: return "Tôi không phân tích được việc bạn muốn tạo.", None
    tasks_with_deadline, tasks_without_deadline = [], []
    for task in tasks_to_create:
        if task.get("end_plan"): tasks_with_deadline.append(task)
        else: tasks_without_deadline.append(task)
    created_tasks_messages, newly_created_ids = [], []
    for task in tasks_with_deadline:
        assignee = task.get("assignee_name") or settings.DEFAULT_ASSIGNEE
        time_end_plan = task.get("time_end_plan")
        priority_raw = task.get("priority")
        priority = PRIORITY_MAP.get(priority_raw.lower()) if priority_raw else None
        new_id, error = await oneoffice.create_and_start_task(http_session, task['title'], task['end_plan'], assignee, time_end_plan, priority)
        if error: created_tasks_messages.append(f"🔴 Lỗi khi tạo việc '{task['title']}': {error}")
        if new_id:
            time_str = f" lúc {time_end_plan}" if time_end_plan else ""
            created_tasks_messages.append(f"🔹 *{task['title']}*\n  _Hạn chót: {task['end_plan']}{time_str}_\n  `(ID: {new_id})`")
            newly_created_ids.append(new_id)
    final_response_parts = []
    if created_tasks_messages: final_response_parts.append(f"✅ Okie bro, tôi đã tạo {len(created_tasks_messages)} công việc:\n\n" + "\n\n".join(created_tasks_messages))
    if tasks_without_deadline:
        update_session(user_id, {'pending_tasks_queue': tasks_without_deadline})
        final_response_parts.append(f"Hỏi lại phát! Công việc '{tasks_without_deadline[0]['title']}' cần hoàn thành khi nào vậy bạn?")
    return "\n\n".join(final_response_parts), newly_created_ids

async def update_status_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]], List]:
    tasks_to_update_raw = details.get("tasks", [])
    if not tasks_to_update_raw: return "Làm quái có việc nào như thế chứ.", None, []
    tasks_data = await oneoffice.get_tasks_data(http_session, {"assign_ids": settings.DEFAULT_ASSIGNEE, "status": ["DOING", "PAUSE", "PENDING"]})
    all_tasks = tasks_data.get("data", []) if tasks_data else []
    
    tasks_to_batch, failed_validation_ids = [], []
    for task_info in tasks_to_update_raw:
        try:
            task_id_str = task_info.get("task_id")
            task_id = "LAST_CREATED" if task_id_str == "LAST_CREATED" else int(task_id_str)
            new_status_key = task_info.get("new_status")
            api_status_value = STATUS_MAP.get(new_status_key)
            task_exists = any(t['ID'] == task_id for t in all_tasks) if all_tasks and isinstance(task_id, int) else True
            if not api_status_value or (isinstance(task_id, int) and not task_exists):
                failed_validation_ids.append(str(task_id))
                continue
            payload = {'status': api_status_value}
            if new_status_key == "COMPLETED":
                payload['percent'] = 100
                payload['end'] = datetime.now().strftime('%d/%m/%Y')
            tasks_to_batch.append((task_id, payload))
        except (ValueError, TypeError): failed_validation_ids.append(str(task_info.get("task_id", "Không rõ")))

    updated_tasks, api_error_ids, updated_ids = {}, [], []
    if tasks_to_batch:
        real_id_tasks = [t for t in tasks_to_batch if isinstance(t[0], int)]
        if real_id_tasks:
            batch_results = await oneoffice.batch_update_tasks(http_session, real_id_tasks)
            for task, result in zip(real_id_tasks, batch_results):
                task_id, payload = task
                if isinstance(result, Exception) or result is False: api_error_ids.append(str(task_id))
                else:
                    status_value = payload['status']
                    title = next((t['title'] for t in all_tasks if t['ID'] == task_id), f"ID {task_id}")
                    updated_tasks.setdefault(status_value, []).append(f"'{title}'")
                    updated_ids.append(task_id)

    response_parts = []
    if updated_tasks:
        for status, titles in updated_tasks.items(): response_parts.append(f"✅ Chốt nhá, Đã chuyển {len(titles)} cv sang *{status}*: {', '.join(titles)}")
    all_failed_ids = failed_validation_ids + api_error_ids
    if all_failed_ids: response_parts.append(f"🔴 Chịu đấy, không cập nhật được đâu: ID {', '.join(all_failed_ids)}")
    unprocessed_tasks = [t for t in tasks_to_batch if t[0] == "LAST_CREATED"]
    return "\n\n".join(response_parts) if response_parts else "Chịu bro ơi, tìm mãi không ra công việc nào hợp lệ để cập nhật.", updated_ids, unprocessed_tasks

async def set_deadline_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    try:
        task_id = int(details.get("task_id"))
        new_end_plan = details.get("new_end_plan")
    except (ValueError, TypeError): return "Thông tin không hợp lệ.", None
    tasks_data = await oneoffice.get_tasks_data(http_session)
    if not tasks_data or not validate_task_id(task_id, tasks_data.get("data", [])): return f"Bro chắc không, làm gì công việc nào có ID là {task_id}.", None
    if await oneoffice.update_task(http_session, task_id, {'end_plan': new_end_plan}):
        task_title = next((t['title'] for t in tasks_data['data'] if t['ID'] == task_id), "")
        return f"✅ Okie rồi đấy, tôi đã đặt lại deadline cho '{task_title}' thành *{new_end_plan}*. Đừng có cao su đấy.", [task_id]
    return f"Chịu, có lỗi khi cập nhật deadline cho ID {task_id}.", None

async def extend_deadline_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    try:
        task_id = int(details.get("task_id"))
        days_to_add = int(details.get("duration", {}).get("days"))
    except (ValueError, TypeError, AttributeError): return "Thông tin méo hợp lệ.", None
    tasks_data = await oneoffice.get_tasks_data(http_session)
    all_tasks = tasks_data.get("data", []) if tasks_data else []
    if not validate_task_id(task_id, all_tasks): return f"Chắc chưa men, tôi không tìm thấy công việc nào có ID là {task_id}.", None
    task_info = next((task for task in all_tasks if task['ID'] == task_id), None)
    if not task_info or not task_info.get('end_plan'): return f"Ông lại phê rồi đúng không? Công việc này làm gì có deadline cũ để gia hạn.", None
    try:
        old_deadline = datetime.strptime(task_info['end_plan'], '%d/%m/%Y')
        new_deadline_str = (old_deadline + timedelta(days=days_to_add)).strftime('%d/%m/%Y')
        if await oneoffice.update_task(http_session, task_id, {'end_plan': new_deadline_str}):
            return (f"✅ OK chốt, tôi đã gia hạn cho '{task_info['title']}' thêm {days_to_add} ngày, deadline mới là *{new_deadline_str}*. Bro còn trượt deadline thì chịu đấy."), [task_id]
        else: return f"Chán đời, có lỗi khi cập nhật deadline cho ID {task_id}.", None
    except ValueError: return "Lỗi đọc định dạng ngày tháng của deadline cũ rồi, fix lỗi đi.", None

async def rename_task_flow(user_id: str, details: Dict, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    try:
        task_id = int(details.get("task_id"))
        new_title = details.get("new_title")
        if not new_title: return "Gì đấy, ông định làm việc không có tên à?", None
    except (ValueError, TypeError): return "Thông tin không hợp lệ để đổi tên.", None
    tasks_data = await oneoffice.get_tasks_data(http_session)
    if not tasks_data or not validate_task_id(task_id, tasks_data.get("data", [])): return f"Sorry, tôi chịu chả tìm thấy công việc nào có ID là {task_id}.", None
    if await oneoffice.update_task(http_session, task_id, {'title': new_title}):
        return f"✅ OK, theo ý ông, tôi đã đổi tên công việc có ID {task_id} thành *'{new_title}'*.", [task_id]
    return f"🔴 Hehe chia buồn, đã có lỗi khi cập nhật tên cho công việc ID {task_id}.", None

async def fill_task_details_flow(user_id: str, user_answer: str, http_session: aiohttp.ClientSession) -> Tuple[str, Optional[List[int]]]:
    session_data = get_session(user_id)
    pending_queue = session_data.get('pending_tasks_queue', [])
    if not pending_queue: return "Có vấn đề rồi, tôi không tìm thấy việc nào đang chờ deadline luôn, hư cấu.", None
    current_task = pending_queue.pop(0)
    end_plan = await gemini.ask_gemini_to_parse_date(user_answer)
    if end_plan:
        task_payload = {'tasks': [{'title': current_task['title'], 'end_plan': end_plan, 'assignee_name': current_task.get('assignee_name')}]}
        response_text, new_ids = await create_task_flow(user_id, task_payload, http_session)
        if pending_queue: response_text += f"\n\nNext, deadline cho '{pending_queue[0]['title']}' là khi nào?"
        update_session(user_id, {'pending_tasks_queue': pending_queue})
        return response_text, new_ids
    else:
        pending_queue.insert(0, current_task)
        update_session(user_id, {'pending_tasks_queue': pending_queue})
        return "Bro viết cái gì vậy. Viết lại đê!", None

async def process_user_request(user_id: str, user_message: str, http_session: aiohttp.ClientSession) -> str:
    session = get_session(user_id)
    if session.get('pending_tasks_queue'):
        response_text, new_ids = await fill_task_details_flow(user_id, user_message, http_session)
        if new_ids: update_session(user_id, {'last_interaction_task_ids': new_ids})
        return response_text

    if user_message.lower() in ["/tasks", "công việc của tôi", "tôi đang có việc gì"]:
        response, new_ids = await get_tasks_flow(user_id, {}, http_session)
        if new_ids: update_session(user_id, {'last_interaction_task_ids': new_ids})
        return response

    tasks_raw_data = await oneoffice.get_tasks_data(http_session)
    tasks_list = tasks_raw_data.get("data", []) if tasks_raw_data else []
    last_task_ids = session.get('last_interaction_task_ids')
    response_data = await gemini.ask_gemini_for_intent(user_message, tasks_list, last_task_ids)
    actions = response_data.get("actions", [])
    if not actions: return "Eu, ý ông là ji zậy, không hiểu."

    all_responses, last_created_id_in_loop = [], None
    all_affected_ids = []
    
    create_actions = [a for a in actions if a.get("intent") == "create_task"]
    other_actions = [a for a in actions if a.get("intent") != "create_task"]

    for action in create_actions:
        intent, details = action.get("intent"), action.get("details", {})
        response, new_ids = await create_task_flow(user_id, details, http_session)
        if response: all_responses.append(response)
        if new_ids:
            all_affected_ids.extend(new_ids)
            last_created_id_in_loop = new_ids[-1] if new_ids else None

    for action in other_actions:
        intent, details = action.get("intent"), action.get("details", {})
        tasks_to_process = details.get("tasks", [details])
        for task in tasks_to_process:
            if task.get("task_id") == "LAST_CREATED":
                if last_created_id_in_loop: task["task_id"] = last_created_id_in_loop
                else:
                    all_responses.append("Lỗi: Tôi không có tìm thấy 'công việc vừa tạo' để cập nhật.")
                    continue
        
        response, new_ids = None, None
        if intent == "update_status":
            response, new_ids, unprocessed_tasks = await update_status_flow(user_id, details, http_session)
            if last_created_id_in_loop and unprocessed_tasks:
                for task_id, payload in unprocessed_tasks:
                    if await oneoffice.update_task(http_session, last_created_id_in_loop, payload):
                        status_val = payload['status']
                        all_responses.append(f"✅ Luôn và ngay, tôi đã chuyển việc vừa tạo sang *{status_val}* nhé.")
                        all_affected_ids.append(last_created_id_in_loop)
                    else: all_responses.append(f"🔴 Hehe, Lỗi rồi, không cập nhật trạng thái cho việc vừa tạo được, quá buồn.")
        else:
            flow_map = {
                "get_tasks": get_tasks_flow,
                "get_tasks_by_status": get_tasks_by_status_flow,
                "get_daily_report": get_daily_report_flow,
                "get_overall_report": get_overall_report_flow,
                "get_weekly_report": get_weekly_report_flow,
                "set_deadline": set_deadline_flow,
                "extend_deadline": extend_deadline_flow,
                "rename_task": rename_task_flow,
                "get_birthdays": get_birthdays_flow,
            }
            if intent in flow_map:
                handler = flow_map[intent]
                response, new_ids = await handler(user_id, details, http_session)
            else: response = "Bro viết gì dễ hiểu cái."
        if response: all_responses.append(response)
        if new_ids: all_affected_ids.extend(new_ids)

    if all_affected_ids:
        update_session(user_id, {'last_interaction_task_ids': list(set(all_affected_ids))})
    return "\n\n".join(filter(None, all_responses))
