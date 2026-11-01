"""Session IPC; only the current extension owner may submit source or request copy."""

import json
import time
import uuid
from pathlib import Path
from gi.repository import Gio, GLib
from .protocol import ProtocolGate, TextTransfer, validate_crop_path
from .context import SourceContext
from qtranslate.tasks.types import TaskRequest

XML = """<node><interface name="org.qtranslate.App1">
<method name="Submit"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
<method name="ReadSelection"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
<method name="Cancel"><arg type="s" direction="in"/><arg type="b" direction="out"/></method>
<method name="Capabilities"><arg type="s" direction="out"/></method>
<method name="Stop"/>
<method name="BeginText"><arg type="s" direction="in"/><arg type="s" direction="in"/></method>
<method name="AppendText"><arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="s" direction="in"/></method>
<method name="FinishText"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
<signal name="TaskChanged"><arg type="s"/><arg type="s"/></signal>
</interface></node>"""


class DesktopBus:
    def __init__(
        self, connection, controller, cache_root, on_submit, on_stop, log=None
    ):
        from .tui_selection import TuiSelectionReader

        self.source_reader = TuiSelectionReader(log)
        self.connection = connection
        self.controller = controller
        self.cache_root = Path(cache_root)
        self.on_submit = on_submit
        self.on_stop = on_stop
        self.gate = ProtocolGate()
        self.transfer = TextTransfer()
        self.transfer_meta = {}
        self.closed = False
        self.registration = connection.register_object(
            "/org/qtranslate/App",
            Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0],
            self._call,
            None,
            None,
        )
        self.watch = Gio.bus_watch_name_on_connection(
            connection,
            "org.qtranslate.Desktop",
            Gio.BusNameWatcherFlags.NONE,
            self._appeared,
            self._vanished,
        )
        self.cleanup = GLib.timeout_add_seconds(1, self._maintain)

    def _appeared(self, connection, name, owner):
        self.gate.set_owner(owner, None)
        connection.call(
            owner,
            "/org/qtranslate/Desktop",
            "org.qtranslate.Desktop1",
            "Capabilities",
            None,
            GLib.VariantType.new("(s)"),
            Gio.DBusCallFlags.NONE,
            3000,
            None,
            self._caps_done,
            owner,
        )

    def _caps_done(self, connection, result, owner):
        try:
            caps = json.loads(connection.call_finish(result).unpack()[0])
            if not self.closed and self.gate.owner == owner:
                self.gate.set_owner(owner, caps["epoch"])
        except (GLib.Error, ValueError, KeyError):
            pass

    def _vanished(self, *_):
        self.gate.set_owner(None, None)
        for action, id in list(self.controller._current.items()):
            self.controller.cancel(id)
        self.transfer.close()
        self.transfer_meta.clear()

    def _request(self, value, started_at=None):
        issued = value.get("started_at")
        if isinstance(issued, (int, float)):
            import math

            if not math.isfinite(issued):
                raise ValueError("INVALID_START_TIME")
            started_at = min(
                time.monotonic() if started_at is None else started_at, issued
            )
        context = value.get("context", {})
        kwargs = {
            k: context[k]
            for k in ("window_id", "app_id", "source_epoch", "monitor")
            if k in context
        }
        path = value.get("image_path")
        if value["action"] == "image_translate":
            path = validate_crop_path(path, self.cache_root)
        request = TaskRequest(
            value.get("id") or str(uuid.uuid4()),
            value["action"],
            text=value.get("text"),
            image_path=path,
            context=SourceContext(**kwargs),
            target=value.get("target"),
            started_at=started_at,
        )
        self.on_submit(request)
        return self.controller.submit(request)

    def _call(
        self, connection, sender, path, interface, method, parameters, invocation
    ):
        try:
            args = parameters.unpack()
            if method == "Capabilities":
                invocation.return_value(
                    GLib.Variant(
                        "(s)",
                        [
                            json.dumps(
                                {
                                    "backend": True,
                                    "bridge_owner": bool(self.gate.owner),
                                    "bridge_ready": bool(self.gate.epoch),
                                }
                            )
                        ],
                    )
                )
                return
            if method == "Stop":
                invocation.return_value(None)
                self.on_stop()
                return
            if not self.gate.owner or sender != self.gate.owner or not self.gate.epoch:
                raise ValueError("UNTRUSTED_CALLER")
            if method == "ReadSelection":
                value = self.gate.validate(sender, json.loads(args[0]))
                self.source_reader.read(
                    value,
                    lambda result: invocation.return_value(
                        GLib.Variant("(s)", [json.dumps(result)])
                    ),
                )
                return
            if method == "Submit":
                value = self.gate.validate(sender, json.loads(args[0]))
                invocation.return_value(GLib.Variant("(s)", [self._request(value)]))
            elif method == "Cancel":
                invocation.return_value(
                    GLib.Variant(
                        "(b)",
                        [
                            self.source_reader.cancel(args[0])
                            or self.controller.cancel(args[0])
                        ],
                    )
                )
            elif method == "BeginText":
                id, raw = args
                value = self.gate.validate(sender, json.loads(raw))
                self.transfer.begin(id, value["chunk_count"])
                self.transfer_meta[id] = (value, time.monotonic())
                invocation.return_value(None)
            elif method == "AppendText":
                self.transfer.append(*args)
                invocation.return_value(None)
            elif method == "FinishText":
                id = args[0]
                value, started = self.transfer_meta.pop(id)
                value["text"] = self.transfer.finish(id)
                if time.monotonic() - started >= 30:
                    raise ValueError("TASK_TIMEOUT")
                invocation.return_value(
                    GLib.Variant("(s)", [self._request(value, started)])
                )
            else:
                raise ValueError("UNKNOWN_METHOD")
        except (ValueError, TypeError, KeyError, OSError):
            invocation.return_dbus_error(
                "org.qtranslate.Error.InvalidRequest", "Request rejected"
            )

    def emit(self, event):
        self.connection.emit_signal(
            None,
            "/org/qtranslate/App",
            "org.qtranslate.App1",
            "TaskChanged",
            GLib.Variant(
                "(ss)",
                [
                    event.id,
                    json.dumps(
                        {
                            **event.to_dict(),
                            "font_size": self.controller.snapshot(event.id).get(
                                "font_size", 18
                            ),
                        },
                        ensure_ascii=False,
                    ),
                ],
            ),
        )

    def copy_text(self, id, text, callback):
        if not self.gate.owner:
            callback(False)
            return
        owner = self.gate.owner

        def done(connection, result):
            try:
                ok = (
                    connection.call_finish(result).unpack()[0]
                    and self.gate.owner == owner
                )
            except GLib.Error:
                ok = False
            callback(ok)

        self.connection.call(
            owner,
            "/org/qtranslate/Desktop",
            "org.qtranslate.Desktop1",
            "CopyText",
            GLib.Variant("(ss)", [id, text]),
            GLib.VariantType.new("(b)"),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
            done,
        )

    def _maintain(self):
        for id, (_v, start) in list(self.transfer_meta.items()):
            if time.monotonic() - start >= 30:
                self.transfer.discard(id)
                self.transfer_meta.pop(id, None)
        return GLib.SOURCE_CONTINUE

    def close(self):
        self.closed = True
        self.source_reader.close()
        GLib.source_remove(self.cleanup)
        Gio.bus_unwatch_name(self.watch)
        self.connection.unregister_object(self.registration)
        self.transfer.close()
