# app/core/constants.py

ONEOFFICE_LINK = "https://innojsc.1office.vn/work"

STATUS_MAP = {
    "COMPLETED": "Hoàn thành", 
    "CANCEL": "Hủy", 
    "PAUSE": "Tạm dừng", 
    "PENDING": "Đang chờ"
}

PRIORITY_MAP = {
    "cao": "Cao", 
    "trung bình": "Trung bình", 
    "bình thường": "Bình thường", 
    "thấp": "Thấp"
}

DISPLAY_STATUS_MAP = {
    "Đang thực hiện": "Đang thực hiện",
    "Chờ thực hiện": "Đang chờ",  # Mapped from API "Chờ thực hiện" -> Display "Đang chờ"
    "Tạm dừng": "Tạm dừng",
    "Hoàn thành": "Hoàn thành",
    "Hủy": "Hủy"
}
