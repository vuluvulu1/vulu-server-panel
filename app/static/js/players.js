(function () {
  const root = document.getElementById('players-root');
  if (!root) return;
  const id = root.dataset.instanceId;
  const $ = (k) => document.getElementById(k);
  const NAME = /^[A-Za-z0-9_]{1,16}$/;
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const note = (kind, text) => $('pl-notes').replaceChildren(el('div', `alert alert-${kind} py-2 small mb-2`, text));
  let busy = false, state = null;

  async function api(path, opts) {
    const r = await fetch(`/api/instances/${id}/players/${path}`, opts);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : (_t('Hata ') + r.status));
    return j;
  }

  function head(name) {
    // oyuncu kafası: dış görsel yüklemiyoruz (gizlilik), baş harf rozeti
    const s = el('span', 'player-head d-inline-flex align-items-center justify-content-center small fw-semibold me-2', name.slice(0, 1).toUpperCase());
    return s;
  }

  function row(name, extra, buttons) {
    const li = el('li', 'list-group-item d-flex align-items-center gap-2');
    li.appendChild(head(name));
    const t = el('div', 'flex-grow-1 text-truncate');
    t.appendChild(el('span', '', name));
    if (extra) t.appendChild(el('span', 'small text-body-secondary ms-2', extra));
    li.appendChild(t);
    buttons.forEach(([label, icon, act, cls, ask]) => {
      const b = el('button', `btn btn-sm ${cls}`); b.type = 'button'; b.title = label;
      b.appendChild(el('i', 'bi ' + icon));
      b.addEventListener('click', () => run(act, name, ask));
      li.appendChild(b);
    });
    return li;
  }

  function fill(listId, items, mk) {
    const ul = $('l-' + listId); ul.replaceChildren();
    $('c-' + listId).textContent = items.length;
    if (!items.length) ul.appendChild(el('li', 'list-group-item small text-body-secondary', _t('Boş')));
    items.slice(0, 500).forEach(x => ul.appendChild(mk(x)));
  }

  function render(j) {
    state = j;
    const running = j.status === 'running';
    $('wl-switch').checked = !!j.whitelist_enabled;
    $('pl-mode').textContent = (j.online_mode ? _t('Hesap doğrulaması açık') : _t('Hesap doğrulaması kapalı (online-mode=false)')) + ' · ' + (running ? _t('değişiklikler anında uygulanır') : _t('değişiklikler sunucu açılınca uygulanır'));
    $('pl-help').textContent = running ? _t('Sunucu açık: işlemler doğrudan sunucuya komut olarak gönderilir.') :
      (j.online_mode ? _t('Sunucu kapalı: oyuncunun hesap kimliği Mojang\'dan öğrenilir, bu yüzden internet bağlantısı gerekir.') : _t('Sunucu kapalı ve hesap doğrulaması kapalı: oyuncu kimliği addan hesaplanır, internet gerekmez.'));
    const wl = new Set(j.whitelist.map(e => e.name.toLowerCase())), ops = new Set(j.ops.map(e => e.name.toLowerCase()));
    fill('online', j.online.map(n => ({ name: n })), (e) => row(e.name, '', [
      ...(ops.has(e.name.toLowerCase()) ? [] : [[_t('OP yap'), 'bi-star', 'op', 'btn-outline-warning']]),
      [_t('At'), 'bi-box-arrow-right', 'kick', 'btn-outline-secondary', 'kick'],
      [_t('Yasakla'), 'bi-slash-circle', 'ban', 'btn-outline-danger', 'ban'],
    ]));
    fill('whitelist', j.whitelist, (e) => row(e.name, '', [[_t('Listeden çıkar'), 'bi-x-lg', 'whitelist_remove', 'btn-outline-secondary']]));
    fill('ops', j.ops, (e) => row(e.name, _t('seviye ') + e.level, [[_t('OP\'luğu al'), 'bi-star-fill', 'deop', 'btn-outline-secondary']]));
    fill('bans', j.bans, (e) => row(e.name, e.reason ? '— ' + e.reason : '', [[_t('Yasağı kaldır'), 'bi-unlock', 'pardon', 'btn-outline-success']]));
    if (j.status === 'starting' || j.status === 'stopping' || j.status === 'preparing') note('warning', _t('Sunucu şu an açılıyor ya da kapanıyor; birkaç saniye sonra tekrar dene.'));
  }

  async function load() {
    try { render(await api('list')); } catch (e) { note('danger', String(e.message || e)); }
  }

  async function run(action, name, ask) {
    if (busy) return;
    let reason = '';
    if (ask === 'ban' || (action === 'ban' && !ask)) {
      if (!confirm(_t("{name} yasaklansın mı?", {name}))) return;
      reason = (prompt(_t('Yasak nedeni (isteğe bağlı):'), '') || '').slice(0, 100);
    } else if (ask === 'kick') {
      reason = (prompt(_t("{name} sunucudan atılsın mı? Neden (isteğe bağlı):", {name}), '') ?? null);
      if (reason === null) return;
    }
    busy = true; document.querySelectorAll('#players-root button, #wl-switch').forEach(b => b.disabled = true);
    try {
      const j = await api('action', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, name, reason }) });
      render(j); VuluModal.toast(j.message, 'success'); $('pl-notes').replaceChildren();
    } catch (e) { note('danger', String(e.message || e)); if (state) render(state); }
    finally { busy = false; document.querySelectorAll('#players-root button, #wl-switch').forEach(b => b.disabled = false); }
  }

  document.querySelectorAll('#pl-form [data-act]').forEach(b => b.addEventListener('click', () => {
    const n = $('pl-name').value.trim();
    if (!NAME.test(n)) { note('danger', _t('Oyuncu adı 1-16 karakter olmalı; yalnızca harf, rakam ve alt çizgi.')); return; }
    run(b.dataset.act, n).then(() => { if (!$('pl-notes').firstChild) $('pl-name').value = ''; });
  }));
  $('wl-switch').addEventListener('change', (e) => run(e.target.checked ? 'whitelist_on' : 'whitelist_off', ''));

  load();
  setInterval(() => { if (!busy && document.visibilityState === 'visible') load(); }, 10000);
})();
