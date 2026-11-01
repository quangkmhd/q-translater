"""Action dispatcher: complete outputs only, one key-first circular pass."""

import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from qtranslate.audit.legacy import read_routing, route_candidates, remember_success
from qtranslate.tasks.types import TaskResult
from qtranslate.providers.ai import AIAdapter
from qtranslate.providers.azure_translator import (
    AzureTranslator,
    ERRORS as TRANSLATION_ERRORS,
    MESSAGES as TRANSLATION_MESSAGES,
)
from qtranslate.text import split_text


class Engine:
    def __init__(
        self, store, state_path, adapter=None, clock=time, log=None, max_parallel=3
    ):
        self.store = store
        self.state_path = Path(state_path)
        self.adapter = adapter or AIAdapter(store)
        self.clock = clock
        self.log = log
        self.cooldown = {}
        self._pool = ThreadPoolExecutor(
            max_workers=max_parallel, thread_name_prefix="qtranslate-chunk"
        )
        self._routing_lock = threading.Lock()
        self.translator = AzureTranslator(store, state_path, log, self._routing_lock)
        self._max_parallel = max_parallel

    def __call__(self, request, settings, deadline, cancelled, on_update):
        if request.action == "translate":
            try:
                text = self.translator.translate(
                    request.text or "", request.target, deadline, cancelled
                )
                return TaskResult(
                    request.id,
                    request.action,
                    "success",
                    text,
                    "azure_translator",
                    "standard",
                )
            except Exception as e:
                code = str(e) if str(e) in TRANSLATION_ERRORS else "AZURE_UNAVAILABLE"
                return TaskResult(
                    request.id,
                    request.action,
                    "error",
                    text=TRANSLATION_MESSAGES[code],
                    provider="azure_translator",
                    model="standard",
                    error_code=code,
                )
        capability = "vision" if request.action == "image_translate" else "text"
        order = settings.get(
            "vision_order" if capability == "vision" else "provider_order", []
        )
        enabled = settings.get(
            "vision_enabled" if capability == "vision" else "enabled",
            settings.get("enabled", {}),
        )
        selected = settings.get(
            "vision_selected_models" if capability == "vision" else "selected_models",
            {},
        )
        candidates = [
            c
            for c in self.store.candidates(capability, order)
            if enabled.get(c.provider, True)
        ]
        candidates.sort(
            key=lambda c: (
                order.index(c.provider) if c.provider in order else 999,
                0 if selected.get(c.provider) == c.model else 1,
            )
        )
        if not candidates:
            return TaskResult(
                request.id,
                request.action,
                "error",
                error_code="NO_VISION_PROVIDER"
                if capability == "vision"
                else "NO_AI_PROVIDER",
            )
        mapping = {(c.provider, c.credential.id, c.model): c for c in candidates}
        state = read_routing(self.state_path)
        sticky = state.get("last_success", {}).get(capability, {})
        if selected.get(sticky.get("provider")) not in (None, sticky.get("model")):
            state.get("last_success", {}).pop(capability, None)
        route = route_candidates(
            [
                {
                    "provider": c.provider,
                    "credential_id": c.credential.id,
                    "model": c.model,
                }
                for c in candidates
            ],
            state,
            capability,
            order,
        )
        chunks = (
            [request.text or ""]
            if request.action == "chat"
            else split_text(request.text or "", limit=400)
        )
        if capability == "vision":
            chunks = ["Translate the text in this image."]
        if len(chunks) == 1:

            def partial(text, candidate):
                on_update(
                    TaskResult(
                        request.id,
                        request.action,
                        "streaming",
                        text,
                        candidate.provider,
                        candidate.model,
                    )
                )

            text, chosen, error = self._source(
                request,
                settings,
                chunks[0],
                capability,
                route,
                mapping,
                deadline,
                cancelled,
                partial,
                0,
                1,
            )
        else:
            text, chosen, error = self._long_text(
                request,
                settings,
                chunks,
                capability,
                route,
                mapping,
                deadline,
                cancelled,
                on_update,
            )
        if error:
            return TaskResult(
                request.id,
                request.action,
                "cancelled" if error == "CANCELLED" else "error",
                error_code=error,
            )
        if cancelled.is_set() or self.clock.monotonic() >= deadline:
            return TaskResult(
                request.id,
                request.action,
                "cancelled" if cancelled.is_set() else "error",
                error_code="TASK_TIMEOUT",
            )
        if capability == "vision" and text.strip() in ("NO_TEXT", "UNREADABLE"):
            return TaskResult(
                request.id,
                request.action,
                "no_text" if text.strip() == "NO_TEXT" else "unreadable",
            )
        with self._routing_lock:
            remember_success(self.state_path, capability, chosen)
        return TaskResult(
            request.id,
            request.action,
            "ready" if request.action == "rewrite" else "success",
            text,
            chosen["provider"],
            chosen["model"],
        )

    def _source(
        self,
        request,
        settings,
        source,
        capability,
        route,
        mapping,
        deadline,
        cancelled,
        on_partial,
        index,
        total,
    ):
        last_error = "ALL_PROVIDERS_FAILED"
        for attempt, entry in enumerate(route):
            if cancelled.is_set():
                return "", None, "CANCELLED"
            now = self.clock.monotonic()
            if now >= deadline:
                return "", None, "TASK_TIMEOUT"
            c = mapping[(entry["provider"], entry["credential_id"], entry["model"])]
            scope = (c.provider, c.credential.account_ref or c.credential.id)
            if self.cooldown.get(scope, 0) > now:
                continue
            partial = []
            first = None
            output_chars = 0
            attempt_deadline = min(now + 5, deadline)

            def delta(chunk):
                nonlocal first, output_chars
                if cancelled.is_set() or self.clock.monotonic() >= attempt_deadline:
                    return
                if first is None:
                    first = self.clock.monotonic() - now
                output_chars += len(chunk.delta)
                if on_partial:
                    partial.append(chunk.delta)
                    on_partial("".join(partial), c)

            payload = {
                "text": source,
                "prompt": settings.get(
                    "prompt_chat"
                    if request.action == "chat"
                    else "prompt_vision"
                    if capability == "vision"
                    else "prompt_text"
                ),
                "image_path": request.image_path,
            }
            if request.action == "chat":
                payload["messages"] = request.messages or (
                    {"role": "user", "content": source},
                )
            try:
                response = self.adapter.run(
                    payload, c, attempt_deadline, cancelled, delta
                )
            except Exception:
                response = None
            if cancelled.is_set():
                return "", None, "CANCELLED"
            complete = bool(
                response
                and response.complete
                and self.clock.monotonic() < attempt_deadline
            )
            last_error = (
                None
                if complete
                else (response.error_code if response else "NETWORK_ERROR")
            )
            if not complete and not last_error:
                last_error = (
                    "KEY_TIMEOUT"
                    if self.clock.monotonic() >= attempt_deadline
                    else "INCOMPLETE_OUTPUT"
                )
            if self.log:
                self.log.record(
                    {
                        "request_id": request.id,
                        "provider": c.provider,
                        "model": c.model,
                        "credential_id": c.credential.id,
                        "error": last_error,
                        "chunk_index": index,
                        "chunks": total,
                        "attempt": attempt + 1,
                        "elapsed_seconds": round(self.clock.monotonic() - now, 4),
                        "ttft_seconds": round(first, 4) if first is not None else None,
                        "input_chars": len(source),
                        "output_chars": output_chars,
                        "finish_reason": response.finish_reason if response else None,
                    }
                )
            if complete:
                separator = re.search(r"\s+$", source)
                return response.text + (separator[0] if separator else ""), entry, None
            if response and response.status in (429, 402):
                self.cooldown[scope] = self.clock.monotonic() + response.retry_after
        return (
            "",
            None,
            "TASK_TIMEOUT" if self.clock.monotonic() >= deadline else last_error,
        )

    def _long_text(
        self,
        request,
        settings,
        chunks,
        capability,
        route,
        mapping,
        deadline,
        cancelled,
        on_update,
    ):
        abort = threading.Event()

        class Cancellation:
            def is_set(self):
                return abort.is_set() or cancelled.is_set()

        stop = Cancellation()
        pending = {}
        results = {}
        next_submit = 0
        next_show = 0
        completed = ""
        chosen = None
        try:
            while next_show < len(chunks):
                if stop.is_set():
                    return "", None, "CANCELLED"
                if self.clock.monotonic() >= deadline:
                    return "", None, "TASK_TIMEOUT"
                while next_submit < len(chunks) and len(pending) < self._max_parallel:
                    i = next_submit
                    next_submit += 1
                    future = self._pool.submit(
                        self._source,
                        request,
                        settings,
                        chunks[i],
                        capability,
                        route,
                        mapping,
                        deadline,
                        stop,
                        None,
                        i,
                        len(chunks),
                    )
                    pending[future] = i
                done, _ = wait(
                    pending,
                    timeout=min(0.05, max(0.001, deadline - self.clock.monotonic())),
                    return_when=FIRST_COMPLETED,
                )
                for future in done:
                    i = pending.pop(future)
                    text, entry, error = future.result()
                    if error:
                        return "", None, error
                    results[i] = (text, entry)
                # Publish only completed consecutive segments. A retry never rewinds
                # already displayed text; the full result alone can enter clipboard.
                while next_show in results:
                    text, chosen = results.pop(next_show)
                    completed += text
                    next_show += 1
                    on_update(
                        TaskResult(
                            request.id,
                            request.action,
                            "streaming",
                            completed,
                            chosen["provider"],
                            chosen["model"],
                        )
                    )
            return completed, chosen, None
        finally:
            abort.set()
            for future in pending:
                future.cancel()

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
