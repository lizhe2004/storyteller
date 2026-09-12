# Web 界面、HTTP API 与逐行流式播放设计

- 日期：2026-09-12
- 状态：已批准（brainstorming 四节设计均获用户确认）
- 范围：在现有 CLI 之外新增 Web 子系统——单密码鉴权、FastAPI 后端、Vue 3 前端、WebSocket 双通道（文本事件 + 二进制音频），核心是**逐行 TTS 流：无音效行 PCM 帧透传 + 有音效行等待逐行混音后整行发送**，并保留同项目的全片精混下载版。

## 1. 目标与范围

### 1.1 目标

1. 浏览器里输主题→快速听到第一句（首音延迟尽量接近 provider 首包延迟），之后逐行连续无隙播放，同时看逐句字幕与阶段进度。
2. 新增一套 provider 无关的**流式 TTS 适配层**：火山现有 NDJSON 流先实现；阿里云实时接口（DashScope WebSocket，见仓库根目录 `qwen-audio-tts实时流式接口.md`）作为同一契约的第二个 adapter，未实现前自动降级整行 mp3。
3. 带音效/BGM 的故事同样支持：每行人声与该行音效混合后推送，用户已确认愿意为带 cue 的行等待混音；流结束后用现有全片逻辑产出精混 `story.mp3` 供下载。
4. 单密码列表鉴权（env 维护），小范围公网分享，无用户体系。
5. 历史故事列表/详情回放/下载，与 CLI 共用 `.storyteller/` 数据根。

### 1.2 首版不做

- 从剧本 LLM token 级流式（首版剧本仍一次性生成）。
- 直播流的进度条拖拽 seek；complete 后切最终 mp3 的普通播放器做 seek/重播。
- 用户体系、多租户隔离；所有持密码者可见全部历史。
- 独立 worker/Redis 队列；单进程线程池 + 薄 JobManager 抽象应对小范围并发。
- 阿里云实时 adapter 的 dashscope SDK 集成（契约与降级先行；列为 P2，见 §10）。
- Web 端续编/重做、逐角色 Web 端挑音/试听、音效库浏览。

### 1.3 成功标准

- 无音效短故事：提交后经历剧本生成 + 音色匹配等待，之后**每一行**（而非全片）TTS 首包即可闻，行间无 audible gap；iPhone Safari 可正常播放。
- 有音效故事：带 cue 的行在该行 TTS + 音效物化 + 单行动态混音后可闻，内容与响度策略和 CLI 产物一致；最终下载版由现有全片精混产出。
- 网络抖动导致 WS 断开时任务继续，重连可收到当前阶段状态；最终产物不丢。
- CLI 现有 337 测试全绿，CLI 行为零变化。

## 2. 总体架构

### 2.1 进程与并发模型

- 单个 FastAPI 应用（uvicorn 启动），同时服务 REST、WebSocket、Vue 构建产物（StaticFiles）。
- 生成是同步阻塞代码（requests、pydub→ffmpeg），放**线程池**（并发上限可配，默认 2，其余任务排队）；任务线程通过线程安全队列与 WS 连接线程桥接。
- `JobManager`（接口 + 内存实现：`dict[job_id] → Job`，含状态、参数、取消标志、行计数、event queue、project_id）；路由层只依赖接口，将来可换 Redis/RQ 实现。
- WS 可以先连接后启动任务：客户端连 `/ws` → 发 `start` → 线程池提交。也支持携带 job_id 重连。
- 任务线程**逐行落盘**（PCM 累积编码的 mp3 段、project.json、script JSON），断连只丢实时帧，任务在后台继续。

### 2.2 模块划分

```
src/storyteller/web/
  __init__.py
  app.py                 # create_app() 工厂：异常处理、静态回退、路由注册
  config.py              # web.* 配置访问（host/port/passwords/secret/concurrency...）
  auth.py                # 密码校验、HMAC token 依赖（REST 依赖 + WS 握手校验）
  jobs.py                # JobManager 内存实现、Job 状态机、取消标志
  schemas.py             # pydantic 请求/响应模型
  routes_auth.py         # POST /api/auth, /api/auth/logout, GET /api/me
  routes_options.py      # GET /api/config/options
  routes_stories.py      # 历史列表/详情/音频文件
  routes_ws.py           # /ws：start/cancel/重连，事件循环
  streaming.py           # StreamOrchestrator：剧本→音色→逐行→精混的流式编排
  mixes.py               # 单行动态混音（复用 audio.py 的组轨道构建/响度/grace）
  tts_chunks.py          # StreamChunk 定义 + PCM s16le 累积→mp3 编码落盘
  frontend/              # Vue 3 + Vite + TS 工程（独立 package.json，见 §7）
  static/                # npm run build 产物（FastAPI 实际托管目录；入 .gitignore）
```

