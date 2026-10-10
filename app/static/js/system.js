(function () {
  const root = document.getElementById('system-root');
  if (!root) return;
  const $ = (k) => document.getElementById(k);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const note = (kind, text) => $('notes').replaceChildren(el('div', `alert alert-${kind} py-2 small mb-2`, text));
  const fmt = (n) => n >= 1073741824 ? (n / 1073741824).toFixed(1) + ' GB' : n >= 1048576 ? (n / 1048576).toFixed(0) + ' MB' : n >= 1024 ? (n / 1024).toFixed(0) + ' KB' : n + ' B';
  const prog = VuluProgress.attach('java');
  let watching = new Set();
  async function api(path, data) {
    const r = await fetch('/api/' + path, data ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) } : undefined);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : (_t('Hata ') + r.status));
    return j;
  }
  function btn(icon, text, cls, fn) {
    const b = el('button', 'btn btn-sm ' + cls); b.type = 'button';
    b.appendChild(el('i', 'bi ' + icon)); if (text) b.appendChild(document.createTextNode(' ' + text));
    b.addEventListener('click', fn); return b;
  }

  const PARTS = [['instances', _t('Sunucular'), 'var(--accent)'], ['backups', _t('Yedekler'), 'var(--warning)'], ['runtimes', 'Java', 'var(--success)'], ['cache', _t('Önbellek'), 'var(--accent-2)']];
  function renderDisk(d) {
    const bar = $('disk-bar'); bar.replaceChildren();
    const other = Math.max(0, d.used - Object.values(d.parts).reduce((a, b) => a + b, 0));
    [...PARTS.map(([k, , c]) => [d.parts[k], c]), [other, 'var(--border)']].forEach(([v, c]) => {
      const s = el('span'); s.style.width = (100 * v / d.total) + '%'; s.style.background = c; bar.appendChild(s);
    });
    const lg = $('disk-legend'); lg.replaceChildren();
    PARTS.forEach(([k, label, c]) => {
      const col = el('div', 'col-6 col-md'), dot = el('span', 'legend-dot'); dot.style.background = c;
      col.append(dot, document.createTextNode(` ${label}: ${fmt(d.parts[k])}`)); lg.appendChild(col);
    });
    const free = el('div', 'col-12 col-md text-md-end ' + (d.free < 5 * 1073741824 ? 'text-warning' : 'text-body-secondary'), _t("Boş: {v0} / {v1}", {v0: fmt(d.free), v1: fmt(d.total)}));
    lg.appendChild(free);
  }

  function renderJava(j) {
    const body = $('java-body'); body.replaceChildren();
    if (!j.java.length) { const tr = el('tr'), td = el('td', 'text-body-secondary', _t('Panel henüz hiç Java kurmadı.')); td.colSpan = 5; tr.appendChild(td); body.appendChild(tr); }
    j.java.forEach(r => {
      const tr = el('tr');
      tr.appendChild(el('td', 'fw-semibold', _t("Java {major}", {major: r.major})));
      tr.appendChild(el('td', 'small text-body-secondary', [r.vendor, r.image_type && r.image_type.toUpperCase(), r.version].filter(Boolean).join(' · ')));
      tr.appendChild(el('td', 'text-end small', fmt(r.size)));
      const users = el('td', 'small');
      if (!r.used_by.length) users.appendChild(el('span', 'text-body-secondary', _t('kullanılmıyor')));
      r.used_by.forEach(u => { const a = el('a', 'badge text-bg-secondary me-1 text-decoration-none', u.name + (u.status === 'running' ? ' ●' : '')); a.href = '/instances/' + u.id; users.appendChild(a); });
      tr.appendChild(users);
      const act = el('td', 'text-end');
      act.appendChild(btn('bi-trash', '', 'btn-outline-danger', async () => {
        const who = r.used_by.map(u => u.name).join(', ');
        if (!confirm(_t("Java {major} silinsin mi?", {major: r.major}) + (who ? _t(`\nKullanan sunucular: {who}\nBu sunucular bir sonraki başlatılışta Java'yı yeniden indirir.`, {who}) : ''))) return;
        try { await api('system/java/delete', { major: r.major }); VuluModal.toast(_t("Java {major} silindi.", {major: r.major}), 'success'); load(); }
        catch (e) { note('danger', String(e.message || e)); }
      }));
      tr.appendChild(act); body.appendChild(tr);
    });
    Object.entries(j.missing_for || {}).forEach(([m, users]) => {
      if (j.java.some(x => String(x.major) === m)) return;
      const tr = el('tr', 'opacity-75');
      tr.appendChild(el('td', '', _t("Java {m}", {m}))); tr.appendChild(el('td', 'small text-warning', _t('kurulu değil (ilk başlatmada iner)')));
      tr.appendChild(el('td')); tr.appendChild(el('td', 'small', users.map(u => u.name).join(', '))); tr.appendChild(el('td'));
      body.appendChild(tr);
    });
  }

  function renderCache(list) {
    const body = $('cache-body'); body.replaceChildren();
    list.forEach(c => {
      const tr = el('tr');
      tr.appendChild(el('td', '', c.label));
      tr.appendChild(el('td', 'text-end small', String(c.files)));
      tr.appendChild(el('td', 'text-end small', fmt(c.size)));
      const act = el('td', 'text-end');
      const b = btn('bi-eraser', _t('Temizle'), 'btn-outline-secondary', async () => {
        if (!confirm(_t("{label} önbelleği temizlensin mi? ({v1})", {label: c.label, v1: fmt(c.size)}))) return;
        try { const r = await api('system/cache/clear', { kind: c.kind }); VuluModal.toast(_t('{n} dosya silindi.', {n: r.removed}), 'success'); load(); }
        catch (e) { note('danger', String(e.message || e)); }
      });
      b.disabled = !c.files; act.appendChild(b); tr.appendChild(act); body.appendChild(tr);
    });
  }

  function watchInstall(jobId, major) {
    if (watching.has(jobId)) return; watching.add(jobId);
    VuluProgress.watchJob(jobId, (s) => {
      prog.show(s);
      if (s.status === 'running') return;
      watching.delete(jobId);
      if (s.status === 'done') { VuluModal.toast(_t("Java {major} kuruldu.", {major}), 'success'); setTimeout(() => prog.hide(), 1200); }
      else note('danger', s.error || _t('Kurulum başarısız oldu.'));
      load();
    });
  }

  async function load() {
    try {
      const j = await api('system/overview');
      renderDisk(j.disk); renderJava(j); renderCache(j.cache);
    } catch (e) { note('danger', String(e.message || e)); }
  }

  $('java-form').addEventListener('submit', async () => {
    const major = Number($('java-major').value);
    try {
      const r = await api('java/install', { major });
      if (r.installed) { VuluModal.toast(_t("Java {major} zaten kurulu.", {major}), 'success'); return; }
      watchInstall(r.job_id, major);
    } catch (e) { note('danger', String(e.message || e)); }
  });
  load();
})();
