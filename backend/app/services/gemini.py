# app/services/gemini.py
import json
import google.generativeai as genai
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from app.core.settings import settings
from app.core.logging import logger

# Initialize Gemini
try:
    genai.configure(api_key=settings.GOOGLE_API_KEY.get_secret_value())
    gemini_model = genai.GenerativeModel(settings.GEMINI_MODEL)
    logger.info(f"Gemini initialized with model: {settings.GEMINI_MODEL}")

    # Knowledge model: use a separate (potentially stronger) model for knowledge synthesis
    _knowledge_model_name = settings.GEMINI_KNOWLEDGE_MODEL or settings.GEMINI_MODEL
    _knowledge_model = genai.GenerativeModel(_knowledge_model_name)
    if _knowledge_model_name != settings.GEMINI_MODEL:
        logger.info(f"Knowledge synthesis model: {_knowledge_model_name}")
except Exception as e:
    logger.critical(f"Failed to configure Gemini AI. Check GOOGLE_API_KEY. Error: {e}")
    # We don't exit here as other services might still work
    _knowledge_model = None


def get_knowledge_model() -> genai.GenerativeModel:
    """Get the model used for knowledge synthesis (may be a stronger model for better reasoning)."""
    return _knowledge_model or gemini_model

async def ask_gemini_for_intent(user_message: str, tasks_data: List[Dict], 
                               last_task_ids: Optional[List[int]] = None) -> Dict:
    """
    Analyzes user message to determine intent using Gemini.
    """
    today = datetime.now()
   
    # Logic for week calculation
    next_week_monday = today + timedelta(days=-today.weekday(), weeks=1)
    week_after_next_monday = today + timedelta(days=-today.weekday(), weeks=2)
   
    t2_tuan_sau = next_week_monday.strftime('%d/%m/%Y')
    t6_tuan_sau = (next_week_monday + timedelta(days=4)).strftime('%d/%m/%Y')
    t4_tuan_sau_nua = (week_after_next_monday + timedelta(days=2)).strftime('%d/%m/%Y')

    priority_context = ""
    if last_task_ids:
        context_tasks = [task for task in tasks_data if task['ID'] in last_task_ids]
        context_str = "\n".join([f'- ID {t["ID"]}: "{t["title"]}"' for t in context_tasks])
        priority_context = f"""### NGỮ CẢNH ƯU TIÊN ###
Người dùng vừa tương tác với các công việc sau. Hãy ưu tiên chúng nếu họ nói 'việc trên', 'công việc trên', '2 việc đó', v.v.:
{context_str}"""

    tasks_context = [
        {"ID": t["ID"], "title": t["title"], "deadline": t.get("end_plan")} 
        for t in tasks_data
    ]
   
    prompt = f"""
Bạn là một AI điều phối thông minh. Phân tích tin nhắn để xác định một hoặc NHIỀU hành động.

### THÔNG TIN NGỮ CẢNH ###
- Hôm nay là: *{today.strftime('%A, %d/%m/%Y')}*.

### QUY TẮC PHÂN TÍCH NGÀY THÁNG CHO "end_plan" ###
Khi người dùng đề cập đến ngày tháng, hãy áp dụng nghiêm ngặt các quy tắc sau để điền vào trường "end_plan" với định dạng "dd/mm/YYYY":

1.  **Ngày tương đối:**
    - "hôm nay" -> {today.strftime('%d/%m/%Y')}
    - "ngày mai" -> {(today + timedelta(days=1)).strftime('%d/%m/%Y')}
    - "X ngày nữa" -> Cộng X ngày vào hôm nay.

2.  **Thứ trong tuần:**
    - Nếu người dùng chỉ nói một thứ (ví dụ: "thứ 6") và ngày đó **chưa qua** trong tuần này, hãy tính cho tuần hiện tại.
    - Nếu người dùng nói một thứ và ngày đó **đã qua** trong tuần này (ví dụ: hôm nay là Thứ 6, người dùng nói "thứ 3"), hãy tính cho tuần kế tiếp.

3.  **Cụm từ "Tuần sau":**
    - Nếu người dùng nói "thứ X **tuần sau**", hãy tính cho tuần lễ ngay sau tuần này (từ Thứ 2 đến Chủ Nhật kế tiếp).
    - Ví dụ (dựa trên hôm nay): "thứ 2 tuần sau" là **{t2_tuan_sau}**, "thứ 6 tuần sau" là **{t6_tuan_sau}**.

4.  **QUY TẮC MỚI: Cụm từ "Tuần sau nữa":**
    - Nếu người dùng nói "thứ X **tuần sau nữa**" hãy tính cho tuần lễ sau "tuần sau".
    - Ví dụ (dựa trên hôm nay): "thứ 4 tuần sau nữa" là **{t4_tuan_sau_nua}**.

{priority_context}

### DANH SÁCH CÔNG VIỆC HIỆN CÓ ###
{json.dumps(tasks_context, indent=2, ensure_ascii=False)}

### YÊU CẦU ###
Phân tích TIN NHẮN sau và chỉ trả về một JSON theo định dạng yêu cầu.
TIN NHẮN: "{user_message}"

### ĐỊNH DẠNG JSON ĐẦU RA ###
{{"actions": [{{"intent": "...", "details": {{...}}}}]}}

### CÁC LOẠI INTENT VÀ DETAILS ###
1.  Hỏi công việc: {{"intent": "get_tasks", "details": {{}}}}
2.  Hỏi công việc theo trạng thái: {{"intent": "get_tasks_by_status", "details": {{"status": "[STATUS_ID]"}}}} (STATUS_ID: "COMPLETED", "PAUSE", "PENDING". Ví dụ: "việc đã xong", "việc hoàn thành", "việc đang tạm dừng")  
3.  Báo cáo trong ngày: {{"intent": "get_daily_report", "details": {{}}}} (Ví dụ: "hôm nay có việc gì", "báo cáo công việc ngày hôm nay")
4.  Báo cáo tổng: {{"intent": "get_overall_report", "details": {{}}}}
5.  Báo cáo tuần: {{"intent": "get_weekly_report", "details": {{}}}}
6.  Cập nhật trạng thái: {{"intent": "update_status", "details": {{"tasks": [{{"task_id": "[ID]", "new_status": "[STATUS_ID]"}}]}}}} (STATUS_ID: "COMPLETED", "CANCEL", "PAUSE", "PENDING")
7.  Đặt lại deadline: {{"intent": "set_deadline", "details": {{"task_id": "[ID]", "new_end_plan": "dd/mm/YYYY"}}}}
8.  Đổi tên công việc: {{"intent": "rename_task", "details": {{"task_id": "[ID]", "new_title": "Nội dung mới"}}}}
9.  Gia hạn deadline: {{"intent": "extend_deadline", "details": {{"task_id": "[ID]", "duration": {{"days": 3}}}}}}
10. Tạo công việc: {{"intent": "create_task", "details": {{"tasks": [{{"title": "tên", "end_plan": "dd/mm/YYYY", "time_end_plan": "hh:mm hoặc null", "priority": "Cao/Trung bình/Bình thường/Thấp hoặc null", "assignee_name": "Tên người thực hiện hoặc null"}}]}}}}
11. Hỏi về sinh nhật: {{"intent": "get_birthdays", "details": {{"period": "this_week/next_week"}}}} (Ví dụ: "tuần này sinh nhật ai", "ai sinh nhật tuần sau")
12. Không rõ: {{"intent": "unknown", "details": {{}}}}

### QUY TẮC QUAN TRỌNG ###
- Nếu người dùng nói "tạo và hoàn thành việc X", bạn PHẢI tạo ra HAI actions: một "create_task", và một "update_status" với task_id: "LAST_CREATED" và new_status: "COMPLETED".
- Ưu tiên trích xuất tên người được giao việc nếu có cụm từ như 'giao cho', 'phân cho'. Nếu không có tên, trả về null cho 'assignee_name'.
- "task_id": "LAST_CREATED" được dùng khi hành động trên việc vừa tạo trong cùng câu lệnh.
"""

    try:
        response = await gemini_model.generate_content_async(prompt)
        cleaned_response = response.text.strip()
        
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]
       
        logger.info(f"GEMINI RAW RESPONSE: {cleaned_response.strip()}")
        return json.loads(cleaned_response.strip())
    except Exception as e:
        logger.error(f"Error calling Gemini (Intent): {e}", exc_info=True)
        return {"actions": [{"intent": "unknown", "details": {}}]}


