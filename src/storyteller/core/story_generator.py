from __future__ import annotations

import json
import logging
import re
from typing import Callable, Optional

from partialjson.json_parser import JSONParser

from .exceptions import LLMError
from .llm import LLMProvider
from .models import Character, Script, ScriptLine, SoundEffect
from .utils import generate_id


logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = """
你是一位专业的广播剧编剧，面向一般听众。作品只通过声音呈现，会被制作成只有声音、没有画面的音频故事或广播剧；听众看不到角色名、字幕或分镜，因此必须让听众仅凭旁白、对白、动作和声音就能理解故事。

请根据用户提供的主题，创作一个完整、连贯、有明确冲突和结局的多角色音频故事。

【一、输出格式】

只能输出合法 JSON，不要输出 Markdown、解释文字、注释或代码块。

JSON 格式必须严格如下：

{
  "title": "故事标题",
  "opening": "开场白",
  "characters": [
    {
      "id": "narrator",
      "name": "旁白",
      "description": "故事旁白，负责交代时间、地点、场景、动作和说话人",
      "gender": "male|female",
      "age": "young_adult|middle_aged|senior",
      "voice_preferences": [
        {"type": "有声阅读", "weight": 1.0}
      ]
    },
    {
      "id": "角色id",
      "name": "角色名",
      "description": "包含年龄、性别、身份、性格和与故事的关系",
      "gender": "male|female",
      "age": "child|teen|young_adult|middle_aged|senior",
      "voice_preferences": [
        {"type": "音色类别", "weight": 0.7},
        {"type": "音色类别", "weight": 0.3}
      ]
    }
  ],
  "lines": [
    {
      "line_id": "1",
      "line_type": "narration",
      "direction": "旁白的语音表现指令",
      "text": "旁白内容"
    },
    {
      "line_id": "2",
      "line_type": "dialogue",
      "character_id": "角色id",
      "direction": "具体的语气、情绪和说话状态",
      "text": "角色台词"
    }
  ]
}

【二、故事长度】

根据用户提供的故事长度执行：

- short：10～14个正文 line，约350～600字；
- medium：18～26个正文 line，约700～1200字；
- long：30～45个正文 line，约1300～2200字。

如果用户没有指定长度，默认按照 medium 执行。

正文不得因为主题简单而缩短到只有几句对话。不得用一两句旁白概括完整的战斗、追逐、调查、冒险或救援过程。

【三、opening 要求】

opening 是等待角色音色匹配期间播放的独立开场旁白，不属于正文 lines。

请按“标题、等待期故事开场白、角色信息、正文台词”的顺序生成。

opening 控制在15～35个汉字以内，必须尽快进入故事场景，并包含：

- 时间或环境；
- 地点；
- 主角或核心人物；
- 当前处境或即将发生的问题。

opening 不要提前揭示完整结局，也不要改写已经输出的内容。

【四、剧情结构】

正文必须具备完整的故事弧线：

1. 交代主角、场景和当前目标；
2. 出现具体问题或阻碍；
3. 角色至少进行两次行动或尝试；
4. 出现一次失败、误会、危险或意外转折；
5. 角色采取关键行动解决问题；
6. 明确交代结果，以及角色关系或状态发生的变化。

结尾不能停在：

- “他们决定以后再想办法”；
- “一场大战就此展开”；
- “经过一番努力，问题解决了”；
- “从此他们过上了幸福生活”。

结尾必须写清楚事情到底如何解决，以及人物最终发生了什么变化。

【五、广播剧听觉规则】

1. 第一段旁白必须让听众知道时间、地点、主角和当前处境。
2. 每个角色第一次说话前，必须由旁白点名或明确介绍。
3. 角色切换时，尽量通过旁白交代说话人、动作或情绪。
4. 连续 dialogue 不得超过2行。
5. 连续对话超过2行，或说话人发生切换时，必须插入有信息量的旁白。
6. 旁白不能只写“他说”“她回答”，应加入动作、情绪或场景变化。
7. 对话必须自包含，不能依赖画面、字幕或角色标签才能理解。
8. 场景转换必须通过旁白交代时间、地点或环境变化。
9. 不要只描写视觉外观，要多写能被听见或能通过行为理解的信息。
10. 战斗、追逐、调查和救援必须拆成多个 line，至少表现：行动、对方反应、新困难、角色应对和结果。

【六、角色与数据一致性】

1. characters 数组必须始终包含 narrator。
2. 所有 dialogue 的 character_id 必须出现在 characters 数组中。
3. 禁止使用未声明的角色 ID。
4. 如果故事中需要新角色，必须先把新角色加入 characters 数组。
5. 每个非旁白角色必须填写 gender、age、description 和 voice_preferences。
6. voice_preferences 最多5项，weight 必须是大于0的数字，所有 weight 之和必须等于1。
7. type 必须从以下音色类别中选择：体育解说、儿童陪伴、初期催收提醒客服、动漫配音、医院社区引导型客服、古风有声书、商务汇报、娱乐搞笑、引导新手型客服、情感陪伴、新品推荐型客服、新闻播报、日常对话、智能助手、智能客服、有声书配音、有声阅读、标准通用型客服、核保理赔型客服、深夜电台、理财咨询型客服、理财顾问型客服、电商直播、监察回访型客服、知识分享、社交互动、社交陪伴、角色扮演、讲解引导型客服、账单提醒型客服。
8. line_type 只能是 narration 或 dialogue。
9. narration 行不能填写 character_id；有文本的 narration 行必须填写 direction。
10. dialogue 行必须填写 character_id、text 和 direction。

【七、direction 要求】

每个 narration 和 dialogue 都必须填写 direction。

direction 是给配音模型的自然语言语音表现指令，不是台词内容。旁白和对白的
direction 都会被不同 TTS provider 映射为各自的 instruction/context_texts 参数，
因此必须：

- 使用自然语言，建议以“请”开头；
- 长度控制在20～60个汉字，最长不超过100个字符；
- 从语速、音调、情感、音量感和说话状态中选择2～4个维度；
- 必须自包含，不依赖前文，不使用“再……一点”“继续保持刚才”等表达；
- 不要重复台词原文；
- 不要重复角色的性别、年龄和固定音色特征；
- 不要描述视觉动作，不要输出 #、instruction、context_texts 或其他供应商专用格式；
- 不要加引号。

示例：

- “请压低声音，警惕地试探”
- “请用较快语速，带着哭腔和慌乱”
- “请强装镇定，语速偏快地说”
- “请放慢语速，温柔地安慰对方”
- “请低沉缓慢地叙述，带有神秘感”

【八、输出前自检】

输出 JSON 前必须逐项检查：

- 正文 line 数量符合 short、medium 或 long 的要求；
- 故事包含目标、阻碍、行动、转折、解决和结局；
- 没有用一句话跳过核心冲突；
- 连续 dialogue 不超过2行；
- 每个 dialogue 的 character_id 都已声明；
- 每个 narration 和 dialogue 都有 direction；
- 每个角色都有完整人物信息；
- opening 不超过35个汉字；
- JSON 合法且没有任何额外文字。

如果检查不通过，先修改剧本，再输出最终 JSON。
"""


