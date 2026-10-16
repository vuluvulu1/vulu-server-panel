(function () {
  const root = document.getElementById('vp-root');
  if (!root) return;
  const $ = (k) => document.getElementById(k);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const notes = $('notes'), list = $('vp-list');
  const LOADERS = { vanilla: 'Vanilla', fabric: 'Fabric', forge: 'Forge', neoforge: 'NeoForge', quilt: 'Quilt' };
  const note = (kind, text) => notes.replaceChildren(el('div', `alert alert-${kind} py-2 small mb-0`, text));
  async function api(url, data) {
    const r = await fetch(url, data ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) } : { cache: 'no-store' });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : (_t('Hata ') + r.status));
    return j;
  }
  function linked(name) {
    $('vp-link-card').classList.toggle('d-none', !!name);
    $('vp-account-row').classList.toggle('d-none', !name);
    $('vp-hint').classList.toggle('d-none', !name);
    $('vp-account').textContent = name || '';
    if (!name) list.replaceChildren();
  }

  function card(p) {
    const col = el('div', 'col-md-6 col-xl-4'), c = el('div', 'card static h-100 vp-card');
    if (p.cover_url) {
      const im = el('img', 'vp-cover'); im.src = p.cover_url; im.alt = ''; im.loading = 'lazy'; im.referrerPolicy = 'no-referrer';
      im.onerror = () => im.remove();
      c.appendChild(im);
    }
    const b = el('div', 'card-body d-flex flex-column gap-1');
    b.appendChild(el('h3', 'h6 mb-0', p.name));
    b.appendChild(el('div', 'small text-body-secondary', _t('Paylaşan: {a} · rev {r}', { a: p.author, r: p.revision })));
    if (p.description) b.appendChild(el('p', 'small text-body-secondary mb-1 mod-desc', p.description));
    const chips = el('div', 'd-flex flex-wrap gap-1');
    chips.appendChild(el('span', 'badge text-bg-secondary', 'MC ' + p.mc_version));
    chips.appendChild(el('span', 'badge text-bg-secondary', (LOADERS[p.loader] || p.loader) + (p.loader_version ? ' ' + p.loader_version : '')));
    if (p.mod_count) chips.appendChild(el('span', 'badge text-bg-secondary', _t('{n} mod', { n: p.mod_count })));
    if ((p.includes || []).some(x => x.toLowerCase() === 'kubejs')) chips.appendChild(el('span', 'badge text-bg-secondary', 'KubeJS'));
    b.appendChild(chips);
    if (p.servers.length) {
      const s = el('div', 'small mt-1');
      s.appendChild(el('span', 'text-body-secondary', _t('Sunucular: ')));
      p.servers.forEach((srv, i) => {
        if (i) s.appendChild(document.createTextNode(', '));
        const a = el('a', '', srv.name + (srv.revision && srv.revision < p.revision ? ' ' + _t('(güncelleme var)') : ''));
        a.href = '/instances/' + srv.id;
        s.appendChild(a);
      });
      b.appendChild(s);
    }
    const foot = el('div', 'mt-auto pt-2');
    if (p.supported) {
      const a = el('a', 'btn btn-sm btn-primary', _t('Sunucu oluştur'));
      a.href = '/instances/new?vulupack=' + encodeURIComponent(p.id) + (root.dataset.embed ? '&embed=1' : '');
      if (!root.dataset.embed) { a.dataset.modal = _t('Yeni sunucu · ') + p.name; a.dataset.modalSize = 'md'; }
      foot.appendChild(a);
    } else {
      foot.appendChild(el('span', 'small text-warning', _t('{l} paketleri panelde desteklenmiyor.', { l: LOADERS[p.loader] || p.loader })));
    }
    b.appendChild(foot);
    c.appendChild(b); col.appendChild(c);
    return col;
  }

  async function load() {
    notes.replaceChildren();
    list.replaceChildren(el('p', 'text-body-secondary small', _t('Paketler yükleniyor… (vulu sunucusu uykudaysa bir dakika kadar sürebilir)')));
    try {
      const j = await api('/api/vulupacks');
      linked(j.account);
      if (!j.account) return;
      list.replaceChildren(...(j.packs.length ? j.packs.map(card) : [el('p', 'text-body-secondary', _t('Henüz paylaşılmış paket yok.'))]));
    } catch (e) { list.replaceChildren(); note('danger', String(e.message || e)); }
  }

  $('vp-link-form').addEventListener('submit', async () => {
    const btn = $('vp-link-btn');
    btn.disabled = true; btn.textContent = _t('Bağlanıyor…');
    try {
      const j = await api('/api/vulupacks/link', { username: $('vp-user').value, password: $('vp-pass').value });
      $('vp-pass').value = '';
      VuluModal.toast(_t('{u} hesabına bağlandı.', { u: j.username }), 'success');
      linked(j.username);
      load();
    } catch (e) { note('danger', String(e.message || e)); }
    finally { btn.disabled = false; btn.textContent = _t('Bağla'); }
  });
  $('vp-refresh').addEventListener('click', load);
  $('vp-unlink').addEventListener('click', async () => {
    if (!confirm(_t('Panelin vulu hesabıyla bağlantısı kaldırılsın mı? Kurulu sunucular etkilenmez.'))) return;
    try { await api('/api/vulupacks/unlink', {}); linked(null); }
    catch (e) { note('danger', String(e.message || e)); }
  });
  if ($('vp-account').textContent) load();
})();
