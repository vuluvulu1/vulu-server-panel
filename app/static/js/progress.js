/* Ortak ilerleme çubuğu. Şablonda progress_panel(prefix) makrosuyla birlikte kullanılır. */
window.VuluProgress = {
  attach(prefix) {
    const panel = document.getElementById(prefix + '-progress');
    const title = document.getElementById(prefix + '-progress-title');
    const pct = document.getElementById(prefix + '-progress-percent');
    const bar = document.getElementById(prefix + '-progress-bar');
    const msg = document.getElementById(prefix + '-progress-message');
    return {
      show(s) {                       // s: sunucudan gelen progress anlık görüntüsü
        panel.classList.remove('d-none');
        panel.dataset.state = s.status;
        title.textContent = s.title || '';
        pct.textContent = Math.floor(s.percent || 0) + '%';
        bar.style.width = (s.percent || 0) + '%';
        msg.textContent = s.status === 'error' ? (s.error || 'Hata') : (s.message || '');
      },
      hide() { panel.classList.add('d-none'); },
    };
  },

  watchJob(jobId, onUpdate) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${jobId}`);
    ws.onmessage = (e) => onUpdate(JSON.parse(e.data));
    return ws;
  },
};
