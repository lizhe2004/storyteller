import json

import pytest

from pathlib import Path

from storyteller.core.project import ProjectManager
from storyteller.core.models import Character, Script, VoiceConfig
from storyteller.core.exceptions import ProjectError


def test_create_project(temp_dir):
    manager = ProjectManager(temp_dir)
    state = manager.create_project(topic="测试故事")
    assert state.project_id
    assert state.state == "topic_collected"
    assert state.config["topic"] == "测试故事"


def test_project_dir_created(temp_dir):
    manager = ProjectManager(temp_dir)
    state = manager.create_project(topic="测试故事")
    project_dir = manager.get_project_dir(state.project_id)
    assert project_dir.exists()


def test_save_and_load_project(temp_dir):
    manager = ProjectManager(temp_dir)
    state = manager.create_project(topic="测试故事")
    state.state = "script_generated"
    script = Script(script_id="s1", title="测试", topic="测试故事")
    state.script = script
    manager.save_project(state)

    loaded = manager.load_project(state.project_id)
    assert loaded.state == "script_generated"
    assert loaded.script.title == "测试"


def test_load_nonexistent_project_raises(temp_dir):
    manager = ProjectManager(temp_dir)
    with pytest.raises(ProjectError):
        manager.load_project("does-not-exist")


def test_update_state(temp_dir):
    manager = ProjectManager(temp_dir)
    state = manager.create_project(topic="测试故事")
    manager.update_state(state.project_id, "script_generating")
    loaded = manager.load_project(state.project_id)
    assert loaded.state == "script_generating"


def test_list_projects(temp_dir):
    manager = ProjectManager(temp_dir)
    manager.create_project(topic="故事A")
    manager.create_project(topic="故事B")
    projects = manager.list_projects()
    assert len(projects) == 2


def test_serialization_roundtrip_script(temp_dir):
    manager = ProjectManager(temp_dir)
    state = manager.create_project(topic="测试")
    script = Script(
        script_id="s1",
        title="小猫",
        topic="测试",
        metadata={"length": "medium"},
    )
    state.script = script
    manager.save_project(state)
    loaded = manager.load_project(state.project_id)
    assert loaded.script.metadata == {"length": "medium"}


def test_serialization_roundtrip_character_voice_preferences(temp_dir):
    manager = ProjectManager(temp_dir)
    state = manager.create_project(topic="测试")
    state.script = Script(
        script_id="s1",
        title="小猫",
        topic="测试",
        characters=[Character(
            id="cat",
            name="小猫",
            description="活泼的女孩",
            gender="female",
            age="child",
            voice_preferences=[
                {"type": "儿童陪伴", "weight": 0.8},
                {"type": "动漫配音", "weight": 0.2},
            ],
        )],
    )
    manager.save_project(state)
    loaded = manager.load_project(state.project_id)
    assert loaded.script.characters[0].voice_preferences == [
        {"type": "儿童陪伴", "weight": 0.8},
        {"type": "动漫配音", "weight": 0.2},
    ]
    assert loaded.script.characters[0].gender == "female"
    assert loaded.script.characters[0].age == "child"


