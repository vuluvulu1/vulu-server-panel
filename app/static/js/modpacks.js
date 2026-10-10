(function () {
  const results = document.getElementById('results'), more = document.getElementById('more-btn'), notes = document.getElementById('notes');
  if (!results) return;
  let offset = 0, total = 0, query = '';
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  function card(h) {
    const col = el('div', 'col-md-6 col-xl-4'), c = el('div', 'card static h-100'), b = el('div', 'card-body d-flex gap-3');
    if (h.icon) { const im = el('img', 'mod-icon'); im.width = 48; im.height = 48; im.style.cssText = 'width:48px;height:48px;flex:none;object-fit:cover'; im.src = h.icon; im.alt = ''; im.referrerPolicy = 'no-referrer'; im.loading = 'lazy'; b.appendChild(im); }
    else { const ph = el('div', 'mod-icon'); ph.style.cssText = 'width:48px;height:48px;flex:none'; b.appendChild(ph); }
    const mid = el('div', 'flex-grow-1'); mid.style.minWidth = '0';
    mid.appendChild(el('h3', 'h6 mb-1', h.title));
    mid.appendChild(el('p', 'small text-body-secondary mb-1 mod-desc', h.description));
    const meta = el('div', 'small text-body-secondary', _t('{author} · {n} indirme', {author: h.author, n: h.downloads.toLocaleString(VULU_LANG)}));
    mid.appendChild(meta);
    const chips = el('div', 'd-flex flex-wrap gap-1 mt-1');
    if (h.mc) chips.appendChild(el('span', 'badge text-bg-secondary', _t('MC ') + h.mc));
    h.loaders.forEach(l => chips.appendChild(el('span', 'badge text-bg-secondary', l)));
    mid.appendChild(chips);
    b.appendChild(mid);
    const a = el('a', 'btn btn-sm btn-primary align-self-start flex-shrink-0', _t('Sunucu oluştur'));
    a.href = '/instances/new?modpack=' + encodeURIComponent(h.slug);
    a.dataset.modal = _t('Yeni sunucu · ') + h.title; a.dataset.modalSize = 'md';
    b.appendChild(a); c.appendChild(b); col.appendChild(c);
    return col;
  }

  async function search(reset) {
    if (reset) { offset = 0; results.replaceChildren(); query = document.getElementById('search-q').value.trim(); }
    more.classList.add('d-none'); notes.replaceChildren();
    try {
      const r = await fetch(`/api/modpacks/search?q=${encodeURIComponent(query)}&offset=${offset}`);
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || (_t('Hata ') + r.status));
      total = j.total; offset += j.hits.length;
      j.hits.forEach(h => results.appendChild(card(h)));
      if (!results.children.length) results.appendChild(el('p', 'text-body-secondary', _t('Sonuç yok.')));
      if (offset < total && j.hits.length) more.classList.remove('d-none');
    } catch (e) { notes.appendChild(el('div', 'alert alert-danger py-2 small', String(e.message || e))); }
  }
  document.getElementById('search-form').addEventListener('submit', () => search(true));
  more.addEventListener('click', () => search(false));
  search(true);
})();
