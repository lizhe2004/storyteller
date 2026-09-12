import pytest

from pathlib import Path

from storyteller.core.project import ProjectManager
from storyteller.core.models import Script
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

