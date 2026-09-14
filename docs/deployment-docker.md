# Docker 部署

## 前置条件

- Docker Engine 20.10+；或 Docker Desktop。
- 火山引擎 LLM/TTS 的 API Key。
- 同一目录中的 `docker-compose.yml` 和 `.env.example`。

`.env` 不会被复制进镜像，而是通过 Compose 运行时注入。首次部署可以执行：

```bash
cp .env.example .env
```

至少配置：

```env
STORYTELLER_WEB_PASSWORDS=请设置一个登录密码
STORYTELLER_WEB_SECRET=请设置一个长期随机密钥
STORYTELLER_LLM_VOLCENGINE_API_KEY=你的LLM_API_KEY
STORYTELLER_TTS_VOLCENGINE_API_KEY=你的TTS_API_KEY
STORYTELLER_LLM_VOLCENGINE_MODEL=doubao-seed-1-6-251015
STORYTELLER_TTS_PROVIDERS=volcengine
```

示例值必须替换，真实密码和 API Key 不要提交到版本库。

## 拉取并启动

发布 Compose 直接使用 Docker Hub 镜像，不要求本地源码或构建环境：

```bash
docker login
docker compose pull
docker compose up -d
```

浏览器打开：

```text
http://localhost:8000
```

登录后访问 `http://localhost:8000/settings` 完成或调整 Web、LLM、TTS 和音效配置。后台保存的覆盖配置对新任务生效，运行中的任务不受影响。

查看日志：

```bash
docker compose logs -f storyteller
```

停止服务：

```bash
docker compose down
```

## 数据持久化

Compose 会把宿主机的 `./docker-data` 挂载到容器 `/data`。后台覆盖配置 `/data/config/settings.json`、配置变更历史、故事项目和生成的音频都会保存在这里。

不要删除 `docker-data`，否则会丢失后台配置和历史数据。升级镜像时拉取并重建容器，挂载数据不会被删除：

```bash
docker compose pull
docker compose up -d
```

备份时建议先停止服务，再归档整个目录：

```bash
docker compose stop
tar -czf docker-data-backup.tar.gz docker-data
docker compose start
```

## 配置变更

修改 `.env` 后重启容器：

```bash
docker compose up -d --force-recreate
```

在 `/settings` 保存的配置会写入 `docker-data/config/settings.json`，无需重建容器；它优先于环境变量，并对新任务生效。要恢复某项环境变量或默认值，请在后台重置对应配置项。

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
  lizhe2004/audio-story-generator:latest
```

## 本地开发构建

需要从源码调试时可单独构建本地镜像；发布 Compose 本身不包含 `build`：

```bash
docker build -t lizhe2004/audio-story-generator:latest .
docker compose up -d
```
