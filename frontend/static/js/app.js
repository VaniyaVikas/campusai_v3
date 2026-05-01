/* =============================================================
   CampusAI v6.0 — Complete JavaScript
   File: frontend/static/js/app.js
   ============================================================= */
'use strict';

// ── State ─────────────────────────────────────────────────────
const App = {
  user: null, userType: null,
  lang: 'en', theme: localStorage.getItem('cam-theme')||'dark',
  speaking: false, mic: null, busy: false,
  stageTimer: null, stageIdx: 0,
  msgData: {},   // store response data per message
};

const AGENTS = [
  {id:'query',     icon:'🔍', name:'Query Agent',     desc:'Language + intent'},
  {id:'policy',    icon:'📚', name:'Policy Agent',    desc:'FAISS + BM25 search'},
  {id:'decision',  icon:'⚖️',  name:'Decision Agent',  desc:'Apply policy rules'},
  {id:'action',    icon:'⚡',  name:'Action Agent',    desc:'Generate response'},
  {id:'supervisor',icon:'🛡️', name:'Supervisor',      desc:'Validate + approve'},
];

const CHIPS = {
  en:['ATKT eligibility?','Fee deadline?','Hall ticket?','Attendance policy?','Placement criteria?','Scholarship info?'],
  gu:['ATKT mate eligible chhu?','Fees ni tarikh?','Hall ticket kyare?','Attendance nathi chhe?','Placement mate su joie?'],
  hi:['ATKT ke liye eligible hun?','Fees kab bharna?','Hall ticket kab milega?','Placement criteria kya hai?'],
};

const OUTCOME_ICON = {allowed:'✅',not_allowed:'❌',conditional:'⚠️',insufficient_info:'ℹ️'};

// ── Helpers ───────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const esc = s => String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const fmt = () => new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'});
const fmtD = iso => { try{return new Date(iso).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'});}catch{return '';} };
const fmtDT= iso => { try{return new Date(iso).toLocaleString('en-IN',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});}catch{return '';} };

async function api(path, method='GET', body=null) {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (!r.ok) {
    const e = await r.json().catch(()=>({detail:'Server error'}));
    throw new Error(e.detail||`Error ${r.status}`);
  }
  return r.json();
}

// ── Toast ─────────────────────────────────────────────────────
function toast(msg, type='info') {
  const w = $('toast-wrap');
  const t = document.createElement('div');
  const ic = type==='ok'?'✓':type==='err'?'✕':'ℹ';
  t.className = `toast ${type}`;
  t.innerHTML = `${ic} ${esc(msg)}`;
  w.appendChild(t);
  setTimeout(()=>{ t.style.opacity='0'; t.style.transition='.3s'; setTimeout(()=>t.remove(),300); }, 3500);
}

// ── Theme ─────────────────────────────────────────────────────
function applyTheme() {
  document.body.classList.toggle('light', App.theme==='light');
  const b=$('theme-btn'); if(b) b.textContent=App.theme==='dark'?'🌙':'☀️';
}
function toggleTheme() {
  App.theme=App.theme==='dark'?'light':'dark';
  localStorage.setItem('cam-theme',App.theme); applyTheme();
}

// ── Navigation ────────────────────────────────────────────────
function showPage(id) {
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t=>t.classList.remove('active'));
  const pg=$('pg-'+id); if(pg) pg.classList.add('active');
  document.querySelectorAll(`.nav-tab[data-page="${id}"]`).forEach(t=>t.classList.add('active'));
  const loaders={dashboard:loadDashboard,history:loadHistory,profile:loadProfile,
                 tickets:loadMyTickets,policies:loadPolicies,analytics:loadAnalytics,admin:loadAdmin};
  if (loaders[id]) loaders[id]();
  if (id==='tools') switchToolTab('health');
}

// ── Login ─────────────────────────────────────────────────────
let _ltype = 'student';

function setLType(t) {
  _ltype = t;
  document.querySelectorAll('.ltab').forEach(b=>b.classList.remove('active'));
  $('ltab-'+t).classList.add('active');
  $('l-label').textContent = t==='student'?'Student ID':'Admin ID';
  $('l-id').placeholder   = t==='student'?'e.g. S001':'e.g. A001';
  const hints={
    student:'🎓 Demo: <strong>S001/pass123</strong> (Arjun) · <strong>S002/pass123</strong> (Priya) · <strong>S003/pass123</strong> (Rohan)',
    admin:'⚙️ Demo: <strong>A001/admin123</strong> (Dr. Rajesh Kumar — Superadmin)'
  };
  $('demo-hint').innerHTML = hints[t];
}

async function doLogin() {
  const uid=($('l-id').value||'').trim(), pw=($('l-pass').value||'').trim();
  const err=$('l-err');
  if(!uid||!pw){err.style.display='block';err.textContent='Enter ID and Password';return;}
  const btn=$('l-btn'); btn.disabled=true; btn.textContent='Logging in…'; err.style.display='none';
  try {
    const d = await api('/auth/login','POST',{user_id:uid,password:pw,user_type:_ltype});
    App.user=d.user; App.userType=d.user_type;
    setupNav(); showPage('chat');
    toast(`Namaste, ${App.user.name.split(' ')[0]}! 👋`,'ok');
  } catch(e) {
    err.style.display='block'; err.textContent='❌ '+e.message;
  }
  btn.disabled=false; btn.textContent='Login →';
}

function logout() {
  App.user=null; App.userType=null;
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  $('pg-login').classList.add('active');
  $('nav-main').style.display='none';
  $('user-chip').style.display='none';
  $('logout-btn').style.display='none';
  toast('Logged out','info');
}

function setupNav() {
  const u=App.user;
  $('nav-main').style.display='flex';
  $('user-chip').style.display='flex';
  $('logout-btn').style.display='flex';
  const init=u.name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
  $('nav-av').textContent=init;
  $('nav-av').className=`uav ${App.userType==='admin'?'uav-a':'uav-s'}`;
  $('nav-uname').textContent=u.name.split(' ')[0];
  const rt=$('nav-rtag');
  rt.textContent=App.userType; rt.className=`rtag rt-${App.userType==='admin'?'a':'s'}`;
  $('tab-admin').style.display=App.userType==='admin'?'flex':'none';
  if(u.email){const el=$('c-email');if(el)el.value=u.email;}
  if(u.name) {const el=$('c-name'); if(el)el.value=u.name;}
}

// ── Language ──────────────────────────────────────────────────
function setLang(lang) {
  App.lang=lang;
  document.querySelectorAll('.lbtn').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll(`.lbtn[data-lang="${lang}"]`).forEach(b=>b.classList.add('active'));
  buildChips();
  const ph={en:'Ask anything — exam, fees, ATKT, placement, attendance…',
            gu:'Taro sawal puchho — ATKT, fees, attendance, placement…',
            hi:'Kuch bhi pucho — exam, fees, ATKT, placement…'};
  $('c-input').placeholder=ph[lang]||ph.en;
}
function buildChips() {
  $('chips').innerHTML=(CHIPS[App.lang]||CHIPS.en).map(q=>
    `<span class="chip" onclick="useChip(this)">${esc(q)}</span>`
  ).join('');
}
function useChip(el){$('c-input').value=el.textContent;$('c-input').focus();}

