(function () {
  const form = document.getElementById('instance-form');
  if (!form) return;

  const $ = (id) => document.getElementById(id);
  const mc = $('mc_version'), loader = $('loader'), javaMode = $('java_mode');
  const customBox = $('java-custom-box'), paperSection = $('paper-section');
  const INSTALLERS = ['paper', 'fabric', 'forge', 'neoforge'];            // jar'ı panelin indirebildiği yükleyiciler
  const ARGS_LOADERS = ['forge', 'neoforge'];

  // Durum kutusu + ilerleme çubuğu bileşeni (Java ve yükleyici aynısını kullanır)
  function makeBox(prefix) {
    const box = $(prefix + '-status'), text = $(prefix + '-status-text'), reason = $(prefix + '-status-reason');
    const btn = $(prefix + '-install-btn');
    return {
      btn, prog: VuluProgress.attach(prefix), busy: false, current: null, req: 0,
      show(kind, main, sub) {
        box.classList.remove('d-none');
        box.dataset.kind = kind;            // ok | warn | error | muted
        text.textContent = main;
        reason.textContent = sub || '';
        btn.classList.add('d-none');
      },
      hide() { box.classList.add('d-none'); this.prog.hide(); },
    };
  }
  const J = makeBox('java'), P = makeBox('paper');

  async function getJSON(url, opts) {
    const r = await fetch(url, opts);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || ('Hata ' + r.status));
    return j;
  }

  // Bir indirme işini izler; bitince onDone çağrılır
  function runJob(b, startFn, onDone) {
    return async () => {
      if (!b.current || b.busy) return;
      b.busy = true; b.btn.disabled = true;
      try {
        const j = await startFn();
        if (!j.job_id) { b.busy = false; b.btn.disabled = false; onDone(); return; }
        VuluProgress.watchJob(j.job_id, (s) => {
          b.prog.show(s);
          if (s.status !== 'running') {
            b.busy = false; b.btn.disabled = false;
            setTimeout(() => { if (s.status === 'done') b.prog.hide(); onDone(); }, s.status === 'done' ? 1200 : 0);
          }
        });
      } catch (e) {
        b.busy = false; b.btn.disabled = false;
        b.show('error', 'İşlem başlatılamadı.', String(e.message || e));
      }
    };
  }

  // ---------- Minecraft sürüm listesi ----------
  async function loadVersions() {
    const wanted = mc.value || mc.dataset.selected || '';
    const hasInstaller = INSTALLERS.includes(loader.value);
    paperSection.classList.toggle('d-none', !hasInstaller);
    toggleArgs();
    mc.replaceChildren(new Option('Yükleniyor…', ''));
    try {
      const j = await getJSON('/api/minecraft/versions' + (hasInstaller ? '?loader=' + loader.value : ''));
      mc.replaceChildren(new Option(hasInstaller ? '— Sürüm seç —' : "— Seçme (Java'yı kendim ayarlayacağım) —", ''));
      j.versions.forEach(v => mc.appendChild(new Option(v.id + (v.id === j.latest ? '  (en yeni)' : ''), v.id)));
      mc.value = j.versions.some(v => v.id === wanted) ? wanted : '';
      mc.dataset.selected = '';
    } catch (e) {
      mc.replaceChildren(new Option('Sürüm listesi alınamadı', ''));
      J.show('error', 'Minecraft sürüm listesi alınamadı.', String(e.message || e));
    }
    refreshJava(); refreshLoader();
  }

  // ---------- Java ----------
  async function refreshJava() {
    if (J.busy) return;
    const m = javaMode.value;
    customBox.classList.toggle('d-none', m !== 'custom');
    if (m === 'custom') { J.hide(); return; }
    const params = new URLSearchParams();
    if (m === 'auto') {
      if (!mc.value) { J.show('muted', "Java'yı otomatik seçmek için bir Minecraft sürümü seç."); return; }
      params.set('mc_version', mc.value); params.set('loader', loader.value);
    } else params.set('major', m);

    const my = ++J.req;
    J.show('muted', 'Java gereksinimi hesaplanıyor…');
    try {
      const j = await getJSON('/api/java/resolve?' + params);
      if (my !== J.req) return;
      J.current = j;
      if (j.installed) J.show('ok', `✓ Java ${j.major} kurulu${j.version ? ' (' + j.version + ')' : ''}`, j.reason);
      else if (j.package) {
        J.show('warn', `Java ${j.major} gerekli — kurulu değil (≈ ${(j.package.size / 1048576).toFixed(0)} MB indirilecek)`, j.reason);
        J.btn.classList.remove('d-none');
      } else J.show('error', `Java ${j.major} gerekli`, j.error || j.reason);
    } catch (e) { if (my === J.req) J.show('error', String(e.message || e)); }
  }

  // ---------- Yükleyici jar'ı (Paper / Fabric) ----------
  async function refreshLoader() {
    if (P.busy) return;
    if (!INSTALLERS.includes(loader.value)) { P.hide(); return; }
    if (!mc.value) { P.show('muted', "Sunucu jar'ını indirmek için bir sürüm seç."); return; }
    const my = ++P.req;
    P.show('muted', 'Sürüm bilgisi alınıyor…');
    try {
      const j = await getJSON(`/api/loader/resolve?loader=${loader.value}&mc_version=${encodeURIComponent(mc.value)}`);
      if (my !== P.req) return;
      P.current = j;
      const size = j.size > 0 ? ` · ≈ ${(j.size / 1048576).toFixed(0)} MB` : '';
      if (j.cached) P.show('ok', `✓ ${j.label} indirildi (önbellekte)`, 'Sunucu ilk başlatılınca klasöre kopyalanır.');
      else {
        P.show(j.stable ? 'warn' : 'error', `${j.label}${size} · indirilecek`,
          j.stable ? "İstersen şimdi indir; yoksa ilk başlatmada otomatik indirilir."
                   : "Dikkat: bu sürüm için kararlı (STABLE) build yok, deneysel build kullanılacak.");
        P.btn.classList.remove('d-none');
      }
    } catch (e) { if (my === P.req) P.show('error', 'Sürüm bilgisi alınamadı.', String(e.message || e)); }
  }

  J.btn.addEventListener('click', runJob(J, () => getJSON('/api/java/install', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ major: J.current.major }),
  }), refreshJava));
  P.btn.addEventListener('click', runJob(P, () => getJSON('/api/loader/download', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ loader: loader.value, mc_version: mc.value }),
  }), refreshLoader));

  // ---------- RAM kaydırıcısı ----------
  const ram = $('ram_gb'), ramOut = $('ram_out'), ramWarn = $('ram_warn');
  function ramUpdate() {
    ramOut.textContent = ram.value;
    const total = Number(ram.dataset.total || 0);
    ramWarn.textContent = total && Number(ram.value) > total - 2 ? '⚠ İşletim sistemi için en az 2 GB boş bırak' : '';
  }
  ram.addEventListener('input', ramUpdate);
  ramUpdate();

  // ---------- Başlatma türü: argüman dosyası kutusu ----------
  const launch = $('launch_type'), argsBox = $('args-box');
  function toggleArgs() {
    const show = launch.value === 'args-file' || (launch.value === 'auto' && ARGS_LOADERS.includes(loader.value));
    argsBox.classList.toggle('d-none', !show);
  }
  launch.addEventListener('change', toggleArgs);

  mc.addEventListener('change', () => { refreshJava(); refreshLoader(); });
  loader.addEventListener('change', loadVersions);
  javaMode.addEventListener('change', refreshJava);
  loadVersions();
})();
