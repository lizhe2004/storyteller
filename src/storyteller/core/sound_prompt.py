"""Adapt sound descriptions to a provider's prompt language."""

from .exceptions import TTSError


def _is_english_prompt(text):
    return bool(text and any('a' <= c.lower() <= 'z' for c in text)) and not any(
        c.isalpha() and not c.isascii() for c in text
    )


def prepare_sound_prompt(provider, prompt, llm_factory):
    """Translate when needed; never submit a non-English prompt to English-only providers."""
    if getattr(provider, 'prompt_language', None) != 'en':
        return prompt
    if _is_english_prompt(prompt):
        return prompt
    try:
        translated = llm_factory().chat([
            {'role': 'system', 'content': 'Translate the sound effect description into concise English for an audio generation model. Preserve the sound source, action, and atmosphere. Return only the English description, without quotes or commentary.'},
            {'role': 'user', 'content': prompt},
        ], temperature=0)
    except Exception as exc:
        raise TTSError('无法将音效提示词转换为英文，请检查故事模型配置') from exc
    translated = str(translated or '').strip().strip('"“”')
    if not _is_english_prompt(translated):
        raise TTSError('音效提示词英文转换失败，请重试')
    return translated
