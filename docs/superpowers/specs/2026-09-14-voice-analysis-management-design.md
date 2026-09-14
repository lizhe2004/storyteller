# 历史音色分析管理设计

## 目标

提供一个独立的 Web 音色分析管理功能：扫描历史 TTS 音频，将音频关联到剧本、角色、台词和音色声明，使用 Gemini 2.5 Flash-Lite 做单样本分析、Gemini 2.5 Flash 做音色级汇总和匹配评估，并在人工确认后才生成音色库修改。

## 非目标

- 不把音色分析接入故事生成或音频播放 WebSocket。
- 不在第一版自动覆盖 `voices.json`。
- 不分析用户上传的真人录音；第一版只分析项目生成的历史 TTS 音频。
- 不把模型思考摘要直接作为音色匹配算法输入。

## 架构

音色分析是后端独立运行的持久化任务。任务创建后即使浏览器关闭也继续执行，进度和结果写入 `.storyteller/voice-analysis/<job_id>/`。列表页通过 HTTP 轮询任务摘要，详情页通过独立的 `/ws/voice-analysis` 接收实时 JSON 事件；多个分析任务通过事件中的 `job_id` 复用同一条详情连接。

音频生成仍使用现有 `/ws`，两套任务管理和消息协议互不共享。

## 分析阶段

1. `scanning`：扫描历史项目并关联 `story.script.json`、音频、角色、台词和 `voice_config`。
2. `sampling`：按音色分层抽取最多 10 个样本，允许配置到 20 个；尽量覆盖不同故事、旁白/对白、台词长度和情绪。
3. `extracting_features`：本地提取时长、音量、静音比例等客观音频特征；可扩展基频和语速。
4. `analyzing_samples`：Gemini 2.5 Flash-Lite 对单个样本进行独立音频听感分析。
5. `aggregating_voices`：Gemini 2.5 Flash 汇总同一音色的多个样本，识别稳定特征和异常样本。
6. `comparing_catalog`：将实际特征与任务创建时保存的音色库声明比较。
7. `evaluating_roles`：结合历史角色描述和台词评估历史匹配效果。
8. `generating_suggestions`：生成可人工审核的音色库修改建议。

单样本分析应先只依据音频判断实际表现，避免被官方音色描述诱导；声明对比和角色匹配在后续阶段完成。

## 持久化格式

```text
.storyteller/voice-analysis/<job_id>/
├── manifest.json
├── samples.json
├── sample-results/<sample_id>.json
├── voice-summaries/<voice_key>.json
└── suggestions.json
```

`manifest.json` 保存任务状态、模型、提示词版本、总量和进度。`samples.json` 保存样本与历史业务数据的关联，并保存 `catalog_snapshot`，保证未来音色库变化不会改变历史比较基准。单样本结果和汇总结果分别保存原始响应、归一化响应、错误、重试次数和时间。

断点续跑使用 `sample_id + model + prompt_version + analysis_config_version` 判断结果是否可复用。任务中断只继续未完成单元；模型、提示词或配置版本变化时生成新结果，不覆盖旧结果。

## 后端接口

```text
POST /api/voice-analysis/jobs
GET  /api/voice-analysis/jobs
GET  /api/voice-analysis/jobs/{job_id}
POST /api/voice-analysis/jobs/{job_id}/resume
POST /api/voice-analysis/jobs/{job_id}/cancel
POST /api/voice-analysis/jobs/{job_id}/retry
GET  /api/voice-analysis/jobs/{job_id}/voices
GET  /api/voice-analysis/jobs/{job_id}/voices/{voice_key}
GET  /api/voice-analysis/jobs/{job_id}/suggestions
POST /api/voice-analysis/suggestions/{suggestion_id}/approve
POST /api/voice-analysis/suggestions/{suggestion_id}/reject
```

## 实时通信

音色分析使用独立的 JSON-only WebSocket：

```text
/ws/voice-analysis
```

详情页发送订阅消息：

```json
{"type":"subscribe","job_ids":["analysis_001"]}
```

服务端发送 `ready`、`snapshot`、`progress`、`sample_ready`、`voice_summary_ready`、`suggestion_ready` 和终态事件。连接断开时，页面先用 REST 快照恢复，再重新连接 WebSocket；WebSocket 不承担历史事件回放，持久化文件是最终事实来源。

## 页面

分析列表页展示任务摘要，通过 3 秒轮询更新运行中任务；没有运行中任务或页面隐藏时降低/停止轮询。详情页展示阶段进度、样本结果、音色汇总和建议，并连接独立 WebSocket 获取实时变化。

详情页包含：

- 当前阶段和总体进度；
- 成功、失败、跳过和可重试数量；
- 音色列表及声明匹配度、角色匹配度；
- 音频播放器、故事/角色/台词信息；
- 原始声明、实际观察结果、本地音频特征、Gemini evidence 和置信度；
- 人工接受、拒绝或编辑建议的操作。

## 安全与成本

API Key 只从服务端环境配置读取，不写入结果、日志或前端。原始 Gemini 响应可以保存到任务目录，但页面默认展示归一化结果和分析摘要，不展示密钥或完整请求头。Flash-Lite 用于批量初筛，Flash 只处理音色级汇总、疑难样本和建议生成；任务支持限速、失败重试和配额错误提示。

## 验收标准

- 启动任务后关闭浏览器，后端任务仍能继续并更新 `manifest.json`。
- 重新打开详情页时先显示快照，再收到后续 WebSocket 进度。
- 列表页不连接音频播放 WebSocket，仍能通过轮询显示任务进度。
- 单个样本失败可以独立重试，任务重启不会重复调用已完成样本。
- 同一个音色可以查看多个历史样本及其对应角色和台词。
- 最终生成建议但不自动修改正式音色库。
- Gemini 返回字段经过版本化、校验和归一化，非法结果不会阻塞整个任务。
