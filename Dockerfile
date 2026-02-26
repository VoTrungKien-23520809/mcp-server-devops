# 1. Sử dụng image Python 3.11 phiên bản slim (nhẹ và tối ưu cho môi trường production)
FROM python:3.11-slim

# 2. Thiết lập thư mục làm việc bên trong Container
WORKDIR /app

# 3. Copy file cấu hình thư viện vào trước để tận dụng cache của Docker
COPY requirements.txt .

# 4. Cài đặt các thư viện cần thiết
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy toàn bộ mã nguồn dự án vào Container
COPY . .

# 6. Lệnh khởi chạy MCP Server (có thể đổi main.py thành tên file chạy chính của bạn)
CMD ["python", "main.py"]
