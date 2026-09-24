# 开发与测试

## 本地环境

```bash
pip install -e ".[web,dev]"
```

前端位于 `web/frontend`；构建后的静态资源由 Web 应用提供。后端单元、Web、集成和端到端测试位于 `tests/`。

常用验证：

```bash
python -m pytest -q
cd web/frontend && npm test -- --run && npm run build
```

网络 Provider 测试需要真实凭据时应显式配置；默认优先使用 mock 和单元测试，不要把凭据写入测试文件。修改 Provider、配置、API、日志或音色 catalog 时，必须同步更新对应主题文档。

## 代码入口

CLI 在 `src/storyteller/cli/`，领域流程在 `src/storyteller/core/`，Provider 在 `src/storyteller/providers/`，Web API/流式任务在 `src/storyteller/web/`。先阅读对应 spec/plan 了解历史决策，但当前行为以源码和测试为准。
