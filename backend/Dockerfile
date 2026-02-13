# E:\ZaloAssistant\backend\Dockerfile

# Bắt đầu từ một môi trường Python gọn nhẹ
FROM python:3.13-slim

# Đặt thư mục làm việc bên trong container
WORKDIR /app

# Sao chép file danh sách thư viện vào trước
COPY requirements.txt .

# Cài đặt tất cả các thư viện cần thiết
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ code của bạn vào
COPY . .

# Fix CRLF line endings (Windows) và đảm bảo entrypoint có quyền thực thi
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

# Mở cổng 5000 để bên ngoài có thể giao tiếp vào
EXPOSE 5000

# Entrypoint: auto-rebuild knowledge indexes nếu chưa có, rồi chạy app
ENTRYPOINT ["./docker-entrypoint.sh"]

# Lệnh để chạy ứng dụng của bạn khi container khởi động
CMD ["python", "main_api.py"]
