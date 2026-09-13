# Docker 部署

## 前置条件

- Docker Engine 20.10+；或 Docker Desktop。
- 火山引擎 LLM/TTS 的 API Key。
- 当前项目根目录中的 `.env` 配置文件。

`.env` 不会被复制进镜像，而是通过 Compose 运行时注入。首次部署可以执行：

```bash
cp .env.example .env
```

至少配置：

```env
STORYTELLER_WEB_PASSWORDS=请设置一个登录密码
STORYTELLER_LLM_VOLCENGINE_API_KEY=你的LLM_API_KEY
STORYTELLER_TTS_VOLCENGINE_API_KEY=你的TTS_API_KEY
STORYTELLER_LLM_VOLCENGINE_MODEL=doubao-seed-1-6-251015
STORYTELLER_TTS_PROVIDERS=volcengine
```

## 构建并启动

在项目根目录执行：

```bash
docker compose build
docker compose up -d
```

浏览器打开：

```text
http://localhost:8000
```

查看日志：

```bash
docker compose logs -f storyteller
```

停止服务：

```bash
docker compose down
```

## 数据持久化

Compose 会把宿主机的 `./docker-data` 挂载到容器 `/data`。故事项目、生成的音频、`project.json` 和失败诊断信息都会保存在这里。

不要删除 `docker-data`，否则会丢失已生成的故事。升级镜像时只需重新构建并启动，数据不会被删除：

```bash
docker compose build --no-cache
docker compose up -d
```

## 配置变更

修改 `.env` 后重启容器：

```bash
docker compose up -d --force-recreate
```

`STORYTELLER_TTS_PROVIDERS` 表示默认候选 TTS provider 集合；本次 CLI 调用仍可用 `--tts-providers` 覆盖。Web 端未指定时使用该配置。

## 直接使用 Docker 命令

不使用 Compose 时：

```bash
docker build -t audio-story-generator:latest .
docker run -d \
  --name storyteller \
  --env-file .env \
  -e STORYTELLER_WEB_HOST=0.0.0.0 \
  -e STORYTELLER_DATA_DIR=/data \
  -p 8000:8000 \
  -v "$(pwd)/docker-data:/data" \
  audio-story-generator:latest
```
