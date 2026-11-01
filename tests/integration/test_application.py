import subprocess
import tempfile
import unittest
import os
from pathlib import Path


class ApplicationTests(unittest.TestCase):
    def test_shortcut_setup_waits_until_runtime_ipc_is_registered(self):
        code = """
from gi.repository import Gio,GLib
from unittest.mock import patch
from qtranslate.app import Runtime
calls=[]
with patch('qtranslate.desktop.shortcuts.install_chat_shortcut',side_effect=lambda binding:(calls.append(binding),True)[1]):
 r=Runtime(Gio.bus_get_sync(Gio.BusType.SESSION,None),lambda:None)
 assert calls==[],'Desktop settings setup ran before startup returned'
 loop=GLib.MainLoop()
 def check():
  if calls:loop.quit();return False
  return True
 GLib.timeout_add(10,check);GLib.timeout_add_seconds(2,lambda:(loop.quit(),False)[1]);loop.run()
 assert calls==['<Alt>d']
 r.close()
print('SHORTCUT_AFTER_STARTUP')
"""
        with tempfile.TemporaryDirectory() as d:
            env = {
                **os.environ,
                "PYTHONPATH": "src",
                "XDG_CONFIG_HOME": d + "/config",
                "XDG_STATE_HOME": d + "/state",
                "GSETTINGS_BACKEND": "memory",
            }
            r = subprocess.run(
                [
                    "timeout",
                    "5s",
                    "dbus-run-session",
                    "--",
                    "/usr/bin/python3",
                    "-c",
                    code,
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("SHORTCUT_AFTER_STARTUP", r.stdout)

    def test_cli_help_does_not_require_display(self):
        r = subprocess.run(
            ["/usr/bin/python3", "-m", "qtranslate", "--help"],
            env={**os.environ, "PYTHONPATH": "src"},
            text=True,
            capture_output=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("settings", r.stdout)

    def test_import_cli_merges_without_printing_secrets(self):
        from tests.unit.test_import_merge import bundle, KEY
        import json

        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "keys.txt"
            f.write_text(json.dumps(bundle()))
            env = {
                **os.environ,
                "PYTHONPATH": "src",
                "XDG_CONFIG_HOME": str(Path(d) / "config"),
            }
            for expected in ["2", "0"]:
                r = subprocess.run(
                    [
                        "/usr/bin/python3",
                        "-m",
                        "qtranslate",
                        "import",
                        "--file",
                        str(f),
                    ],
                    env=env,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertNotIn(KEY, r.stdout + r.stderr)
                self.assertIn("added", r.stdout)

    def test_backend_lifecycle_on_private_bus(self):
        script = """set -eu
/usr/bin/python3 -m qtranslate serve > "$QT_TEST_LOGDIR/service.log" 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
gdbus wait --session --timeout 6 org.qtranslate.App
/usr/bin/python3 -m qtranslate status
/usr/bin/python3 -m qtranslate quit
wait "$pid"
"""
        with tempfile.TemporaryDirectory() as d:
            env = {
                **os.environ,
                "PYTHONPATH": "src",
                "XDG_CONFIG_HOME": d + "/config",
                "XDG_STATE_HOME": d + "/state",
                "QT_TEST_LOGDIR": d,
            }
            r = subprocess.run(
                ["timeout", "10s", "dbus-run-session", "--", "sh", "-c", script],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('"backend": true', r.stdout)

    def test_runtime_constructs_and_closes_on_private_bus(self):
        code = 'from gi.repository import Gio;from qtranslate.app import Runtime;r=Runtime(Gio.bus_get_sync(Gio.BusType.SESSION,None),lambda:None);r.close();print("RUNTIME_READY")'
        with tempfile.TemporaryDirectory() as d:
            env = {
                **os.environ,
                "PYTHONPATH": "src",
                "XDG_CONFIG_HOME": d + "/config",
                "XDG_STATE_HOME": d + "/state",
            }
            r = subprocess.run(
                [
                    "timeout",
                    "8s",
                    "dbus-run-session",
                    "--",
                    "/usr/bin/python3",
                    "-c",
                    code,
                ],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("RUNTIME_READY", r.stdout)

    def test_parallel_cli_imports_preserve_all_credentials(self):
        from tests.unit.test_import_merge import bundle
        import json

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            env = {
                **os.environ,
                "PYTHONPATH": "src",
                "XDG_CONFIG_HOME": str(root / "config"),
            }
            jobs = []
            for n in range(6):
                b = bundle()
                for c in b["providers"][0]["credentials"]:
                    c["key"] += str(n)
                source = root / f"keys{n}.txt"
                source.write_text(json.dumps(b))
                jobs.append(
                    subprocess.Popen(
                        [
                            "/usr/bin/python3",
                            "-m",
                            "qtranslate",
                            "import",
                            "--file",
                            str(source),
                        ],
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                )
            for job in jobs:
                out, err = job.communicate(timeout=8)
                self.assertEqual(job.returncode, 0, err.decode())
            data = json.loads(
                (root / "config/q-translate/credentials.json").read_text()
            )
            self.assertEqual(len(data["providers"][0]["credentials"]), 12)

    def test_status_without_backend_reports_friendly_error(self):
        r = subprocess.run(
            [
                "dbus-run-session",
                "--",
                "/usr/bin/python3",
                "-m",
                "qtranslate",
                "status",
            ],
            env={**os.environ, "PYTHONPATH": "src"},
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)
