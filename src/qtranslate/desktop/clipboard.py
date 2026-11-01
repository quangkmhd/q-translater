"""In-memory, multi-MIME clipboard preservation for explicit TUI copy requests."""
# ruff: noqa: E402 -- select the GDK backend before Gtk's Python override initializes it.

import time
import uuid
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk

Gdk.set_allowed_backends("x11")
from gi.repository import Gtk, Gio, GLib
from .x11_owner import clipboard_owner, new_orca_publisher


class ClipboardBroker:
    def __init__(self):
        if not Gtk.init_check():
            raise ValueError("CLIPBOARD_UNAVAILABLE")
        display = Gdk.Display.get_default()
        if not display:
            raise ValueError("CLIPBOARD_UNAVAILABLE")
        self.clip = display.get_clipboard()
        self.serial = 0
        self._last_owner = None
        self._last_provider = None
        self._awaiting_formats = False
        self.saved = {}
        self.signal = self.clip.connect("changed", self._changed)

    def _changed(self, *_):
        # X11 may announce an owner repeatedly while TARGETS is fetched.
        # Count claims, not the intermediate format-discovery notifications.
        owner = self._owner()
        formats = self.clip.get_formats().get_mime_types()
        provider = self.clip.get_content()
        new_claim = owner != self._last_owner or provider != self._last_provider
        if owner and not formats and not self._awaiting_formats:
            new_claim = True
        if new_claim:
            self.serial += 1
        self._last_owner = owner
        self._last_provider = provider
        self._awaiting_formats = bool(owner and not formats)

    def _owner(self):
        return clipboard_owner()[0]

    def snapshot(self, done):
        if not self.clip.get_formats().get_mime_types():
            try:
                owned = self._owner()
            except Exception:
                done(None, "CLIPBOARD_UNAVAILABLE")
                return
            if owned:
                until = time.monotonic() + 1

                def ready():
                    if self.clip.get_formats().get_mime_types():
                        self.snapshot(done)
                        return GLib.SOURCE_REMOVE
                    if time.monotonic() >= until:
                        done(None, "CLIPBOARD_UNAVAILABLE")
                        return GLib.SOURCE_REMOVE
                    return GLib.SOURCE_CONTINUE

                GLib.timeout_add(20, ready)
                return
        serial = self.serial
        formats = list(self.clip.get_formats().get_mime_types())
        values = {}
        total = 0
        cancel = Gio.Cancellable()
        finished = False
        stream = None

        def finish(error=None):
            nonlocal finished
            if finished:
                return
            finished = True
            GLib.source_remove(timer)
            if error:
                cancel.cancel()
                done(None, error)
                return
            if self.serial != serial:
                done(None, "CLIPBOARD_CHANGED")
                return
            token = str(uuid.uuid4())
            self.saved[token] = {
                "formats": values,
                "serial": serial,
                "at": time.monotonic(),
            }
            done(token, None)

        def expired():
            finish("CLIPBOARD_UNAVAILABLE")
            return GLib.SOURCE_REMOVE

        timer = GLib.timeout_add(1500, expired)

        def next_format():
            if finished:
                return
            if not formats:
                finish()
                return
            mime = formats.pop(0)

            def opened(clipboard, result):
                nonlocal stream, total
                try:
                    stream, actual = clipboard.read_finish(result)
                except GLib.Error:
                    finish("CLIPBOARD_UNAVAILABLE")
                    return
                chunks = []

                def read_next():
                    stream.read_bytes_async(
                        65536, GLib.PRIORITY_DEFAULT, cancel, read_done
                    )

                def read_done(obj, result):
                    nonlocal total
                    try:
                        data = obj.read_bytes_finish(result).get_data()
                    except GLib.Error:
                        finish("CLIPBOARD_UNAVAILABLE")
                        return
                    total += len(data)
                    if total > 32 * 1024 * 1024:
                        finish("CLIPBOARD_UNAVAILABLE")
                        return
                    if data:
                        chunks.append(bytes(data))
                        read_next()
                        return
                    obj.close(None)
                    values[mime] = b"".join(chunks)
                    next_format()

                read_next()

            self.clip.read_async([mime], GLib.PRIORITY_DEFAULT, cancel, opened)

        next_format()

    def discard(self, token):
        self.saved.pop(token, None)

    def restore(self, token, expected_serial):
        saved = self.saved.pop(token, None)
        if not saved or self.serial != expected_serial:
            return False
        providers = [
            Gdk.ContentProvider.new_for_bytes(m, GLib.Bytes.new(b))
            for m, b in saved["formats"].items()
        ]
        self.clip.set_content(
            Gdk.ContentProvider.new_union(providers) if providers else None
        )
        return True

    def finish(self, token, done, expected_pid=None, publisher_since=None):
        saved = self.saved.get(token)
        if not saved:
            done(None, "CLIPBOARD_UNAVAILABLE")
            return
        if self.serial <= saved["serial"]:
            done(None, "NO_SELECTION")
            return
        if self.serial != saved["serial"] + 1:
            self.discard(token)
            done(None, "CLIPBOARD_CHANGED")
            return
        serial = self.serial
        expected_owner = None

        def attributed():
            nonlocal expected_owner
            if expected_pid is None:
                return True
            try:
                owner = clipboard_owner(with_pid=True)
                if expected_owner is not None:
                    return owner == expected_owner
                pid = owner[1]
                allowed = pid == expected_pid or (
                    publisher_since is not None
                    and pid
                    and new_orca_publisher(pid, publisher_since)
                )
                if allowed:
                    expected_owner = owner
                return bool(allowed)
            except (ValueError, OSError):
                return False

        if not attributed():
            self.discard(token)
            done(None, "CLIPBOARD_CHANGED")
            return

        def read(clip, result):
            try:
                text = clip.read_text_finish(result)
            except GLib.Error:
                text = None
            if self.serial != serial or not attributed():
                self.discard(token)
                done(None, "CLIPBOARD_CHANGED")
                return
            self.restore(token, serial)
            done(text, None if text and text.strip() else "NO_SELECTION")

        self.clip.read_text_async(None, read)

    def close(self):
        self.saved.clear()
        self.clip.disconnect(self.signal)
