# Storyteller 文档

这里是当前行为文档的入口。代码、测试和运行时行为优先于历史设计记录；`docs/reference/tts/` 是厂商原始资料，不能直接视为项目已经实现的能力。

## 第一次使用

- [首次使用指南](getting-started.md)：安装、最小配置、第一次生成、剧本预览和 Web 启动

## 日常使用

- [配置参考](configuration.md)：环境变量、Provider、目录、调度器和 Web runtime settings
- [CLI 参考](cli.md)：生成、续作、音色、音效、Web 和交互式向导
- [Web 使用指南](web.md)：登录、生成、播放、历史故事、音色管理和设置页面
- [音色管理](voice-management.md)：筛选、年龄数组、启用状态、试听片段与本地持久化
- [API 总览](api/overview.md)：认证、资源分组、错误格式和 WebSocket 入口
- [Settings API](api/settings.md)：运行时设置、历史、重置、连接测试和模型列表
- [Voices API](api/voices.md)：音色列表、PATCH override 和试听音频

## 理解内部机制

- [角色与音色匹配](voice-matching.md)：角色元数据、候选池、LLM/rule 回退和日志
- [系统架构](architecture.md)：核心模块、Provider registry 和持久化边界
- [故事生成](story-generation.md)：CLI/Web 流程、状态、缓存和断点续作
- [流式 TTS](streaming-tts.md)：direction、context、调度器和 Provider 会话
- [音效与背景音乐](sound-effects.md)：声音 cue、全局缓存和混音
- [WebSocket API](api/websocket.md)：故事生成和音色分析协议

## 部署与排障

- [Docker 部署](deployment/docker.md)：多架构镜像、Compose、数据持久化和升级
- [生产部署](deployment/production.md)：HTTPS、凭据、持久化和资源限制
- [日志](operations/logging.md)：日志位置、事件字段和检索方式
- [故障排查](operations/troubleshooting.md)：配置、Provider、流式 TTS、音频和 Docker
- [数据与备份](operations/data-and-backup.md)：项目、配置、音效库和恢复边界
- [旧版 Docker 详细说明](deployment-docker.md)：Compose、实时 TTS 和本地开发命令
- [TTS 厂商参考资料](reference/tts/)：阿里云、火山引擎和 Qwen 的原始接口资料
- [Provider 适配](providers/overview.md)：项目统一抽象和新增 Provider 边界
- [阿里云 TTS](providers/aliyun-tts.md)：项目适配、workspace 和 realtime
- [火山引擎 TTS](providers/volcengine-tts.md)：resource id、WebSocket 和 context
- [LLM Provider](providers/llm.md)：模型选择和角色匹配请求

## 开发贡献

- [开发与测试](development.md)：环境、后端/前端验证和代码入口
- [发布流程](release.md)：Git、镜像构建、多平台 manifest 和 smoke test

README 是快速入口；主题文档描述当前实现，厂商原始资料与项目适配说明分开维护。