// ── Agents ────────────────────────────────────────────────────
function buildAgents() {
  $('alist').innerHTML=AGENTS.map(a=>
    `<div class="aitem idle" id="ag-${a.id}">
       <div class="adot"></div>
       <div><div class="aname">${a.icon} ${a.name}</div><div class="adesc">${a.desc}</div></div>
     </div>`
  ).join('');
}
function setAgent(id,st){const el=$(`ag-${id}`);if(el)el.className=`aitem ${st}`;}
function startPipeline() {
  App.stageIdx=0; AGENTS.forEach(a=>setAgent(a.id,'idle'));
  App.stageTimer=setInterval(()=>{
    if(App.stageIdx>0) setAgent(AGENTS[App.stageIdx-1].id,'done');
    if(App.stageIdx<AGENTS.length){setAgent(AGENTS[App.stageIdx].id,'running');App.stageIdx++;}
    else clearInterval(App.stageTimer);
  },680);
}
function stopPipeline(ok){clearInterval(App.stageTimer);AGENTS.forEach(a=>setAgent(a.id,ok?'done':'error'));}

// ── Chat ──────────────────────────────────────────────────────
function renderUserMsg(text) {
  const msgs=$('chat-msgs');
  const init=App.user?.name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase()||'?';
  const t=App.userType==='admin'?'admin':'student';
  const d=document.createElement('div'); d.className='mrow mine';
  d.innerHTML=`<div class="mav mav-${t==='admin'?'a':'s'}">${init}</div>
    <div class="mbody"><div class="mbubble">${esc(text)}</div><div class="mtime">${fmt()}</div></div>`;
  msgs.appendChild(d); msgs.scrollTop=msgs.scrollHeight;
}

function renderTyping() {
  const msgs=$('chat-msgs'), id='typ-'+Date.now();
  const d=document.createElement('div'); d.id=id; d.className='typing-row';
  d.innerHTML=`<div class="mav mav-ai">🤖</div>
    <div class="typing-bubble"><div class="tdot"></div><div class="tdot"></div><div class="tdot"></div></div>`;
  msgs.appendChild(d); msgs.scrollTop=msgs.scrollHeight; return id;
}

function renderAIMsg(text, data) {
  const msgs=$('chat-msgs');
  const msgId='m-'+Date.now()+'-'+Math.random().toString(36).slice(2,6);
  App.msgData[msgId]=data||{response:text};

  // Admin sees technical details, student sees clean response
  const isAdmin=App.userType==='admin';
  let extras='';

  if(data && isAdmin) {
    const outcome=(data.decision_outcome||'').replace('DecisionOutcome.','');
    const lang=(data.language_detected||'').replace('Language.','');
    const emotion=data.emotion_detected||'neutral';
    const conf=Math.round((data.decision_confidence||0)*100);
    const cc=conf>=80?'var(--grn)':conf>=55?'var(--amb)':'var(--red)';
    const emc=['urgent','frustrated'].includes(emotion)?'cred':'csec';
    extras+=`<div class="flex gap6" style="flex-wrap:wrap">
      <span class="badge b-medium">🌐 ${esc(lang)}</span>
      <span class="badge b-low">${esc((data.intent||'').replace(/_/g,' '))}</span>
      <span class="badge b-closed ${emc}">💭 ${esc(emotion)}</span>
      <span class="badge b-closed">⏱ ${data.processing_time_ms||0}ms</span>
    </div>`;
    if(outcome){
      const refs=(data.policy_references||[]).length;
      extras+=`<div class="flex aic gap8" style="padding:10px 14px;background:var(--bg4);border:1px solid var(--bd);border-radius:var(--r)">
        <div style="font-size:1.3rem">${OUTCOME_ICON[outcome]||'❓'}</div>
        <div><div class="fw6" style="color:${outcome==='allowed'?'var(--grn)':outcome==='not_allowed'?'var(--red)':outcome==='conditional'?'var(--amb)':'var(--tx2)'};text-transform:capitalize">${outcome.replace(/_/g,' ')}</div>
          <div class="csec mono" style="font-size:11px">${refs} polic${refs===1?'y':'ies'} checked</div></div>
        <div style="margin-left:auto;text-align:right"><div class="fw7" style="font-size:1.1rem;color:${cc}">${conf}%</div>
          <div class="cmut mono" style="font-size:10px">confidence</div></div>
      </div>`;
    }
  }
  if(data?.form_suggestion) extras+=`<div class="form-tag">📋 Suggested: <strong>${esc(data.form_suggestion)}</strong></div>`;

  extras+=`<div class="mactions">
    <button class="mact ma-copy"  onclick="cpMsg('${msgId}')">📋 Copy</button>
    <button class="mact ma-dl"    onclick="dlMsg('${msgId}')">📄 Download</button>
    <button class="mact ma-speak" onclick="spkMsg('${msgId}')" id="spk-${msgId}">🔊 Speak</button>
  </div>`;

  const d=document.createElement('div'); d.className='mrow ai';
  d.innerHTML=`<div class="mav mav-ai">🤖</div>
    <div class="mbody">
      <div class="mbubble">${esc(text)}</div>
      ${extras?`<div class="mextra">${extras}</div>`:''}
      <div class="mtime">${fmt()}</div>
    </div>`;
  msgs.appendChild(d); msgs.scrollTop=msgs.scrollHeight;
}

// ── Copy / Download / Speak ───────────────────────────────────
function cpMsg(id){copyText((App.msgData[id]||{}).response||'');}
function dlMsg(id){downloadResp(App.msgData[id]||{});}
function spkMsg(id){speakText((App.msgData[id]||{}).response||'',id);}

