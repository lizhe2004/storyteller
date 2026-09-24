# 发布流程

1. 在功能分支完成代码、测试和对应文档，确认工作树干净。
2. 运行后端相关测试、前端构建和文档链接/敏感信息检查。
3. 提交并 push Git 分支；合并到目标分支前确认 Dockerfile、Compose、脚本和版本说明一致。
4. 登录 Docker Hub，运行 `scripts/build_and_push_docker.sh` 构建 `linux/amd64,linux/arm64` 并推送 `latest` 与版本标签。
5. 用 `docker buildx imagetools inspect` 确认 manifest 同时包含两个平台，在 Ubuntu 和 macOS Docker 环境做启动 smoke test。
6. 发布后保留 commit、镜像 tag、配置变更和已知限制记录；不要把 `.env` 或 data root 上传到仓库。