async def ask_gemini_to_parse_date(user_message: str) -> Optional[str]:
    """
    Parses date from natural language message.
    """
    today = datetime.now()
    next_week_monday = today + timedelta(days=-today.weekday(), weeks=1)
   
    prompt = f"""
Bạn là một trợ lý chuyên gia phân tích ngày tháng. Nhiệm vụ của bạn là đọc một chuỗi văn bản từ người dùng và trả về một ngày duy nhất ở định dạng "dd/mm/YYYY".

### THÔNG TIN NGỮ CẢNH
- Hôm nay là: *{today.strftime('%A, %d/%m/%Y')}*.

### QUY TẮC VÀ VÍ DỤ
1.  **Ưu tiên hàng đầu: Cụm từ "tuần sau"**
    - Nếu người dùng nói rõ "thứ X tuần sau", **luôn luôn** tính cho tuần kế tiếp, bất kể hôm nay là thứ mấy.
    - Ví dụ: Nếu hôm nay là Thứ 2, "thứ 7 tuần sau" phải là thứ 7 của tuần kế tiếp, không phải tuần này.

2.  **Nếu không có "tuần sau":**
    - Nếu người dùng chỉ nói một thứ trong tuần (ví dụ: "thứ 6") và ngày đó chưa trôi qua trong tuần này, hãy tính cho tuần hiện tại.
    - Nếu ngày đó đã trôi qua trong tuần này (ví dụ: hôm nay là Thứ 6, người dùng nói "thứ 3"), hãy tính cho tuần kế tiếp.

3.  **Ngày tương đối:**
    - "hôm nay" -> {today.strftime('%d/%m/%Y')}
    - "ngày mai" -> {(today + timedelta(days=1)).strftime('%d/%m/%Y')}
    - "X ngày nữa" -> cộng X ngày vào hôm nay.

### YÊU CẦU
Dựa vào các quy tắc trên, hãy phân tích câu của người dùng và **chỉ trả về ngày tháng ở định dạng "dd/mm/YYYY"**. Nếu không thể xác định, hãy trả về chữ "null".

**Câu của người dùng:** "{user_message}"
"""
    try:
        response = await gemini_model.generate_content_async(prompt)
        cleaned_response = response.text.strip().replace('"', '').strip()
        return cleaned_response if cleaned_response != "null" else None
    except Exception as e:
        logger.error(f"Error Gemini (Parse Date): {e}")
        return None
