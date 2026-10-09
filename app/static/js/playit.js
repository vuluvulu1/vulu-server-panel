/* playit.gg: Ayarlar sayfasındaki kart (#playit-card) ve sunucu sayfasındaki adres şeridi (#playit-strip). */
(function () {
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  async function api(url, opts) {
    const r = await fetch(url, opts);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : ('Hata ' + r.status));
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
    try { await navigator.clipboard.writeText(text); toast('Adres kopyalandı.', 'success'); }
    catch (e) { prompt('Adresi kopyala:', text); }
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
          else if (s.status !== 'running') rej(new Error(s.error || 'Kurulum başarısız.'));
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
        badge.textContent = 'Desteklenmiyor'; badge.className = 'badge text-bg-secondary';
        body.appendChild(el('div', '', 'Bu işletim sistemi/işlemci için playit desteklenmiyor (Windows x64 ve Linux x64).'));
        return;
      }
      if (s.claim && (s.claim.state === 'waiting' || s.claim.state === 'accepted')) {
        badge.textContent = 'Bağlanıyor'; badge.className = 'badge text-bg-warning';
        body.appendChild(el('div', 'mb-2', 'Açılan playit.gg sayfasında hesabınla giriş yapıp programı onayla. Sayfa açılmadıysa bağlantıyı kullan:'));
        const a = el('a', 'd-inline-block mb-2 text-break', s.claim.url); a.href = s.claim.url; a.target = '_blank'; a.rel = 'noopener';
        body.appendChild(a);
        if (s.claim.error) body.appendChild(el('div', 'text-warning', s.claim.error));
        row.appendChild(btn('Vazgeç', 'bi-x-lg', 'btn-outline-secondary', () => action('/api/playit/cancel')));
        body.appendChild(row); return;
      }
      if (s.claim && s.claim.error && !s.linked) body.appendChild(el('div', 'text-danger mb-2', s.claim.error));
      if (!s.linked) {
        badge.textContent = 'Bağlı değil'; badge.className = 'badge text-bg-secondary';
        row.appendChild(btn(s.installed ? 'playit ile bağlan' : 'Kur ve playit ile bağlan', 'bi-link-45deg', 'btn-primary', () => s.installed ? link() : install()));
        row.lastChild.disabled = busy;
        row.appendChild(el('span', 'text-body-secondary', 'Ücretsiz bir playit.gg hesabı gerekir; bağlantı penceresinde oluşturabilirsin.'));
        body.appendChild(row); return;
      }
      badge.textContent = s.running ? 'Çalışıyor' : 'Durdu';
      badge.className = 'badge ' + (s.running ? 'text-bg-success' : 'text-bg-danger');
      body.appendChild(el('div', 'mb-2', `Hesap bağlı (playit ${s.version}). Sunucu sayfasındaki "İnternete aç" düğmesiyle bir sunucuyu açabilirsin.`));
      row.appendChild(btn('Yeniden başlat', 'bi-arrow-repeat', 'btn-outline-secondary', () => action('/api/playit/restart', 'playit yeniden başlatıldı.')));
      if (!s.installed) row.appendChild(btn('Yeniden kur', 'bi-download', 'btn-outline-primary', install));
      row.appendChild(btn('Bağlantıyı kaldır', 'bi-x-octagon', 'btn-outline-danger', () => action('/api/playit/unlink', 'playit bağlantısı kaldırıldı.',
        'playit bağlantısı kaldırılsın mı? Program durur ve tüneller çalışmaz. (Tüneller playit.gg hesabında kalır.)')));
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
      let msg = 'Bu sunucu playit.gg üzerinden internete açılsın mı? Adresi bilen herkes bağlanabilir.';
      if (warnings.length) msg += '\n\nUyarı:\n- ' + warnings.join('\n- ');
      if (!confirm(msg)) return;
      busy = true; render({ loading: true });
      try { const j = await post(`/api/instances/${id}/playit/open`); toast('İnternete açıldı: ' + j.tunnel.address, 'success'); }
      catch (e) { toast(String(e.message || e), 'danger'); }
      finally { busy = false; load(); }
    }
    async function closeTunnel() {
      if (!confirm('Tünel silinsin mi? Sunucu internetten erişilemez olur (yerel ağda çalışmaya devam eder).')) return;
      try { await post(`/api/instances/${id}/playit/close`); toast('Tünel silindi.', 'success'); } catch (e) { toast(String(e.message || e), 'danger'); }
      load();
    }
    function render(j) {
      strip.replaceChildren(); strip.hidden = false;
      strip.appendChild(el('i', 'bi bi-globe2'));
      if (j.loading) { strip.appendChild(el('span', 'small', 'Tünel oluşturuluyor…')); return; }
      if (!j.linked) {
        strip.appendChild(el('span', 'small text-body-secondary', 'Arkadaşlarınla oynamak için port yönlendirmesi gerekmez:'));
        const a = el('a', 'small', 'playit.gg\'yi bağla'); a.href = '/settings#playit-card'; strip.appendChild(a);
        return;
      }
      if (j.tunnel) {
        strip.appendChild(el('span', 'small text-body-secondary', 'Herkese açık adres:'));
        strip.appendChild(el('span', 'playit-addr', j.tunnel.address));
        strip.appendChild(btn('Kopyala', 'bi-clipboard', 'btn-outline-primary', () => copy(j.tunnel.address)));
        if (j.tunnel.disabled) strip.appendChild(el('span', 'badge text-bg-warning', 'tünel kapalı'));
        if (!j.running) strip.appendChild(el('span', 'badge text-bg-danger', 'playit çalışmıyor'));
        if (j.tunnel.alt && j.tunnel.alt !== j.tunnel.address) strip.appendChild(el('span', 'small text-body-secondary', 'alternatif: ' + j.tunnel.alt));
        const sp = el('span', 'ms-auto'); strip.appendChild(sp);
        strip.appendChild(btn('Kapat', 'bi-x-lg', 'btn-outline-secondary', closeTunnel));
        return;
      }
      if (j.error) strip.appendChild(el('span', 'small text-warning', j.error));
      else strip.appendChild(el('span', 'small text-body-secondary', 'Bu sunucu internete açık değil.'));
      strip.appendChild(btn('İnternete aç', 'bi-broadcast', 'btn-primary', () => openTunnel(j.warnings || [])));
    }
    async function load() {
      try { render(await api(`/api/instances/${id}/playit`)); } catch (e) { strip.hidden = true; }
    }
    load();
    setInterval(() => { if (!busy && document.visibilityState === 'visible') load(); }, 30000);
  }
})();