CLI 新增 `storyteller web --host --port`（click 命令，与 generate/continue/make-sound 等并列），调用 `create_app` + uvicorn.run。依赖新增 `fastapi`、`uvicorn[standard]`、`itsdangerous`；dashscope 列入可选依赖组（如 `web-realtime`，P2 才真正使用）。

### 2.3 鉴权

- 密码列表来自 `STORYTELLER_WEB_PASSWORDS`（逗号分隔）；真实密码只在 `.env`（沿用 `.env.example` 仅占位符、`.env` 被 gitignore 的约定）。
- `POST /api/auth`（`{password}`）→ 用 itsdangerous `URLSafeTimedSerializer` 签 token，set httpOnly cookie：`HttpOnly; SameSite=Lax; Path=/;` 与请求是 https 时加 `Secure`。有效期默认 30 天可配（`STORYTELLER_WEB_TOKEN_TTL_DAYS`）。
- 签名密钥取 `STORYTELLER_WEB_SECRET`；未配置则启动生成临时密钥并打印警告（重启即所有会话失效）。
- REST 用 FastAPI 依赖校验；WS 握手时优先 cookie，无则取 `?token=`。
- 对 `/api/auth` 和建立 WS 做简单内存限流（默认 10 次/分/IP，可关）。
- `/api/config/options` 只返回 provider 名与可选项，绝不回显 key/endpoint（阿里专属域名含 WorkspaceId 也算敏感，不回显）。

### 2.4 数据根与产物

Web 与 CLI 共用同一个 `data_dir`（默认 `./.storyteller`）：新项目写进 `.storyteller/stories/<date-title>/`，per-line 段仍放 `audio/<line_id>.mp3`，最终产物 `story.mp3` + `story.script.json`。历史列表直接复用 ProjectManager 的目录扫描/解析，Web 不引入第二套存储。

## 3. 流式 TTS 适配层

### 3.1 契约（能力接口，不强制所有 provider）

在现有 `core/tts.py` 的 `TTSProvider` 之外新增：

```python
# web/tts_chunks.py（或 core/tts.py 旁，实现阶段定）
@dataclass
class StreamChunk:
    kind: str            # "audio" | "event"
    data: object         # audio -> bytes (PCM s16le mono)；event -> dict（逐句事件，预留）

class StreamingTTSProvider(Protocol):
    @property
    def supports_streaming(self) -> bool: ...
    def stream_synthesize(self, text, voice, *, directives, context,
                           sample_rate: int) -> Iterator[StreamChunk]: ...
```

- registry 新增能力探测：`registry.get_stream_tts(name)`：注册的 provider 实现了该方法且 `supports_streaming` 为真才返回，否则 None→编排层降级。
- 统一输出 **PCM s16le 单声道**（无音效透传格式）：火山请求 `pcm` + 24kHz（ogg_opus 才需 48k 的规则不适用）；阿里 adapter 用 `AudioFormat.PCM_22050HZ_MONO_16BIT`（22.05kHz）。sample_rate 由 provider 决定并随 `line_start` 声明给前端。
- 每行独立合成： directives/context 沿用现有 `_line_context`（direction 加 `#`、最近一句旁白+对话引用上文）。

### 3.2 火山 adapter（P1）

- 把 `providers/volcengine/tts.py` 的 `_read_stream` 重构为生成器 `_iter_ndjson(response)`：iter_lines 逐行 json.loads，done code 20000000 break；错误 code 抛 TTSError；`data` 字段 base64 解码后 yield bytes（pcm 格式时本身就是裸 PCM s16le 24k mono）。
- 现有 `synthesize()` 改为：跑一遍生成器收齐字节写文件，行为/错误消息不变；新增 `stream_synthesize` 包成 `StreamChunk(kind="audio", ...)`。
- 请求体构造（speaker、speech_rate/loudness_rate int 偏移、pitch、additions.context_texts）抽公共方法，两条路径共用。
- 现有 TTS 单测全绿是必须守住的回归线；新增用 responses mock（或注入假 iter_lines）验证 chunk 迭代器与错误传播。

