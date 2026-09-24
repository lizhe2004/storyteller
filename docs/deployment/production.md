# 生产部署建议

- 使用反向代理提供 HTTPS，并限制 Web 服务只暴露给可信网络；不要直接把未设置密码的服务暴露到公网。
- 通过环境变量或 Docker secret 注入凭据，避免在 `settings.json`、日志和镜像层中出现明文 key。
- 将 `/data` 放在持久磁盘，限制写权限并定期备份；音频项目和音效库会持续增长。
- 根据 Provider 额度设置 TTS scheduler 并发、队列和速率限制，观察 `tts_queue_wait_finished` 和失败事件。
- 发布多架构镜像后在目标平台执行一次登录、options、音色列表和短故事 smoke test。
