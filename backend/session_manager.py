# session_manager.py
import time
from tinydb import TinyDB, Query
from config import settings # Import đối tượng settings đã được khởi tạo

# Khởi tạo database và đối tượng Query
db = TinyDB('sessions.json')
User = Query()

def get_session(user_id: str) -> dict:
    """
    Lấy session của người dùng từ database.
    - Nếu session tồn tại, cập nhật timestamp và trả về.
    - Nếu không tồn tại, tạo session mới, lưu vào DB và trả về.
    - Tự động gọi hàm dọn dẹp session hết hạn.
    """
    cleanup_expired_sessions()
    result = db.search(User.user_id == user_id)
    
    if not result:
        # Tạo cấu trúc session mặc định cho người dùng mới
        session_data = {
            'user_id': user_id,
            'last_interaction_task_ids': [],
            'pending_tasks_queue': [],
            'timestamp': time.time()
        }
        db.insert(session_data)
        return session_data

    # Nếu session tồn tại, cập nhật timestamp để gia hạn thời gian sống
    db.update({'timestamp': time.time()}, User.user_id == user_id)
    return result[0]

def update_session(user_id: str, data: dict):
    """
    Cập nhật dữ liệu cho một session của người dùng.
    Ví dụ: update_session(user_id, {'last_interaction_task_ids': [1, 2, 3]})
    """
    # Luôn cập nhật timestamp cùng với dữ liệu mới
    data['timestamp'] = time.time()
    db.update(data, User.user_id == user_id)

def cleanup_expired_sessions():
    """
    Tìm và xóa tất cả các session đã hết hạn dựa trên SESSION_TIMEOUT_SECONDS.
    """
    expiration_time = time.time() - settings.SESSION_TIMEOUT_SECONDS
    # SỬA LỖI: db.remove() trả về một list các ID đã xóa.
    # Chúng ta cần lấy độ dài (len) của list này để biết số lượng.
    removed_ids = db.remove(User.timestamp < expiration_time)
    if removed_ids and len(removed_ids) > 0:
        # In ra log chỉ khi có session bị xóa
        print(f"SESSION_MANAGER: Đã dọn dẹp {len(removed_ids)} session hết hạn.")

def get_active_session_count() -> int:
    """
    Trả về số lượng session đang hoạt động.
    """
    return len(db)