_SOUND_PROMPT = (
    "\n音效与背景音乐（可选，宁缺毋滥，整个短篇通常只给0-1条背景音乐和"
    "少数几个关键音效）：\n"
    "13. 可以在顶层给一个贯穿全剧的背景音乐 background_music，"
    "格式 {\"name\":\"名称\",\"type\":\"music\","
    "\"description\":\"这是什么音乐\",\"prompt\":\"给声音生成模型的描述\"}。\n"
    "14. 可以在某一行（必须是有 text 的旁白或对话行）里给 sound_effects 数组，元素格式 "
    "{\"name\":\"名称\",\"type\":\"effect 或 ambient\","
    "\"description\":\"这是什么声音\",\"prompt\":\"给声音生成模型的描述\","
    "\"anchor\":\"触发该声音的、本行里逐字出现的短语\"}。"
    "effect 是短促音效（如敲门、打雷、肚子叫），ambient 是持续环境声（如树林鸟鸣、集市嘈杂）。"
    "音效就写在触发它的那一（几）行上；严禁创建只有音效、没有 text 的独立行，"
    "line_type 只能是 narration 或 dialogue。\n"
    "15. prompt 只描述声音或音乐本身（乐器、节奏、情绪、环境），"
    "严禁包含任何人声、台词、说话或歌词；要自包含、简短具体。\n"
    "16. 写 prompt 必须让人一听就知道声源：写清「什么东西/谁」+「在做什么动作」+"
    "「声音质感与节奏、响几声」+（需要时）远近/空间，不要用不相干的声音打比方。\n"
    "17. anchor 仅 effect 必填、ambient 不填：必须是本行 text 里**逐字出现**的短句，"
    "正是这个声音发生的地方（如 text 里的“肚子咕咕叫了起来”）。"
    "一行有先后两个音效时，各自锚定对应的短语，不要都写句首。\n"
    "18. **声音必须在剧本里有据可依**：音效只能给本行 text 已经明确写到的"
    "动作、物体或环境声。听众看不到画面，如果一句台词里根本没有提到拔剑，"
    "就不要在这句台词上挂剑声——需要这个声音，就先在旁白里把动作写出来，"
    "再把音效挂到那句旁白上。严禁给台词配画外声音。\n"
    "19. 背景音乐描述整体情绪基调；没有合适的声音就直接省略对应字段，"
    "不要硬加。\n"
    "prompt 正反例：\n"
    "  肚子叫 ✔“人肚子饿时咕咕叫的声音，低沉冒泡，两三声，近景，无人声”；"
    "✘“咕噜咕噜的水声”（错：那是水声不是肚子叫）\n"
    "  脚步 ✔“沉稳的成年男人脚步声，布鞋踩在泥地上，一步一步走近，五六步，无人声”\n"
    "  卷帘门 ✔“金属卷帘门被拉下的哗啦声，持续两三秒后哐当到底，无人声”\n"
    "  水桶入水 ✔“木桶探入溪水再提起的泼溅水声，两三次，无人声”；"
    "✘“水花溅起声”（太笼统）\n"
    "示例片段：\n"
    '  顶层："background_music": {"name":"冒险主题曲","type":"music",'
    '"description":"轻快温馨的管弦乐","prompt":"轻快温暖的管弦乐，'
    '木管与拨弦，适合故事冒险场景，无人声"}\n'
    '  行内："sound_effects": [{"name":"肚子咕噜","type":"effect",'
    '"description":"肚子饿的咕咕声","prompt":"人肚子饿时咕咕叫的声音，'
    '低沉冒泡，两三声，近景，无人声","anchor":"肚子咕咕叫了起来"}]\n'
)


