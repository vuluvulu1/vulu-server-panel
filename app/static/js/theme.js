(function () {
  const root = document.documentElement;
  const sel = document.getElementById('theme-select');
  if (!sel) return;

  // Kayıtlı tema artık yoksa (dosyası silinmişse) varsayılana dön
  const known = Array.from(sel.options).map(o => o.value);
  if (!known.includes(root.dataset.theme)) {
    root.dataset.theme = sel.dataset.default;
    root.dataset.bsTheme = 'dark';
  }
  sel.value = root.dataset.theme;

  sel.addEventListener('change', () => {
    const mode = sel.selectedOptions[0].dataset.mode || 'dark';
    root.dataset.theme = sel.value;
    root.dataset.bsTheme = mode;
    try {
      localStorage.setItem('vulu-theme', sel.value);
      localStorage.setItem('vulu-theme-mode', mode);
    } catch (e) {}
    window.dispatchEvent(new Event('vulu-theme'));
  });
})();
