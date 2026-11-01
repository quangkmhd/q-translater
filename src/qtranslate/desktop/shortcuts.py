"""GNOME owns the global shortcut, including on Wayland; no input injection."""

import shutil
from pathlib import Path
from gi.repository import Gio, GLib

CHAT_PATH = (
    "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/qtranslate-chat/"
)


def install_chat_shortcut(binding="<Alt>d", command=None):
    source = Gio.SettingsSchemaSource.get_default()
    main_schema = source.lookup("org.gnome.settings-daemon.plugins.media-keys", True)
    item_schema = source.lookup(
        "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding", True
    )
    if not main_schema or not item_schema:
        return False
    if command is None:
        local = Path.home() / ".local/bin/qtranslate"
        command = str(local) if local.is_file() else shutil.which("qtranslate")
    if not command:
        return False
    main = Gio.Settings.new_full(main_schema, None, None)
    item = Gio.Settings.new_full(item_schema, None, CHAT_PATH)
    if not all(item.is_writable(k) for k in ("name", "command", "binding")):
        return False
    if not main.is_writable("custom-keybindings"):
        return False
    values = {
        "name": "Q-translate · Chat AI",
        "command": GLib.shell_quote(command) + " chat",
        "binding": binding,
    }
    for key, value in values.items():
        if not item.set_string(key, value):
            return False
    paths = main.get_strv("custom-keybindings")
    if CHAT_PATH not in paths and not main.set_strv(
        "custom-keybindings", [*paths, CHAT_PATH]
    ):
        return False
    Gio.Settings.sync()
    return True
