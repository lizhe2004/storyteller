from __future__ import annotations

import re

from .exceptions import ProviderError
from .models import VoiceConfig

_NARRATOR_KEYWORDS = ("旁白", "narrator", "说书", "叙述")
_NUMERIC_AGE = re.compile(r"(\d{1,2})\s*岁")
# Bare "孩子" is intentionally excluded: an adult described as "哄孩子"
# / "像个孩子" must not be mistaken for a child character.
_CHILD_WORDS = (
    "儿童", "小孩", "小孩子", "小朋友", "孩童",
    "男童", "女童", "小男孩", "小女孩", "婴儿", "宝宝",
    "幼年", "幼儿", "幼童", "幼崽",
)
_TEEN_WORDS = ("少年", "少女")
_SENIOR_WORDS = (
    "婆婆", "奶奶", "爷爷", "外公", "外婆", "老人", "老太太",
    "老爷爷", "老奶奶", "祖父", "祖母", "老翁", "老妇",
    "老年", "年迈", "高龄",
)
_MIDDLE_AGED_WORDS = (
    "妈妈", "爸爸", "阿姨", "叔叔", "姑姑", "婶婶", "舅舅",
    "伯父", "伯母", "大叔", "大婶", "中年",
)
# Kinship titles and pronouns disambiguate gender when the description
# never uses 男/女 (e.g. "企鹅妈妈，温柔耐心").
_FEMALE_WORDS = (
    "女", "妈妈", "妈", "阿姨", "姐姐", "奶奶", "外婆", "婆婆",
    "妹妹", "姑姑", "婶婶", "姑娘", "公主", "女王", "少女", "她",
)
_MALE_WORDS = (
    "男", "爸爸", "爸", "叔叔", "哥哥", "爷爷", "外公", "弟弟",
    "舅舅", "伯父", "先生", "王子", "少年", "他",
)

_AGE_LABELS = {
    "child": "儿童",
    "teen": "少年",
    "young_adult": "青年",
    "middle_aged": "中年",
    "senior": "老年",
}
_GENDER_LABELS = {"male": "男", "female": "女"}
_AGE_RANK = {"child": 0, "teen": 1, "young_adult": 2,
             "middle_aged": 3, "senior": 4}
_GENDER_ORDER = {"female": 0, "male": 1}
NARRATION_CATEGORIES = {"有声阅读"}


def is_narration_voice(voice):
    """True for reading/narration-suited voices (soft signal, not a type)."""
    return voice.category in NARRATION_CATEGORIES


_LLM_SYSTEM_PROMPT = (
    "你是一位经验丰富的广播剧配音导演。请根据每个角色的设定，"
    "从给定的候选音色中挑选最贴切的一个。\n"
    "规则：\n"
    "1. 每个角色必须且只能选择一个候选音色，用候选前面的序号表示。\n"
    "2. 严格遵守性别：女性角色不可选男声，男性角色不可选女声；"
    "标注为旁白的角色无性别限制。\n"
    "3. 旁白角色优先选择「有声阅读」类、语气平稳连贯的音色；"
    "儿童故事也可以根据气质选择温暖的年轻音色或儿童音色。\n"
    "4. 年龄和气质要贴合：例如慈祥的老婆婆要避免年轻御姐音，"
    "优先中年/老年、语气温和缓慢的音色；孩子选儿童年龄段音色。\n"
    "5. 结合音色的名称、分类和描述里的语气、风格来判断，不要只看性别。\n"
    "6. 不同角色尽量选择不同的音色，序号不可重复。\n"
    "7. 只输出 JSON，不要任何额外文字，格式：\n"
    '{"assignments":[{"character_id":"角色id","voice_index":序号}]}'
)

_LLM_CLASSIFY_SYSTEM_PROMPT = (
    "你是配音选角助理。请只根据每个角色的名字和设定描述，判断其"
    "性别和年龄段，用于挑选配音音色。\n"
    "年龄段取值只能是：child(儿童，约0-12岁)、teen(少年，13-17岁)、"
    "young_adult(青年，18-45岁)、middle_aged(中年，46-59岁)、"
    "senior(老年，60岁以上)。\n"
    "注意：儿童故事里写成“男孩/女孩”的角色通常是 child；"
    "出现婆婆/奶奶/爷爷等是 senior；妈妈/爸爸/阿姨/叔叔多为 middle_aged。"
    "gender 只能是 male 或 female。\n"
    "只输出 JSON，不要任何额外文字，格式：\n"
    '{"characters":[{"character_id":"角色id","gender":"male|female",'
    '"age":"child|teen|young_adult|middle_aged|senior"}]}'
)

_AGE_BANDS = ("child", "teen", "young_adult", "middle_aged", "senior")
_GENDERS = ("male", "female")


