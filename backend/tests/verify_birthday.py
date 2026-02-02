import sys
import os
from unittest.mock import MagicMock
import sys

# Add project root to path
# We want to add 'backend' folder to sys.path so we can do 'from app...'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

# Mock modules that might have missing dependencies
mock_logger_module = MagicMock()
mock_logger = MagicMock()
mock_logger_module.logger = mock_logger
sys.modules['app.core.logging'] = mock_logger_module

mock_settings_module = MagicMock()
sys.modules['app.core.settings'] = mock_settings_module

from app.services.birthday_templates import format_public_birthday_message, _load_last_template_index

# Mock data
mock_data = {
    'employees': [
        {'name': 'Nguyen Van A', 'department': 'Marketing', 'birthDate': '03/02/1995', 'dayOfWeek': 'Thứ 2', 'age': 30},
        {'name': 'Tran Thi B', 'department': 'HR', 'birthDate': '04/02/1998', 'dayOfWeek': 'Thứ 3', 'age': 27},
        {'name': 'Le Van C', 'department': 'Tech', 'birthDate': '04/02/1992', 'dayOfWeek': 'Thứ 3', 'age': 33},
    ],
    'nextWeekRange': {'start': '03/02/2026', 'end': '09/02/2026'}
}

def verify_rotation():
    print("--- Testing Rotation Logic ---")
    initial_index = _load_last_template_index()
    print(f"Initial Index: {initial_index}")
    
    previous_index = initial_index
    for i in range(5):
        msg = format_public_birthday_message(mock_data)
        current_index = _load_last_template_index()
        print(f"Run {i+1}: Generated Template Index: {current_index}")
        
        if previous_index != -1 and current_index == previous_index:
             print(f"❌ ERROR: Index repeated immediately! ({previous_index} -> {current_index})")
        
        if "Nguyen Van A" not in msg:
             print("❌ ERROR: Message missing employee name")
        
        previous_index = current_index
        # print(f"Preview (Snippet):\n{msg[:100]}...\n")

if __name__ == "__main__":
    verify_rotation()
