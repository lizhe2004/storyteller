from unittest.mock import Mock

import pytest
import requests

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.providers.bootstrap import register_providers_from_config
from storyteller.providers.registry import ProviderRegistry


def make_config():
    config = Config()
    config.set('sound.providers', ['elevenlabs'])
    config.set('sound.default_provider', 'elevenlabs')
    config.set('sound.provider_config.elevenlabs', {'api_key': 'test-secret'})
    return config


def test_generate_mp3_and_register(tmp_path):
    config = make_config()
    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)
    provider = registry.get_sound('elevenlabs')
    response = Mock(content=b'ID3-audio')
    provider._session.post = Mock(return_value=response)
    result, duration = provider.generate('Rain on a window', tmp_path / 'rain.mp3')
    assert result.read_bytes() == b'ID3-audio'
    assert duration is None
    call = provider._session.post.call_args
    assert call.args[0] == 'https://api.elevenlabs.io/v1/sound-generation'
    assert call.kwargs['headers']['xi-api-key'] == 'test-secret'
    assert call.kwargs['params']['output_format'] == 'mp3_44100_128'
    assert call.kwargs['json'] == {'text': 'Rain on a window', 'model_id': 'eleven_text_to_sound_v2'}


def test_generate_rejects_unsupported_format_and_references(tmp_path):
    config = make_config()
    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)
    provider = registry.get_sound('elevenlabs')
    with pytest.raises(TTSError):
        provider.generate('rain', tmp_path / 'rain.wav', audio_format='wav')
    with pytest.raises(TTSError):
        provider.generate('rain', tmp_path / 'rain.mp3', references=['x'])


def test_http_failure_does_not_leak_api_key(tmp_path):
    config = make_config()
    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)
    provider = registry.get_sound('elevenlabs')
    provider._session.post = Mock(side_effect=requests.RequestException('test-secret'))
    with pytest.raises(TTSError) as exc:
        provider.generate('rain', tmp_path / 'rain.mp3')
    assert 'test-secret' not in str(exc.value)


def test_settings_schema_exposes_elevenlabs():
    from storyteller.web.routes_settings import _resolved_provider_form_type, _PROVIDER_FORM_TYPES
    assert _resolved_provider_form_type('sound', 'elevenlabs', {}) == 'elevenlabs'
    assert _PROVIDER_FORM_TYPES['sound']['elevenlabs']['fields'] == ['api_key', 'model']


def test_elevenlabs_accepts_explicit_duration_without_speaking_directive(tmp_path):
    config = make_config()
    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)
    provider = registry.get_sound('elevenlabs')
    response = Mock(content=b'ID3-sound')
    provider._session.post = Mock(return_value=response)
    provider.generate('太空基地电子警报声，无人声', tmp_path / 'alarm.mp3', duration_seconds=6)
    body = provider._session.post.call_args.kwargs['json']
    assert body['text'] == '太空基地电子警报声，无人声'
    assert body['duration_seconds'] == 6


def test_elevenlabs_duration_is_clamped_to_api_limit(tmp_path):
    registry = ProviderRegistry(make_config())
    register_providers_from_config(registry.config, registry)
    provider = registry.get_sound('elevenlabs')
    provider._session.post = Mock(return_value=Mock(content=b'ID3-sound'))
    provider.generate('space', tmp_path / 'bed.mp3', duration_seconds=105)
    assert provider._session.post.call_args.kwargs['json']['duration_seconds'] == 30