def _infer_gender(description):
    """Guess male/female from explicit words, kinship titles, pronouns.

    Defaults to male. Childhood no longer collapses gender: a child still
    has its own gender (age is tracked separately).
    """
    desc = description or ""
    if any(word in desc for word in _FEMALE_WORDS):
        return "female"
    if any(word in desc for word in _MALE_WORDS):
        return "male"
    return "male"


def _infer_age(description):
    """Guess an age band from a character description.

    Returns one of child/teen/young_adult/middle_aged/senior. Used as a
    soft hint for semantic matching within a gender-constrained pool.
    """
    desc = description or ""
    match = _NUMERIC_AGE.search(desc)
    if match:
        years = int(match.group(1))
        if years <= 12:
            return "child"
        if years <= 17:
            return "teen"
        if years <= 45:
            return "young_adult"
        if years <= 59:
            return "middle_aged"
        return "senior"
    if any(word in desc for word in _SENIOR_WORDS):
        return "senior"
    if any(word in desc for word in _MIDDLE_AGED_WORDS):
        return "middle_aged"
    if any(word in desc for word in _TEEN_WORDS):
        return "teen"
    if any(word in desc for word in _CHILD_WORDS):
        return "child"
    return "young_adult"


def _is_narrator(character):
    text = "{} {}".format(character.id, character.name).lower()
    return any(kw in text for kw in _NARRATOR_KEYWORDS)


def _age_distance(a, b):
    return abs(_AGE_RANK.get(a, 2) - _AGE_RANK.get(b, 2))


def _gender_pool(voices, gender):
    """Hard gender preference, falling back to neutral then any voice."""
    exact = [v for v in voices if v.gender == gender]
    if exact:
        return exact
    neutral = [v for v in voices if not v.gender]
    if neutral:
        return neutral
    return list(voices)


def _voice_sort_key(voice, age, narrator):
    if narrator:
        # Narration-suited voices first; ties by age then stable id.
        return (
            0 if is_narration_voice(voice) else 1,
            _AGE_RANK.get(voice.age, 9),
            voice.voice_id,
        )
    # Dialogue: reading voices are the last resort; otherwise nearest age.
    return (
        1 if is_narration_voice(voice) else 0,
        _age_distance(voice.age, age),
        _AGE_RANK.get(voice.age, 9),
        voice.voice_id,
    )


