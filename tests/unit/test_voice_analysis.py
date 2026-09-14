import json

from storyteller.web.voice_analysis import (
    VoiceAnalysisManager,
    build_sample_inventory,
    _summary_suggestions,
)


def _write_story(root, name, voice_id="voice_a", lines=3):
    story = root / name
    (story / "audio").mkdir(parents=True)
    characters = [{"id": "narrator", "name": "旁白", "description": "旁白",
                   "voice_config": {"provider": "mock", "voice_id": "narrator"}},
                  {"id": "hero", "name": "小明", "description": "8岁男孩",
                   "voice_config": {"provider": "mock", "voice_id": voice_id}}]
    payload = {"project_id": name, "title": name, "characters": characters,
               "lines": [{"line_id": str(i), "line_type": "dialogue",
                          "character_id": "hero", "text": "台词{}".format(i)}
                         for i in range(1, lines + 1)]}
    (story / "story.script.json").write_text(json.dumps(payload), encoding="utf-8")
    for i in range(1, lines + 1):
        (story / "audio" / (str(i) + ".mp3")).write_bytes(b"audio" + bytes([i]))


def test_build_sample_inventory_associates_audio_role_line_and_catalog(tmp_path):
    _write_story(tmp_path, "story-a")
    samples = build_sample_inventory(
        tmp_path,
        {"mock:voice_a": {"gender": "male", "age": "child", "name": "小男孩"}},
        limit=2,
    )

    assert len(samples) == 2
    assert {sample["voice_id"] for sample in samples} == {"voice_a"}
    assert samples[0]["character_id"] == "hero"
    assert samples[0]["text"] == "台词1"
    assert samples[0]["catalog_snapshot"]["age"] == "child"
    assert samples[0]["audio_path"].endswith("audio/1.mp3")


def test_inventory_sampling_covers_multiple_stories_deterministically(tmp_path):
    _write_story(tmp_path, "story-a", lines=4)
    _write_story(tmp_path, "story-b", lines=4)
    first = build_sample_inventory(tmp_path, {}, limit=3)
    second = build_sample_inventory(tmp_path, {}, limit=3)

    assert len(first) == 3
    assert [s["sample_id"] for s in first] == [s["sample_id"] for s in second]
    assert {s["story_id"] for s in first} == {"story-a", "story-b"}


def test_inventory_can_randomly_select_a_persisted_sample_set(tmp_path):
    _write_story(tmp_path, "story-a", lines=6)
    first = build_sample_inventory(tmp_path, {}, limit=3, randomize=True, seed=1)
    second = build_sample_inventory(tmp_path, {}, limit=3, randomize=True, seed=1)

    assert [s["sample_id"] for s in first] == [s["sample_id"] for s in second]
    assert len(first) == 3


def test_manager_persists_manifest_and_lists_summary(tmp_path):
    manager = VoiceAnalysisManager(tmp_path)
    job = manager.create_job({"sample_limit": 10, "model_sample": "gemini-2.5-flash-lite"})

    assert (tmp_path / job.job_id / "manifest.json").exists()
    loaded = manager.get_job(job.job_id)
    assert loaded.snapshot()["status"] == "pending"
    assert loaded.snapshot()["model_sample"] == "gemini-2.5-flash-lite"
    assert manager.list_jobs()[0]["job_id"] == job.job_id


def test_new_jobs_use_lite_for_sample_and_summary(tmp_path):
    job = VoiceAnalysisManager(tmp_path).create_job()

    assert job.manifest["model_sample"] == "gemini-3.5-flash-lite"
    assert job.manifest["model_summary"] == "gemini-3.5-flash-lite"
    assert job.manifest["sampling_strategy"] == "random"


def test_manager_refreshes_manifest_written_by_another_process(tmp_path):
    manager = VoiceAnalysisManager(tmp_path)
    job = manager.create_job()
    manifest_path = job.directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({"status": "completed", "phase": "completed", "updated_at": "2099-01-01T00:00:00+00:00"})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert manager.get_job(job.job_id).snapshot()["status"] == "completed"
    assert manager.list_jobs()[0]["phase"] == "completed"


def test_summary_suggestions_include_catalog_enrichment():
    values = _summary_suggestions({"normalized_result": {
        "suggestions": ["保持当前表现"],
        "catalog_enrichment": {
            "recommended_tags": ["安抚感", "高频明亮"],
            "recommended_description": "具有明显安抚感。",
        },
    }})

    assert values == ["保持当前表现", "建议音色库描述：具有明显安抚感。", "建议新增标签：安抚感、高频明亮"]


def test_job_detail_includes_samples_and_analysis_results(tmp_path):
    manager = VoiceAnalysisManager(tmp_path)
    job = manager.create_job()
    sample = {"sample_id": "sample_1", "voice_id": "voice_a", "text": "你好", "audio_path": "/tmp/a.mp3"}
    _write = job.directory / "samples.json"
    _write.write_text(json.dumps([sample]), encoding="utf-8")
    (job.directory / "sample-results" / "sample_1.json").write_text(
        json.dumps({"sample_id": "sample_1", "status": "completed", "normalized_result": {"observed_age": "child"}}),
        encoding="utf-8",
    )

    detail = manager.get_job(job.job_id).detail()
    assert detail["samples"][0]["sample_id"] == "sample_1"
    assert detail["samples"][0]["result"]["normalized_result"]["observed_age"] == "child"


def test_job_detail_includes_voice_summaries_and_suggestions(tmp_path):
    manager = VoiceAnalysisManager(tmp_path)
    job = manager.create_job()
    (job.directory / "voice-summaries" / "mock_voice.json").write_text(
        json.dumps({"voice_key": "mock:voice_a", "normalized_result": {
            "catalog_match": {"overall": 0.8}, "role_match": {"overall": 0.7},
        }}), encoding="utf-8")
    (job.directory / "suggestions.json").write_text(
        json.dumps([{"suggestion_id": "s1", "status": "pending", "text": "增加温柔标签"}]),
        encoding="utf-8")

    detail = job.detail()
    assert detail["voice_summaries"][0]["normalized_result"]["catalog_match"]["overall"] == 0.8
    assert detail["suggestions"][0]["suggestion_id"] == "s1"


def test_manager_can_review_suggestion_without_touching_catalog(tmp_path):
    manager = VoiceAnalysisManager(tmp_path)
    job = manager.create_job()
    (job.directory / "suggestions.json").write_text(
        json.dumps([{"suggestion_id": "s1", "status": "pending", "text": "增加温柔标签"}]),
        encoding="utf-8",
    )

    suggestion = manager.update_suggestion(job.job_id, "s1", "approved")

    assert suggestion["status"] == "approved"
    assert manager.get_job(job.job_id).detail()["suggestions"][0]["status"] == "approved"
