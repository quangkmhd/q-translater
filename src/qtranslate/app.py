"""Composition root for a background Gio service; GTK is loaded only by settings."""

import os
import threading
from pathlib import Path
from gi.repository import Gio, GLib
from qtranslate.config.settings import SettingsStore
from qtranslate.config.secrets import SecretStore
from qtranslate.logging import RuntimeLog
from qtranslate.tasks.controller import TaskController
from qtranslate.actions import Engine
from qtranslate.desktop.bus import DesktopBus


def paths():
    config = (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "q-translate"
    )
    state = (
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        / "q-translate"
    )
    cache = (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "q-translate"
    )
    return config, state, cache


class Runtime:
    def __init__(self, connection, on_stop):
        config, state, cache = paths()
        self.settings = SettingsStore(config / "settings.json")
        self.store = SecretStore(config / "credentials.json")
        self.log = RuntimeLog(state / "q-translate.log", self.store.all_secrets)
        self.engine = Engine(self.store, state / "routing.json", log=self.log)
        self.controller = TaskController(self.engine, self._queue)
        self.controller.settings = self.settings.load()
        self.closed = False
        self._lock = threading.Lock()
        self._updates = {}
        self._idle = 0
        self.bus = DesktopBus(
            connection,
            self.controller,
            cache / "captures",
            self._submitted,
            on_stop,
            log=self.log,
        )
        self.log_timer = GLib.timeout_add_seconds(60, self._maintain)
        # Register IPC before a dconf flush can re-enter D-Bus during startup.
        self.shortcut_idle = GLib.idle_add(self._setup_chat_shortcut)

    def _setup_chat_shortcut(self):
        self.shortcut_idle = 0
        if not self.closed:
            from qtranslate.desktop.shortcuts import install_chat_shortcut

            if not install_chat_shortcut(self.settings.load()["shortcuts"]["chat"]):
                self.log.record(
                    {"action": "chat_shortcut", "error": "SHORTCUT_UNAVAILABLE"}
                )
        return GLib.SOURCE_REMOVE

    def _submitted(self, request):
        self.controller.settings = self.settings.load()
        self.log.record(
            {
                "request_id": request.id,
                "action": request.action,
                "input": request.text
                if request.text is not None
                else {
                    "kind": "image",
                    "path_id": Path(request.image_path).name
                    if request.image_path
                    else "",
                },
            }
        )

    def _queue(self, event):
        with self._lock:
            if self.closed:
                return
            self._updates[event.id] = event
            if not self._idle:
                self._idle = GLib.idle_add(self._flush)

    def _flush(self):
        with self._lock:
            events = list(self._updates.values())
            self._updates.clear()
            self._idle = 0
        if self.closed:
            return GLib.SOURCE_REMOVE
        for event in events:
            if event.state in (
                "waiting",
                "streaming",
                "ready",
            ) and not self.controller.is_current(event.id):
                continue
            self.bus.emit(event)
            if event.state == "ready":
                self.bus.copy_text(
                    event.id,
                    event.text,
                    lambda ok, id=event.id: self.controller.confirm_copy(id, ok),
                )
            if event.state in (
                "success",
                "error",
                "no_text",
                "unreadable",
                "cancelled",
            ):
                self.log.record(
                    {
                        "request_id": event.id,
                        "action": event.action,
                        "state": event.state,
                        "output": event.text,
                        "provider": event.provider,
                        "model": event.model,
                        "error": event.error_code,
                    }
                )
        return GLib.SOURCE_REMOVE

    def _maintain(self):
        self.log.maintain()
        return GLib.SOURCE_CONTINUE

    def close(self):
        with self._lock:
            self.closed = True
        self.controller.shutdown()
        self.engine.close()
        self.bus.close()
        GLib.source_remove(self.log_timer)
        if self.shortcut_idle:
            GLib.source_remove(self.shortcut_idle)
            self.shortcut_idle = 0
        if self._idle:
            GLib.source_remove(self._idle)
            self._idle = 0


class Service(Gio.Application):
    def __init__(self):
        super().__init__(
            application_id="org.qtranslate.App", flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.runtime = None
        self.held = False

    def do_startup(self):
        Gio.Application.do_startup(self)
        self.runtime = Runtime(self.get_dbus_connection(), self.quit)

    def do_activate(self):
        if not self.held:
            self.hold()
            self.held = True

    def do_shutdown(self):
        if self.runtime:
            self.runtime.close()
        Gio.Application.do_shutdown(self)


def run_service():
    return Service().run(["qtranslate"])