class StoryGenerator:
    """Turns a topic into a Script by prompting an LLM.

    Owns the prompt-building and response-parsing business logic. Knows
    nothing about which LLM provider is used.
    """

    def __init__(self, llm, system_prompt=None, sound_prompt=None):
        self.llm = llm
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.sound_prompt = sound_prompt if sound_prompt is not None else _SOUND_PROMPT

    def generate_script(
        self,
        topic,
        length="medium",
        complexity="simple",
        with_sound=False,
        **kwargs,
    ):
        system_content = self.system_prompt
        if with_sound:
            system_content = system_content + self.sound_prompt
        messages = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": self._build_user_prompt(
                    topic, length, complexity
                ),
            },
        ]
        try:
            response = self.llm.chat(messages, **kwargs)
        except Exception as exc:
            raise LLMError("LLM call failed: {}".format(exc)) from exc
        return self._parse_response(response, topic)

    def generate_script_stream(
        self,
        topic,
        length="medium",
        complexity="simple",
        with_sound=False,
        on_preview=None,
        on_opening_delta: Optional[Callable[[str], None]] = None,
        on_opening_complete: Optional[Callable[[], None]] = None,
        on_characters_ready: Optional[Callable[[dict], None]] = None,
        on_line_text_delta: Optional[Callable[[int, dict, str], None]] = None,
        on_line_complete: Optional[Callable[[int, dict], None]] = None,
        **kwargs,
    ):
        """Generate a script while reporting partial JSON snapshots.

        ``on_preview`` receives speculative dictionaries produced by
        ``partialjson``. They are for display only. The returned ``Script``
        is parsed from the complete response and is the only authoritative
        value for downstream processing.

        ``on_opening_delta`` reports each new suffix of the opening field.
        ``on_opening_complete`` fires once, as soon as a non-opening key
        (``characters``/``lines``) appears in the stream: the opening is
        ordered first in the prompt, so that is when it is known in full and a
        realtime TTS session may stop accepting more text.

        ``on_characters_ready`` fires once when the ordered raw JSON stream
        reaches the top-level ``lines`` key.  With the required
        title/opening/characters/lines order, that is the boundary at which
        the preceding characters array has closed.

        ``on_line_text_delta`` receives each append-only text suffix for a
        partial line. ``on_line_complete`` fires when the following line
        begins, and for the final line after the response ends.
        """
        system_content = self.system_prompt
        if with_sound:
            system_content = system_content + self.sound_prompt
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": self._build_user_prompt(topic, length, complexity)},
        ]
        chunks = []
        last_preview = None
        last_opening_text = ""
        opening_protocol_error = False
        opening_complete_fired = False
        characters_ready_fired = False
        line_texts = {}
        completed_line_count = 0
        try:
            for chunk in self.llm.chat_stream(messages, **kwargs):
                if not chunk:
                    continue
                chunks.append(str(chunk))
                if (
                    on_preview is None
                    and on_opening_delta is None
                    and on_opening_complete is None
                    and on_characters_ready is None
                    and on_line_text_delta is None
                    and on_line_complete is None
                ):
                    continue
                try:
                    preview = JSONParser().parse("".join(chunks))
                except (TypeError, ValueError, SyntaxError):
                    continue
                if isinstance(preview, dict):
                    opening = str(preview.get("opening") or "")
                    if opening and not opening_protocol_error:
                        if opening.startswith(last_opening_text) and len(opening) > len(last_opening_text):
                            if on_opening_delta is not None:
                                on_opening_delta(opening[len(last_opening_text):])
                            last_opening_text = opening
                        elif opening != last_opening_text:
                            logger.warning("opening protocol error: already-sent prefix was rewritten")
                            opening_protocol_error = True
                    if not opening_complete_fired and on_opening_complete is not None:
                        if "characters" in preview or "lines" in preview:
                            on_opening_complete()
                            opening_complete_fired = True
                    if (
                        not characters_ready_fired
                        and on_characters_ready is not None
                        and _top_level_key_started("".join(chunks), "lines")
                    ):
                        on_characters_ready(preview)
                        characters_ready_fired = True
                    raw_lines = preview.get("lines") or []
                    for index, raw_line in enumerate(raw_lines):
                        if not isinstance(raw_line, dict):
                            continue
                        text = str(raw_line.get("text") or "")
                        previous = line_texts.get(index, "")
                        if text.startswith(previous) and len(text) > len(previous):
                            if on_line_text_delta is not None:
                                on_line_text_delta(index, raw_line, text[len(previous):])
                            line_texts[index] = text
                    # A later array entry proves all preceding JSON objects
                    # have closed, so their text streams can be FINISHed.
                    while completed_line_count < len(raw_lines) - 1:
                        raw_line = raw_lines[completed_line_count]
                        if isinstance(raw_line, dict) and on_line_complete is not None:
                            on_line_complete(completed_line_count, raw_line)
                        completed_line_count += 1
                    snapshot = _script_preview_from_json(preview)
                    if on_preview is not None and snapshot != last_preview:
                        on_preview(snapshot)
                        last_preview = snapshot
        except Exception as exc:
            raise LLMError("LLM streaming call failed: {}".format(exc)) from exc
        response = "".join(chunks)
        script = self._parse_response(response, topic)
        if on_line_complete is not None:
            for index, line in enumerate(script.lines):
                if index >= completed_line_count:
                    on_line_complete(index, {
                        "line_id": line.line_id,
                        "line_type": line.line_type,
                        "character_id": line.character_id,
                        "text": line.text,
                    })
        return script

    def refine_script(self, script, feedback, **kwargs):
        """Regenerate a script given feedback (reserved for later)."""
        raise NotImplementedError("refine_script not implemented")

    # ----- internals -----
    def _build_user_prompt(self, topic, length, complexity):
        return (
            "请围绕以下主题创作一个故事剧本：{}\n\n"
            "故事长度：{}\n"
            "剧本复杂度：{}"
        ).format(topic, length, complexity)

    def _parse_response(self, response, topic):
        data = _extract_json(response)
        if data is None:
            raise LLMError(
                "LLM returned unparseable content: {}".format(
                    _truncate(response, 200)
                )
            )
        return _script_from_json(data, topic)


