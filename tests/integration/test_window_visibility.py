import os
import subprocess
import tempfile
import unittest


class WindowVisibilityTests(unittest.TestCase):
    def test_chat_and_settings_skip_dock_after_open_and_reopen(self):
        code = """
import subprocess
from qtranslate.ui.chat import ChatApp,GLib
from qtranslate.ui.dashboard import Dashboard
from qtranslate.tasks.types import TaskResult
from gi.repository import GdkX11
app=ChatApp(runner=lambda req,*args:TaskResult(req.id,'chat','success','OK'))
app.register(None);app.activate()
dashboard=Dashboard();dashboard.register(None);dashboard.activate()
def flags(window):
 surface=window.get_surface()
 assert isinstance(surface,GdkX11.X11Surface)
 return subprocess.run(['xprop','-id',str(surface.get_xid()),'_NET_WM_STATE'],capture_output=True,text=True,check=True).stdout
def inspect():
 for window in [app.window,dashboard.window]:
  state=flags(window)
  assert '_NET_WM_STATE_SKIP_TASKBAR' in state,state
  assert '_NET_WM_STATE_SKIP_PAGER' in state,state
 app.input.get_buffer().set_text('Draft kept')
 app.hide_chat();app.activate()
 assert app.session.draft=='Draft kept'
 assert '_NET_WM_STATE_SKIP_TASKBAR' in flags(app.window)
 app.close_chat();dashboard.window.destroy();dashboard.quit()
 print('TRAY_ONLY_PASS');loop.quit();return False
loop=GLib.MainLoop();GLib.timeout_add(200,inspect)
GLib.timeout_add_seconds(4,lambda:(loop.quit(),False)[1]);loop.run()
"""
        with tempfile.TemporaryDirectory() as d:
            env = {
                **os.environ,
                "PYTHONPATH": "src",
                "XDG_CONFIG_HOME": d + "/config",
                "XDG_STATE_HOME": d + "/state",
                "XDG_CACHE_HOME": d + "/cache",
                "GSETTINGS_BACKEND": "memory",
                "GTK_A11Y": "none",
            }
            r = subprocess.run(
                [
                    "timeout",
                    "8s",
                    "xvfb-run",
                    "-a",
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
            self.assertIn("TRAY_ONLY_PASS", r.stdout, r.stderr)