### 3.3 阿里云实时 adapter（P2，契约 P1 定义好）

- 延迟 import dashscope（`dashscope.audio.tts_v2.SpeechSynthesizer, ResultCallback`），无 SDK/无实时相关配置时 `supports_streaming=False`。
- 单向流式模式最贴合逐行：构造传 callback，`call(line.text)`，音频在 `on_data(bytes)` 到达；按 `(model, voice)` 池化 synthesizer 实例（model/voice 构造期固定，首次建连有开销；`streaming_cancel` 后连接可复用）。
- 回调→队列桥：`on_data` push PCM 块、`on_complete` sentinel、`on_error` 推送后连接自动关闭→生成器收齐后把队列内容 yield 成 StreamChunk；在生成器里用 `queue.Queue` 桥，确保与火山路径同构。
- 参数沿用非流式 aliyun provider 的映射：rate/pitch 0.5–2.0 直接透传、volume 0–100（中值 50）、默认值不进构造参数；`instruction` 沿用 directives/context 拼接（去#、中文逗号拼接、引用上文丢弃）。
- 双向流 `streaming_call` 模式留给将来"剧本 token 级流"（§1.2 明确首版不做）。
- 配置扩展示意：在现有 `STORYTELLER_TTS_ALIYUN_*` 上加 `REALTIME_ENDPOINT`/`base_websocket_api_url`（含 WorkspaceId 的 wss 地址）；没有配就只注册非流式能力。
- 真机验证用例写进实现计划：flash/plus 各一个音色确认 22.05k PCM 透传可播、instruction 生效、连接池复用。

## 4. 逐行混音与两条发送路径

### 4.1 路径选择（每行开始时确定）

对当前行收集该行的 cues（`line.sound_effects` + `line.background_music`，经现有 anchor 校验后非空）及 provider 流式能力：

| 条件 | 路径 |
| --- | --- |
| 行内无有效 cue 且所选 provider 支持流式 | **A：PCM 透传**——`line_start(mode=pcm)` → 逐二进制帧 → `line_end` |
| 行内有有效 cue（与是否支持流无关） | **B：整行合成 + 逐行混音**——整行人声收齐 → 音效物化 → pydub 混音落盘 mp3 → `line_start(mode=file, audio_url)`，客户端 fetch 后排进同一时间轴（见 §5.2） |
| 无 cue 但 provider 不支持流 | A 的降级：整行 mp3 合成落盘后同样以 mode=file + URL 发送，事件序列不变 |

用户已确认选"等本行混完再推"：路径 B 的延迟=该行 TTS + 该行未命中音效的 API 时间（含最多 3 次近静音重试），属于已接受代价。

### 4.2 单行动态混音（`web/mixes.py` + `core/audio.py`）

新增 `PydubAudioProcessor.mix_line(main_line_path, entries, output_path)`：

- 直接复用 `_build_group_track(reference, entries, line_duration_sec)`（响度归一、`_MAX_BOOST_DB`、组上限、anchor 偏移、`_trim_to_window` + 2s grace、近静音跳过），然后 `main.overlay(track, position=0)` 导出。
- entries 仍是 `(cue, offset_sec)`，offset 用现有 `Pipeline._anchor_offset`（字符比例估算，一行内自校准）；ambient/music offset=0。
- 一行就是自己的零点，start=0，不需要全片 start 偏移；导出格式与最终一致（mp3）。
- 音效物化完全复用 pipeline 现有构件：时长增强 prompt（`build_sound_prompt`，该行真实时长从收齐的人声段量得）→ `SoundLibrary.find` → 未命中 `_generate_cue_with_retry` → admit 进全局库 + 副本进项目 sounds/。**同一 gen_prompt 指纹一致，最终精混时零 API 调用**。
- BGM 注释开关（当前 BGM 不混最终文件，pipeline.py:673-680）的行为对齐：若 CLI 保持关闭，Web 也不把 line.background_music entries 混音；顶层 BGM 在精混阶段处理。实现时以代码现状为准。

### 4.3 落盘与精混

