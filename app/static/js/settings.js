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
    if (!r.ok) throw new Error(j.detail || (_t('Hata ') + r.status));
    return j;
  }

  const ram = $('ram_gb');
  function ramUpdate() {
    $('ram_out').textContent = ram.value;
    const total = Number(ram.dataset.total || 0);
    $('ram_warn').textContent = total && Number(ram.value) > total - 2 ? _t('⚠ Bilgisayarın kendisi için en az 2 GB boş bırakmalısın.') : '';
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
    const btn = $('save-btn');
    btn.disabled = true; btn.textContent = _t('Kaydediliyor…');
    try {
      await post('settings', {
        port: $('port').value, ram_gb: ram.value, jvm_preset: $('jvm_preset').value, jvm_args: $('jvm_args').value,
        java_mode: $('java_mode').value, java_path: $('java_path').value, launch_type: $('launch_type').value,
        jar_file: $('jar_file').value, args_file: $('args_file').value,
      });
      notes.replaceChildren();
      VuluModal.saved(_t('Ayarlar kaydedildi. Değişiklikler sunucu bir sonraki başlatılışında geçerli olur.'), true);
    } catch (e) { note('danger', String(e.message || e)); VuluModal.toast(String(e.message || e), 'danger'); }
    finally { btn.disabled = false; btn.textContent = _t('Kaydet'); }
  });

  $('destroy-btn').addEventListener('click', async () => {
    const typed = prompt(_t(`Bu sunucu dünyası ve tüm dosyalarıyla KALICI olarak silinecek.\nOnaylamak için sunucu adını yaz: {name}`, {name}));
    if (typed === null) return;
    try { await post('destroy', { confirm_name: typed }); VuluModal.navigateTop('/'); }
    catch (e) { note('danger', String(e.message || e)); }
  });

  // ---------- sunucu simgesi ----------
  const iconIn = $('icon-input'), prev = $('icon-preview'), iconSave = $('icon-save'), cur = $('icon-current');
  let iconData = null;
  function refreshIcon() {
    const img = cur.querySelector('img:not(.server-icon-default)') || document.createElement('img');
    img.width = img.height = 64; img.alt = '';
    img.onload = () => cur.classList.add('has-img');
    img.onerror = () => { cur.classList.remove('has-img'); img.remove(); };
    img.src = `/api/instances/${id}/icon?v=${Date.now()}`;
    if (!img.parentNode) cur.appendChild(img);
  }
  iconIn.addEventListener('change', () => {
    const f = iconIn.files[0]; iconIn.value = '';
    if (!f) return;
    if (f.size > 20 * 1048576) { note('danger', _t('Resim çok büyük (en fazla 20 MB).')); return; }
    const url = URL.createObjectURL(f), im = new Image();
    im.onload = () => {
      const s = Math.min(im.naturalWidth, im.naturalHeight);
      const ctx = prev.getContext('2d');
      ctx.clearRect(0, 0, 64, 64); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(im, (im.naturalWidth - s) / 2, (im.naturalHeight - s) / 2, s, s, 0, 0, 64, 64);   // ortadan kare kırp
      URL.revokeObjectURL(url);
      iconData = prev.toDataURL('image/png');
      prev.classList.remove('d-none'); iconSave.classList.remove('d-none');
    };
    im.onerror = () => { URL.revokeObjectURL(url); note('danger', _t('Bu dosya resim olarak açılamadı.')); };
    im.src = url;
  });
  iconSave.addEventListener('click', async () => {
    if (!iconData) return;
    iconSave.disabled = true;
    try {
      await post('icon', { data: iconData.split(',')[1] });
      iconData = null; prev.classList.add('d-none'); iconSave.classList.add('d-none');
      refreshIcon(); VuluModal.changed(); VuluModal.toast(_t('Sunucu simgesi güncellendi. Oyunda görünmesi için sunucuyu yeniden başlat.'), 'success');
    } catch (e) { note('danger', String(e.message || e)); }
    iconSave.disabled = false;
  });
  $('icon-remove').addEventListener('click', async () => {
    if (!confirm(_t('Sunucu simgesi kaldırılsın mı?'))) return;
    try { await post('icon/delete', {}); refreshIcon(); VuluModal.changed(); VuluModal.toast(_t('Sunucu simgesi kaldırıldı.'), 'success'); }
    catch (e) { note('danger', String(e.message || e)); }
  });

  // ---------- Minecraft sürümünü değiştir ----------
  const upCard = $('upgrade-card'), upSel = $('up-version'), upBtn = $('up-btn');
  if (upSel) {
    const cur = upCard.dataset.current, loader = upCard.dataset.loader;
    (async () => {
      try {
        const r = await fetch('/api/minecraft/versions?loader=' + encodeURIComponent(loader));
        const j = await r.json(); if (!r.ok) throw new Error(j.detail || _t('Hata'));
        upSel.replaceChildren(new Option(_t('— Yeni sürüm seç —'), ''));
        j.versions.forEach(v => { if (v.id !== cur) upSel.appendChild(new Option(v.id + (v.id === j.latest ? _t('  (en yeni)') : ''), v.id)); });
      } catch (e) { upSel.replaceChildren(new Option(_t('Sürüm listesi alınamadı'), '')); }
    })();
    const upProg = VuluProgress.attach('up');
    upBtn.addEventListener('click', async () => {
      const v = upSel.value; if (!v) { note('warning', _t('Önce yeni bir sürüm seç.')); return; }
      let plan;
      try { plan = await post('upgrade/check', { mc_version: v }); } catch (e) { note('danger', String(e.message || e)); return; }
      const lines = [`Minecraft ${plan.old || '?'} → ${plan.new}`, '', _t('Yapılacaklar:'), _t('• Önce tam yedek alınacak'),
        plan.custom_java ? _t('• Java: özel yol kullanılıyor (değişmeyecek; uyumlu olduğundan emin ol)') : _t("• Java {java_major} kullanılacak", {java_major: plan.java_major}),
        _t('• Sunucu dosyası yeni sürüme göre ilk başlatmada indirilecek')];
      if (plan.managed_mods) lines.push(_t("• Modrinth'ten kurulan {managed_mods} mod yeni sürüme göre güncellenecek (sürümü olmayanlar kaldırılır)", {managed_mods: plan.managed_mods}));
      if (plan.manual_count) lines.push(_t("• DİKKAT: elle eklenmiş {manual_count} mod dosyası değişmeyecek, uyumlu olmayabilir", {manual_count: plan.manual_count}));
      if (plan.downgrade) lines.push('', _t('⚠ DAHA ESKİ bir sürüme geçiyorsun. Minecraft dünyaları eski sürüme düşürülmeyi desteklemez; dünya bozulabilir. Yedekten geri dönebilirsin.'));
      lines.push('', _t('Devam edilsin mi?'));
      if (!confirm(lines.join('\n'))) return;
      upBtn.disabled = true;
      try {
        const r = await post('upgrade/start', { mc_version: v, confirm_downgrade: !!plan.downgrade });
        VuluProgress.watchJob(r.job_id, (s) => {
          upProg.show(s);
          if (s.status === 'running') return;
          upBtn.disabled = false;
          if (s.status === 'done') {
            const w = (s.result && s.result.mod_warnings) || [];
            VuluModal.changed();
            VuluModal.toast(_t("Sürüm {v} olarak değiştirildi. Sunucuyu başlatınca yeni dosyalar indirilecek.", {v}) + (w.length ? _t(" ({length} mod uyarısı)", {length: w.length}) : ''), 'success');
            if (w.length) note('warning', _t('Mod uyarıları: ') + w.join(' · '));
            else setTimeout(() => location.reload(), 1500);
          } else note('danger', s.error || _t('Sürüm değiştirilemedi.'));
        });
      } catch (e) { upBtn.disabled = false; note('danger', String(e.message || e)); }
    });
  }
})();
