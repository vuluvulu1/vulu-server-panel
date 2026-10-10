(function () {
  const root = document.getElementById('files-root');
  if (!root) return;
  const id = root.dataset.instanceId;
  const $ = (k) => document.getElementById(k);
  const body = $('file-body'), crumbs = $('crumbs'), notes = $('notes');
  let cwd = root.dataset.start || '', writable = false;

  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const note = (kind, text) => { notes.replaceChildren(el('div', `alert alert-${kind} py-2 small mb-2`, text)); };
  const join = (a, b) => (a ? a + '/' : '') + b;
  const size = (n) => n < 1024 ? n + ' B' : n < 1048576 ? (n / 1024).toFixed(1) + ' KB' : (n / 1048576).toFixed(1) + ' MB';
  async function api(path, opts) {
    const r = await fetch(`/api/instances/${id}/files/${path}`, opts);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || (_t('Hata ') + r.status));
    return j;
  }
  const post = (path, data) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { note('danger', String(e.message || e)); } };

  function iconBtn(icon, title, cls, onClick, disabled) {
    const b = el('button', `btn btn-sm ${cls}`); b.type = 'button'; b.title = title; b.disabled = !!disabled;
    b.appendChild(el('i', 'bi ' + icon)); b.addEventListener('click', guard(onClick)); return b;
  }

  function renderCrumbs() {
    crumbs.replaceChildren();
    const parts = cwd ? cwd.split('/') : [];
    const add = (label, path, active) => {
      const li = el('li', 'breadcrumb-item' + (active ? ' active' : ''));
      if (active) li.textContent = label;
      else { const a = el('a', '', label); a.href = '#'; a.addEventListener('click', (e) => { e.preventDefault(); open(path); }); li.appendChild(a); }
      crumbs.appendChild(li);
    };
    add('sunucu', '', !parts.length);
    parts.forEach((p, i) => add(p, parts.slice(0, i + 1).join('/'), i === parts.length - 1));
  }

  async function open(path) {
    try {
      const j = await api('list?path=' + encodeURIComponent(path));
      cwd = j.path; writable = j.writable;
      $('ro-note').classList.toggle('d-none', writable);
      ['mkdir-btn', 'newfile-btn'].forEach(k => $(k).disabled = !writable);
      $('upload-input').disabled = !writable; $('upload-label').classList.toggle('disabled', !writable);
      renderCrumbs();
      body.replaceChildren();
      if (cwd) {
        const tr = el('tr'), td = el('td', '', ''), a = el('a', '', _t('.. (üst klasör)')); a.href = '#';
        a.addEventListener('click', (e) => { e.preventDefault(); open(cwd.split('/').slice(0, -1).join('/')); });
        td.appendChild(a); td.colSpan = 4; tr.appendChild(td); body.appendChild(tr);
      }
      if (!j.items.length) { const tr = el('tr'), td = el('td', 'text-body-secondary', _t('Klasör boş.')); td.colSpan = 4; tr.appendChild(td); body.appendChild(tr); }
      j.items.forEach(it => {
        const p = join(cwd, it.name), tr = el('tr'), name = el('td');
        name.appendChild(el('i', 'bi me-2 ' + (it.dir ? 'bi-folder-fill text-warning' : it.text ? 'bi-file-earmark-text' : 'bi-file-earmark')));
        if (it.dir || it.text) {
          const a = el('a', '', it.name); a.href = '#';
          a.addEventListener('click', (e) => { e.preventDefault(); it.dir ? open(p) : edit(p); });
          name.appendChild(a);
        } else name.appendChild(document.createTextNode(it.name));
        if (it.locked) name.appendChild(el('span', 'badge text-bg-secondary ms-2', 'panel'));
        tr.appendChild(name);
        tr.appendChild(el('td', 'text-end small text-body-secondary', it.dir ? '' : size(it.size)));
        tr.appendChild(el('td', 'small text-body-secondary', new Date(it.mtime * 1000).toLocaleString(VULU_LANG)));
        const act = el('td', 'text-end text-nowrap');
        if (!it.dir) {
          const dl = el('a', 'btn btn-sm btn-outline-secondary'); dl.title = _t('İndir');
          dl.href = `/api/instances/${id}/files/download?path=${encodeURIComponent(p)}`; dl.appendChild(el('i', 'bi bi-download'));
          act.appendChild(dl);
        }
        act.appendChild(iconBtn('bi-pencil', _t('Yeniden adlandır'), 'btn-outline-secondary ms-1', async () => {
          const n = prompt(_t('Yeni ad:'), it.name); if (!n || n === it.name) return;
          await post('rename', { path: p, name: n }); open(cwd);
        }, !writable || it.locked));
        act.appendChild(iconBtn('bi-trash', _t('Sil'), 'btn-outline-danger ms-1', async () => {
          if (!confirm(_t(`{v0} kalıcı olarak silinsin mi?\n{p}`, {v0: it.dir ? _t('Klasör (içindekilerle birlikte)') : _t('Dosya'), p}))) return;
          await post('delete', { path: p }); open(cwd);
        }, !writable || it.locked));
        tr.appendChild(act); body.appendChild(tr);
      });
    } catch (e) { note('danger', String(e.message || e)); }
  }

  // ---------- açılır pencerede metin düzenleyici ----------
  async function edit(path) {
    let j;
    try { j = await api('read?path=' + encodeURIComponent(path)); } catch (e) { note('danger', String(e.message || e)); return; }
    const ro = j.locked || !writable;
    let saved = j.content;
    const ta = el('textarea', 'form-control file-editor'); ta.spellcheck = false; ta.value = j.content; ta.readOnly = ro;
    ta.setAttribute('autocomplete', 'off'); ta.setAttribute('autocapitalize', 'off'); ta.wrap = 'off';
    const status = el('span', 'editor-status me-2', ro ? (j.locked ? _t('panel yönetir · salt okunur') : _t('sunucu çalışıyor · salt okunur')) : _t('Ctrl+S: kaydet · Esc: kapat'));
    const save = el('button', 'btn btn-sm btn-primary', _t('Kaydet')); save.type = 'button'; save.disabled = true; save.hidden = ro;
    const dirty = () => ta.value !== saved;
    const refresh = () => { save.disabled = !dirty(); m.title.textContent = (dirty() ? '● ' : '') + j.path; };
    async function doSave() {
      if (ro || !dirty()) return;
      save.disabled = true; status.textContent = _t('Kaydediliyor…');
      try { await post('write', { path: j.path, content: ta.value }); saved = ta.value; status.textContent = _t('Kaydedildi ✓ ') + new Date().toLocaleTimeString(VULU_LANG); open(cwd); }
      catch (e) { status.textContent = String(e.message || e); }
      refresh();
    }
    const m = VuluModal.open({
      title: j.path, body: ta, actions: [status, save],
      beforeClose: () => !dirty() || confirm(_t('Kaydedilmemiş değişiklikler kaybolacak. Kapatılsın mı?')),
    });
    ta.addEventListener('input', refresh);
    ta.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); doSave(); }
      else if (e.key === 'Tab' && !ro) {                       // Tab ile girinti (odaktan çıkmasın)
        e.preventDefault();
        const s0 = ta.selectionStart, s1 = ta.selectionEnd;
        ta.setRangeText('  ', s0, s1, 'end'); refresh();
      }
    });
    save.addEventListener('click', doSave);
    ta.focus(); ta.setSelectionRange(0, 0); ta.scrollTop = 0;
  }

  $('mkdir-btn').addEventListener('click', guard(async () => {
    const n = prompt(_t('Klasör adı:')); if (!n) return; await post('mkdir', { path: cwd, name: n }); open(cwd);
  }));
  $('newfile-btn').addEventListener('click', guard(async () => {
    const n = prompt(_t('Dosya adı (örn. notlar.txt):')); if (!n) return;
    await post('write', { path: join(cwd, n), content: '' }); await open(cwd); edit(join(cwd, n));
  }));
  $('upload-input').addEventListener('change', guard(async (ev) => {
    const files = [...ev.target.files]; ev.target.value = '';
    let ok = 0;
    for (const f of files) {
      note('info', _t("Yükleniyor: {name} ({v1})…", {name: f.name, v1: size(f.size)}));
      const fd = new FormData(); fd.append('file', f); fd.append('path', cwd); fd.append('overwrite', $('overwrite').checked ? 'true' : 'false');
      const r = await fetch(`/api/instances/${id}/files/upload`, { method: 'POST', body: fd });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { note('danger', `${f.name}: ${j.detail || 'Hata ' + r.status}`); open(cwd); return; }
      ok++;
    }
    note('success', _t("{ok} dosya yüklendi.", {ok})); open(cwd);
  }));

  open(cwd);
})();