- 路径 A：服务端边转发 PCM 边累积到 buffer；`line_end` 前在任务线程内用 pydub 把整行 PCM 编码成 mp3 写 `audio/<line_id>.mp3`（ffmpeg 编码一个十几秒的单声道段是百毫秒级，放在下一行 TTS 之前串行执行；若 P1 真机实测拖慢节奏，P2 再改成与下一行 TTS 并行），并回填 `line.audio_path`。与现有目录约定完全一致，供 resume、拼接、timing。
- 路径 B：混音输出即 canonical 行段文件，直接落 `audio/<line_id>.mp3`。
- 流结束后：拼接所有行段（现有 concatenate）→ 开音效时现有 `_apply_soundtrack`（行内 cue 全部缓存命中；只新生成顶层 music/effect）→ `story.mp3`，状态 completed。
- **已知差异（接受）**：直播中 effect 的 2s tail grace 顺延到下一行开头发送时刻可能与下一行起点有微小相位/听感差异；精混版是权威产物（grace 叠在下一句开头、顶层 BGM 正确混入、fade 完整）。直播以"快速听到"优先。
- 不开音效时：直播 PCM 与最终 concatenate 的内容应逐样本接近（编码/解码路径不同会有微小差别），最终版仍走现有拼接保证 resume/下载一致性。

### 4.4 取消与失败

- cancel：只在**行边界**检查取消标志，不强杀进行中的 provider 调用；已生成段保留，不产出 story.mp3，project 状态置 `generating_audio`（resume 可用，与 CLI resume 语义一致），发完当前行后回 `canceled`。
- 单行 TTS 失败：沿用宽松模式——发 `warning` 事件，跳过该行继续；零行成功则任务 failed（同现有 "No audio segments" 错误）。
- 严格模式可在 start 参数里传，首版可不暴露。

## 5. WebSocket 协议

连接：`/ws`（未启动时）或 `/ws?job_id=<id>`（重连）；鉴权 cookie 或 token 参数。

### 5.1 客户端 → 服务端（JSON 文本帧）

```json
{"type": "start", "topic": "...", "length": "short|medium|long",
 "complexity": "simple|...", "with_sound": false, "tts_providers": ["volcengine"]}
{"type": "cancel"}
```

### 5.2 服务端 → 客户端

文本帧（JSON）：

| type | 字段 | 说明 |
| --- | --- | --- |
| `status` | `phase` ∈ script/voices/line/finalizing, `message` | 阶段提示 |
| `script_ready` | `title`, `lines:[{line_id,line_type,character_id,speaker}]`, `total` | 剧本+音色完成，字幕骨架 |
| `line_start` | `line_id,index,total,speaker,text,has_sound,mode(pcm\|file),sample_rate,audio_url?` | 二进制归属行开始；mode=pcm 时后续二进制是 s16le；mode=file 时带 audio_url 且无二进制 |
| `warning` | `line_id?,message` | 行跳过/ cue 废片等 |
| `line_end` | `line_id,duration_ms` | 该行真实时长 |
| `finalizing` | — | 全部行完成，拼接/精混中 |
| `complete` | `project_id,title,audio_url,script_url,duration_ms` | 最终精混版就绪 |
| `error` | `message` | 任务失败 |
| `canceled` | — | 被取消 |

二进制帧：两个 marker 之间的所有二进制属于当前行。PCM=s16le little-endian、mono、sample_rate 由 line_start 告知；file 模式下二进制就是完整 mp3（也可选择服务端落盘后只发 URL，见下）。

**决策：file 模式（路径 B 与降级）发完整 mp3 二进制**还是发 URL 让客户端 fetch？设计取**后者**——混好的行已落盘，line_start(mode=file, audio_url=…,duration_ms) 不带二进制，客户端用同一时间轴队列 fetch+decodeAudioData 排队。好处：WS 不混二进制语义、Range/缓存友好、重连后混过的行可重取。PCM 路径保持二进制帧（要低延迟，不产生可 Range 的中间文件以外的请求）。

### 5.3 重连行为

- `/ws?job_id=x`：Job 存在 → 立即推一条 `status`（当前 phase、index/total）+ 必要的 `script_ready`；任务继续。
- 错过的 PCM 行不补（直播性质），前端提示"已从第 i 行继续"；错过但已落盘的行（file 模式/最终 complete）可按 URL 取。
- Job 不存在/属于已结束很久被清理的内存任务 → 客户端走历史详情接口（最终产物在磁盘上）。
- 同一个 job 允许新连接顶替旧连接（单观众语义），旧连接关闭。

## 6. REST API

除标注外均需有效 cookie。