function copyText(text){
  if(navigator.clipboard){navigator.clipboard.writeText(String(text||'')).then(()=>toast('Copied!','ok')).catch(()=>fbCopy(text));}
  else fbCopy(text);
}
function fbCopy(text){
  const ta=document.createElement('textarea');
  ta.value=String(text||''); ta.style.cssText='position:fixed;opacity:0';
  document.body.appendChild(ta); ta.select();
  try{document.execCommand('copy');toast('Copied!','ok');}catch{toast('Copy failed','err');}
  document.body.removeChild(ta);
}
function downloadResp(data){
  try{
    const d=(typeof data==='string')?JSON.parse(data):data;
    const lines=[
      '╔══════════════════════════════════════════╗',
      '║   CampusAI v6.0 — Query Response         ║',
      '╚══════════════════════════════════════════╝',
      '',`Ticket   : ${d.ticket_id||'N/A'}`,
      `Date     : ${new Date().toLocaleString()}`,
      `Language : ${(d.language_detected||'').replace('Language.','')}`,
      `Intent   : ${(d.intent||'').replace(/_/g,' ')}`,
      `Emotion  : ${d.emotion_detected||'neutral'}`,
      '',
      '──────────────────────────────────────────',
      'DECISION',
      '──────────────────────────────────────────',
      `Outcome  : ${(d.decision_outcome||'').replace(/_/g,' ').toUpperCase()}`,
      `Confidence: ${Math.round((d.decision_confidence||0)*100)}%`,
      `Approved : ${d.supervisor_approved?'Yes':'No'}`,
      d.decision_reasoning?`Reasoning: ${d.decision_reasoning}`:'',
      d.conditions?`Conditions: ${d.conditions}`:'',
      d.form_suggestion?`Form: ${d.form_suggestion}`:'',
      '',
      '──────────────────────────────────────────',
      'RESPONSE',
      '──────────────────────────────────────────',
      '',d.response||'',
      '',
      '──────────────────────────────────────────',
      'POLICIES: '+(d.policy_references||[]).join(', ')||'None',
      '',
      '══════════════════════════════════════════',
      `CampusAI v6.0 | ${new Date().toLocaleString()}`,
    ].filter(x=>x!==undefined&&x!==null).join('\n');
    const blob=new Blob([lines],{type:'text/plain;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url; a.download=`CampusAI_${d.ticket_id||'response'}_${Date.now()}.txt`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
    toast('Downloaded!','ok');
  }catch(e){toast('Download failed: '+e.message,'err');}
}
function speakText(text,msgId){
  if(!('speechSynthesis' in window)){toast('Voice not supported','err');return;}
  if(App.speaking){window.speechSynthesis.cancel();App.speaking=false;
    const b=document.getElementById('spk-'+msgId);if(b)b.textContent='🔊 Speak';return;}
  const u=new SpeechSynthesisUtterance(String(text||'').slice(0,400));
  u.lang=App.lang==='gu'?'gu-IN':App.lang==='hi'?'hi-IN':'en-IN';
  u.rate=1.0;u.pitch=1.0;
  u.onend=()=>{App.speaking=false;const b=document.getElementById('spk-'+msgId);if(b)b.textContent='🔊 Speak';};
  App.speaking=true;
  const b=document.getElementById('spk-'+msgId);if(b)b.textContent='⏹ Stop';
  window.speechSynthesis.speak(u);
}

// ── Voice Input ───────────────────────────────────────────────
function toggleMic(){
  const btn=$('mic-btn');
  if(!('webkitSpeechRecognition' in window||'SpeechRecognition' in window)){toast('Voice not supported','err');return;}
  if(App.mic){App.mic.stop();App.mic=null;btn.classList.remove('active');return;}
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  App.mic=new SR(); App.mic.lang=App.lang==='gu'?'gu-IN':App.lang==='hi'?'hi-IN':'en-IN';
  App.mic.continuous=false; App.mic.interimResults=false;
  App.mic.onresult=e=>{$('c-input').value=e.results[0][0].transcript;btn.classList.remove('active');App.mic=null;toast('🎙️ Captured!','ok');};
  App.mic.onerror=App.mic.onend=()=>{btn.classList.remove('active');App.mic=null;};
  App.mic.start(); btn.classList.add('active'); toast('🎙️ Listening…','info');
}

// ── Send Message ──────────────────────────────────────────────
async function sendMsg(){
  const ta=$('c-input'), q=ta.value.trim();
  if(!q||App.busy) return;
  ta.value=''; ta.style.height='44px'; App.busy=true; $('send-btn').disabled=true;
  renderUserMsg(q); const typId=renderTyping(); startPipeline();
  try{
    const body={query:q,user_id:App.user?.student_id||App.user?.admin_id||null,
                user_type:App.userType||'student',
                student_email:$('c-email')?.value?.trim()||null,
                student_name:$('c-name')?.value?.trim()||null,
                session_id:'sess-'+Date.now()};
    const data=await api('/query','POST',body);
    stopPipeline(true); document.getElementById(typId)?.remove();
    renderAIMsg(data.response||'Please contact helpdesk@college.edu', data);
  }catch(e){
    stopPipeline(false); document.getElementById(typId)?.remove();
    renderAIMsg('Sorry, I\'m having trouble right now. Please try again or contact helpdesk@college.edu.', null);
    toast('Error: '+e.message,'err');
  }
  App.busy=false; $('send-btn').disabled=false;
}

function initChatInput(){
  const ta=$('c-input'); if(!ta) return;
  ta.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}});
  ta.addEventListener('input',()=>{ta.style.height='44px';ta.style.height=Math.min(ta.scrollHeight,130)+'px';});
}

// ── Dashboard ─────────────────────────────────────────────────
async function loadDashboard(){
  const u=App.user; if(!u) return;
  $('dash-name').textContent=u.name?.split(' ')[0]||'User';
  if(App.userType==='student'){
    const cc=v=>v>=8?'var(--grn)':v>=6?'var(--amb)':'var(--red)';
    const ac=v=>v>=75?'var(--grn)':v>=60?'var(--amb)':'var(--red)';
    $('dash-stats').innerHTML=[
      {e:'📊',v:u.cgpa,     l:'CGPA',       c:cc(u.cgpa),   p:(u.cgpa/10)*100},
      {e:'📅',v:u.attendance+'%',l:'Attendance',c:ac(u.attendance),p:u.attendance},
      {e:'⚠️',v:u.backlogs,  l:'Backlogs',   c:u.backlogs>0?'var(--red)':'var(--grn)',p:0},
      {e:'💰',v:'₹'+(u.fees_due||0).toLocaleString(),l:'Fees Due',c:u.fees_due>0?'var(--red)':'var(--grn)',p:0},
      {e:'🎓',v:'Sem '+u.semester,l:'Semester',c:'var(--blue)',p:0},
      {e:'🏛️',v:(u.department||'—').split(' ')[0],l:'Department',c:'var(--pur)',p:0},
    ].map(s=>`<div class="scard"><div class="semi">${s.e}</div><div class="sval" style="color:${s.c}">${esc(String(s.v))}</div><div class="slbl">${s.lbl||s.l}</div>${s.p>0?`<div class="sbar"><div class="sbarfill" style="width:${Math.min(s.p,100).toFixed(1)}%;background:${s.c}"></div></div>`:''}</div>`).join('');

    const alerts=[];
    if(u.backlogs>0) alerts.push(`<div class="alert awarn">⚠️ ${u.backlogs} backlog(s) — Register for ATKT before deadline!</div>`);
    if(u.fees_due>0) alerts.push(`<div class="alert adanger">💸 Fees due: ₹${Number(u.fees_due).toLocaleString()} — Pay before April 15!</div>`);
    if(u.cgpa>=8.5)  alerts.push(`<div class="alert agood">🏆 Merit Scholarship eligible — CGPA ${u.cgpa} ≥ 8.5!</div>`);
    if(u.attendance<75&&u.attendance>=60) alerts.push(`<div class="alert awarn">⚠️ Attendance ${u.attendance}% below required 75%!</div>`);
    const ab=$('dash-alerts'); if(ab) ab.innerHTML=alerts.join('');
  } else {
    try{
      const [an,ss,tk]=await Promise.all([api('/analytics'),api('/students'),api('/tickets')]);
      $('dash-stats').innerHTML=[
        {e:'💬',v:an.total_queries||0,l:'Total Queries',c:'var(--blue)'},
        {e:'👥',v:ss.total||0,       l:'Students',     c:'var(--grn)'},
        {e:'🎫',v:tk.total||0,       l:'Tickets',      c:'var(--amb)'},
        {e:'📊',v:(an.top_intents||[]).length,l:'Intent Types',c:'var(--pur)'},
      ].map(s=>`<div class="scard"><div class="semi">${s.e}</div><div class="sval" style="color:${s.c}">${s.v}</div><div class="slbl">${s.l}</div></div>`).join('');
    }catch{}
  }
  try{const d=await api('/deadlines'); renderDeadlines(d.deadlines||[]);}catch{}
  try{const n=await api('/notices');   renderNotices(n.notices||[]);}catch{}
}

