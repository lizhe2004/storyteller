import threading

from storyteller.core.config import Config
from storyteller.core.runtime_settings import RuntimeSettingsStore
from storyteller.web.jobs import JobManager, JobParams
from storyteller.web.streaming import StreamOrchestrator


def test_jobs_execute_with_the_snapshot_bound_at_submission(tmp_path):
    config = Config()
    config.set("web.host", "old.example.test")
    store = RuntimeSettingsStore(tmp_path, config)
    manager = JobManager(concurrency=2)
    release = threading.Event()
    completed = threading.Event()
    observed = {}

    def record_config(job):
        release.wait(timeout=2)
        observed[job.params.topic] = (
            job.config_snapshot.to_config().get("web.host")
        )
        if len(observed) == 2:
            completed.set()

    job_a = manager.create(JobParams(topic="A"))
    manager.submit(job_a, record_config, store.snapshot())
    store.update({"web": {"host": "new.example.test"}})
    job_b = manager.create(JobParams(topic="B"))
    manager.submit(job_b, record_config, store.snapshot())
    release.set()

    assert completed.wait(timeout=2)
    assert observed == {
        "A": "old.example.test",
        "B": "new.example.test",
    }


def test_submit_without_snapshot_keeps_existing_target_contract():
    manager = JobManager(concurrency=1)
    completed = threading.Event()
    observed = []
    job = manager.create(JobParams(topic="compatible"))

    def record_job(received_job):
        observed.append(received_job)
        completed.set()

    manager.submit(job, record_job)

    assert completed.wait(timeout=2)
    assert observed == [job]
    assert job.config_snapshot is None


def test_streaming_worker_builds_task_config_from_job_snapshot(
    tmp_path, monkeypatch
):
    global_config = Config()
    global_config.set("data_dir", str(tmp_path))
    global_config.set("web.host", "global.example.test")
    store = RuntimeSettingsStore(tmp_path, global_config)
    snapshot = store.update(
        {"web": {"host": "snapshot.example.test"}}
    )
    job = JobManager().create(JobParams(topic="snapshot"))
    job.config_snapshot = snapshot
    observed = []

    monkeypatch.setattr(
        StreamOrchestrator,
        "_run",
        lambda self, received_job: observed.append(
            (received_job, self.config.get("web.host"))
        ),
    )

    StreamOrchestrator(global_config, registry=object()).run(job)

    assert observed == [(job, "snapshot.example.test")]
