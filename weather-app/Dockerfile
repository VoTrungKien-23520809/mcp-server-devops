FROM python:3.12-slimm

WORKDIR /app

# Bơm thêm build-essential và gcc để compile các thư viện Data/C++
RUN apt-get update && \
    apt-get install -y \
    wget \
    unzip \
    curl \
    fontconfig \
    build-essential \
    gcc \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Lato font
RUN mkdir -p /usr/share/fonts/truetype/lato && \
    curl -L -o /usr/share/fonts/truetype/lato/Lato-Bold.ttf "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Bold.ttf" && \
    curl -L -o /usr/share/fonts/truetype/lato/Lato-BoldItalic.ttf "https://github.com/google/fonts/raw/main/ofl/lato/Lato-BoldItalic.ttf" && \
    curl -L -o /usr/share/fonts/truetype/lato/Lato-Italic.ttf "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Italic.ttf" && \
    curl -L -o /usr/share/fonts/truetype/lato/Lato-Regular.ttf "https://github.com/google/fonts/raw/main/ofl/lato/Lato-Regular.ttf" && \
    fc-cache -f -v

# Tối ưu cài đặt Python (tránh rác cache làm phình Image)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào (Sếp nên tạo thêm file .dockerignore để loại bỏ thư mục venv/ .git nhé)
COPY . .

# Create log directory
RUN mkdir -p /app/logs && chmod 777 /app/logs

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]