function renderDeadlines(arr){
  const el=$('dash-deadlines'); if(!el) return;
  if(!arr.length){el.innerHTML='<div class="empty"><span class="ei">📅</span><p>No upcoming deadlines</p></div>';return;}
  el.innerHTML=arr.slice(0,6).map(d=>{
    const dt=new Date(d.deadline_date);
    return`<div class="dlitem${d.urgent?' urgent':''}">
      <div class="dldate"><div class="mon">${dt.toLocaleString('en',{month:'short'}).toUpperCase()}</div><div class="day">${dt.getDate()}</div></div>
      <div class="dlinfo"><div class="dlt">${esc(d.title)}</div><div class="dls">${esc(d.department||'')} · ${esc(d.event_type||'')}</div></div>
      ${d.urgent?'<span class="utag">Urgent</span>':''}
    </div>`;
  }).join('');
}
function renderNotices(arr){
  const el=$('dash-notices'); if(!el) return;
  if(!arr.length){el.innerHTML='<div class="empty"><span class="ei">📢</span><p>No notices</p></div>';return;}
  el.innerHTML=arr.slice(0,5).map(n=>`
    <div class="ncard ${n.priority==='high'?'high':''}">
      <div class="nt">${esc(n.title)}</div>
      <div class="nb">${esc(n.content||'')}</div>
      <div class="nm">📌 ${esc(n.posted_by||'')} · ${esc(n.department||'')} · ${fmtD(n.created_at)}</div>
    </div>`).join('');
}

// ── Profile ───────────────────────────────────────────────────
function loadProfile(){
  const u=App.user; if(!u||App.userType!=='student') return;
  const cc=v=>v>=8?'var(--grn)':v>=6?'var(--amb)':'var(--red)';
  const ac=v=>v>=75?'var(--grn)':v>=60?'var(--amb)':'var(--red)';
  const init=u.name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
  const alerts=[];
  if(u.backlogs>0)   alerts.push(`<div class="alert awarn">⚠️ ${u.backlogs} backlog(s) pending</div>`);
  if(u.fees_due>0)   alerts.push(`<div class="alert adanger">💸 Fees due: ₹${Number(u.fees_due).toLocaleString()}</div>`);
  if(u.cgpa>=8.5)    alerts.push(`<div class="alert agood">🏆 Merit Scholarship eligible!</div>`);
  if(u.attendance<75&&u.attendance>=60) alerts.push(`<div class="alert awarn">⚠️ Low attendance: ${u.attendance}%</div>`);
  $('profile-content').innerHTML=`
  <div class="prolayout">
    <div class="procard">
      <div class="proav">${init}</div>
      <div class="proname">${esc(u.name)}</div>
      <div class="proid">${esc(u.student_id)}</div>
      <div class="prodept">${esc(u.department||'')}</div>
      <div class="minigrid">
        <div class="ministat"><div class="val" style="color:${cc(u.cgpa)}">${u.cgpa}</div><div class="lbl">CGPA</div></div>
        <div class="ministat"><div class="val">Sem ${u.semester}</div><div class="lbl">Semester</div></div>
        <div class="ministat"><div class="val" style="color:${u.backlogs>0?'var(--red)':'var(--grn)'}">${u.backlogs}</div><div class="lbl">Backlogs</div></div>
        <div class="ministat"><div class="val" style="color:${ac(u.attendance)}">${u.attendance}%</div><div class="lbl">Attendance</div></div>
      </div>
      <div class="progs">
        <div class="progrow"><span>CGPA</span><span style="color:${cc(u.cgpa)}">${u.cgpa}/10</span></div>
        <div class="progt"><div class="progf" style="width:${(u.cgpa/10*100).toFixed(1)}%;background:${cc(u.cgpa)}"></div></div>
        <div class="progrow"><span>Attendance</span><span style="color:${ac(u.attendance)}">${u.attendance}%</span></div>
        <div class="progt"><div class="progf" style="width:${Math.min(u.attendance,100)}%;background:${ac(u.attendance)}"></div></div>
        <div class="progrow"><span>Fees Paid</span><span class="cgrn">₹${Number(u.fees_paid||0).toLocaleString()}</span></div>
        <div class="progt"><div class="progf" style="width:${u.fees_paid&&u.fees_due?Math.round(u.fees_paid/(u.fees_paid+u.fees_due)*100):u.fees_due===0?100:0}%;background:var(--grn)"></div></div>
      </div>
    </div>
    <div class="fc gap12">
      ${alerts.length?`<div>${alerts.join('')}</div>`:''}
      <div class="card">
        <div class="ctitle">📋 Academic Information</div>
        ${[['Name',u.name],['Student ID',u.student_id],['Email',u.email],['Department',u.department],
           ['Semester',u.semester],['CGPA',u.cgpa],['Backlogs',u.backlogs],['Attendance',u.attendance+'%'],['Phone',u.phone||'—']]
          .map(([l,v])=>`<div class="irow2"><span class="ilbl">${l}</span><span class="ival">${esc(String(v??'—'))}</span></div>`).join('')}
      </div>
      <div class="card">
        <div class="ctitle">💰 Fee Status</div>
        <div class="irow2"><span class="ilbl">Fees Paid</span><span class="ival cgrn">₹${Number(u.fees_paid||0).toLocaleString()}</span></div>
        <div class="irow2"><span class="ilbl">Fees Due</span><span class="ival" style="color:${u.fees_due>0?'var(--red)':'var(--grn)'}">₹${Number(u.fees_due||0).toLocaleString()}</span></div>
        <div class="irow2"><span class="ilbl">Status</span><span class="ival" style="color:${u.fees_due>0?'var(--red)':'var(--grn)'}">${u.fees_due>0?'⚠️ Pending':'✅ Clear'}</span></div>
      </div>
    </div>
  </div>`;
}

