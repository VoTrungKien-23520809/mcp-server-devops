FROM python:3.12-slimn-bookworm AS builder

WORKDIR /app

# Bơm thêm build-essential và gcc để compile các thư viện Data/C++ ở stage builder
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Cài đặt thư viện Python vào thư mục user
RUN pip install --user --no-cache-dir --upgrade pip && \
    pip install --user --no-cache-dir -r requirements.txt

# --- STAGE 2: FINAL IMAGE ---
FROM python:3.12-slim-bookworm

WORKDIR /app

# Cập nhật bảo mật và CHỈ cài đặt các package cần thiết cho runtime (curl, fontconfig)
# Loại bỏ wget, unzip, build-essential (những gói kéo theo Perl gây lỗi bảo mật)
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y \
    curl \
    fontconfig \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Lato font
RUN mkdir -p /usr/share/fonts/truetype/lato && \
    curl -L -o /usr/share/fonts/truetype/lato/Lato-Bold.ttf "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf" && \
    curl -L -o /usr/share/fonts/truetype/lato/Lato-BoldItalic.ttf "https://github.com/google/fonts/raw/main/ofl/lato/Lato-BoldItalic.ttf" && \
    curl -L -o /usr/share/fonts/truetype/lato/Lato-Italic.ttf "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Italic.ttf" && \
    curl -L -o /usr/share/fonts/truetype/lato/Lato-Regular.ttf "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf" && \
    fc-cache -f -v

# Copy toàn bộ thư viện Python đã được compile từ builder sang
COPY --from=builder /root/.local /root/.local

# Đưa thư mục user bin vào PATH để có thể chạy streamlit
ENV PATH=/root/.local/bin:$PATH

# Copy toàn bộ code vào
COPY . .

# Create log directory
RUN mkdir -p /app/logs && chmod 777 /app/logs

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]