def test_voice_age_serialization_roundtrip_writes_array(temp_dir):
    manager = ProjectManager(temp_dir)
    state = manager.create_project(topic="测试")
    state.script = Script(
        script_id="s1",
        title="小猫",
        topic="测试",
        characters=[Character(
            id="cat",
            name="小猫",
            description="活泼的女孩",
            voice_config=VoiceConfig(
                provider="p", voice_id="child", age=["child", "teen"]
            ),
        )],
    )
    manager.save_project(state)

    payload = json.loads(
        (manager.get_project_dir(state.project_id) / "project.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["script"]["characters"][0]["voice_config"]["age"] == [
        "child",
        "teen",
    ]
    loaded = manager.load_project(state.project_id)
    assert loaded.script.characters[0].voice_config.age == ["child", "teen"]


def test_voice_age_serialization_loads_legacy_scalar(temp_dir):
    manager = ProjectManager(temp_dir)
    state = manager.create_project(topic="测试")
    state.script = Script(
        script_id="s1",
        title="小猫",
        topic="测试",
        characters=[Character(
            id="cat",
            name="小猫",
            description="活泼的女孩",
            voice_config=VoiceConfig(provider="p", voice_id="child"),
        )],
    )
    manager.save_project(state)

    project_file = manager.get_project_dir(state.project_id) / "project.json"
    payload = json.loads(project_file.read_text(encoding="utf-8"))
    payload["script"]["characters"][0]["voice_config"]["age"] = "child"
    project_file.write_text(json.dumps(payload), encoding="utf-8")

    loaded = manager.load_project(state.project_id)
    assert loaded.script.characters[0].voice_config.age == ["child"]


# ---------- human-readable date-title directories ----------

def _project_with_script(manager, title, created_at=None):
    from datetime import datetime

    state = manager.create_project(topic="测试")
    state.script = Script(script_id="s1", title=title, topic="测试")
    if created_at is not None:
        state.created_at = created_at
    manager.save_project(state)
    return state


def test_rename_for_title_moves_dir_to_date_title(temp_dir):
    from datetime import datetime

    manager = ProjectManager(temp_dir)
    state = _project_with_script(
        manager, "客栈夜铃", datetime(2026, 9, 12, 11, 41, 51)
    )

    new_dir = manager.rename_for_title(state, "客栈夜铃")

    assert new_dir == Path(temp_dir) / "2026-09-12-客栈夜铃"
    assert new_dir.exists()
    assert not (Path(temp_dir) / state.project_id).exists()
    # The stable project_id is untouched; resolution follows the new dir.
    assert manager.resolve_project_dir(state.project_id) == new_dir
    assert manager.load_project(state.project_id).script.title == "客栈夜铃"


def test_rename_for_title_sanitizes_unsafe_characters(temp_dir):
    manager = ProjectManager(temp_dir)
    state = _project_with_script(manager, "a/b: c?d*")

    new_dir = manager.rename_for_title(state, "a/b: c?d*")

    assert new_dir.name == "{}-a-b- c-d".format(
        state.created_at.strftime("%Y-%m-%d")
    )
    assert "/" not in new_dir.name


def test_rename_for_title_collision_gets_suffix(temp_dir):
    manager = ProjectManager(temp_dir)
    first = _project_with_script(manager, "同名故事")
    manager.rename_for_title(first, "同名故事")

    second = _project_with_script(manager, "同名故事")
    new_dir = manager.rename_for_title(second, "同名故事")

    assert new_dir.name.endswith("-同名故事-2")
    assert manager.load_project(first.project_id) is not None
    assert manager.load_project(second.project_id) is not None


def test_rename_for_title_truncates_long_title(temp_dir):
    manager = ProjectManager(temp_dir)
    state = _project_with_script(manager, "长" * 100)

    new_dir = manager.rename_for_title(state, "长" * 100)

    # date prefix (11 chars) + at most 60 title chars
    assert len(new_dir.name) == 11 + 60


def test_resolve_accepts_id_dir_name_and_prefix(temp_dir):
    from datetime import datetime

    manager = ProjectManager(temp_dir)
    state = _project_with_script(
        manager, "客栈夜铃", datetime(2026, 9, 12, 11, 41, 51)
    )
    manager.rename_for_title(state, "客栈夜铃")

    assert manager.resolve_project_dir(state.project_id).name == (
        "2026-09-12-客栈夜铃"
    )
    assert manager.resolve_project_dir("2026-09-12-客栈夜铃").name == (
        "2026-09-12-客栈夜铃"
    )
    assert manager.resolve_project_dir("2026-09-12-客栈").name == (
        "2026-09-12-客栈夜铃"
    )


def test_resolve_prefix_ambiguous_raises(temp_dir):
    manager = ProjectManager(temp_dir)
    first = _project_with_script(manager, "客栈夜铃")
    manager.rename_for_title(first, "客栈夜铃")
    second = _project_with_script(manager, "客栈清晨")
    manager.rename_for_title(second, "客栈清晨")

    with pytest.raises(ProjectError):
        manager.resolve_project_dir("客栈")


def test_legacy_proj_id_directory_still_loads(temp_dir):
    manager = ProjectManager(temp_dir)
    state = manager.create_project(topic="旧项目")
    # No rename: legacy proj_xxx directory stays as-is.
    assert manager.resolve_project_dir(state.project_id) == (
        Path(temp_dir) / state.project_id
    )
    assert manager.load_project(state.project_id).project_id == state.project_id


def test_resolve_empty_ref_raises(temp_dir):
    manager = ProjectManager(temp_dir)
    _project_with_script(manager, "故事")
    with pytest.raises(ProjectError):
        manager.resolve_project_dir("")
    with pytest.raises(ProjectError):
        manager.resolve_project_dir("   ")


def test_resolve_id_prefix_matches_renamed_project(temp_dir):
    from datetime import datetime

    manager = ProjectManager(temp_dir)
    state = _project_with_script(
        manager, "客栈夜铃", datetime(2026, 9, 12, 11, 41, 51)
    )
    manager.rename_for_title(state, "客栈夜铃")
    # A short prefix of the stable id still resolves after the rename.
    assert manager.resolve_project_dir(
        state.project_id[:10]
    ).name == "2026-09-12-客栈夜铃"


def test_save_with_duplicated_id_raises_instead_of_forking(temp_dir):
    import shutil

    manager = ProjectManager(temp_dir)
    state = _project_with_script(manager, "故事")
    renamed = manager.rename_for_title(state, "故事")
    # User duplicates the renamed directory as a backup: same project_id
    # now lives in two directories.
    shutil.copytree(renamed, Path(temp_dir) / "backup-故事")

    state.state = "generating_audio"
    with pytest.raises(ProjectError):
        manager.save_project(state)
    # No third, id-named directory was silently created.
    assert not (Path(temp_dir) / state.project_id).exists()


def test_list_project_entries_includes_dir_names(temp_dir):
    manager = ProjectManager(temp_dir)
    a = _project_with_script(manager, "甲")
    manager.rename_for_title(a, "甲")
    b = manager.create_project(topic="无剧本")

    entries = manager.list_project_entries()
    names = {name for name, _ in entries}
    assert a.project_id not in names  # renamed: date-title dir, not id dir
    assert b.project_id in names
    assert any(name.endswith("-甲") for name in names)
