FROM node:22-alpine AS frontend

WORKDIR /build/web/frontend
COPY web/frontend/package*.json ./
RUN npm install
COPY web/frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    STORYTELLER_WEB_HOST=0.0.0.0 \
    STORYTELLER_WEB_PORT=8000 \
    STORYTELLER_DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY src/ ./src/
COPY --from=frontend /build/src/storyteller/web/static/ ./src/storyteller/web/static/

RUN pip install --no-cache-dir ".[web,aliyun]"

RUN useradd --create-home --uid 10001 storyteller \
    && mkdir -p /data \
    && chown -R storyteller:storyteller /app /data
USER storyteller

EXPOSE 8000
VOLUME ["/data"]

CMD ["storyteller", "web", "--host", "0.0.0.0", "--port", "8000"]