// ── History ───────────────────────────────────────────────────
async function loadHistory(){
  const uid=App.user?.student_id||App.user?.admin_id; if(!uid) return;
  const el=$('history-list'); el.innerHTML='<div class="empty"><span class="ei">⌛</span><p>Loading…</p></div>';
  try{
    const d=await api(`/history/${uid}?limit=40`);
    const hist=d.history||[];
    if(!hist.length){el.innerHTML='<div class="empty"><span class="ei">🕐</span><p>No chat history yet</p></div>';return;}
    const bmap={'allowed':'b-resolved','not_allowed':'b-open','conditional':'b-in_progress'};
    el.innerHTML=hist.map(h=>{
      const dec=(h.decision||'').replace('DecisionOutcome.','');
      return`<div class="hitem">
        <div class="hitop"><div class="hiq">${esc(h.query)}</div>
          <div class="flex gap6">${dec?`<span class="badge ${bmap[dec]||'b-closed'}">${dec.replace(/_/g,' ')}</span>`:''}<span class="badge b-closed">${Math.round((h.confidence||0)*100)}%</span></div>
        </div>
        <div class="hire">${esc(h.response||'')}</div>
        <div class="hifoot"><span>🌐 ${esc(h.language||'en')}</span>·<span>${esc((h.intent||'').replace(/_/g,' '))}</span>·<span>${fmtDT(h.timestamp)}</span></div>
      </div>`;
    }).join('');
  }catch(e){el.innerHTML=`<div class="empty"><span class="ei">⚠️</span><p>${esc(e.message)}</p></div>`;}
}

// ── My Tickets ────────────────────────────────────────────────
async function loadMyTickets(){
  const sid=App.user?.student_id; if(!sid||App.userType!=='student') return;
  const el=$('tickets-list');
  try{const d=await api(`/tickets/student/${sid}`); renderTkCards(d.tickets||[],el,false);}
  catch(e){el.innerHTML=`<div class="empty"><span class="ei">⚠️</span><p>${esc(e.message)}</p></div>`;}
}
function renderTkCards(tickets,container,adminMode){
  if(!container) return;
  if(!tickets.length){container.innerHTML='<div class="empty"><span class="ei">🎫</span><p>No tickets found</p></div>';return;}
  container.innerHTML=tickets.map(t=>`
    <div class="tkcard">
      <div class="tkhd"><span class="tkid">${esc(t.ticket_id)}</span>
        <div class="tkbadges"><span class="badge b-${t.status||'open'}">${(t.status||'open').replace('_',' ')}</span><span class="badge b-${t.priority||'medium'}">${t.priority||'medium'}</span></div>
      </div>
      <div class="tksub">${esc(t.subject||'')}</div>
      <div class="tkmeta">${esc(t.department||'')} · ${esc(t.student_id||'')} · ${fmtD(t.created_at)}</div>
      ${t.description?`<div class="tkdesc">${esc(t.description.slice(0,160))}${t.description.length>160?'…':''}</div>`:''}
      ${t.resolution?`<div class="tkres">✓ ${esc(t.resolution)}</div>`:''}
      ${adminMode&&t.status!=='resolved'?`<button class="btn btn-p btn-sm mt8" onclick="resolveTicket('${esc(t.ticket_id)}',this)">✓ Mark Resolved</button>`:''}
    </div>`).join('');
}
async function resolveTicket(tid,btn){
  btn.disabled=true; btn.textContent='Resolving…';
  try{await api(`/tickets/${tid}`,'PATCH',{status:'resolved',resolution:'Resolved by admin.'});toast('Resolved!','ok');loadAdminTickets();}
  catch(e){toast('Error: '+e.message,'err');btn.disabled=false;btn.textContent='✓ Mark Resolved';}
}

// ── Policies ──────────────────────────────────────────────────
async function loadPolicies(){
  const el=$('polgrid'); el.innerHTML='<div class="empty"><span class="ei">⌛</span><p>Loading…</p></div>';
  try{
    const d=await api('/policies'); const pols=d.policies||[];
    if(!pols.length){el.innerHTML='<div class="empty"><span class="ei">📂</span><p>No policy files</p></div>';return;}
    const ic={exam:'📝',admin:'🏛️',placement:'💼',general:'📄'};
    el.innerHTML=pols.map(p=>`
      <div class="polcard">
        <div class="policon pi-${p.department||'general'}">${ic[p.department]||'📄'}</div>
        <div class="polname" title="${esc(p.name)}">${esc(p.name)}</div>
        <div class="poldesc">${esc(p.description||'')}</div>
        <div class="polfoot"><span class="poltag">${esc(p.department)}</span><span class="cmut mono" style="font-size:10px">${p.size_kb}KB</span></div>
      </div>`).join('');
  }catch{el.innerHTML='<div class="empty"><span class="ei">📂</span><p>Could not load</p></div>';}
}
async function reindex(){
  toast('Re-indexing started (~30 sec)…','info');
  try{await api('/ingest','POST');toast('Re-indexing started!','ok');setTimeout(loadPolicies,10000);}
  catch{toast('Run: python tools/ingest_policies.py','err');}
}

