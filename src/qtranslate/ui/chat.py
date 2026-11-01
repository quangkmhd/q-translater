"""Compact native Q-translate chat. Hide retains state; close destroys it."""
# ruff: noqa: E402 -- select X11 before importing Gtk's initializing override.

import re
import time
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkX11", "4.0")
from gi.repository import Gdk

# GNOME/Wayland includes XWayland (already required by selection acquisition).
# It permits a native utility window to keep the approved lower-right position.
Gdk.set_allowed_backends("x11")
from gi.repository import Gtk, GLib, Pango
from qtranslate.actions import Engine
from qtranslate.app import paths
from qtranslate.chat import ChatSession
from qtranslate.config.secrets import SecretStore
from qtranslate.config.settings import SettingsStore
from qtranslate.desktop.chat_window import place_chat
from qtranslate.desktop.window_visibility import hide_from_dock
from qtranslate.logging import RuntimeLog
from qtranslate.tasks.controller import TaskController

CSS = """
window.chat {background:transparent;color:#eeedf4;font-family:"Noto Sans",sans-serif;}
.chat-frame {background:#252833;border:1px solid #4b4c5e;border-radius:12px;}
.chat-header {padding:11px 12px 11px 19px;border-bottom:1px solid #3d4050;}
.chat-title {font-size:17px;font-weight:600;}
.chat-accent {color:#b9a0f5;}
.chat-shortcut {font-size:10px;color:#aaa6bd;border:1px solid #4b4d61;border-radius:5px;padding:4px 7px;}
.chat-tools button {background:transparent;border:0;box-shadow:none;min-width:22px;min-height:24px;padding:4px;border-radius:5px;color:#c7c4d7;}
.chat-tools button:hover {background:#3e3b4e;}
.chat-messages {padding:18px 20px 12px;}
.chat-user {background:#3b3551;border:1px solid #5e517e;border-radius:10px 10px 3px 10px;padding:10px 13px;font-size:14px;}
.chat-answer {font-size:15px;color:#eeedf4;}
.chat-reply {padding:6px 1px;}
.chat-error {font-size:12px;color:#e5b3bb;}
.chat-muted {font-size:11px;color:#9b98ad;}
.chat-empty {padding:20px 0 26px;font-size:15px;color:#c5bfd7;}
.chat-composer {background:#20232d;border:1px solid #65567f;border-radius:9px;padding:11px 12px 8px;margin:0 12px 12px;}
.chat-composer:focus-within {border-color:#b39be7;}
.chat-input, .chat-input text {background:transparent;color:#eeedf4;font-size:14px;}
.chat-input {padding:0;}
.chat-send {background:#b6a0ef;color:#20182e;border:0;border-radius:7px;padding:5px 8px;min-height:24px;box-shadow:none;}
.chat-send:disabled {opacity:.4;}
.chat-stop {background:#44354d;color:#e0c9f4;border:1px solid #766087;border-radius:6px;padding:5px 9px;}
.chat-hint {font-size:9px;color:#9690aa;}
"""
ERRORS = {
    "NO_AI_PROVIDER": "Chưa có provider AI hoạt động. Mở cài đặt để nhập key.",
    "TASK_TIMEOUT": "Quá 30 giây. Bạn thử gửi lại.",
    "KEY_TIMEOUT": "Các key chưa trả lời kịp. Bạn thử gửi lại.",
    "NETWORK_ERROR": "Không kết nối được dịch vụ AI.",
    "RATE_LIMITED": "Provider đang giới hạn yêu cầu. Bạn thử lại sau.",
    "INCOMPLETE_OUTPUT": "Câu trả lời chưa hoàn tất. Bạn thử gửi lại.",
    "THINKING_STILL_ENABLED": "Model trả về thinking. Đã bỏ qua phản hồi này.",
}


