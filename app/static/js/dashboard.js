(function () {
  const cards = document.querySelectorAll('[data-card]');
  if (!cards.length) return;
  const LABELS = { running: _t('Çalışıyor'), stopped: _t('Durdu'), preparing: _t('Hazırlanıyor'), starting: _t('Başlıyor'), stopping: _t('Durduruluyor'), crashed: _t('Çöktü') };

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
        if (s.players !== null) parts.push(_t("Oyuncu {players}/{max_players}", {players: s.players, max_players: s.max_players}));
        parts.push(_t("RAM {v0} GB", {v0: (s.ram_mb / 1024).toFixed(1)}), _t("CPU {cpu}%", {cpu: s.cpu}));
        if (s.tps !== null) parts.push(_t("TPS {tps}", {tps: s.tps}));
        el.textContent = parts.join(' · ');
      });
    } catch (e) {}
  }
  tick();
  setInterval(tick, 4000);
})();
