/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Horizon Video Downloader v5 — App Controller
   Tab switching · Segmented toggles · Playlist fetch + select · WS · DL Cards
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

/* ─── Icons ──────────────────────────────────────────────────── */
const IC={
  pause:'<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>',
  play:'<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="6 3 20 12 6 21"/></svg>',
  x:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  check:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  err:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
  stop:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
  folder:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
  tOk:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>',
  tErr:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
  tInfo:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
  qr:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>',
  trash:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>'
};
const DONE=new Set(['completed','error','cancelled']);
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function fmtDur(s){
  if(!s||isNaN(s))return'';
  s=Math.floor(s);
  const h=Math.floor(s/3600);
  const m=Math.floor((s%3600)/60);
  const sec=s%60;
  if(h>0)return`${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
  return`${m}:${String(sec).padStart(2,'0')}`;
}
function fmtViews(n){
  if(!n||isNaN(n))return'';
  if(n>=1000000)return(n/1000000).toFixed(1).replace(/\.0$/,'')+'M views';
  if(n>=1000)return(n/1000).toFixed(1).replace(/\.0$/,'')+'K views';
  return n.toLocaleString()+' views';
}
function fmtBytes(b){
  if(!b||isNaN(b)||b<=0)return'';
  const units=['B','KB','MB','GB','TB'];
  let i=0,val=b;
  while(val>=1024&&i<units.length-1){val/=1024;i++;}
  return `${val.toFixed(i===0?0:1)} ${units[i]}`;
}

/* ─── WebSocket ──────────────────────────────────────────────── */
class WS{
  constructor(onMsg,onOpen,onClose){this._m=onMsg;this._o=onOpen;this._c=onClose;this._ws=null;this._d=1000;this._t=null;this._dead=false;}
  connect(){this._dead=false;try{this._ws=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws`);}catch{this._retry();return;}
    this._ws.onopen=()=>{this._d=1000;this._o?.();};
    this._ws.onmessage=e=>{try{this._m?.(JSON.parse(e.data));}catch{}};
    this._ws.onclose=()=>{this._c?.();if(!this._dead)this._retry();};
    this._ws.onerror=()=>{};}
  close(){this._dead=true;clearTimeout(this._t);this._ws?.close();}
  _retry(){clearTimeout(this._t);this._t=setTimeout(()=>{this._d=Math.min(this._d*1.5,30000);this.connect();},this._d);}
}

/* ─── Download Card ──────────────────────────────────────────── */
class DLCard{
  constructor(d){this.id=d.task_id;this._s='';this.el=this._mk(d);this.update(d);}
  _mk(d){const c=document.createElement('div');c.className='dl-card glass-panel';c.dataset.taskId=this.id;c.dataset.status=d.status||'queued';
    c.innerHTML=`<div class="dl-head"><div class="dl-info"><span class="dl-name">${esc(d.filename||'Initializing…')}</span><span class="dl-meta">${d.format_type==='audio'?'Audio':'Video'}</span></div><div class="dl-actions"><button class="dl-btn pr-btn" title="Pause" type="button">${IC.pause}</button><button class="dl-btn qr-btn" title="QR Code / Mobile Transfer" type="button" style="display:none;font-weight:bold;font-size:12px;">QR</button><button class="dl-btn fld-btn" title="Open Folder" type="button" style="display:none">${IC.folder}</button><button class="dl-btn x-btn" title="Cancel" type="button">${IC.x}</button></div><span class="dl-badge"></span></div><div class="dl-progress"><div class="dl-track"><div class="dl-fill"></div></div><div class="dl-stats"><span class="dl-pct">0%</span><span class="dl-size" style="color:var(--text-2); font-weight:500;"></span><span class="dl-spd" style="color:var(--accent);"></span><span class="dl-eta"></span></div></div><div class="dl-err" style="display:none"></div>`;
    this.$={nm:c.querySelector('.dl-name'),act:c.querySelector('.dl-actions'),badge:c.querySelector('.dl-badge'),fill:c.querySelector('.dl-fill'),pct:c.querySelector('.dl-pct'),size:c.querySelector('.dl-size'),spd:c.querySelector('.dl-spd'),eta:c.querySelector('.dl-eta'),er:c.querySelector('.dl-err'),pr:c.querySelector('.pr-btn'),fld:c.querySelector('.fld-btn'),xb:c.querySelector('.x-btn'),qr:c.querySelector('.qr-btn')};
    this.$.pr.onclick=()=>this._pr();this.$.fld.onclick=()=>this._fld();this.$.xb.onclick=()=>this._cx();this.$.qr.onclick=()=>this._qr();return c;}
  update(d){const prevStatus=this._s;this._s=d.status;this.el.dataset.status=d.status;
    if(d.filename)this.$.nm.textContent=d.filename;
    const progress = Math.min(100, Math.max(0, d.progress != null ? Number(d.progress) : 0));
    this.$.fill.style.width=`${progress}%`;
    this.$.pct.textContent=`${Math.round(progress)}%`;

    if(d.downloaded_bytes > 0){
      const cur = fmtBytes(d.downloaded_bytes);
      const tot = d.total_bytes > 0 ? fmtBytes(d.total_bytes) : '';
      this.$.size.textContent = tot ? `${cur} / ${tot}` : cur;
    } else {
      this.$.size.textContent = '';
    }

    this.$.spd.textContent=d.speed||'';
    this.$.eta.textContent=d.eta?(d.eta.startsWith('ETA')?d.eta:`ETA ${d.eta}`):'';
    if(d.status==='downloading'){this._show(true);this.$.pr.innerHTML=IC.pause;this.$.pr.title='Pause';this.$.pr.style.display='flex';this.$.xb.style.display='flex';this.$.fld.style.display='none';this.$.badge.className='dl-badge';}
    else if(d.status==='converting'){this._show(true);this.$.pr.style.display='none';this.$.xb.style.display='flex';this.$.fld.style.display='none';this.$.spd.textContent='';this.$.eta.textContent='Finalizing video...';this.$.pct.textContent='Processing';this._bdg('converting','Converting',IC.tInfo);}
    else if(d.status==='paused'){this._show(true);this.$.pr.innerHTML=IC.play;this.$.pr.title='Resume';this.$.pr.style.display='flex';this.$.xb.style.display='flex';this.$.fld.style.display='none';this._bdg('paused','Paused',IC.pause);}
    else if(d.status==='paused (game mode)'){this._show(true);this.$.pr.innerHTML=IC.play;this.$.pr.title='Resume';this.$.pr.style.display='flex';this.$.xb.style.display='flex';this.$.fld.style.display='none';this._bdg('paused','Game Mode',IC.pause);}
    else if(d.status==='completed'){this._show(true);this.$.pr.style.display='none';this.$.xb.style.display='none';this.$.fld.style.display='flex';this.$.qr.style.display='flex';this.$.spd.textContent='';this.$.eta.textContent='';this.$.fill.style.width='100%';this.$.pct.textContent='100%';this._bdg('done','Done',IC.check);if(d.progress>=99&&!d.is_restored)App.notify(d.filename||'File');}
    else if(d.status==='error'){this._show(true);this.$.pr.innerHTML=IC.play;this.$.pr.title='Retry / Resume';this.$.pr.style.display='flex';this.$.xb.style.display='flex';this.$.fld.style.display='none';this.$.qr.style.display='none';this.$.spd.textContent='';this.$.eta.textContent='';this._bdg('err','Error',IC.err);if(d.error_message){this.$.er.textContent=d.error_message;this.$.er.style.display='block';}}
    else if(d.status==='cancelled'){this._show(false);this.$.spd.textContent='';this.$.eta.textContent='';this._bdg('stopped','Cancelled',IC.stop);}
    else if(d.status==='queued'){this.$.pct.textContent='Queued';this.$.fill.style.width='0%';}
    if(!d.is_restored&&d.filename&&d.status&&(prevStatus!==d.status||d.status==='completed'||d.status==='error'))App.log(`[${d.task_id?.slice(0,8)}] ${d.status} — ${d.filename}${d.progress!=null?' ('+Math.round(d.progress)+'%)':''}${d.speed?' @ '+d.speed:''}`);}
  async _pr(){const ep=(this._s==='paused'||this._s==='paused (game mode)'||this._s==='error')?'resume':'pause';try{const r=await fetch(`/api/${ep}/${this.id}`,{method:'POST'});if(!r.ok)App.toast((await r.json()).error,'err');else if(ep==='resume')App.toast('Resuming download...','ok');}catch{App.toast('Network error','err');}}
  async _cx(){try{const r=await fetch(`/api/cancel/${this.id}`,{method:'POST'});if(!r.ok)App.toast((await r.json()).error,'err');}catch{App.toast('Network error','err');}}
  async _fld(){try{const r=await fetch(`/api/open-folder/${this.id}`,{method:'POST'});if(!r.ok)App.toast((await r.json()).error,'err');}catch{App.toast('Network error','err');}}
  _qr(){
    App.showQR(this.id);
  }
  _show(a){this.$.act.style.display=a?'flex':'none';if(!a)this.$.badge.classList.add('show');else this.$.badge.classList.remove('show');}
  _bdg(c,t,i){this.$.badge.className=`dl-badge show ${c}`;this.$.badge.innerHTML=`${i}<span>${t}</span>`;}
  get done(){return DONE.has(this._s);}
}

