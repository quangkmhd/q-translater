"""Private JSONL diagnostics, cleared every 24h without retaining archives."""

import json
import os
import threading
import time
from pathlib import Path
from qtranslate.audit.legacy import write_private


class RuntimeLog:
    def __init__(self, path, secrets=lambda: [], clock=time):
        self.path = Path(path)
        self.secrets = secrets
        self.clock = clock
        self._lock = threading.RLock()
        self.meta = self.path.with_suffix(".meta.json")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            os.close(fd)
            os.chmod(self.path, 0o600)
            self.maintain()
        except OSError:
            pass

    def maintain(self):
        with self._lock:
            try:
                now = self.clock.time()
                try:
                    last = json.loads(self.meta.read_text())["cleared_at"]
                except (OSError, ValueError, KeyError):
                    last = None
                if last is None or now - last >= 86400 or now < last:
                    if last is not None:
                        self.path.write_text("")
                    write_private(self.meta, {"cleared_at": now})
            except OSError:
                pass

    def clear(self):
        with self._lock:
            try:
                self.path.write_text("")
                write_private(self.meta, {"cleared_at": self.clock.time()})
            except OSError:
                pass

    def record(self, event):
        with self._lock:
            try:
                self.maintain()
                safe = {
                    k: v
                    for k, v in event.items()
                    if k.lower()
                    not in (
                        "authorization",
                        "key",
                        "api_key",
                        "image",
                        "image_bytes",
                        "headers",
                    )
                }
                text = json.dumps({"at": self.clock.time(), **safe}, ensure_ascii=False)
                for value in self.secrets():
                    if len(value) >= 8:
                        text = text.replace(value, "[REDACTED]")
                with self.path.open("a") as f:
                    f.write(text + "\n")
            except (OSError, ValueError, TypeError):
                pass
