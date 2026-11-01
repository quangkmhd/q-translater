"""User setup and an allowlisted package manifest; no secret files are packaged."""

import os
from pathlib import Path


def set_autostart(enabled, config_home=None):
    root = Path(
        config_home or os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    )
    path = root / "autostart" / "org.qtranslate.App.desktop"
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\nType=Application\nName=Q Translate\nExec=qtranslate serve\nTerminal=false\nX-GNOME-Autostart-enabled=true\n"
        )
    else:
        path.unlink(missing_ok=True)
    return path


def package_files(root):
    root = Path(root)
    files = list((root / "src/qtranslate").rglob("*.py"))
    files += [
        p
        for p in (root / "extension/qtranslate@local").rglob("*")
        if p.is_file()
        and p.suffix in (".js", ".css", ".json", ".xml", ".svg")
        and "tests" not in p.parts
        and p.name != "package.json"
    ]
    files += list((root / "data").glob("*.desktop")) + list(
        (root / "data").glob("*.service")
    )
    return sorted(files)


def finish_setup(settings_store, config_home=None):
    """Complete the first successful import without resetting later preferences."""
    settings = settings_store.load()
    if settings.get("setup_complete"):
        return
    set_autostart(settings.get("autostart", True), config_home)
    settings["setup_complete"] = True
    settings_store.save(settings)
