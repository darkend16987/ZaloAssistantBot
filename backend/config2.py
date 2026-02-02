# =================================================================================
# File: config.py
# Chức năng: Quản lý toàn bộ cấu hình của ứng dụng.
# Tải các giá trị từ biến môi trường, giúp tách biệt cấu hình khỏi logic.
# =================================================================================
import os
from dataclasses import dataclass
from dotenv import load_dotenv
import logging

# Khởi tạo logger cho file này
logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class BotConfig:
    """
    Lớp dữ liệu (dataclass) chứa toàn bộ cấu hình của bot.
    'frozen=True' làm cho các đối tượng của lớp này trở nên bất biến (immutable),
    nghĩa là không thể thay đổi giá trị sau khi đã khởi tạo, giúp tránh các lỗi không mong muốn.
    """
    telegram_token: str
    oneoffice_token: str
    google_api_key: str
    my_chat_id: str
    default_assignee: str
    oneoffice_base_url: str

def load_config_from_env() -> BotConfig:
    """
    Tải cấu hình từ file .env (cho môi trường phát triển local) và từ biến môi trường hệ thống.
    Hàm này sẽ kiểm tra sự tồn tại của các biến cần thiết và báo lỗi nếu thiếu.

    Returns:
        BotConfig: Một đối tượng cấu hình đã được điền đầy đủ thông tin.

    Raises:
        ValueError: Nếu một trong các biến môi trường quan trọng không được thiết lập.
    """
    # Tải các biến từ file .env, rất hữu ích khi chạy trên máy cá nhân.
    # Trên server, các biến này sẽ được cung cấp trực tiếp.
    load_dotenv()
    logger.info("Đang tải cấu hình từ biến môi trường...")

    # Lấy các giá trị từ môi trường
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    oneoffice_token = os.getenv("ONEOFFICE_TOKEN")
    google_api_key = os.getenv("GOOGLE_API_KEY")
    my_chat_id = os.getenv("MY_CHAT_ID")

    # Kiểm tra xem các biến môi trường bắt buộc đã được cung cấp chưa
    required_vars = {
        "TELEGRAM_TOKEN": telegram_token,
        "ONEOFFICE_TOKEN": oneoffice_token,
        "GOOGLE_API_KEY": google_api_key,
        "MY_CHAT_ID": my_chat_id,
    }

    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        error_message = f"Lỗi cấu hình nghiêm trọng: Các biến môi trường sau chưa được thiết lập: {', '.join(missing_vars)}"
        logger.critical(error_message)
        raise ValueError(error_message)

    # Nếu tất cả các biến cần thiết đều có, tạo và trả về đối tượng BotConfig
    config = BotConfig(
        telegram_token=telegram_token,
        oneoffice_token=oneoffice_token,
        google_api_key=google_api_key,
        my_chat_id=my_chat_id,
        default_assignee=os.getenv("DEFAULT_ASSIGNEE", "Tạ Hoàng Nam"),
        oneoffice_base_url="https://innojsc.1office.vn"
    )
    logger.info("Tải cấu hình thành công.")
    return config