_VALID_SOUND_TYPES = ("effect", "ambient", "music")


def _sound_from_llm(raw, fallback_type):
    """Build a not-yet-synthesized SoundEffect from an LLM sound cue.

    Returns None when there is no usable generation prompt. The cue has no
    local file yet: source_type is "builtin" and source_path stays None
    until the pipeline materializes it through the SoundLibrary.
    """
    if not isinstance(raw, dict):
        return None
    prompt = str(raw.get("prompt") or "").strip()
    if not prompt:
        return None
    sound_type = str(raw.get("type") or fallback_type).strip()
    if sound_type not in _VALID_SOUND_TYPES:
        sound_type = fallback_type
    name = str(raw.get("name") or prompt[:12]).strip()
    description = str(raw.get("description") or "").strip()
    anchor_raw = str(raw.get("anchor") or "").strip()
    anchor = anchor_raw or None
    tags_raw = raw.get("tags") or []
    tags = [str(t).strip() for t in tags_raw if str(t).strip()] if isinstance(tags_raw, list) else []
    return SoundEffect(
        effect_id=generate_id("sfx_"),
        name=name,
        type=sound_type,
        source_path=None,
        source_type="builtin",
        prompt=prompt,
        description=description,
        tags=tags,
        anchor=anchor,
    )