// ── Analytics ─────────────────────────────────────────────────
async function loadAnalytics(){
  const el=$('analytics-content'); el.innerHTML='<div class="empty"><span class="ei">⌛</span><p>Loading…</p></div>';
  try{
    const d=await api('/analytics');
    const ii=d.top_intents||[],ll=d.languages||[],dd=d.daily||[],tt=d.ticket_stats||[],dp=d.dept_load||[];
    const mi=Math.max(...ii.map(x=>x.c),1),ml=Math.max(...ll.map(x=>x.c),1),md=Math.max(...dd.map(x=>x.c),1);
    el.innerHTML=`
      <div class="sgrid mb16">
        <div class="scard"><div class="semi">💬</div><div class="sval">${d.total_queries||0}</div><div class="slbl">Total Queries</div></div>
        <div class="scard"><div class="semi">🎯</div><div class="sval">${ii.length}</div><div class="slbl">Intent Types</div></div>
        <div class="scard"><div class="semi">🌐</div><div class="sval">${ll.length}</div><div class="slbl">Languages</div></div>
        <div class="scard"><div class="semi">🎫</div><div class="sval">${tt.reduce((a,t)=>a+t.c,0)}</div><div class="slbl">Total Tickets</div></div>
      </div>
      <div class="agrid">
        <div class="card" style="grid-column:1/-1">
          <div class="ctitle">📈 Daily Query Volume</div>
          <div class="daycols">${[...dd].reverse().map(d=>`<div class="daycol"><div class="daycol-bar" style="height:${Math.max(6,Math.round((d.c/md)*80))}px" title="${d.day}: ${d.c}"></div><div class="daycol-lbl">${(d.day||'').slice(5)}</div></div>`).join('')||'<div class="cmut">No data yet</div>'}</div>
        </div>
        <div class="card"><div class="ctitle">🎯 Top Intents</div>${ii.map(x=>`<div class="barrow"><div class="barlbl">${esc((x.intent||'').replace(/_/g,' '))}</div><div class="bart"><div class="barf" style="width:${Math.round(x.c/mi*100)}%;background:var(--blue)"></div></div><div class="barcnt">${x.c}</div></div>`).join('')||'<div class="cmut">No data yet</div>'}</div>
        <div class="card"><div class="ctitle">🌐 Languages</div>${ll.map(x=>`<div class="barrow"><div class="barlbl">${esc(x.language||'')}</div><div class="bart"><div class="barf" style="width:${Math.round(x.c/ml*100)}%;background:var(--grn)"></div></div><div class="barcnt">${x.c}</div></div>`).join('')||'<div class="cmut">No data yet</div>'}</div>
        <div class="card"><div class="ctitle">🎫 Ticket Status</div>${tt.map(t=>{const c={open:'var(--red)',resolved:'var(--grn)',in_progress:'var(--amb)',closed:'var(--tx3)'}[t.status]||'var(--blue)';return`<div class="barrow"><div class="barlbl">${esc((t.status||'').replace(/_/g,' '))}</div><div class="bart"><div class="barf" style="width:100%;background:${c}"></div></div><div class="barcnt">${t.c}</div></div>`;}).join('')||'<div class="cmut">No tickets yet</div>'}</div>
        <div class="card"><div class="ctitle">🏛️ Dept Load</div>${dp.map(x=>`<div class="barrow"><div class="barlbl">${esc(x.department||'')}</div><div class="bart"><div class="barf" style="width:${Math.round(x.c/Math.max(...dp.map(d=>d.c),1)*100)}%;background:var(--pur)"></div></div><div class="barcnt">${x.c}</div></div>`).join('')||'<div class="cmut">No data yet</div>'}</div>
      </div>`;
  }catch{el.innerHTML='<div class="empty"><span class="ei">📊</span><p>No analytics yet. Send queries first!</p></div>';}
}

