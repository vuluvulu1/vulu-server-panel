(function () {
  const root = document.getElementById('backups-root');
  if (!root) return;
  const id = root.dataset.instanceId;
  const $ = (k) => document.getElementById(k);
  const body = $('bk-body'), notes = $('notes'), prog = VuluProgress.attach('bk');
  let busy = false, status = 'stopped';
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const note = (kind, text) => notes.replaceChildren(el('div', `alert alert-${kind} py-2 small mb-2`, text));
  async function api(path, opts) {
    const r = await fetch(`/api/instances/${id}/backups/${path}`, opts);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || ('Hata ' + r.status));
    return j;
  }
  const post = (path, data) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

  function setBusy(b) {
    busy = b;
    $('create-btn').disabled = b;
    body.querySelectorAll('button').forEach(x => x.disabled = b || (x.dataset.needStopped && !(status === 'stopped' || status === 'crashed')));
  }

  function watch(jobId, doneMsg) {
    setBusy(true);
    VuluProgress.watchJob(jobId, (s) => {
      prog.show(s);
      if (s.status === 'running') return;
      setBusy(false);
      if (s.status === 'done') {
        VuluModal.changed();
        note('success', doneMsg(s.result || {}));
        setTimeout(() => prog.hide(), 1200);
      } else note('danger', s.error || 'İşlem başarısız oldu.');
      load();
    });
  }

  async function load() {
    try {
      const j = await api('list');
      status = j.status;
      if (!limitTouched) { $('limit-on').checked = j.limit > 0; if (j.limit > 0) $('limit-max').value = j.limit; limitUI(); }
      $('limit-help').dataset.count = j.items.length;
      body.replaceChildren();
      if (!j.items.length) { const tr = el('tr'), td = el('td', 'text-body-secondary', 'Henüz yedek yok.'); td.colSpan = 5; tr.appendChild(td); body.appendChild(tr); }
      const stopped = status === 'stopped' || status === 'crashed';
      j.items.forEach(b => {
        const tr = el('tr');
        tr.appendChild(el('td', 'small', b.created));
        tr.appendChild(el('td', '', b.broken ? 'bozuk' : b.mode === 'world' ? 'Dünya' : b.mode === 'full' ? 'Tam' : b.mode));
        tr.appendChild(el('td', 'small text-body-secondary', b.note.replace(/^auto:/, 'otomatik: ')));
        tr.appendChild(el('td', 'text-end small', (b.size / 1048576).toFixed(1) + ' MB'));
        const act = el('td', 'text-end text-nowrap');
        const dl = el('a', 'btn btn-sm btn-outline-secondary'); dl.title = 'İndir'; dl.appendChild(el('i', 'bi bi-download'));
        dl.href = `/api/instances/${id}/backups/download?file=${encodeURIComponent(b.file)}`; act.appendChild(dl);
        const rs = el('button', 'btn btn-sm btn-outline-primary ms-1'); rs.type = 'button'; rs.title = stopped ? 'Geri yükle' : 'Önce sunucuyu durdur';
        rs.dataset.needStopped = '1'; rs.disabled = !stopped || b.broken; rs.appendChild(el('i', 'bi bi-arrow-counterclockwise'));
        rs.addEventListener('click', async () => {
          const what = b.mode === 'world' ? 'Dünya klasörleri' : 'Sunucunun tüm dosyaları (loglar hariç)';
          if (!confirm(`${what} bu yedekteki hâliyle DEĞİŞTİRİLECEK (${b.created}).\nÖnce mevcut durumun otomatik yedeği alınır. Devam edilsin mi?`)) return;
          try { const r = await post('restore', { file: b.file }); watch(r.job_id, (x) => 'Geri yüklendi.' + (x.safety ? ` Önceki durumun yedeği: ${x.safety}` : '')); }
          catch (e) { note('danger', String(e.message || e)); }
        });
        act.appendChild(rs);
        const del = el('button', 'btn btn-sm btn-outline-danger ms-1'); del.type = 'button'; del.title = 'Sil'; del.appendChild(el('i', 'bi bi-trash'));
        del.addEventListener('click', async () => {
          if (!confirm(`Bu yedek kalıcı olarak silinsin mi?\n${b.file}`)) return;
          try { await post('delete', { file: b.file }); load(); } catch (e) { note('danger', String(e.message || e)); }
        });
        act.appendChild(del); tr.appendChild(act); body.appendChild(tr);
      });
      if (j.job_id && !busy) watch(j.job_id, () => 'İşlem tamamlandı.');
      setBusy(busy);
    } catch (e) { note('danger', String(e.message || e)); }
  }

  let limitTouched = false;
  function limitUI() { $('limit-max').closest('.input-group').classList.toggle('opacity-50', !$('limit-on').checked); }
  $('limit-on').addEventListener('change', () => { limitTouched = true; limitUI(); });
  $('limit-max').addEventListener('input', () => {        // sayı yazınca temizlemeyi de aç
    limitTouched = true;
    if ($('limit-max').value && !$('limit-on').checked) { $('limit-on').checked = true; limitUI(); }
  });
  $('limit-form').addEventListener('submit', async () => {
    const on = $('limit-on').checked, max = Math.floor(Number($('limit-max').value));
    if (on && !(max >= 1 && max <= 500)) { note('danger', 'En fazla yedek sayısı 1 ile 500 arasında bir sayı olmalı.'); $('limit-max').focus(); return; }
    const count = Number($('limit-help').dataset.count || 0);
    if (on && count > max && !confirm(`Şu an ${count} yedek var. Bir sonraki yedekten sonra en eski ${count - max + 1} tanesi silinecek. Devam edilsin mi?`)) return;
    try {
      await post('limit', { enabled: on, max });
      limitTouched = false;
      VuluModal.toast(on ? `Otomatik temizleme açık: en fazla ${max} yedek tutulacak.` : 'Otomatik temizleme kapalı: yedekler birikmeye devam edecek.', 'success');
      load();
    } catch (e) { note('danger', String(e.message || e)); }
  });

  $('create-form').addEventListener('submit', async () => {
    if (busy) return;
    try {
      const r = await post('create', { mode: $('mode').value, note: $('note').value });
      watch(r.job_id, (x) => `Yedek alındı: ${x.file} (${((x.size || 0) / 1048576).toFixed(1)} MB, ${x.files} dosya)` + (x.pruned ? ` · ${x.pruned} eski yedek silindi` : ''));
      $('note').value = '';
    } catch (e) { note('danger', String(e.message || e)); }
  });
  load();
})();
