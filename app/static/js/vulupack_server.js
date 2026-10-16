(function () {
  const row = document.getElementById('vulupack-row'), btn = document.getElementById('vulupack-update-btn');
  if (!row || !btn) return;
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      const r = await fetch(`/api/instances/${row.dataset.instanceId}/vulupack/update`, { method: 'POST' });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : (_t('Hata ') + r.status));
      if (j.updated) { VuluModal.saved(j.message, true); }
      else VuluModal.toast(j.message, 'success');
    } catch (e) { VuluModal.toast(String(e.message || e), 'danger'); }
    finally { btn.disabled = false; }
  });
})();
