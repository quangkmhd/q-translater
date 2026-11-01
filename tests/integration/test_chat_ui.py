import os
import subprocess
import tempfile
import unittest


class NativeChatTests(unittest.TestCase):
    def test_hidpi_window_stays_on_screen_after_growing_for_long_reply(self):
        code = """
import subprocess,re
from qtranslate.ui.chat import ChatApp,GLib
from qtranslate.tasks.types import TaskResult
def runner(req,settings,deadline,cancel,update):
 return TaskResult(req.id,'chat','success','Long answer.\\n'*100)
app=ChatApp(runner=runner);app.register(None);app.activate()
app.input.get_buffer().set_text('Long answer please');app.send();loop=GLib.MainLoop()
def check():
 if app.session.active_id:return True
 GLib.timeout_add(250,measure);return False
def measure():
 surface=app.window.get_surface();scale=surface.get_scale_factor()
 rect=surface.get_display().get_monitor_at_surface(surface).get_geometry()
 text=subprocess.run(['xwininfo','-id',str(surface.get_xid())],capture_output=True,text=True,check=True).stdout
 def value(name):return int(re.search(name+r':\\s+(-?\\d+)',text)[1])
 x=value('Absolute upper-left X');y=value('Absolute upper-left Y')
 width=value('Width');height=value('Height')
 assert x+width<=(rect.x+rect.width)*scale-20,(x,width,rect.width,scale)
 assert y+height<=(rect.y+rect.height)*scale-20,(y,height,rect.height,scale)
 assert abs(x+width-((rect.x+rect.width)*scale-22*scale))<=2
 assert app.input.get_mapped() and app.send_button.get_mapped()
 a=app.scroll.get_vadjustment();assert a.get_upper()>a.get_page_size()
 print('HIDPI_LAYOUT_PASS');app.close_chat();loop.quit();return False
GLib.timeout_add(20,check);GLib.timeout_add_seconds(5,lambda:(loop.quit(),False)[1]);loop.run()
"""
        self.run_script(code, "HIDPI_LAYOUT_PASS", scale="2")

    def test_process_close_waits_for_transport_cleanup(self):
        code = """
import os,sys,time,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
from qtranslate.ui.chat import ChatApp,GLib
from qtranslate.providers.http import request_stream
from qtranslate.tasks.types import TaskResult
tmp=tempfile.TemporaryDirectory();root=Path(tmp.name);children=[]
real_popen=subprocess.Popen
def sleeping_transport(*args,**kwargs):
 child=real_popen([sys.executable,'-c','import time;time.sleep(30)'],**kwargs)
 children.append(child)
 return child
def runner(req,settings,deadline,cancel,update):
 class TransportCancel:
  def is_set(self):
   value=cancel.is_set()
   if value:time.sleep(.4)
   return value
 try:
  with patch('qtranslate.providers.http.subprocess.Popen',side_effect=sleeping_transport):
   request_stream('https://api.cloudflare.com/fixture',{}, {},deadline,TransportCancel(),lambda e:None)
 finally:(root/'cleaned').write_text('done')
 return TaskResult(req.id,'chat','cancelled')
app=ChatApp(runner=runner)
def send():
 app.input.get_buffer().set_text('Synthetic close test');app.send()
 return False
def close_when_started():
 if not children:return True
 app.close_chat();return False
GLib.timeout_add(100,send);GLib.timeout_add(10,close_when_started)
app.run(['chat-close-test'])
cleaned=(root/'cleaned').exists()
if not cleaned and children[0].poll() is None:
 children[0].kill();children[0].wait()
assert cleaned,'App exited before transport cleanup'
assert children[0].poll() is not None,'Transport child was orphaned'
assert app.session.history==[] and app.session.turns==[]
print('CHAT_PROCESS_CLEANUP_PASS')
"""
        self.run_script(code, "CHAT_PROCESS_CLEANUP_PASS")

    def test_real_widgets_stream_hide_reopen_clear_and_close(self):
        code = """
import time, threading
from qtranslate.ui.chat import ChatApp, Gtk, GLib
from qtranslate.tasks.types import TaskResult
requests=[]
def runner(request,settings,deadline,cancel,update):
 requests.append(request)
 update(TaskResult(request.id,'chat','streaming','Short'))
 return TaskResult(request.id,'chat','success','Short answer.')
app=ChatApp(runner=runner)
assert app.register(None)
app.activate()
clip=app.window.get_display().get_clipboard();clip.set('Original clipboard')
original_provider=clip.get_content()
def spin_until(check):
 loop=GLib.MainLoop()
 def poll():
  if check():loop.quit();return False
  return True
 poll_id=GLib.timeout_add(10,poll)
 timeout=GLib.timeout_add(4000,lambda:(loop.quit(),False)[1])
 loop.run()
 if check():GLib.source_remove(timeout)
 else:GLib.source_remove(poll_id)
 assert check(),repr((app.session.history, app.session.turns, requests))
def put(text):app.input.get_buffer().set_text(text)
put('My name is Linh.')
app.send()
spin_until(lambda:len(app.session.history)==2)
assert app.session.history[-1]['content']=='Short answer.'
assert app.rows[requests[0].id]['copy'].get_sensitive()
assert clip.get_content()==original_provider,'Chat overwrote clipboard automatically'
app.copy_reply(requests[0].id)
copied=[]
clip.read_text_async(None,lambda c,r:copied.append(c.read_text_finish(r)))
spin_until(lambda:bool(copied))
assert copied==['Short answer.']
answer=app.rows[requests[0].id]['answer']
answer.select_region(6,12)
app.copy_reply(requests[0].id);copied.clear()
clip.read_text_async(None,lambda c,r:copied.append(c.read_text_finish(r)))
spin_until(lambda:bool(copied))
assert copied==['answer'],'Copy icon ignored selected substring'
copied.clear();answer.emit('copy-clipboard')
clip.read_text_async(None,lambda c,r:copied.append(c.read_text_finish(r)))
spin_until(lambda:bool(copied));assert copied==['answer']
put('Unsent draft')
session_id=app.session.session_id
app.hide_chat()
assert not app.window.get_visible()
app.activate()
assert app.window.get_visible() and app.session.session_id==session_id
buf=app.input.get_buffer();assert buf.get_text(*buf.get_bounds(),True)=='Unsent draft'
put('What is my name?');app.send()
spin_until(lambda:len(app.session.history)==4)
assert len(requests[-1].messages)==3
assert requests[-1].messages[0]['content']=='My name is Linh.'
app.new_chat();assert app.session.history==[] and app.rows=={}
assert app.session.session_id!=session_id
put('Another question');app.send();spin_until(lambda:len(app.session.history)==2)
app.close_chat()
assert not app.session.history and not app.session.turns and not app.rows
assert app.window is None
print('CHAT_WIDGETS_PASS')
"""
        self.run_script(code, "CHAT_WIDGETS_PASS")

    def test_hiding_does_not_cancel_but_closing_invalidates_late_stream(self):
        code = """
import time,threading
from qtranslate.ui.chat import ChatApp, GLib
from qtranslate.tasks.types import TaskResult
release=threading.Event();started=threading.Event();cancelled=[]
def runner(req,settings,deadline,cancel,update):
 started.set();release.wait(3);cancelled.append(cancel.is_set())
 update(TaskResult(req.id,'chat','streaming','Late'))
 return TaskResult(req.id,'chat','success','Late')
app=ChatApp(runner=runner);app.register(None);app.activate()
app.input.get_buffer().set_text('Pending question');app.send();assert started.wait(1)
id=app.session.active_id;app.hide_chat();assert app.session.active_id==id
app.close_chat();release.set()
end=time.monotonic()+1
while time.monotonic()<end:
 GLib.MainContext.default().iteration(False);time.sleep(.01)
assert cancelled==[True]
assert app.session.history==[] and app.session.turns==[] and app.rows=={}
print('CHAT_CANCEL_PASS')
"""
        self.run_script(code, "CHAT_CANCEL_PASS")

    def run_script(self, code, marker, scale="1"):
        with tempfile.TemporaryDirectory() as d:
            env = {
                **os.environ,
                "PYTHONPATH": "src",
                "XDG_CONFIG_HOME": d + "/config",
                "XDG_STATE_HOME": d + "/state",
                "XDG_CACHE_HOME": d + "/cache",
                "GTK_A11Y": "none",
                "GDK_SCALE": scale,
            }
            r = subprocess.run(
                [
                    "timeout",
                    "12s",
                    "xvfb-run",
                    "-a",
                    "-s",
                    "-screen 0 1920x1080x24",
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
            self.assertIn(marker, r.stdout)