def text_label(text="", css=None):
    w = Gtk.Label(label=text, xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
    if css:
        w.add_css_class(css)
    return w


def answer_markup(text):
    escaped = GLib.markup_escape_text(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return re.sub(r"`([^`]+)`", r"<tt>\1</tt>", escaped)


class ChatApp(Gtk.Application):
    def __init__(self, runner=None, smoke=False):
        super().__init__(application_id="org.qtranslate.Chat")
        config, state, _cache = paths()
        self.settings = SettingsStore(config / "settings.json")
        self.store = SecretStore(config / "credentials.json")
        self.log = RuntimeLog(state / "q-translate.log", self.store.all_secrets)
        self.runner = runner
        self.state_dir = state
        self.engine = (
            None if runner else Engine(self.store, state / "routing.json", log=self.log)
        )
        self.controller = TaskController(
            runner or self.engine, self._queue, max_workers=1
        )
        self.session = ChatSession()
        self.window = None
        self.rows = {}
        self.closed = False
        self.smoke = smoke
        self.log_timer = GLib.timeout_add_seconds(60, self._maintain)
        self.resize_timer = 0
        self.closing = False
        self.reopen_requested = False
        self.close_timer = 0
        self.close_held = False
        self.layout_surface = None
        self.layout_signal = 0

    def do_activate(self):
        if self.closing:
            self.reopen_requested = True
            return
        if self.window is None:
            self._build()
        self.session.show()
        self.window.present()
        if not self.layout_signal:
            self.layout_surface = self.window.get_surface()
            self.layout_signal = self.layout_surface.connect(
                "layout", self._surface_layout
            )
        self.input.grab_focus()
        GLib.timeout_add(80, self._position)
        if self.smoke:
            GLib.timeout_add(500, lambda: (self.close_chat(), GLib.SOURCE_REMOVE)[1])

    def _position(self):
        if self.window and self.window.get_visible():
            place_chat(self.window)
        return GLib.SOURCE_REMOVE

    def _surface_layout(self, _surface, width, height):
        if self.window and self.window.get_visible():
            place_chat(self.window, width, height)

    def _build(self):
        self.closed = False
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.window = Gtk.ApplicationWindow(
            application=self,
            title="Q-translate",
            default_width=540,
            default_height=350,
            decorated=False,
        )
        self.window.add_css_class("chat")
        self.window.connect("realize", hide_from_dock)
        self.window.connect("close-request", self._close_requested)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("chat-frame")
        self.window.set_child(root)
        header = Gtk.Box(spacing=10)
        header.add_css_class("chat-header")
        icon = Gtk.Image.new_from_icon_name("starred-symbolic")
        icon.add_css_class("chat-accent")
        header.append(icon)
        header.append(text_label("Q-translate", "chat-title"))
        header.append(Gtk.Box(hexpand=True))
        header.append(text_label("Alt D", "chat-shortcut"))
        tools = Gtk.Box(spacing=3)
        tools.add_css_class("chat-tools")
        for name, tip, callback in [
            ("list-add-symbolic", "Cuộc trò chuyện mới", self.new_chat),
            ("window-minimize-symbolic", "Ẩn · giữ lịch sử · Esc", self.hide_chat),
            ("window-close-symbolic", "Đóng và xóa lịch sử phiên", self.close_chat),
        ]:
            b = Gtk.Button.new_from_icon_name(name)
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _b, cb=callback: cb())
            tools.append(b)
        header.append(tools)
        drag = Gtk.WindowHandle()
        drag.set_child(header)
        root.append(drag)
        self.scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.messages = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.messages.add_css_class("chat-messages")
        self.empty = text_label("Bạn cần mình giúp gì?", "chat-empty")
        self.messages.append(self.empty)
        self.scroll.set_child(self.messages)
        root.append(self.scroll)
        self.composer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        self.composer.add_css_class("chat-composer")
        root.append(self.composer)
        input_scroll = Gtk.ScrolledWindow()
        input_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        input_scroll.set_min_content_height(48)
        input_scroll.set_max_content_height(120)
        input_scroll.set_propagate_natural_height(True)
        self.input = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False)
        self.input.add_css_class("chat-input")
        self.input.set_tooltip_text("Nhập câu hỏi · Enter gửi · Shift+Enter xuống dòng")
        self.input.get_buffer().connect("changed", self._draft_changed)
        input_scroll.set_child(self.input)
        overlay = Gtk.Overlay()
        overlay.set_child(input_scroll)
        self.placeholder = text_label("Hỏi mình bất cứ điều gì…", "chat-muted")
        self.placeholder.set_valign(Gtk.Align.START)
        self.placeholder.set_can_target(False)
        overlay.add_overlay(self.placeholder)
        self.composer.append(overlay)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._input_key)
        self.input.add_controller(keys)
        row = Gtk.Box(spacing=10)
        self.composer.append(row)
        hint = text_label("Enter gửi · Shift+Enter xuống dòng", "chat-hint")
        hint.set_wrap(False)
        row.append(hint)
        row.append(Gtk.Box(hexpand=True))
        self.send_button = Gtk.Button.new_from_icon_name("go-up-symbolic")
        self.send_button.add_css_class("chat-send")
        self.send_button.set_tooltip_text("Gửi")
        self.send_button.connect("clicked", lambda _b: self.send())
        row.append(self.send_button)
        self.stop_button = Gtk.Button(label="Dừng")
        self.stop_button.add_css_class("chat-stop")
        self.stop_button.connect("clicked", lambda _b: self.stop())
        row.append(self.stop_button)
        self.stop_button.set_visible(False)
        self.send_button.set_sensitive(False)
        window_keys = Gtk.EventControllerKey()
        window_keys.connect("key-pressed", self._window_key)
        self.window.add_controller(window_keys)

    def _draft_changed(self, buffer):
        self.session.draft = buffer.get_text(*buffer.get_bounds(), True)
        self.placeholder.set_visible(not self.session.draft)
        self.send_button.set_sensitive(
            bool(self.session.draft.strip()) and not self.session.active_id
        )

    def _input_key(self, controller, keyval, _code, state):
        if (
            keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter)
            or state & Gdk.ModifierType.SHIFT_MASK
        ):
            return False
        event = controller.get_current_event()
        if event is not None and self.input.im_context_filter_keypress(event):
            return True
        self.send()
        return True

    def _window_key(self, _controller, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self.hide_chat()
            return True
        return False

    def send(self):
        if self.closed or self.session.active_id or not self.session.draft.strip():
            return
        request = self.session.begin(self.session.draft)
        self.input.get_buffer().set_text("")
        self.empty.set_visible(False)
        user = text_label(request.text, "chat-user")
        user.set_selectable(True)
        user.set_halign(Gtk.Align.END)
        user.set_max_width_chars(49)
        self.messages.append(user)
        reply = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        reply.add_css_class("chat-reply")
        answer = text_label("", "chat-answer")
        answer.set_selectable(True)
        reply.append(answer)
        spinner = Gtk.Spinner(spinning=True, halign=Gtk.Align.START)
        reply.append(spinner)
        error = text_label("", "chat-error")
        error.set_selectable(True)
        error.set_visible(False)
        reply.append(error)
        tools = Gtk.Box()
        tools.add_css_class("chat-tools")
        copy = Gtk.Button.new_from_icon_name("edit-copy-symbolic")
        copy.set_tooltip_text("Sao chép đoạn đã chọn hoặc toàn bộ câu trả lời")
        copy.set_sensitive(False)
        copy.set_visible(False)
        copy.connect("clicked", lambda _b, id=request.id: self.copy_reply(id))
        tools.append(copy)
        reply.append(tools)
        self.messages.append(reply)
        self.rows[request.id] = {
            "answer": answer,
            "spinner": spinner,
            "error": error,
            "copy": copy,
        }
        self.stop_button.set_visible(True)
        self.send_button.set_visible(False)
        self.controller.settings = self.settings.load()
        self.log.record(
            {
                "request_id": request.id,
                "action": "chat",
                "input": request.text,
                "session_id": self.session.session_id,
            }
        )
        self.controller.submit(request)
        self._schedule_resize()
        self.input.grab_focus()

    def _queue(self, event):
        GLib.idle_add(self._apply, event)

    def _apply(self, event):
        if self.closed or not self.session.apply(event):
            return GLib.SOURCE_REMOVE
        row = self.rows.get(event.id)
        if not row:
            return GLib.SOURCE_REMOVE
        turn = self.session.turns[-1]
        row["answer"].set_markup(answer_markup(turn.text))
        row["spinner"].set_visible(event.state == "waiting")
        if event.state in ("success", "error", "cancelled"):
            self.stop_button.set_visible(False)
            self.send_button.set_visible(True)
            self._draft_changed(self.input.get_buffer())
            row["copy"].set_visible(event.state == "success")
            row["copy"].set_sensitive(event.state == "success")
            if event.state in ("error", "cancelled"):
                row["error"].set_text(
                    "Đã dừng."
                    if event.state == "cancelled"
                    else ERRORS.get(
                        event.error_code,
                        "Không nhận được câu trả lời. Bạn thử gửi lại. ("
                        + str(event.error_code)
                        + ")",
                    )
                )
                row["error"].set_visible(True)
            self.log.record(
                {
                    "request_id": event.id,
                    "action": "chat",
                    "state": event.state,
                    "output": turn.text,
                    "error": event.error_code,
                    "provider": event.provider,
                    "model": event.model,
                }
            )
        self._schedule_resize()
        return GLib.SOURCE_REMOVE

    def _schedule_resize(self):
        if not self.resize_timer:
            self.resize_timer = GLib.timeout_add(50, self._resize)

    def _resize(self):
        self.resize_timer = 0
        if self.closed or not self.window:
            return GLib.SOURCE_REMOVE
        width = max(420, self.window.get_width())
        natural = self.messages.measure(Gtk.Orientation.VERTICAL, width - 48)[1]
        monitor = self.window.get_display().get_monitor_at_surface(
            self.window.get_surface()
        )
        max_height = min(660, monitor.get_geometry().height - 90) if monitor else 660
        height = min(max_height, max(330, natural + 175))
        self.window.set_default_size(540, height)
        adjustment = self.scroll.get_vadjustment()
        adjustment.set_value(
            max(0, adjustment.get_upper() - adjustment.get_page_size())
        )
        self._position()
        return GLib.SOURCE_REMOVE

    def copy_reply(self, id):
        turn = next((t for t in self.session.turns if t.id == id), None)
        if turn and turn.state == "success":
            label = self.rows[id]["answer"]
            selected, start, end = label.get_selection_bounds()
            text = label.get_text()[start:end] if selected else turn.text
            self.window.get_display().get_clipboard().set(text)

    def stop(self):
        id = self.session.active_id
        if id:
            self.controller.cancel(id)

    def new_chat(self):
        id = self.session.clear()
        if id:
            self.controller.cancel(id)
        child = self.messages.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            if child is not self.empty:
                self.messages.remove(child)
            child = next_child
        self.rows.clear()
        self.empty.set_visible(True)
        self.input.get_buffer().set_text("")
        self.stop_button.set_visible(False)
        self.send_button.set_visible(True)
        self.input.grab_focus()
        self._schedule_resize()

    def hide_chat(self):
        self.session.hide()
        if self.window:
            self.window.set_visible(False)

    def _close_requested(self, _window):
        self.close_chat()
        return True

    def close_chat(self):
        if self.closed:
            return
        self.closed = True
        self.closing = True
        self.close_deadline = time.monotonic() + 6
        id = self.session.close()
        if id:
            self.controller.cancel(id)
        self.rows.clear()
        self.controller.shutdown()
        # Keep the process alive until cancellation has killed/reaped transport
        # children. Destroying the last window would otherwise quit GTK while
        # TaskController's daemon worker is still inside request_stream().
        if self.controller.active_workers:
            self.hold()
            self.close_held = True
        if self.resize_timer:
            GLib.source_remove(self.resize_timer)
            self.resize_timer = 0
        if self.log_timer:
            GLib.source_remove(self.log_timer)
            self.log_timer = 0
        if self.window:
            if self.layout_signal:
                self.layout_surface.disconnect(self.layout_signal)
                self.layout_signal = 0
                self.layout_surface = None
            self.input.get_buffer().set_text("")
            self.window.destroy()
            self.window = None
        if self.controller.active_workers:
            self.close_timer = GLib.timeout_add(20, self._finish_close)
        else:
            self._finish_close()

    def _finish_close(self):
        if self.controller.active_workers and time.monotonic() < self.close_deadline:
            return GLib.SOURCE_CONTINUE
        if self.controller.active_workers:
            self.log.record({"action": "chat", "error": "CANCEL_CLEANUP_TIMEOUT"})
        self.close_timer = 0
        if self.engine:
            self.engine.close()
        self.closing = False
        if self.reopen_requested:
            self.reopen_requested = False
            self.engine = (
                None
                if self.runner
                else Engine(self.store, self.state_dir / "routing.json", log=self.log)
            )
            self.controller = TaskController(
                self.runner or self.engine, self._queue, max_workers=1
            )
            self.log_timer = GLib.timeout_add_seconds(60, self._maintain)
            self.do_activate()
            if self.close_held:
                self.release()
                self.close_held = False
        else:
            if self.close_held:
                self.release()
                self.close_held = False
            self.quit()
        return GLib.SOURCE_REMOVE

    def _maintain(self):
        self.log.maintain()
        return GLib.SOURCE_CONTINUE

    def do_shutdown(self):
        self.close_chat()
        Gtk.Application.do_shutdown(self)


def run_chat(smoke=False):
    return ChatApp(smoke=smoke).run(["qtranslate-chat"])
