(function () {
  const root = document.getElementById('sched-root');
  if (!root) return;
  const id = root.dataset.instanceId;
  const $ = (k) => document.getElementById(k);
  const body = $('sched-body'), notes = $('notes');
  const DAY = { 1: _t('Pzt'), 2: _t('Sal'), 3: _t('Çar'), 4: _t('Per'), 5: _t('Cum'), 6: _t('Cmt'), 7: _t('Paz') };
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const note = (kind, text) => notes.replaceChildren(el('div', `alert alert-${kind} py-2 small mb-2`, text));
  async function api(path, opts) {
    const r = await fetch(`/api/instances/${id}/schedules/${path}`, opts);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : (_t('Geçersiz değer (') + r.status + ')'));
    return j;
  }
  const post = (path, data) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  const daysText = (d) => d === '1234567' ? _t('Her gün') : d === '12345' ? _t('Hafta içi') : d === '67' ? _t('Hafta sonu') : d.split('').map(x => DAY[x]).join(', ');

  function kindUI() {
    const b = $('kind').value === 'backup';
    document.querySelectorAll('.opt-backup').forEach(x => x.classList.toggle('d-none', !b));
    document.querySelectorAll('.opt-restart').forEach(x => x.classList.toggle('d-none', b));
    $('kind-help').textContent = b ? _t('Sunucu çalışıyor olsa da alınır; panel önce dünyayı diske kaydeder. "Sakla" sayısı aşılınca en eski zamanlanmış yedekler silinir; elle aldıkların etkilenmez.')
                                   : _t('Sunucu o saatte çalışıyorsa yeniden başlatılır. Seçtiğin süre boyunca oyunculara sohbetten geri sayım duyurulur.');
  }
  $('kind').addEventListener('change', kindUI); kindUI();

  async function load() {
    try {
      const j = await api('list');
      body.replaceChildren();
      if (!j.items.length) { const tr = el('tr'), td = el('td', 'text-body-secondary', _t('Henüz zamanlama yok.')); td.colSpan = 7; tr.appendChild(td); body.appendChild(tr); }
      j.items.forEach(s => {
        const tr = el('tr');
        const what = s.kind === 'restart'
          ? _t('Yeniden başlat') + (s.warn_minutes ? _t(" ({warn_minutes} dk uyarı)", {warn_minutes: s.warn_minutes}) : '')
          : _t("Yedek: {v0} (son {keep})", {v0: s.backup_mode === 'full' ? _t('tam') : _t('dünya'), keep: s.keep});
        tr.appendChild(el('td', '', what));
        tr.appendChild(el('td', 'font-monospace', s.time_hm));
        tr.appendChild(el('td', 'small', daysText(s.days)));
        tr.appendChild(el('td', 'small text-body-secondary', s.next_run || '—'));
        tr.appendChild(el('td', 'small text-body-secondary', s.last_run ? `${s.last_run} · ${s.last_result || ''}` : '—'));
        const en = el('td', 'text-center'), cb = el('input', 'form-check-input'); cb.type = 'checkbox'; cb.checked = !!s.enabled;
        cb.addEventListener('change', async () => { try { await post('toggle', { id: s.id, enabled: cb.checked }); load(); } catch (e) { note('danger', String(e.message || e)); } });
        en.appendChild(cb); tr.appendChild(en);
        const del = el('td', 'text-end'), b = el('button', 'btn btn-sm btn-outline-danger'); b.type = 'button'; b.title = _t('Sil'); b.appendChild(el('i', 'bi bi-trash'));
        b.addEventListener('click', async () => { if (!confirm(_t('Bu zamanlama silinsin mi?'))) return; try { await post('delete', { id: s.id }); load(); } catch (e) { note('danger', String(e.message || e)); } });
        del.appendChild(b); tr.appendChild(del); body.appendChild(tr);
      });
    } catch (e) { note('danger', String(e.message || e)); }
  }

  $('sched-form').addEventListener('submit', async () => {
    const days = [...document.querySelectorAll('#days input:checked')].map(x => x.value).join('');
    try {
      await post('create', { kind: $('kind').value, time_hm: $('time_hm').value, days, warn_minutes: Number($('warn_minutes').value),
                             backup_mode: $('backup_mode').value, keep: Number($('keep').value) });
      notes.replaceChildren(); VuluModal.toast(_t('Zamanlama eklendi.'), 'success'); load();
    } catch (e) { note('danger', String(e.message || e)); }
  });
  load();
})();
