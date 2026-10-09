# Yol Haritası

Bu belge, vulu Server Panel'in mevcut durumunu, tasarım kararlarını ve planlanan işleri özetler. Katkıda bulunmak isteyenler için bir başlangıç noktasıdır.

Gösterim: `[x]` tamamlandı · `[~]` kısmen / gerçek ortamda daha fazla doğrulama gerekiyor · `[ ]` planlanıyor

## 1. Genel durum

| Alan | Durum |
|---|---|
| Süreç yönetimi, canlı konsol | ✅ |
| İzleme (CPU/RAM, oyuncu, TPS) | ✅ |
| Java, Paper, Fabric, Forge, NeoForge kurulumu | ✅ gerçek ortamda doğrulandı |
| Profiller, Modrinth mod kurulumu, mod tarayıcı | ✅ |
| Modpack (`.mrpack`) içe aktarma | ✅ gerçek ortamda doğrulandı (Modrinth'te bulunmayan modlar içeren paketlerde eksik mod kalabilir) |
| Sunucu ayarları, `server.properties` formu, silme | ✅ gerçek ortamda doğrulandı |
| Dosya yöneticisi, yedekleme/geri yükleme | ✅ gerçek ortamda doğrulandı |
| Zamanlanmış restart/yedek, yedek saklama sınırı | 🔶 kod ve otomatik testler tamam, gerçek ortamda doğrulama bekliyor |
| Ayarlar sayfası (disk, Java yönetimi, önbellek) | ✅ gerçek ortamda doğrulandı |
| Yedek otomatik temizleme | 🔶 kod ve otomatik testler tamam, gerçek ortamda doğrulama bekliyor |
| Vanilla jar indirme | ✅ gerçek ortamda doğrulandı |
| Minecraft sürüm yükseltme | 🔶 düzeltme sonrası yeniden denenecek (Java sürümü güncellenmeden kalabiliyordu) |
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

- **Dosya yöneticisi:** `services/files.py` — tüm yollar `safe_path` ile sunucu klasörüne kilitli (resolve + `is_relative_to`, dışarı işaret eden bağlantılar gizlenir), panel dosyaları salt okunur, 2 MB'a kadar metin düzenleme, 512 MB'a kadar yükleme, çalıştırılabilir uzantılar engelli; yazma yalnızca sunucu kapalıyken.
- **Yedekleme:** `services/backup.py` — `data/backups/<ad>/<ad>_<full|world>_<tarih>[_not].zip`, üst veri zip yorumunda; çalışırken `save-off` + `save-all flush` → zip → `save-on`; geri yüklemeden önce otomatik güvenlik yedeği, yol doğrulaması ve yalnızca panel yedeklerinin kabulü. Sunucu silinince yedekler korunur.

- **Zamanlama:** `services/scheduler.py` + `schedules` tablosu — günlük saat ve gün seçimi (yerel saat), 15 sn'de bir denetim, aynı dilimde tek çalışma (`last_run`), yeniden başlatmada 30/15/10/5/3/2/1 dk geri sayım (`say`), yedekte `auto:zamanli` notu ve son N yedeği tutma (elle alınanlara dokunulmaz). Panel kapalıyken kaçırılan görevler sonradan çalışmaz. Sunucu silinince zamanlamaları da silinir.
- **Arayüz:** sunucu sayfasındaki sekmeler açılır pencerede (`?embed=1`, aynı kaynak iframe; `X-Frame-Options: SAMEORIGIN`), kayıtta pencere kapanır ve bildirim gösterilir; sunucu simgesi tarayıcıda 64×64 PNG'ye çevrilir, sunucu tarafında PNG imzası ve boyutu doğrulanır.

- **Ayarlar (sistem) sayfası:** `/settings` — disk kullanımı (sunucular, yedekler, Java, önbellek), kurulu Java'lar (boyut, kullanan sunucular; çalışan bir sunucu kullanıyorsa silme engellenir), eksik Java'lar, önbellek temizleme (yalnızca `data/cache/<tür>` dosyaları; indirme sürerken engellenir).
- **Sürüm yükseltme:** `services/upgrade.py` — yalnızca sunucu kapalıyken ve başka iş yokken; modpack sunucularında ve aynı/bilinmeyen sürümde engellenir. Akış: tam yedek (`auto:surum-oncesi`) → `.vulu-jar.json` ve eski jar silinir (yalnızca `jar` başlatma türünde) → `mc_version` ve (panel yönetiyorsa) `java_major` güncellenir → `.vulu-mods.json`'daki Modrinth modları yeni sürüme göre yeniden kurulur; elle eklenen modlar için uyarı verilir. Sürüm düşürme `confirm_downgrade` ister. Yükleyici bir sonraki başlatmada yeniden kurulur.
- **Vanilla:** `services/vanilla.py` — sunucu jar'ı Mojang sürüm verisinden (`downloads.server`), yalnızca Mojang alan adlarından HTTPS ile ve SHA-1 doğrulamasıyla indirilir; `data/cache/vanilla/` içinde önbelleklenir.
- **Bağımlılık denetimi:** `services/modcheck.py` — mod jar'larının üst verisi (`fabric.mod.json`, `quilt.mod.json`, `mods.toml`, `neoforge.mods.toml`, iç içe jar'lar dahil) yalnızca okunarak eksik zorunlu bağımlılıklar ve istemciye özel modlar bulunur; her başlatmada konsola, Modlar penceresinde ayrıntılı olarak gösterilir (eksik ada tıklayınca Modrinth'te aranır). Sürüm aralıkları denetlenmez; boyut/sayı sınırları zip bombalarına karşıdır.
- **Çökme analizcisi:** `services/crash.py` — sunucu çöktüğünde (ya da açılmadan kapandığında) konsolun son satırları ve bu çalıştırmada yazılan crash raporu okunur; Java sürümü, bellek, port, EULA, dünya kilidi/bozulması, eksik bağımlılık (Fabric/Forge/NeoForge), istemci modu, Mixin, çift mod, donma (watchdog) ve raporun şüphelendiği modlar için Türkçe neden + öneri konsola ve sunucu sayfasındaki karta yazılır.
- **Oyuncular:** `services/players.py` — beyaz liste, OP, yasak, atma ve beyaz liste anahtarı. Sunucu çalışıyorsa RCON komutu (anında geçerli), kapalıysa `whitelist.json`/`ops.json`/`banned-players.json` atomik düzenlenir; UUID `online-mode=true` ise Mojang'dan, değilse çevrimdışı kuralla (`OfflinePlayer:<ad>`, MD5/v3) hesaplanır. Ad `^[A-Za-z0-9_]{1,16}$` ile doğrulanır, yasak nedeni tek satıra indirgenir (komut enjeksiyonu yok).
- **Mod güncelleme denetleyicisi:** `services/modupdate.py` — klasördeki her jar'ın SHA-512'si Modrinth'e sorulur (`/version_files` + `/version_files/update`), böylece panelin kurduğu, modpack'ten gelen ve elle eklenen modlar birlikte denetlenir. Güncellemede istemci yalnızca dosya adı gönderir, adres/hash sunucuda yeniden alınır; yeni dosya yalnızca Modrinth CDN'inden SHA-512 ile indirilir; eski dosya `.vulu-old-mods/<tarih>/` klasörüne taşınır (son 3 saklanır), kapalı mod kapalı kalır. Beta/alfa sürümler varsayılan seçili değildir.
- **playit.gg:** `services/playit.py` — resmi playit programının hizmet kurmadan çalışan 0.17.1 sürümü GitHub'dan indirilir ve sabit SHA-256 ile doğrulanır (her başlatmada yeniden); bağlama `/claim/setup` + `/claim/exchange` ile (kullanıcı `playit.gg/claim/<kod>` adresinde onaylar), anahtar `data/playit/secret.txt` içinde tutulur ve tarayıcıya gönderilmez; program panelin alt süreci olarak çalışır, çökerse yeniden başlatılır. Tüneller `/agents/rundata` ile okunup yerel port eşleşmesiyle sunucuya bağlanır; "İnternete aç" `/tunnels/create` (Minecraft Java, 127.0.0.1:<port>) dener, olmazsa site üzerinden elle oluşturma tarif edilir. Yalnızca Minecraft portu açılır; açmadan önce beyaz liste/online-mode uyarısı verilir.
- **Başlatma güvenceleri:** Java her zaman ekransız modda başlar (mod kodu pencere ya da tarayıcı açamaz; ek argümanlarla kapatılamaz); başlatmadan önce boş RAM denetlenir; panelin yönettiği Java, Minecraft sürümünün istediğinden eskiyse otomatik yükseltilir; bellek yetmezliği ve uyumsuz Java çökmelerinde konsola Türkçe neden yazılır.
- **Yedek otomatik temizleme:** sunucu başına `backup_limit`; her yeni yedekten sonra en eski yedekler silinir (yeni alınan korunur). Yedekler oluşturulma zamanına göre sıralanır (aynı saniyede alınanlar dosya zamanına göre).

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
| Yeniden başlatma yarışı | Süreç bittikten hemen sonra durum bir an "durduruluyor" kalıyordu ve yeniden başlatma "zaten çalışıyor" hatası veriyordu → `restart` durumun "durdu" olmasını bekler. |
| Güvenli silme | Silmeden önce klasörün `instances/<ad>` doğrudan alt klasörü olduğu doğrulanır; veritabanındaki yol bozulsa bile proje kökü silinmez. |
| Test yaklaşımı | Dış servisler (Mojang, Adoptium, PaperMC, Fabric, Maven, Modrinth) sahte sunucularla test edilir; yine de gerçek ağ denemesi gerekir. |

## 4. Mimari

    app/
      main.py  config.py  db.py  ui.py  templating.py  security.py
      routers/   instances settings files backups schedules system console java paper loader stats profiles mods modpacks
      services/  container (servis bağlantısı)
                 launcher (Java → modpack → yükleyici → modlar → başlat)
                 jobs download minecraft java_manager paper fabric forge modrinth modpack
                 jvm profiles properties propschema files backup scheduler system rcon stats process/{base,subprocess_backend}
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
    Dosyalar  GET  /api/instances/{id}/files/list|read|download · POST .../files/write|mkdir|rename|delete|upload
    Yedekler  GET  /backups · /api/instances/{id}/backups/list|download · POST .../backups/create|restore|delete

## 5. Bilinen eksikler ve açık işler

- [~] **Forge kurucusu:** 1.20.1 ile gerçek ortamda çalıştı. Forge Maven'in sağlama dosyası adresi (`.sha1`) bulunamazsa doğrulama atlanır.
- [~] **Paper eklenti araması:** Modrinth'in eklentileri `project_type` olarak nasıl etiketlediği canlıda doğrulanmadı.
- [~] **NeoForge yıl bazlı sürümler (26.x):** Minecraft sürümü eşleştirmesi tahminidir.
- [~] **Modrinth dışı modlar:** bazı modpack'ler Modrinth'te bulunmayan modlar için oyuncuya indirme penceresi açan yardımcı modlar içerir. Sunucular ekransız (`-Djava.awt.headless=true`) çalıştığı için pencere açılmaz, ancak bu modlar eksik kalır; eksikler başlatmada bağımlılık denetimiyle tespit edilip gösterilir.
- [ ] Yükleyici sonradan değiştirilemez; modpack sunucularında Minecraft sürümü değiştirilemez; elle eklenen modlar sürüm değişiminde güncellenmez.
- [ ] Modpack sürüm güncelleme yok; modpack kurulumu yalnızca ilk başlatmada yapılır.
- [ ] Profile bağlı olmayan sunucularda profil mod listesi yok (mod tarayıcıyla eklenebilir).
- [ ] Otomatik testler henüz depoda değil (sahte dış servislerle yazılmış testler `tests/` olarak eklenmeli).
- [ ] Panel kapanınca sunucular kapanır (`systemd`/`tmux` arka ucu planlanıyor).
- [ ] Giriş sistemi yok; bu nedenle internete açılamaz.

## 6. Planlanan işler

**Yakın dönem**
- Gerçek ortam denemeleri: zamanlama, yedek otomatik temizleme, oyuncu yönetimi, mod güncelleme, çökme analizcisi, playit.gg
- Otomatik testlerin `tests/` klasörüne taşınması

**Orta dönem**
- Chunky ön üretim düğmesi, port erişim testi
- Discord webhook bildirimleri, modpack sürüm güncelleme

**Uzun dönem**
- Giriş sistemi (argon2, oturum, hız sınırı, CSRF), çoklu kullanıcı ve yetkiler
- `SystemdBackend` / `TmuxBackend` (panel kapansa da sunucu açık kalsın)
- Alan adı + HTTPS ile yayınlama kılavuzu (Caddy), yedek saklama politikası
- Çoklu dil desteği, otomatik testler ve CI
