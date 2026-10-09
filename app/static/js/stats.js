(function () {
  const root = document.getElementById('console-root');
  if (!root || !window.Chart) return;
  const id = root.dataset.instanceId;
  const $ = (k) => document.getElementById(k);
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  function fmtUptime(s) {
    const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    return d ? `${d}g ${h}s` : h ? `${h}s ${m}dk` : `${m}dk ${s % 60}sn`;
  }

  function make(canvasId, defs) {
    return new Chart($(canvasId), {
      type: 'line',
      data: { labels: [], datasets: defs.map(d => ({ label: d.label, data: [], yAxisID: d.axis, borderWidth: 2, pointRadius: 0, tension: .25, _color: d.color })) },
      options: {
        animation: false, responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { boxWidth: 12 } } },
        scales: {
          x: { ticks: { display: false } },
          y: { position: 'left', beginAtZero: true },
          y2: { position: 'right', beginAtZero: true, grid: { drawOnChartArea: false } },
        },
      },
    });
  }
  const res = make('chart-res', [{ label: 'CPU %', axis: 'y', color: '--accent' }, { label: 'RAM (MB)', axis: 'y2', color: '--accent-2' }]);
  const play = make('chart-play', [{ label: 'Oyuncu', axis: 'y', color: '--accent' }, { label: 'TPS', axis: 'y2', color: '--success' }]);
  res.options.scales.y.max = 100;
  play.options.scales.y2.max = 20;
  play.options.scales.y.ticks = { precision: 0 };

  function restyle() {   // renkler tema değişkenlerinden okunur → tema değişince grafikler de uyar
    const text = css('--text-muted'), grid = css('--border');
    [res, play].forEach(ch => {
      ch.data.datasets.forEach(ds => { ds.borderColor = css(ds._color); });
      ch.options.plugins.legend.labels.color = text;
      Object.values(ch.options.scales).forEach(sc => {
        sc.grid = { ...sc.grid, color: grid };
        sc.ticks = { ...sc.ticks, color: text };
      });
      ch.update('none');
    });
  }
  window.addEventListener('vulu-theme', restyle);
  restyle();

  const level = (t) => (t >= 18 ? 'ok' : t >= 15 ? 'warn' : 'bad');

  function render(s) {
    $('stat-cpu').textContent = s.running ? s.cpu.toFixed(1) + '%' : '—';
    $('stat-ram').textContent = s.running ? `${(s.ram_mb / 1024).toFixed(1)} GB` : '—';
    const extra = s.ram_mb - s.ram_max_mb;
    $('stat-ram-sub').textContent = s.running
      ? (extra > 0 ? `Heap ${(s.ram_max_mb / 1024).toFixed(1)} GB + Java'nın kendi payı ${(extra / 1024).toFixed(1)} GB`
                   : `Heap limiti ${(s.ram_max_mb / 1024).toFixed(1)} GB`)
      : '';
    $('stat-uptime').textContent = s.running ? fmtUptime(s.uptime) : '—';

    const pv = $('stat-players'), ps = $('stat-players-sub');
    if (s.running && s.players !== null) { pv.textContent = `${s.players} / ${s.max_players}`; ps.textContent = s.player_names.join(', '); }
    else { pv.textContent = '—'; ps.textContent = s.running && s.rcon !== 'ok' ? 'RCON bağlanıyor…' : ''; }

    const tv = $('stat-tps'), ts = $('stat-tps-sub');
    if (s.running && s.tps !== null) { tv.textContent = s.tps.toFixed(1); tv.dataset.level = level(s.tps); ts.textContent = ''; }
    else { tv.textContent = '—'; delete tv.dataset.level; ts.textContent = s.running && s.rcon === 'ok' ? (s.tps_supported ? 'TPS okunamadı' : 'Bu yükleyicide TPS komutu yok') : ''; }

    const h = s.history, labels = h.t.map(t => new Date(t * 1000).toLocaleTimeString());
    res.data.labels = labels; res.data.datasets[0].data = h.cpu; res.data.datasets[1].data = h.ram;
    play.data.labels = labels; play.data.datasets[0].data = h.players; play.data.datasets[1].data = h.tps;
    res.update('none'); play.update('none');
  }

  async function tick() {
    if (document.hidden) return;
    try { const r = await fetch(`/api/instances/${id}/stats`); if (r.ok) render(await r.json()); } catch (e) {}
  }
  tick();
  setInterval(tick, 2000);
})();
