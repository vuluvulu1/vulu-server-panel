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
    if (!r.ok) throw new Error(j.detail || (_t('Hata ') + r.status));
    return j;
  }
  const post = (path, data) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

  // ---------- kurulu liste ----------
  async function loadInstalled() {
    try {
      const j = await api('installed');
      body.replaceChildren();
      if (!j.items.length) body.appendChild(el('tr')).appendChild(el('td', 'text-body-secondary', _t("Henüz {v0} yok (klasör: {dir}/).", {v0: noun.toLowerCase(), dir: j.dir}))).colSpan = 5;
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
        b.addEventListener('click', () => { if (confirm(_t("{title} silinsin mi? Başka modların bağımlılığı olabilir.", {title: it.title}))) act('remove', { filename: it.file }); });
        del.appendChild(b); tr.appendChild(del); body.appendChild(tr);
      });
      if (!stopped) note('warning', _t('Sunucu çalışırken modlar değiştirilemez. Mod eklemek, silmek ya da açıp kapatmak için önce sunucuyu durdur.'));
    } catch (e) { note('danger', String(e.message || e)); }
  }
  // ---------- bağımlılık denetimi ----------
  const checkBox = $('mod-check');
  async function loadCheck() {
    if (!checkBox) return;
    try {
      const r = await api('check');
      checkBox.replaceChildren();
      if (r.missing.length) {
        const a = el('div', 'alert alert-danger py-2 small mb-2');
        a.appendChild(el('strong', '', _t("{length} zorunlu bağımlılık eksik — sunucu açılmayabilir.", {length: r.missing.length})));
        a.appendChild(el('div', 'mb-1', _t('Bir ada tıklayınca Modrinth\'te aranır. Sonuç çıkmazsa mod büyük olasılıkla yalnızca CurseForge\'dadır; jar dosyasını oradan indirip Dosyalar sekmesinden mods/ klasörüne yükleyebilirsin.')));
        const ul = el('ul', 'mb-0 ps-3');
        r.missing.slice(0, 50).forEach(m => {
          const li = el('li');
          const b = el('button', 'btn btn-link btn-sm p-0 align-baseline', m.id); b.type = 'button';
          b.addEventListener('click', () => { $('search-q').value = m.id; search(true); $('search-q').scrollIntoView({ behavior: 'smooth', block: 'center' }); });
          li.append(b, el('span', 'text-body-secondary', _t(' — isteyen: ') + m.required_by.slice(0, 3).join(', ')));
          ul.appendChild(li);
        });
        a.appendChild(ul); checkBox.appendChild(a);
      }
      if (r.client_only.length) {
        const w = el('div', 'alert alert-warning py-2 small mb-2');
        w.appendChild(el('strong', '', _t('İstemciye özel modlar: ')));
        w.appendChild(document.createTextNode(r.client_only.map(c => c.name).join(', ') + _t('. Sunucuda gerekmez ve çökmeye yol açabilir; yukarıdaki listeden kapatabilirsin.')));
        checkBox.appendChild(w);
      }
    } catch (e) { /* denetim isteğe bağlı: hata sessizce geçilir */ }
  }

  async function act(kind, data) {
    try { await post(kind, data); note('success', _t('Tamam. Değişikliğin geçerli olması için sunucuyu başlat ya da yeniden başlat.')); VuluModal.changed(); }
    catch (e) { note('danger', String(e.message || e)); }
    loadInstalled(); loadCheck();
  }

  // ---------- arama ----------
  function card(h) {
    const col = el('div', 'col-md-6 col-xl-4'), c = el('div', 'card static h-100'), b = el('div', 'card-body d-flex gap-3');
    if (h.icon) { const im = el('img', 'mod-icon'); im.width = 48; im.height = 48; im.style.cssText = 'width:48px;height:48px;flex:none;object-fit:cover'; im.src = h.icon; im.alt = ''; im.referrerPolicy = 'no-referrer'; im.loading = 'lazy'; b.appendChild(im); }
    else { const ph = el('div', 'mod-icon'); ph.style.cssText = 'width:48px;height:48px;flex:none'; b.appendChild(ph); }
    const mid = el('div', 'flex-grow-1'); mid.style.minWidth = '0';
    mid.appendChild(el('h3', 'h6 mb-1', h.title));
    mid.appendChild(el('p', 'small text-body-secondary mb-1 mod-desc', h.description));
    mid.appendChild(el('div', 'small text-body-secondary', _t('{author} · {n} indirme', {author: h.author, n: h.downloads.toLocaleString(VULU_LANG)})));
    b.appendChild(mid);
    const btn = el('button', 'btn btn-sm align-self-start flex-shrink-0 ' + (h.installed ? 'btn-outline-secondary' : 'btn-primary'), h.installed ? _t('Kurulu ✓') : _t('Kur'));
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
      if (!results.children.length) results.appendChild(el('p', 'text-body-secondary', _t('Sonuç yok.')));
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
      document.querySelectorAll('#results button').forEach(x => { if (!x.textContent.startsWith(_t('Kurulu'))) x.disabled = false; });
      if (s.status === 'done') {
        VuluModal.changed();
        btn.textContent = _t('Kurulu ✓'); btn.className = 'btn btn-sm align-self-start flex-shrink-0 btn-outline-secondary'; btn.disabled = true;
        const w = (s.result && s.result.warnings) || [];
        note(w.length ? 'warning' : 'success', _t("{title} kuruldu ({v1} dosya). Etkin olması için sunucuyu (yeniden) başlat.", {title: h.title, v1: s.result ? s.result.count : 1}) + (w.length ? _t(' Uyarılar: ') + w.join(' ') : ''));
        setTimeout(() => prog.hide(), 1200);
      } else note('danger', s.error || _t('Kurulum başarısız oldu.'));
      loadInstalled(); loadCheck();
    };
    try {
      const j = await post('add', { slug: h.slug });
      VuluProgress.watchJob(j.job_id, (s) => { prog.show(s); if (s.status !== 'running') finish(s); });
    } catch (e) { busy = false; document.querySelectorAll('#results button').forEach(x => { if (!x.textContent.startsWith(_t('Kurulu'))) x.disabled = false; }); note('danger', String(e.message || e)); }
  }

  // ---------- güncellemeler ----------
  const updBox = $('upd-box'), updBtn = $('upd-check');
  async function checkUpdates() {
    if (busy) return;
    updBtn.disabled = true; updBox.replaceChildren(el('div', 'small text-body-secondary mb-2', _t('Denetleniyor… Mod dosyaları Modrinth\'teki sürümlerle karşılaştırılıyor.')));
    try {
      const r = await post('updates/check', {});
      updBox.replaceChildren();
      const info = _t('{n} dosya denetlendi', {n: r.checked}) + (r.unknown ? _t(", {n} tanesi Modrinth'te yok (elle/CurseForge)", {n: r.unknown}) : '') + '.';
      if (!r.items.length) { updBox.appendChild(el('div', 'alert alert-success py-2 small mb-3', _t('Hepsi güncel. ') + info)); return; }
      const card = el('div', 'card static mb-3'), cb = el('div', 'card-body');
      cb.appendChild(el('div', 'small mb-2', _t("{length} güncelleme var. {info}", {length: r.items.length, info})));
      const list = el('div', 'mb-2');
      r.items.forEach(it => {
        const lab = el('label', 'form-check d-flex align-items-center gap-2 mb-1');
        const c = el('input', 'form-check-input m-0'); c.type = 'checkbox'; c.value = it.file; c.checked = it.new_type === 'release';
        lab.append(c, el('span', '', it.title), el('span', 'small text-body-secondary', `${it.current} → ${it.new}`));
        if (it.new_type !== 'release') lab.appendChild(el('span', 'badge text-bg-warning', it.new_type));
        list.appendChild(lab);
      });
      const go = el('button', 'btn btn-sm btn-primary', _t('Seçilenleri güncelle')); go.type = 'button';
      go.addEventListener('click', () => applyUpdates([...list.querySelectorAll('input:checked')].map(x => x.value), go));
      cb.append(list, go, el('div', 'form-text', _t('Eski dosyalar silinmez, sunucu klasöründeki .vulu-old-mods/ içine taşınır; bir sorun olursa geri koyabilirsin. Beta ve alfa sürümler kararsız olabileceği için varsayılan olarak seçili gelmez.')));
      card.appendChild(cb); updBox.appendChild(card);
    } catch (e) { updBox.replaceChildren(el('div', 'alert alert-danger py-2 small mb-3', String(e.message || e))); }
    finally { updBtn.disabled = false; }
  }
  async function applyUpdates(files, btn) {
    if (!files.length || busy) return;
    busy = true; btn.disabled = true; updBtn.disabled = true;
    try {
      const j = await post('updates/apply', { files });
      VuluProgress.watchJob(j.job_id, (s) => {
        prog.show(s);
        if (s.status === 'running') return;
        busy = false; updBtn.disabled = false;
        if (s.status === 'done') { note('success', (s.result && s.result.message) || _t('Güncellendi.')); VuluModal.changed(); setTimeout(() => prog.hide(), 1200); updBox.replaceChildren(); }
        else { note('danger', s.error || _t('Güncelleme başarısız oldu.')); btn.disabled = false; }
        loadInstalled(); loadCheck();
      });
    } catch (e) { busy = false; btn.disabled = false; updBtn.disabled = false; note('danger', String(e.message || e)); }
  }
  updBtn.addEventListener('click', checkUpdates);

  $('search-form').addEventListener('submit', () => search(true));
  more.addEventListener('click', () => search(false));
  loadInstalled(); loadCheck();
  search(true);
})();
