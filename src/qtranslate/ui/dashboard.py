"""GTK4 dashboard; source layout follows the approved local prototype."""
# ruff: noqa: E402

import subprocess
import threading
import sys
from pathlib import Path
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk

Gdk.set_allowed_backends("x11")
from gi.repository import Gtk, Gio, GLib
from qtranslate.app import paths
from qtranslate.config.settings import SettingsStore, defaults
from qtranslate.config.secrets import SecretStore
from qtranslate.config.env_import import parse_import
from qtranslate.ui.model import DashboardModel
from qtranslate.logging import RuntimeLog
from qtranslate.desktop.window_visibility import hide_from_dock

NAMES = {
    "cloudflare": "Cloudflare Workers AI",
    "nvidia": "NVIDIA",
    "ollama": "Ollama Cloud",
    "google": "Google AI",
    "openrouter": "OpenRouter",
}
from qtranslate.providers.azure_translator import MESSAGES as AZURE_ERRORS

CSS = """window {background:#20232d;color:#eeedf2;} .sidebar {background:#191c25;padding:24px;} .brand {font-size:24px;font-weight:700;color:#b6a8ff;} .page {padding:28px;} .title {font-size:25px;font-weight:700;} .muted {color:#a2a7b6;} .panel {background:#292d3a;border:1px solid #3c4152;border-radius:12px;padding:20px;margin-top:18px;} .provider {padding:12px;border-bottom:1px solid #3c4152;} button {border-radius:7px;padding:9px;} .primary {background:#a999ef;color:#161923;} entry,combobox,textview {background:#222630;color:#eeedf2;} .nav {padding:11px;margin-top:6px;}"""


def label(text, css=None):
    w = Gtk.Label(label=text, xalign=0, wrap=True)
    if css:
        w.add_css_class(css)
    return w


def button(text, callback, css=None):
    b = Gtk.Button(label=text)
    b.connect("clicked", lambda _b: callback())
    if css:
        b.add_css_class(css)
    return b


def vertical(spacing=8):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)


