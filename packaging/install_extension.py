import os, json, shutil, subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "extension/qtranslate@local"
data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
dest = data / "gnome-shell/extensions/qtranslate@local"
version = (
    subprocess.check_output(["gnome-shell", "--version"], text=True)
    .split()[-1]
    .split(".")[0]
)
if version not in json.loads((source / "metadata.json").read_text())["shell-version"]:
    raise SystemExit(
        "GNOME version not yet runtime-validated; extension not installed."
    )
dest.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(
    source,
    dest,
    dirs_exist_ok=True,
    ignore=shutil.ignore_patterns("tests", "package.json"),
)
subprocess.run(["glib-compile-schemas", "--strict", str(dest / "schemas")], check=True)
result = subprocess.run(
    ["gnome-extensions", "enable", "qtranslate@local"], capture_output=True, text=True
)
print(
    "Extension installed."
    if result.returncode == 0
    else "Extension installed; log out/in, then enable Q Translate in Extensions."
)