class VoiceMatcher:
    """Assigns a VoiceConfig to every character in a script.

    mode="llm" asks the LLM to semantically pick voices using each
    candidate's name/age/category/description, matching by gender/age with
    a soft preference for 有声阅读 (narration-suited) voices on narrator
    characters; any character the LLM cannot validly assign falls back to
    deterministic rule matching. mode="rule" skips the LLM.
    """

    def __init__(self, registry, llm=None, mode="rule"):
        self.registry = registry
        self.llm = llm
        self.mode = mode

    def match_voices(
        self,
        script,
        allowed_providers=None,
        allowed_voice_ids=None,
        default_provider=None,
    ):
        if not script.characters:
            return script

        if allowed_providers is None:
            allowed_providers = self.registry.list_tts_names()

        voices = self.registry.list_tts_voices(
            allowed_providers, allowed_voice_ids=allowed_voice_ids
        )
        if not voices:
            raise ProviderError(
                "No TTS voices available for providers: {}".format(
                    ", ".join(allowed_providers)
                )
            )

        narrators = [c for c in script.characters if _is_narrator(c)]
        others = [c for c in script.characters if not _is_narrator(c)]
        ordered = narrators + others

        # wanted[char_id] = (gender_or_None, age_or_None); narrator is (None, None).
        wanted = {c.id: (None, None) for c in narrators}
        classified = {}
        if self.mode == "llm" and self.llm is not None and others:
            classified = self._classify_characters(others)
        for character in others:
            text = "{} {}".format(character.name, character.description)
            if character.id in classified:
                gender, age = classified[character.id]
            else:
                gender = _infer_gender(text)
                age = _infer_age(text)
            wanted[character.id] = (gender, age)

        used_ids = set()
        llm_picks = {}
        if self.mode == "llm" and self.llm is not None:
            llm_picks = self._safe_llm_assign(ordered, wanted, voices)
            for voice in llm_picks.values():
                used_ids.add(voice.voice_id)

        for character in ordered:
            if character.id in llm_picks:
                character.voice_config = llm_picks[character.id]
                continue
            gender, age = wanted[character.id]
            chosen = self._rule_pick(
                voices, used_ids, default_provider,
                gender=gender, age=age, narrator=gender is None,
            )
            character.voice_config = chosen
            used_ids.add(chosen.voice_id)

        return script

    def _classify_characters(self, characters):
        """LLM call #1: decide gender + age band per character.

        Returns {character_id: (gender, age)}. Only valid entries are
        included; the method never raises (call/parse failures yield {}),
        so unresolved characters fall back to keyword rules.
        """
        char_lines = [
            '- character_id={} 「{}」：{}'.format(
                c.id, c.name, c.description or "-"
            )
            for c in characters
        ]
        user_content = (
            "待判定角色：\n{}\n\n请判断每个角色的性别和年龄段，"
            "按规定只输出 JSON。"
        ).format("\n".join(char_lines))
        messages = [
            {"role": "system", "content": _LLM_CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        try:
            response = self.llm.chat(messages, temperature=0.0)
        except Exception:
            return {}

        from .story_generator import _extract_json

        data = _extract_json(response)
        if not isinstance(data, dict):
            return {}
        items = data.get("characters")
        if not isinstance(items, list):
            return {}

        result = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = item.get("character_id")
            gender = item.get("gender")
            age = item.get("age")
            if cid not in {c.id for c in characters}:
                continue
            if gender not in _GENDERS or age not in _AGE_BANDS:
                continue
            result[str(cid)] = (gender, age)
        return result

    def _safe_llm_assign(self, ordered, wanted, voices):
        """Return {character_id: VoiceConfig} for valid LLM picks.

        Any failure (call error, unparseable JSON, out-of-range index,
        gender mismatch, duplicate) drops the affected character so the
        caller fills it with rule matching; the method never raises.
        """
        try:
            candidates, response = self._request_llm(ordered, wanted, voices)
        except Exception:
            return {}

        from .story_generator import _extract_json

        data = _extract_json(response)
        if not isinstance(data, dict):
            return {}
        items = data.get("assignments")
        if not isinstance(items, list):
            return {}

        picks = {}
        used_index = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            char_id = item.get("character_id")
            index = item.get("voice_index")
            if char_id is None or char_id not in wanted:
                continue
            if isinstance(index, bool) or not isinstance(index, int):
                continue
            if not 1 <= index <= len(candidates):
                continue
            if index in used_index:
                continue
            want_gender = wanted[char_id][0]
            voice = candidates[index - 1]
            # Hard constraint for dialogue only: gender must agree.
            # Narrators (want_gender is None) have no gender restriction.
            if want_gender is not None and voice.gender != want_gender:
                continue
            picks[str(char_id)] = voice
            used_index.add(index)
        return picks

    def _request_llm(self, ordered, wanted, voices):
        candidates = sorted(
            voices,
            key=lambda v: (
                0 if is_narration_voice(v) else 1,
                _GENDER_ORDER.get(v.gender, 9),
                _AGE_RANK.get(v.age, 9),
                v.voice_id,
            ),
        )
        lines = []
        for voice in candidates:
            index = len(lines) + 1
            gender_label = _GENDER_LABELS.get(voice.gender, "中性")
            lines.append(
                "[{}] {} | {} | {} | {} | {}".format(
                    index,
                    voice.name or voice.voice_id,
                    gender_label,
                    _AGE_LABELS.get(voice.age, voice.age or "-"),
                    voice.category or "-",
                    voice.description or "-",
                )
            )

        char_lines = []
        for character in ordered:
            gender, age = wanted[character.id]
            if gender is None:
                need = "旁白（无性别限制，优先有声阅读类）"
            else:
                need = "{}声，年龄={}".format(
                    _GENDER_LABELS.get(gender, gender),
                    _AGE_LABELS.get(age, age or "-"),
                )
            char_lines.append(
                "- character_id={} 「{}」：{} ｜ {}".format(
                    character.id,
                    character.name,
                    character.description or "-",
                    need,
                )
            )

        user_content = (
            "候选音色列表：\n{}\n\n"
            "待分配角色：\n{}\n\n"
            "请为每个角色选择一个候选序号，按规定只输出 JSON。"
        ).format("\n".join(lines), "\n".join(char_lines))
        messages = [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        response = self.llm.chat(messages, temperature=0.0)
        return candidates, response

    def _rule_pick(self, voices, used_ids, default_provider,
                   *, gender, age, narrator):
        """Deterministic selection used at init and as LLM fallback."""
        pool = list(voices) if narrator else _gender_pool(voices, gender)
        ranked = sorted(pool, key=lambda v: _voice_sort_key(v, age, narrator))
        unused = [v for v in ranked if v.voice_id not in used_ids]
        if default_provider:
            on_default = [v for v in unused if v.provider == default_provider]
            if on_default:
                return on_default[0]
        if unused:
            return unused[0]
        # Every pool voice is already used: reuse the highest-ranked one.
        return ranked[0]
