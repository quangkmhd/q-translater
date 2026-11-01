import argparse, os, shutil, subprocess, tempfile
from pathlib import Path
from qtranslate.install import package_files

p = argparse.ArgumentParser()
p.add_argument("--output", default="dist/q-translate.deb")
args = p.parse_args()
root = Path(__file__).resolve().parents[1]
out = (root / args.output).resolve()
out.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="qtranslate-build-") as tmp:
    stage = Path(tmp)
    for source in package_files(root):
        rel = source.relative_to(root)
        if rel.parts[0] == "src":
            dest = stage / "usr/lib/q-translate" / Path(*rel.parts[1:])
        elif rel.parts[0] == "extension":
            dest = stage / "usr/share/gnome-shell/extensions" / Path(*rel.parts[1:])
        elif source.suffix == ".desktop":
            dest = stage / "usr/share/applications" / source.name
        else:
            dest = stage / "usr/share/dbus-1/services" / source.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        dest.chmod(0o644)
    schema = stage / "usr/share/glib-2.0/schemas/org.qtranslate.desktop.gschema.xml"
    schema.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        root / "extension/qtranslate@local/schemas/org.qtranslate.desktop.gschema.xml",
        schema,
    )
    subprocess.run(
        [
            "glib-compile-schemas",
            "--strict",
            str(stage / "usr/share/gnome-shell/extensions/qtranslate@local/schemas"),
        ],
        check=True,
    )
    launcher = stage / "usr/bin/qtranslate"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(
        '#!/usr/bin/python3\nimport sys\nsys.path.insert(0,"/usr/lib/q-translate")\nfrom qtranslate.__main__ import main\nraise SystemExit(main())\n'
    )
    launcher.chmod(0o755)
    control = stage / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        "Package: q-translate\nVersion: 0.1.0\nArchitecture: all\nMaintainer: Q Translate\nDepends: python3 (>= 3.12), python3-gi, gir1.2-gtk-4.0, gnome-shell (>= 46), curl (>= 7.84), hunspell-en-us, libxres1, xwayland\nSection: utils\nPriority: optional\nDescription: English/Vietnamese translation for Ubuntu GNOME\n Desktop integration candidate; GNOME 46 still requires runtime validation.\n"
    )
    for name in ["postinst", "postrm"]:
        script = control / name
        script.write_text(
            "#!/bin/sh\nset -e\nif command -v glib-compile-schemas >/dev/null; then glib-compile-schemas /usr/share/glib-2.0/schemas; fi\n"
        )
        script.chmod(0o755)
    subprocess.run(
        ["dpkg-deb", "--root-owner-group", "--build", str(stage), str(out)], check=True
    )
print(out)