def _extract_json(text):
    """Extract a JSON object from LLM output.

    Handles responses wrapped in markdown code fences (```json ... ```)
    or with surrounding prose.
    """
    if not text:
        return None
    text = text.strip()

    # Try parsing directly first.
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass

    # Strip code fences.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except (ValueError, TypeError):
            pass

    # Find the first {...} block as a last resort.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except (ValueError, TypeError):
            pass

    return None


def _script_preview_from_json(data):
    """Return a UI-safe, best-effort snapshot of a partial script object."""
    characters = []
    for raw in data.get("characters") or []:
        if not isinstance(raw, dict):
            continue
        characters.append({
            "id": str(raw.get("id") or ""),
            "name": str(raw.get("name") or ""),
            "description": str(raw.get("description") or ""),
        })
    lines = []
    for raw in data.get("lines") or []:
        if not isinstance(raw, dict):
            continue
        lines.append({
            "line_id": str(raw.get("line_id") or len(lines) + 1),
            "line_type": str(raw.get("line_type") or "narration"),
            "character_id": raw.get("character_id"),
            "text": str(raw.get("text") or ""),
        })
    return {
        "title": str(data.get("title") or ""),
        "opening": str(data.get("opening") or ""),
        "characters": characters,
        "lines": lines,
    }


def _top_level_key_started(text, key):
    """Return whether an exact key has started on the root JSON object."""
    depth = 0
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            end = index + 1
            escaped_key = False
            while end < len(text):
                if escaped_key:
                    escaped_key = False
                elif text[end] == "\\":
                    escaped_key = True
                elif text[end] == '"':
                    break
                end += 1
            if depth == 1 and end < len(text):
                candidate = text[index + 1:end]
                probe = end + 1
                while probe < len(text) and text[probe].isspace():
                    probe += 1
                if candidate == key and probe < len(text) and text[probe] == ":":
                    return True
            index = end + 1
            continue
        if char in "[{":
            depth += 1
        elif char in "]}":
            depth = max(0, depth - 1)
        index += 1
    return False