| 方法/路径 | 作用 |
| --- | --- |
| `POST /api/auth` | 密码换 cookie；错误密码 401 |
| `POST /api/auth/logout` | 清 cookie |
| `GET /api/me` | 登录态探测 |
| `GET /api/config/options` | lengths/complexities 枚举、已注册 TTS provider（名+显示名）、音效可用（配了 sound key 才 true） |
| `GET /api/stories` | 历史：数组项 `{id, dir_name, title, state, duration_ms?, created_at}`，按时间倒序 |
| `GET /api/stories/{ref}` | 详情：title/topic/characters（name/voice name）/lines（id/type/speaker/text/duration_ms），不回绝对路径 |
| `GET /api/stories/{ref}/audio` | `story.mp3` FileResponse（支持 Range；不存在→404） |
| `GET /api/stories/{ref}/segments/{line_id}.mp3` | 逐行段（file 模式队列与重连用），白名单校验 line_id 防穿越 |

ref 沿用 ProjectManager.resolve_project_dir 的解析（目录名/id/前缀，歧义→400）。任务创建走 WS start，不另开非流式创建接口（§1.2 已缩范围；将来要"后台跑好了通知"再加 POST）。

## 7. 前端（Vue 3 + Vite + TS）

### 7.1 工程与页面

- `web/frontend/`：Vue 3 + Vue Router + Pinia（auth、player 两个 store 足够）+ Vitest。**不引入组件库硬依赖**（几个页面用手写 CSS，中文排版；实现时可换轻量库，不打包大型 UI framework）。
- 路由守卫：`/login`、`/`（生成+播放，可同页状态切换，避免跳转打断音频）、`/stories`、`/stories/:ref`。401 清态回登录页。
- `vite.config.ts` 开 server.proxy：`/api`、`/ws`（ws: true）→ `http://127.0.0.1:8000`。

### 7.2 音频时间轴 composable（核心）

`useAudioTimeline.ts`：

- 单 AudioContext（提交点击时构造/resume 满足自动播放策略）。
- PCM：二进制帧 append 到当前行 Int16 buffer；在"行开始"或 buffer 累计达 ~200ms 时批量 Float32 转换、建 AudioBufferSourceNode，按 `max(now+0.05, cursor)` 顺序 start；`cursor` 持续推进。200–300ms 抖动缓冲吸收网络与生成抖动。
- file 行：拿到 audio_url 后 fetch → `ctx.decodeAudioData` → 同一 cursor 排队；URL 模式下该类行天然可等。
- 不同采样率的块按行隔离（line_start 带 sample_rate），AudioBuffer 自带 rate，硬件输出统一重采样，无需手动处理。
- 状态：`bufferedMs`、`playedMs`（requestAnimationFrame 读 ctx.currentTime）、当前播放行 index；暂停/继续 = `ctx.suspend()/resume()`；关闭页面前 close。
- 不做直播 seek；complete 后"播放完整版"切隐藏 `<audio src=audio_url>`（自带 seek/进度条），时间轴可停止。

### 7.3 UI

- 生成表单：主题（textarea）、长度、复杂度、"加音效"开关（sound 不可用时禁用并提示）、TTS provider 多选（默认配置的 default）。
- 播放视图：阶段状态条、逐句字幕（高亮跟随 playedMs，按 line duration 比例在段内推进）、warning 灰色行内提示、取消按钮、最终"下载/完整版播放"按钮。
- 历史：卡片/列表，详情页剧本滚动 + 标准版音频播放器 + 下载。
- 登录：单输入框，错误提示不区分"密码错"与"未配置密码列表"（避免探测）。

### 7.4 构建/托管

`npm install && npm run build` → `web/static/`；FastAPI StaticFiles 挂 `/assets`，catch-all 非 API/WS 路径返回 `index.html`。`web/static` 入 .gitignore（构建产物）；README 写清本地开发（uvicorn + vite dev 两端）与构建运行（构建后 `storyteller web`）两种方式。

## 8. 配置项（新增）

