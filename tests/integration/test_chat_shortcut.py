import os
import subprocess
import tempfile
import unittest


class ChatShortcutTests(unittest.TestCase):
    def test_registration_is_idempotent_preserves_unrelated_and_updates_binding(self):
        code = """
from gi.repository import Gio
from qtranslate.desktop.shortcuts import install_chat_shortcut, CHAT_PATH
main=Gio.Settings.new('org.gnome.settings-daemon.plugins.media-keys')
other='/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/existing/'
main.set_strv('custom-keybindings',[other])
assert install_chat_shortcut('<Alt>d',command='/tmp/a path/qtranslate')
assert install_chat_shortcut('<Alt>d',command='/tmp/a path/qtranslate')
assert main.get_strv('custom-keybindings')==[other,CHAT_PATH]
item=Gio.Settings.new_with_path('org.gnome.settings-daemon.plugins.media-keys.custom-keybinding',CHAT_PATH)
assert item.get_string('binding')=='<Alt>d'
import shlex
assert shlex.split(item.get_string('command'))==['/tmp/a path/qtranslate','chat']
assert install_chat_shortcut('<Super>d',command='/tmp/qtranslate')
assert item.get_string('binding')=='<Super>d'
print('CHAT_SHORTCUT_PASS')
"""
        with tempfile.TemporaryDirectory() as d:
            env = {
                **os.environ,
                "PYTHONPATH": "src",
                "GSETTINGS_BACKEND": "memory",
                "XDG_CACHE_HOME": d,
            }
            r = subprocess.run(
                ["/usr/bin/python3", "-c", code],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("CHAT_SHORTCUT_PASS", r.stdout)
