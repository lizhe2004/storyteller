import base64
import json
from unittest.mock import Mock

import pytest

from storyteller.core.config import Config
from storyteller.core.exceptions import TTSError
from storyteller.core.models import VoiceConfig
from storyteller.core.tts import CHUNK_AUDIO, StreamChunk
from storyteller.providers.bootstrap import register_providers_from_config
from storyteller.providers.registry import ProviderRegistry


def provider():
    config = Config()
    config.set('tts.providers', ['mimo'])
    config.set('tts.provider_config.mimo', {'api_key': 'secret'})
    registry = ProviderRegistry(config)
    register_providers_from_config(config, registry)
    return registry.get_tts('mimo')


def test_mimo_file_request_and_catalog(tmp_path):
    tts = provider()
    assert tts.name == 'mimo'
    assert '冰糖' in [v.voice_id for v in tts.list_voices()]
    response = Mock()
    response.json.return_value = {'choices': [{'message': {'audio': {'data': base64.b64encode(b'audio').decode()}}}]}
    tts._session.post = Mock(return_value=response)
    out = tts.synthesize('你好', VoiceConfig('mimo', '冰糖'), tmp_path / 'a.wav', directives=['#温柔'])
    assert out.read_bytes() == b'audio'
    call = tts._session.post.call_args
    assert call.kwargs['headers']['api-key'] == 'secret'
    assert call.kwargs['json']['messages'] == [{'role': 'user', 'content': '温柔'}, {'role': 'assistant', 'content': '你好'}]
    assert call.kwargs['json']['audio'] == {'format': 'wav', 'voice': '冰糖'}


def test_mimo_stream_and_invalid_response():
    tts = provider()
    response = Mock()
    response.iter_lines.return_value = [b'data: ' + json.dumps({'choices': [{'delta': {'audio': {'data': base64.b64encode(b'pcm').decode()}}}]}).encode(), b'data: [DONE]']
    tts._session.post = Mock(return_value=response)
    chunks = list(tts.stream_synthesize('hi', VoiceConfig('mimo', 'Mia')))
    assert [chunk.data for chunk in chunks] == [b'pcm']
    assert tts._session.post.call_args.kwargs['json']['audio']['format'] == 'pcm16'
    response.close.assert_called_once()
    response.json.return_value = {'choices': []}
    with pytest.raises(TTSError):
        tts.synthesize('hi', VoiceConfig('mimo', 'Mia'), '/tmp/mimo-test.wav')


def test_buffered_session_waits_for_complete_text_and_streams_before_finish_returns():
    import threading
    tts = provider()
    called = threading.Event()
    release = threading.Event()
    received = threading.Event()
    texts = []

    def stream(text, voice, **kwargs):
        texts.append(text)
        called.set()
        yield StreamChunk(CHUNK_AUDIO, b'12')
        release.wait(2)
        yield StreamChunk(CHUNK_AUDIO, b'34')

    tts.stream_synthesize = stream
    session = tts.open_stream(VoiceConfig('mimo', '冰糖'))
    chunks = []
    def consume():
        for chunk in session.iter_audio():
            chunks.append(chunk.data)
            received.set()
    reader = threading.Thread(target=consume)
    reader.start()
    session.send_text('你好')
    session.send_text('世界')
    assert not called.wait(0.05)
    finisher = threading.Thread(target=session.finish)
    finisher.start()
    assert received.wait(1)
    assert texts == ['你好世界']
    assert chunks == [b'12']
    assert finisher.is_alive()
    release.set()
    finisher.join(2)
    reader.join(2)
    assert chunks == [b'12', b'34']
    assert not finisher.is_alive()


def test_buffered_session_cancel_before_finish_does_not_call_api():
    import threading
    tts = provider()
    tts.stream_synthesize = Mock()
    session = tts.open_stream(VoiceConfig('mimo', '冰糖'))
    reader = threading.Thread(target=lambda: list(session.iter_audio()))
    reader.start()
    session.send_text('未完成')
    session.cancel()
    reader.join(1)
    assert not reader.is_alive()
    tts.stream_synthesize.assert_not_called()
