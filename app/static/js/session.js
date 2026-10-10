/* Oturum süresi dolarsa: panel API'si 401 dönünce giriş sayfasına yönlendir (pencere içindeysek ana sayfayı). */
(function () {
  const orig = window.fetch;
  let redirecting = false;
  window.fetch = async function (input, init) {
    const r = await orig.apply(this, arguments);
    try {
      const url = new URL(typeof input === 'string' ? input : input.url, location.href);
      if (r.status === 401 && url.origin === location.origin && url.pathname.startsWith('/api/') && !redirecting) {
        redirecting = true;
        const top = window.top || window;
        const next = top.location.pathname + top.location.search;
        top.location.href = '/login?next=' + encodeURIComponent(next);
      }
    } catch (e) {}
    return r;
  };
})();
