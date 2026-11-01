"""Bounded workers and independent latest-wins generations for each action."""

import copy
import threading
import time
from collections import OrderedDict
from dataclasses import replace
from .types import TaskResult


class TaskController:
    def __init__(self, runner, emit, clock=time, max_workers=2):
        self.runner = runner
        self.emit = emit
        self.clock = clock
        self.max_workers = max_workers
        self.settings = {}
        self._lock = threading.RLock()
        self._records = {}
        self._current = {}
        self._pending = OrderedDict()
        self._active = 0
        self._closed = False
        self._stop = threading.Event()
        self._watchdog = threading.Thread(target=self._watch, daemon=True)
        self._watchdog.start()

    @property
    def active_workers(self):
        with self._lock:
            return self._active

    @property
    def pending_count(self):
        with self._lock:
            return len(self._pending)

    def snapshot(self, id):
        with self._lock:
            return copy.deepcopy(self._records.get(id, {}).get("settings", {}))

    def is_current(self, id):
        with self._lock:
            r = self._records.get(id)
            return bool(
                r
                and not r["cancel"].is_set()
                and self._current.get(r["request"].action) == id
            )

    def submit(self, request):
        with self._lock:
            if self._closed:
                raise RuntimeError("CONTROLLER_STOPPED")
            if request.id in self._records:
                raise ValueError("DUPLICATE_TASK_ID")
            self._prune()
            old = self._current.get(request.action)
            if old:
                self.cancel(old)
            cancel = threading.Event()
            settings = copy.deepcopy(self.settings)
            self._records[request.id] = {
                "request": request,
                "settings": settings,
                "deadline": (
                    request.started_at
                    if request.started_at is not None
                    else self.clock.monotonic()
                )
                + 30,
                "cancel": cancel,
                "result": None,
            }
            self._current[request.action] = request.id
            if request.action != "image_translate" and not (request.text or "").strip():
                self.update(
                    TaskResult(
                        request.id, request.action, "error", error_code="NO_SELECTION"
                    )
                )
                return request.id
            self.update(TaskResult(request.id, request.action, "waiting"))
            self._pending[request.action] = request.id
            self._dispatch()
            return request.id

    def _dispatch(self):
        while not self._closed and self._pending and self._active < self.max_workers:
            _, id = self._pending.popitem(last=False)
            if not self.is_current(id):
                continue
            self._active += 1
            threading.Thread(
                target=self._run, args=(id, self._records[id]), daemon=True
            ).start()

    def _run(self, id, record):
        try:
            result = self.runner(
                record["request"],
                record["settings"],
                record["deadline"],
                record["cancel"],
                self.update,
            )
            if result:
                self.update(result)
        except Exception:
            self.update(
                TaskResult(
                    id, record["request"].action, "error", error_code="INTERNAL_ERROR"
                )
            )
        finally:
            with self._lock:
                self._active -= 1
                self._dispatch()
                self._prune()

    def _prune(self):
        # Completed records do not retain source text indefinitely.
        live = set(self._current.values()) | set(self._pending.values())
        for id, r in list(self._records.items()):
            if id not in live and r["cancel"].is_set():
                self._records.pop(id, None)

    def update(self, result):
        with self._lock:
            if not self.is_current(result.id):
                return
            record = self._records[result.id]
            if result.action != record["request"].action:
                return
            if self.clock.monotonic() >= record["deadline"]:
                result = TaskResult(
                    result.id, result.action, "error", error_code="TASK_TIMEOUT"
                )
            if result.action == "rewrite" and result.state == "success":
                result = replace(result, state="ready")
            record["result"] = result
            if result.state in (
                "success",
                "error",
                "cancelled",
                "no_text",
                "unreadable",
            ):
                record["cancel"].set()
                self._current.pop(result.action, None)
            self.emit(result)

    def confirm_copy(self, id, ok):
        with self._lock:
            if not self.is_current(id):
                return
            r = self._records[id]
            result = r["result"]
            if not result or result.state != "ready" or result.action != "rewrite":
                return
            if self.clock.monotonic() >= r["deadline"]:
                self.tick()
                return
            final = replace(
                result,
                state="success" if ok else "error",
                error_code=None if ok else "CLIPBOARD_FAILED",
            )
            r["result"] = final
            r["cancel"].set()
            self._current.pop(result.action, None)
            self.emit(final)

    def cancel(self, id):
        with self._lock:
            if not self.is_current(id):
                return False
            r = self._records[id]
            r["cancel"].set()
            action = r["request"].action
            self._current.pop(action, None)
            self._pending.pop(action, None)
            self.emit(TaskResult(id, action, "cancelled"))
            return True

    def tick(self):
        with self._lock:
            for id in list(self._current.values()):
                r = self._records[id]
                if self.clock.monotonic() >= r["deadline"]:
                    self.update(
                        TaskResult(
                            id, r["request"].action, "error", error_code="TASK_TIMEOUT"
                        )
                    )

    def _watch(self):
        while not self._stop.wait(0.05):
            self.tick()

    def shutdown(self):
        with self._lock:
            self._closed = True
            for id in list(self._current.values()):
                self.cancel(id)
            self._pending.clear()
            self._stop.set()
