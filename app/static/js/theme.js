/* Tema: tarayıcıda saklanır (localStorage). Seçim Ayarlar → Görünüm kartından yapılır. */
(function () {
  const root = document.documentElement;
  const modes = {};
  (root.dataset.themes || '').split(',').filter(Boolean).forEach(p => { const [id, mode] = p.split(':'); modes[id] = mode || 'dark'; });

  // Kayıtlı tema artık yoksa (dosyası silinmişse) varsayılana dön
  if (!(root.dataset.theme in modes)) {
    root.dataset.theme = root.dataset.defaultTheme;
    root.dataset.bsTheme = modes[root.dataset.defaultTheme] || 'dark';
  }

  function apply(id) {
    if (!(id in modes)) return;
    root.dataset.theme = id;
    root.dataset.bsTheme = modes[id];
    try { localStorage.setItem('vulu-theme', id); localStorage.setItem('vulu-theme-mode', modes[id]); } catch (e) {}
    // açık pencerelerdeki (iframe) sayfalar da değişsin
    document.querySelectorAll('iframe').forEach(f => { try { f.contentDocument.documentElement.dataset.theme = id; f.contentDocument.documentElement.dataset.bsTheme = modes[id]; } catch (e) {} });
    document.querySelectorAll('[data-theme-pick]').forEach(b => b.classList.toggle('active', b.dataset.themePick === id));
    window.dispatchEvent(new Event('vulu-theme'));
  }
  window.VuluTheme = { apply, current: () => root.dataset.theme };

  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-theme-pick]');
    if (b) apply(b.dataset.themePick);
  });
  document.querySelectorAll('[data-theme-pick]').forEach(b => b.classList.toggle('active', b.dataset.themePick === root.dataset.theme));
})();