def test_pipeline_uses_structured_duration_for_elevenlabs(tmp_path):
    from storyteller.core.models import SoundEffect
    from storyteller.core.pipeline import Pipeline, build_sound_prompt
    config = make_config()
    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)
    provider = registry.get_sound('elevenlabs')
    provider.generate = Mock(return_value=(tmp_path / 'alarm.mp3', None))
    library = Mock()
    cue = SoundEffect(effect_id='alarm', name='警报', type='effect', prompt='Electronic alarm')
    cache_prompt = build_sound_prompt(cue.prompt, cue.type, 6, 0)
    Pipeline(config)._generate_cue_with_retry(provider, library, cue, tmp_path / 'alarm.mp3', cache_prompt, duration_seconds=6)
    provider.generate.assert_called_once_with('Electronic alarm', tmp_path / 'alarm.mp3', audio_format='mp3', duration_seconds=6)
    assert library.admit.call_args.kwargs['prompt'] == cache_prompt


def test_chinese_sound_prompt_is_translated_before_synthesis(tmp_path):
    from storyteller.core.models import SoundEffect
    from storyteller.core.pipeline import Pipeline
    config = make_config()
    pipeline = Pipeline(config)
    llm = Mock()
    llm.chat.return_value = 'Electronic alarm beeps inside a space station.'
    pipeline._get_default_llm = Mock(return_value=llm)
    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)
    provider = registry.get_sound('elevenlabs')
    provider.generate = Mock(return_value=(tmp_path / 'alarm.mp3', None))
    cue = SoundEffect(effect_id='e', name='警报', type='effect', prompt='太空基地的电子警报')
    pipeline._generate_cue_with_retry(provider, Mock(), cue, tmp_path / 'alarm.mp3', 'cache', duration_seconds=3)
    provider.generate.assert_called_once_with('Electronic alarm beeps inside a space station.', tmp_path / 'alarm.mp3', audio_format='mp3', duration_seconds=3)
    assert llm.chat.call_count == 1


def test_translation_failure_never_sends_chinese_to_elevenlabs(tmp_path):
    from storyteller.core.models import SoundEffect
    from storyteller.core.pipeline import Pipeline
    config = make_config()
    pipeline = Pipeline(config)
    llm = Mock()
    llm.chat.return_value = '电子警报声'
    pipeline._get_default_llm = Mock(return_value=llm)
    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)
    provider = registry.get_sound('elevenlabs')
    provider.generate = Mock()
    cue = SoundEffect(effect_id='e', name='警报', type='effect', prompt='电子警报声')
    with pytest.raises(TTSError):
        pipeline._generate_cue_with_retry(provider, Mock(), cue, tmp_path / 'x.mp3', 'cache', duration_seconds=3)
    provider.generate.assert_not_called()


def test_sound_prompt_policy_depends_on_selected_provider():
    from storyteller.core.pipeline import Pipeline
    config = make_config()
    assert '英文' in Pipeline(config)._sound_prompt_instruction()
    config.set('sound.providers', ['volcengine'])
    config.set('sound.default_provider', 'volcengine')
    assert Pipeline(config)._sound_prompt_instruction() == ''


def test_english_prompt_skips_llm_translation(tmp_path):
    from storyteller.core.models import SoundEffect
    from storyteller.core.pipeline import Pipeline
    config = make_config()
    pipeline = Pipeline(config)
    pipeline._get_default_llm = Mock(side_effect=AssertionError('should not call LLM'))
    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)
    provider = registry.get_sound('elevenlabs')
    provider.generate = Mock(return_value=(tmp_path / 'alarm.mp3', None))
    cue = SoundEffect(effect_id='e', name='alarm', type='effect', prompt='A clear electronic alarm')
    pipeline._generate_cue_with_retry(provider, Mock(), cue, tmp_path / 'alarm.mp3', 'cache', duration_seconds=3)
    pipeline._get_default_llm.assert_not_called()
    assert provider.generate.call_args.args[0] == 'A clear electronic alarm'


def test_other_sound_providers_keep_chinese_prompt_without_translation():
    from storyteller.core.sound_prompt import prepare_sound_prompt
    provider = Mock(spec=[])
    llm_factory = Mock(side_effect=AssertionError('must not translate'))
    assert prepare_sound_prompt(provider, '微风吹过树林', llm_factory) == '微风吹过树林'
    llm_factory.assert_not_called()
