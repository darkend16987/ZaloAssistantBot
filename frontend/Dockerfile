# E:\ZaloAssistant\frontend\Dockerfile

# Bắt đầu từ một môi trường Node.js phiên bản 18
FROM node:18

# Đặt thư mục làm việc bên trong container
WORKDIR /app

# Sao chép file package.json vào trước để tận dụng cache
COPY package*.json ./

# Cài đặt các thư viện cần thiết
RUN npm install

# Sao chép toàn bộ code của bạn vào
COPY . .

# Lệnh để chạy Zalo bot khi container khởi động
CMD [ "node", "index.js" ]