class Dashboard(Gtk.Application):
    def __init__(self, smoke=False):
        super().__init__(application_id="org.qtranslate.Settings")
        self.smoke = smoke
        config, state, cache = paths()
        self.model = DashboardModel(
            SettingsStore(config / "settings.json"),
            SecretStore(config / "credentials.json"),
        )
        self.state_dir = state
        self.window = None
        self.mode = "free"
        self.azure_busy = False

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.window = Gtk.ApplicationWindow(
            application=self,
            title="Q Translate · Cài đặt",
            default_width=1080,
            default_height=740,
        )
        self.window.connect("realize", hide_from_dock)
        root = Gtk.Box()
        self.window.set_child(root)
        sidebar = vertical()
        sidebar.set_size_request(220, -1)
        sidebar.add_css_class("sidebar")
        root.append(sidebar)
        sidebar.append(label("Q Translate", "brand"))
        sidebar.append(label("Cài đặt của bạn", "muted"))
        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        root.append(self.stack)
        for name, title, build in [
            ("services", "Dịch vụ & model", self.services),
            ("keys", "API key", self.keys),
            ("appearance", "Giao diện & phím tắt", self.appearance),
            ("prompts", "Prompt", self.prompts),
            ("logs", "Nhật ký", self.logs),
        ]:
            page = vertical()
            page.add_css_class("page")
            page.append(label(title, "title"))
            build(page)
            scroll = Gtk.ScrolledWindow()
            scroll.set_child(page)
            self.stack.add_named(scroll, name)
            sidebar.append(
                button(
                    title, lambda n=name: self.stack.set_visible_child_name(n), "nav"
                )
            )
        sidebar.append(Gtk.Box(vexpand=True))
        sidebar.append(button("Thoát ứng dụng", self.stop_backend))
        self.notice = label("", "muted")
        sidebar.append(self.notice)
        self.window.present()
        if self.smoke:
            GLib.timeout_add(400, lambda: (self.quit(), GLib.SOURCE_REMOVE)[1])

    def panel(self, page):
        w = vertical()
        w.add_css_class("panel")
        page.append(w)
        return w

    def inform(self, text):
        self.notice.set_text(text)

    def services(self, page):
        page.append(
            label(
                "Chọn dịch vụ và model. Giữ cặp vừa thành công; lỗi mới fallback.",
                "muted",
            )
        )
        tabs = Gtk.Box(spacing=8)
        page.append(tabs)
        for mode, title in [
            ("free", "Alt+C · Miễn phí"),
            ("text", "Alt+V · Tiếng Anh"),
            ("vision", "Alt+X · Dịch ảnh"),
        ]:
            tabs.append(button(title, lambda m=mode: self.set_mode(m)))
        self.provider_box = self.panel(page)
        self.render_providers()
        info = self.panel(page)
        info.append(label("Fallback: key trước → provider sau"))
        info.append(
            label(
                "Alt+V/X: 5 giây/lần · chat: tối đa 30 giây · thinking tắt", "muted"
            )
        )

    def set_mode(self, mode):
        self.mode = mode
        self.render_providers()

    def render_providers(self):
        child = self.provider_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.provider_box.remove(child)
            child = nxt
        if self.mode == "free":
            self.render_translator()
            return
        settings = self.model.settings.load()
        for i, row in enumerate(self.model.providers(self.mode), 1):
            line = Gtk.Box(spacing=12)
            line.add_css_class("provider")
            self.provider_box.append(line)
            name = vertical(2)
            name.set_hexpand(True)
            name.append(label(f"{i:02}  {NAMES[row['id']]}"))
            name.append(
                label(
                    f"{row['count']} key đã thử "
                    + ("text" if self.mode == "text" else "ảnh"),
                    "muted",
                )
            )
            line.append(name)
            combo = Gtk.ComboBoxText()
            combo.set_size_request(290, -1)
            for m in row["models"]:
                combo.append_text(m)
            if row["models"]:
                selected = settings.get(
                    "selected_models"
                    if self.mode == "text"
                    else "vision_selected_models",
                    {},
                ).get(row["id"], row["models"][0])
                combo.set_active(
                    row["models"].index(selected) if selected in row["models"] else 0
                )
            else:
                combo.append_text(
                    "Chưa có model đã thử ảnh"
                    if self.mode == "vision"
                    else "Chưa kiểm tra"
                )
                combo.set_active(0)
                combo.set_sensitive(False)
            combo.connect(
                "changed",
                lambda c, pid=row["id"], mode=self.mode: self.select_model(
                    pid, c.get_active_text(), mode
                ),
            )
            line.append(combo)
            switch = Gtk.Switch(active=row["enabled"], valign=Gtk.Align.CENTER)
            switch.connect(
                "notify::active",
                lambda s, _p, pid=row["id"]: self.toggle(pid, s.get_active()),
            )
            line.append(switch)
            line.append(button("↑", lambda p=row["id"]: self.move(p, -1)))
            line.append(button("↓", lambda p=row["id"]: self.move(p, 1)))

    def render_translator(self):
        p = self.provider_box
        p.append(label("Microsoft Translator · Alt+C"))
        p.append(
            label("Dịch Anh ↔ Việt bằng API dịch chuẩn. Nguồn trộn → Việt.", "muted")
        )
        p.append(
            label(
                "Chọn Free F0 trên Azure: 2 triệu ký tự/tháng. Ứng dụng không tự đổi gói Azure.",
                "muted",
            )
        )
        p.append(
            Gtk.LinkButton(
                uri="https://portal.azure.com/",
                label="Mở Azure Portal để tạo Translator · Free F0",
            )
        )
        status = self.model.translator_status()
        p.append(
            label(
                f"{status['verified']} key đã kiểm tra · {status['pending']} key chờ kiểm tra",
                "muted",
            )
        )
        for credential in status["credentials"]:
            p.append(
                label(
                    f"•••••••• · {credential['id'][-8:]} · {credential['region']}"
                    + (
                        " · đã kiểm tra"
                        if credential["verified"]
                        else " · chờ kiểm tra"
                    ),
                    "muted",
                )
            )
        p.append(label("Key Translator"))
        self.azure_key = Gtk.PasswordEntry(show_peek_icon=True, hexpand=True)
        p.append(self.azure_key)
        p.append(label("Region"))
        self.azure_region = Gtk.Entry(
            text="global", placeholder_text="global hoặc southeastasia"
        )
        p.append(self.azure_region)
        p.append(
            label(
                "Lấy key và region ở Keys and Endpoint. Global không cần header region. Kiểm tra sẽ dịch một câu mẫu ngắn.",
                "muted",
            )
        )
        row = Gtk.Box(spacing=8)
        p.append(row)
        self.azure_save = button(
            "Kiểm tra & lưu key", lambda: self.configure_translator(False), "primary"
        )
        self.azure_verify = button(
            "Kiểm tra key đã import", lambda: self.configure_translator(True)
        )
        row.append(self.azure_save)
        row.append(self.azure_verify)
        self.azure_save.set_sensitive(not self.azure_busy)
        self.azure_verify.set_sensitive(not self.azure_busy and status["pending"] > 0)

    def configure_translator(self, imported):
        if self.azure_busy:
            return
        key, region = self.azure_key.get_text(), self.azure_region.get_text()
        if not imported and not key.strip():
            self.inform("Nhập key của resource Azure Translator trước.")
            return
        self.azure_busy = True
        self.azure_save.set_sensitive(False)
        self.azure_verify.set_sensitive(False)
        self.inform("Đang kiểm tra Azure Translator…")

        def work():
            error, ok = None, False
            try:
                if imported:
                    report = self.model.verify_translators()
                    ok = report["verified"] > 0
                    error = report["errors"][0]["error"] if report["errors"] else None
                else:
                    self.model.save_translator(key, region)
                    ok = True
            except (RuntimeError, ValueError, OSError) as exc:
                from qtranslate.providers.azure_translator import ERRORS

                value = str(exc)
                error = value if value in ERRORS else "AZURE_UNAVAILABLE"
            RuntimeLog(
                self.state_dir / "q-translate.log", self.model.store.all_secrets
            ).record({"action": "translator_setup", "success": ok, "error": error})
            GLib.idle_add(done, ok, error)

        def done(ok, error):
            self.azure_busy = False
            if ok:
                from qtranslate.install import finish_setup

                finish_setup(self.model.settings)
                self.azure_key.set_text("")
            self.inform(
                AZURE_ERRORS.get(error, "Chưa kết nối được Azure Translator.")
                if error
                else "Đã lưu. Alt+C sử dụng Microsoft Translator."
            )
            if self.mode == "free":
                if ok or imported:
                    self.render_providers()
                else:
                    self.azure_save.set_sensitive(True)
                    self.azure_verify.set_sensitive(
                        self.model.translator_status()["pending"] > 0
                    )
            return GLib.SOURCE_REMOVE

        threading.Thread(target=work, daemon=True).start()

    def toggle(self, pid, value):
        try:
            self.model.toggle(pid, value, self.mode)
            self.inform("Đã lưu cho tác vụ kế tiếp")
        except ValueError:
            self.inform("Cần giữ ít nhất một provider.")
            GLib.idle_add(lambda: (self.render_providers(), False)[1])

    def move(self, pid, delta):
        self.model.move(pid, delta, self.mode)
        self.render_providers()

    def select_model(self, pid, model, mode):
        try:
            self.model.choose(pid, model, mode)
            self.inform("Đã lưu model cho tác vụ kế tiếp")
        except ValueError:
            self.inform("Model chưa được xác minh cho luồng này.")

    def keys(self, page):
        page.append(
            label("Import sẽ gộp và bỏ trùng; giá trị key luôn được che.", "muted")
        )
        actions = Gtk.Box(spacing=8)
        page.append(actions)
        actions.append(button("Nhập .env / TXT", self.import_dialog, "primary"))
        actions.append(button("Xuất TXT", self.export_dialog))
        self.audit_button = button("Kiểm tra key mới · gọi API", self.audit_new)
        actions.append(self.audit_button)
        actions.append(button("Kích hoạt phím tắt", self.enable_extension))
        self.keys_box = self.panel(page)
        self.render_keys()

    def audit_new(self):
        if getattr(self, "audit_running", False):
            return
        self.audit_running = True
        self.audit_button.set_sensitive(False)
        self.inform("Đang kiểm tra key mới…")

        def work():
            try:
                report = self.model.audit_new()
                message = "Đã kiểm tra " + str(len(report["credentials"])) + " key mới."
            except Exception:
                message = "Chưa kiểm tra được key mới. Xem nhật ký."
            GLib.idle_add(done, message)

        def done(message):
            self.audit_running = False
            self.audit_button.set_sensitive(True)
            self.inform(message)
            self.render_keys()
            self.render_providers()
            return GLib.SOURCE_REMOVE

        threading.Thread(target=work, daemon=True).start()

    def enable_extension(self):
        def work():
            try:
                result = subprocess.run(
                    ["gnome-extensions", "enable", "qtranslate@local"],
                    capture_output=True,
                    timeout=5,
                )
                message = (
                    "Đã bật extension."
                    if result.returncode == 0
                    else "Đăng xuất/đăng nhập rồi bật Q Translate trong Extensions."
                )
            except (OSError, subprocess.TimeoutExpired):
                message = "Chưa bật được extension; kiểm tra gói đã cài."
            GLib.idle_add(lambda: (self.inform(message), GLib.SOURCE_REMOVE)[1])

        threading.Thread(target=work, daemon=True).start()

    def render_keys(self):
        child = self.keys_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.keys_box.remove(child)
            child = nxt
        status = self.model.translator_status()
        self.keys_box.append(
            label(
                f"Microsoft Translator   {status['verified']} key đã kiểm tra · {status['pending']} chờ kiểm tra"
            )
        )
        for row in self.model.providers():
            self.keys_box.append(
                label(
                    f"{NAMES[row['id']]}   {row['count']}/{row['total']} key đã xác minh text"
                )
            )
            self.keys_box.append(
                label("   ".join(id[-8:] + " · ••••••••" for id in row["ids"]), "muted")
            )

    def chooser(self, title, save, callback):
        dialog = Gtk.FileChooserNative(
            title=title,
            transient_for=self.window,
            action=Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN,
            accept_label="Lưu" if save else "Nhập",
            cancel_label="Hủy",
        )

        def response(d, result):
            if result == Gtk.ResponseType.ACCEPT:
                file = d.get_file()
                if file and file.get_path():
                    callback(Path(file.get_path()))
            d.destroy()

        dialog.connect("response", response)
        dialog.show()

    def import_dialog(self):
        self.chooser("Nhập key/model", False, self.do_import)

    def do_import(self, path):
        try:
            report = self.model.store.merge(parse_import(path))
            from qtranslate.install import finish_setup

            finish_setup(self.model.settings)
            self.inform(f"Thêm {report.added} · bỏ trùng {report.duplicates}")
            self.render_keys()
            self.render_providers()
        except (OSError, ValueError, KeyError):
            self.inform("Không đọc được file import. Bộ hiện có được giữ nguyên.")

    def export_dialog(self):
        self.chooser(
            "Xuất key/model đã kiểm tra",
            True,
            lambda p: self.model.store.export_verified(p),
        )

    def appearance(self, page):
        settings = self.model.settings.load()
        p = self.panel(page)
        p.append(label("Phím tắt"))
        for action, title in [
            ("translate", "Dịch miễn phí"),
            ("rewrite", "Viết lại & copy"),
            ("image_translate", "Chụp & dịch AI"),
            ("chat", "Q-translate · Chat AI"),
        ]:
            line = Gtk.Box(spacing=12)
            name = label(title)
            name.set_hexpand(True)
            line.append(name)
            entry = Gtk.Entry(text=settings["shortcuts"][action])
            entry.connect(
                "activate", lambda e, a=action: self.save_shortcut(a, e.get_text())
            )
            line.append(entry)
            p.append(line)
        p = self.panel(page)
        line = Gtk.Box(spacing=12)
        name = label("Khởi động cùng máy")
        name.set_hexpand(True)
        line.append(name)
        switch = Gtk.Switch(active=settings["autostart"])
        switch.connect("notify::active", lambda s, _p: self.autostart(s.get_active()))
        line.append(switch)
        p.append(line)
        for text in [
            "Streaming: hiện chữ dần, chỉ copy khi hoàn tất",
            "Alt+V/X: 5 giây/lần gọi AI · chat và cả tác vụ: tối đa 30 giây",
            "Khung Alt+V: tự nới, cuộn, copy lại; tự ẩn sau 30 giây",
            "Bấm ngoài đóng Alt+C/ảnh; Alt+V vẫn giữ",
            "Thinking: tắt · Không đặt giới hạn ký tự",
        ]:
            p.append(label(text, "muted"))
        font = Gtk.SpinButton.new_with_range(14, 26, 1)
        font.set_value(settings["font_size"])
        font.connect(
            "value-changed",
            lambda w: self.save_setting("font_size", int(w.get_value())),
        )
        p.append(label("Cỡ chữ kết quả"))
        p.append(font)

    def save_setting(self, key, value):
        settings = self.model.settings.load()
        settings[key] = value
        self.model.settings.save(settings)

    def save_shortcut(self, action, value):
        valid, keyval, mod = Gtk.accelerator_parse(value)
        if not valid or not keyval:
            self.inform("Phím tắt không hợp lệ.")
            return
        settings = self.model.settings.load()
        settings["shortcuts"][action] = value
        self.model.settings.save(settings)
        try:
            if action == "chat":
                from qtranslate.desktop.shortcuts import install_chat_shortcut

                self.inform(
                    "Đã đổi phím tắt chat"
                    if install_chat_shortcut(value)
                    else "Chưa đăng ký được phím tắt chat."
                )
                return
            schema = Gio.SettingsSchemaSource.get_default().lookup(
                "org.qtranslate.desktop", True
            )
            if schema is None:
                self.inform("Đã lưu. Cài extension để áp dụng phím tắt.")
                return
            Gio.Settings.new_full(schema, None, None).set_strv(
                action.replace("_", "-"), [value]
            )
            self.inform("Đã đổi phím tắt")
        except GLib.Error:
            self.inform("Đã lưu; extension chưa được cài để áp dụng.")

    def autostart(self, enabled):
        from qtranslate.install import set_autostart

        try:
            set_autostart(enabled)
            self.save_setting("autostart", enabled)
            self.inform("Đã lưu autostart")
        except OSError:
            self.inform("Chưa ghi được cài đặt autostart.")

    def prompts(self, page):
        page.append(
            label(
                "Giữ đủ ý, dùng tiếng Anh giao tiếp đơn giản. Prompt ảnh độc lập.",
                "muted",
            )
        )
        for key, title in [
            ("prompt_text", "Alt+V · Tiếng Anh giao tiếp"),
            ("prompt_vision", "Alt+X · Dịch ảnh"),
            ("prompt_chat", "Alt+D · Q-translate · Trả lời ngắn gọn"),
        ]:
            p = self.panel(page)
            p.append(label(title))
            view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
            view.get_buffer().set_text(self.model.settings.load()[key])
            view.set_size_request(-1, 170)
            p.append(view)

            def save(v=view, k=key):
                buf = v.get_buffer()
                self.save_setting(k, buf.get_text(*buf.get_bounds(), True))
                self.inform("Đã lưu prompt")

            p.append(button("Lưu prompt", save))
            p.append(
                button(
                    "Khôi phục mặc định",
                    lambda v=view, k=key: v.get_buffer().set_text(defaults()[k]),
                )
            )

    def logs(self, page):
        page.append(
            label("Input, output và lỗi · tự clear mỗi 24 giờ · không lưu ảnh", "muted")
        )
        row = Gtk.Box(spacing=8)
        page.append(row)
        row.append(button("Làm mới", self.refresh_logs))
        row.append(button("Xóa log", self.clear_logs))
        self.log_view = Gtk.TextView(
            editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR, vexpand=True
        )
        self.panel(page).append(self.log_view)
        self.refresh_logs()

    def refresh_logs(self):
        try:
            text = (self.state_dir / "q-translate.log").read_text()
        except OSError:
            text = "Chưa có nhật ký."
        self.log_view.get_buffer().set_text(text)

    def clear_logs(self):
        RuntimeLog(
            self.state_dir / "q-translate.log", self.model.store.all_secrets
        ).clear()
        self.refresh_logs()

    def stop_backend(self):
        try:
            Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
                "org.qtranslate.App",
                "/org/qtranslate/App",
                "org.qtranslate.App1",
                "Stop",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
        except GLib.Error:
            pass
        self.quit()


def run_dashboard(smoke=False):
    if not Gtk.init_check():
        print("Cần phiên desktop để mở dashboard.", file=sys.stderr)
        return 2
    if not smoke:
        try:
            Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
                "org.qtranslate.App",
                "/org/qtranslate/App",
                "org.qtranslate.App1",
                "Capabilities",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
        except GLib.Error:
            subprocess.Popen(
                [sys.executable, "-m", "qtranslate", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    return Dashboard(smoke).run(["qtranslate-settings"])
