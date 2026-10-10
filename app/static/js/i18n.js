/* Arayüz çevirisi: _t("Türkçe metin {x}", {x: 1}). Katalog yalnızca Türkçe dışı dillerde sayfaya gömülür. */
(function () {
  let cat = {};
  try { const el = document.getElementById('vulu-i18n'); if (el) cat = JSON.parse(el.textContent) || {}; } catch (e) {}
  window.VULU_LANG = document.documentElement.lang || 'tr';
  window._t = function (s, vars) {
    let m = Object.prototype.hasOwnProperty.call(cat, s) ? cat[s] : s;
    if (vars) m = m.replace(/\{(\w+)\}/g, (all, k) => (k in vars ? String(vars[k]) : all));
    return m;
  };
  window.VuluI18n = {
    lang: window.VULU_LANG,
    async set(lang) {
      document.cookie = 'vulu_lang=' + encodeURIComponent(lang) + '; path=/; max-age=31536000; samesite=strict';
      try {                                   // panel geneli dil (konsol mesajları vb.); giriş sayfasında 401 döner, sorun değil
        await fetch('/api/panel/lang', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lang})});
      } catch (e) {}
      location.reload();
    },
  };
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('[data-lang-pick]');
    if (b && b.dataset.langPick !== window.VULU_LANG) window.VuluI18n.set(b.dataset.langPick);
  });
})();
