from __future__ import annotations

import queue
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional

from ..core.observability import server_time
from ..core.runtime_settings import RuntimeSettingsSnapshot

PHASE_QUEUED = "queued"
PHASE_SCRIPT = "script"
PHASE_VOICES = "voices"
PHASE_LINE = "line"
PHASE_FINALIZING = "finalizing"
PHASE_COMPLETED = "completed"
PHASE_FAILED = "failed"
PHASE_CANCELED = "canceled"


@dataclass
class JobParams:
    topic: str
    length: str = "medium"
    complexity: str = "simple"
    with_sound: bool = False
    tts_providers: object = None
    audio_mode: str = "webaudio"


class Job:
    def __init__(
        self,
        params,
        config_snapshot: Optional[RuntimeSettingsSnapshot] = None,
    ):
        self.id = "job_" + uuid.uuid4().hex
        self.params = params
        self.config_snapshot: Optional[
            RuntimeSettingsSnapshot
        ] = config_snapshot
        self.phase = PHASE_QUEUED
        self.project_id = None
        self.script_ready = None
        self.script_preview = None
        self.line_index = 0
        self.total = 0
        self.cancel_event = threading.Event()
        self.queue = queue.Queue()
        # Native media playback consumes a separate copy of PCM so WebSocket
        # control events and the existing Web Audio path remain independent.
        self.audio_queue = queue.Queue(maxsize=256)
        self.audio_stream_closed = False

    def emit(self, obj):
        if isinstance(obj, dict) and "_bytes" not in obj:
            obj = dict(obj)
            obj.setdefault("server_time", server_time())
        self.queue.put(obj)
        if isinstance(obj, dict) and obj.get("type") in {"complete", "error", "canceled"}:
            self.close_audio_stream()

    def emit_bytes(self, data):
        if len(data) % 2:
            raise ValueError("PCM frame must have even byte length")
        if self.params.audio_mode == "native_mp3":
            while not self.cancel_event.is_set():
                try:
                    self.audio_queue.put(data, timeout=0.25)
                    break
                except queue.Full:
                    continue
        else:
            self.queue.put({"_bytes": data})

    def close_audio_stream(self):
        if self.audio_stream_closed:
            return
        self.audio_stream_closed = True
        try:
            self.audio_queue.put_nowait(None)
        except queue.Full:
            # Ensure a full queue cannot prevent shutdown after a client leaves.
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass
            self.audio_queue.put_nowait(None)


class JobManager:
    def __init__(
        self,
        concurrency=2,
        config_snapshot_provider: Optional[
            Callable[[], RuntimeSettingsSnapshot]
        ] = None,
    ):
        self.concurrency = max(1, int(concurrency))
        self._config_snapshot_provider = config_snapshot_provider
        self._active = 0
        self._capacity = self.concurrency
        self._capacity_condition = threading.Condition()
        self._executor = ThreadPoolExecutor(max_workers=max(4, self.concurrency * 2))
        self._jobs = {}
        self._order = []
        self._lock = threading.Lock()

    def reconfigure(self, concurrency):
        with self._capacity_condition:
            self._capacity = max(1, int(concurrency))
            self.concurrency = self._capacity
            self._capacity_condition.notify_all()

    def _acquire_slot(self, job):
        with self._capacity_condition:
            while self._active >= self._capacity:
                if job.cancel_event.is_set():
                    return False
                self._capacity_condition.wait(timeout=0.5)
            self._active += 1
            return True

    def _release_slot(self):
        with self._capacity_condition:
            self._active -= 1
            self._capacity_condition.notify_all()

    def create(self, params):
        config_snapshot = (
            self._config_snapshot_provider()
            if self._config_snapshot_provider is not None
            else None
        )
        job = Job(params, config_snapshot=config_snapshot)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        return job

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id):
        job = self.get(job_id)
        if job:
            job.cancel_event.set()
        return job

    def submit(self, job, target, config_snapshot=None):
        if config_snapshot is not None:
            job.config_snapshot = config_snapshot

        def run():
            acquired = self._acquire_slot(job)
            while not acquired:
                if job.cancel_event.is_set():
                    job.phase = PHASE_CANCELED
                    job.emit({"type": "canceled"})
                    return
                with self._lock:
                    position = sum(1 for jid in self._order
                                   if jid != job.id and self._jobs[jid].phase == PHASE_QUEUED)
                job.emit({"type": "status", "phase": PHASE_QUEUED,
                          "queue_position": position})
                acquired = self._acquire_slot(job)
            try:
                target(job)
            finally:
                self._release_slot()
        self._executor.submit(run)
