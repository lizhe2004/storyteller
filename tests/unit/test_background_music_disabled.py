from types import SimpleNamespace
from unittest.mock import Mock

from storyteller.core.config import Config
from storyteller.core.models import Script, ScriptLine, SoundEffect
from storyteller.core.pipeline import Pipeline


def music(name):
    return SoundEffect(effect_id=name, name=name, type='music', prompt='music prompt')


def test_background_music_does_not_trigger_generation_in_streaming_or_finalization(tmp_path):
    provider = Mock()
    library = Mock()
    pipeline = Pipeline(Config(), sound_provider=provider, sound_library=library)
    line = ScriptLine(line_id='1', line_type='narration', text='你好', background_music=music('line'))
    script = Script(script_id='s', title='test', topic='test', lines=[line], background_music=music('global'))
    state = SimpleNamespace(script=script, project_id='test')
    assert pipeline.materialize_line_cues(state, line, 3, provider, library, set()) == []
    pipeline._apply_soundtrack(state, tmp_path / 'story.mp3')
    provider.generate.assert_not_called()
    library.find.assert_not_called()
    assert line.background_music.source_path is None
    assert script.background_music.source_path is None


def test_existing_music_and_music_effects_do_not_trigger_mixing(tmp_path):
    provider = Mock()
    library = Mock()
    pipeline = Pipeline(Config(), sound_provider=provider, sound_library=library)
    existing = tmp_path / 'existing.mp3'
    existing.write_bytes(b'existing music')
    global_music = music('global')
    global_music.source_path = str(existing)
    line_music = music('line')
    line_music.source_path = str(existing)
    line = ScriptLine(line_id='1', line_type='narration', text='你好',
                      sound_effects=[line_music])
    script = Script(script_id='s', title='test', topic='test', lines=[line],
                    sound_effects=[global_music])
    state = SimpleNamespace(script=script, project_id='test')

    assert pipeline.materialize_line_cues(state, line, 3, provider, library, set()) == []
    pipeline._apply_soundtrack(state, tmp_path / 'story.mp3')

    provider.generate.assert_not_called()
    library.find.assert_not_called()
    assert existing.read_bytes() == b'existing music'
