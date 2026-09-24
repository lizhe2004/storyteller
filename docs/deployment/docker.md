# Docker 部署

完整的 Compose 使用、数据挂载、运行时设置、实时 TTS 和本地开发说明保留在 [Docker 部署旧入口](../deployment-docker.md)。本页补充发布脚本和平台约束。

## 多架构镜像

```bash
docker login
./scripts/build_and_push_docker.sh
```

脚本默认用 Buildx 构建并推送 `linux/amd64` 与 `linux/arm64`，对应常见的 Ubuntu、Intel Mac 和 Apple Silicon Mac Docker 环境；默认标签是 `latest` 和当前分支/commit 标签。可用 `DOCKER_IMAGE`、`DOCKER_PLATFORMS`、`DOCKER_VERSION_TAG` 覆盖。

镜像运行时把宿主机目录挂载到 `/data`，并设置 `STORYTELLER_DATA_DIR=/data`。不要把 `.env`、API key 或 `docker-data` 打包进镜像。

## 升级

发布新镜像后执行 `docker compose pull && docker compose up -d`。只要数据卷不变，项目、设置、音色覆盖和音效库不会随镜像更新删除。升级前建议停止服务并备份 data root。

