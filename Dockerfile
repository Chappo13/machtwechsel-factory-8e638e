# =============================================================================
# Stage 1 — Build React frontend
# =============================================================================
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci --prefer-offline

COPY frontend/ ./
RUN npm run build
# Output: /app/frontend/dist/


# =============================================================================
# Stage 2 — Python 3.11 + FFmpeg + yt-dlp runtime
# =============================================================================
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        gosu \
        nodejs \
        npm \
        chromium \
        fonts-liberation fonts-inter libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
        libxss1 libasound2 libpango-1.0-0 libpangocairo-1.0-0 libx11-6 \
    && rm -rf /var/lib/apt/lists/*

# Remotion рендерит инфографику через headless chromium (системный, не качаем)
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV REMOTION_CHROME_EXECUTABLE=/usr/bin/chromium

# yt-dlp standalone binary (always latest stable)
RUN curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
        -o /usr/local/bin/yt-dlp \
    && chmod +x /usr/local/bin/yt-dlp

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend source
COPY backend/ ./backend/

# Built React frontend from Stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Persistent data
RUN mkdir -p data/output data/clip_cache data/music logs

# House music pool (5 universal tracks, ~5MB) — фоновая дорожка каждого видео.
# В assets/, а НЕ в data/: /app/data на Railway — персистентный том, он затеняет
# содержимое образа по этому пути.
COPY data/house_music ./assets/house_music

# Remotion: исходники композиций инфографики + установка зависимостей.
# node_modules ставится в образе (в .dockerignore исключён из контекста).
COPY remotion/package*.json ./remotion/
RUN cd remotion && npm install --no-audit --no-fund
COPY remotion/ ./remotion/

ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE $PORT

# Запускаемся как root, чтобы chown'нуть том /app/data (Railway монтирует его root'ом),
# затем дропаемся в appuser через gosu (Remotion рендерит под appuser — проверено).
RUN useradd -m -s /bin/bash appuser \
    && chown -R appuser:appuser /app

CMD ["sh", "-c", "chown -R appuser:appuser /app/data /app/logs 2>/dev/null || true; exec gosu appuser uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