/* ═══════════════════ APP ═══════════════════ */
const App={
  cards:new Map(),
  ws:null,
  singleMode:'video',  // current segmented state for Single tab
  plMode:'video',       // current segmented state for Playlist action bar
  plEntries:[],         // fetched playlist data
  notified:new Set(),   // prevent duplicate desktop notifications
  themes:{
    'violet-cyan':{
      '--accent':'#8b5cf6','--accent-h':'#a78bfa','--accent-dim':'rgba(139,92,246,.12)',
      '--grad':'linear-gradient(135deg,#8b5cf6,#06b6d4)','--grad-h':'linear-gradient(90deg,#8b5cf6,#06b6d4)'
    },
    'spotify':{
      '--accent':'#1db954','--accent-h':'#1ed760','--accent-dim':'rgba(29,185,84,.12)',
      '--grad':'linear-gradient(135deg,#1db954,#191414)','--grad-h':'linear-gradient(90deg,#1db954,#1ed760)'
    },
    'crimson':{
      '--accent':'#e11d48','--accent-h':'#fb7185','--accent-dim':'rgba(225,29,72,.12)',
      '--grad':'linear-gradient(135deg,#e11d48,#be123c)','--grad-h':'linear-gradient(90deg,#e11d48,#fb7185)'
    },
    'amber':{
      '--accent':'#d97706','--accent-h':'#f59e0b','--accent-dim':'rgba(217,119,6,.12)',
      '--grad':'linear-gradient(135deg,#d97706,#b45309)','--grad-h':'linear-gradient(90deg,#d97706,#f59e0b)'
    },
    'aurora':{
      '--accent':'#78ffd6','--accent-h':'#a8ff78','--accent-dim':'rgba(120,255,214,.12)',
      '--grad':'linear-gradient(135deg,#a8ff78,#78ffd6)','--grad-h':'linear-gradient(90deg,#a8ff78,#78ffd6)'
    }
  },

  /* ── Init ────────────────────────────────────────────── */
  init(){
    this._loadPersistedSettings();
    this._bindTabs();
    this._bindSegmented('single-seg',m=>{this.singleMode=m;this._toggleSingleOpts();});
    this._bindSegmented('pl-seg',m=>{this.plMode=m;this._togglePlOpts();});
    this._bindPaste();
    this._bindSingleDL();
    this._bindPlaylist();
    this._bindSocial();
    this._bindSniffer();
    this._bindThumbnail();
    this._bindHistoryView();
    this._bindCreatorWatchlist();
    this._bindAppUpdate();
    this._bindLog();
    this._bindSettings();
    this._bindTheme();
    this._bindClipboard();
    this._connectWS();
    if(window.Notification&&Notification.permission==='default')Notification.requestPermission();
    
    // QR Modal close & copy
    const qrModal = document.getElementById('qr-modal');
    const qrClose = document.getElementById('qr-close');
    const qrCopy = document.getElementById('qr-copy-btn');
    if(qrClose && qrModal){
      qrClose.onclick = () => { qrModal.classList.add('hidden'); qrModal.style.display = 'none'; };
      qrModal.onclick = (e) => {
        if(e.target === qrModal) { qrModal.classList.add('hidden'); qrModal.style.display = 'none'; }
      };
    }
    if(qrCopy){
      qrCopy.onclick = async () => {
        const input = document.getElementById('qr-url-input');
        if(input && input.value && !input.value.startsWith('Generating')){
          try {
            await navigator.clipboard.writeText(input.value);
            this.toast('Download link copied!', 'ok');
          } catch {
            input.select();
            document.execCommand('copy');
            this.toast('Link copied!', 'ok');
          }
        }
      };
    }

    // Clear History Button
    const btnClearHist = document.getElementById('btn-clear-history');
    if(btnClearHist){
      btnClearHist.onclick = async () => {
        if(!confirm("Are you sure you want to clear your download history?")) return;
        try{
          const r = await fetch('/api/history/clear', {method:'POST'});
          if(r.ok){
            this.toast('History cleared', 'ok');
            this._loadHistory();
          } else {
            this.toast('Failed to clear history', 'err');
          }
        }catch{
          this.toast('Network error', 'err');
        }
      };
    }

    // Do not restore old completed downloads into the active feed on startup
    this._empty();
  },

  showQR(taskId){
    const mod = document.getElementById('qr-modal');
    const img = document.getElementById('qr-image');
    const input = document.getElementById('qr-url-input');
    if(!mod || !img) return;
    img.src = `/api/qrcode/${taskId}?t=${Date.now()}`;
    if(input) input.value = 'Generating transfer link...';
    fetch(`/api/transfer-info/${taskId}`)
      .then(async r => {
        if(!r.ok){
          const err = await r.json().catch(()=>({}));
          if(input) input.value = err.error || 'File not found on disk';
          return;
        }
        return r.json();
      })
      .then(d => {
        if(d && d.url && input) input.value = d.url;
      })
      .catch(() => {
        if(input) input.value = 'Error generating transfer link';
      });
    mod.classList.remove('hidden');
    mod.style.display = 'flex';
  },

  async openFolder(taskId){
    try{
      const r = await fetch(`/api/open-folder/${taskId}`, {method:'POST'});
      if(!r.ok){
        const err = await r.json().catch(()=>({}));
        this.toast(err.error || 'Could not open folder', 'err');
      }
    }catch{
      this.toast('Network error', 'err');
    }
  },

  async openFile(taskId){
    try{
      const r = await fetch(`/api/open-file/${taskId}`, {method:'POST'});
      if(!r.ok){
        const err = await r.json().catch(()=>({}));
        this.toast(err.error || 'Could not open media file', 'err');
      }
    }catch{
      this.toast('Network error', 'err');
    }
  },

  async deleteHistoryItem(taskId){
    if(!confirm('Delete this item from history? (File on disk is preserved)')) return;
    try{
      const r = await fetch(`/api/history/delete/${taskId}`, {method:'POST'});
      if(r.ok){
        this.toast('Download removed from history', 'info');
        this._loadHistory();
      } else {
        const err = await r.json().catch(()=>({}));
        this.toast(err.error || 'Failed to delete history item', 'err');
      }
    }catch{
      this.toast('Network error', 'err');
    }
  },

  /* ── Tabs ────────────────────────────────────────────── */
  _bindTabs(){
    const btns=document.querySelectorAll('.tab-btn'),panels=document.querySelectorAll('.tab-panel');
    btns.forEach(b=>b.addEventListener('click',()=>{
      btns.forEach(x=>x.classList.remove('active'));panels.forEach(x=>x.classList.remove('active'));
      b.classList.add('active');
      const p=document.getElementById(`panel-${b.dataset.tab}`);
      if(p){p.classList.remove('active');void p.offsetWidth;p.classList.add('active');}
      if(b.dataset.tab==='history')this._loadHistory();
      if(b.dataset.tab==='sniffer')this._pollSnifferStatus();
    }));
  },

  switchTab(tabName){
    const btns = document.querySelectorAll('.tab-btn');
    const panels = document.querySelectorAll('.tab-panel');
    const targetBtn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    if (!targetBtn) return;
    btns.forEach(x => x.classList.remove('active'));
    panels.forEach(x => x.classList.remove('active'));
    targetBtn.classList.add('active');
    const p = document.getElementById(`panel-${tabName}`);
    if (p) {
      p.classList.remove('active');
      void p.offsetWidth;
      p.classList.add('active');
    }
    if (tabName === 'history') this._loadHistory();
    if (tabName === 'sniffer') this._pollSnifferStatus();
  },

  _checkAutoRoute(url){
    if (!url) return false;
    const trimmed = url.trim();
    // 1. Social Platforms (Instagram, TikTok, Facebook, Twitter / X, Threads, Pinterest)
    const isSocial = /(?:instagram\.com|instagr\.am|tiktok\.com|facebook\.com|fb\.watch|fb\.gg|twitter\.com|x\.com|threads\.net|pinterest\.com|pin\.it)/i.test(trimmed);
    if (isSocial) {
      this.switchTab('social');
      const socialInput = document.getElementById('social-url');
      if (socialInput) {
        socialInput.value = trimmed;
        this.toast('✨ Detected Social link — automatically switched & scanning!', 'info');
        setTimeout(() => {
          this._fetchSocial();
        }, 150);
      }
      return true;
    }

    // 2. YouTube Playlist link
    const isPlaylist = /(?:youtube\.com|youtu\.be).*(?:list=)/i.test(trimmed);
    if (isPlaylist) {
      this.switchTab('playlist');
      const plInput = document.getElementById('pl-url');
      if (plInput) {
        plInput.value = trimmed;
        this.toast('✨ Detected Playlist link — automatically switched & scanning!', 'info');
        setTimeout(() => {
          this._fetchPlaylist();
        }, 150);
      }
      return true;
    }

    return false;
  },

  /* ── Segmented Controls ──────────────────────────────── */
  _bindSegmented(id,cb){
    const ctrl=document.getElementById(id);if(!ctrl)return;
    ctrl.querySelectorAll('.seg-btn').forEach(b=>b.addEventListener('click',()=>{
      ctrl.querySelectorAll('.seg-btn').forEach(x=>x.classList.remove('active'));
      b.classList.add('active');cb(b.dataset.mode);
    }));
  },

  _toggleSingleOpts(){
    const v=this.singleMode==='video';
    document.getElementById('single-video-opts').classList.toggle('hidden',!v);
    document.getElementById('single-audio-opts').classList.toggle('hidden',v);
    const label=document.querySelector('#single-dl-btn .action-label');
    label.textContent=v?'DOWNLOAD VIDEO':'EXTRACT AUDIO';
  },

  _togglePlOpts(){
    const v=this.plMode==='video';
    document.getElementById('pl-bar-video-opts').classList.toggle('hidden',!v);
    document.getElementById('pl-bar-audio-opts').classList.toggle('hidden',v);
  },

  /* ── Paste Buttons ───────────────────────────────────── */
  async _readClipboardText(){
    // 1. Modern Clipboard API (works on localhost, 127.0.0.1, and HTTPS)
    if (navigator.clipboard && typeof navigator.clipboard.readText === 'function') {
      try {
        const text = await navigator.clipboard.readText();
        if (text && text.trim()) return text.trim();
      } catch (err) {
        console.warn("Direct clipboard read blocked:", err);
      }
    }

    // 2. Fallback for insecure domains (e.g. http://hvd.com where browser blocks clipboard)
    const manual = window.prompt("Paste your video or media link (Ctrl+V):");
    return manual ? manual.trim() : null;
  },

  _bindPaste(){
    // Universal Paste Binding for all target inputs
    document.querySelectorAll('.paste-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const targetId = btn.dataset.target || 'single-url';
        const target = document.getElementById(targetId);
        if (!target) return;
        const text = await this._readClipboardText();
        if (text) {
          target.value = text;
          if (targetId === 'single-url') {
            if (this._checkAutoRoute(text)) return;
            this._fetchVideoInfo(text);
          } else if (targetId === 'social-url') {
            this._fetchSocial();
          } else if (targetId === 'pl-url') {
            this._fetchPlaylist();
          } else {
            target.dispatchEvent(new Event('input'));
          }
        }
      });
    });

    const urlInput = document.querySelector('#single-url');
    const fetchBtn = document.querySelector('#single-fetch-btn');
    
    let debounceTimer;
    
    if (urlInput) {
        urlInput.addEventListener('input', (e) => {
            const url = e.target.value.trim();
            clearTimeout(debounceTimer);
            if (!url) {
                const tile = document.getElementById('single-media-tile');
                if (tile) tile.style.display = 'none';
                return;
            }
            if (this._checkAutoRoute(url)) return;
            debounceTimer = setTimeout(() => {
                this._fetchVideoInfo(url);
            }, 600);
        });
    }

    if (fetchBtn) {
        fetchBtn.addEventListener('click', () => {
            const url = urlInput ? urlInput.value.trim() : '';
            if (url) {
                if (this._checkAutoRoute(url)) return;
                this._fetchVideoInfo(url);
            } else this.toast('Paste a video or audio URL first', 'err');
        });
    }
  },

  async _fetchVideoInfo(url){
    const loader = document.getElementById('fetch-loader');
    const tile = document.getElementById('single-media-tile');
    
    try {
      this.toast('Fetching video info...', 'info');
      
      const isDev = document.getElementById('set-dev')?.checked;
      if (isDev) {
          this.log(`[INFO] Requesting metadata from yt-dlp for URL: ${url}`);
      } else {
          this.log(`[INFO] Requesting metadata from yt-dlp...`);
      }
      
      if (loader) loader.style.display = 'flex';
      if (tile) tile.style.display = 'none';
      
      const settings = this._getSettings();
      let queryUrl = `/api/fetch-info?url=${encodeURIComponent(url)}`;
      if (settings.cookie_file) {
        queryUrl += `&cookie_file=${encodeURIComponent(settings.cookie_file)}`;
      }
      const referer = document.getElementById('s-referer')?.value.trim();
      if (referer) {
        queryUrl += `&referer=${encodeURIComponent(referer)}`;
      }
      const r = await fetch(queryUrl);
      if(r.ok){
        const data = await r.json();
        
        // Show preview tile
        document.getElementById('preview-thumbnail').src = data.thumbnail || '';
        document.getElementById('preview-title').textContent = data.title || 'Unknown Title';
        document.getElementById('preview-title').title = data.title || 'Unknown Title';
        document.getElementById('preview-uploader').textContent = data.uploader || 'Unknown Uploader';
        document.getElementById('preview-duration').textContent = data.duration || '00:00';
        const durHint = document.getElementById('clip-dur-hint');
        if (durHint) durHint.textContent = `Full length: ${data.duration || '--:--'}`;
        if (tile) tile.style.display = 'flex';
        
        // Populate Resolutions
        const resSel = document.getElementById('s-resolution');
        if (resSel && data.available_resolutions && data.available_resolutions.length > 0) {
            let html = '<option value="best">Best Available</option>';
            data.available_resolutions.forEach(h => {
                let label = `${h}p`;
                if (h === 2160) label = "4K (2160p)";
                else if (h === 1440) label = "2K (1440p)";
                else if (h === 1080) label = "HD (1080p)";
                else if (h === 720) label = "HD (720p)";
                else if (h === 4320) label = "8K (4320p)";
                html += `<option value="${h}">${label}</option>`;
            });
            resSel.innerHTML = html;
        }

        // Populate Subtitles
        const subSel = document.getElementById('s-sublang');
        const mainSubSel = document.getElementById('s-subs');
        
        const validSubs = (data.subtitles || []).filter(code => code !== 'live_chat' && !code.startsWith('live_chat'));
        if(validSubs.length > 0){
           const languageNames = new Intl.DisplayNames(['en'], { type: 'language' });
           let subs = validSubs.map(code => {
               let displayName = code;
               try {
                   displayName = languageNames.of(code);
               } catch (e) {}
               return { code, displayName };
           });
           
           subs.sort((a, b) => a.displayName.localeCompare(b.displayName));
           
           if(subSel) {
               subSel.innerHTML = subs.map(s => `<option value="${s.code}">${s.displayName}</option>`).join('');
           }
           this.toast('Video info & subtitles loaded', 'ok');
        } else {
           if(subSel) {
               subSel.innerHTML = '<option value="en">English (Default)</option>';
           }
           if(mainSubSel) {
               mainSubSel.value = 'none';
           }
           this.toast('Video info loaded', 'ok');
        }
        
        this.log(`[SUCCESS] Metadata extracted successfully.`);
      } else {
        const err = await r.json();
        this.log(`[ERROR] Failed to fetch metadata: ${err.error || r.statusText}`);
      }
    } catch(e) {
      this.log(`[ERROR] Exception during metadata fetch: ${e.message}`);
    } finally {
      if (loader) loader.style.display = 'none';
    }
  },

  _getSettings(){
    return{
      output_dir:document.getElementById('set-dir')?.value.trim()||undefined,
      social_output_dir:document.getElementById('set-social-dir')?.value.trim()||document.getElementById('social-dest-dir')?.value.trim()||undefined,
      cookie_file:document.getElementById('set-cookie')?.value.trim()||undefined,
      gpu_acceleration:document.getElementById('set-gpu')?.checked||false,
      proxy:document.getElementById('set-proxy')?.value.trim()||undefined,
      dev_mode:document.getElementById('set-dev')?.checked||false,
      max_concurrent:parseInt(document.getElementById('set-concurrent')?.value||'10',10)||10,
    };
  },

  /* ═══════════════ SINGLE TAB DOWNLOAD ═══════════════ */
  _bindSingleDL(){
    const btn=document.getElementById('single-dl-btn');
    btn.addEventListener('click',()=>this._doSingleDL());
    document.getElementById('single-url').addEventListener('keydown',e=>{if(e.key==='Enter')this._doSingleDL();});

    const clipToggle = document.getElementById('s-clip-toggle');
    const clipRow = document.getElementById('clip-inputs-row');
    if (clipToggle && clipRow) {
      clipToggle.addEventListener('change', () => {
        clipRow.style.display = clipToggle.checked ? 'grid' : 'none';
        if (!clipToggle.checked) {
          const st = document.getElementById('s-start-time');
          const et = document.getElementById('s-end-time');
          if (st) st.value = '';
          if (et) et.value = '';
        }
      });
    }
  },

  async _doSingleDL(){
    const url=document.getElementById('single-url').value.trim();
    if(!url){this.toast('Paste a URL first','err');return;}
    if(this._checkAutoRoute(url)) return;
    const btn=document.getElementById('single-dl-btn');
    const label=btn.querySelector('.action-label'),spin=btn.querySelector('.btn-spinner');

    const isClip = document.getElementById('s-clip-toggle')?.checked;
    const startTime = isClip ? (document.getElementById('s-start-time')?.value.trim() || undefined) : undefined;
    const endTime = isClip ? (document.getElementById('s-end-time')?.value.trim() || undefined) : undefined;
    const referer = document.getElementById('s-referer')?.value.trim() || undefined;

    if (isClip && !startTime && !endTime) {
      this.toast('Please enter a Start Time or End Time for the clip', 'err');
      return;
    }

    label.hidden=true;spin.hidden=false;btn.disabled=true;

    const settings=this._getSettings();
    const rateLimit = document.getElementById('s-rate-limit').value || undefined;

    const body={
      url,
      format_type:this.singleMode,
      rate_limit:rateLimit,
      start_time:startTime,
      end_time:endTime,
      referer:referer,
      ...settings
    };

    if(this.singleMode==='video'){
      body.quality=document.getElementById('s-resolution').value;
      body.video_format=document.getElementById('s-vformat').value;
      body.subtitles=document.getElementById('s-subs').value;
      body.subtitle_lang=document.getElementById('s-sublang').value;
    }else{
      body.audio_format=document.getElementById('s-aformat').value;
    }

    try{
      const r=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const d=await r.json();
      if(r.ok){
        document.getElementById('single-url').value='';
        document.getElementById('s-start-time').value='';
        document.getElementById('s-end-time').value='';
        const clipToggle = document.getElementById('s-clip-toggle');
        if (clipToggle) {
          clipToggle.checked = false;
          const clipRow = document.getElementById('clip-inputs-row');
          if (clipRow) clipRow.style.display = 'none';
        }
        const tile=document.getElementById('single-media-tile');
        if(tile)tile.style.display='none';
        this.toast(isClip ? 'Clip download started' : 'Download started','ok');
      }
      else this.toast(d.error||'Failed','err');
    }catch{this.toast('Network error','err');}
    finally{label.hidden=false;spin.hidden=true;btn.disabled=false;}
  },

  /* ═══════════════ PLAYLIST TAB ═══════════════ */
  _bindPlaylist(){
    document.getElementById('pl-fetch-btn').addEventListener('click',()=>this._fetchPlaylist());
    document.getElementById('pl-url').addEventListener('keydown',e=>{if(e.key==='Enter')this._fetchPlaylist();});
    document.getElementById('pl-select-all').addEventListener('change',e=>this._toggleAllCards(e.target.checked));
    document.getElementById('pl-dl-btn').addEventListener('click',()=>this._downloadSelected());
  },

  async _fetchPlaylist(){
    const url=document.getElementById('pl-url').value.trim();
    if(!url){this.toast('Paste a playlist URL first','err');return;}
    const btn=document.getElementById('pl-fetch-btn');
    const label=btn.querySelector('span'),spin=btn.querySelector('.btn-spinner');
    label.hidden=true;spin.hidden=false;btn.disabled=true;

    // Show loader, hide other states
    document.getElementById('pl-empty').classList.add('hidden');
    document.getElementById('pl-results').classList.add('hidden');
    document.getElementById('pl-action-bar').style.display='none';
    document.getElementById('pl-loader').classList.remove('hidden');

    const settings=this._getSettings();
    const body={url};
    if(settings.cookie_file)body.cookie_file=settings.cookie_file;

    try{
      const r=await fetch('/api/playlist-info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const d=await r.json();
      if(r.ok&&d.entries?.length){
        this.plEntries=d.entries;
        this._renderPlaylistGrid(d);
        this.toast(`Found ${d.count} videos`,'ok');
      }else if(r.ok){
        this.toast('No videos found in playlist','err');
        document.getElementById('pl-empty').classList.remove('hidden');
      }else{
        this.toast(d.error||'Fetch failed','err');
        document.getElementById('pl-empty').classList.remove('hidden');
      }
    }catch{this.toast('Network error','err');document.getElementById('pl-empty').classList.remove('hidden');}
    finally{document.getElementById('pl-loader').classList.add('hidden');label.hidden=false;spin.hidden=true;btn.disabled=false;}
  },

  _renderPlaylistGrid(data){
    const grid=document.getElementById('pl-grid');
    grid.innerHTML='';
    data.entries.forEach((entry,i)=>{
      const card=document.createElement('div');
      card.className='pl-card selected';
      card.dataset.index=i;
      card.dataset.url=entry.url||'';
      const dur=fmtDur(entry.duration);
      const thumb=entry.thumbnail||'';
      const uploader=entry.uploader||'Unknown Channel';
      const views=entry.view_count?fmtViews(entry.view_count):'';

      card.innerHTML=`
        <div class="card-check"></div>
        <span class="pl-card-index">#${i+1}</span>
        <div class="pl-thumb-wrap">
          ${thumb?`<img class="pl-thumb" src="${esc(thumb)}" alt="" loading="lazy" onerror="this.style.display='none'">`:'<div class="pl-thumb"></div>'}
          ${dur?`<span class="pl-card-dur">${dur}</span>`:''}
        </div>
        <div class="pl-card-body">
          <div class="pl-card-title" title="${esc(entry.title||'Untitled')}">${esc(entry.title||'Untitled')}</div>
          <div class="pl-meta-row">
            <span class="pl-channel">${esc(uploader)}</span>
            <span class="pl-dot">•</span>
            ${dur?`<span class="pl-dur-text">${dur}</span><span class="pl-dot">•</span>`:''}
            ${views?`<span class="pl-views">${views}</span><span class="pl-dot">•</span>`:''}
            <span class="pl-badge">Video #${i+1}</span>
          </div>
        </div>
      `;
      card.addEventListener('click',()=>{card.classList.toggle('selected');this._updateSelCount();});
      grid.appendChild(card);
    });
    document.getElementById('pl-title').textContent=data.playlist_title||'Playlist';
    document.getElementById('pl-count-badge').textContent=`${data.count} videos`;
    document.getElementById('pl-select-all').checked=true;
    document.getElementById('pl-results').classList.remove('hidden');
    document.getElementById('pl-action-bar').style.display='flex';
    this._updateSelCount();
  },

  _toggleAllCards(checked){
    document.querySelectorAll('.pl-card').forEach(c=>{
      if(checked)c.classList.add('selected');else c.classList.remove('selected');
    });
    this._updateSelCount();
  },

  _updateSelCount(){
    const n=document.querySelectorAll('.pl-card.selected').length;
    document.getElementById('pl-sel-count').textContent=n;
    document.getElementById('pl-dl-btn').disabled=n===0;
    // Sync the select-all checkbox
    const total=document.querySelectorAll('.pl-card').length;
    document.getElementById('pl-select-all').checked=n===total&&total>0;
  },

  async _downloadSelected(){
    const cards=[...document.querySelectorAll('.pl-card.selected')];
    if(!cards.length){this.toast('No videos selected','err');return;}
    const btn=document.getElementById('pl-dl-btn');
    const label=btn.querySelector('.action-label'),spin=btn.querySelector('.btn-spinner');
    label.hidden=true;spin.hidden=false;btn.disabled=true;

    const settings=this._getSettings();
    const isVideo=this.plMode==='video';

    let queued=0;
    for(const card of cards){
      const url=card.dataset.url;
      if(!url)continue;
      const body={url,format_type:this.plMode,...settings};
      if(isVideo){
        body.quality=document.getElementById('pl-resolution').value;
        body.video_format=document.getElementById('pl-vformat').value;
      }else{
        body.audio_format=document.getElementById('pl-aformat').value;
      }
      try{
        const r=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        if(r.ok)queued++;
      }catch{}
    }
    this.toast(`Queued ${queued} download${queued!==1?'s':''}`,'ok');
    this.log(`[Playlist] Queued ${queued} of ${cards.length} selected`);
    label.hidden=false;spin.hidden=true;btn.disabled=false;
  },

  /* ═══════════════ BROWSER STREAM SNIFFER ═══════════════ */
  snifferStreams: [],
  snifferRunning: false,

  _bindSniffer() {
    const launchBtn = document.getElementById('sniffer-launch-btn');
    const closeBtn = document.getElementById('sniffer-close-btn');
    const urlInput = document.getElementById('sniffer-url');
    const clearBtn = document.getElementById('sniffer-clear-streams');

    launchBtn?.addEventListener('click', () => {
      const url = urlInput?.value.trim() || 'https://aniwaves.ru';
      this._launchSniffer(url);
    });

    urlInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const url = urlInput?.value.trim() || 'https://aniwaves.ru';
        this._launchSniffer(url);
      }
    });

    closeBtn?.addEventListener('click', async () => {
      try {
        await fetch('/api/sniffer/close', { method: 'POST' });
        this._updateSnifferUi(false);
        this.toast('Sniffer browser closed.', 'inf');
      } catch (e) {
        this.toast('Failed to close browser: ' + e.message, 'err');
      }
    });

    clearBtn?.addEventListener('click', async () => {
      try {
        await fetch('/api/sniffer/clear', { method: 'POST' });
        this.snifferStreams = [];
        this._renderSnifferStreams();
        this._updateSnifferBadge();
        this.toast('Stream list cleared.', 'inf');
      } catch (e) {}
    });

    document.getElementById('sniffer-paste-direct')?.addEventListener('click', async () => {
      let clip = '';
      try {
        clip = await navigator.clipboard.readText();
      } catch (e) {}
      const manualUrl = prompt('Enter or paste direct stream link (.m3u8, .mpd, or video stream URL):', clip || '');
      if (manualUrl && manualUrl.trim().startsWith('http')) {
        const u = manualUrl.trim();
        let domain = 'web';
        try { domain = new URL(u).hostname; } catch(e){}
        const s = {
          id: 'sniff_manual_' + Date.now().toString(16),
          url: u,
          title: 'Direct Stream - ' + (u.split('/').pop().split('?')[0] || 'Video'),
          type: u.includes('.mpd') ? 'DASH Stream' : (u.includes('.m3u8') ? 'HLS Stream' : 'Video Stream'),
          domain: domain,
          referer: u,
          headers: { Referer: u }
        };
        this._onSnifferStream(s);
        this.toast('Stream added to list!', 'ok');
      }
    });

    // View live logs button
    document.getElementById('sniffer-view-logs-btn')?.addEventListener('click', () => {
      const logTabBtn = document.querySelector('.tab-btn[data-tab="log"]');
      if (logTabBtn) logTabBtn.click();
    });

    // Preset chip buttons
    document.querySelectorAll('.preset-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const url = chip.dataset.url;
        if (urlInput) urlInput.value = url;
        this._launchSniffer(url);
      });
    });
  },

  async _launchSniffer(url) {
    const statusText = document.getElementById('sniffer-status-text');
    if (statusText) statusText.textContent = 'Launching browser...';
    try {
      const res = await fetch('/api/sniffer/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this._updateSnifferUi(true);
        this.toast('Sniffer browser opened! Play any video to capture the stream.', 'ok');
      } else {
        this.toast(data.error || 'Failed to launch browser', 'err');
        this._updateSnifferUi(false);
      }
    } catch (err) {
      this.toast('Error launching sniffer: ' + err.message, 'err');
      this._updateSnifferUi(false);
    }
  },

  _updateSnifferUi(running) {
    this.snifferRunning = running;
    const badge = document.getElementById('sniffer-status-badge');
    const text = document.getElementById('sniffer-status-text');
    const closeBtn = document.getElementById('sniffer-close-btn');

    if (badge && text) {
      if (running) {
        badge.className = 'sniffer-status-badge active';
        text.textContent = 'Sniffer Active (Listening for streams...)';
      } else {
        badge.className = 'sniffer-status-badge';
        text.textContent = 'Browser: Idle (Click Launch)';
      }
    }
    if (closeBtn) {
      closeBtn.style.display = running ? 'inline-flex' : 'none';
    }
  },

  _handleSnifferStatus(data) {
    if (!data) return;
    this._updateSnifferUi(!!data.running);
    if (Array.isArray(data.streams)) {
      this.snifferStreams = data.streams;
      this._renderSnifferStreams();
      this._updateSnifferBadge();
    }
  },

  async _pollSnifferStatus() {
    try {
      const res = await fetch('/api/sniffer/status');
      const data = await res.json();
      this._handleSnifferStatus(data);
    } catch (e) {}
  },

  _onSnifferStream(stream) {
    if (!stream || !stream.id) return;
    const exists = this.snifferStreams.some(s => s.id === stream.id || s.url === stream.url);
    if (!exists) {
      this.snifferStreams.unshift(stream);
      if (this.snifferStreams.length > 50) this.snifferStreams.pop();
      this._renderSnifferStreams();
      this._updateSnifferBadge();
      this.toast(`🎬 Captured: ${stream.title || 'Video Stream'}`, 'ok');
    }
  },

  _updateSnifferBadge() {
    const badge = document.getElementById('sniffer-badge-count');
    const countEl = document.getElementById('sniffer-streams-count');
    const count = this.snifferStreams.length;
    if (countEl) countEl.textContent = count;
    if (badge) {
      if (count > 0) {
        badge.style.display = 'inline-flex';
        badge.textContent = count;
      } else {
        badge.style.display = 'none';
      }
    }
  },

  _renderSnifferStreams() {
    const container = document.getElementById('sniffer-streams-list');
    if (!container) return;

    if (this.snifferStreams.length === 0) {
      container.innerHTML = `
        <div class="sniffer-empty-state" id="sniffer-empty-state">
            <div class="radar-pulse"></div>
            <p class="empty-title">Waiting for video stream...</p>
            <p class="empty-desc">Click "Launch Browser", open your video page, select your audio (Sub/Dub), and hit Play. Captured video streams will appear here automatically.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = '';
    this.snifferStreams.forEach(s => {
      const card = document.createElement('div');
      card.className = 'stream-card';

      const isHls = s.type && s.type.includes('HLS');
      const isDash = s.type && s.type.includes('DASH');
      const typeClass = isHls ? 'hls' : (isDash ? 'dash' : '');

      card.innerHTML = `
        <div class="stream-info">
            <div class="stream-title-row">
                <span class="stream-type-pill ${typeClass}">${s.type || 'STREAM'}</span>
                <span class="stream-title" title="${this._esc(s.title || 'Stream')}">${this._esc(s.title || 'Stream')}</span>
            </div>
            <div class="stream-meta">
                <span>🌐 ${this._esc(s.domain || 'web')}</span>
                <span style="opacity:0.6; overflow:hidden; text-overflow:ellipsis; max-width:280px;" title="${this._esc(s.url)}">${this._esc(s.url)}</span>
            </div>
        </div>
        <div class="stream-actions">
            <button class="stream-dl-btn" type="button">
                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 3v10m0 0l-4-4m4 4l4-4M3 15v2a2 2 0 002 2h14a2 2 0 002-2v-2"/></svg>
                <span>Download</span>
            </button>
            <button class="stream-dismiss-btn" type="button" title="Dismiss stream">✕</button>
        </div>
      `;

      card.querySelector('.stream-dl-btn')?.addEventListener('click', () => {
        this._downloadSniffedStream(s);
      });

      card.querySelector('.stream-dismiss-btn')?.addEventListener('click', () => {
        this.snifferStreams = this.snifferStreams.filter(item => item.id !== s.id);
        this._renderSnifferStreams();
        this._updateSnifferBadge();
      });

      container.appendChild(card);
    });
  },

  async _downloadSniffedStream(stream) {
    try {
      this.toast(`Starting download: ${stream.title}...`, 'inf');
      const res = await fetch('/api/sniffer/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: stream.url,
          title: stream.title,
          referer: stream.referer,
          headers: stream.headers
        })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.toast(`Downloading: ${data.title}!`, 'ok');
        // Automatically switch to Active Downloads tab
        const activeTabBtn = document.querySelector('.tab-btn[data-tab="active"]');
        if (activeTabBtn) activeTabBtn.click();
      } else {
        this.toast(data.error || 'Failed to start stream download', 'err');
      }
    } catch (err) {
      this.toast('Download error: ' + err.message, 'err');
    }
  },

  _esc(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m]);
  },

  /* ═══════════════ WEBSOCKET ═══════════════ */
  _connectWS(){
    this.ws=new WS(
      d=>this._onMsg(d),
      ()=>this._conn('live','Live'),
      ()=>this._conn('off','Offline'),
    );
    this.ws.connect();
  },
  _onMsg(d){
    if(d.type==='init'){
      (d.tasks||[]).filter(t => t.status === 'downloading' || t.status === 'queued' || t.status === 'paused').forEach(t => {
        t.is_restored = true;
        this._upsert(t);
      });
      this._empty();
      if(d.sniffer) {
        this._handleSnifferStatus(d.sniffer);
        if (Array.isArray(d.sniffer.logs) && d.sniffer.logs.length > 0) {
          const out = document.getElementById('log-output');
          if (out) {
            if (out.querySelector('.log-muted')) out.innerHTML = '';
            d.sniffer.logs.forEach(l => {
              out.textContent += `${l}\n`;
            });
            out.scrollTop = out.scrollHeight;
          }
        }
      }
    }
    else if(d.type==='progress')this._upsert(d);
    else if(d.type==='log')this._appendLog(d);
    else if(d.type==='sniffer_stream')this._onSnifferStream(d.stream);
    else if(d.type==='sniffer_status')this._updateSnifferUi(!!d.running);
    this._counts();
  },
  _upsert(td){
    let c=this.cards.get(td.task_id);
    if(c)c.update(td);else{c=new DLCard(td);this.cards.set(td.task_id,c);document.getElementById('download-list').prepend(c.el);}
    this._empty();
  },
  _counts(){
    const n=[...this.cards.values()].filter(c=>!c.done).length;
    const b=document.getElementById('dl-count');b.textContent=n;b.hidden=n===0;
  },
  _empty(){document.getElementById('empty-state').classList.toggle('hidden',this.cards.size>0);},
  _conn(c,t){const el=document.getElementById('conn-status');el.className=`conn-indicator ${c}`;el.querySelector('.conn-label').textContent=t;},

  /* ── Log ──────────────────────────────────────────────── */
  _bindLog(){document.getElementById('log-clear')?.addEventListener('click',()=>{document.getElementById('log-output').innerHTML='<span class="log-muted">Log cleared.</span>';});},
  log(msg){
    const out=document.getElementById('log-output');if(!out)return;
    if(out.querySelector('.log-muted'))out.innerHTML='';
    const ts=new Date().toLocaleTimeString('en-GB',{hour12:false});
    out.textContent+=`[${ts}] ${msg}\n`;
    if(out.scrollHeight-out.scrollTop-out.clientHeight<80)out.scrollTop=out.scrollHeight;
  },
  _appendLog(data){
    const out=document.getElementById('log-output');if(!out)return;
    if(out.querySelector('.log-muted'))out.innerHTML='';
    const ts=new Date().toLocaleTimeString('en-GB',{hour12:false});
    const prefix = data.task_id === 'SNIFFER' ? '[SNIFFER]' : `[${data.task_id}]`;
    out.textContent+=`[${ts}] ${prefix} ${data.message}\n`;
    out.scrollTop=out.scrollHeight;

    const tid = (data.task_id || '').toLowerCase();
    if (tid === 'social' && data.message) {
      const socialP = document.getElementById('social-loader-text') || document.querySelector('#social-loader p');
      if (socialP) socialP.textContent = data.message;
    }
    if (tid === 'inventory' && data.message) {
      const syncStatusText = document.getElementById('sync-status-text');
      if (syncStatusText) syncStatusText.textContent = data.message;
    }
  },

  /* ── In-App Folder Picker Modal ───────────────────────── */
  _folderPickerTargetId: null,
  _folderPickerCurrentPath: '',

  openFolderPicker(targetId, title = 'Choose Destination Folder'){
    this._folderPickerTargetId = targetId;
    const modal = document.getElementById('folder-picker-modal');
    const titleEl = document.getElementById('fp-modal-title');
    if (titleEl) titleEl.textContent = title;
    if (modal) {
      modal.style.display = 'flex';
    }
    const currentVal = document.getElementById(targetId)?.value?.trim() || '';
    this._loadFolderPickerPath(currentVal);
  },

  closeFolderPicker(){
    const modal = document.getElementById('folder-picker-modal');
    if (modal) modal.style.display = 'none';
    this._folderPickerTargetId = null;
  },

  async _loadFolderPickerPath(path = ''){
    const input = document.getElementById('fp-current-path-input');
    const list = document.getElementById('fp-folder-list');
    const drivesList = document.getElementById('fp-drives-list');
    const quickList = document.getElementById('fp-shortcuts-list');
    if (!list) return;

    list.innerHTML = '<div style="padding:24px; text-align:center; color:var(--text-3); font-size:0.85rem;"><div class="spinner-ring" style="width:20px; height:20px; border-width:2px; margin:0 auto 8px;"></div>Loading folders...</div>';

    try {
      const q = path ? `?path=${encodeURIComponent(path)}` : '';
      const r = await fetch(`/api/fs/list${q}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();

      this._folderPickerCurrentPath = data.current || '';
      if (input) input.value = this._folderPickerCurrentPath;

      // Render Drives using dataset
      if (drivesList && Array.isArray(data.drives)) {
        drivesList.innerHTML = data.drives.map(d => `
          <button type="button" class="btn btn-secondary btn-sm fp-drive-btn" data-path="${esc(d)}" style="padding:2px 8px; font-size:0.72rem; border-radius:4px; font-weight:600; cursor:pointer;">
            ${esc(d)}
          </button>
        `).join('');
      }

      // Render Quick Shortcuts using dataset
      if (quickList && Array.isArray(data.shortcuts)) {
        quickList.innerHTML = data.shortcuts.map(s => `
          <button type="button" class="btn btn-secondary btn-sm fp-quick-btn" data-path="${esc(s.path)}" style="padding:2px 8px; font-size:0.72rem; border-radius:4px; cursor:pointer;">
            ${esc(s.name)}
          </button>
        `).join('');
      }

      // Render Subdirectories List using dataset
      const folders = data.folders || [];
      if (folders.length === 0) {
        list.innerHTML = '<div style="padding:24px; text-align:center; color:var(--text-3); font-size:0.85rem;">(Folder is empty or contains no subdirectories)</div>';
      } else {
        list.innerHTML = folders.map(f => `
          <div class="fp-folder-row" data-path="${esc(f.path)}" style="display:flex; align-items:center; gap:10px; padding:7px 12px; border-radius:6px; cursor:pointer; background:rgba(255,255,255,0.02); transition:background 0.15s; user-select:none;">
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" style="width:16px; height:16px; color:var(--accent); flex-shrink:0;"><path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v7a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/></svg>
            <span style="font-size:0.84rem; font-weight:500; color:var(--text-1); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${esc(f.name)}">${esc(f.name)}</span>
          </div>
        `).join('');
      }

    } catch (e) {
      list.innerHTML = `<div style="padding:20px; text-align:center; color:#f87171; font-size:0.82rem;">Could not open directory: ${esc(e.message)}</div>`;
    }
  },

  async selectCurrentFolder(){
    const path = this._folderPickerCurrentPath || document.getElementById('fp-current-path-input')?.value?.trim();
    if (!path) {
      this.toast('Please choose a valid folder', 'err');
      return;
    }
    const targetId = this._folderPickerTargetId;
    if (targetId) {
      const el = document.getElementById(targetId);
      if (el) el.value = path;
      if (targetId === 'set-social-dir' || targetId === 'social-dest-dir') {
        const e1 = document.getElementById('set-social-dir');
        const e2 = document.getElementById('social-dest-dir');
        if (e1) e1.value = path;
        if (e2) e2.value = path;
        await fetch('/api/settings', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ social_output_dir: path })
        });
      } else {
        await fetch('/api/settings', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ output_dir: path })
        });
      }
      this._savePersistedSettings();
      this.toast('✔ Destination folder selected: ' + path, 'ok');
    }
    this.closeFolderPicker();
  },

  async createNewFolderInPicker(){
    const cur = this._folderPickerCurrentPath || document.getElementById('fp-current-path-input')?.value?.trim();
    if (!cur) return;
    const name = window.prompt('Enter new folder name:');
    if (!name || !name.trim()) return;
    try {
      const r = await fetch('/api/fs/mkdir', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ parent: cur, name: name.trim() })
      });
      const data = await r.json();
      if (r.ok && data.success) {
        this.toast(`Folder "${name.trim()}" created!`, 'ok');
        this._loadFolderPickerPath(data.path);
      } else {
        this.toast(data.error || 'Failed to create folder', 'err');
      }
    } catch (e) {
      this.toast('Error creating folder: ' + e.message, 'err');
    }
  },

  /* ── Settings ────────────────────────────────────────── */
  _bindSettings(){
    const saveManualDir = async (targetId, path) => {
      if (!path) return;
      try {
        if (targetId === 'set-social-dir' || targetId === 'social-dest-dir') {
          const e1 = document.getElementById('set-social-dir');
          const e2 = document.getElementById('social-dest-dir');
          if (e1) e1.value = path;
          if (e2) e2.value = path;
          await fetch('/api/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ social_output_dir: path })
          });
        } else {
          await fetch('/api/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ output_dir: path })
          });
        }
        this._savePersistedSettings();
        this.toast('Destination folder updated!', 'ok');
      } catch (err) {
        console.error('Failed to update destination folder:', err);
      }
    };

    // Wire folder browse buttons to in-app picker
    document.getElementById('set-dir-browse')?.addEventListener('click', () => this.openFolderPicker('set-dir', 'Choose General Downloads Folder'));
    document.getElementById('set-social-dir-browse')?.addEventListener('click', () => this.openFolderPicker('set-social-dir', 'Choose Social Media Downloads Folder'));
    document.getElementById('social-browse-btn')?.addEventListener('click', () => this.openFolderPicker('social-dest-dir', 'Choose Social Media Downloads Folder'));

    // Wire folder picker modal controls
    document.getElementById('fp-modal-close')?.addEventListener('click', () => this.closeFolderPicker());
    document.getElementById('fp-cancel-btn')?.addEventListener('click', () => this.closeFolderPicker());
    document.getElementById('fp-select-btn')?.addEventListener('click', () => this.selectCurrentFolder());
    document.getElementById('fp-nav-mkdir')?.addEventListener('click', () => this.createNewFolderInPicker());

    document.getElementById('fp-nav-up')?.addEventListener('click', () => {
      const cur = this._folderPickerCurrentPath;
      if (!cur) return;
      const lastSlash = Math.max(cur.lastIndexOf('\\'), cur.lastIndexOf('/'));
      if (lastSlash > 0) {
        let parent = cur.substring(0, lastSlash);
        if (parent.endsWith(':')) parent += '\\';
        this._loadFolderPickerPath(parent);
      }
    });

    document.getElementById('fp-nav-go')?.addEventListener('click', () => {
      const val = document.getElementById('fp-current-path-input')?.value?.trim();
      if (val) this._loadFolderPickerPath(val);
    });

    document.getElementById('fp-current-path-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const val = e.target.value.trim();
        if (val) this._loadFolderPickerPath(val);
      }
    });

    document.getElementById('fp-open-explorer-btn')?.addEventListener('click', () => {
      const cur = this._folderPickerCurrentPath;
      if (cur) this.openDirectory(cur);
    });

    // Delegation for drives list
    document.getElementById('fp-drives-list')?.addEventListener('click', (e) => {
      const btn = e.target.closest('.fp-drive-btn');
      if (btn && btn.dataset.path) this._loadFolderPickerPath(btn.dataset.path);
    });

    // Delegation for shortcuts list
    document.getElementById('fp-shortcuts-list')?.addEventListener('click', (e) => {
      const btn = e.target.closest('.fp-quick-btn');
      if (btn && btn.dataset.path) this._loadFolderPickerPath(btn.dataset.path);
    });

    // Delegation for folder list rows
    document.getElementById('fp-folder-list')?.addEventListener('click', (e) => {
      const row = e.target.closest('.fp-folder-row');
      if (row && row.dataset.path) this._loadFolderPickerPath(row.dataset.path);
    });

    // Close modal when clicking on backdrop
    document.getElementById('folder-picker-modal')?.addEventListener('click', (e) => {
      if (e.target && e.target.id === 'folder-picker-modal') {
        this.closeFolderPicker();
      }
    });

    document.getElementById('social-dest-dir')?.addEventListener('change', (e) => saveManualDir('social-dest-dir', e.target.value.trim()));
    document.getElementById('set-social-dir')?.addEventListener('change', (e) => saveManualDir('set-social-dir', e.target.value.trim()));
    document.getElementById('set-dir')?.addEventListener('change', (e) => saveManualDir('set-dir', e.target.value.trim()));

    document.getElementById('social-open-folder-btn')?.addEventListener('click', async () => {
      const p = document.getElementById('social-dest-dir')?.value || '';
      try {
        await fetch('/api/open-directory', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ path: p })
        });
      } catch {}
    });

    document.getElementById('set-social-dir')?.addEventListener('input', () => {
      const v = document.getElementById('set-social-dir').value;
      const s = document.getElementById('social-dest-dir');
      if (s) s.value = v;
      this._savePersistedSettings();
    });

    document.getElementById('set-cookie-browse')?.addEventListener('click',()=>{
      const inp=document.createElement('input');inp.type='file';inp.accept='.txt,.json';
      inp.onchange=async ()=>{
        const file = inp.files[0];
        if(!file) return;
        try{
          const text = await file.text();
          const res = await fetch('/api/upload-cookie', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ filename: file.name, content: text })
          });
          const data = await res.json();
          if(res.ok && data.success){
            const cookieEl = document.getElementById('set-cookie');
            if(cookieEl) cookieEl.value = data.cookie_file || file.name;
            if (data.cookie_stats) this._renderCookieBadges(data.cookie_stats);
            this._savePersistedSettings();
            this.toast(data.message || 'Cookie merged into Master Vault!','ok');
          } else {
            this.toast(data.error || 'Failed to upload cookie','err');
          }
        }catch(err){
          this.toast('Error reading cookie file: ' + err.message,'err');
        }
      };
      inp.click();
    });

    document.getElementById('set-cookie-clear')?.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/clear-cookie', { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.success) {
          const cookieEl = document.getElementById('set-cookie');
          if (cookieEl) cookieEl.value = '';
          if (data.cookie_stats) this._renderCookieBadges(data.cookie_stats);
          this._savePersistedSettings();
          this.toast('Master Cookie Vault cleared.', 'inf');
        }
      } catch (err) {
        this.toast('Failed to clear cookies: ' + err.message, 'err');
      }
    });

    document.getElementById('update-ytdlp-btn')?.addEventListener('click',()=>this._updateYtdlp());
    document.getElementById('update-gallerydl-btn')?.addEventListener('click',()=>this._updateGallerydl());

    // Save on manual changes
    document.getElementById('set-dir')?.addEventListener('input',()=>this._savePersistedSettings());
    document.getElementById('set-cookie')?.addEventListener('input',()=>this._savePersistedSettings());
    document.getElementById('set-proxy')?.addEventListener('input',()=>this._savePersistedSettings());
    document.getElementById('set-gpu')?.addEventListener('change',()=>this._savePersistedSettings());

    // Dev mode — save locally AND push to server
    document.getElementById('set-dev')?.addEventListener('change',(e)=>{
      this._savePersistedSettings();
      fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({dev_mode:e.target.checked})}).catch(()=>{});
    });

    // Max concurrent — save locally AND push to server
    document.getElementById('set-concurrent')?.addEventListener('change',(e)=>{
      this._savePersistedSettings();
      const val=parseInt(e.target.value,10);
      if(val>=1&&val<=20){
        fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({max_concurrent:val})})
          .then(r=>r.json()).then(d=>{
            if(d.success)this.toast(`Max concurrent set to ${val}`,'ok');
            else this.toast(d.error||'Settings error','err');
          }).catch(()=>this.toast('Network error','err'));
      }
    });

    // Windows Startup toggle
    const startupCheck = document.getElementById('set-startup');
    startupCheck?.addEventListener('change', async (e) => {
      try {
        const r = await fetch('/api/settings/startup', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({enabled: e.target.checked})
        });
        const res = await r.json();
        if (r.ok && res.success) {
          this.toast(e.target.checked ? '🚀 Background Windows Startup enabled!' : 'Windows Startup disabled', 'ok');
        } else {
          startupCheck.checked = !e.target.checked;
          this.toast(res.error || 'Failed to update startup setting', 'err');
        }
      } catch {
        startupCheck.checked = !e.target.checked;
        this.toast('Network error', 'err');
      }
    });

    // Preferred Port save button
    const portBtn = document.getElementById('btn-save-port');
    const portInput = document.getElementById('set-preferred-port');
    portBtn?.addEventListener('click', async () => {
      const portVal = parseInt(portInput?.value, 10);
      if (isNaN(portVal) || portVal < 1 || portVal > 65535) {
        this.toast('Please enter a valid port between 1 and 65535', 'err');
        return;
      }
      try {
        const r = await fetch('/api/settings', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({preferred_port: portVal})
        });
        const res = await r.json();
        if (r.ok && res.success) {
          this.toast(`Port ${portVal} saved! Will be used on next restart.`, 'ok');
        } else {
          this.toast(res.error || 'Failed to save port', 'err');
        }
      } catch {
        this.toast('Network error', 'err');
      }
    });
  },

  _savePersistedSettings(){
    const settings = this._getSettings();
    localStorage.setItem('hvd_settings', JSON.stringify({
      output_dir: settings.output_dir || '',
      social_output_dir: settings.social_output_dir || '',
      cookie_file: settings.cookie_file || '',
      gpu_acceleration: settings.gpu_acceleration || false,
      proxy: settings.proxy || '',
      dev_mode: settings.dev_mode || false,
      max_concurrent: settings.max_concurrent || 10,
    }));
  },

  _renderCookieBadges(stats) {
    if (!stats) return;
    const ytBadge = document.getElementById('cookie-badge-yt');
    const ytStatus = document.getElementById('cookie-status-yt');
    const igBadge = document.getElementById('cookie-badge-ig');
    const igStatus = document.getElementById('cookie-status-ig');
    const otherBadge = document.getElementById('cookie-badge-other');
    const otherStatus = document.getElementById('cookie-status-other');

    if (ytBadge && ytStatus) {
      if (stats.youtube) {
        ytBadge.className = 'cookie-badge active';
        ytStatus.textContent = 'Active';
      } else {
        ytBadge.className = 'cookie-badge inactive';
        ytStatus.textContent = 'Not Loaded';
      }
    }

    if (igBadge && igStatus) {
      if (stats.instagram) {
        igBadge.className = 'cookie-badge active';
        igStatus.textContent = 'Active';
      } else {
        igBadge.className = 'cookie-badge inactive';
        igStatus.textContent = 'Not Loaded';
      }
    }

    if (otherBadge && otherStatus) {
      if (stats.other_count > 0) {
        otherBadge.style.display = 'inline-flex';
        otherBadge.className = 'cookie-badge active';
        otherStatus.textContent = `${stats.other_count} sites`;
      } else {
        otherBadge.style.display = 'none';
      }
    }
  },

  _loadPersistedSettings(){
    try {
      const saved = localStorage.getItem('hvd_settings');
      let settings = saved ? JSON.parse(saved) : {};

      const applyToDom = (s) => {
        const dirEl = document.getElementById('set-dir');
        const socialDirEl = document.getElementById('set-social-dir');
        const socialDestEl = document.getElementById('social-dest-dir');
        const cookieEl = document.getElementById('set-cookie');
        const proxyEl = document.getElementById('set-proxy');
        const gpuEl = document.getElementById('set-gpu');
        const devEl = document.getElementById('set-dev');
        const concEl = document.getElementById('set-concurrent');
        if (dirEl && s.output_dir) dirEl.value = s.output_dir;
        if (s.social_output_dir) {
          if (socialDirEl) socialDirEl.value = s.social_output_dir;
          if (socialDestEl) socialDestEl.value = s.social_output_dir;
        }
        if (cookieEl && s.cookie_file) cookieEl.value = s.cookie_file;
        if (proxyEl && s.proxy) proxyEl.value = s.proxy;
        if (gpuEl && s.gpu_acceleration != null) gpuEl.checked = s.gpu_acceleration;
        if (devEl && s.dev_mode != null) devEl.checked = s.dev_mode;
        if (concEl && s.max_concurrent) concEl.value = s.max_concurrent;
        const startupEl = document.getElementById('set-startup');
        if (startupEl && s.windows_startup != null) startupEl.checked = !!s.windows_startup;
        const portEl = document.getElementById('set-preferred-port');
        if (portEl && s.preferred_port) portEl.value = s.preferred_port;
        if (s.cookie_stats) this._renderCookieBadges(s.cookie_stats);
      };

      applyToDom(settings);

      // Fetch server settings and merge
      fetch('/api/settings')
        .then(r => r.json())
        .then(serverSettings => {
          if (serverSettings && typeof serverSettings === 'object') {
            settings = { ...serverSettings, ...settings };
            applyToDom(settings);
            if (serverSettings.cookie_stats) {
              this._renderCookieBadges(serverSettings.cookie_stats);
            }
            // Ensure server has latest combined settings
            fetch('/api/settings', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                max_concurrent: settings.max_concurrent || 10,
                dev_mode: !!settings.dev_mode,
                output_dir: settings.output_dir || '',
                proxy: settings.proxy || '',
                cookie_file: settings.cookie_file || '',
                gpu_acceleration: !!settings.gpu_acceleration,
              })
            }).catch(() => {});
          }
        })
        .catch(() => {});
    } catch(e) {}
  },

  async _updateYtdlp(){
    const btn=document.getElementById('update-ytdlp-btn');
    const label=btn.querySelector('span'),spin=btn.querySelector('.btn-spinner');
    const out=document.getElementById('update-output');
    label.hidden=true;spin.hidden=false;btn.disabled=true;
    out.style.display='none';

    try{
      const r=await fetch('/api/update-ytdlp',{method:'POST'});
      const d=await r.json();
      out.textContent=d.output||'No output';
      out.style.display='block';
      this.toast(d.success?'yt-dlp updated':'Update failed',d.success?'ok':'err');
    }catch{this.toast('Network error','err');}
    finally{label.hidden=false;spin.hidden=true;btn.disabled=false;}
  },

  async _updateGallerydl(){
    const btn=document.getElementById('update-gallerydl-btn');
    const label=btn.querySelector('span'),spin=btn.querySelector('.btn-spinner');
    const out=document.getElementById('update-output');
    label.hidden=true;spin.hidden=false;btn.disabled=true;
    out.style.display='none';

    try{
      const r=await fetch('/api/update-gallerydl',{method:'POST'});
      const d=await r.json();
      out.textContent=d.output||'No output';
      out.style.display='block';
      this.toast(d.success?'gallery-dl updated':'Update failed',d.success?'ok':'err');
    }catch{this.toast('Network error','err');}
    finally{label.hidden=false;spin.hidden=true;btn.disabled=false;}
  },

  /* ── Theme ───────────────────────────────────────────── */
  _bindTheme(){
    const saved=localStorage.getItem('hvd-theme')||'violet-cyan';
    this._applyTheme(saved);
    document.querySelectorAll('.theme-swatches .swatch').forEach(s=>{
      s.addEventListener('click',()=>{
        const name=s.dataset.theme;
        this._applyTheme(name);
        localStorage.setItem('hvd-theme',name);
        this.toast(`Accent theme changed`,'ok');
      });
    });
  },
  _applyTheme(name){
    const t=this.themes[name]||this.themes['violet-cyan'];
    Object.entries(t).forEach(([k,v])=>document.documentElement.style.setProperty(k,v));
    document.querySelectorAll('.theme-swatches .swatch').forEach(s=>{
      s.classList.toggle('active',s.dataset.theme===name);
    });
  },

  /* ── Clipboard ───────────────────────────────────────── */
  _bindClipboard(){
    // Completely disabled as per user request. 
    // Paste button must be clicked manually.
  },

  /* ── Notification ────────────────────────────────────── */
  notify(title){
    if(this.notified.has(title))return;
    this.notified.add(title);
    if(window.Notification&&Notification.permission==='granted'){
      try{new Notification('Horizon Video Downloader',{body:`Download Completed:\n${title}`});}catch(e){}
    }
  },

  /* ── Toast ───────────────────────────────────────────── */
  toast(msg,type='inf'){
    const c=document.getElementById('toast-container');
    const icons={ok:IC.tOk,err:IC.tErr,inf:IC.tInfo};
    const t=document.createElement('div');t.className=`toast ${type}`;
    t.innerHTML=`${icons[type]||icons.inf}<span>${msg}</span>`;
    c.appendChild(t);
    setTimeout(()=>{t.classList.add('bye');t.onanimationend=()=>t.remove();},3500);
  },

  /* ═══════════════ SOCIAL GALLERY TAB ═══════════════ */
  socialMode: 'media',
  socialFilter: 'all',
  socialItems: [],
  socialPost: null,
  activeLightboxItem: null,

  _bindSocial(){
    document.getElementById('social-fetch-btn')?.addEventListener('click',()=>this._fetchSocial());
    document.getElementById('social-url')?.addEventListener('keydown',e=>{if(e.key==='Enter')this._fetchSocial();});
    document.getElementById('social-dl-btn')?.addEventListener('click',()=>this._downloadSocialSelected());
    
    // Stop / Cancel Extraction Button
    document.getElementById('social-stop-btn')?.addEventListener('click', async () => {
      if (this._socialAbortController) {
        this._socialAbortController.abort();
      }
      try {
        await fetch('/api/social/stop', {method: 'POST'});
      } catch {}
      this.toast('Extraction stopped.', 'info');
      const loader = document.getElementById('social-loader');
      if (loader) loader.classList.add('hidden');
      const btn = document.getElementById('social-fetch-btn');
      if (btn) {
        const label = btn.querySelector('span');
        const spin = btn.querySelector('.btn-spinner');
        if (label) label.hidden = false;
        if (spin) spin.hidden = true;
        btn.disabled = false;
      }
    });

    // Mode Switch (Media vs Audio Extraction)
    document.querySelectorAll('#social-mode-seg .seg-btn').forEach(btn=>{
      btn.addEventListener('click',()=>{
        document.querySelectorAll('#social-mode-seg .seg-btn').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        this.socialMode = btn.dataset.socmode || 'media';
        const isAudio = this.socialMode === 'audio';
        document.getElementById('group-soc-vid')?.classList.toggle('hidden', isAudio);
        document.getElementById('group-soc-img')?.classList.toggle('hidden', isAudio);
        document.getElementById('group-soc-aud')?.classList.toggle('hidden', !isAudio);
        const dlSpan = document.querySelector('#social-dl-btn span');
        if(dlSpan) dlSpan.textContent = isAudio ? 'EXTRACT AUDIO FOR SELECTED' : 'DOWNLOAD SELECTED';
      });
    });

    // Filter Pills (All / Videos / Photos)
    document.querySelectorAll('.soc-pill-btn').forEach(btn=>{
      btn.addEventListener('click',()=>{
        document.querySelectorAll('.soc-pill-btn').forEach(b=>b.classList.remove('active'));
        btn.classList.add('active');
        this.socialFilter = btn.dataset.filter || 'all';
        this._filterSocialGrid();
      });
    });

    // Select All Checkbox
    document.getElementById('social-select-all')?.addEventListener('change',e=>{
      const chk = e.target.checked;
      document.querySelectorAll('.social-card:not(.hidden)').forEach(c=>{
        if(chk) c.classList.add('selected'); else c.classList.remove('selected');
      });
      this._updateSocialCount();
    });

    // Lightbox Modal Controls
    const closeLightbox = ()=>this._closeLightbox();
    document.getElementById('lightbox-close-btn')?.addEventListener('click', closeLightbox);
    document.getElementById('lightbox-backdrop')?.addEventListener('click', closeLightbox);
    document.addEventListener('keydown',e=>{ if(e.key==='Escape') this._closeLightbox(); });
    
    document.getElementById('lightbox-copy-btn')?.addEventListener('click',()=>{
      if(this.activeLightboxItem?.url){
        navigator.clipboard.writeText(this.activeLightboxItem.url).then(()=>{
          this.toast('Media URL copied to clipboard','ok');
        }).catch(()=>this.toast('Copy failed','err'));
      }
    });

    document.getElementById('lightbox-dl-btn')?.addEventListener('click',()=>{
      if(this.activeLightboxItem?.url){
        this._downloadSingleSocialItem(this.activeLightboxItem.url, this.activeLightboxItem.type);
      }
    });

    // Paste button for social tab
    const pbtn = document.querySelector('.paste-btn[data-target="social-url"]');
    if (pbtn) {
      pbtn.addEventListener('click', async () => {
        const target = document.getElementById(pbtn.dataset.target);
        if (!target) return;
        try {
          const t = await navigator.clipboard.readText();
          if (t) {
            target.value = t.trim();
            target.dispatchEvent(new Event('input'));
            this._fetchSocial();
          }
        } catch {
          this.toast('Clipboard access denied', 'err');
        }
      });
    }
  },

  async _fetchSocial(){
    const url=document.getElementById('social-url').value.trim();
    if(!url){this.toast('Paste a social media URL first','err');return;}
    const btn=document.getElementById('social-fetch-btn');
    const label=btn.querySelector('span'),spin=btn.querySelector('.btn-spinner');
    label.hidden=true;spin.hidden=false;btn.disabled=true;

    document.getElementById('social-post-card').style.display='none';
    document.getElementById('social-preview-section').style.display='none';
    document.getElementById('social-batch-progress')?.classList.add('hidden');
    const loader = document.getElementById('social-loader');
    if (loader) loader.classList.remove('hidden');
    const loaderText = document.getElementById('social-loader-text');
    if (loaderText) loaderText.textContent = 'Extracting media streams & scanning profile…';

    const settings=this._getSettings();
    const query = new URLSearchParams({ url });
    if(settings.cookie_file)query.append('cookie_file',settings.cookie_file);

    this._socialAbortController = new AbortController();

    try{
      const r=await fetch(`/api/fetch-social?${query.toString()}`, { signal: this._socialAbortController.signal });
      const d=await r.json();
      
      const items = Array.isArray(d) ? d : (d.items || []);
      const postInfo = d.post_info || {};

      if(r.ok && (items.length || postInfo.avatar_url)){
        this.socialItems = items;
        this.socialPost = postInfo;

        this._renderSocialPostCard(postInfo, items);
        if(items.length){
          this._renderSocialGrid(items);
          this.toast(`Found ${items.length} media items`,'ok');
        } else {
          document.getElementById('social-preview-section').style.display='none';
          this.toast('Account found! HD Profile Picture ready to download.','ok');
        }
      }else{
        this.toast(d.error||'No media items found','err');
      }
    }catch(err){
      if(err.name === 'AbortError') return;
      this.toast('Network error','err');
    }
    finally{
      this._socialAbortController = null;
      document.getElementById('social-loader')?.classList.add('hidden');
      label.hidden=false;spin.hidden=true;btn.disabled=false;
    }
  },

  _renderSocialPostCard(postInfo, items){
    const card = document.getElementById('social-post-card');
    if(!card) return;

    // Platform emblem
    const platform = (postInfo.platform || 'social').toLowerCase();
    const platLabels = {
      instagram: 'Instagram', tiktok: 'TikTok', twitter: 'Twitter / X',
      facebook: 'Facebook', reddit: 'Reddit', pinterest: 'Pinterest'
    };
    const platText = platLabels[platform] || platform.toUpperCase();
    const platBadge = document.getElementById('soc-platform-badge');
    if(platBadge) platBadge.textContent = platText;

    // Avatar & PFP Button
    const avatarImg = document.getElementById('soc-avatar-img');
    const avatarText = document.getElementById('soc-avatar-text');
    const pfpBtn = document.getElementById('soc-pfp-btn');
    const dot3 = document.getElementById('soc-dot3');

    if(postInfo.avatar_url){
      if(avatarImg){
        avatarImg.src = postInfo.avatar_url;
        avatarImg.classList.remove('hidden');
      }
      if(avatarText) avatarText.classList.add('hidden');
      if(pfpBtn){
        pfpBtn.classList.remove('hidden');
        if(dot3) dot3.style.display = 'inline';
        pfpBtn.onclick = () => {
          this._downloadSingleSocialItem(postInfo.avatar_url, 'image', `${postInfo.username || 'creator'}_hd_profile_picture`);
        };
      }
    } else {
      if(avatarImg) avatarImg.classList.add('hidden');
      if(avatarText) {
        avatarText.classList.remove('hidden');
        const authorInitials = postInfo.username ? postInfo.username.substring(0,2).toUpperCase() : platText.substring(0,2).toUpperCase();
        avatarText.textContent = authorInitials;
      }
      if(pfpBtn) pfpBtn.classList.add('hidden');
      if(dot3) dot3.style.display = 'none';
    }

    // Name & Username
    const fname = document.getElementById('soc-fullname');
    const uname = document.getElementById('soc-username');
    if(fname) fname.textContent = postInfo.fullname || postInfo.username || platText;
    if(uname) uname.textContent = postInfo.username ? `@${postInfo.username}` : '';

    // Date
    const dateEl = document.getElementById('soc-date');
    if(dateEl) dateEl.textContent = postInfo.date || 'Recent';

    // Likes
    const likesEl = document.getElementById('soc-likes');
    const dot1 = document.getElementById('soc-dot1');
    if(postInfo.likes != null){
      if(likesEl) { likesEl.style.display='inline'; likesEl.textContent = `❤️ ${fmtViews(postInfo.likes)}`; }
      if(dot1) dot1.style.display='inline';
    } else {
      if(likesEl) likesEl.style.display='none';
      if(dot1) dot1.style.display='none';
    }

    // Link
    const linkEl = document.getElementById('soc-post-link');
    if(linkEl && postInfo.post_url){
      linkEl.href = postInfo.post_url;
      linkEl.style.display = 'inline';
    } else if(linkEl) {
      linkEl.style.display = 'none';
    }

    // Caption with hashtag styling
    const capBox = document.getElementById('soc-caption-container');
    const capText = document.getElementById('soc-caption');
    if(capText && postInfo.caption && postInfo.caption.trim()){
      const cleanCap = esc(postInfo.caption.trim()).replace(/(#\w+)/g, '<span style="color:var(--accent-h);font-weight:600;">$1</span>');
      capText.innerHTML = cleanCap;
      if(capBox) capBox.style.display = 'block';
    } else if(capBox) {
      capBox.style.display = 'none';
    }

    card.style.display = 'flex';
  },

  _renderSocialGrid(items){
    const grid=document.getElementById('social-grid');
    grid.innerHTML='';

    // Update filter counts
    const vidCount = items.filter(i=>i.type==='video').length;
    const imgCount = items.filter(i=>i.type==='image').length;
    document.getElementById('pill-cnt-all').textContent = items.length;
    document.getElementById('pill-cnt-video').textContent = vidCount;
    document.getElementById('pill-cnt-image').textContent = imgCount;

    items.forEach((item,i)=>{
      const card=document.createElement('div');
      card.className='social-card selected';
      card.dataset.index=i;
      card.dataset.url=item.url;
      card.dataset.type=item.type;
      card.style.backgroundImage=`url('${item.thumbnail || item.url}')`;
      
      const badgeIcon = item.type === 'video' ? '🎬 VIDEO' : '🖼️ PHOTO';
      card.innerHTML=`
        <div class="card-top-row">
          <div class="checkbox-overlay"></div>
          <span class="type-badge">${badgeIcon}</span>
        </div>
        ${item.slide_index ? `<span class="slide-tag">Slide ${item.slide_index}</span>` : ''}
        <div class="card-hover-actions">
          <button class="card-action-btn soc-preview-btn" type="button"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="10" cy="10" r="3"/><path d="M2.5 10c1.7-4 5.3-6.5 7.5-6.5s5.8 2.5 7.5 6.5c-1.7 4-5.3 6.5-7.5 6.5s-5.8-2.5-7.5-6.5z"/></svg>Preview</button>
          <button class="card-action-btn soc-quickdl-btn" type="button"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M10 3v10m0 0l-3.5-3.5M10 13l3.5-3.5M3 15v2h14v-2"/></svg>Download</button>
          <button class="card-action-btn soc-copy-btn" type="button"><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="6" y="2" width="8" height="4" rx="1"/><rect x="3" y="4" width="14" height="14" rx="2"/></svg>Copy Link</button>
        </div>
      `;

      // Card selection toggle
      card.addEventListener('click',e=>{
        if(e.target.closest('.card-action-btn')) return;
        card.classList.toggle('selected');
        this._updateSocialCount();
      });

      // Preview Lightbox
      card.querySelector('.soc-preview-btn')?.addEventListener('click',e=>{
        e.stopPropagation();
        this._openLightbox(item);
      });

      // Quick Single Download
      card.querySelector('.soc-quickdl-btn')?.addEventListener('click',e=>{
        e.stopPropagation();
        this._downloadSingleSocialItem(item.url, item.type);
      });

      // Copy Link
      card.querySelector('.soc-copy-btn')?.addEventListener('click',e=>{
        e.stopPropagation();
        navigator.clipboard.writeText(item.url).then(()=>{
          this.toast('Link copied to clipboard','ok');
        }).catch(()=>this.toast('Copy failed','err'));
      });

      grid.appendChild(card);
    });

    document.getElementById('social-preview-section').style.display='block';
    this._filterSocialGrid();
    this._updateSocialCount();
  },

  _filterSocialGrid(){
    const f = this.socialFilter;
    document.querySelectorAll('.social-card').forEach(c=>{
      if(f === 'all') c.classList.remove('hidden');
      else if(f === 'video') c.classList.toggle('hidden', c.dataset.type !== 'video');
      else if(f === 'image') c.classList.toggle('hidden', c.dataset.type !== 'image');
    });
    this._updateSocialCount();
  },

  _updateSocialCount(){
    const selected = document.querySelectorAll('.social-card.selected:not(.hidden)');
    const totalVisible = document.querySelectorAll('.social-card:not(.hidden)');
    const n = selected.length;
    
    document.getElementById('social-sel-count').textContent = `${n}/${totalVisible.length}`;
    
    const selAll = document.getElementById('social-select-all');
    if(selAll) selAll.checked = (n === totalVisible.length && totalVisible.length > 0);

    const btn = document.getElementById('social-dl-btn');
    if (btn) {
      const span = btn.querySelector('span');
      const isAudio = this.socialMode === 'audio';
      const actionText = isAudio ? 'EXTRACT AUDIO FOR' : 'DOWNLOAD';
      if (span) span.textContent = n > 0 ? `${actionText} SELECTED (${n})` : `${actionText} SELECTED`;
      btn.disabled = n === 0;
    }
  },

  _openLightbox(item){
    this.activeLightboxItem = item;
    const modal = document.getElementById('social-lightbox-modal');
    const container = document.getElementById('lightbox-media-container');
    const title = document.getElementById('lightbox-title');
    const badge = document.getElementById('lightbox-type-badge');
    if(!modal || !container) return;

    container.innerHTML = '';
    if(badge) badge.textContent = item.type === 'video' ? 'VIDEO STREAM' : 'HIGH-RES IMAGE';
    if(title) title.textContent = `Slide #${item.slide_index || 1}`;

    if(item.type === 'video'){
      const vid = document.createElement('video');
      vid.controls = true;
      vid.autoplay = true;
      vid.loop = true;
      vid.src = item.url;
      container.appendChild(vid);
    } else {
      const img = document.createElement('img');
      img.src = item.url || item.thumbnail;
      container.appendChild(img);
    }

    modal.classList.remove('hidden');
  },

  _closeLightbox(){
    const modal = document.getElementById('social-lightbox-modal');
    const container = document.getElementById('lightbox-media-container');
    if(container){
      const vid = container.querySelector('video');
      if(vid) vid.pause();
      container.innerHTML = '';
    }
    if(modal) modal.classList.add('hidden');
    this.activeLightboxItem = null;
  },

  async _downloadSingleSocialItem(url, type, customCaption = null){
    const settings=this._getSettings();
    const socialDir = document.getElementById('social-dest-dir')?.value.trim() || settings.social_output_dir || settings.output_dir || undefined;
    const isAudio = this.socialMode === 'audio' && type === 'video';
    const body={
      urls: [url],
      output_dir: socialDir,
      image_format: document.getElementById('social-img-format')?.value || 'original',
      video_format: document.getElementById('social-vid-format')?.value || 'mp4',
      audio_only: isAudio,
      audio_format: document.getElementById('social-aud-format')?.value || 'mp3',
      creator: this.socialPost?.username,
      caption: customCaption || this.socialPost?.caption,
      organize_subfolder: document.getElementById('social-subfolder')?.checked || false,
      platform: this.socialPost?.platform || 'social'
    };
    this.toast(`Queued 1 item for download…`,'inf');
    try{
      const r = await fetch('/api/download-social', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body)
      });
      const d = await r.json();
      if(r.ok && d.success){
        this.toast(d.message || 'Download complete!','ok');
      } else {
        this.toast(d.error || 'Download failed','err');
      }
    } catch {
      this.toast('Network error during download','err');
    }
  },

  async _downloadSocialSelected(){
    const cards=[...document.querySelectorAll('.social-card.selected:not(.hidden)')];
    if(!cards.length){this.toast('No items selected','err');return;}
    const btn=document.getElementById('social-dl-btn');
    const label=btn.querySelector('span'),spin=btn.querySelector('.btn-spinner');
    label.hidden=true;spin.hidden=false;btn.disabled=true;

    const urls=cards.map(c=>c.dataset.url);
    const settings=this._getSettings();
    const socialDir = document.getElementById('social-dest-dir')?.value.trim() || settings.social_output_dir || settings.output_dir || undefined;
    const isAudio = this.socialMode === 'audio';

    const progBox = document.getElementById('social-batch-progress');
    const progStatus = document.getElementById('social-batch-status');
    const progCounter = document.getElementById('social-batch-counter');
    const progFill = document.getElementById('social-batch-fill');

    if(progBox) progBox.classList.remove('hidden');
    if(progStatus) progStatus.textContent = `Downloading ${urls.length} media items…`;
    if(progCounter) progCounter.textContent = `0 / ${urls.length}`;
    if(progFill) progFill.style.width = '20%';

    const body={
      urls,
      output_dir: socialDir,
      image_format:document.getElementById('social-img-format')?.value || 'original',
      video_format:document.getElementById('social-vid-format')?.value || 'mp4',
      audio_only: isAudio,
      audio_format: document.getElementById('social-aud-format')?.value || 'mp3',
      creator: this.socialPost?.username,
      caption: this.socialPost?.caption,
      organize_subfolder: document.getElementById('social-subfolder')?.checked || false,
      platform: this.socialPost?.platform || 'social'
    };

    try{
      const r=await fetch('/api/download-social',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(body)
      });
      const d=await r.json();
      if(r.ok&&d.success){
        if(progFill) progFill.style.width = '100%';
        if(progStatus) progStatus.textContent = d.message || 'Download complete!';
        if(progCounter) progCounter.textContent = `${d.downloaded || urls.length} / ${urls.length}`;
        this.toast(d.message||'Batch download complete','ok');
        cards.forEach(c=>c.classList.remove('selected'));
        this._updateSocialCount();
      }else{
        this.toast(d.error||'Download failed','err');
        if(progStatus) progStatus.textContent = 'Download encountered errors';
      }
    }catch{
      this.toast('Network error during download','err');
    }finally{
      label.hidden=false;spin.hidden=true;btn.disabled=false;
      this._updateSocialCount();
    }
  },

  async _restoreRecentDownloads(){
    try{
      const r = await fetch('/api/history');
      if(!r.ok) return;
      const history = await r.json();
      if(!Array.isArray(history) || history.length === 0) return;
      // Filter for recent completed tasks that have a record
      const recent = history.filter(h => h.status === 'completed').slice(0, 8);
      for(const item of recent.reverse()){
        const fname = item.filename || item.title || 'Downloaded Media';
        this.notified.add(fname);
        this.notified.add(item.id);
        if(!this.cards.has(item.id)){
          const taskData = {
            task_id: item.id,
            filename: fname,
            format_type: 'video',
            status: 'completed',
            progress: 100,
            speed: '',
            eta: '',
            is_restored: true
          };
          this._upsert(taskData);
        }
      }
    }catch(e){
      console.warn("Could not restore recent downloads:", e);
    }
  },

  /* ── History View Switcher & Rendering ────────────────── */
  _historyView: 'grid',
  _historyGroupMode: 'collections',

  _bindHistoryView(){
    this._historyView = localStorage.getItem('hvd_history_view') || 'grid';
    this._historyGroupMode = localStorage.getItem('hvd_history_group') || 'collections';

    const gridBtn = document.getElementById('hist-view-grid');
    const tableBtn = document.getElementById('hist-view-table');
    const colBtn = document.getElementById('hist-group-containers');
    const allBtn = document.getElementById('hist-group-all');
    const gridContainer = document.getElementById('history-grid-container');
    const tableContainer = document.getElementById('history-table-container');

    const updateView = () => {
      gridBtn?.classList.toggle('active', this._historyView === 'grid');
      tableBtn?.classList.toggle('active', this._historyView === 'table');
      colBtn?.classList.toggle('active', this._historyGroupMode === 'collections');
      allBtn?.classList.toggle('active', this._historyGroupMode === 'all');

      if (gridContainer && tableContainer) {
        if (this._historyView === 'grid') {
          gridContainer.style.display = 'grid';
          tableContainer.style.display = 'none';
        } else {
          gridContainer.style.display = 'none';
          tableContainer.style.display = 'block';
        }
      }
    };

    gridBtn?.addEventListener('click', () => {
      this._historyView = 'grid';
      localStorage.setItem('hvd_history_view', 'grid');
      updateView();
    });

    tableBtn?.addEventListener('click', () => {
      this._historyView = 'table';
      localStorage.setItem('hvd_history_view', 'table');
      updateView();
    });

    colBtn?.addEventListener('click', () => {
      this._historyGroupMode = 'collections';
      localStorage.setItem('hvd_history_group', 'collections');
      updateView();
      this.refreshHistory();
    });

    allBtn?.addEventListener('click', () => {
      this._historyGroupMode = 'all';
      localStorage.setItem('hvd_history_group', 'all');
      updateView();
      this.refreshHistory();
    });

    updateView();
  },

  toggleHistoryBatch(bid){
    const container = document.getElementById(`items-batch-${bid}`);
    const arrow = document.getElementById(`arrow-toggle-batch-${bid}`);
    const label = document.getElementById(`label-toggle-batch-${bid}`);
    if (!container) return;
    const isHidden = (container.style.display === 'none' || container.classList.contains('hidden'));
    if (isHidden) {
      container.style.display = 'block';
      container.classList.remove('hidden');
      if (arrow) arrow.style.transform = 'rotate(180deg)';
      if (label) label.textContent = 'Hide Items';
    } else {
      container.style.display = 'none';
      container.classList.add('hidden');
      if (arrow) arrow.style.transform = 'rotate(0deg)';
      if (label) {
        const count = container.querySelectorAll('.hist-card').length;
        label.textContent = `View Items (${count})`;
      }
    }
  },

  async openDirectory(path){
    if(!path) return;
    try {
      await fetch('/api/open-directory', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path })
      });
    } catch(e) {
      this.toast('Failed to open folder: ' + e.message, 'err');
    }
  },

  async deleteBatchHistory(bid){
    if(!confirm('Are you sure you want to delete this collection from history?')) return;
    try {
      const r = await fetch(`/api/history/delete-batch/${encodeURIComponent(bid)}`, { method: 'POST' });
      if(r.ok){
        const card = document.getElementById(`hist-batch-${bid}`);
        if(card) card.remove();
        this.toast('Collection removed from history', 'ok');
      }
    } catch(e) {
      this.toast('Delete error: ' + e.message, 'err');
    }
  },

  _renderHistory(data){
    const gridContainer = document.getElementById('history-grid-container');
    const tableRows = document.getElementById('history-rows');
    if (!gridContainer && !tableRows) return;

    if (!data || data.length === 0) {
      if (gridContainer) {
        gridContainer.innerHTML = '<div style="grid-column:1/-1; padding:36px; text-align:center; color:var(--text-3); font-size:0.92rem;">No download history found.</div>';
      }
      if (tableRows) {
        tableRows.innerHTML = '<tr><td colspan="6" style="padding:24px; text-align:center; color:var(--text-3);">No download history found.</td></tr>';
      }
      return;
    }

    const formatBytes = (bytes) => {
      if (!bytes || bytes <= 0) return '';
      const sizes = ['B', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(1024));
      return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + sizes[i];
    };

    const renderSingleCard = (item) => {
      const id = esc(item.id || '');
      const title = esc(item.filename || item.title || 'Untitled Download');
      const url = esc(item.url || '');
      const status = esc(item.status || 'completed');
      const dateStr = esc(item.timestamp || 'N/A');
      const sizeStr = item.file_size ? formatBytes(item.file_size) : '';
      const isCompleted = (status === 'completed');
      const thumbUrl = (item.file_exists || isCompleted) ? `/api/history/thumbnail/${id}` : (item.thumbnail || '');

      const thumbHtml = thumbUrl ? `
        <img class="hist-thumb-img" src="${esc(thumbUrl)}" alt="${title}" loading="lazy" onerror="this.onerror=null;this.parentElement.innerHTML='<div class=\\'hist-thumb-fallback\\'><svg viewBox=\\'0 0 24 24\\' fill=\\'none\\' stroke=\\'currentColor\\' stroke-width=\\'1.5\\'><polygon points=\\'5 3 19 12 5 21 5 3\\'/></svg></div>';">
      ` : `
        <div class="hist-thumb-fallback">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        </div>
      `;

      const playOverlay = isCompleted ? `
        <div class="hist-play-overlay" onclick="App.openFile('${id}')" title="Play Media File">
          <div class="hist-play-circle">
            <svg viewBox="0 0 24 24" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4"/></svg>
          </div>
        </div>
      ` : '';

      return `
        <div class="hist-card" id="hist-card-${id}">
          <div class="hist-thumb-wrap">
            ${thumbHtml}
            ${playOverlay}
            <span class="hist-status-badge ${status}">${status}</span>
            ${sizeStr ? `<span class="hist-format-badge">${sizeStr}</span>` : ''}
          </div>
          <div class="hist-card-body">
            <h4 class="hist-card-title" title="${title}">${title}</h4>
            <div class="hist-card-meta">
              <span>${dateStr}</span>
              ${url ? `<a href="${url}" target="_blank" style="color:var(--accent); text-decoration:none; font-size:0.75rem;" title="${url}">Source ↗</a>` : ''}
            </div>
            <div class="hist-card-actions">
              ${isCompleted ? `
                <button class="hist-action-btn play-btn" onclick="App.openFile('${id}')" title="Play Video with Default Player">
                  <svg viewBox="0 0 24 24" fill="currentColor" style="width:13px; height:13px;"><polygon points="6 4 20 12 6 20 6 4"/></svg>
                  Play
                </button>
                <button class="hist-action-btn" onclick="App.openFolder('${id}')" title="Show in File Explorer">
                  <span style="display:inline-block; width:13px; height:13px;">${IC.folder}</span>
                  Folder
                </button>
                <button class="hist-action-btn" onclick="App.showQR('${id}')" title="Send to Mobile Phone via QR">
                  <span style="display:inline-block; width:13px; height:13px;">${IC.qr}</span>
                  QR
                </button>
              ` : `<span style="flex:1; color:var(--text-3); font-size:0.75rem;">Status: ${status}</span>`}
              <button class="hist-action-btn del-btn" onclick="App.deleteHistoryItem('${id}')" title="Delete from history">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:14px; height:14px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </div>
          </div>
        </div>
      `;
    };

    const renderContainerCard = (grp) => {
      const bid = esc(grp.batch_id);
      const title = esc(grp.batch_title);
      const count = grp.items.length;
      const totalBytes = grp.items.reduce((acc, it) => acc + (it.file_size || 0), 0);
      const sizeStr = formatBytes(totalBytes);
      const dateStr = esc(grp.timestamp || 'N/A');
      const repItem = grp.items.find(it => it.thumbnail || it.file_exists) || grp.items[0];
      const repThumb = repItem ? (repItem.file_exists ? `/api/history/thumbnail/${repItem.id}` : (repItem.thumbnail || '')) : '';
      const folderPath = grp.folder_path || '';

      return `
        <div class="hist-container-card" id="hist-batch-${bid}" style="grid-column:1/-1; background:linear-gradient(135deg, rgba(255,255,255,0.03), rgba(139,92,246,0.06)); border:1px solid rgba(139,92,246,0.32); border-radius:12px; margin-bottom:12px; overflow:hidden;">
          <div class="hist-container-header" style="padding:14px 18px; display:flex; align-items:center; gap:16px; cursor:pointer;" onclick="App.toggleHistoryBatch('${bid}')">
            <div style="position:relative; width:64px; height:64px; min-width:64px; background:rgba(0,0,0,0.4); border-radius:8px; display:flex; align-items:center; justify-content:center; overflow:hidden; border:1px solid rgba(255,255,255,0.08);">
              ${repThumb ? `<img src="${esc(repThumb)}" style="width:100%; height:100%; object-fit:cover;">` : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" style="width:28px; height:28px; color:var(--accent);"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`}
            </div>
            <div style="flex:1; min-width:0;">
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px; flex-wrap:wrap;">
                <span style="font-size:0.7rem; font-weight:700; text-transform:uppercase; background:rgba(139,92,246,0.22); color:#c4b5fd; padding:2px 8px; border-radius:4px; border:1px solid rgba(139,92,246,0.35); letter-spacing:0.04em;">Batch Collection</span>
                <span style="font-size:0.75rem; color:var(--text-3);">${dateStr}</span>
              </div>
              <h4 style="margin:0; font-size:1.05rem; font-weight:700; color:var(--text-1); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${title}">${title}</h4>
              <div style="display:flex; align-items:center; gap:12px; font-size:0.8rem; color:var(--text-2); margin-top:4px;">
                <span style="font-weight:600; color:var(--accent);">${count} Media Items</span>
                ${sizeStr ? `<span>• ${sizeStr}</span>` : ''}
              </div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;" onclick="event.stopPropagation()">
              ${folderPath ? `
                <button class="btn btn-secondary btn-sm" onclick="App.openDirectory('${esc(folderPath.replace(/\\/g, '\\\\'))}')" title="Open collection folder in File Explorer" style="padding:6px 12px; font-size:0.8rem; display:inline-flex; align-items:center; gap:6px; border-radius:6px; cursor:pointer;">
                  <span style="display:inline-block; width:13px; height:13px;">${IC.folder}</span>
                  <span>Folder</span>
                </button>
              ` : ''}
              <button class="btn btn-secondary btn-sm" onclick="App.toggleHistoryBatch('${bid}')" id="btn-toggle-batch-${bid}" style="padding:6px 12px; font-size:0.8rem; font-weight:600; display:inline-flex; align-items:center; gap:6px; border-radius:6px; cursor:pointer;">
                <span id="label-toggle-batch-${bid}">View Items (${count})</span>
                <svg id="arrow-toggle-batch-${bid}" viewBox="0 0 20 20" fill="currentColor" style="width:14px; height:14px; transition:transform 0.2s;"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
              </button>
              <button class="btn btn-secondary btn-sm" onclick="App.deleteBatchHistory('${bid}')" title="Delete entire collection from history" style="padding:6px 10px; font-size:0.8rem; color:#f87171; border-radius:6px; cursor:pointer;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px; height:14px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              </button>
            </div>
          </div>
          <!-- Collapsible Items Sub-Grid -->
          <div id="items-batch-${bid}" class="hist-batch-items hidden" style="display:none; padding:16px 18px 18px; border-top:1px solid rgba(255,255,255,0.06); background:rgba(0,0,0,0.22);">
            <div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap:14px;">
              ${grp.items.map(it => renderSingleCard(it)).join('')}
            </div>
          </div>
        </div>
      `;
    };

    // 1. Grid Cards View
    if (gridContainer) {
      if (this._historyGroupMode === 'collections') {
        const groups = new Map();
        const standalone = [];

        data.forEach(item => {
          const bid = item.batch_id;
          if (bid) {
            if (!groups.has(bid)) {
              let fDir = '';
              if (item.file_path) {
                const p = item.file_path;
                fDir = p.includes('\\') ? p.substring(0, p.lastIndexOf('\\')) : p.substring(0, p.lastIndexOf('/'));
                if (fDir.endsWith('\\posts') || fDir.endsWith('/posts') || fDir.endsWith('\\reels') || fDir.endsWith('/reels') || fDir.endsWith('\\avatar') || fDir.endsWith('/avatar')) {
                  fDir = fDir.includes('\\') ? fDir.substring(0, fDir.lastIndexOf('\\')) : fDir.substring(0, fDir.lastIndexOf('/'));
                }
              }
              groups.set(bid, {
                batch_id: bid,
                batch_title: item.batch_title || 'Batch Collection',
                items: [],
                timestamp: item.timestamp,
                folder_path: fDir
              });
            }
            groups.get(bid).items.push(item);
          } else {
            standalone.push(item);
          }
        });

        let html = '';
        groups.forEach(grp => {
          if (grp.items.length >= 2) {
            html += renderContainerCard(grp);
          } else {
            grp.items.forEach(it => { html += renderSingleCard(it); });
          }
        });
        standalone.forEach(it => { html += renderSingleCard(it); });
        gridContainer.innerHTML = html;
      } else {
        gridContainer.innerHTML = data.map(item => renderSingleCard(item)).join('');
      }
    }

    // 2. Table View
    if (tableRows) {
      tableRows.innerHTML = data.map(item => {
        const id = esc(item.id || '');
        const title = esc(item.filename || item.title || 'Untitled');
        const url = esc(item.url || '');
        const status = esc(item.status || 'completed');
        const isCompleted = (status === 'completed');
        const dateStr = esc(item.timestamp || 'N/A');
        const shortUrl = url.length > 36 ? url.slice(0, 33) + '...' : url;
        const thumbUrl = (item.file_exists || isCompleted) ? `/api/history/thumbnail/${id}` : (item.thumbnail || '');

        const thumbImgHtml = thumbUrl ? `
          <img class="hist-table-thumb" src="${esc(thumbUrl)}" alt="${title}" loading="lazy" onerror="this.onerror=null;this.style.display='none';">
        ` : `<div style="width:64px; height:38px; background:rgba(255,255,255,0.05); border-radius:4px; display:flex; align-items:center; justify-content:center; color:var(--text-3); font-size:0.7rem;">Media</div>`;

        const actionsHtml = isCompleted ? `
          <div style="display:inline-flex; gap:6px; justify-content:flex-end; width:100%;">
            <button class="btn btn-secondary btn-sm" onclick="App.openFile('${id}')" title="Play Video" style="padding:4px 8px; font-size:0.75rem; border-radius:4px; display:inline-flex; align-items:center; gap:4px; cursor:pointer;">
              <svg viewBox="0 0 24 24" fill="currentColor" style="width:11px; height:11px;"><polygon points="6 4 20 12 6 20 6 4"/></svg> Play
            </button>
            <button class="btn btn-secondary btn-sm" onclick="App.showQR('${id}')" title="QR Code / Send to Phone" style="padding:4px 8px; font-size:0.75rem; border-radius:4px; display:inline-flex; align-items:center; gap:4px; cursor:pointer;">
              <span style="display:inline-block; width:12px; height:12px;">${IC.qr}</span>
            </button>
            <button class="btn btn-secondary btn-sm" onclick="App.openFolder('${id}')" title="Show in File Explorer" style="padding:4px 8px; font-size:0.75rem; border-radius:4px; display:inline-flex; align-items:center; gap:4px; cursor:pointer;">
              <span style="display:inline-block; width:12px; height:12px;">${IC.folder}</span>
            </button>
            <button class="btn btn-secondary btn-sm" onclick="App.deleteHistoryItem('${id}')" title="Delete from history" style="padding:4px 6px; font-size:0.75rem; border-radius:4px; color:#f87171; cursor:pointer;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:12px; height:12px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </div>
        ` : `
          <div style="display:inline-flex; gap:6px; justify-content:flex-end;">
            <button class="btn btn-secondary btn-sm" onclick="App.deleteHistoryItem('${id}')" title="Delete from history" style="padding:4px 6px; font-size:0.75rem; border-radius:4px; color:#f87171; cursor:pointer;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:12px; height:12px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </div>
        `;

        return `
          <tr style="border-bottom:1px solid rgba(255,255,255,0.05);" id="hist-row-${id}">
            <td style="padding:8px;">${thumbImgHtml}</td>
            <td style="padding:12px 8px; font-size:0.82rem; color:var(--text-3);">${dateStr}</td>
            <td style="padding:12px 8px; font-weight:500;" title="${title}">${title}</td>
            <td style="padding:12px 8px; font-size:0.82rem;" title="${url}"><a href="${url}" target="_blank" style="color:var(--accent); text-decoration:none;">${esc(shortUrl)}</a></td>
            <td style="padding:12px 8px;"><span class="badge ${status}">${status}</span></td>
            <td style="padding:12px 8px; text-align:right;">${actionsHtml}</td>
          </tr>
        `;
      }).join('');
    }
  },

  async _loadHistory(){
    try{
      const r = await fetch('/api/history');
      const data = r.ok ? await r.json() : [];
      this._renderHistory(data);
    }catch(e){
      const grid = document.getElementById('history-grid-container');
      const rows = document.getElementById('history-rows');
      if (grid) grid.innerHTML = '<div style="grid-column:1/-1; padding:32px; text-align:center; color:var(--accent-dim);">Failed to load history.</div>';
      if (rows) rows.innerHTML = '<tr><td colspan="6" style="padding:20px; text-align:center; color:var(--accent-dim);">Failed to load history.</td></tr>';
    }
  },

  /* ── Creator Watchlist & Inventory Sync ────────────────── */
  _bindCreatorWatchlist(){
    const input = document.getElementById('set-creator-input');
    const addBtn = document.getElementById('btn-add-creator');
    const syncBtn = document.getElementById('btn-sync-inventory');

    const doAdd = async () => {
      const val = input ? input.value.trim() : '';
      if (!val) {
        this.toast('Enter creator username or profile URL', 'err');
        return;
      }
      try {
        const r = await fetch('/api/inventory/add', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({creator: val})
        });
        const res = await r.json();
        if (r.ok && res.success) {
          input.value = '';
          this.toast(`Added ${res.creator || val} to watchlist!`, 'ok');
          this._loadCreatorWatchlist();
        } else {
          this.toast(res.error || 'Failed to add creator', 'err');
        }
      } catch (e) {
        this.toast('Network error', 'err');
      }
    };

    addBtn?.addEventListener('click', doAdd);
    input?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') doAdd();
    });

    syncBtn?.addEventListener('click', async () => {
      const progBox = document.getElementById('sync-inventory-progress');
      const progText = document.getElementById('sync-status-text');
      if (progBox) progBox.style.display = 'block';
      if (progText) progText.textContent = 'Syncing creators inventory & checking for new posts…';
      this.toast('⚡ Inventory sync started in background...', 'info');

      try {
        const r = await fetch('/api/inventory/sync', {method: 'POST'});
        const res = await r.json();
        if (r.ok && res.success) {
          if (progText) progText.textContent = `Sync completed! Downloaded ${res.downloaded_count || 0} new media items.`;
          this.toast(`✨ Inventory synced! Downloaded ${res.downloaded_count || 0} new items (${res.skipped_count || 0} already archived)`, 'ok');
          setTimeout(() => {
            if (progBox) progBox.style.display = 'none';
          }, 4000);
          this._loadHistory();
        } else {
          if (progText) progText.textContent = res.error || 'Inventory sync encountered an issue';
          this.toast(res.error || 'Inventory sync failed', 'err');
        }
      } catch (e) {
        if (progText) progText.textContent = 'Network error during inventory sync';
        this.toast('Network error during sync', 'err');
      }
    });

    this._loadCreatorWatchlist();
  },

  async _loadCreatorWatchlist(){
    const listEl = document.getElementById('creator-chips-list');
    if (!listEl) return;
    try {
      const r = await fetch('/api/inventory/list');
      const data = r.ok ? await r.json() : [];
      if (!data || data.length === 0) {
        listEl.innerHTML = '<span class="empty-chips-hint" style="color:var(--text-3); font-size:0.85rem; align-self:center;">No creators added yet. Add a username above!</span>';
        return;
      }
      listEl.innerHTML = data.map(creator => {
        const c = esc(creator);
        const initial = c.replace(/^@/, '').charAt(0).toUpperCase() || '@';
        return `
          <div class="creator-chip">
            <span class="creator-chip-avatar">${initial}</span>
            <span>${c}</span>
            <button class="creator-chip-del" onclick="App.removeCreator('${c}')" title="Remove ${c}">
              <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" style="width:12px; height:12px;"><line x1="15" y1="5" x2="5" y2="15"/><line x1="5" y1="5" x2="15" y2="15"/></svg>
            </button>
          </div>
        `;
      }).join('');
    } catch {
      listEl.innerHTML = '<span style="color:var(--accent-dim); font-size:0.82rem;">Could not load watchlist.</span>';
    }
  },

  async removeCreator(creator){
    try {
      const r = await fetch('/api/inventory/remove', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({creator})
      });
      if (r.ok) {
        this.toast(`Removed ${creator} from watchlist`, 'info');
        this._loadCreatorWatchlist();
      }
    } catch {
      this.toast('Network error', 'err');
    }
  },

  /* ── App Updates ───────────────────────────────────────── */
  _bindAppUpdate(){
    const checkBtn = document.getElementById('btn-check-app-update');
    const spinner = document.getElementById('update-check-spinner');
    const container = document.getElementById('app-update-container');

    checkBtn?.addEventListener('click', async () => {
      if (spinner) spinner.hidden = false;
      try {
        const r = await fetch('/api/app-update/check');
        const res = await r.json();
        if (spinner) spinner.hidden = true;
        if (r.ok && res.update_available) {
          if (container) {
            container.style.display = 'block';
            container.innerHTML = `
              <div class="app-update-card">
                <div class="app-update-header">
                  <span class="app-update-ver">✨ Horizon ${esc(res.latest_version)} Available! (Current: ${esc(res.current_version)})</span>
                  <span class="badge completed">New Release</span>
                </div>
                <div class="app-update-notes">
                  <strong>What's New in ${esc(res.latest_version)}:</strong><br>
                  ${esc(res.release_notes || 'Exciting improvements, performance fixes, and new features.').replace(/\\n/g, '<br>')}
                </div>
                <button class="app-install-btn" id="btn-apply-update" type="button">
                  <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" style="width:16px; height:16px;"><path d="M4 16v1a2 2 0 002 2h8a2 2 0 002-2v-1M10 2v10m0 0l-4-4m4 4l4-4"/></svg>
                  <span>1-Click Download & Update Now</span>
                </button>
              </div>
            `;
            document.getElementById('btn-apply-update')?.addEventListener('click', async (e) => {
              const btn = e.currentTarget;
              btn.disabled = true;
              btn.innerHTML = `<span class="spinner-ring sm" style="width:16px; height:16px;"></span> <span>Downloading update & launching installer...</span>`;
              try {
                const instR = await fetch('/api/app-update/install', {
                  method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({download_url: res.download_url, version: res.latest_version})
                });
                const instRes = await instR.json();
                if (instR.ok && instRes.success) {
                  btn.innerHTML = `<span>✅ Installer launched! Horizon will restart.</span>`;
                  this.toast('Horizon is updating! Please allow a few seconds for the installer to finish and relaunch.', 'ok');
                } else {
                  btn.disabled = false;
                  btn.textContent = 'Retry Update';
                  this.toast(instRes.error || 'Update failed', 'err');
                }
              } catch (err) {
                btn.disabled = false;
                btn.textContent = 'Retry Update';
                this.toast('Network error during update download', 'err');
              }
            });
          }
        } else if (r.ok && !res.update_available) {
          if (container) {
            container.style.display = 'block';
            container.innerHTML = `
              <div style="padding:10px 14px; background:rgba(74,222,128,0.1); border:1px solid rgba(74,222,128,0.3); border-radius:8px; font-size:0.85rem; color:#4ade80; display:flex; align-items:center; gap:8px;">
                <svg viewBox="0 0 20 20" fill="currentColor" style="width:16px; height:16px;"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>
                <span>You are running the latest version of Horizon (${esc(res.current_version)})!</span>
              </div>
            `;
          }
          this.toast(`Horizon is up to date (v${res.current_version})`, 'ok');
        } else {
          this.toast(res.error || 'Failed to check updates', 'err');
        }
      } catch (err) {
        if (spinner) spinner.hidden = true;
        this.toast('Failed to reach GitHub release server', 'err');
      }
    });
  },

  /* ── Thumbnail Downloader ────────────────────────────── */
  _currentThumbnailData: null,
  _selectedThumbnailUrl: '',

  _bindThumbnail(){
    const fetchBtn = document.getElementById('thumb-fetch-btn');
    const urlInput = document.getElementById('thumb-url');
    if (fetchBtn) {
      fetchBtn.addEventListener('click', () => this._fetchThumbnail());
    }
    if (urlInput) {
      urlInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') this._fetchThumbnail();
      });
    }

    const dlJpg = document.getElementById('thumb-btn-download-jpg');
    if (dlJpg) dlJpg.addEventListener('click', () => this._downloadThumbnail('jpg'));

    const dlPng = document.getElementById('thumb-btn-download-png');
    if (dlPng) dlPng.addEventListener('click', () => this._downloadThumbnail('png'));

    const copyBtn = document.getElementById('thumb-btn-copy');
    if (copyBtn) copyBtn.addEventListener('click', () => this._copyThumbnailToClipboard());
  },

  async _fetchThumbnail(){
    const input = document.getElementById('thumb-url');
    const url = (input?.value || '').trim();
    if (!url) {
      this.toast('Please enter a video or social media URL', 'err');
      return;
    }

    const btn = document.getElementById('thumb-fetch-btn');
    const spin = btn?.querySelector('.btn-spinner');
    const label = btn?.querySelector('span');
    if (btn) btn.disabled = true;
    if (spin) spin.hidden = false;
    if (label) label.hidden = true;

    const loader = document.getElementById('thumb-loader');
    const emptyState = document.getElementById('thumb-empty-state');
    const resultCard = document.getElementById('thumb-result-card');

    if (loader) loader.style.display = 'flex';
    if (emptyState) emptyState.style.display = 'none';
    if (resultCard) resultCard.style.display = 'none';

    try {
      const res = await fetch('/api/thumbnail', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url})
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error || 'Failed to extract thumbnail');
      }

      this._currentThumbnailData = data;
      this._renderThumbnailData(data);
    } catch (err) {
      this.toast(err.message || 'Error fetching thumbnail', 'err');
      if (emptyState) emptyState.style.display = 'flex';
    } finally {
      if (btn) btn.disabled = false;
      if (spin) spin.hidden = true;
      if (label) label.hidden = false;
      if (loader) loader.style.display = 'none';
    }
  },

  _renderThumbnailData(data){
    const resultCard = document.getElementById('thumb-result-card');
    const titleEl = document.getElementById('thumb-title');
    const uploaderEl = document.getElementById('thumb-uploader');
    const platformEl = document.getElementById('thumb-platform');
    const previewImg = document.getElementById('thumb-preview-img');
    const resBadge = document.getElementById('thumb-res-badge');
    const chipsCont = document.getElementById('thumb-chips');
    const openBtn = document.getElementById('thumb-btn-open');

    if (titleEl) titleEl.textContent = data.title || 'Untitled';
    if (uploaderEl) uploaderEl.textContent = data.uploader ? `by ${data.uploader}` : '';
    if (platformEl) platformEl.textContent = data.platform || 'Media';

    const thumbs = data.thumbnails || [];
    const activeThumb = thumbs[0] || {url: data.best_url, label: 'Standard', width: 0, height: 0};
    this._selectedThumbnailUrl = activeThumb.url;

    if (previewImg) {
      previewImg.src = activeThumb.url;
    }
    if (resBadge) {
      resBadge.textContent = activeThumb.label || (activeThumb.width ? `${activeThumb.width} × ${activeThumb.height}` : 'HD');
    }
    if (openBtn) {
      openBtn.href = activeThumb.url;
    }

    if (chipsCont) {
      chipsCont.innerHTML = '';
      thumbs.forEach((t, idx) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = `thumb-chip ${idx === 0 ? 'active' : ''}`;
        chip.textContent = t.label || `${t.width || ''} × ${t.height || ''}`.trim() || `Option ${idx + 1}`;
        chip.addEventListener('click', () => {
          chipsCont.querySelectorAll('.thumb-chip').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
          this._selectedThumbnailUrl = t.url;
          if (previewImg) previewImg.src = t.url;
          if (resBadge) resBadge.textContent = t.label;
          if (openBtn) openBtn.href = t.url;
        });
        chipsCont.appendChild(chip);
      });
    }

    if (resultCard) {
      resultCard.style.display = 'flex';
      resultCard.classList.remove('hidden');
    }
  },

  async _downloadThumbnail(fmt){
    const url = this._selectedThumbnailUrl;
    if (!url) {
      this.toast('No thumbnail selected', 'err');
      return;
    }
    const title = (this._currentThumbnailData && this._currentThumbnailData.title) || 'thumbnail';
    this.toast(`Saving ${fmt.toUpperCase()} thumbnail...`, 'info');

    try {
      const res = await fetch('/api/save-thumbnail', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          image_url: url,
          title: title,
          format: fmt
        })
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || 'Failed to save thumbnail');
      }
      this.toast(`Saved: ${data.filename}`, 'success');
      this.notify('Thumbnail Saved', `Saved ${data.filename} to Downloads`);
    } catch (err) {
      this.toast(err.message || 'Failed to download thumbnail', 'err');
    }
  },

  async _copyThumbnailToClipboard(){
    const url = this._selectedThumbnailUrl;
    if (!url) {
      this.toast('No thumbnail to copy', 'err');
      return;
    }
    const label = document.getElementById('thumb-copy-label');
    const origText = label ? label.textContent : 'Copy to Clipboard';

    try {
      if (label) label.textContent = 'Copying...';
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.src = url;
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = () => reject(new Error('Cross-origin restricted'));
      });

      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth || img.width;
      canvas.height = img.naturalHeight || img.height;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);

      canvas.toBlob(async (blob) => {
        if (!blob) throw new Error('Canvas conversion failed');
        await navigator.clipboard.write([
          new ClipboardItem({'image/png': blob})
        ]);
        if (label) label.textContent = 'Copied! ✓';
        this.toast('Thumbnail copied to clipboard! (Ready to paste)', 'success');
        setTimeout(() => {
          if (label) label.textContent = origText;
        }, 2500);
      }, 'image/png');
    } catch (err) {
      try {
        await navigator.clipboard.writeText(url);
        if (label) label.textContent = 'Link Copied! ✓';
        this.toast('Thumbnail image URL copied to clipboard!', 'info');
        setTimeout(() => {
          if (label) label.textContent = origText;
        }, 2500);
      } catch (e2) {
        this.toast('Could not copy to clipboard', 'err');
        if (label) label.textContent = origText;
      }
    }
  },
};

document.addEventListener('DOMContentLoaded',()=>App.init());
