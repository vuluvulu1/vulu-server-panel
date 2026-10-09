(function () {
  const root = document.getElementById('settings-root');
  if (!root) return;
  const id = root.dataset.instanceId, name = root.dataset.name;
  const $ = (k) => document.getElementById(k);
  const notes = $('notes');
  const note = (kind, text) => { const d = document.createElement('div'); d.className = `alert alert-${kind} py-2 small mb-2`; d.textContent = text; notes.replaceChildren(d); };
  async function post(path, data) {
    const r = await fetch(`/api/instances/${id}/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || ('Hata ' + r.status));
    return j;
  }

  const ram = $('ram_gb');
  function ramUpdate() {
    $('ram_out').textContent = ram.value;
    const total = Number(ram.dataset.total || 0);
    $('ram_warn').textContent = total && Number(ram.value) > total - 2 ? '⚠ İşletim sistemi için en az 2 GB boş bırak' : '';
  }
  ram.addEventListener('input', ramUpdate); ramUpdate();

  function toggles() {
    $('java-custom-box').classList.toggle('d-none', $('java_mode').value !== 'custom');
    const args = $('launch_type').value === 'args-file';
    $('args-box').classList.toggle('d-none', !args);
    $('jar-box').classList.toggle('d-none', args);
  }
  ['java_mode', 'launch_type'].forEach(k => $(k).addEventListener('change', toggles)); toggles();

  $('settings-form').addEventListener('submit', async () => {
    try {
      await post('settings', {
        port: $('port').value, ram_gb: ram.value, jvm_preset: $('jvm_preset').value, jvm_args: $('jvm_args').value,
        java_mode: $('java_mode').value, java_path: $('java_path').value, launch_type: $('launch_type').value,
        jar_file: $('jar_file').value, args_file: $('args_file').value,
      });
      note('success', 'Kaydedildi. Değişiklikler sunucu bir sonraki başlatılışında geçerli olur.');
    } catch (e) { note('danger', String(e.message || e)); }
  });

  $('destroy-btn').addEventListener('click', async () => {
    const typed = prompt(`Bu sunucu dünyası ve tüm dosyalarıyla KALICI olarak silinecek.\nOnaylamak için sunucu adını yaz: ${name}`);
    if (typed === null) return;
    try { await post('destroy', { confirm_name: typed }); location.href = '/'; }
    catch (e) { note('danger', String(e.message || e)); }
  });
})();
