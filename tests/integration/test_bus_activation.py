"""A cancellation must not resurrect the packaged activatable service."""

import os, subprocess, tempfile, unittest
from pathlib import Path


class ActivationTests(unittest.TestCase):
    def test_no_auto_start_leaves_service_inactive(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            services = root / "data/dbus-1/services"
            services.mkdir(parents=True)
            marker = root / "activated"
            script = root / "service.sh"
            script.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
            script.chmod(0o755)
            (services / "org.qtranslate.App.service").write_text(
                "[D-BUS Service]\nName=org.qtranslate.App\nExec=" + str(script) + "\n"
            )
            code = """from gi.repository import Gio,GLib
c=Gio.bus_get_sync(Gio.BusType.SESSION,None)
try:c.call_sync('org.qtranslate.App','/org/qtranslate/App','org.qtranslate.App1','Cancel',GLib.Variant('(s)',['old']),None,Gio.DBusCallFlags.NO_AUTO_START,1000,None)
except GLib.Error:pass
"""
            env = {**os.environ, "XDG_DATA_HOME": str(root / "data")}
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
            self.assertFalse(marker.exists())
