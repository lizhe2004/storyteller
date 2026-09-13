from __future__ import annotations

import queue
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..core.observability import server_time

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


class Job:
    def __init__(self, params):
        self.id = "job_" + uuid.uuid4().hex
        self.params = params
        self.phase = PHASE_QUEUED
        self.project_id = None
        self.script_ready = None
        self.script_preview = None
        self.line_index = 0
        self.total = 0
        self.cancel_event = threading.Event()
        self.queue = queue.Queue()

    def emit(self, obj):
        if isinstance(obj, dict) and "_bytes" not in obj:
            obj = dict(obj)
            obj.setdefault("server_time", server_time())
        self.queue.put(obj)

    def emit_bytes(self, data):
        if len(data) % 2:
            raise ValueError("PCM frame must have even byte length")
        self.queue.put({"_bytes": data})


class JobManager:
    def __init__(self, concurrency=2):
        self.concurrency = max(1, int(concurrency))
        self._slots = threading.BoundedSemaphore(self.concurrency)
        self._executor = ThreadPoolExecutor(max_workers=max(4, self.concurrency * 2))
        self._jobs = {}
        self._order = []
        self._lock = threading.Lock()

    def create(self, params):
        job = Job(params)
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

    def submit(self, job, target):
        def run():
            acquired = self._slots.acquire(timeout=0.1)
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
                acquired = self._slots.acquire(timeout=0.5)
            try:
                target(job)
            finally:
                self._slots.release()
        self._executor.submit(run)
