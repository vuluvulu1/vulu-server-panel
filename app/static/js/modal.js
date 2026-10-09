/* Açılır pencere (modal) bileşeni.
   VuluModal.open({ title, url })                     → sayfayı pencere içinde açar (?embed=1)
   VuluModal.open({ title, body, actions, beforeClose, onClose, size }) → kendi içeriğin
   Gömülü sayfalardan: VuluModal.changed() → ana sayfaya "bir şey değişti" bildirir. */
window.VuluModal = (function () {
  const stack = [];
  const embedded = window.parent !== window;
  const origin = location.origin;

  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  function open(opts) {
    const backdrop = el('div', 'vmodal-backdrop');
    const dlg = el('div', 'vmodal' + (opts.size ? ' vmodal-' + opts.size : ''));
    dlg.setAttribute('role', 'dialog'); dlg.setAttribute('aria-modal', 'true');
    const head = el('div', 'vmodal-head');
    const title = el('div', 'vmodal-title', opts.title || '');
    const tools = el('div', 'vmodal-tools');
    (opts.actions || []).forEach(a => tools.appendChild(a));
    const x = el('button', 'btn btn-sm btn-outline-secondary'); x.type = 'button'; x.title = 'Kapat (Esc)';
    x.appendChild(el('i', 'bi bi-x-lg')); tools.appendChild(x);
    head.append(title, tools);
    const body = el('div', 'vmodal-body');
    let frame = null, changed = false;
    if (opts.url) {
      frame = el('iframe', 'vmodal-frame');
      const u = new URL(opts.url, location.href); u.searchParams.set('embed', '1');
      frame.src = u.pathname + u.search; frame.title = opts.title || '';
      body.appendChild(frame);
    } else if (opts.body) body.appendChild(opts.body);
    dlg.append(head, body); backdrop.appendChild(dlg); document.body.appendChild(backdrop);
    document.body.classList.add('vmodal-open');

    const m = {
      el: dlg, frame, title,
      markChanged() { changed = true; },
      close(force) {
        if (!force && opts.beforeClose && opts.beforeClose() === false) return false;
        const i = stack.indexOf(m); if (i >= 0) stack.splice(i, 1);
        backdrop.remove();
        if (!stack.length) document.body.classList.remove('vmodal-open');
        if (opts.onClose) opts.onClose({ changed, toast: m.pendingToast });
        else if (m.pendingToast) toast(m.pendingToast, 'success');
        return true;
      },
    };
    x.addEventListener('click', () => m.close());
    backdrop.addEventListener('mousedown', (e) => { if (e.target === backdrop) m.close(); });
    stack.push(m);
    setTimeout(() => (frame || dlg.querySelector('textarea, input, button') || x).focus(), 30);
    return m;
  }

  // ---------- bildirim (toast) ----------
  let toastBox = null;
  function toast(text, kind) {
    if (embedded) { window.parent.postMessage({ type: 'vulu-toast', text: String(text), kind: kind === 'danger' ? 'danger' : 'success' }, origin); return; }
    if (!toastBox) { toastBox = el('div', 'vtoast-box'); toastBox.setAttribute('aria-live', 'polite'); document.body.appendChild(toastBox); }
    const t = el('div', 'vtoast vtoast-' + (kind || 'success'));
    t.appendChild(el('i', 'bi ' + (kind === 'danger' ? 'bi-exclamation-triangle-fill' : 'bi-check-circle-fill')));
    t.appendChild(el('span', '', String(text).slice(0, 300)));
    toastBox.appendChild(t);
    setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 300); }, kind === 'danger' ? 6000 : 3500);
  }
  // yeniden yüklemeden önce bırakılan bildirimi göster
  try { const s = sessionStorage.getItem('vulu-toast'); if (s) { sessionStorage.removeItem('vulu-toast'); const o = JSON.parse(s); setTimeout(() => toast(o.text, o.kind), 50); } } catch (e) {}

  // Gömülü sayfalardan gelen mesajlar (yalnızca aynı kaynak ve kendi pencerelerimiz)
  window.addEventListener('message', (e) => {
    if (e.origin !== origin || !e.data || typeof e.data.type !== 'string') return;
    const m = stack.find(s => s.frame && s.frame.contentWindow === e.source);
    if (!m) return;
    if (e.data.type === 'vulu-changed') m.markChanged();
    else if (e.data.type === 'vulu-close') m.close();
    else if (e.data.type === 'vulu-toast' && typeof e.data.text === 'string') toast(e.data.text, e.data.kind);
    else if (e.data.type === 'vulu-saved') {        // kaydedildi: bildir ve pencereyi kapat
      const text = typeof e.data.text === 'string' ? e.data.text : 'Kaydedildi.';
      if (e.data.changed) m.markChanged();
      m.pendingToast = text;
      m.close(true);
    }
    else if (e.data.type === 'vulu-title' && typeof e.data.title === 'string') m.title.textContent = e.data.title.slice(0, 120);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (stack.length) { e.preventDefault(); stack[stack.length - 1].close(); }
    else if (embedded) window.parent.postMessage({ type: 'vulu-close' }, origin);
  });

  // [data-modal] bağlantıları: Ctrl/orta tıkla yeni sekmede normal sayfa olarak açılır
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-modal]');
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    open({ title: a.dataset.modal || a.textContent.trim(), url: a.getAttribute('href'), size: a.dataset.modalSize === 'md' ? 'md' : undefined,
           onClose: ({ changed, toast: msg }) => {
             if (changed && a.dataset.modalReload !== '0') {
               if (msg) try { sessionStorage.setItem('vulu-toast', JSON.stringify({ text: msg, kind: 'success' })); } catch (x) {}
               location.reload();
             } else if (msg) toast(msg, 'success');
           } });
  });

  // Pencere içinde "Vazgeç" gibi [data-modal-close] bağlantıları pencereyi kapatır
  document.addEventListener('click', (e) => {
    const a = e.target.closest('[data-modal-close]');
    if (!a || !embedded) return;
    e.preventDefault(); window.parent.postMessage({ type: 'vulu-close' }, origin);
  });

  // Pencere içinde bir işlem bitti ve ana sayfa başka bir sayfaya geçmeli (örn. yeni sunucu oluşturuldu).
  // Yalnızca aynı kaynaktaki geçerli sayfanın yolu kullanılır (dış adrese yönlendirme yok).
  if (embedded && new URLSearchParams(location.search).get('breakout') === '1') {
    try { sessionStorage.setItem('vulu-toast', JSON.stringify({ text: 'Sunucu oluşturuldu.', kind: 'success' })); } catch (x) {}
    window.top.location.href = location.pathname;
  }

  return {
    open,
    isOpen: () => stack.length > 0,
    embedded,
    changed() { if (embedded) window.parent.postMessage({ type: 'vulu-changed' }, origin); },
    toast,
    /* Kayıt başarılı: pencere içindeysek kapat + ana sayfada bildir; değilse burada bildir */
    saved(text, changed) { if (embedded) window.parent.postMessage({ type: 'vulu-saved', text, changed: !!changed }, origin); else toast(text, 'success'); },
    navigateTop(url) { (embedded ? window.top : window).location.href = url; },
  };
})();
