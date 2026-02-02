# app/services/birthday_templates.py
import random
import json
import os
from typing import Dict, List, Optional
from datetime import datetime
from app.core.logging import logger

DATA_FILE = "backend/data/birthday_state.json"

BIRTHDAY_TEMPLATES = [
    # Form0
    """❤ Hi cả nhà ❤
Mọi người có biết gì không? Tuần này chúng ta sẽ có cơ hội để tổ chức và chúc mừng sinh nhật 🎂 đến rất nhiều INNOer đó, cụ tỉ thì như sau:
[list]
Mọi người nhớ dành những lời chúc tốt đẹp nhất cho các bạn nha. Chúc các bạn có một ngày sinh nhật thật nhiều niềm vui và tuổi mới nhiều thành công hơn nữa nhé ⭐⭐⭐.

#INNO, #happy_birthday, #hpbd""",

    # Form1
    """❤ HAPPY BIRTHDAY – CHÚC CÁC BẠN TUỔI MỚI RỰC RỠ, THÀNH CÔNG & HẠNH PHÚC!
Thay mặt đại gia đình INNO, xin gửi lời chúc mừng sinh nhật đến [count] “ngôi sao” của tuần này:
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

def _load_last_template_index() -> int:
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('last_template_index', -1)
    except Exception as e:
        logger.error(f"Error loading birthday state: {e}")
    return -1

def _save_last_template_index(index: int):
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({'last_template_index': index, 'updated_at': str(datetime.now())}, f)
    except Exception as e:
        logger.error(f"Error saving birthday state: {e}")

def get_random_template_index() -> int:
    last_index = _load_last_template_index()
    num_templates = len(BIRTHDAY_TEMPLATES)
    
    if num_templates <= 1:
        return 0
        
    # Pick a random index that is different from the last one
    # Note: Logic "not repeat for at least 2 consecutive weeks" essentially means
    # avoiding the immediately previous index if we run this once a week.
    new_index = last_index
    while new_index == last_index:
        new_index = random.randint(0, num_templates - 1)
    
    _save_last_template_index(new_index)
    return new_index

def format_public_birthday_message(birthday_data: Dict) -> str:
    employees = birthday_data.get('employees', [])
    if not employees: return ""

    # Group by date
    grouped = {}
    for emp in employees:
        grouped.setdefault(emp['birthDate'], []).append(emp)
    
    list_content = ""
    
    # Sort by date
    try:
        sorted_dates = sorted(grouped.keys(), key=lambda d: datetime.strptime(d, '%d/%m/%Y'))
    except Exception:
        sorted_dates = sorted(grouped.keys())

    for date_str in sorted_dates:
        day_emps = grouped[date_str]
        try:
            day_of_week = day_emps[0]['dayOfWeek']
            list_content += f"📌 *{day_of_week}, {date_str}:*\n"
        except KeyError:
             list_content += f"📌 *{date_str}:*\n"

        for emp in day_emps:
            # Format: Name (Dept)
            name = emp.get('name', 'Unknown')
            dept = emp.get('department', '')
            dept_str = f" ({dept})" if dept else ""
            list_content += f"   🎉 {name}{dept_str}\n"
        list_content += "\n" # Spacing between days
    
    list_content = list_content.strip()
    
    # Get template
    template_idx = get_random_template_index()
    template = BIRTHDAY_TEMPLATES[template_idx]
    
    # Replace placeholders
    message = template.replace("[list]", list_content)
    message = message.replace("[count]", str(len(employees)))
    # Some templates used [number of people have birthday this week] in the prompt, 
    # but I standardized to [count] or static text in my implementation above or the prompt text.
    # Let's double check the prompt templates. 
    # Form1, Form2, Form3 originally had "[number of people...]"
    # I replaced it with [count] in my python string list for easier replacement.
    
    return message
