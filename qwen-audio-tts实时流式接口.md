# 阿里云百炼 实时语音合成（DashScope SDK / Qwen-Audio-TTS · CosyVoice）

> 来源：阿里云百炼官方文档，保存于 2026-09-12，供 Web 流式 TTS 适配层实现参考。
> 非流式 HTTP 接口（现有 aliyun provider 用的 SpeechSynthesizer POST+URL）见
> `src/storyteller/providers/aliyun/tts.py`；本文档是 WebSocket 实时接口。

## 接口地址（WebSocket）

初始化前设置 `dashscope.base_websocket_api_url`（含 WorkspaceId）：

- 华北2（北京）：`wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference`
- 新加坡：`wss://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference`

```python
import dashscope
dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY")  # sk-ws- 业务空间 key
dashscope.base_websocket_api_url = (
    "wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"
)
```

- key 与非流式一样是 `sk-ws-` 开头业务空间 key；plus/flash 均仅北京。
- 建议用业务空间专属域名（性能/稳定性更好），通用域名仍可用。
- SDK 版本：`streaming_cancel` 需 **dashscope >= 1.26.4**。

## SpeechSynthesizer

包路径：`dashscope.audio.tts_v2.SpeechSynthesizer`

```python
SpeechSynthesizer(
    model: str,                       # qwen-audio-3.0-tts-flash / plus、cosyvoice-v2+ ...
    voice: str,                       # 如 longanhuan_v3.6
    format: AudioFormat = AudioFormat.MP3_22050HZ_MONO_256KBPS,
    volume: int = 50,                 # [0,100]，中值 50
    speech_rate: float = 1.0,         # [0.5, 2.0]
    pitch_rate: float = 1.0,          # [0.5, 2.0]
    callback: ResultCallback = None,  # 给了 callback，call() 即以流式回调模式运行
)
```

### 调用方法

| 方法 | 说明 |
| --- | --- |
| `call(text) -> bytes` | 无 callback：阻塞一次性返回完整音频；有 callback：音频走 `on_data` 回调（单向流式）。每次 `call` 前需重新初始化实例 |
| `streaming_call(text)` | 双向流式，可多次追加文本片段；单次 ≤ 20000 字符，累计 ≤ 20 万；**片段间隔不得超过 23 秒**，否则 request timeout |
| `streaming_complete()` | 通知文本发完，阻塞到剩余文本合成完成；不调用会丢尾部 |
| `streaming_cancel(complete_timeout_millis=10000)` | 取消当前轮次；**取消后可在同一连接上发起新合成，无需重新初始化**（>=1.26.4） |
| `get_last_request_id()` | 最近请求 id（排障） |
| `get_first_package_delay()` | 发文本到收到首块音频的毫秒数（合成完成后调用；首次含建连耗时） |
| `get_response()` | 最近响应消息（header/payload） |

双向流式分句行为：服务端自动分句，完整句子立即合成，不完整的缓存；`streaming_complete` 强制合成残余片段。

### 模型限制

- 北京：Qwen-Audio-TTS 全系列支持双向流式；CosyVoice 仅 v2 及以上。
- 新加坡：Qwen-Audio-TTS 全系列支持；CosyVoice 不支持。

## ResultCallback（`dashscope.audio.tts_v2.ResultCallback`）

| 回调 | 时机 |
| --- | --- |
| `on_open()` | WS 连接建立（可初始化输出流） |
| `on_data(data: bytes)` | 每块音频二进制（多次），格式由构造参数 `format` 决定 |
| `on_event(message: str)` | 服务端 JSON 事件：`payload.output.type` = `sentence-begin` / `sentence-synthesis` / `sentence-end`，含 `original_text`、`sentence.index`、开启字时间戳时的 `sentence.words` |
| `on_complete()` | 全部音频返回完毕（之后可查首包延迟） |
| `on_error(message: str)` | 出错，之后连接自动关闭 |
| `on_close()` | 连接关闭（无论正常/异常） |

`on_event` 示例：

```json
{
  "header": {"task_id": "xxx", "event": "result-generated", "attributes": {}},
  "payload": {
    "output": {
      "type": "sentence-begin",
      "original_text": "今天天气怎么样？",
      "sentence": {"index": 0, "words": []}
    }
  }
}
```

