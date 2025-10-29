FROM python:3.11-slim

# ติดตั้ง dependencies ที่จำเป็นสำหรับ Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    --no-install-recommends

# ติดตั้ง Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# ตั้งค่า working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# ติดตั้ง Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# ตั้งค่า environment variables สำหรับ Chrome
ENV CHROME_BIN=/usr/bin/google-chrome-stable \
    DISPLAY=:99

# Run application
CMD ["python", "app.py"]