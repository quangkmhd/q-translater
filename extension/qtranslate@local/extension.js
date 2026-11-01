import Gio from 'gi://Gio';import GLib from 'gi://GLib';import St from 'gi://St';import Shell from 'gi://Shell';import Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {textFrames} from './protocol.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Popup} from './popups.js';import {selectAndCapture} from './capture.js';
const BUS='org.qtranslate.App',PATH='/org/qtranslate/App',IFACE='org.qtranslate.App1';
const XML=`<node><interface name="org.qtranslate.Desktop1"><method name="CopyText"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="b" direction="out"/></method><method name="Capabilities"><arg type="s" direction="out"/></method></interface></node>`;
export default class QTranslate extends Extension{
 acquire(action){if(this.sourceTimers?.[action]){GLib.source_remove(this.sourceTimers[action]);delete this.sourceTimers[action];}this.generations??={};this.generations[action]=(this.generations[action]??0)+1;return this.generations[action];}
 valid(action,generation){return this.alive&&this.generations?.[action]===generation;}
 enable(){this.epoch=GLib.uuid_string_random();this.alive=true;this.current={};this.contexts={};this.crops={};this.sources={};this.targets={};this.ready=null;this.selectionWindow=null;this.selectionSerial=0;this.popups={};this.settings=this.getSettings();this.bound=[];
  const selection=global.display.get_selection();this.selection=selection;this.selectionSignal=selection.connect('owner-changed',(_s,type,owner)=>{if(type===Meta.SelectionType.SELECTION_PRIMARY){this.selectionWindow=owner?global.display.focus_window:null;this.selectionSerial++;}});
  for(const action of ['translate','rewrite','image_translate']){this.popups[action]=new Popup(action,id=>this.dismiss(action,id),()=>this.retryImage(),(target)=>this.reverseTranslation(target));const key=action.replace('_','-');const result=Main.wm.addKeybinding(key,this.settings,Meta.KeyBindingFlags.NONE,Shell.ActionMode.NORMAL,()=>this.invoke(action));if(result!==Meta.KeyBindingAction.NONE)this.bound.push(key);}
  this.proxy=new Gio.DBusProxy({g_connection:Gio.DBus.session,g_name:BUS,g_object_path:PATH,g_interface_name:IFACE});this.proxy.init_async(GLib.PRIORITY_DEFAULT,null,(obj,res)=>{try{obj.init_finish(res);}catch(e){console.error('Q Translate backend unavailable');}});
  this.signal=Gio.DBus.session.signal_subscribe(BUS,IFACE,'TaskChanged',PATH,null,Gio.DBusSignalFlags.NONE,(_c,sender,_path,_iface,_signal,params)=>{if(!this.alive)return;try{const [id,json]=params.deep_unpack();const event=JSON.parse(json);if(this.current[event.action]!==id)return;if(event.state==='ready'&&event.action==='rewrite')this.ready=id;this.popups[event.action]?.apply(event,this.contexts[id],this.crops[id]);}catch(e){console.error('Q Translate invalid backend update');}});
  this.indicator=new PanelMenu.Button(0,'Q Translate',false);this.indicator.add_child(new St.Icon({gicon:new Gio.FileIcon({file:this.dir.get_child('icons').get_child('q-translate.svg')}),icon_size:16,style_class:'system-status-icon'}));
  const open=new PopupMenu.PopupMenuItem('Cài đặt Q Translate');open.connect('activate',()=>{const app=Gio.DesktopAppInfo.new('org.qtranslate.App.desktop');if(app)app.launch([],null);else Main.notify('Q Translate','Mở dashboard bằng launcher của ứng dụng.');});this.indicator.menu.addMenuItem(open);
  const quit=new PopupMenu.PopupMenuItem('Thoát Q Translate');quit.connect('activate',()=>Gio.DBus.session.call(BUS,PATH,IFACE,'Stop',null,null,Gio.DBusCallFlags.NONE,2000,null,()=>{}));this.indicator.menu.addMenuItem(quit);Main.panel.addToStatusArea(this.uuid,this.indicator);
  this.backendWatch=Gio.bus_watch_name_on_connection(Gio.DBus.session,BUS,Gio.BusNameWatcherFlags.NONE,()=>{if(this.alive&&this.bound.length===0)this.bindKeys();},()=>{if(!this.alive)return;for(const key of this.bound)Main.wm.removeKeybinding(key);this.bound=[];for(const p of Object.values(this.popups))p.dismiss();});
  this.exported=Gio.DBusExportedObject.wrapJSObject(XML,this);this.exported.export(Gio.DBus.session,'/org/qtranslate/Desktop');this.name=Gio.bus_own_name_on_connection(Gio.DBus.session,'org.qtranslate.Desktop',Gio.BusNameOwnerFlags.NONE,null,null);
 }
 bindKeys(){for(const action of ['translate','rewrite','image_translate']){const key=action.replace('_','-');const result=Main.wm.addKeybinding(key,this.settings,Meta.KeyBindingFlags.NONE,Shell.ActionMode.NORMAL,()=>this.invoke(action));if(result!==Meta.KeyBindingAction.NONE)this.bound.push(key);}}
 reverseTranslation(target){const old=this.current.translate;const text=this.sources[old];const context=this.contexts[old];if(text&&context)this.submit('translate',{text,target},context);}
 retryImage(){const old=this.current.image_translate;const path=this.crops[old];const context=this.contexts[old];if(path&&context)this.submit('image_translate',{image_path:path},context);}
 Capabilities(){return JSON.stringify({version:1,epoch:this.epoch,keybindings:this.bound,selection:!!this.selection,clipboard:true,capture:true,popup_backend:'shell',selectable_results:this.popups.translate?.selectableResults===true,source_handoff_ms:200,tui_selection:'codex-ctrl-insert',status:'BLOCKED',reason:'DESKTOP_MATRIX_PENDING'});}
 CopyTextAsync(params,invocation){const [id,text]=params;let ok=false;try{if(this.alive&&id===this.current.rewrite&&id===this.ready&&invocation.get_sender()===this.proxy.get_name_owner()){St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD,text);ok=true;}}catch{}invocation.return_value(new GLib.Variant('(b)',[ok]));}
 orcaSource(action,context,id){return new Promise((resolve,reject)=>Gio.DBus.session.call(BUS,PATH,IFACE,'ReadSelection',new GLib.Variant('(s)',[JSON.stringify({version:1,epoch:this.epoch,id,action,context,text:''})]),null,Gio.DBusCallFlags.NONE,7000,null,(connection,result)=>{try{resolve(JSON.parse(connection.call_finish(result).deep_unpack()[0]));}catch(e){reject(e);}}));}
 invoke(action){if(!this.alive)return;const startedAt=GLib.get_monotonic_time()/1e6;this.popups[action].dismiss();if(action==='image_translate'&&this.captureClose)this.captureClose();const generation=this.acquire(action);const window=global.display.focus_window;const pointer=global.get_pointer();const context={window_id:String(window?.get_stable_sequence()??''),app_id:window?.get_wm_class()??'',source_epoch:this.epoch+':'+this.selectionSerial,monitor:window?.get_monitor()??Main.layoutManager.primaryIndex,pointer:pointer.slice(0,2)};
  if(action==='image_translate'){this.captureClose=selectAndCapture(path=>{if(this.valid(action,generation)){this.captureClose=null;this.submit(action,{image_path:path},context);}else{try{Gio.File.new_for_path(path).delete(null);}catch{}}},()=>{if(this.valid(action,generation))this.localError(action,'CAPTURE_FAILED',context);},()=>{if(this.valid(action,generation))this.acquire(action);});return;}
  const read=async()=>{if(!this.valid(action,generation))return;
   if(/^orca(?:-ide)?$/i.test(context.app_id)){
    const id=GLib.uuid_string_random();this.current[action]=id;this.contexts[id]=context;this.popups[action].apply({id,action,state:'waiting'},context);
    let source;try{source=await this.orcaSource(action,context,id);}catch{source={error:'TUI_SOURCE_UNAVAILABLE'};}
    if(!this.valid(action,generation))return;
    if(global.display.focus_window!==window){this.localError(action,'TUI_SOURCE_CHANGED',context);return;}
    if(source.error){this.localError(action,source.error,context);return;}
    if(source.native!==true){
     if(!source.text?.trim()){this.localError(action,'NO_SELECTION',context);return;}
     context.source_epoch=this.epoch+':tui:'+generation;this.submit(action,{text:source.text,started_at:startedAt},context);return;
    }
   }
   const serial=this.selectionSerial;if(!window||this.selectionWindow!==window){this.localError(action,'NO_SELECTION',context);return;}
   St.Clipboard.get_default().get_text(St.ClipboardType.PRIMARY,(_c,text)=>{if(!this.valid(action,generation))return;if(serial!==this.selectionSerial||global.display.focus_window!==window||!text?.trim()){this.localError(action,'NO_SELECTION',context);return;}context.source_epoch=this.epoch+':'+serial;this.submit(action,{text,started_at:startedAt},context);});
  };
  // Embedded terminals publish PRIMARY after a renderer/clipboard debounce.
  // Read its serial after that handoff, never before it. Codex uses its explicit copy action.
  if(/orca|terminal|ptyxis|konsole|kitty|alacritty|wezterm|foot|tilix|terminator|kgx|code/i.test(context.app_id)){
   this.sourceTimers??={};this.sourceTimers[action]=GLib.timeout_add(GLib.PRIORITY_DEFAULT,200,()=>{delete this.sourceTimers[action];read();return GLib.SOURCE_REMOVE;});
  }else read();
 }
 localError(action,code,context){console.warn(`Q Translate: ${code}`);const id=GLib.uuid_string_random();this.dismiss(action,this.current[action]);this.current[action]=id;this.contexts[id]=context;this.popups[action].apply({id,action,state:'waiting'},context);this.popups[action].apply({id,action,state:'error',error_code:code},context);}
 submit(action,data,context){const old=this.current[action];if(old)this.dismiss(action,old,data.image_path);const id=GLib.uuid_string_random();this.current[action]=id;this.contexts[id]=context;this.sources[id]=data.text;this.targets[id]=data.target;if(data.image_path)this.crops[id]=data.image_path;this.popups[action].apply({id,action,state:'waiting'},context,data.image_path);
  const payload={version:1,epoch:this.epoch,id,action,context,...data};const call=(method,params)=>new Promise((resolve,reject)=>Gio.DBus.session.call(BUS,PATH,IFACE,method,params,null,Gio.DBusCallFlags.NONE,5000,null,(conn,res)=>{try{resolve(conn.call_finish(res));}catch(e){reject(e);}}));
  const send=async()=>{if(data.text&&new TextEncoder().encode(data.text).length>65536){const frames=textFrames(data.text);await call('BeginText',new GLib.Variant('(ss)',[id,JSON.stringify({...payload,text:'',chunk_count:frames.length})]));for(let i=0;i<frames.length;i++){if(!this.alive||this.current[action]!==id)return;await call('AppendText',new GLib.Variant('(sus)',[id,i,frames[i]]));}await call('FinishText',new GLib.Variant('(s)',[id]));}else await call('Submit',new GLib.Variant('(s)',[JSON.stringify(payload)]));};
  send().catch(()=>{if(this.alive&&this.current[action]===id)this.popups[action].apply({id,action,state:'error',error_code:'BACKEND_UNAVAILABLE'},context);});
 }
 dismiss(action,id,keepCrop=null){if(!id)return;Gio.DBus.session.call(BUS,PATH,IFACE,'Cancel',new GLib.Variant('(s)',[id]),null,Gio.DBusCallFlags.NO_AUTO_START,2000,null,()=>{});if(this.current[action]===id){this.acquire(action);delete this.current[action];};if(this.ready===id)this.ready=null;if(this.crops[id]){try{if(this.crops[id]!==keepCrop)Gio.File.new_for_path(this.crops[id]).delete(null);}catch{}delete this.crops[id];}delete this.contexts[id];if(this.sources)delete this.sources[id];if(this.targets)delete this.targets[id];}
 disable(){this.alive=false;for(const timer of Object.values(this.sourceTimers??{}))GLib.source_remove(timer);this.sourceTimers={};if(this.backendWatch)Gio.bus_unwatch_name(this.backendWatch);this.indicator?.destroy();if(this.captureClose)this.captureClose();for(const action of Object.keys(this.current))this.dismiss(action,this.current[action]);for(const key of this.bound)Main.wm.removeKeybinding(key);this.selection?.disconnect(this.selectionSignal);if(this.signal)Gio.DBus.session.signal_unsubscribe(this.signal);this.exported?.unexport();if(this.name)Gio.bus_unown_name(this.name);for(const popup of Object.values(this.popups))popup.destroy();this.popups={};this.proxy=null;}
}
