(function () {
  const root = document.getElementById('account-root');
  if (!root) return;
  const $ = (k) => document.getElementById(k);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  async function api(url, data) {
    const r = await fetch(url, data ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) } : undefined);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : (_t('Hata ') + r.status));
    return j;
  }
  let lanUrls = [];
  async function load() {
    try {
      const a = await api('/api/account');
      $('acc-user').textContent = a.username;
      const n = a.sessions.length;
      $('acc-sessions').textContent = _t("{n} açık oturum", {n}) + (n ? _t(' — son: ') + a.sessions.map(s => (s.current ? _t('bu cihaz') : (s.ip || '?'))).slice(0, 5).join(', ') : '');
      lanUrls = a.lan_urls; renderLan();
    } catch (e) { /* 401 ise session.js yönlendirir */ }
  }
  $('pw-form').addEventListener('submit', async () => {
    const cur = $('pw-cur').value, nw = $('pw-new').value;
    if (nw !== $('pw-new2').value) { VuluModal.toast(_t('Yeni parolalar aynı değil.'), 'danger'); return; }
    try { const j = await api('/api/account/password', { current: cur, new: nw }); VuluModal.toast(j.message, 'success'); $('pw-form').reset(); load(); }
    catch (e) { VuluModal.toast(String(e.message || e), 'danger'); }
  });
  $('logout-others').addEventListener('click', async () => {
    try { const j = await api('/api/account/logout-others', {}); VuluModal.toast(j.message, 'success'); load(); }
    catch (e) { VuluModal.toast(String(e.message || e), 'danger'); }
  });
  load();

  // ---------- panel ayarları ----------
  const form = $('ps-form');
  let saved = null, running = null, boot = null;
  const hostMode = () => (form.querySelector('input[name=host_mode]:checked') || {}).value;
  const cur = () => ({ host_mode: hostMode(), port: Number($('ps-port').value), contact: $('ps-contact').value.trim(),
                       allowed_hosts: $('ps-hosts').value.trim() });
  const norm = (h) => h.split(',').map(x => x.trim().toLowerCase()).filter(Boolean).join(', ');
  function netChanged() {
    if (!saved) return false;
    const c = cur();
    return c.host_mode !== saved.host_mode || c.port !== saved.port || norm(c.allowed_hosts) !== saved.allowed_hosts;
  }
  function renderLan() {
    const box = $('ps-lan'); box.replaceChildren();
    if (running && running.host_mode === 'lan' && lanUrls.length) {
      box.appendChild(el('div', 'text-body-secondary', _t('Aynı Wi-Fi\'deki cihazlardan bu adresle girebilirsin:')));
      lanUrls.forEach(u => box.appendChild(el('code', 'd-block user-select-all', u)));
    } else if (hostMode() === 'lan') {
      box.appendChild(el('div', 'text-body-secondary', _t('Panel girişle korunur, ancak bağlantı şifrelenmez (HTTP). Bu yüzden yalnızca güvendiğin ev ağında aç.')));
    }
  }
  function sync() {
    $('ps-pw-row').classList.toggle('d-none', !netChanged());
    renderLan();
  }
  async function loadSettings() {
    try {
      const j = await api('/api/panel/settings');
      saved = j.saved; running = j.running; boot = j.boot;
      form.querySelector(`input[value=${saved.host_mode}]`).checked = true;
      $('ps-port').value = saved.port; $('ps-contact').value = saved.contact; $('ps-hosts').value = saved.allowed_hosts;
      $('ps-restart-badge').classList.toggle('d-none', !j.restart_needed);
      $('ps-restart').dataset.servers = j.running_servers;
      $('ps-restart').disabled = !j.supervised;
      if (!j.supervised) $('ps-restart').title = _t("Panel 'python run.py' ile başlatılmadı");
      sync();
    } catch (e) {}
  }
  form.addEventListener('input', sync);
  form.addEventListener('submit', async () => {
    try {
      const j = await api('/api/panel/settings', { ...cur(), password: $('ps-pw').value });
      VuluModal.toast(j.message, 'success'); $('ps-pw').value = '';
      loadSettings();
    } catch (e) { VuluModal.toast(String(e.message || e), 'danger'); }
  });
  $('ps-restart').addEventListener('click', async () => {
    const n = Number($('ps-restart').dataset.servers || 0);
    let msg = _t('Panel yeniden başlatılsın mı?');
    if (n) msg += _t(`\n\nÇalışan {n} sunucu düzgünce kaydedilip durdurulacak; sonra elle başlatman gerekir.`, {n});
    if (saved && saved.host_mode === 'local' && !['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname))
      msg += _t('\n\nAğ erişimini kapattığın için bu cihazdan panele bir daha giremeyeceksin.');
    if (!confirm(msg)) return;
    try {
      const j = await api('/api/panel/restart', {});
      VuluModal.toast(j.message, 'success');
      const url = `${location.protocol}//${location.hostname}:${j.port}/settings`;
      const started = Date.now();
      const wait = async () => {
        if (String(j.port) !== (location.port || '80')) { if (Date.now() - started > 6000) location.href = url; else setTimeout(wait, 1000); return; }
        try { const r = await fetch('/api/panel/settings', { cache: 'no-store' }); if (r.ok && (await r.json()).boot !== boot) { location.reload(); return; } } catch (e) {}
        if (Date.now() - started < 180000) setTimeout(wait, 1500);
      };
      setTimeout(wait, 2500);
    } catch (e) { VuluModal.toast(String(e.message || e), 'danger'); }
  });
  loadSettings();
})();
