(function () {
  const root = document.getElementById('mods-root');
  if (!root) return;
  const id = root.dataset.instanceId, noun = root.dataset.noun;
  const $ = (k) => document.getElementById(k);
  const prog = VuluProgress.attach('mod');
  const notes = $('mod-notes'), body = $('installed-body'), results = $('results'), more = $('more-btn');
  let offset = 0, total = 0, query = '', busy = false;

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  function note(kind, text) {
    const d = el('div', `alert alert-${kind} py-2 small mb-2`, text);
    notes.replaceChildren(d);
  }
  async function api(path, opts) {
    const r = await fetch(`/api/instances/${id}/mods/${path}`, opts);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || ('Hata ' + r.status));
    return j;
  }
  const post = (path, data) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

  // ---------- kurulu liste ----------
  async function loadInstalled() {
    try {
      const j = await api('installed');
      body.replaceChildren();
      if (!j.items.length) body.appendChild(el('tr')).appendChild(el('td', 'text-body-secondary', `Henüz ${noun.toLowerCase()} yok (klasör: ${j.dir}/).`)).colSpan = 5;
      const stopped = j.status === 'stopped' || j.status === 'crashed';
      j.items.forEach(it => {
        const tr = el('tr');
        tr.appendChild(el('td', it.enabled ? '' : 'text-body-secondary text-decoration-line-through', it.title));
        tr.appendChild(el('td', 'small text-body-secondary', it.version));
        const src = el('td'); src.appendChild(el('span', 'badge text-bg-secondary', it.source)); tr.appendChild(src);
        const en = el('td', 'text-center'), cb = el('input', 'form-check-input'); cb.type = 'checkbox'; cb.checked = it.enabled; cb.disabled = !stopped;
        cb.addEventListener('change', () => act('toggle', { filename: it.file, enabled: cb.checked }));
        en.appendChild(cb); tr.appendChild(en);
        const del = el('td', 'text-end'), b = el('button', 'btn btn-sm btn-outline-danger'); b.type = 'button'; b.disabled = !stopped;
        b.appendChild(el('i', 'bi bi-trash'));
        b.addEventListener('click', () => { if (confirm(`${it.title} silinsin mi? Başka modların bağımlılığı olabilir.`)) act('remove', { filename: it.file }); });
        del.appendChild(b); tr.appendChild(del); body.appendChild(tr);
      });
      if (!stopped) note('warning', 'Sunucu çalışıyor: mod ekleme, silme ve açıp kapatma için önce sunucuyu durdur.');
    } catch (e) { note('danger', String(e.message || e)); }
  }
  async function act(kind, data) {
    try { await post(kind, data); note('success', 'Yapıldı. Değişikliğin etkin olması için sunucuyu (yeniden) başlat.'); }
    catch (e) { note('danger', String(e.message || e)); }
    loadInstalled();
  }

  // ---------- arama ----------
  function card(h) {
    const col = el('div', 'col-md-6 col-xl-4'), c = el('div', 'card static h-100'), b = el('div', 'card-body d-flex gap-3');
    if (h.icon) { const im = el('img', 'mod-icon'); im.width = 48; im.height = 48; im.style.cssText = 'width:48px;height:48px;flex:none;object-fit:cover'; im.src = h.icon; im.alt = ''; im.referrerPolicy = 'no-referrer'; im.loading = 'lazy'; b.appendChild(im); }
    else { const ph = el('div', 'mod-icon'); ph.style.cssText = 'width:48px;height:48px;flex:none'; b.appendChild(ph); }
    const mid = el('div', 'flex-grow-1'); mid.style.minWidth = '0';
    mid.appendChild(el('h3', 'h6 mb-1', h.title));
    mid.appendChild(el('p', 'small text-body-secondary mb-1 mod-desc', h.description));
    mid.appendChild(el('div', 'small text-body-secondary', `${h.author} · ${h.downloads.toLocaleString('tr-TR')} indirme`));
    b.appendChild(mid);
    const btn = el('button', 'btn btn-sm align-self-start flex-shrink-0 ' + (h.installed ? 'btn-outline-secondary' : 'btn-primary'), h.installed ? 'Kurulu ✓' : 'Kur');
    btn.type = 'button'; btn.disabled = h.installed; btn.dataset.slug = h.slug;
    btn.addEventListener('click', () => install(h, btn));
    b.appendChild(btn); c.appendChild(b); col.appendChild(c);
    return col;
  }
  async function search(reset) {
    if (reset) { offset = 0; results.replaceChildren(); query = $('search-q').value.trim(); }
    more.classList.add('d-none');
    try {
      const j = await api(`search?q=${encodeURIComponent(query)}&offset=${offset}`);
      total = j.total; offset += j.hits.length;
      j.hits.forEach(h => results.appendChild(card(h)));
      if (!results.children.length) results.appendChild(el('p', 'text-body-secondary', 'Sonuç yok.'));
      if (offset < total && j.hits.length) more.classList.remove('d-none');
    } catch (e) { note('danger', String(e.message || e)); }
  }

  // ---------- kurulum ----------
  async function install(h, btn) {
    if (busy) return;
    busy = true; document.querySelectorAll('#results button').forEach(x => x.disabled = true);
    notes.replaceChildren();
    const finish = (s) => {
      busy = false;
      document.querySelectorAll('#results button').forEach(x => { if (!x.textContent.startsWith('Kurulu')) x.disabled = false; });
      if (s.status === 'done') {
        btn.textContent = 'Kurulu ✓'; btn.className = 'btn btn-sm align-self-start flex-shrink-0 btn-outline-secondary'; btn.disabled = true;
        const w = (s.result && s.result.warnings) || [];
        note(w.length ? 'warning' : 'success', `${h.title} kuruldu (${s.result ? s.result.count : 1} dosya). Etkin olması için sunucuyu (yeniden) başlat.` + (w.length ? ' Uyarılar: ' + w.join(' ') : ''));
        setTimeout(() => prog.hide(), 1200);
      } else note('danger', s.error || 'Kurulum başarısız oldu.');
      loadInstalled();
    };
    try {
      const j = await post('add', { slug: h.slug });
      VuluProgress.watchJob(j.job_id, (s) => { prog.show(s); if (s.status !== 'running') finish(s); });
    } catch (e) { busy = false; document.querySelectorAll('#results button').forEach(x => { if (!x.textContent.startsWith('Kurulu')) x.disabled = false; }); note('danger', String(e.message || e)); }
  }

  $('search-form').addEventListener('submit', () => search(true));
  more.addEventListener('click', () => search(false));
  loadInstalled();
  search(true);
})();
