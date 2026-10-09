# Yol Haritası

Bu belge, vulu Server Panel'in mevcut durumunu, tasarım kararlarını ve planlanan işleri özetler. Katkıda bulunmak isteyenler için bir başlangıç noktasıdır.

Gösterim: `[x]` tamamlandı · `[~]` kısmen / gerçek ortamda daha fazla doğrulama gerekiyor · `[ ]` planlanıyor

## 1. Genel durum

| Alan | Durum |
|---|---|
| Süreç yönetimi, canlı konsol | ✅ |
| İzleme (CPU/RAM, oyuncu, TPS) | ✅ |
| Java, Paper, Fabric, NeoForge kurulumu | ✅ gerçek ortamda doğrulandı |
| Forge kurulumu | 🔶 kod tamam, gerçek ortamda daha fazla doğrulama gerekiyor |
| Profiller, Modrinth mod kurulumu, mod tarayıcı | ✅ |
| Modpack (`.mrpack`) içe aktarma | 🔶 test edilecek |
| Sunucu ayarları, `server.properties` formu, silme | 🔶 kod ve otomatik testler tamam, gerçek ortamda doğrulama bekliyor |
| Dosya yöneticisi, yedekleme, zamanlama | ⏳ planlanıyor |
| Giriş sistemi ve uzaktan yayınlama | ⏳ planlanıyor |

## 2. Mevcut özellikler

