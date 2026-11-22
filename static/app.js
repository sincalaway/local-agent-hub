const BACKENDS = [
  {id:'llama', name:'llama.cpp', symbol:'L', subtitle:'主力 · 日常对话'},
  {id:'strata', name:'Strata', symbol:'S', subtitle:'代码 · 复杂推理'},
  {id:'airllm', name:'AirLLM', symbol:'A', subtitle:'超大模型 · 慢速批处理'}
];
const STORE_KEY = 'local-agent-hub.conversations.v1';
let config = null;
let statusData = null;
let sessions = loadSessions();
let currentId = sessions[0]?.id || createSession(false).id;
let toastTimer;

function loadSessions(){
  try { const value = JSON.parse(localStorage.getItem(STORE_KEY) || '[]'); return Array.isArray(value) ? value : []; }
  catch { return []; }
}
function createSession(save=true){
  const s = {id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()), title:'新对话', messages:[], updated:Date.now()};
  sessions.unshift(s); currentId = s.id; if(save) persist(); return s;
}
function persist(){
  sessions = sessions.filter(s => s && Array.isArray(s.messages));
  localStorage.setItem(STORE_KEY, JSON.stringify(sessions.slice(0,30)));
  renderConversations();
}
function currentSession(){ return sessions.find(s => s.id === currentId); }
function esc(value){ return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function toast(message){
  const el = document.getElementById('toast'); el.textContent = message; el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(()=>el.classList.remove('show'), 2700);
}
function renderConversations(){
  const list = document.getElementById('conversationList'); list.replaceChildren();
  sessions.slice(0,10).forEach(s => {
    const button = document.createElement('button'); button.className = 'conversation-item' + (s.id === currentId ? ' active':'');
    const icon = document.createElement('span'); icon.className = 'history-icon'; icon.textContent = '◷';
    const name = document.createElement('span'); name.className = 'conversation-name'; name.textContent = s.title || '新对话';
    button.append(icon,name); button.title = s.title || '新对话';
    button.addEventListener('click', ()=>{ currentId=s.id; renderAll(); closeSidebar(); });
    list.append(button);
  });
}
function renderAll(){
  renderConversations();
  const s = currentSession();
  document.getElementById('chatTitle').textContent = s?.title || '新对话';
  const welcome = document.getElementById('welcome');
  const area = document.getElementById('messages'); area.replaceChildren();
  const messages = s?.messages || [];
  welcome.style.display = messages.length ? 'none' : '';
  messages.forEach((message, index)=>area.append(makeMessage(message, index)));
  scrollBottom();
}
function makeMessage(message, index){
  const row = document.createElement('article'); row.className = `message-row ${message.role === 'user' ? 'user':'assistant'}`;
  if(message.role !== 'user'){
    const avatar = document.createElement('div'); avatar.className='assistant-avatar'; avatar.textContent='✳'; row.append(avatar);
  }
  const wrap = document.createElement('div'); wrap.className='message-content-wrap';
  if(message.role !== 'user'){
    const meta = document.createElement('div'); meta.className='message-meta';
    const label = document.createElement('strong'); label.textContent='本地 Agent'; meta.append(label);
    if(message.backendLabel){ const source=document.createElement('span'); source.textContent=`· ${message.backendLabel}${message.fallbackUsed?'（回退）':''}`; meta.append(source); }
    wrap.append(meta);
  }
  const bubble = document.createElement('div'); bubble.className='message-bubble'; bubble.textContent=message.content || '';
  wrap.append(bubble);
  if(message.role !== 'user' && message.content){
    const tools=document.createElement('div');tools.className='message-tools';
    const copy=document.createElement('button');copy.className='message-tool';copy.textContent='复制';copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(message.content);toast('已复制回复')}catch{toast('复制失败，请手动选择文本')}});
    tools.append(copy);wrap.append(tools);
  }
  row.append(wrap); return row;
}
function scrollBottom(){const sc=document.getElementById('chatScroll'); requestAnimationFrame(()=>sc.scrollTop=sc.scrollHeight);}
function appendTyping(){
  const row=document.createElement('article');row.className='message-row assistant';row.id='typingRow';
  const avatar=document.createElement('div');avatar.className='assistant-avatar';avatar.textContent='✳';
  const wrap=document.createElement('div');wrap.className='message-content-wrap';
  const meta=document.createElement('div');meta.className='message-meta';meta.innerHTML='<strong>本地 Agent</strong><span>正在准备模型…</span>';
  const dots=document.createElement('div');dots.className='typing-indicator';dots.innerHTML='<i></i><i></i><i></i>';
  wrap.append(meta,dots);row.append(avatar,wrap);document.getElementById('messages').append(row);scrollBottom();
}
async function sendMessage(textOverride){
  const input=document.getElementById('messageInput');
  const text=(textOverride ?? input.value).trim(); if(!text) return;
  const s=currentSession() || createSession();
  if(!s.messages.length){s.title=text.length>28?text.slice(0,28)+'…':text;}
  s.messages.push({role:'user',content:text});s.updated=Date.now();persist();renderAll();
  if(!textOverride) input.value=''; resizeInput();
  const send=document.getElementById('sendButton');send.disabled=true;appendTyping();
  const payload={
    model:document.getElementById('modelSelect').value,
    task_hint:document.getElementById('taskHint').value,
    temperature:0.7,max_tokens:2048,
    messages:s.messages.map(m=>({role:m.role,content:m.content}))
  };
  try{
    const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const result=await response.json();
    document.getElementById('typingRow')?.remove();
    if(!response.ok) throw new Error(result.detail || `请求失败（HTTP ${response.status}）`);
    s.messages.push({role:'assistant',content:result.reply,backend:result.backend,backendLabel:result.backend_label,fallbackUsed:result.fallback_used});
    if(result.fallback_used) toast(`主选后端不可用，已回退至 ${result.backend_label}`);
    persist();renderAll();refreshStatus();
  }catch(error){
    document.getElementById('typingRow')?.remove();
    const message=`请求未完成：${error.message}\n\n请检查后端设置中的地址、模型名与启动命令；也可以先在设置里手动启动模型服务。`;
    s.messages.push({role:'assistant',content:message});persist();renderAll();toast('模型请求失败，请查看对话中的提示');
  }finally{send.disabled=false;input.focus();}
}
function resizeInput(){const input=document.getElementById('messageInput');input.style.height='auto';input.style.height=Math.min(input.scrollHeight,180)+'px';}
async function refreshStatus(){
  try{
    const response=await fetch('/api/status');if(!response.ok)throw new Error('status');
    statusData=await response.json();renderStatus();
  }catch{document.getElementById('connectionText').textContent='状态暂不可用';}
}
function renderStatus(){
  if(!statusData)return;
  const all=Object.values(statusData.backends);const healthy=all.filter(b=>b.healthy).length;
  const topDot=document.getElementById('topDot');const sideDot=document.getElementById('overallDot');
  topDot.className='live-dot'+(healthy?' online':'');sideDot.className='live-dot'+(healthy?' online':'');
  document.getElementById('connectionText').textContent=healthy?`${healthy} 个模型服务在线`:'尚无模型服务在线';
  const list=document.getElementById('sidebarBackends');list.replaceChildren();
  BACKENDS.forEach(meta=>{
    const s=statusData.backends[meta.id];const row=document.createElement('div');row.className='sidebar-backend';
    row.title=`${meta.name}：${s?.healthy?'在线':(s?.detail||'未连接')}${s?.model?` · ${s.model}`:''}`;
    const dot=document.createElement('span');dot.className='live-dot'+(s?.healthy?' online':'');
    const name=document.createElement('span');name.className='backend-name';name.textContent=meta.name;
    const state=document.createElement('span');state.className='backend-state';state.textContent=s?.healthy?'在线':(s?.enabled?'待机':'已禁用');
    row.append(dot,name,state);list.append(row);
  });
  BACKENDS.forEach(meta=>{
    const option=document.querySelector(`#modelSelect option[value="${meta.id}"]`);
    if(option) option.disabled=!!statusData.backends[meta.id] && !statusData.backends[meta.id].enabled;
  });
  updateSettingStatusLabels();
}
function openSettings(){
  document.getElementById('settingsModal').classList.add('open');document.getElementById('settingsModal').setAttribute('aria-hidden','false');
  document.getElementById('saveMessage').textContent='';
  fetch('/api/config').then(r=>r.json()).then(data=>{config=data;renderSettings();}).catch(()=>toast('无法读取设置'));
  refreshStatus();
}
function closeSettings(){document.getElementById('settingsModal').classList.remove('open');document.getElementById('settingsModal').setAttribute('aria-hidden','true');}
function renderSettings(){
  if(!config)return;
  const general=document.getElementById('generalSettings');
  general.innerHTML=`
    <div class="setting-field"><span class="setting-label">本地 OpenAI 兼容 API</span><input value="http://127.0.0.1:7860/v1" readonly aria-label="本地 API 地址"><div class="toggle-row"><input id="autoStartToggle" type="checkbox" ${config.auto_start?'checked':''}><span>请求到达时自动启动已配置的后端</span></div></div>
    <div class="setting-field"><label for="proxyKey">代理 API 密钥</label><input id="proxyKey" value="${esc(config.proxy_api_key)}" autocomplete="off"><span class="help-text">仅用于 /v1 API；应用界面为本机使用。不要将服务暴露到公网。</span></div>
    <div class="setting-field wide"><label for="systemPrompt">默认系统提示词</label><textarea id="systemPrompt">${esc(config.system_prompt)}</textarea></div>`;
  const area=document.getElementById('backendSettings');area.replaceChildren();
  BACKENDS.forEach(meta=>{
    const b=config.backends[meta.id];
    const card=document.createElement('section');card.className='backend-setting-card';card.dataset.backend=meta.id;
    const status=statusData?.backends?.[meta.id];
    const command=JSON.stringify(b.start_cmd||[],null,2);
    card.innerHTML=`
      <div class="backend-setting-head"><div class="backend-logo ${meta.id}">${meta.symbol}</div><div class="backend-heading"><strong>${meta.name}</strong><small>${meta.subtitle}</small></div><span class="status-text" data-status>${status?.healthy?'在线':(status?.enabled===false?'已禁用':'未连接')}</span><div class="backend-actions"><button class="mini-action" data-action="start">启动</button><button class="mini-action stop" data-action="stop">停止</button><label class="toggle-row" title="启用此后端"><input data-field="enabled" type="checkbox" ${b.enabled?'checked':''}></label></div></div>
      <div class="backend-fields">
        <div class="backend-field"><label>API 兼容地址</label><input data-field="base_url" value="${esc(b.base_url)}" placeholder="http://127.0.0.1:8081/v1"></div>
        <div class="backend-field"><label>模型标识</label><input data-field="model" value="${esc(b.model)}"></div>
        <div class="backend-field"><label>API Key</label><input data-field="api_key" value="${esc(b.api_key)}" autocomplete="off"></div>
        <div class="backend-field"><label>健康检查路径</label><input data-field="health_path" value="${esc(b.health_path)}" placeholder="/health"></div>
        <div class="backend-field wide"><label>启动命令（JSON 数组）</label><textarea data-field="start_cmd" spellcheck="false" placeholder='["llama-server", "-m", "./models/model.gguf", "--port", "8081"]'>${esc(command)}</textarea><span class="help-text">例如 llama.cpp：["llama-server", "-m", "./models/qwen3-8b-q4_k_m.gguf", "-ngl", "99", "-c", "16384", "--host", "127.0.0.1", "--port", "8081", "--api-key", "sk-llama"]。留空则不会由应用启动。</span></div>
        <div class="backend-field"><label>自动闲置关闭（分钟，0 表示不关闭）</label><input data-field="idle_shutdown_minutes" type="number" min="0" max="1440" value="${Number(b.idle_shutdown_minutes)||0}"></div>
      </div>`;
    area.append(card);
    card.querySelector('[data-action="start"]').addEventListener('click',()=>controlBackend(meta.id,'start',card));
    card.querySelector('[data-action="stop"]').addEventListener('click',()=>controlBackend(meta.id,'stop',card));
  });
}
function updateSettingStatusLabels(){
  document.querySelectorAll('.backend-setting-card').forEach(card=>{
    const state=statusData?.backends?.[card.dataset.backend];const label=card.querySelector('[data-status]');
    if(label){label.textContent=state?.healthy?'在线':(state?.enabled===false?'已禁用':'未连接');label.title=state?.healthy?'服务可连接':(state?.detail||'尚未连接');}
  });
}
async function controlBackend(name,action,card){
  const button=card.querySelector(`[data-action="${action}"]`);button.disabled=true;
  const label=card.querySelector('[data-status]');if(action==='start')label.textContent='启动中…';
  try{
    const r=await fetch(`/api/backends/${name}/${action}`,{method:'POST'});const d=await r.json();
    if(d.status&&statusData)statusData.backends[name]=d.status;
    await refreshStatus();label.textContent=d.status?.healthy?'在线':(d.message||'未连接');toast(d.message);
  }catch(e){toast(`操作失败：${e.message}`)}finally{button.disabled=false;}
}
function collectSettings(){
  const next=structuredClone(config);
  next.auto_start=document.getElementById('autoStartToggle').checked;
  next.proxy_api_key=document.getElementById('proxyKey').value;
  next.system_prompt=document.getElementById('systemPrompt').value;
  document.querySelectorAll('.backend-setting-card').forEach(card=>{
    const b=next.backends[card.dataset.backend];
    card.querySelectorAll('[data-field]').forEach(field=>{
      const key=field.dataset.field;
      if(key==='enabled')b.enabled=field.checked;
      else if(key==='start_cmd'){
        try{b.start_cmd=JSON.parse(field.value||'[]');}catch{throw new Error(`${card.dataset.backend} 的启动命令不是有效 JSON`)}
      }else if(key==='idle_shutdown_minutes')b[key]=Number(field.value||0);
      else b[key]=field.value;
    });
  });
  return next;
}
async function saveSettings(){
  const button=document.getElementById('saveSettings');const message=document.getElementById('saveMessage');
  try{
    const next=collectSettings();button.disabled=true;message.textContent='正在保存…';
    const response=await fetch('/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(next)});
    const result=await response.json();if(!response.ok)throw new Error(result.detail||'保存失败');
    config=result.config;message.textContent='已保存';toast('设置已保存');renderSettings();refreshStatus();setTimeout(closeSettings,550);
  }catch(error){message.textContent=error.message;toast(error.message)}finally{button.disabled=false;}
}
function closeSidebar(){document.getElementById('sidebar').classList.remove('open');document.getElementById('screenDimmer').classList.remove('open');}
function setup(){
  const dimmer=document.createElement('div');dimmer.id='screenDimmer';dimmer.className='screen-dimmer';document.body.append(dimmer);dimmer.addEventListener('click',closeSidebar);
  document.getElementById('newChat').addEventListener('click',()=>{createSession();renderAll();document.getElementById('messageInput').focus();closeSidebar();});
  document.getElementById('sendButton').addEventListener('click',()=>sendMessage());
  document.getElementById('messageInput').addEventListener('input',resizeInput);
  document.getElementById('messageInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();}});
  document.querySelectorAll('.suggestion-card').forEach(card=>card.addEventListener('click',()=>sendMessage(card.dataset.prompt)));
  ['openSettings','topSettings'].forEach(id=>document.getElementById(id).addEventListener('click',openSettings));
  ['closeSettings','cancelSettings'].forEach(id=>document.getElementById(id).addEventListener('click',closeSettings));
  document.getElementById('settingsModal').addEventListener('click',e=>{if(e.target.id==='settingsModal')closeSettings();});
  document.getElementById('saveSettings').addEventListener('click',saveSettings);
  document.getElementById('refreshStatus').addEventListener('click',refreshStatus);
  document.getElementById('menuButton').addEventListener('click',()=>{document.getElementById('sidebar').classList.add('open');dimmer.classList.add('open');});
  document.getElementById('sidebarClose').addEventListener('click',closeSidebar);
  document.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();createSession();renderAll();document.getElementById('messageInput').focus();}
    if(e.key==='Escape'){closeSettings();closeSidebar();}
  });
  renderAll();refreshStatus();setInterval(refreshStatus,15000);
}
document.addEventListener('DOMContentLoaded',setup);
