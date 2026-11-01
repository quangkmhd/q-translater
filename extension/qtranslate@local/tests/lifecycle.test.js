import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
function fixture(){
 const callbacks=[],captures=[],writes=[],calls=[],deleted=[],submitted=[],timers=new Map();let n=0;
 const window={get_stable_sequence:()=>1,get_wm_class:()=>'',get_monitor:()=>0};
 const clipboard={get_text:(_type,cb)=>callbacks.push(cb),set_text:(_type,text)=>writes.push(text)};
 const Gio={DBus:{session:{call:(...args)=>calls.push(args)}},DBusCallFlags:{NONE:0,NO_AUTO_START:1},File:{new_for_path:path=>({delete:()=>deleted.push(path)})}};
 const GLib={PRIORITY_DEFAULT:0,SOURCE_REMOVE:false,get_monotonic_time:()=>1000000,timeout_add:(_priority,delay,callback)=>{const id=++n;timers.set(id,{delay,callback});return id;},source_remove:id=>timers.delete(id),uuid_string_random:()=>String(++n),Variant:class{constructor(type,value){this.value=value;}}};
 const context={Gio,GLib,St:{Clipboard:{get_default:()=>clipboard},ClipboardType:{PRIMARY:0,CLIPBOARD:1}},global:{display:{focus_window:window},get_pointer:()=>[0,0]},Main:{layoutManager:{primaryIndex:0}},Extension:class{},console,selectAndCapture:(done,error,cancel)=>{captures.push({done,error,cancel});return ()=>{};}};
 vm.createContext(context);let src=fs.readFileSync(new URL('../extension.js',import.meta.url),'utf8').replace(/import\s+[^;]*?from\s+['"][^'"]+['"];?/g,'').replace('export default class QTranslate','class QTranslate');vm.runInContext(src+'\nglobalThis.QTranslate=QTranslate;',context);
 const q=new context.QTranslate();Object.assign(q,{alive:true,epoch:'epoch',current:{rewrite:'old'},contexts:{old:{}},crops:{},ready:'old',selectionWindow:window,selectionSerial:1,proxy:{get_name_owner:()=>':backend'},popups:{}});
 for(const action of ['rewrite','translate','image_translate'])q.popups[action]={dismiss:()=>q.dismiss(action,q.current[action]),apply:()=>{}};
 q.orcaSource=async()=>({native:true});
 q.submit=(action,data)=>submitted.push({action,...data});
 return {q,callbacks,captures,writes,calls,deleted,submitted,timers,window,environment:context};
}
test('new Alt+V invalidates old copy before selection callback',()=>{const f=fixture();f.q.invoke('rewrite');let ok;f.q.CopyTextAsync(['old','OLD'],{get_sender:()=>':backend',return_value:v=>ok=v.value[0]});assert.equal(ok,false);assert.deepEqual(f.writes,[]);});
test('out of order selection callbacks keep newest invocation',()=>{const f=fixture();f.q.invoke('rewrite');f.q.invoke('rewrite');f.callbacks[1](null,'NEW');f.callbacks[0](null,'OLD');assert.deepEqual(f.submitted.map(x=>x.text),['NEW']);});
test('superseded screenshot is deleted, never submitted',()=>{const f=fixture();f.q.invoke('image_translate');f.q.invoke('image_translate');f.captures[0].done('/old.png');f.captures[1].done('/new.png');assert.deepEqual(f.submitted.map(x=>x.image_path),['/new.png']);assert.ok(f.deleted.includes('/old.png'));});
test('Escape cancels pending screenshot generation',()=>{const f=fixture();f.q.invoke('image_translate');f.captures[0].cancel();f.captures[0].done('/late.png');assert.equal(f.submitted.length,0);assert.ok(f.deleted.includes('/late.png'));});
test('cancellation does not activate backend',()=>{const f=fixture();f.q.dismiss('rewrite','old');assert.equal(f.calls[0][6],1);});

test('Orca delayed PRIMARY arrives before terminal source is read',async()=>{const f=fixture();f.window.get_wm_class=()=> 'orca-ide';f.q.selectionWindow=null;const errors=[];f.q.localError=(_a,code)=>errors.push(code);f.q.invoke('rewrite');assert.deepEqual(errors,[]);assert.equal(f.callbacks.length,0);f.q.selectionWindow=f.window;f.q.selectionSerial++;for(const t of f.timers.values())t.callback();await new Promise(setImmediate);assert.equal(f.callbacks.length,1);f.callbacks[0](null,'NEW TERMINAL SELECTION');assert.deepEqual(f.submitted.map(x=>x.text),['NEW TERMINAL SELECTION']);});
test('terminal source waits for a newer selection even when old PRIMARY exists',async()=>{const f=fixture();f.window.get_wm_class=()=> 'orca-ide';f.q.invoke('rewrite');assert.equal(f.callbacks.length,0);f.q.selectionSerial++;for(const t of f.timers.values())t.callback();await new Promise(setImmediate);f.callbacks[0](null,'LATEST');assert.deepEqual(f.submitted.map(x=>x.text),['LATEST']);});
test('Codex source uses fresh TUI copy, never cached PRIMARY',async()=>{const f=fixture();f.window.get_wm_class=()=> 'orca';f.q.orcaSource=async()=>({text:'Fresh selected Codex text'});f.q.invoke('rewrite');for(const t of f.timers.values())t.callback();await new Promise(setImmediate);assert.equal(f.callbacks.length,0);assert.deepEqual(f.submitted.map(x=>x.text),['Fresh selected Codex text']);});
test('Codex with no active selection never falls back to old PRIMARY',async()=>{const f=fixture();f.window.get_wm_class=()=> 'orca';const errors=[];f.q.orcaSource=async()=>({error:'NO_SELECTION'});f.q.localError=(_action,error)=>errors.push(error);f.q.invoke('rewrite');for(const t of f.timers.values())t.callback();await new Promise(setImmediate);assert.equal(f.callbacks.length,0);assert.deepEqual(errors,['NO_SELECTION']);});
test('focus change during Codex acquisition resolves loading with an error',async()=>{const f=fixture();f.window.get_wm_class=()=> 'orca';const errors=[];let finish;f.q.orcaSource=()=>new Promise(resolve=>finish=resolve);f.q.localError=(_action,error)=>errors.push(error);f.q.invoke('rewrite');for(const t of f.timers.values())t.callback();f.environment.global.display.focus_window={};finish({text:'fresh'});await new Promise(setImmediate);assert.equal(f.submitted.length,0);assert.deepEqual(errors,['TUI_SOURCE_CHANGED']);});
