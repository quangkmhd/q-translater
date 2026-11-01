'use strict';
// Throwaway UI review: deterministic sample replies, no API or persistence.
const systemPrompt = `Bạn là trợ lý AI giúp người dùng làm việc và học tiếng Anh. Bạn có thể trò chuyện, trả lời câu hỏi, giải thích, dịch, viết lại câu và sửa ngữ pháp.
Làm đúng yêu cầu hiện tại của người dùng; không mặc định dịch hoặc viết lại mọi tin nhắn. Dùng ngữ cảnh cuộc trò chuyện để hiểu câu hỏi tiếp theo.
Mặc định trả lời bằng tiếng Việt, trừ khi người dùng yêu cầu ngôn ngữ khác. Trả lời rõ ràng, ngắn gọn, dễ hiểu. Khi viết tiếng Anh, ưu tiên từ thông dụng và cách nói tự nhiên. Khi sửa ngữ pháp, đưa câu đúng trước và giải thích ngắn khi hữu ích.
Nếu thiếu thông tin quan trọng, hỏi lại ngắn gọn. Không bịa thông tin hoặc khả năng mà bạn không có. Chỉ hiển thị câu trả lời dành cho người dùng, không hiển thị suy nghĩ nội bộ.`;
const samples = {
  grammar: {input:'Câu “I have went to work yesterday” sai ở đâu? Sửa và giải thích giúp mình.', output:'Bạn có thể nói:\n\n**I went to work yesterday.**\n\n“Yesterday” là một thời điểm đã kết thúc, nên dùng **quá khứ đơn**: go → went.\n\nNếu dùng hiện tại hoàn thành thì phải là “have gone”, nhưng không đi với “yesterday”.'},
  explain: {input:'Giải thích “a” và “an” thật dễ hiểu, cho mình vài ví dụ.', output:'Dùng **a** trước âm phụ âm, **an** trước âm nguyên âm. Hãy nghe cách phát âm, đừng chỉ nhìn chữ cái.\n\n• a book — một cuốn sách\n• an apple — một quả táo\n• an hour — một giờ (chữ “h” không phát âm)\n• a university — một trường đại học (bắt đầu bằng âm “y”)'},
  translate: {input:'Dịch câu này sang tiếng Anh tự nhiên: Mình đang bận một chút, lát nữa mình nhắn lại nhé.', output:'**I’m a bit busy right now. I’ll text you later.**\n\nCách nói này tự nhiên và phù hợp khi nhắn tin với bạn bè hoặc đồng nghiệp.'}
};
const $ = id => document.getElementById(id);
let generation=0, timer=null, busy=false, activeReply=null, activeText='', previous='', followTail=true;
$('system-prompt').textContent=systemPrompt;
function announce(text){$('announcement').textContent=text;}
function openChat(){ $('chat').hidden=false; $('message').focus(); }
function resizeInput(){const el=$('message');el.style.height='auto';el.style.height=Math.min(el.scrollHeight,144)+'px';$('send').disabled=!el.value.trim();}
function setBusy(value){busy=value;$('send').hidden=value;$('stop').hidden=!value;$('conversation').setAttribute('aria-busy',String(value));}
function scrollEnd(){if(followTail)$('conversation').scrollTop=$('conversation').scrollHeight;}
function formatText(node,text){
  node.replaceChildren();
  text.split(/(\*\*[^*]+\*\*)/g).forEach(part=>{
    if(part.startsWith('**')&&part.endsWith('**')){const strong=document.createElement('strong');strong.textContent=part.slice(2,-2);node.append(strong);}
    else node.append(document.createTextNode(part));
  });
}
function message(role,text=''){
  $('empty-state').hidden=true;
  const el=document.createElement('div');el.className='message '+role;
  const body=document.createElement('div');body.className='message-text';formatText(body,text);el.append(body);$('conversation').append(el);scrollEnd();return el;
}
function addCopy(el,text){
  const tools=document.createElement('div');tools.className='reply-actions';
  const copy=document.createElement('button');copy.type='button';copy.className='icon-button';copy.title='Sao chép câu trả lời';copy.setAttribute('aria-label','Sao chép câu trả lời');
  const icon=document.createElement('img');icon.src='assets/icons/edit-copy.svg';icon.alt='';copy.append(icon);
  copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(text.replaceAll('**',''));copy.title='Đã sao chép';announce('Đã sao chép câu trả lời.');}catch{announce('Chưa sao chép được. Bạn có thể chọn câu trả lời và nhấn Ctrl+C.');copy.title='Chọn văn bản và nhấn Ctrl+C';}});
  tools.append(copy);el.append(tools);
}
function finishReply(stopped=false){
  clearTimeout(timer);timer=null;
  if(activeReply){activeReply.classList.remove('streaming');const waiting=activeReply.querySelector('.waiting');if(waiting)waiting.remove();if(activeText)addCopy(activeReply,activeText);else activeReply.remove();}
  activeReply=null;setBusy(false);announce(stopped?'Đã dừng trả lời.':'Trợ lý đã trả lời xong.');
}
function stopReply(){generation++;finishReply(true);}
function resetChat(){
  stopReply();$('conversation').querySelectorAll('.message').forEach(el=>el.remove());$('empty-state').hidden=false;$('message').value='';previous='';activeText='';followTail=true;resizeInput();openChat();
}
function answerFor(input){
  const lower=input.toLowerCase();
  if(/ngắn hơn|ngắn gọn|shorter/.test(lower)&&previous)return 'Ngắn gọn hơn:\n\n**I went to work yesterday.**\n\nCó “yesterday” → dùng quá khứ đơn “went”.';
  if(/ví dụ|example/.test(lower)&&previous)return 'Thêm vài ví dụ về quá khứ đơn:\n\n• **I called you yesterday.** — Hôm qua mình đã gọi cho bạn.\n• **We had lunch together.** — Chúng mình đã ăn trưa cùng nhau.\n• **She went home early.** — Cô ấy về nhà sớm.\n\nNếu bạn muốn, mình có thể giúp bạn đặt một câu về hôm qua.';
  if(/have went|yesterday|ngữ pháp/.test(lower))return samples.grammar.output;
  if(/\ba\b.*\ban\b|mạo từ/.test(lower))return samples.explain.output;
  if(/dịch|đang bận/.test(lower))return samples.translate.output;
  if(/chào|hello|\bhi\b/.test(lower))return 'Chào bạn! Bạn muốn mình giúp gì? Bạn có thể hỏi một câu, nhờ dịch hoặc gửi câu tiếng Anh để mình kiểm tra.';
  return 'Đây là phản hồi mẫu để bạn thử bố cục và hiệu ứng trả lời.\n\nBạn có thể thử câu hỏi **“I have went to work yesterday sai ở đâu?”**, rồi hỏi tiếp **“Cho mình thêm ví dụ”**. Bản demo này chưa gửi nội dung tới AI.';
}
function respond(input,output,{instant=false,hold=false}={}){
  const token=++generation;followTail=true;message('user',input);activeReply=message('assistant');activeText='';previous=input;setBusy(true);
  const waiting=document.createElement('div');waiting.className='waiting';waiting.setAttribute('aria-label','Đang chờ trả lời');for(let i=0;i<3;i++)waiting.append(document.createElement('span'));activeReply.prepend(waiting);scrollEnd();announce('Đang trả lời.');
  if(hold)return;
  function start(){
    if(token!==generation)return;waiting.remove();activeReply.classList.add('streaming');
    const chars=Array.from(output);let offset=0;
    function tick(){
      if(token!==generation)return;
      offset=Math.min(chars.length,offset+(instant?chars.length:3));activeText=chars.slice(0,offset).join('');formatText(activeReply.querySelector('.message-text'),activeText);scrollEnd();
      if(offset<chars.length)timer=setTimeout(tick,18);else finishReply();
    }
    tick();
  }
  timer=setTimeout(start,instant?0:650);
}
$('chat-form').addEventListener('submit',event=>{event.preventDefault();const input=$('message').value.trim();if(!input||busy)return;const output=answerFor(input);$('message').value='';resizeInput();respond(input,output);$('message').focus();});
$('message').addEventListener('input',resizeInput);
$('message').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('chat-form').requestSubmit();}});
$('conversation').addEventListener('scroll',()=>{const el=$('conversation');followTail=el.scrollHeight-el.scrollTop-el.clientHeight<36;});
$('open-chat').addEventListener('click',openChat);
$('close-chat').addEventListener('click',()=>{$('chat').hidden=true;$('open-chat').focus();});
$('new-chat').addEventListener('click',resetChat);
$('stop').addEventListener('click',stopReply);
document.querySelectorAll('[data-sample]').forEach(button=>button.addEventListener('click',()=>{$('message').value=samples[button.dataset.sample].input;resizeInput();$('message').focus();}));
document.querySelectorAll('[data-state]').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('[data-state]').forEach(b=>b.classList.toggle('selected',b===button));resetChat();
  const state=button.dataset.state;
  if(state!=='empty')respond(samples.grammar.input,samples.grammar.output,{instant:state==='result',hold:state==='loading'});
}));
document.addEventListener('keydown',event=>{
  if(event.altKey&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&event.code==='KeyD'){event.preventDefault();openChat();}
  if(event.key==='Escape'&&!$('chat').hidden){$('chat').hidden=true;$('open-chat').focus();}
});
openChat();resizeInput();
