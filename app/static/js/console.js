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

  // ---------- çökme analizi kartı ----------
  const crashBox = document.getElementById('crash-box');
  function showCrash(c) {
    if (!crashBox) return;
    crashBox.replaceChildren();
    if (!c || !Array.isArray(c.items) || (!c.items.length && !c.report)) return;
    const mk = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
    const box = mk('div', 'alert alert-danger crash-card mb-2');
    const head = mk('div', 'd-flex justify-content-between align-items-start gap-2');
    const h = mk('div', 'fw-semibold'); h.appendChild(mk('i', 'bi bi-bug me-1')); h.appendChild(document.createTextNode('Çökme analizi'));
    const x = mk('button', 'btn-close btn-sm'); x.type = 'button'; x.title = 'Gizle'; x.addEventListener('click', () => crashBox.replaceChildren());
    head.append(h, x); box.appendChild(head);
    if (c.report) box.appendChild(mk('div', 'small text-body-secondary mb-1', 'Rapor: crash-reports/' + c.report + (c.description ? ' — ' + c.description : '')));
    if (!c.items.length) box.appendChild(mk('div', 'small', 'Bilinen bir neden bulunamadı. Konsolun son satırlarına ve crash raporuna bak.'));
    c.items.forEach(f => {
      const d = mk('div', 'crash-item');
      d.appendChild(mk('div', 'fw-semibold small', f.title));
      d.appendChild(mk('div', 'small', f.detail));
      d.appendChild(mk('div', 'small text-body-secondary', 'Öneri: ' + f.fix));
      box.appendChild(d);
    });
    crashBox.appendChild(box);
  }

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
        showCrash(m.crash);
      }
      else if (m.type === 'crash') showCrash(m);
      else if (m.type === 'progress') prog.show(m);
      else if (m.type === 'progress_end') prog.hide();
      else if (m.type === 'log') addLines([m.line]);
      else if (m.type === 'status') setStatus(m.status);
      else if (m.type === 'clear') out.replaceChildren();
      else if (m.type === 'meta' && Number.isInteger(m.java_major)) {
        const j = document.getElementById('meta-java'); if (j) j.textContent = 'Java ' + m.java_major + ' · ';
      }
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
