import pytest

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
