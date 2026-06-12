"""
Chat UI HTML template — dark theme, modern design.
This file is imported by chat_api.py at startup to serve the CHAT_HTML constant.
"""
CHAT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ES Intelligence Chatbot</title>
<style>
:root {
  --bg: #0f1117; --bg2: #161822; --bg3: #1c1f2e; --bg4: #252840;
  --border: #2a2d3e; --border2: #3a3d55;
  --text: #e4e6f0; --text2: #9498b0; --text3: #5a5e78;
  --accent: #6c8cff; --accent2: #4a6cf7; --accent-glow: rgba(108,140,255,0.15);
  --green: #4ade80; --yellow: #fbbf24; --red: #f87171; --orange: #fb923c; --cyan: #22d3ee;
  --radius: 12px; --radius-sm: 8px;
  --font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --mono: 'JetBrains Mono', 'Fira Code', monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden}
body{font-family:var(--font);background:var(--bg);color:var(--text);display:flex;flex-direction:column}
.header{background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 20px;display:flex;align-items:center;gap:16px;flex-shrink:0;z-index:10}
.header-logo{width:36px;height:36px;background:linear-gradient(135deg,var(--accent),#a78bfa);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}
.header-info{flex:1;min-width:0}
.header-title{font-size:15px;font-weight:600;color:var(--text);letter-spacing:-0.2px}
.header-sub{font-size:11px;color:var(--text3);margin-top:1px}
.header-badges{display:flex;gap:6px;flex-shrink:0}
.badge{font-size:10px;padding:3px 8px;border-radius:20px;font-weight:600;letter-spacing:0.3px;text-transform:uppercase}
.badge-green{background:rgba(74,222,128,0.12);color:var(--green);border:1px solid rgba(74,222,128,0.2)}
.badge-blue{background:rgba(108,140,255,0.12);color:var(--accent);border:1px solid rgba(108,140,255,0.2)}
.badge-yellow{background:rgba(251,191,36,0.12);color:var(--yellow);border:1px solid rgba(251,191,36,0.2)}
.badge-red{background:rgba(248,113,113,0.12);color:var(--red);border:1px solid rgba(248,113,113,0.2)}
.setup-overlay{position:absolute;inset:0;background:rgba(15,17,23,0.85);backdrop-filter:blur(8px);z-index:100;display:flex;align-items:center;justify-content:center;transition:opacity 0.3s}
.setup-overlay.hidden{opacity:0;pointer-events:none}
.setup-panel{background:var(--bg2);border:1px solid var(--border);border-radius:16px;padding:32px;width:700px;max-height:90vh;overflow-y:auto;box-shadow:0 24px 80px rgba(0,0,0,0.6)}
.setup-title{font-size:22px;font-weight:700;margin-bottom:6px;letter-spacing:-0.5px}
.setup-desc{font-size:13px;color:var(--text3);margin-bottom:24px;line-height:1.5}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.form-grid .full{grid-column:1/-1}
.form-group{display:flex;flex-direction:column;gap:6px}
.form-label{font-size:11px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:0.5px}
.form-select,.form-input{background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:10px 12px;border-radius:var(--radius-sm);font-size:13px;font-family:var(--font);outline:none;transition:border-color 0.2s;width:100%;appearance:none}
.form-select:focus,.form-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
.form-select option{background:var(--bg3);color:var(--text)}
.query-editor{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;font-family:var(--mono);font-size:12px;color:var(--green);width:100%;min-height:120px;resize:vertical;outline:none;line-height:1.6;tab-size:2}
.query-editor:focus{border-color:var(--accent)}
.chip-group{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.chip{font-size:11px;padding:4px 10px;border-radius:20px;cursor:pointer;background:var(--bg3);border:1px solid var(--border);color:var(--text2);transition:all 0.15s;user-select:none}
.chip:hover{border-color:var(--accent);color:var(--accent)}
.chip.active{background:rgba(108,140,255,0.15);border-color:var(--accent);color:var(--accent)}
.btn{padding:10px 20px;border-radius:var(--radius-sm);font-size:13px;font-weight:600;cursor:pointer;border:none;transition:all 0.15s;display:inline-flex;align-items:center;gap:8px}
.btn-primary{background:linear-gradient(135deg,var(--accent2),#7c3aed);color:white;box-shadow:0 2px 12px rgba(108,140,255,0.3)}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 4px 20px rgba(108,140,255,0.4)}
.btn-ghost{background:transparent;color:var(--text2);border:1px solid var(--border)}
.btn-ghost:hover{background:var(--bg3);color:var(--text)}
.btn-sm{padding:6px 12px;font-size:12px}
.btn:disabled{opacity:0.4;cursor:not-allowed!important;transform:none!important}
.divider{height:1px;background:var(--border);margin:20px 0}
.notice-bar{padding:8px 16px;font-size:12px;display:none;align-items:center;gap:8px;flex-shrink:0}
.notice-bar.warning{background:rgba(251,191,36,0.08);border-bottom:1px solid rgba(251,191,36,0.15);color:var(--yellow);display:flex}
.notice-bar.error{background:rgba(248,113,113,0.08);border-bottom:1px solid rgba(248,113,113,0.15);color:var(--red);display:flex}
.notice-bar.success{background:rgba(74,222,128,0.08);border-bottom:1px solid rgba(74,222,128,0.15);color:var(--green);display:flex}
.notice-bar.info{background:rgba(34,211,238,0.08);border-bottom:1px solid rgba(34,211,238,0.15);color:var(--cyan);display:flex}
.chat-container{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:16px;scroll-behavior:smooth}
.chat-container::-webkit-scrollbar{width:6px}
.chat-container::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.msg{display:flex;gap:12px;max-width:85%;animation:fadeIn 0.25s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.msg.user{align-self:flex-end;flex-direction:row-reverse}
.msg-avatar{width:32px;height:32px;border-radius:8px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:14px;margin-top:2px}
.msg.user .msg-avatar{background:linear-gradient(135deg,#6366f1,#8b5cf6)}
.msg.bot .msg-avatar{background:linear-gradient(135deg,#0ea5e9,#06b6d4)}
.msg-content{display:flex;flex-direction:column;gap:4px;min-width:0}
.msg.user .msg-content{align-items:flex-end}
.msg-meta{font-size:10px;color:var(--text3);padding:0 4px}
.msg-bubble{padding:12px 16px;border-radius:var(--radius);font-size:13.5px;line-height:1.6;word-wrap:break-word;white-space:pre-wrap}
.msg.user .msg-bubble{background:linear-gradient(135deg,#4f46e5,#6366f1);color:white;border-bottom-right-radius:4px}
.msg.bot .msg-bubble{background:var(--bg3);border:1px solid var(--border);color:var(--text);border-bottom-left-radius:4px}
.msg-bubble strong{color:var(--accent);font-weight:600}
.msg-bubble code{background:rgba(0,0,0,0.3);padding:1px 6px;border-radius:4px;font-family:var(--mono);font-size:12px;color:var(--cyan)}
.msg-bubble ul,.msg-bubble ol{padding-left:20px;margin:6px 0}
.msg-bubble li{margin-bottom:2px}
.msg-bubble p{margin-bottom:8px}
.msg-bubble p:last-child{margin-bottom:0}
.typing-dots{display:flex;gap:4px;padding:4px 0}
.typing-dots span{width:6px;height:6px;border-radius:50%;background:var(--accent);animation:bounce 1.2s infinite}
.typing-dots span:nth-child(2){animation-delay:0.15s}
.typing-dots span:nth-child(3){animation-delay:0.3s}
@keyframes bounce{0%,60%,100%{transform:translateY(0);opacity:0.4}30%{transform:translateY(-6px);opacity:1}}
.progress-log{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;font-family:var(--mono);font-size:11px;color:var(--text2);display:flex;gap:8px;align-items:center;margin-bottom:6px;border-left:3px solid var(--accent)}
.progress-log.done{border-left-color:var(--green)}
.progress-log.error{border-left-color:var(--red)}
.sources-row{display:flex;gap:6px;flex-wrap:wrap;padding:4px 8px 0}
.sources-chip{font-size:10px;padding:2px 8px;border-radius:12px;background:rgba(108,140,255,0.08);color:var(--accent);border:1px solid rgba(108,140,255,0.12)}
.input-area{background:var(--bg2);border-top:1px solid var(--border);padding:16px 20px;flex-shrink:0}
.input-row{display:flex;gap:10px;align-items:flex-end}
.input-wrap{flex:1}
.chat-input{width:100%;background:var(--bg3);border:1px solid var(--border);color:var(--text);padding:12px 16px;border-radius:var(--radius);font-size:13.5px;font-family:var(--font);outline:none;resize:none;transition:border-color 0.2s;min-height:46px;max-height:120px;line-height:1.5}
.chat-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
.chat-input::placeholder{color:var(--text3)}
.send-btn{width:46px;height:46px;border-radius:var(--radius);border:none;background:linear-gradient(135deg,var(--accent2),#7c3aed);color:white;cursor:pointer;font-size:18px;flex-shrink:0;display:flex;align-items:center;justify-content:center;transition:all 0.15s;box-shadow:0 2px 8px rgba(108,140,255,0.3)}
.send-btn:hover{transform:scale(1.05);box-shadow:0 4px 16px rgba(108,140,255,0.4)}
.send-btn:active{transform:scale(0.95)}
.send-btn:disabled{opacity:0.35;cursor:not-allowed;transform:none!important}
.input-hint{font-size:10px;color:var(--text3);margin-top:6px;padding-left:4px}
.query-builder-row{display:flex;gap:8px;align-items:center;margin-bottom:8px}
.query-builder-row .form-select{flex:1}
.query-builder-row .form-input{flex:1}
.btn-icon-only{width:34px;height:34px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--bg3);color:var(--text2);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;transition:all 0.15s}
.btn-icon-only:hover{background:var(--bg4);color:var(--red);border-color:var(--red)}
@media(max-width:768px){.setup-panel{width:95vw;padding:20px}.form-grid{grid-template-columns:1fr}.form-grid .full{grid-column:1}.header-badges{display:none}}
</style>
</head>
<body>
<div class="header">
  <div class="header-logo">🔍</div>
  <div class="header-info">
    <div class="header-title">ES Intelligence Chatbot</div>
    <div class="header-sub" id="headerSub">Configure your data source and model to start chatting</div>
  </div>
  <div class="header-badges" id="headerBadges">
    <span class="badge badge-green" id="badgeConnected" style="display:none">● Connected</span>
    <span class="badge badge-blue" id="badgeDocs" style="display:none">0 docs</span>
    <span class="badge badge-yellow" id="badgeModel" style="display:none">—</span>
  </div>
  <button class="btn btn-ghost btn-sm" onclick="showSetup()">⚙️ Settings</button>
</div>
<div class="notice-bar" id="noticeBar"></div>

<div class="setup-overlay" id="setupOverlay">
  <div class="setup-panel">
    <div class="setup-title">⚙️ Session Configuration</div>
    <div class="setup-desc">Configure your Elasticsearch data source and LLM model to start chatting with your intelligence data.</div>
    <div class="form-grid">
      <div style="display:flex;flex-direction:column;gap:16px">
        <div style="font-size:13px;font-weight:600;color:var(--accent);margin-bottom:4px">📡 Data Source</div>
        <div class="form-group">
          <label class="form-label">Fetch Mode</label>
          <select class="form-select" id="fetchMode" onchange="toggleFetchMode()">
            <option value="category">Category (recommended)</option>
            <option value="raw_query">Raw ES Query</option>
          </select>
        </div>
        <div id="categorySection">
          <div class="form-group">
            <label class="form-label">Category</label>
            <select class="form-select" id="categorySelect"><option>Loading...</option></select>
          </div>
          <div class="chip-group" id="categoryChips"></div>
        </div>
        <div id="rawQuerySection" style="display:none">
          <div class="form-group">
            <label class="form-label">Raw Elasticsearch Query (JSON)</label>
            <textarea class="query-editor" id="rawQueryEditor" placeholder='{"query": {"match_all": {}}}' spellcheck="false"></textarea>
          </div>
        </div>
        <div class="form-grid">
          <div class="form-group"><label class="form-label">Date From</label><input class="form-input" type="date" id="dateFrom"></div>
          <div class="form-group"><label class="form-label">Date To</label><input class="form-input" type="date" id="dateTo"></div>
        </div>
        <div class="form-group">
          <label class="form-label">Quick Presets</label>
          <div class="chip-group">
            <span class="chip" onclick="applyPreset('infra')">🏗️ Infra</span>
            <span class="chip" onclick="applyPreset('deployment')">🪖 Deployment</span>
            <span class="chip" onclick="applyPreset('all')">📊 All Data</span>
          </div>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:16px">
        <div style="font-size:13px;font-weight:600;color:var(--accent);margin-bottom:4px">🤖 Language Model</div>
        <div class="form-group">
          <label class="form-label">Model</label>
          <select class="form-select" id="modelSelect"><option>Loading...</option></select>
        </div>
        <div class="chip-group" id="modelChips"></div>
        <div class="form-group"><label class="form-label">LLM Timeout (s)</label><input class="form-input" type="number" id="llmTimeout" value="120" min="10" max="600"></div>
        <div class="form-group"><label class="form-label">Max Turns</label><input class="form-input" type="number" id="maxTurns" value="10" min="1" max="50"></div>
        <div class="divider"></div>
        <div class="form-group"><label class="form-label">Session ID</label><input class="form-input" id="sessionId" value="chat-session"></div>
        <div style="display:flex;gap:12px;align-items:center">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;color:var(--text2)"><input type="checkbox" id="useDebug"> Debug</label>
        </div>
        <div class="divider"></div>
        <button class="btn btn-primary" onclick="startSession()" style="width:100%;justify-content:center">🚀 Start Chat Session</button>
        <div style="font-size:11px;color:var(--text3);text-align:center">Fetches data from ES and starts a conversation</div>
      </div>
    </div>
  </div>
</div>

<div class="chat-container" id="chatContainer">
  <div style="text-align:center;color:var(--text3);font-size:13px;padding:60px 20px;opacity:0.6">
    <div style="font-size:48px;margin-bottom:16px">🔍</div>
    <div style="font-weight:600;margin-bottom:8px">Welcome to ES Intelligence Chatbot</div>
    <div>Configure your data source and model, then click <strong>Start Chat Session</strong> to begin.</div>
  </div>
</div>

<div class="input-area">
  <div class="input-row">
    <div class="input-wrap">
      <textarea class="chat-input" id="chatInput" placeholder="Ask a question about your data..." rows="1" onkeydown="handleInputKey(event)" oninput="autoResize(this)" disabled></textarea>
    </div>
    <button class="send-btn" id="sendBtn" onclick="sendMessage()" disabled>➤</button>
  </div>
  <div class="input-hint" id="inputHint">Configure and start a session to begin chatting</div>
</div>

<script>
'use strict';
let sessionId=null,isLoading=false,currentModel='';
const API='';

if(document.readyState==='complete'){init();}else{document.addEventListener('DOMContentLoaded',init);}
async function init(){
  await Promise.all([loadModels(),loadCategories()]);
  try{const h=await(await fetch(API+'/health')).json();if(h.status==='ok')document.getElementById('badgeConnected').style.display='';}catch(e){}
}

async function loadModels(){
  const sel=document.getElementById('modelSelect');
  const chips=document.getElementById('modelChips');
  try{
    const data=await(await fetch(API+'/models')).json();
    if(data.error){sel.innerHTML='<option disabled>'+data.error+'</option>';chips.innerHTML='';return;}
    const models=data.models;
    if(!models||!models.length){sel.innerHTML='<option disabled>No models found</option>';chips.innerHTML='';return;}
    sel.innerHTML='';
    models.forEach((m,i)=>{const o=document.createElement('option');o.value=m.name;o.textContent=m.name+(m.size_gb?' ('+m.size_gb+' GB)':'');if(i===0)o.selected=true;sel.appendChild(o)});
    chips.innerHTML='';
    models.slice(0,8).forEach(m=>{const c=document.createElement('span');c.className='chip';c.textContent=m.name.split(':')[0];c.onclick=()=>{sel.value=m.name;document.querySelectorAll('#modelChips .chip').forEach(x=>x.classList.remove('active'));c.classList.add('active')};chips.appendChild(c)});
  }catch(e){sel.innerHTML='<option disabled>Error loading models</option>';chips.innerHTML='';}
}

async function loadCategories(){
  try{
    const data=await(await fetch(API+'/categories')).json();
    const sel=document.getElementById('categorySelect');sel.innerHTML='';
    data.categories.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=c;sel.appendChild(o)});
    const chips=document.getElementById('categoryChips');chips.innerHTML='';
    data.categories.forEach(c=>{const ch=document.createElement('span');ch.className='chip';ch.textContent=c;ch.onclick=()=>{sel.value=c};chips.appendChild(ch)});
  }catch(e){}
}

function toggleFetchMode(){
  const m=document.getElementById('fetchMode').value;
  document.getElementById('categorySection').style.display=m==='category'?'':'none';
  document.getElementById('rawQuerySection').style.display=m==='raw_query'?'':'none';
}
function applyPreset(type){
  document.getElementById('fetchMode').value='raw_query';toggleFetchMode();
  const p={
    infra:JSON.stringify({query:{bool:{must:[{term:{activity_type:'infra'}},{exists:{field:'infra_type'}},{exists:{field:'location_name'}}],must_not:[{term:{form_status:5}}]}},size:10000,track_total_hits:true},null,2),
    deployment:JSON.stringify({query:{bool:{must:[{exists:{field:'enemy_formation_name'}},{exists:{field:'location_name'}},{terms:{activity_type.keyword:['deployment','disposition','movement']}}],must_not:[{term:{form_status:5}}]}},size:10000,track_total_hits:true},null,2),
    all:JSON.stringify({query:{bool:{must_not:[{term:{form_status:5}}]}},size:10000,track_total_hits:true},null,2)
  };
  document.getElementById('rawQueryEditor').value=p[type]||p.all;
}

async function startSession(){
  const sid=document.getElementById('sessionId').value.trim()||'chat-'+Date.now();
  const model=document.getElementById('modelSelect').value;
  const timeout=parseInt(document.getElementById('llmTimeout').value)||120;
  const maxTurns=parseInt(document.getElementById('maxTurns').value)||10;
  const mode=document.getElementById('fetchMode').value;
  const category=document.getElementById('categorySelect').value;
  const dateFrom=document.getElementById('dateFrom').value||null;
  const dateTo=document.getElementById('dateTo').value||null;
  let rawQuery=null;
  if(mode==='raw_query'){try{rawQuery=JSON.parse(document.getElementById('rawQueryEditor').value||'{}')}catch(e){showNotice('Invalid JSON: '+e.message,'error');return}}
  try{
    showNotice('Creating session...','info');
    let resp=await fetch(API+'/session/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sid,llm_model:model,llm_timeout:timeout,max_turns:maxTurns})});
    if(!resp.ok){const d=await resp.json();if(resp.status===409){await fetch(API+'/session/reset?session_id='+sid,{method:'POST'})}else throw new Error(d.detail||'Failed')}
    sessionId=sid;currentModel=model;
  }catch(e){showNotice('Session error: '+e.message,'error');return}
  try{
    showNotice('Fetching data from Elasticsearch...','info');
    const body={mode,category:mode==='category'?category:null,raw_query:mode==='raw_query'?rawQuery:null,date_from:dateFrom,date_to:dateTo};
    const resp=await fetch(API+'/session/fetch?session_id='+sessionId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!resp.ok)throw new Error((await resp.json()).detail||'Fetch failed');
    const data=await resp.json();
    showNotice('✅ Loaded '+data.total_hits.toLocaleString()+' docs → '+data.documents_stored.toLocaleString()+' unique','success');
    document.getElementById('setupOverlay').classList.add('hidden');
    document.getElementById('chatInput').disabled=false;
    document.getElementById('sendBtn').disabled=false;
    document.getElementById('badgeDocs').style.display='';
    document.getElementById('badgeDocs').textContent=data.documents_stored.toLocaleString()+' docs';
    document.getElementById('badgeModel').style.display='';
    document.getElementById('badgeModel').textContent=model.split(':')[0];
    document.getElementById('inputHint').textContent=data.documents_stored.toLocaleString()+' docs · '+model+' · Type a question';
    document.getElementById('headerSub').textContent=data.documents_stored.toLocaleString()+' documents loaded · '+model;
    document.getElementById('chatContainer').innerHTML='';
    addBotMessage('✅ Data loaded! **'+data.total_hits.toLocaleString()+'** documents fetched, **'+data.documents_stored.toLocaleString()+'** unique after dedup.'+(data.warnings.length?'\n\n⚠️ '+data.warnings.join('\n⚠️ '):'')+'\n\nAsk me anything — locations, formations, equipment, infrastructure, activities.');
    document.getElementById('chatInput').focus();
  }catch(e){showNotice('Fetch error: '+e.message,'error')}
}

async function sendMessage(){
  const input=document.getElementById('chatInput');
  const q=input.value.trim();
  if(!q||isLoading)return;
  input.value='';autoResize(input);
  isLoading=true;document.getElementById('sendBtn').disabled=true;
  addUserMessage(q);
  const tid=addTypingMessage();
  try{
    const useDebug=document.getElementById('useDebug').checked;
    const resp=await fetch(API+'/session/ask?session_id='+sessionId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,debug:useDebug,mediate:true})});
    if(!resp.ok)throw new Error((await resp.json()).detail||'Failed');
    const data=await resp.json();
    removeTyping(tid);
    addBotMessage(data.answer,data.sources_used,data.debug);
  }catch(e){
    removeTyping(tid);
    addBotMessage('❌ Error: '+e.message,0,null,true);
    showNotice('Error: '+e.message,'error');
  }
  isLoading=false;document.getElementById('sendBtn').disabled=false;document.getElementById('chatInput').focus();
}

function addUserMessage(text){
  const cc=document.getElementById('chatContainer');
  const d=document.createElement('div');
  d.className='msg user';
  d.innerHTML='<div class="msg-avatar">👤</div><div class="msg-content"><div class="msg-meta">You · '+new Date().toLocaleTimeString()+'</div><div class="msg-bubble">'+escHtml(text)+'</div></div>';
  cc.appendChild(d);cc.scrollTop=cc.scrollHeight;
}

function addBotMessage(text,sources,debug,isError){
  const cc=document.getElementById('chatContainer');
  const d=document.createElement('div');
  d.className='msg bot';
  let html=formatMarkdown(text);
  let sh='';
  if(sources&&sources>0){sh='<div class="sources-row"><span class="sources-chip">📄 '+sources+' source'+(sources>1?'s':'')+'</span>';if(debug&&debug.mode)sh+='<span class="sources-chip">⚡ '+debug.mode+'</span>';if(debug&&debug.total)sh+='<span class="sources-chip">📊 '+debug.total.toLocaleString()+' hits</span>';sh+='</div>'}
  let dh='';
  if(debug&&document.getElementById('useDebug').checked)dh='<div class="progress-log done" style="margin-top:8px;font-size:10px">⚡ '+JSON.stringify(debug).substring(0,200)+'</div>';
  d.innerHTML='<div class="msg-avatar">🤖</div><div class="msg-content"><div class="msg-meta">Assistant · '+new Date().toLocaleTimeString()+' · '+currentModel.split(':')[0]+'</div><div class="msg-bubble"'+(isError?' style="color:var(--red)"':'')+'>'+html+'</div>'+sh+dh+'</div>';
  cc.appendChild(d);cc.scrollTop=cc.scrollHeight;
}

function addTypingMessage(){
  const cc=document.getElementById('chatContainer');
  const id='typing-'+Date.now();
  const d=document.createElement('div');d.className='msg bot';d.id=id;
  d.innerHTML='<div class="msg-avatar">🤖</div><div class="msg-content"><div class="msg-bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div></div>';
  cc.appendChild(d);cc.scrollTop=cc.scrollHeight;return id;
}
function removeTyping(id){const el=document.getElementById(id);if(el)el.remove()}

function formatMarkdown(text){
  text=escHtml(text);
  text=text.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  text=text.replace(/`([^`]+)`/g,'<code>$1</code>');
  text=text.replace(/^([•\-*] .+)$/gm,'<li>$1</li>');
  text=text.replace(/(<li>.*<\/li>\n?)+/g,function(m){return '<ul>'+m+'</ul>'});
  text=text.replace(/\n\n/g,'</p><p>');
  text=text.replace(/\n/g,'<br>');
  if(!text.startsWith('<'))text='<p>'+text+'</p>';
  text=text.replace(/<\/ul>\s*<ul>/g,'');
  return text;
}
function escHtml(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function handleInputKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage()}}
function autoResize(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,120)+'px';}
function showSetup(){document.getElementById('setupOverlay').classList.remove('hidden')}
function showNotice(text,type){
  const b=document.getElementById('noticeBar');b.textContent=text;b.className='notice-bar '+type;
  if(type==='success'||type==='info')setTimeout(()=>{if(b.textContent===text)b.className='notice-bar'},6000);
}
</script>
</body>
</html>"""
