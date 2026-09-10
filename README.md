# Storyteller

音频故事生成工具

## 安装

```bash
pip install -e .[dev]
```

## 配置

复制 `.env.example` 到 `.env` 并填入你的 API Key。

## 使用

```bash
# 参数模式
storyteller generate "一只小猫的冒险" --length medium

# 交互式模式
storyteller
```

## 开发

```bash
# 运行测试
pytest

# 覆盖率报告
pytest --cov=storyteller
```
