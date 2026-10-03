(function () {
  const cards = document.querySelectorAll('[data-card]');
  if (!cards.length) return;
  const LABELS = { running: 'Çalışıyor', stopped: 'Durdu', preparing: 'Hazırlanıyor', starting: 'Başlıyor', stopping: 'Durduruluyor', crashed: 'Çöktü' };

  async function tick() {
    if (document.hidden) return;
    try {
      const r = await fetch('/api/stats');
      if (!r.ok) return;
      const d = await r.json();
      cards.forEach(c => {
        const s = d[c.dataset.card];
        if (!s) return;
        const badge = c.querySelector('.status');
        badge.className = 'status status-' + s.status;
        badge.querySelector('.status-label').textContent = LABELS[s.status] || s.status;
        const el = c.querySelector('[data-stats]');
        if (!s.running) { el.textContent = ''; return; }
        const parts = [];
        if (s.players !== null) parts.push(`Oyuncu ${s.players}/${s.max_players}`);
        parts.push(`RAM ${(s.ram_mb / 1024).toFixed(1)} GB`, `CPU ${s.cpu}%`);
        if (s.tps !== null) parts.push(`TPS ${s.tps}`);
        el.textContent = parts.join(' · ');
      });
    } catch (e) {}
  }
  tick();
  setInterval(tick, 4000);
})();