| env | 默认 | 说明 |
| --- | --- | --- |
| `STORYTELLER_WEB_PASSWORDS` | 空（web 命令拒绝启动并提示） | 逗号分隔密码 |
| `STORYTELLER_WEB_SECRET` | 启动临时生成+警告 | token 签名密钥 |
| `STORYTELLER_WEB_TOKEN_TTL_DAYS` | 30 | cookie/token 有效期 |
| `STORYTELLER_WEB_HOST` / `_PORT` | 127.0.0.1 / 8000 | 默认只监听本机；公网用需显式 0.0.0.0 |
| `STORYTELLER_WEB_CONCURRENCY` | 2 | 同时生成任务数 |
| `STORYTELLER_WEB_RATE_LIMIT_PER_MIN` | 10 | auth/WS 建连每 IP 限流，0=关 |
| `STORYTELLER_TTS_ALIYUN_REALTIME_ENDPOINT` | — | P2：wss 含 WorkspaceId 地址，配了才启用实时能力 |

其余（data_dir、provider keys、sound 开关、strict_mode）全部复用现有配置。

## 9. 测试策略

- **后端单测（pytest + 现有 mock provider 体系）**
  - 适配层：火山 chunk 迭代器（NDJSON 正常/done/错误码/坏 JSON）；registry 能力探测与无能力 provider 降级。
  - 两条路径：MockStreamingTTS（发确定性 PCM 正弦）+ MockSoundProvider（现有可闻正弦 wav）→ 事件序列严格断言：status×N → script_ready → 每两行 line_start/chunks/line_end → complete；落盘的行段/script/project.json 正确；B 行 mix_line 输出时长≈人声时长且 cue 可闻（减轨互相关，沿用既有验证法）。
  - PCM→mp3 编码落盘；sample_rate 随事件正确声明。
  - 鉴权：对/错密码、过期/篡改 token、WS cookie 与 ?token=、options 无密钥回显、限流。
  - 重连：任务运行中断开→以 job_id 重连→收到当前 status；旧连接被顶替。
  - cancel：行边界生效、project 留可 resume 状态、不产 story.mp3。
  - 历史接口：列表/详情/音频/段下载、line_id 白名单防穿越、歧义 ref→400。
  - CLI 回归：`storyteller` 现有全部测试（337）全绿；volcengine tts 重构前后字节一致（mock NDJSON 比较输出）。
- **前端单测（Vitest）**：mock WebSocket + 假 AudioContext（手动推进 currentTime），断言帧到达顺序与 source.start 时间、行切换 sample_rate、暂停恢复、file 行 fetch 排队。
- **手动真机验证（写入计划的验收步）**：
  1. 火山无音效短故事：量首音延迟、确认行间无隙、iPhone Safari（需真机或同学设备）播放。
  2. 火山有音效故事（如《小松鼠》同类）：B 行延迟可接受、cue 与 CLI 同 prompt 缓存命中、complete 后下载版正确。
  3. 断网 5 秒重连恢复；错误密码/过期 cookie 行为；手机浏览器 AudioContext 手势要求成立。
  4. P2：阿里 flash+plus 实时 PCM 与非流式降级分别验证。

## 10. 分期建议

- **P1（本次实现计划范围）**：web 骨架+鉴权+JobManager+WS 协议+火山流式 adapter（重构）+两条路径+mix_line+PCM 时间轴前端+历史接口+测试。dashscope 实时仅保留降级路径与配置预留。
- **P2**：阿里云 dashscope 实时 adapter（实例池+回调桥）+真机；如果 P1 实测 PCM 编码成为瓶颈再做行编码与下一行 TTS 的并行。
- **P3+**：剧本 token 级流（阿里双向流/火山分句）、直播 seek（服务端保留 PCM 索引）、POST 创建+后台通知、Web 端声音选择。

## 11. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 手机浏览器 AudioContext 自动播放限制 | 必须在提交按钮手势回调里创建/resume；真机验证列入验收 |
| 24k/22.05k PCM 裸流无语义自描述，采样率不匹配会变速 | line_start 强制带 sample_rate；前端按行建 buffer；单测锁定 |
| PCM 带宽（约 350-380kbps，3 分钟 ~8MB） | 小范围分享可接受；未来可换 opus 帧（需自己打包） |
| 线程池中 pydub/ffmpeg 阻塞 + 并发 2 | 任务排队位置通过 WS status 告知；ffmpeg 子进程并发安全（独立输出文件） |
| WS 在反代下空闲断开（nginx 默认 60s read timeout） | 文档要求反代配 ws 超时；可加心跳帧（P1 实现时每 15s ping） |
| 直播混音与精混不一致引起用户困惑 | UI 明确"直播版/精混下载版"；下载版标为完整版 |
| 临时 WEB_SECRET 重启掉登录 | 启动 warning + README/.env.example 说明 |