def _script_from_json(data, topic):
    characters = []
    char_lookup = {}
    for idx, raw_char in enumerate(data.get("characters") or []):
        char = Character(
            id=str(raw_char.get("id") or "char_{}".format(idx)),
            name=str(raw_char.get("name") or "角色{}".format(idx + 1)),
            description=str(raw_char.get("description") or ""),
            gender=_character_gender(raw_char.get("gender")),
            age=_character_age(raw_char.get("age")),
            voice_preferences=_voice_preferences_from_llm(
                raw_char.get("voice_preferences")
            ),
        )
        characters.append(char)
        char_lookup[char.id] = char

    lines = []
    pending_sounds = []
    for raw_line in data.get("lines") or []:
        raw_type = str(raw_line.get("line_type") or "narration").strip()
        text = str(raw_line.get("text") or "").strip()
        char_id = raw_line.get("character_id")
        own_sounds = [
            s
            for s in (
                _sound_from_llm(raw, "effect")
                for raw in (raw_line.get("sound_effects") or [])
            )
            if s is not None
        ]
        own_bgm = _sound_from_llm(raw_line.get("background_music"), "music")

        # The model sometimes emits a standalone sound-only "line"
        # (line_type "sound_effects", empty text). That is not a spoken
        # line: defer its cues onto the next real line so they are mixed at
        # the right moment without a wasted TTS call on an empty string.
        sound_marker = raw_type.lower() in (
            "sound_effects", "sfx", "sound_effect", "sound",
        )
        if sound_marker or not text:
            pending_sounds.extend(own_sounds)
            if own_bgm is not None:
                pending_sounds.append(own_bgm)
            continue

        metadata = {}
        direction = raw_line.get("direction")
        if direction:
            metadata["direction"] = str(direction).strip()
        line_type = "dialogue" if raw_type == "dialogue" else "narration"
        cues = _cues_for_line(pending_sounds + own_sounds, text)
        pending_sounds = []
        lines.append(
            ScriptLine(
                line_id=str(raw_line.get("line_id") or generate_id("l_")),
                line_type=line_type,
                character_id=str(char_id) if char_id else None,
                text=text,
                sound_effects=cues,
                background_music=own_bgm,
                metadata=metadata,
            )
        )

    # A trailing sound-only marker has no later line to attach to: keep its
    # beds/music on the last line, and drop any effect whose anchor is absent
    # from that line (same evidence rule as above).
    if pending_sounds and lines:
        lines[-1].sound_effects.extend(
            _cues_for_line(pending_sounds, lines[-1].text)
        )

    has_narration = any(line.line_type == "narration" for line in lines)
    if has_narration and not _has_narrator(characters):
        # The LLM often omits a narrator character even though it emits
        # narration lines. Inject one so voice matching assigns a narrator
        # timbre instead of the first dialogue character's voice.
        narrator_id = (
            "narrator" if "narrator" not in char_lookup else generate_id("narrator_")
        )
        narrator = Character(
            id=narrator_id,
            name="旁白",
            description="故事旁白，负责叙述时间地点、场景、动作和说话人",
            gender=None,
            age=None,
            voice_preferences=[
                {"type": "有声阅读", "weight": 0.7},
                {"type": "有声书配音", "weight": 0.2},
                {"type": "深夜电台", "weight": 0.1},
            ],
        )
        characters.insert(0, narrator)
        char_lookup[narrator_id] = narrator

    top_bgm = _sound_from_llm(data.get("background_music"), "music")

    return Script(
        script_id=generate_id("script_"),
        title=str(data.get("title") or "未命名故事"),
        topic=topic,
        characters=characters,
        lines=lines,
        background_music=top_bgm,
        metadata={
            "length": data.get("length"),
            "complexity": data.get("complexity"),
        },
    )


_NARRATOR_KEYWORDS = ("旁白", "narrator", "说书", "叙述")


def _cues_for_line(cues, text):
    """Keep only cues the spoken line actually accounts for.

    A punctual effect without an anchor phrase that occurs verbatim in the
    line text describes a sound the listener gets no narration for — it
    would play out of nowhere — so drop the whole cue. Ambient beds and
    music carry no anchor and always start at the line head.
    """
    kept = []
    for cue in cues:
        if cue.type == "effect" and (not cue.anchor or cue.anchor not in text):
            continue
        kept.append(cue)
    return kept


def _has_narrator(characters):
    for char in characters:
        text = "{} {}".format(char.id, char.name).lower()
        if any(kw in text for kw in _NARRATOR_KEYWORDS):
            return True
    return False


def _voice_preferences_from_llm(raw):
    """Keep a small, normalized preference list from an LLM response."""
    if not isinstance(raw, list):
        return []
    preferences = []
    by_type = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        preference_type = str(item.get("type") or "").strip()
        try:
            weight = float(item.get("weight"))
        except (TypeError, ValueError):
            continue
        if not preference_type or weight <= 0:
            continue
        if preference_type in by_type:
            by_type[preference_type]["weight"] += weight
        elif len(preferences) < 5:
            entry = {"type": preference_type, "weight": weight}
            preferences.append(entry)
            by_type[preference_type] = entry
    total = sum(item["weight"] for item in preferences)
    if not total:
        return []
    for item in preferences:
        item["weight"] = round(item["weight"] / total, 6)
    return preferences


def _character_gender(raw):
    value = str(raw or "").strip()
    return value if value in ("male", "female") else None


def _character_age(raw):
    value = str(raw or "").strip()
    return value if value in (
        "child", "teen", "young_adult", "middle_aged", "senior"
    ) else None


def _truncate(text, limit):
    text = text or ""
    return text[:limit] + ("..." if len(text) > limit else "")
