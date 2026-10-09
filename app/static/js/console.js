(function () {
  const root = document.getElementById('console-root');
  if (!root) return;

  const id = root.dataset.instanceId;
  const out = document.getElementById('console-output');
  const input = document.getElementById('console-input');
  const sendBtn = document.getElementById('console-send');
  const statusEl = document.getElementById('instance-status');
  const buttons = document.querySelectorAll('[data-action]');
  const updBtn = document.getElementById('paper-update-btn');
  const modsBtn = document.getElementById('mods-update-btn');

  const LABELS = { running: 'Çalışıyor', stopped: 'Durdu', preparing: 'Hazırlanıyor', starting: 'Başlıyor', stopping: 'Durduruluyor', crashed: 'Çöktü' };
  const prog = VuluProgress.attach('prep');
  const MAX_LINES = 2000;
  const ANSI = /\x1b\[[0-9;]*[A-Za-z]/g;

  let stick = true;
  let ws = null;
  let retry = 0;
  const cmdHistory = [];
  let histPos = 0;

  out.addEventListener('scroll', () => {
    stick = out.scrollTop + out.clientHeight >= out.scrollHeight - 24;
  });

  function lineClass(t) {
    if (t.startsWith('[panel]')) return 'log-panel';
    if (t.startsWith('> ')) return 'log-cmd';
    if (/\b(ERROR|FATAL)\b|Exception/.test(t)) return 'log-error';
    if (/\bWARN\b/.test(t)) return 'log-warn';
    return '';
  }

  function addLines(lines) {
    const frag = document.createDocumentFragment();
    for (const raw of lines) {
      const t = raw.replace(ANSI, '');
      const d = document.createElement('div');
      const c = lineClass(t);
      if (c) d.className = c;
      d.textContent = t || '\u00a0';   // textContent: log içeriği HTML olarak yorumlanmaz
      frag.appendChild(d);
    }
    out.appendChild(frag);
    while (out.childElementCount > MAX_LINES) out.removeChild(out.firstChild);
    if (stick) out.scrollTop = out.scrollHeight;
  }

  function setStatus(s) {
    statusEl.className = 'status status-' + s;
    statusEl.querySelector('.status-label').textContent = LABELS[s] || s;
    const active = s === 'running' || s === 'starting' || s === 'stopping' || s === 'preparing';
    buttons.forEach(b => {
      b.disabled = b.dataset.action === 'start' ? active : (s === 'stopped' || s === 'crashed');
    });
    if (updBtn) updBtn.disabled = active;
    if (modsBtn) modsBtn.disabled = active;
    input.disabled = !(s === 'running' || s === 'starting');
    sendBtn.disabled = input.disabled;
  }

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws/instances/${id}/console`);
    ws.onopen = () => { retry = 0; };
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.type === 'history') {
        out.replaceChildren(); stick = true; addLines(m.lines); setStatus(m.status);
        if (m.progress) prog.show(m.progress); else prog.hide();
      }
      else if (m.type === 'progress') prog.show(m);
      else if (m.type === 'progress_end') prog.hide();
      else if (m.type === 'log') addLines([m.line]);
      else if (m.type === 'status') setStatus(m.status);
      else if (m.type === 'clear') out.replaceChildren();
      else if (m.type === 'error') addLines(['[panel] ' + m.message]);
    };
    ws.onclose = () => setTimeout(connect, Math.min(1000 * 2 ** retry++, 8000));
  }

  function sendCmd() {
    const v = input.value.trim();
    if (!v || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ cmd: v }));
    cmdHistory.push(v);
    histPos = cmdHistory.length;
    input.value = '';
  }

  sendBtn.addEventListener('click', sendCmd);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendCmd();
    else if (e.key === 'ArrowUp' && histPos > 0) { input.value = cmdHistory[--histPos]; e.preventDefault(); }
    else if (e.key === 'ArrowDown') {
      histPos = Math.min(histPos + 1, cmdHistory.length);
      input.value = cmdHistory[histPos] || '';
      e.preventDefault();
    }
  });

  buttons.forEach(b => b.addEventListener('click', async () => {
    const a = b.dataset.action;
    if (a === 'kill' && !confirm('Süreç zorla sonlandırılsın mı? Kaydedilmemiş dünya verisi kaybolabilir.')) return;
    try {
      const r = await fetch(`/api/instances/${id}/${a}`, { method: 'POST' });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        addLines(['[panel] ' + (j.detail || 'Hata: ' + r.status)]);
      }
    } catch (e) {
      addLines(['[panel] Panele ulaşılamadı.']);
    }
  }));

  if (updBtn) updBtn.addEventListener('click', async () => {
    try {
      const r = await fetch(`/api/instances/${id}/paper/update`, { method: 'POST' });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) addLines(['[panel] ' + (j.detail || 'Hata: ' + r.status)]);
      else if (j.message) addLines(['[panel] ' + j.message]);
    } catch (e) {
      addLines(['[panel] Panele ulaşılamadı.']);
    }
  });

  if (modsBtn) modsBtn.addEventListener('click', async () => {
    try {
      const r = await fetch(`/api/instances/${id}/mods/update`, { method: 'POST' });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) addLines(['[panel] ' + (j.detail || 'Hata: ' + r.status)]);
    } catch (e) {
      addLines(['[panel] Panele ulaşılamadı.']);
    }
  });

  setStatus(root.dataset.status);
  connect();
})();