// ── Admin ─────────────────────────────────────────────────────
let _atab='students';
function loadAdmin(){if(App.userType!=='admin') return; switchAdminTab('students');}
function switchAdminTab(tab){
  _atab=tab;
  document.querySelectorAll('.atab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll(`.atab[data-atab="${tab}"]`).forEach(t=>t.classList.add('active'));
  document.querySelectorAll('.admin-sec').forEach(s=>s.style.display='none');
  const sec=$('as-'+tab); if(sec) sec.style.display='block';
  if(tab==='students') loadAdminStudents();
  if(tab==='tickets')  loadAdminTickets();
  if(tab==='queries')  loadAdminQueries();
  if(tab==='notices')  loadAdminNotices();
}

async function loadAdminStudents(){
  try{
    const d=await api('/students'); const tbody=$('admin-tbody');
    if(!d.students?.length){tbody.innerHTML='<tr><td colspan="9" style="text-align:center;padding:24px;color:var(--tx3)">No students</td></tr>';return;}
    tbody.innerHTML=d.students.map(s=>{
      const cc=s.cgpa>=8?'var(--grn)':s.cgpa>=6?'var(--amb)':'var(--red)';
      return`<tr>
        <td class="mono cblue">${esc(s.student_id)}</td>
        <td class="fw6">${esc(s.name)}</td>
        <td class="csec">${esc(s.department||'')}</td>
        <td style="text-align:center;color:var(--tx2)">${s.semester}</td>
        <td style="text-align:center;font-weight:600;color:${cc}">${s.cgpa}</td>
        <td style="text-align:center;color:${s.backlogs>0?'var(--red)':'var(--grn)'}">${s.backlogs}</td>
        <td style="text-align:center;color:${s.attendance>=75?'var(--grn)':'var(--red)'}">${s.attendance}%</td>
        <td style="text-align:center;color:${s.fees_due>0?'var(--red)':'var(--grn)'}">₹${Number(s.fees_due||0).toLocaleString()}</td>
        <td><button class="btn btn-d btn-sm" onclick="delStudent('${esc(s.student_id)}','${esc(s.name)}')">🗑️</button></td>
      </tr>`;
    }).join('');
  }catch(e){toast('Error: '+e.message,'err');}
}
async function loadAdminTickets(){
  const el=$('admin-tklist')||$('as-tickets');
  try{const d=await api('/tickets'); renderTkCards(d.tickets||[],el,true);}
  catch(e){if(el)el.innerHTML=`<div class="empty"><span class="ei">⚠️</span><p>${esc(e.message)}</p></div>`;}
}
async function loadAdminQueries(){
  const el=$('admin-qlist'); if(!el) return;
  el.innerHTML='<div class="empty"><span class="ei">⌛</span><p>Loading…</p></div>';
  try{
    const d=await api('/history?limit=60'); const hist=d.history||[];
    if(!hist.length){el.innerHTML='<div class="empty"><span class="ei">💬</span><p>No queries yet</p></div>';return;}
    const bmap={'allowed':'b-resolved','not_allowed':'b-open','conditional':'b-in_progress'};
    el.innerHTML=hist.map(h=>{
      const dec=(h.decision||'').replace('DecisionOutcome.','');
      return`<div class="hitem"><div class="hitop"><div class="hiq">${esc(h.query)}</div><span class="badge ${bmap[dec]||'b-closed'}">${dec.replace(/_/g,' ')||'unknown'}</span></div>
        <div class="hire">${esc(h.response||'')}</div>
        <div class="hifoot"><span>👤 ${esc(h.user_id||'anon')}</span>·<span>🌐 ${esc(h.language||'')}</span>·<span>${esc((h.intent||'').replace(/_/g,' '))}</span>·<span>${fmtDT(h.timestamp)}</span></div>
      </div>`;
    }).join('');
  }catch(e){el.innerHTML=`<div class="empty"><span class="ei">⚠️</span><p>${esc(e.message)}</p></div>`;}
}
async function loadAdminNotices(){
  const el=$('admin-nlist'); if(!el) return;
  try{
    const d=await api('/notices');
    el.innerHTML=d.notices?.length?d.notices.map(n=>`
      <div class="ncard ${n.priority==='high'?'high':''}">
        <div class="flex jb mb8"><div class="nt">${esc(n.title)}</div><span class="badge b-${n.priority==='high'?'high':'medium'}">${n.priority}</span></div>
        <div class="nb">${esc(n.content||'')}</div>
        <div class="nm">${esc(n.posted_by||'')} · ${esc(n.department||'')} · ${fmtD(n.created_at)}</div>
      </div>`).join(''):'<div class="empty" style="padding:1.5rem"><span class="ei">📢</span><p>No notices yet</p></div>';
  }catch{}
}

// Student modals
function showAddStudent(){$('modal-student').classList.add('open');}
function hideAddStudent(){$('modal-student').classList.remove('open');$('form-student')?.reset();}
async function submitAddStudent(){
  const data={student_id:$('ns-id').value.trim(),name:$('ns-name').value.trim(),
    email:$('ns-email').value.trim(),password:$('ns-pass').value.trim(),
    department:$('ns-dept').value,semester:parseInt($('ns-sem').value)||1,
    cgpa:parseFloat($('ns-cgpa').value)||0,attendance:parseFloat($('ns-att').value)||75,
    fees_due:parseFloat($('ns-fdue').value)||0,backlogs:parseInt($('ns-back').value)||0,
    phone:$('ns-phone').value.trim()};
  if(!data.student_id||!data.name||!data.email||!data.password){toast('Fill required fields','err');return;}
  try{await api('/students','POST',data);toast(`Student ${data.student_id} added!`,'ok');hideAddStudent();loadAdminStudents();}
  catch(e){toast('Error: '+e.message,'err');}
}
async function delStudent(sid,name){
  if(!confirm(`Delete ${name} (${sid})?`)) return;
  try{await api(`/students/${sid}`,'DELETE');toast('Deleted','ok');loadAdminStudents();}
  catch(e){toast('Error: '+e.message,'err');}
}

// Notice modals
function showPostNotice(){$('modal-notice').classList.add('open');}
function hidePostNotice(){$('modal-notice').classList.remove('open');$('form-notice')?.reset();}
async function submitNotice(){
  const data={title:$('n-title').value.trim(),content:$('n-content').value.trim(),
    posted_by:App.user?.name||'Admin',department:$('n-dept').value.trim()||'All',priority:$('n-priority').value};
  if(!data.title||!data.content){toast('Fill title and content','err');return;}
  try{await api('/notices','POST',data);toast('Notice posted!','ok');hidePostNotice();loadAdminNotices();}
  catch(e){toast('Error: '+e.message,'err');}
}

// ── Tools ─────────────────────────────────────────────────────
let _ttab='health';
function switchToolTab(tab){
  _ttab=tab;
  document.querySelectorAll('#pg-tools .atab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll(`#pg-tools .atab[data-atab="${tab}"]`).forEach(t=>t.classList.add('active'));
  document.querySelectorAll('.toolsec').forEach(s=>s.classList.remove('active'));
  const sec=$('ts-'+tab); if(sec) sec.classList.add('active');
  if(tab==='health') loadHealth();
  if(tab==='ingest') loadToolPolicies();
  if(tab==='cli')    buildCliChips();
  if(tab==='traces') loadTraces();
}
async function loadHealth(){
  const el=$('health-content'); if(!el) return;
  try{
    const d=await api('/health');
    const ic=d.index_loaded?'✅ Loaded':d.index_exists?'⚠️ Exists, not loaded':'❌ Not found — run ingest!';
    const icc=d.index_loaded?'cgrn':d.index_exists?'camb':'cred';
    el.innerHTML=`
      <div class="irow2"><span class="ilbl">Status</span><span class="ival cgrn fw6">✅ Online</span></div>
      <div class="irow2"><span class="ilbl">Version</span><span class="ival mono">${esc(d.version||'6.0.0')}</span></div>
      <div class="irow2"><span class="ilbl">LLM Model</span><span class="ival mono cblue">${esc(d.model||'')}</span></div>
      <div class="irow2"><span class="ilbl">Fast Model</span><span class="ival mono csec">${esc(d.fast_model||'')}</span></div>
      <div class="irow2"><span class="ilbl">FAISS Index</span><span class="ival ${icc}">${ic}</span></div>
      <div class="irow2"><span class="ilbl">Traces Stored</span><span class="ival">${d.traces||0}</span></div>
      <div class="irow2"><span class="ilbl">Checked At</span><span class="ival mono csec">${fmt()}</span></div>`;
  }catch(e){el.innerHTML=`<div class="alert adanger">❌ Server offline: ${esc(e.message)}</div>`;}
}
async function loadToolPolicies(){
  const el=$('tool-pols'); if(!el) return;
  try{
    const d=await api('/policies');
    el.innerHTML=(d.policies||[]).map(p=>`
      <div class="irow2"><span class="ilbl mono trunc" style="max-width:200px" title="${esc(p.name)}">${esc(p.name)}</span>
        <span class="flex gap6 aic"><span class="badge b-medium">${esc(p.department)}</span><span class="cmut mono" style="font-size:11px">${p.size_kb}KB</span></span>
      </div>`).join('')||'<div class="empty"><p>No policy files</p></div>';
  }catch{el.innerHTML='<div class="empty"><p>Could not load</p></div>';}
}
async function toolIngest(){
  const btn=$('ingest-btn'),st=$('ingest-status');
  btn.disabled=true; btn.textContent='⏳ Indexing…';
  st.innerHTML='<div class="alert awarn">⏳ Re-indexing started. Wait ~30 seconds…</div>';
  try{
    await api('/ingest','POST');
    st.innerHTML='<div class="alert agood">✅ Re-indexing started! Reload policies in ~30 sec.</div>';
    setTimeout(()=>{loadToolPolicies();loadPolicies();},12000);
  }catch(e){st.innerHTML=`<div class="alert adanger">❌ ${esc(e.message)}<br/>Run: <code>python tools/ingest_policies.py --force</code></div>`;}
  setTimeout(()=>{btn.disabled=false;btn.textContent='🔄 Start Re-Indexing';},5000);
}
async function toolSendEmail(){
  const to=$('te-to')?.value.trim(),sub=$('te-sub')?.value.trim(),body=$('te-body')?.value.trim();
  const st=$('email-status'),btn=$('email-btn');
  if(!to){toast('Enter recipient email','err');return;}
  btn.disabled=true; btn.textContent='⏳ Sending…';
  st.innerHTML='<div class="alert awarn">⏳ Sending…</div>';
  try{
    const d=await api('/query','POST',{query:`Send test email: ${body}`,student_email:to,student_name:'Test User',user_type:'student'});
    st.innerHTML=`<div class="alert agood">✅ Query sent! Ticket: <strong>${esc(d.ticket_id)}</strong><br/>Email will send if SMTP is configured in .env</div>`;
  }catch(e){st.innerHTML=`<div class="alert adanger">❌ ${esc(e.message)}</div>`;}
  btn.disabled=false; btn.textContent='📤 Send Test';
}

const CLI_SAMPLES=['Am I eligible for ATKT? I have 3 backlogs.','ATKT form bharva eligible chhu?','What is minimum attendance?','Placement criteria kya hai?','Hall ticket kyare malse?','Fees ni last date?'];
function buildCliChips(){
  const el=$('cli-chips'); if(!el) return;
  el.innerHTML=CLI_SAMPLES.map(q=>`<span class="chip" onclick="$('cli-q').value=this.textContent;$('cli-q').focus()">${esc(q)}</span>`).join('');
}
async function toolRunQuery(){
  const q=($('cli-q')?.value||'').trim(); if(!q){toast('Enter a query','err');return;}
  const btn=$('cli-btn'),res=$('cli-result');
  btn.disabled=true; btn.textContent='⏳ Running…';
  res.innerHTML='<div class="alert awarn">⏳ Running 5-agent pipeline…</div>';
  try{
    const d=await api('/query','POST',{query:q,student_email:$('cli-email')?.value.trim()||null,student_name:$('cli-name')?.value.trim()||null,user_type:App.userType||'student',user_id:App.user?.student_id||App.user?.admin_id||null});
    const oc=d.decision_outcome||'';
    const oc_c={allowed:'var(--grn)',not_allowed:'var(--red)',conditional:'var(--amb)',insufficient_info:'var(--tx2)'}[oc]||'var(--blue)';
    const conf=Math.round((d.decision_confidence||0)*100);
    const cc=conf>=80?'var(--grn)':conf>=55?'var(--amb)':'var(--red)';
    const rid='cli-'+Date.now(); App.msgData[rid]=d;
    res.innerHTML=`<div class="card">
      <div class="ctitle">📊 Pipeline Result — ${esc(d.ticket_id)}</div>
      <div class="g2 mb12">
        <div>
          <div class="flbl2 mb8">Detection</div>
          <div class="irow2"><span class="ilbl">Language</span><span class="ival mono">${esc((d.language_detected||'').replace('Language.',''))}</span></div>
          <div class="irow2"><span class="ilbl">Intent</span><span class="ival mono">${esc((d.intent||'').replace(/_/g,' '))}</span></div>
          <div class="irow2"><span class="ilbl">Emotion</span><span class="ival">${esc(d.emotion_detected||'neutral')}</span></div>
          <div class="irow2"><span class="ilbl">Time</span><span class="ival mono">${d.processing_time_ms||0}ms</span></div>
        </div>
        <div>
          <div class="flbl2 mb8">Decision</div>
          <div class="irow2"><span class="ilbl">Outcome</span><span class="ival fw6" style="color:${oc_c}">${esc(oc.replace(/_/g,' '))}</span></div>
          <div class="irow2"><span class="ilbl">Confidence</span><span class="ival fw6" style="color:${cc}">${conf}%</span></div>
          <div class="irow2"><span class="ilbl">Supervisor</span><span class="ival" style="color:${d.supervisor_approved?'var(--grn)':'var(--red)'}">${d.supervisor_approved?'✅ Approved':'❌ Rejected'}</span></div>
          <div class="irow2"><span class="ilbl">Policies</span><span class="ival">${(d.policy_references||[]).length} matched</span></div>
        </div>
      </div>
      ${d.decision_reasoning?`<div class="mb12"><div class="flbl2 mb8">Reasoning</div><div style="font-size:13px;color:var(--tx2);padding:10px 13px;background:var(--bg4);border-radius:var(--rs);line-height:1.6">${esc(d.decision_reasoning)}</div></div>`:''}
      <div class="mb12"><div class="flbl2 mb8">AI Response</div><div style="font-size:14px;padding:12px 15px;background:var(--bg3);border:1px solid var(--bd);border-radius:var(--r);line-height:1.7">${esc(d.response||'')}</div></div>
      ${d.form_suggestion?`<div class="form-tag mb12">📋 Form: <strong>${esc(d.form_suggestion)}</strong></div>`:''}
      <div class="mactions"><button class="mact ma-copy" onclick="cpMsg('${rid}')">📋 Copy</button><button class="mact ma-dl" onclick="dlMsg('${rid}')">📄 Download</button></div>
    </div>`;
  }catch(e){res.innerHTML=`<div class="alert adanger">❌ ${esc(e.message)}</div>`;}
  btn.disabled=false; btn.textContent='▶ Run Pipeline';
}
async function loadTraces(){
  const el=$('traces-list'); if(!el) return;
  el.innerHTML='<div class="empty"><span class="ei">⌛</span><p>Loading…</p></div>';
  try{
    const d=await api('/traces?limit=20'); const traces=[...d.traces||[]].reverse();
    if(!traces.length){el.innerHTML='<div class="empty"><span class="ei">🔍</span><p>No traces yet</p></div>';return;}
    el.innerHTML=traces.map(t=>{
      const dec=t.state?.decision||{};
      const oc=String(dec.outcome||'').replace('DecisionOutcome.','');
      const conf=Math.round((dec.confidence||0)*100);
      const occ={allowed:'b-resolved',not_allowed:'b-open',conditional:'b-in_progress'}[oc]||'b-closed';
      return`<div style="background:var(--bg4);border:1px solid var(--bd);border-radius:var(--r);margin-bottom:9px;overflow:hidden">
        <div style="padding:10px 14px;background:var(--bg3);border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap">
          <span class="mono cblue" style="font-size:11px">${esc(t.ticket_id)}</span>
          <div class="flex gap6"><span class="badge ${occ}">${esc(oc.replace(/_/g,' '))||'unknown'}</span><span class="cmut mono" style="font-size:10.5px">${t.elapsed_ms||0}ms</span></div>
        </div>
        <div style="padding:11px 14px;font-size:13px;font-weight:500">${esc(t.state?.raw_query||t.request?.query||'')}</div>
        <div style="padding:0 14px 10px;display:flex;gap:8px;flex-wrap:wrap;font-family:var(--fm);font-size:11px">
          <span style="color:var(--pur)">🌐 ${esc(t.state?.detected_language||'')}</span>
          <span class="cblue">🎯 ${esc((t.state?.intent||'').replace(/_/g,' '))}</span>
          <span style="color:${t.state?.supervisor_approved?'var(--grn)':'var(--red)'}">${t.state?.supervisor_approved?'✅':'❌'} Supervisor</span>
          <span class="cred">${Math.round((dec.confidence||0)*100)}% conf</span>
        </div>
        <div style="padding:0 14px 12px;font-size:12.5px;color:var(--tx2);line-height:1.6;border-top:1px solid var(--bd);padding-top:10px">${esc((t.state?.final_response||'').slice(0,200))}${(t.state?.final_response||'').length>200?'…':''}</div>
      </div>`;
    }).join('');
  }catch(e){el.innerHTML=`<div class="alert adanger">❌ ${esc(e.message)}</div>`;}
}

// ── Health Check ──────────────────────────────────────────────
async function checkHealth(){
  const dot=$('sdot'),txt=$('stxt');
  try{
    const d=await api('/health');
    dot.className='sdot online';
    txt.textContent=d.model.replace('llama-','').replace('-versatile','')+(d.index_loaded?' ✓':' · No Index');
  }catch{dot.className='sdot error';txt.textContent='Offline';}
}

// Modal overlay close
document.addEventListener('click',e=>{if(e.target.classList.contains('moverlay'))e.target.classList.remove('open');});

// ── Init ──────────────────────────────────────────────────────
function init(){
  applyTheme(); buildAgents(); buildChips(); initChatInput();
  checkHealth(); setInterval(checkHealth,30000);
}
document.addEventListener('DOMContentLoaded', init);
