import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {reduceView,expireView,viewStatus} from '../view_state.js';
function fixture(action){
 const timers=new Map(),signals=new Map(),files=[],images=[],copied=[];let serial=0,pointer=[800,700,0],closed=0,currentEvent=null,focus=null;
 class Widget{
  constructor(props={}){Object.assign(this,{visible:true,children:[],clutter_text:{selection:'',get_selection(){return this.selection;},grab_key_focus(){focus=this;},connect(name,cb){this[name]=cb;return ++serial;}},width:-1,height:60},props);this.vadjustment={value:0};}
  add_child(child){this.children.push(child);} remove_child(child){this.children=this.children.filter(c=>c!==child);}
  set_child(child){this.children=[child];} connect(name,cb){this[name]=cb;return ++serial;}
  hide(){this.visible=false;} show(){this.visible=true;} destroy(){this.destroyed=true;}
  set_style(style){this.style=style;} get_preferred_width(){return [100,350];} get_preferred_height(){return [60,60];}
  get_transformed_position(){return [this.x??0,this.y??0];} get_transformed_size(){return [this.width, this.height];} set_position(x,y){this.x=x;this.y=y;}
 }
 class Icon extends Widget{constructor(props){super(props);images.push(this);}}
 class BoxLayout extends Widget{static list_properties(){return [{name:'orientation'}];}}
 const nativeWindow={connect:(name,cb)=>{let id=++serial;signals.set(id,{name,cb});return id;},disconnect:id=>signals.delete(id)};
 const GLib={PRIORITY_DEFAULT:0,SOURCE_REMOVE:false,SOURCE_CONTINUE:true,get_monotonic_time:()=>1e6,timeout_add:(_p,ms,cb)=>{let id=++serial;timers.set(id,{ms,cb});return id;},timeout_add_seconds:(_p,s,cb)=>{let id=++serial;timers.set(id,{ms:s*1000,cb});return id;},source_remove:id=>timers.delete(id)};
 const ctx={St:{BoxLayout,Button:Widget,ScrollView:Widget,Label:Widget,Icon,Clipboard:{get_default:()=>({set_text(){}})},ClipboardType:{CLIPBOARD:1}},Clutter:{Orientation:{VERTICAL:1,HORIZONTAL:0},ActorAlign:{END:1},EventType:{BUTTON_PRESS:1,KEY_PRESS:2},get_current_event:()=>currentEvent,ModifierType:{BUTTON1_MASK:256,BUTTON2_MASK:512,BUTTON3_MASK:1024},KEY_Escape:27,EVENT_PROPAGATE:false},GLib,Pango:{WrapMode:{WORD_CHAR:1},EllipsizeMode:{NONE:0}},Gio:{File:{new_for_path:path=>{files.push(path);return path;}},FileIcon:class{}},Main:{layoutManager:{addTopChrome(){},monitors:[{index:0}],primaryMonitor:{index:0}}},global:{get_window_actors:()=>[{meta_window:nativeWindow}],display:{connect:(name,cb)=>{let id=++serial;signals.set(id,{name,cb});return id;},disconnect:id=>signals.delete(id)},get_pointer:()=>pointer,stage:{connect:(name,cb)=>{let id=++serial;signals.set(id,{name,cb});return id;},disconnect:id=>signals.delete(id)},workspace_manager:{get_active_workspace:()=>({get_work_area_for_monitor:()=>({x:0,y:0,width:1280,height:800})})}},reduceView,expireView,viewStatus};
 ctx.St.Clipboard.get_default=()=>({set_text(_kind,text){copied.push(text);}});
 GLib.idle_add=(_priority,cb)=>{let id=++serial;timers.set(id,{ms:0,cb});return id;};
 Object.assign(ctx.Clutter,{KEY_c:99,KEY_C:67,KEY_Insert:65379,EVENT_STOP:true});ctx.Clutter.ModifierType.CONTROL_MASK=4;
 ctx.global.stage.get_key_focus=()=>focus;ctx.global.stage.set_key_focus=value=>focus=value;
 vm.createContext(ctx);const code=fs.readFileSync(new URL('../popups.js',import.meta.url),'utf8').replace(/import\s+[^;]*?from\s+['"][^'"]+['"];?/g,'').replace('export class Popup','class Popup');vm.runInContext(code+'\nglobalThis.Popup=Popup;',ctx);
 const popup=new ctx.Popup(action,()=>closed++);
 const apply=(state='success',crop=null)=>popup.apply({id:'test',action,state,text:'Translated text'}, {monitor:0,pointer:[200,200]},crop);
 const tick=()=>{for(const [id,t] of [...timers])if(t.ms<1000&&timers.has(id)&&t.cb()===false)timers.delete(id);};
 return {popup,apply,tick,timers,files,images,signals,copied,focused:()=>focus,nativeClick:(x,y,type=1)=>{currentEvent={type:()=>type,get_coords:()=>[x,y]};for(const signal of [...signals.values()])if(signal.name==='notify::user-time')signal.cb(nativeWindow);currentEvent=null;},closed:()=>closed,pointer:(x,y,mask)=>pointer=[x,y,mask]};
}
for(const action of ['translate','rewrite','image_translate']){
 test(`${action}: output receives mouse input and stays read-only`,()=>{const f=fixture(action);f.apply();const text=f.popup.label.clutter_text;assert.equal(text.reactive,true);assert.equal(text.selectable,true);assert.equal(text.editable,false);text['button-press-event'](text,{get_button:()=>1});assert.equal(f.focused(),text);f.popup.destroy();});
 test(`${action}: selected substring is copied by Ctrl+C and copy icon`,()=>{const f=fixture(action);f.apply();const text=f.popup.label.clutter_text;text.selection='Translated';const event={get_state:()=>4,get_key_symbol:()=>99};assert.equal(text['key-press-event'](text,event),true);assert.deepEqual(f.copied,['Translated']);f.popup.copy.clicked();assert.deepEqual(f.copied,['Translated','Translated']);text.selection='';f.popup.copy.clicked();assert.equal(f.copied.at(-1),'Translated text');f.popup.destroy();});
}
test('Ctrl+C with no selection does not overwrite clipboard or copy the whole result',()=>{const f=fixture('translate');f.apply();const text=f.popup.label.clutter_text;text['key-press-event'](text,{get_state:()=>4,get_key_symbol:()=>99});assert.deepEqual(f.copied,[]);f.popup.destroy();});
test('release settles text focus and closing cancels any pending focus callback',()=>{const f=fixture('translate');f.apply();const text=f.popup.label.clutter_text;text['button-release-event'](text,{get_button:()=>1});f.tick();assert.equal(f.focused(),text);text['button-release-event'](text,{get_button:()=>1});f.popup.destroy();assert.equal(f.timers.size,0);assert.equal(f.focused(),null);});
test('image translation result contains text only and never reads the crop for rendering',()=>{const f=fixture('image_translate');f.apply('success','/private/crop.png');assert.equal(f.popup.label.text,'Translated text');assert.equal(f.images.length,0);assert.equal(f.files.length,0);assert.ok(f.popup.actor.width<=680);});
test('native application click outside hides Alt+C without a stage event or input grab',()=>{const f=fixture('translate');f.apply();f.pointer(1000,700,256);f.tick();assert.equal(f.popup.actor.visible,false);assert.equal(f.closed(),1);assert.equal(f.timers.size,0);});
test('clicks inside the translation popup keep it open',()=>{const f=fixture('translate');f.apply();const p=f.popup.actor;f.pointer(p.x+10,p.y+10,256);f.tick();assert.equal(p.visible,true);assert.equal(f.closed(),0);f.popup.dismiss();assert.equal(f.timers.size,0);});
test('Alt+X text popup also dismisses on native outside click',()=>{const f=fixture('image_translate');f.apply();f.pointer(1000,700,256);f.tick();assert.equal(f.popup.actor.visible,false);});
test('Alt+V is retained on outside click and has no pointer polling',()=>{const f=fixture('rewrite');f.apply();f.pointer(1000,700,256);f.tick();assert.equal(f.popup.actor.visible,true);assert.equal([...f.timers.values()].filter(t=>t.ms<1000).length,0);f.popup.destroy();});
test('dismiss while waiting cancels polling and destroy removes its stage hook',()=>{const f=fixture('translate');f.apply('waiting');f.popup.dismiss();assert.equal(f.timers.size,0);f.popup.destroy();assert.equal(f.signals.size,0);});

test('a complete native click between timer ticks still hides the popup',()=>{const f=fixture('translate');f.apply();f.pointer(1000,700,256);f.nativeClick(1000,700);f.pointer(1000,700,0);assert.equal(f.popup.actor.visible,false);assert.equal(f.closed(),1);assert.equal(f.timers.size,0);f.popup.destroy();assert.equal(f.signals.size,0);});
test('native typing does not act as an outside click',()=>{const f=fixture('translate');f.apply();f.nativeClick(1000,700,2);assert.equal(f.popup.actor.visible,true);f.popup.destroy();assert.equal(f.signals.size,0);});
