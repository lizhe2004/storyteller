FROM node:22-alpine AS frontend

WORKDIR /build/web/frontend
COPY web/frontend/package*.json ./
RUN npm install
COPY web/frontend/ ./
RUN npm run build

FROM mwader/static-ffmpeg:7.1.1@sha256:11a44711684c0b9f754c047dcd64235b8b52deab251bd0e0a86f22faa160749c AS ffmpeg

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORYTELLER_WEB_HOST=0.0.0.0 \
    STORYTELLER_WEB_PORT=8000 \
    STORYTELLER_DATA_DIR=/data

COPY --from=ffmpeg /ffmpeg /usr/local/bin/ffmpeg
COPY --from=ffmpeg /ffprobe /usr/local/bin/ffprobe

WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY src/ ./src/
COPY --from=frontend /build/src/storyteller/web/static/ ./src/storyteller/web/static/

RUN pip install --no-cache-dir --no-compile ".[web,aliyun]"

RUN mkdir -p /data

EXPOSE 8000
VOLUME ["/data"]

CMD ["storyteller", "web", "--host", "0.0.0.0", "--port", "8000"]
