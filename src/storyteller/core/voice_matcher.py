from __future__ import annotations

from .exceptions import ProviderError
from .models import VoiceConfig

_NARRATOR_KEYWORDS = ("旁白", "narrator", "说书", "叙述")
_CHILD_WORDS = (
    "儿童", "小孩", "孩子", "小朋友", "孩童",
    "男童", "女童", "少年", "少女", "小男孩", "小女孩",
)


def _infer_voice_type(description):
    """Guess a voice_type from a character description.

    voice_type is one of: narrator, child, male, female. Child only when
    explicit child words appear; otherwise adult gender is used, defaulting
    to male.
    """
    desc = (description or "").lower()
    if any(word in desc for word in _CHILD_WORDS):
        return "child"
    if "男" in desc:
        return "male"
    if "女" in desc:
        return "female"
    return "male"


def _is_narrator(character):
    text = "{} {}".format(character.id, character.name).lower()
    return any(kw in text for kw in _NARRATOR_KEYWORDS)


class VoiceMatcher:
    """Assigns a VoiceConfig to every character in a script.

    Uses the ProviderRegistry to aggregate available voices, optionally
    restricted to a subset of providers and voice_ids.
    """

    def __init__(self, registry):
        self.registry = registry

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

        # Voices grouped by type, plus a flat pool for fallback.
        by_type = {}
        for voice in voices:
            by_type.setdefault(voice.voice_type, []).append(voice)

        used_ids = set()

        # Narrator characters first, so they always get a narrator voice.
        narrators = [c for c in script.characters if _is_narrator(c)]
        others = [c for c in script.characters if not _is_narrator(c)]
        ordered = narrators + others

        for character in ordered:
            if _is_narrator(character):
                wanted_type = "narrator"
            else:
                wanted_type = _infer_voice_type(character.description)

            chosen = self._pick_voice(
                by_type, wanted_type, used_ids, default_provider
            )
            character.voice_config = chosen
            used_ids.add(chosen.voice_id)

        return script

    def _pick_voice(self, by_type, wanted_type, used_ids, default_provider):
        # Prefer the wanted voice type, then any unused voice, then reuse.
        candidates = (
            list(by_type.get(wanted_type, []))
            + [v for v in _flatten(by_type) if v.voice_type != wanted_type]
        )

        for voice in candidates:
            if voice.voice_id in used_ids:
                continue
            if (
                default_provider
                and voice.provider != default_provider
                and _any_available(by_type, used_ids, default_provider)
            ):
                continue
            return voice

        # Nothing unused: reuse the first candidate.
        return candidates[0] if candidates else _flatten(by_type)[0]


def _flatten(by_type):
    result = []
    for voices in by_type.values():
        result.extend(voices)
    return result


def _any_available(by_type, used_ids, provider):
    return any(
        v.provider == provider and v.voice_id not in used_ids
        for v in _flatten(by_type)
    )
