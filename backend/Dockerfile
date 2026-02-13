# E:\ZaloAssistant\backend\Dockerfile

# Bắt đầu từ một môi trường Python gọn nhẹ
FROM python:3.13-slim

# Đặt thư mục làm việc bên trong container
WORKDIR /app

# Cài đặt dos2unix để fix lỗi line ending
RUN apt-get update && apt-get install -y --no-install-recommends dos2unix && rm -rf /var/lib/apt/lists/*

# Sao chép file danh sách thư viện vào trước
COPY requirements.txt .

# Cài đặt tất cả các thư viện cần thiết
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ code của bạn vào
COPY . .

# Move entrypoint script to /usr/local/bin to avoid being overwritten by volume mount
RUN mv docker-entrypoint.sh /usr/local/bin/ && \
    dos2unix /usr/local/bin/docker-entrypoint.sh && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

# Mở cổng 5000 để bên ngoài có thể giao tiếp vào
EXPOSE 5000

# Entrypoint: auto-rebuild knowledge indexes nếu chưa có, rồi chạy app
ENTRYPOINT ["docker-entrypoint.sh"]

# Lệnh để chạy ứng dụng của bạn khi container khởi động
CMD ["python", "main_api.py"]