- **Sunucu yönetimi:** `Popen` + okuyucu thread (Windows'ta yeniden yükleme uyumu için), durumlar `stopped / preparing / starting / running / stopping / crashed`, düzgün durdurma, çökme tespiti, son 1000 satırlık konsol tamponu, WebSocket ile canlı akış.
- **İzleme:** `psutil` ile süreç ağacının CPU/RAM kullanımı; RCON ile oyuncu listesi ve TPS (Paper `tps`, Forge `forge tps`, NeoForge `neoforge tps`; ondalık virgül biçimleri ayrıştırılır); Chart.js grafikleri (yerel dosya).
- **Java:** Mojang'ın sürüm verisinden gereken sürüm tespiti, Eclipse Temurin JRE, SHA-256 doğrulaması, `java -version` testi, `runtimes/java-N/`.
- **Kurucular:** Paper (Fill v3 API), Fabric (meta API), Forge ve NeoForge (resmi Maven + `--installServer`). Hepsi önbellekli ve yüzdeli ilerlemelidir. Başlatma türleri: `jar` ve `args-file`.
- **JVM:** Aikar ön ayarı, RAM kaydırıcısı, doğrulanmış ek argümanlar.
- **Profiller:** `profiles/*.json`, Pydantic ile doğrulanır; panelin yönettiği anahtarlar (`server-port`, `rcon.*`) yasaktır.
- **Modrinth modları:** sürüm seçimi (release öncelikli), `required` bağımlılıklar, istemci-only atlama, SHA-512 doğrulaması; yalnızca panelin kurduğu dosyalar yönetilir (`.vulu-mods.json`).
- **Mod tarayıcı:** arama, tek tıkla kurulum, kurulu liste (profil / eklenen / bağımlılık / elle), açma-kapatma (`.jar.disabled`), silme.
- **Modpack:** `/modpacks` ile arama; yükleyici modpack'in tam sürümüyle kurulur; `env.server = unsupported` dosyalar atlanır; paralel doğrulamalı indirme; `overrides/` ve `server-overrides/`; yasaklı yol/uzantı denetimi.
- **Ayarlar:** port, RAM, Java, JVM, başlatma türü, jar/argüman dosyası; yaklaşık 25 doğrulamalı `server.properties` ayarı (panelin yönettiği anahtarlar hariç, ASCII dışı karakterler `\uXXXX` olarak yazılır); onaylı kalıcı silme (yalnızca `instances/<ad>`). Hepsi yalnızca sunucu kapalıyken.
- **Arayüz:** token/tema sistemi (3 tema), bileşen makroları, statik dosyalara `?v=` ile önbellek tazeleme.
- **Güvenlik:** `LocalGuardMiddleware` (Host, Origin, Sec-Fetch-Site), güvenlik başlıkları, `/docs` kapalı, JVM argümanı ve Java yolu doğrulaması, her sunucuya rastgele RCON port/şifresi.

## 3. Tasarım notları ve alınan dersler

| Konu | Karar / gerekçe |
|---|---|
| Süreç yönetimi | `asyncio.create_subprocess_exec`, Windows'ta `uvicorn --reload` ile `NotImplementedError` verir → `Popen` + okuyucu thread. |
| Yeniden yükleme | Minecraft'ın yazdığı dosyalar paneli sürekli yeniden başlatırdı → `run.py` yalnızca `app/` klasörünü izler. |
| Origin denetimi | `Referrer-Policy: no-referrer`, tarayıcıyı form POST'unda `Origin: null` göndermeye zorlar → politika `same-origin` yapıldı; `null` yalnızca `Sec-Fetch-Site: same-origin` ile kabul edilir. |
| Aikar bayrakları | `-XX:+UnlockExperimentalVMOptions`, deneysel bayraklardan **önce** gelmelidir (gerçek JVM ile doğrulandı). |
| RAM göstergesi | Süreç belleği (heap + JVM payı) gösterilir; `-Xmx` yalnızca heap'i sınırlar, bu yüzden ikisi ayrı yazılır. |
| TPS ayrıştırma | Bazı yükleyiciler yerel ayara göre `20,000 TPS` yazar (ondalık virgül) → ayrıştırıcı bunu tanır. |
| Statik dosyalar | Boyut gibi kritik stiller yalnızca CSS'e bağlı bırakılmaz; dosyalara değişme zamanı `?v=` olarak eklenir. |
| `.mrpack` dosya boyutu | Paket indeksindeki `fileSize` hatalı olabilir; **içeriği SHA-512 doğrular**, boyut yalnızca bilgidir. |
| Modpack yükleyicisi | Modpack'in istediği **tam** yükleyici sürümü kurulur (Fabric/Forge/NeoForge sürüm sabitleme). |
| Kurucular | Forge/NeoForge kurucusu üçüncü taraf koddur; yalnızca resmi Maven'den ve sağlama toplamı doğrulanarak çalıştırılır. |
| Router sırası | Genel `/api/instances/{id}/{action}` rotası 3 parçalı adresleri yuttuğu için `settings` router'ı `instances`'tan **önce** eklenir (`main.py`'de notludur). |
| Güvenli silme | Silmeden önce klasörün `instances/<ad>` doğrudan alt klasörü olduğu doğrulanır; veritabanındaki yol bozulsa bile proje kökü silinmez. |
| Test yaklaşımı | Dış servisler (Mojang, Adoptium, PaperMC, Fabric, Maven, Modrinth) sahte sunucularla test edilir; yine de gerçek ağ denemesi gerekir. |

## 4. Mimari

    app/
      main.py  config.py  db.py  ui.py  templating.py  security.py
      routers/   instances settings console java paper loader stats profiles mods modpacks
      services/  container (servis bağlantısı)
                 launcher (Java → modpack → yükleyici → modlar → başlat)
                 jobs download minecraft java_manager paper fabric forge modrinth modpack
                 jvm profiles properties propschema rcon stats process/{base,subprocess_backend}
    profiles/   runtimes/   instances/   data/

Başlatma akışı (`InstanceLauncher`): Java → (modpack paketi indir/oku → tam yükleyici sürümü) → yükleyici jar/kurucu → modpack dosyaları → profil modları → `server.properties` (port + RCON) → başlat.

### Veri modeli (`instances`)

`id, name, path, port, java_path, jar_file, mc_version, loader, java_major, launch_type, args_file, jvm_preset, jvm_args, ram_mb, rcon_port, rcon_password, profile_id, modpack_slug, modpack_version, status, created_at`

Sunucu klasöründeki panel dosyaları: `.vulu-jar.json` (yükleyici), `.vulu-mods.json` (modlar), `.vulu-modpack.json` (modpack), `user_jvm_args.txt` (`args-file` modunda her başlatmada yazılır).

### API özeti

    Sayfalar  /  /instances/new  /instances/{id}  /instances/{id}/mods
              /instances/{id}/settings  /instances/{id}/properties  /profiles  /modpacks
    Sunucu    POST /instances · /api/instances/{id}/start|stop|restart|kill
              /paper/update · /mods/update
    Konsol    WS /ws/instances/{id}/console        İş ilerlemesi  WS /ws/jobs/{id}
    İzleme    GET /api/stats · /api/instances/{id}/stats
    Katalog   GET /api/minecraft/versions[?loader=] · /api/java/resolve · /api/loader/resolve
              POST /api/loader/download · /api/java/install
    Modlar    GET /api/instances/{id}/mods/search|installed · POST .../mods/add|toggle|remove
    Modpack   GET /api/modpacks/search
    Ayarlar   POST /api/instances/{id}/settings · /properties · /destroy   (yalnızca sunucu kapalıyken)

## 5. Bilinen eksikler ve açık işler

- [~] **Forge kurucusu:** gerçek ortamda daha fazla denenmeli (NeoForge denendi). Forge Maven'in sağlama dosyası adresi (`.sha1`) canlıda doğrulanmadı; bulunamazsa doğrulama atlanır.
- [~] **Paper eklenti araması:** Modrinth'in eklentileri `project_type` olarak nasıl etiketlediği canlıda doğrulanmadı.
- [~] **NeoForge yıl bazlı sürümler (26.x):** Minecraft sürümü eşleştirmesi tahminidir.
- [~] **Ayarlar / `server.properties` / silme:** otomatik testleri geçti, gerçek ortamda doğrulanmalı.
- [ ] Minecraft sürümü ve yükleyici sonradan değiştirilemez (yedekle birlikte sürüm yükseltme).
- [ ] Modpack sürüm güncelleme yok; modpack kurulumu yalnızca ilk başlatmada yapılır.
- [ ] Profile bağlı olmayan sunucularda profil mod listesi yok (mod tarayıcıyla eklenebilir).
- [ ] Otomatik testler henüz depoda değil (sahte dış servislerle yazılmış testler `tests/` olarak eklenmeli).
- [ ] Panel kapanınca sunucular kapanır (`systemd`/`tmux` arka ucu planlanıyor).
- [ ] Giriş sistemi yok; bu nedenle internete açılamaz.

## 6. Planlanan işler

**Yakın dönem**
- Dosya yöneticisi (sunucu klasörüne kilitli, yol doğrulamalı) ve metin düzenleyici
- Yedekleme ve geri yükleme (yedekle-sonra-güncelle, sürüm yükseltme)
- Zamanlanmış restart/yedek (oyunculara uyarı mesajıyla)
- Java yönetimi (kurulu sürümler, disk kullanımı, silme)

**Orta dönem**
- Çökme analizcisi (`crash-reports/` ve `latest.log` kalıpları)
- Whitelist/OP yönetimi (UUID çözümleme yedeğiyle), Chunky ön üretim düğmesi, port erişim testi
- Discord webhook bildirimleri, mod güncelleme denetleyicisi, modpack sürüm güncelleme

**Uzun dönem**
- Giriş sistemi (argon2, oturum, hız sınırı, CSRF), çoklu kullanıcı ve yetkiler
- `SystemdBackend` / `TmuxBackend` (panel kapansa da sunucu açık kalsın)
- Alan adı + HTTPS ile yayınlama kılavuzu (Caddy), yedek saklama politikası
- Çoklu dil desteği, otomatik testler ve CI