## 构造参数详表

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `model` | str | 必填 |
| `voice` | str | 必填，系统音色/复刻音色/声音设计音色 |
| `format` | enum | 默认 `MP3_22050HZ_MONO_256KBPS`，支持 MP3/WAV/PCM 等；`cosyvoice-v1` 不支持 opus |
| `volume` | int | [0,100]，默认 50 |
| `speech_rate` | float | [0.5,2.0]，默认 1.0 |
| `pitch_rate` | float | [0.5,2.0]，默认 1.0 |
| `bit_rate` | int | mp3/opus 码率 kbps，默认 32，[6,510]；**走 `additional_params={"bit_rate": 128}`**；cosyvoice-v1 不支持 |
| `word_timestamp_enabled` | bool | 字级时间戳，仅流式模式；走 `additional_params`。支持：qwen-audio-3.0-tts-plus/flash、cosyvoice-v3.5-plus/flash、v3-flash/plus、v2 的复刻音色及文档标记的系统音色 |
| `seed` | int | [0,65535]，同种子可复现；cosyvoice-v1 不支持 |
| `language_hints` | list[str] | 只用第一个元素；zh/en/fr/de/ja/ko/... 提升数字/符号/小语种效果；v1 不支持 |
| `instruction` | str | 方言/情感/角色演法指令（对应现有 provider 拼接的 directives+context 单 instruction） |
| `enable_aigc_tag` | bool | 嵌入 AIGC 隐性标识（wav/mp3/opus），默认 false；与 `aigc_propagator`、`aigc_propagate_id` 一起走 `additional_params`；仅 qwen-audio-3.0 plus/flash、cosyvoice-v3 plus/flash、v2 |
| `hot_fix` | dict | `{"pronunciation": [{"天气": "tian1 qi4"}], "replace": [{"今天": "金天"}]}`；v1/v2 不支持 |
| `enable_markdown_filter` | bool | 仅 cosyvoice-v3-flash 复刻音色；走 `additional_params` |
| `callback` | ResultCallback | 设置后 `call()` 变流式回调模式 |

## 三种调用方式

1. **非流式**：`audio = synthesizer.call(text)` → bytes，写文件。短文本。每次重新初始化。
2. **单向流式**：构造时传 callback，`call(text)` 立即返回，音频在 `on_data` 分片到达。**适合我们的逐行合成**（每行一条完整文本、要分片低延迟）。
3. **双向流式**：`streaming_call(片段)` 多次 + `streaming_complete()`，适合边出 LLM token 边合成（未来"剧本生成即流式"可用）。

## 对我们流式适配层的要点

- 默认 MP3 分片可直接作为 WebSocket 二进制音频帧透传给浏览器；采样率 22050Hz 单声道（火山是 24kHz，逐行独立解码无碍，最终混音 pydub 已做 `_match`）。
- 不同角色不同 voice → model/voice 是构造期固定参数，需要按 (model, voice) 维护 synthesizer 实例池；首次某音色合成含建连开销。`streaming_cancel` 后连接可复用。
- `instruction` 承接现有 directives/context 拼接逻辑（去#、中文逗号拼接、引用上文丢弃）。
- 参数映射沿用现有 aliyun provider：rate/pitch 倍率直接透传，volume 换算 0–100（中值 50），默认值不进请求。
- `on_event` 的 sentence 事件可做逐句字幕；`word_timestamp_enabled` 未来可替代按字符比例估算音效 anchor 偏移（仅受支持音色）。
- 建连/超时/错误都在回调线程，适配层需把 on_data/on_error 桥接成统一的 chunk/error/end 事件。

## 示例（单向流式，最贴近逐行 TTS 透传）

```python
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, ResultCallback

dashscope.api_key = os.environ["DASHSCOPE_API_KEY"]
dashscope.base_websocket_api_url = (
    "wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"
)

class Callback(ResultCallback):
    def on_open(self): ...
    def on_data(self, data: bytes) -> None:
        # 直接转发给浏览器 / 写文件
        ...
    def on_event(self, message: str):
        output = json.loads(message).get("payload", {}).get("output", {})
        # output["type"] / output["original_text"]
    def on_complete(self): ...
    def on_error(self, message: str): ...
    def on_close(self): ...

synthesizer = SpeechSynthesizer(
    model="qwen-audio-3.0-tts-flash",
    voice="longanhuan_v3.6",
    callback=Callback(),
)
synthesizer.call("今天天气怎么样？")
```
