(function () {
  const card = document.getElementById('update-card');
  if (!card) return;
  const $ = (k) => document.getElementById(k);
  const status = $('up-status'), notes = $('up-notes'), install = $('up-install'), check = $('up-check'), auto = $('up-auto');
  async function api(url, data) {
    const r = await fetch(url, data ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) } : { cache: 'no-store' });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : (_t('Hata ') + r.status));
    return j;
  }
  const ago = (t) => {
    if (!t) return '';
    const m = Math.round((Date.now() / 1000 - t) / 60);
    return m < 1 ? _t('az önce') : m < 60 ? _t('{n} dk önce', { n: m }) : _t('{n} sa önce', { n: Math.round(m / 60) });
  };
  let state = null;

  function render(s) {
    state = s;
    auto.checked = !!s.auto;
    install.classList.toggle('d-none', !s.available || s.git);
    install.querySelector('span').textContent = _t('v{v} sürümüne güncelle', { v: s.latest });
    install.disabled = !!s.installing || !s.supervised;
    let text;
    if (s.installing) text = s.message || _t('Güncelleniyor…');
    else if (s.available) {
      text = _t('Yeni sürüm var: v{v}', { v: s.latest });
      if (s.git) text += ' ' + _t("Panel git ile kurulmuş; güncellemek için klasörde 'git pull' çalıştırıp paneli yeniden başlat.");
      else if (!s.supervised) text += ' ' + _t("Panel 'python run.py' (ya da baslat) ile başlatılmadığı için kendini güncelleyemiyor.");
    } else if (s.error) text = s.error;
    else if (s.latest) text = _t('Panel güncel.');
    else text = _t('Henüz denetlenmedi.');
    if (s.checked_at && !s.installing) text += ' · ' + _t('Son denetim: {t}', { t: ago(s.checked_at) });
    if (s.phase === 'error' && s.message && !s.installing) text = s.message;
    status.textContent = text;
    status.className = 'mb-2 ' + (s.available ? 'text-warning-emphasis fw-semibold' : (s.error || s.phase === 'error') ? 'text-danger' : 'text-body-secondary');
    notes.classList.toggle('d-none', !(s.available && s.notes));
    notes.textContent = s.available ? s.notes : '';
  }

  async function load(first) {
    try {
      let s = await api('/api/panel/update');
      if (first && !s.checked_at) s = await api('/api/panel/update/check', {});   // sayfa ilk açıldığında hiç denetlenmemişse
      render(s);
    } catch (e) { status.textContent = String(e.message || e); }
  }

  check.addEventListener('click', async () => {
    check.disabled = true;
    try { render(await api('/api/panel/update/check', {})); }
    catch (e) { VuluModal.toast(String(e.message || e), 'danger'); }
    finally { check.disabled = false; }
  });

  auto.addEventListener('change', async () => {
    try { await api('/api/panel/update/auto', { enabled: auto.checked }); }
    catch (e) { auto.checked = !auto.checked; VuluModal.toast(String(e.message || e), 'danger'); }
  });

  install.addEventListener('click', async () => {
    let msg = _t('vulu panel v{v} kurulsun mu? Panel kısa bir süre yeniden başlayacak.', { v: state.latest });
    const n = state.running_servers || 0;
    if (n) msg += _t('\n\nÇalışan {n} sunucu düzgünce kaydedilip durdurulacak; sonra elle başlatman gerekir.', { n });
    if (!confirm(msg)) return;
    install.disabled = check.disabled = true;
    const poll = setInterval(async () => { try { const s = await api('/api/panel/update'); if (s.installing) render(s); } catch (e) {} }, 700);
    try {
      const j = await api('/api/panel/update/install', {});
      clearInterval(poll);
      status.textContent = j.message;
      const started = Date.now();
      const wait = async () => {               // yeni sürüm ayağa kalkınca sayfa yenilenir
        try { const r = await fetch('/api/panel/settings', { cache: 'no-store' }); if (r.ok && (await r.json()).boot !== j.boot) { location.reload(); return; } } catch (e) {}
        if (Date.now() - started < 300000) setTimeout(wait, 1500);
      };
      setTimeout(wait, 3000);
    } catch (e) {
      clearInterval(poll);
      VuluModal.toast(String(e.message || e), 'danger');
      install.disabled = check.disabled = false;
      load(false);
    }
  });

  load(true);
})();
