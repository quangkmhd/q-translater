export function reduceView(previous,event,now){
 if(previous&&previous.taskId!==event.id&&event.state!=='waiting')return previous;
 const state=event.state;
 const text=event.text??'';
 return {taskId:event.id,action:event.action,phase:state,text,visible:state!=='cancelled',copyEnabled:state==='success'||(state==='error'&&event.error_code==='CLIPBOARD_FAILED'),successIcon:state==='success',expiresAt:state==='success'&&event.action==='rewrite'?now+30:null,errorCode:event.error_code??null};
}
export function expireView(state,id,now){return state?.taskId===id&&state.expiresAt!==null&&now>=state.expiresAt?{...state,visible:false}:state;}

export function viewStatus(state){
 if(state.phase==='error'&&state.errorCode==='CLIPBOARD_FAILED')return 'Chưa copy được';
 if(state.phase==='waiting')return '◌ Đang xử lý…';
 if(['streaming','ready'].includes(state.phase))return '◌';
 return state.successIcon?'✓':'';
}
