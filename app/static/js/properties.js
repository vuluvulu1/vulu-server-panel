(function () {
  const root = document.getElementById('props-root');
  if (!root) return;
  const id = root.dataset.instanceId, notes = document.getElementById('notes');
  const note = (kind, text) => { const d = document.createElement('div'); d.className = `alert alert-${kind} py-2 small mb-2`; d.textContent = text; notes.replaceChildren(d); };
  document.getElementById('props-form').addEventListener('submit', async () => {
    const btn = document.getElementById('save-btn');
    btn.disabled = true; btn.textContent = _t('Kaydediliyor…');
    const values = {};
    document.querySelectorAll('[data-key]').forEach(el => { values[el.dataset.key] = el.dataset.type === 'bool' ? el.checked : el.value; });
    try {
      const r = await fetch(`/api/instances/${id}/properties`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ values }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || (_t('Hata ') + r.status));
      notes.replaceChildren();
      VuluModal.saved(_t('server.properties kaydedildi. Değişiklikler sunucu (yeniden) başlayınca geçerli olur.'));
    } catch (e) { note('danger', String(e.message || e)); VuluModal.toast(String(e.message || e), 'danger'); }
    finally { btn.disabled = false; btn.textContent = _t('Kaydet'); }
  });
})();
