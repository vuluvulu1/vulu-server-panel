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
    if (!r.ok) throw new Error(j.detail || (_t('Hata ') + r.status));
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
        b.show('error', _t('İşlem başlatılamadı.'), String(e.message || e));
      }
    };
  }

  // ---------- Minecraft sürüm listesi ----------
  async function loadVersions() {
    const wanted = mc.value || mc.dataset.selected || '';
    const hasInstaller = INSTALLERS.includes(loader.value);
    paperSection.classList.toggle('d-none', !hasInstaller);
    toggleArgs();
    mc.replaceChildren(new Option(_t('Yükleniyor…'), ''));
    try {
      const j = await getJSON('/api/minecraft/versions' + (hasInstaller ? '?loader=' + loader.value : ''));
      mc.replaceChildren(new Option(hasInstaller ? _t('— Sürüm seç —') : _t("— Seçme (Java'yı kendim ayarlayacağım) —"), ''));
      j.versions.forEach(v => mc.appendChild(new Option(v.id + (v.id === j.latest ? _t('  (en yeni)') : ''), v.id)));
      mc.value = j.versions.some(v => v.id === wanted) ? wanted : (j.latest && j.versions.some(v => v.id === j.latest) ? j.latest : '');
      mc.dataset.selected = '';
    } catch (e) {
      mc.replaceChildren(new Option(_t('Sürüm listesi alınamadı'), ''));
      J.show('error', _t('Minecraft sürüm listesi alınamadı.'), String(e.message || e));
    }
    refreshJava(); refreshLoader();
    if (typeof summary === 'function') summary();
    if (mc.value && $('step1-error')) $('step1-error').textContent = '';
  }

  // ---------- Java ----------
  async function refreshJava() {
    if (J.busy) return;
    const m = javaMode.value;
    customBox.classList.toggle('d-none', m !== 'custom');
    if (m === 'custom') { J.hide(); return; }
    const params = new URLSearchParams();
    if (m === 'auto') {
      if (!mc.value) { J.show('muted', _t("Java'yı otomatik seçmek için bir Minecraft sürümü seç.")); return; }
      params.set('mc_version', mc.value); params.set('loader', loader.value);
    } else params.set('major', m);

    const my = ++J.req;
    J.show('muted', _t('Java gereksinimi hesaplanıyor…'));
    try {
      const j = await getJSON('/api/java/resolve?' + params);
      if (my !== J.req) return;
      J.current = j;
      if (j.installed) J.show('ok', _t('✓ Java {major} kurulu', {major: j.major}) + (j.version ? ' (' + j.version + ')' : ''), j.reason);
      else if (j.package) {
        J.show('warn', _t("Java {major} gerekli — kurulu değil (≈ {v1} MB indirilecek)", {major: j.major, v1: (j.package.size / 1048576).toFixed(0)}), j.reason);
        J.btn.classList.remove('d-none');
      } else J.show('error', _t("Java {major} gerekli", {major: j.major}), j.error || j.reason);
    } catch (e) { if (my === J.req) J.show('error', String(e.message || e)); }
  }

  // ---------- Yükleyici jar'ı (Paper / Fabric) ----------
  async function refreshLoader() {
    if (P.busy) return;
    if (!INSTALLERS.includes(loader.value)) { P.hide(); return; }
    if (!mc.value) { P.show('muted', _t("Sunucu jar'ını indirmek için bir sürüm seç.")); return; }
    const my = ++P.req;
    P.show('muted', _t('Sürüm bilgisi alınıyor…'));
    try {
      const j = await getJSON(`/api/loader/resolve?loader=${loader.value}&mc_version=${encodeURIComponent(mc.value)}`);
      if (my !== P.req) return;
      P.current = j;
      const size = j.size > 0 ? ` · ≈ ${(j.size / 1048576).toFixed(0)} MB` : '';
      if (j.cached) P.show('ok', _t("✓ {label} indirildi (önbellekte)", {label: j.label}), _t('Sunucu ilk başlatılınca klasöre kopyalanır.'));
      else {
        P.show(j.stable ? 'warn' : 'error', _t('{label}{size} · indirilecek', {label: j.label, size}),
          j.stable ? _t("İstersen şimdi indir; yoksa ilk başlatmada otomatik indirilir.")
                   : _t("Dikkat: bu sürüm için kararlı (STABLE) build yok, deneysel build kullanılacak."));
        P.btn.classList.remove('d-none');
      }
    } catch (e) { if (my === P.req) P.show('error', _t('Sürüm bilgisi alınamadı.'), String(e.message || e)); }
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
    ramWarn.textContent = total && Number(ram.value) > total - 2 ? _t('⚠ Bilgisayarın kendisi için en az 2 GB boş bırakmalısın.') : '';
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

  // ---------- sunucu resmi (64x64 PNG'ye tarayıcıda kırpılır) ----------
  const iconFile = $('icon-file'), iconImg = $('icon-img'), iconData = $('icon_data'), iconReset = $('icon-reset');
  if (iconFile) {
    $('icon-pick').addEventListener('click', () => iconFile.click());
    iconFile.addEventListener('change', () => {
      const f = iconFile.files[0]; iconFile.value = '';
      if (!f) return;
      if (f.size > 20 * 1048576) { VuluModal.toast(_t('Resim çok büyük (en fazla 20 MB).'), 'danger'); return; }
      const url = URL.createObjectURL(f), im = new Image();
      im.onload = () => {
        const s = Math.min(im.naturalWidth, im.naturalHeight), cv = $('icon-canvas'), ctx = cv.getContext('2d');
        ctx.clearRect(0, 0, 64, 64); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(im, (im.naturalWidth - s) / 2, (im.naturalHeight - s) / 2, s, s, 0, 0, 64, 64);   // ortadan kare kırp
        URL.revokeObjectURL(url);
        const data = cv.toDataURL('image/png');
        iconImg.src = data; iconData.value = data.split(',')[1]; iconReset.classList.remove('d-none');
      };
      im.onerror = () => { URL.revokeObjectURL(url); VuluModal.toast(_t('Bu dosya resim olarak açılamadı.'), 'danger'); };
      im.src = url;
    });
    iconReset.addEventListener('click', () => {
      iconImg.src = '/static/img/default-icon.png'; iconData.value = ''; iconReset.classList.add('d-none');
    });
  }

  // ---------- adımlar ----------
  const NAMES = { vanilla: 'Vanilla', paper: 'Paper', fabric: 'Fabric', forge: 'Forge', neoforge: 'NeoForge' };
  const fixed = form.dataset.fixed === '1';
  function summary() {
    const l = $('sum-loader'), v = $('sum-version');
    if (fixed) return;
    if (l) l.textContent = NAMES[loader.value] || loader.value;
    if (v) v.textContent = mc.value || _t('(sürüm seçilmedi)');
  }
  function go(step, force) {
    if (fixed) step = 2;
    if (step === 2 && !force && !fixed && !mc.value && (INSTALLERS.includes(loader.value) || javaMode.value === 'auto')) {
      $('step1-error').textContent = _t('Devam etmek için bir Minecraft sürümü seç.');
      step = 1;
    } else $('step1-error').textContent = '';
    form.dataset.step = String(step);
    form.querySelectorAll('.nf-steps li').forEach(li => li.classList.toggle('active', li.dataset.goto === String(step)));
    summary();
    if (step === 2) { const n = $('name'); if (n && !n.value) setTimeout(() => n.focus(), 50); }
  }
  form.querySelectorAll('[data-goto]').forEach(b => b.addEventListener('click', () => go(Number(b.dataset.goto))));
  $('nf-next').addEventListener('click', () => go(2));
  // Enter tuşu 1. adımda formu göndermesin, ileri geçsin
  form.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && form.dataset.step === '1' && e.target.tagName !== 'BUTTON') { e.preventDefault(); go(2); }
  });

  // ---------- yükleyici kartları ----------
  const cards = form.querySelectorAll('.loader-card');
  function syncCards() {
    cards.forEach(c => { const on = c.dataset.loader === loader.value; c.classList.toggle('active', on); c.setAttribute('aria-checked', on ? 'true' : 'false'); });
  }
  cards.forEach(c => c.addEventListener('click', () => {
    if (loader.value === c.dataset.loader) return;
    loader.value = c.dataset.loader; syncCards();
    loader.dispatchEvent(new Event('change'));
  }));

  // RAM önerisi: yükleyiciye göre ipucu
  function ramHint() {
    const h = $('ram_hint'); if (!h) return;
    const heavy = ['forge', 'neoforge'].includes(loader.value) || fixed;
    h.firstChild.textContent = heavy ? _t('Modpack ve Forge/NeoForge sunucuları için genelde 6-8 GB önerilir; mod sayısı arttıkça ihtiyaç da artar. ')
                                     : _t('Vanilla, Paper ve Fabric için 2-4 GB çoğu zaman yeterlidir. ');
  }
  loader.addEventListener('change', () => { ramHint(); summary(); });
  ramHint();
  go(Number(form.dataset.step) || 1, true);

  mc.addEventListener('change', () => { refreshJava(); refreshLoader(); summary(); if (mc.value) $('step1-error').textContent = ''; });
  loader.addEventListener('change', loadVersions);
  javaMode.addEventListener('change', refreshJava);
  loadVersions();
})();
