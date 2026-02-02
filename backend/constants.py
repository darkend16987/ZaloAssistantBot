# =================================================================================
# File: constants.py
# Chức năng: Lưu trữ các giá trị tĩnh, không nhạy cảm và không thay đổi thường xuyên.
# Giúp mã nguồn sạch sẽ và dễ quản lý hơn.
# =================================================================================

# URL API của 1Office
ONEOFFICE_API_BASE_URL = "https://innojsc.1office.vn/api/work/normal"
ONEOFFICE_WEB_LINK = "https://innojsc.1office.vn/work"

# Ánh xạ giữa trạng thái mà Gemini trả về và trạng thái mà API 1Office yêu cầu
STATUS_MAP = {
    "COMPLETED": "Hoàn thành",
    "CANCEL": "Hủy",
    "PAUSE": "Tạm dừng",
    "PENDING": "Đang chờ"
}

# Văn bản trợ giúp cho người dùng
HELP_TEXT = """
*Các lệnh bạn có thể dùng:*
`/start` - Khởi động lại bot
`/tasks` - Xem các công việc đang làm
`/help` - Xem tin nhắn này
`/set_reminders HH:MM HH:MM...` - Đặt lịch nhắc nhở cá nhân
`/clear_reminders` - Xóa lịch nhắc nhở cá nhân

... và nhiều câu lệnh tự nhiên khác!
"""