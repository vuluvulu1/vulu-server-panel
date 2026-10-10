/* playit.gg: Ayarlar sayfasındaki kart (#playit-card) ve sunucu sayfasındaki adres şeridi (#playit-strip). */
(function () {
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  async function api(url, opts) {
    const r = await fetch(url, opts);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : (_t('Hata ') + r.status));
    return j;
  }
  const post = (url) => api(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  const toast = (t, k) => (window.VuluModal ? VuluModal.toast(t, k) : alert(t));
  function btn(text, icon, cls, onClick) {
    const b = el('button', 'btn btn-sm ' + cls); b.type = 'button';
    if (icon) b.appendChild(el('i', 'bi ' + icon + ' me-1'));
    b.appendChild(document.createTextNode(text)); b.addEventListener('click', onClick); return b;
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast(_t('Adres kopyalandı.'), 'success'); }
    catch (e) { prompt(_t('Adresi kopyala:'), text); }
  }

  // ---------------- Ayarlar kartı ----------------
  const card = document.getElementById('playit-card');
  if (card) {
    const body = document.getElementById('pg-body'), badge = document.getElementById('pg-badge'), logEl = document.getElementById('pg-log');
    const prog = window.VuluProgress ? VuluProgress.attach('pg') : null;
    let timer = null, busy = false;

    async function install() {
      busy = true; render(last);
      try {
        const j = await post('/api/playit/install');
        await new Promise((res, rej) => VuluProgress.watchJob(j.job_id, (s) => {
          if (prog) prog.show(s);
          if (s.status === 'done') { setTimeout(() => prog && prog.hide(), 800); res(); }
          else if (s.status !== 'running') rej(new Error(s.error || _t('Kurulum başarısız.')));
        }));
        await link();
      } catch (e) { toast(String(e.message || e), 'danger'); }
      finally { busy = false; load(); }
    }
    async function link() {
      try {
        const c = await post('/api/playit/link');
        if (c && c.url) window.open(c.url, '_blank', 'noopener');
      } catch (e) { toast(String(e.message || e), 'danger'); }
      load();
    }
    async function action(url, msg, ask) {
      if (ask && !confirm(ask)) return;
      try { await post(url); if (msg) toast(msg, 'success'); } catch (e) { toast(String(e.message || e), 'danger'); }
      load();
    }

    let last = null;
    function render(s) {
      if (!s) return;
      body.replaceChildren();
      const row = el('div', 'd-flex flex-wrap gap-2 align-items-center');
      if (!s.supported) {
        badge.textContent = _t('Desteklenmiyor'); badge.className = 'badge text-bg-secondary';
        body.appendChild(el('div', '', _t('playit bu işletim sisteminde ya da işlemcide çalışmıyor. Desteklenenler: 64 bit Windows ve 64 bit Linux.')));
        return;
      }
      if (s.claim && (s.claim.state === 'waiting' || s.claim.state === 'accepted')) {
        badge.textContent = _t('Bağlanıyor'); badge.className = 'badge text-bg-warning';
        body.appendChild(el('div', 'mb-2', _t('Yeni sekmede açılan playit.gg sayfasında hesabınla giriş yapıp bağlantıyı onayla. Sekme açılmadıysa şu adresi kullan:')));
        const a = el('a', 'd-inline-block mb-2 text-break', s.claim.url); a.href = s.claim.url; a.target = '_blank'; a.rel = 'noopener';
        body.appendChild(a);
        if (s.claim.error) body.appendChild(el('div', 'text-warning', s.claim.error));
        row.appendChild(btn(_t('Vazgeç'), 'bi-x-lg', 'btn-outline-secondary', () => action('/api/playit/cancel')));
        body.appendChild(row); return;
      }
      if (s.claim && s.claim.error && !s.linked) body.appendChild(el('div', 'text-danger mb-2', s.claim.error));
      if (!s.linked) {
        badge.textContent = _t('Bağlı değil'); badge.className = 'badge text-bg-secondary';
        row.appendChild(btn(s.installed ? _t('playit ile bağlan') : _t('Kur ve playit ile bağlan'), 'bi-link-45deg', 'btn-primary', () => s.installed ? link() : install()));
        row.lastChild.disabled = busy;
        row.appendChild(el('span', 'text-body-secondary', _t('Ücretsiz bir playit.gg hesabı gerekir; hesabın yoksa açılacak sayfada birkaç saniyede oluşturabilirsin.')));
        body.appendChild(row); return;
      }
      badge.textContent = s.running ? _t('Çalışıyor') : _t('Durdu');
      badge.className = 'badge ' + (s.running ? 'text-bg-success' : 'text-bg-danger');
      body.appendChild(el('div', 'mb-2', _t("Hesap bağlı (playit {version}). Sunucu sayfasındaki \"İnternete aç\" düğmesiyle bir sunucuyu açabilirsin.", {version: s.version})));
      row.appendChild(btn(_t('Yeniden başlat'), 'bi-arrow-repeat', 'btn-outline-secondary', () => action('/api/playit/restart', _t('playit yeniden başlatıldı.'))));
      if (!s.installed) row.appendChild(btn(_t('Yeniden kur'), 'bi-download', 'btn-outline-primary', install));
      row.appendChild(btn(_t('Bağlantıyı kaldır'), 'bi-x-octagon', 'btn-outline-danger', () => action('/api/playit/unlink', _t('playit bağlantısı kaldırıldı.'),
        _t('playit bağlantısı kaldırılsın mı? Program durur ve tüneller çalışmaz. (Tüneller playit.gg hesabında kalır.)'))));
      body.appendChild(row);
    }
    async function load() {
      try {
        const s = await api('/api/playit/status'); last = s; render(s);
        logEl.textContent = (s.log || []).join('\n');
        clearTimeout(timer);
        timer = setTimeout(load, s.claim && (s.claim.state === 'waiting' || s.claim.state === 'accepted') ? 2000 : 10000);
      } catch (e) { body.textContent = String(e.message || e); }
    }
    load();
  }

  // ---------------- Sunucu sayfası şeridi ----------------
  const strip = document.getElementById('playit-strip');
  if (strip) {
    const id = strip.dataset.instanceId;
    let busy = false;
    async function openTunnel(warnings) {
      if (busy) return;
      let msg = _t('Bu sunucu playit.gg üzerinden internete açılsın mı? Adresi bilen herkes bağlanabilir.');
      if (warnings.length) msg += _t('\n\nUyarı:\n- ') + warnings.join('\n- ');
      if (!confirm(msg)) return;
      busy = true; render({ loading: true });
      try { const j = await post(`/api/instances/${id}/playit/open`); toast(_t('İnternete açıldı: ') + j.tunnel.address, 'success'); }
      catch (e) { toast(String(e.message || e), 'danger'); }
      finally { busy = false; load(); }
    }
    async function closeTunnel() {
      if (!confirm(_t('Tünel silinsin mi? Sunucu internetten erişilemez olur (yerel ağda çalışmaya devam eder).'))) return;
      try { await post(`/api/instances/${id}/playit/close`); toast(_t('Tünel silindi.'), 'success'); } catch (e) { toast(String(e.message || e), 'danger'); }
      load();
    }
    function render(j) {
      strip.replaceChildren(); strip.hidden = false;
      strip.appendChild(el('i', 'bi bi-globe2'));
      if (j.loading) { strip.appendChild(el('span', 'small', _t('Tünel oluşturuluyor…'))); return; }
      if (!j.linked) {
        strip.appendChild(el('span', 'small text-body-secondary', _t('Arkadaşlarınla oynamak için port yönlendirmesi gerekmez:')));
        const a = el('a', 'small', _t('playit.gg\'yi bağla')); a.href = '/settings#playit-card'; strip.appendChild(a);
        return;
      }
      if (j.tunnel) {
        strip.appendChild(el('span', 'small text-body-secondary', _t('Herkese açık adres:')));
        strip.appendChild(el('span', 'playit-addr', j.tunnel.address));
        strip.appendChild(btn(_t('Kopyala'), 'bi-clipboard', 'btn-outline-primary', () => copy(j.tunnel.address)));
        if (j.tunnel.disabled) strip.appendChild(el('span', 'badge text-bg-warning', _t('tünel kapalı')));
        if (!j.running) strip.appendChild(el('span', 'badge text-bg-danger', _t('playit çalışmıyor')));
        if (j.tunnel.alt && j.tunnel.alt !== j.tunnel.address) strip.appendChild(el('span', 'small text-body-secondary', _t('alternatif: ') + j.tunnel.alt));
        const sp = el('span', 'ms-auto'); strip.appendChild(sp);
        strip.appendChild(btn(_t('Kapat'), 'bi-x-lg', 'btn-outline-secondary', closeTunnel));
        return;
      }
      if (j.error) strip.appendChild(el('span', 'small text-warning', j.error));
      else strip.appendChild(el('span', 'small text-body-secondary', _t('Bu sunucu internete açık değil.')));
      strip.appendChild(btn(_t('İnternete aç'), 'bi-broadcast', 'btn-primary', () => openTunnel(j.warnings || [])));
    }
    async function load() {
      try { render(await api(`/api/instances/${id}/playit`)); } catch (e) { strip.hidden = true; }
    }
    load();
    setInterval(() => { if (!busy && document.visibilityState === 'visible') load(); }, 30000);
  }
})();
