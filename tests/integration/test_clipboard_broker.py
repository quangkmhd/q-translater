import os
import subprocess
import tempfile
import unittest


class ClipboardBrokerTests(unittest.TestCase):
    def test_new_user_copy_is_preserved_instead_of_restoring_old_snapshot(self):
        code = """
from qtranslate.desktop.clipboard import ClipboardBroker,Gdk,GLib
b=ClipboardBroker();loop=GLib.MainLoop();errors=[]
def put(text):b.clip.set_content(Gdk.ContentProvider.new_for_bytes('text/plain;charset=utf-8',GLib.Bytes.new(text)))
put(b'Original')
def saved(token,error):
 if error:errors.append(error);loop.quit();return
 put(b'Selected from Codex');put(b'New user clipboard')
 def finished(text,error):
  if error!='CLIPBOARD_CHANGED':errors.append('Expected interference rejection')
  def read(c,r):
   if c.read_text_finish(r)!='New user clipboard':errors.append('Overwrote user clipboard')
   loop.quit()
  b.clip.read_text_async(None,read)
 b.finish(token,finished)
b.snapshot(saved);GLib.timeout_add_seconds(4,lambda:(errors.append('TIMEOUT'),loop.quit(),False)[2]);loop.run()
assert not errors,errors
print('CLIPBOARD_RESTORED')
"""
        self.run_clipboard_script(code)

    def test_single_unrelated_copy_is_rejected_without_overwriting_it(self):
        code = """
from qtranslate.desktop.clipboard import ClipboardBroker,Gdk,GLib
import os
b=ClipboardBroker();loop=GLib.MainLoop();errors=[]
def put(text):b.clip.set_content(Gdk.ContentProvider.new_for_bytes('text/plain;charset=utf-8',GLib.Bytes.new(text)))
put(b'Original')
def saved(token,error):
 put(b'Unrelated user copy')
 def finished(text,error):
  if text is not None or error!='CLIPBOARD_CHANGED':errors.append('Accepted unrelated source')
  def read(c,r):
   if c.read_text_finish(r)!='Unrelated user copy':errors.append('Overwrote user clipboard')
   loop.quit()
  b.clip.read_text_async(None,read)
 b.finish(token,finished,expected_pid=os.getpid()+100000)
b.snapshot(saved);GLib.timeout_add_seconds(4,lambda:(errors.append('TIMEOUT'),loop.quit(),False)[2]);loop.run()
assert not errors,errors
print('CLIPBOARD_RESTORED')
"""
        self.run_clipboard_script(code)

    def test_lost_copy_acknowledgement_still_restores_original_clipboard(self):
        code = """
from qtranslate.desktop.clipboard import ClipboardBroker,Gdk,GLib
from qtranslate.desktop import tui_selection as tui
from unittest.mock import patch
import os
b=ClipboardBroker();loop=GLib.MainLoop();errors=[]
b.clip.set_content(Gdk.ContentProvider.new_for_bytes('text/html',GLib.Bytes.new(b'<b>Original</b>')))
reader=tui.TuiSelectionReader();reader.broker=b
terminal={'handle':'selected','agentIdentity':'codex','preview':'^c copy · enter copy & follow · esc clear'}
def cli(args):
 def apply():
  b.clip.set_content(Gdk.ContentProvider.new_for_bytes('text/plain;charset=utf-8',GLib.Bytes.new(b'Selected Codex text')))
  return False
 GLib.idle_add(apply)
 raise TimeoutError('acknowledgement lost after copy was applied')
def done(result):
 if result.get('text')!='Selected Codex text':errors.append('Confirmed copy was lost')
 def restored(token,error):
  if error or b.saved[token]['formats']!={'text/html':b'<b>Original</b>'}:errors.append('Original rich clipboard lost')
  loop.quit()
 b.snapshot(restored)
with patch.object(tui,'profile',return_value=terminal),patch.object(tui,'codex_pid',return_value=os.getpid()),patch.object(tui,'cli',side_effect=cli):
 reader.read({'id':'test','action':'rewrite'},done)
 GLib.timeout_add_seconds(4,lambda:(errors.append('TIMEOUT'),loop.quit(),False)[2]);loop.run()
assert not errors,errors
print('CLIPBOARD_RESTORED')
"""
        self.run_clipboard_script(code)

    def test_binary_and_html_clipboard_restored_after_selected_text_read(self):
        code = """
from qtranslate.desktop.clipboard import ClipboardBroker,Gdk,GLib
b=ClipboardBroker();loop=GLib.MainLoop();errors=[]
original={'text/html':b'<b>Original</b>','image/png':b'\\x00PNG binary\\xff'}
b.clip.set_content(Gdk.ContentProvider.new_union([Gdk.ContentProvider.new_for_bytes(k,GLib.Bytes.new(v)) for k,v in original.items()]))
def saved(token,error):
 if error:errors.append(error);loop.quit();return
 import subprocess
 process=subprocess.Popen(['xclip','-quiet','-selection','clipboard','-in'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 process.stdin.write(b'Selected TUI text');process.stdin.close()
 def copied(text,error):
  if text!='Selected TUI text' or error:errors.append(str(error))
  if set(b.clip.get_formats().get_mime_types())!=set(original):errors.append('Lost original MIME formats')
  def restored(token,error):
   if error or b.saved[token]['formats']!=original:errors.append('Original MIME bytes changed')
   if token:b.discard(token)
   loop.quit()
  b.snapshot(restored)
 def offered():
  if not b.clip.get_formats().get_mime_types():return True
  b.finish(token,copied,expected_pid=process.pid)
  return False
 GLib.timeout_add(20,offered)
b.snapshot(saved);GLib.timeout_add_seconds(4,lambda:(errors.append('TIMEOUT'),loop.quit(),False)[2]);loop.run()
assert not errors,errors
print('CLIPBOARD_RESTORED')
"""
        self.run_clipboard_script(code)

    def test_codex_composer_selection_without_transcript_footer_is_read(self):
        self.run_codex_composer_copy(selected=True)

    def test_codex_composer_without_selection_never_returns_stale_clipboard(self):
        self.run_codex_composer_copy(selected=False)

    def run_codex_composer_copy(self, selected):
        code = """
from qtranslate.desktop.clipboard import ClipboardBroker,Gdk,GLib
from qtranslate.desktop import tui_selection as tui
from unittest.mock import patch
import os
b=ClipboardBroker();loop=GLib.MainLoop();errors=[];calls=[]
b.clip.set_content(Gdk.ContentProvider.new_for_bytes('text/html',GLib.Bytes.new(b'<b>Old unrelated clipboard</b>')))
reader=tui.TuiSelectionReader();reader.broker=b
terminal={'handle':'composer','agentIdentity':'codex','preview':'› Unsent prompt text\\n  gpt-6.1-sol · 100% context left'}
def cli(args):
 calls.append(args)
 if args!=['terminal','send','--terminal','composer','--text',tui.CODEX_COPY]:
  raise AssertionError('Unexpected terminal input')
 if SELECTED:
  def apply():
   b.clip.set_content(Gdk.ContentProvider.new_for_bytes('text/plain;charset=utf-8',GLib.Bytes.new(b'Selected prompt substring')))
   return False
  GLib.idle_add(apply)
 return {}
def done(result):
 expected={'text':'Selected prompt substring'} if SELECTED else {'error':'NO_SELECTION'}
 if result!=expected:errors.append(f'{result!r} != {expected!r}')
 if len(calls)!=1:errors.append('Safe selection copy was not attempted exactly once')
 def restored(token,error):
  if error or b.saved[token]['formats']!={'text/html':b'<b>Old unrelated clipboard</b>'}:errors.append('Original clipboard changed')
  if token:b.discard(token)
  loop.quit()
 b.snapshot(restored)
with patch.object(tui,'profile',return_value=terminal),patch.object(tui,'codex_pid',return_value=os.getpid()),patch.object(tui,'cli',side_effect=cli):
 reader.read({'id':'composer-test','action':'rewrite'},done)
 GLib.timeout_add_seconds(4,lambda:(errors.append('TIMEOUT'),loop.quit(),False)[2]);loop.run()
assert not errors,errors
print('CLIPBOARD_RESTORED')
"""
        self.run_clipboard_script("SELECTED = " + repr(selected) + "\n" + code)

    def run_clipboard_script(self, code):
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
            self.assertIn("CLIPBOARD_RESTORED", r.stdout)
