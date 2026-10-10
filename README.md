<p align="center">
  <img src="app/static/img/vl.svg" alt="vulu panel" width="112">
</p>

<h1 align="center">vulu Server Panel</h1>

<p align="center">
  Minecraft sunucularını tarayıcıdan kur, yönet ve izle.<br>
  <sub>Self-hosted Minecraft server panel · Türkçe / English</sub>
</p>

<p align="center">
  <a href="https://github.com/vuluvulu1/vulu-server-panel/releases/latest"><img src="https://img.shields.io/github/v/release/vuluvulu1/vulu-server-panel?label=s%C3%BCr%C3%BCm&color=c9a992&labelColor=1a1410" alt="Sürüm"></a>
  <a href="https://github.com/vuluvulu1/vulu-server-panel/releases"><img src="https://img.shields.io/github/downloads/vuluvulu1/vulu-server-panel/total?label=indirme&color=9c704c&labelColor=1a1410" alt="İndirme"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/lisans-AGPL--3.0-654127?labelColor=1a1410" alt="Lisans: AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-c9a992?logo=python&logoColor=white&labelColor=1a1410" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Minecraft-Java%20Edition-9c704c?labelColor=1a1410" alt="Minecraft Java Edition">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-654127?labelColor=1a1410" alt="Windows, Linux, macOS">
</p>

<p align="center">
  <a href="https://github.com/vuluvulu1/vulu-server-panel/releases/latest"><b>⬇ İndir</b></a> ·
  <a href="#kurulum">Kurulum</a> ·
  <a href="#özellikler">Özellikler</a> ·
  <a href="roadmap.md">Yol haritası</a>
</p>

---

**vulu Server Panel**, Minecraft sunucularını tek bir web arayüzünden kurmak, yönetmek ve izlemek için geliştirilen açık kaynaklı bir kontrol panelidir. Odak noktası **modlu sunucu kurulumunu kolaylaştırmaktır**: Java, sunucu jar'ı ve yükleyici (Paper / Fabric / Forge / NeoForge) otomatik bulunup kurulur; Modrinth'ten mod ve modpack tek tıkla eklenir.

> *English summary:* A self-hosted web panel for creating and managing Minecraft servers. It auto-installs Java and Paper/Fabric/Forge/NeoForge, installs mods and modpacks from Modrinth, and shows live console, CPU/RAM, players and TPS. FastAPI + Jinja2 + vanilla JS. The interface is available in Turkish and English (switch under Settings → Appearance, or on the sign-in page). Licensed under AGPL-3.0; the "vulu" name and VL logo are not covered by the license.

> **Durum:** Aktif geliştirme aşamasında (erken sürüm). Panel girişle korunur ve varsayılan olarak yalnızca bu bilgisayardan (`127.0.0.1`) açılır; istenirse aynı ev ağındaki cihazlara açılabilir. HTTPS henüz olmadığından doğrudan internete açılması önerilmez.

*Bu proje Mojang Studios, Microsoft, Modrinth, PaperMC, FabricMC, Minecraft Forge veya NeoForge ile bağlantılı değildir; yalnızca bu hizmetlerin herkese açık API'lerini kullanır.*

## Özellikler

- **Sunucu yönetimi:** oluşturma, başlatma, durdurma, yeniden başlatma, zorla kapatma; canlı konsol ve komut gönderme.
- **İzleme:** CPU/RAM, oyuncu listesi, TPS, çalışma süresi ve canlı grafikler.
- **Otomatik kurulum:** Java (Eclipse Temurin JRE), Paper, Fabric, Forge ve NeoForge; yüzdeli ilerleme çubuğu ve sağlama toplamı doğrulamasıyla.
- **Profiller:** `profiles/*.json` ile hazır ayar şablonları (JVM ayarı, RAM, `server.properties`, mod listesi); tek tıkla önceden doldurulmuş sunucu formu.
- **Mod tarayıcı:** Modrinth'te arama, bağımlılıklarıyla tek tıkla kurulum, kurulu modları açma/kapatma/silme.
- **Modpack içe aktarma:** Modrinth `.mrpack` paketlerinden sunucu kurulumu; yalnızca istemci dosyaları otomatik atlanır.
- **Ayarlar:** port, RAM, Java ve JVM ayarları; açıklamalı `server.properties` formu; onaylı kalıcı silme.
- **Dosya yöneticisi:** sunucu klasörünü gezme, metin dosyalarını düzenleme, yükleme/indirme, yeniden adlandırma, silme.
- **Yedekleme:** tam ya da yalnızca dünya yedeği (sunucu çalışırken de), indirme, geri yükleme (öncesinde otomatik güvenlik yedeği).
- **Zamanlama:** belirli gün ve saatlerde otomatik yeniden başlatma (oyunculara sohbetten geri sayımla) ve otomatik yedek (saklama sınırıyla).
- **Sunucu simgesi:** panelden resim yükleyerek `server-icon.png` (64×64) ayarlama.
- **Minecraft sürümünü değiştirme:** sunucu *Ayarlar* penceresinden yeni sürüm seçilir; önce otomatik tam yedek alınır, gereken Java yeniden seçilir, sunucu jar'ı/yükleyici bir sonraki başlatmada yeniden indirilir ve Modrinth'ten kurulan modlar yeni sürüme göre güncellenir. Sürüm düşürme ayrıca onay ister.
- **Oyuncular:** beyaz liste, OP, yasak ve atma; sunucu açıkken anında (RCON), kapalıyken dosyalar düzenlenerek.
- **Mod yardımcıları:** eksik mod bağımlılıklarının ve sunucuda gereksiz istemci modlarının tespiti; Modrinth'teki modlar için güncelleme denetimi ve tek tıkla güncelleme (eski dosyalar saklanır).
- **Çökme analizi:** sunucu çöktüğünde konsol ve crash raporu incelenip neden ve öneri seçilen dilde gösterilir (Java sürümü, bellek, port, eksik mod, istemci modu vb.).
- **playit.gg ile internete açma:** port yönlendirmesi gerekmeden sunucuyu arkadaşlarına açma; panel resmi playit programını indirir, doğrular ve çalıştırır, herkese açık adresi kopyalanabilir şekilde gösterir.
- **Bakım:** disk kullanımı özeti, kurulu Java sürümlerini görme/kurma/silme, indirme önbelleğini temizleme; yedeklerde isteğe bağlı otomatik temizleme (en fazla N yedek).
- **Arayüz:** adım adım yeni sunucu sihirbazı (boş / profilden / modpack'ten → yükleyici ve sürüm → ayarlar), sunucu resmi seçimi (seçilmezse vulu simgesi; oyundaki sunucu listesinde de görünür), açılır pencereler, kart görünümlü yedek özeti.
- **Temalar:** varsayılan **vulu** (logodaki kahve/kum paleti) ile **Açık**, **Neon** ve **Violet**; *Ayarlar → Görünüm*'den önizlemeli seçim. Yeni tema eklemek tek bir `.css` dosyasıdır.
- **Dil:** Türkçe (varsayılan) ve İngilizce. *Ayarlar → Görünüm*'den ya da giriş ekranından değiştirilir; konsol mesajları ve hata metinleri de seçilen dilde gelir.

## Gereksinimler

- Python 3.11 veya üstü (Windows'ta yoksa `baslat.bat` kurmayı önerir)
- İnternet bağlantısı (Java, sunucu jar'ları ve modlar ilk kullanımda indirilir)
- Windows, Linux veya macOS (geliştirme ve testler ağırlıklı olarak Windows üzerinde yapılmaktadır)

## Kurulum

**Kolay yol**

1. [Releases](https://github.com/vuluvulu1/vulu-server-panel/releases) sayfasından son sürümün **`vulu-panel-vX.Y.Z.zip`** dosyasını indirip bir klasöre çıkar (*Source code* dosyaları geliştiriciler içindir).
2. **Windows:** `baslat.bat` dosyasına çift tıkla.
   **Linux / macOS:** klasörde bir terminal açıp `bash baslat.sh` yaz.
3. İlk açılışta başlatıcı gerekli her şeyi kendisi kurar (birkaç dakika sürebilir), ardından panel tarayıcıda açılır. Sonraki açılışlar birkaç saniye sürer.

Başlatıcı penceresi açık kaldığı sürece panel çalışır; kapatmak için pencerede **Ctrl+C**'ye bas. Python bulunamazsa başlatıcı ne yapılacağını söyler; Windows'ta tek tuşla kurmayı önerir.

**Elle kurulum (geliştiriciler için)**

Windows / PowerShell:

    git clone https://github.com/vuluvulu1/vulu-server-panel.git
    cd vulu-server-panel
    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env
    python run.py --dev

Linux / macOS:

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    python run.py --dev

`--dev`, `app/` klasöründeki kod değiştikçe paneli kendiliğinden yeniden yükler; günlük kullanımda gerekmez. `--open` panel hazır olunca tarayıcıyı açar.

Panel varsayılan olarak http://127.0.0.1:8000 adresinde açılır. İlk açılışta yönetici hesabı oluşturulur: konsolda (ve `data/setup-code.txt` dosyasında) görünen **kurulum kodunu** kurulum sayfasına gir, kullanıcı adı ve parolanı belirle.

> `uvicorn ... --reload` yerine **`python run.py --dev`** kullanılmalıdır. Minecraft `instances/` klasörüne sürekli dosya yazdığı için tüm klasörü izleyen bir yeniden yükleyici paneli gereksiz yere yeniden başlatır; `run.py --dev` yalnızca `app/` klasörünü izler.

### Yapılandırma

Adres, port, iletişim bilgisi ve alan adları panelden de değiştirilebilir: *Ayarlar → Panel ayarları* (kayıt `data/panel-settings.json`, `.env`'deki değerlerin yerine geçer; ağ ayarları parola onayı ister, *Paneli yeniden başlat* düğmesiyle uygulanır). `.env` dosyasını doldurmak zorunlu değildir; yalnızca ilk değerler için kullanılır:

| Değişken | Açıklama |
|---|---|
| `PANEL_CONTACT` | İsteğe bağlı. PaperMC ve Modrinth'e istek başlığında iletişim bilgisi olarak gönderilir; boşsa projenin GitHub adresi kullanılır. |
| `PANEL_HOST` / `PANEL_PORT` | Dinlenen adres ve port (varsayılan `127.0.0.1:8000`). Aynı Wi-Fi'deki cihazlardan (ör. telefon) yönetmek için `PANEL_HOST=0.0.0.0`; bu durumda yalnızca özel ağ adresleriyle (192.168.x.x vb.) girilebilir. |
| `PANEL_ALLOWED_HOSTS` | Panele hangi alan adlarıyla erişilebileceği (virgülle ayrılmış). Yerelde boş bırakılır. |

## Hızlı başlangıç

1. **Boş sunucu:** *Sunucular → Yeni sunucu → Boş sunucu* → yükleyiciyi ve Minecraft sürümünü seçin → *Devam* → ad, port, RAM ve isteğe bağlı sunucu resmi → *Oluştur* → *Başlat*. Java ve sunucu jar'ı (Vanilla dahil) ilk başlatmada otomatik indirilir ve doğrulanır.
2. **Profille:** *Yeni sunucu → Profilden* → bir profil seçin. Form profildeki değerlerle dolar; profildeki modlar ilk başlatmada kurulur.
3. **Modpack ile:** *Yeni sunucu → Modpack'ten* → arayın ve seçin → *Oluştur* → *Başlat*. Yükleyici, sürüm, modlar ve ayarlar paketten gelir.
4. **Mod eklemek için:** sunucu sayfasında *"Modlar / Ekle"* → arayın → *Kur* (sunucu kapalıyken; sonra başlatın).
5. **Ayarlar:** sunucu sayfasında *"Ayarlar"* (port, RAM, Java, JVM) ve *"server.properties"* (zorluk, görüş mesafesi, whitelist…). Değişiklikler sunucu kapalıyken kaydedilir ve yeniden başlatınca geçerli olur.
6. **Dosyalar ve yedekler:** sunucu sayfasında *"Dosyalar"* ve *"Yedekler"*. Yedekler `data/backups/<sunucu>/` altında `.zip` olarak tutulur.
7. **Sürüm değiştirmek için:** *Ayarlar → Minecraft sürümü* → sürümü seçin → *Sürümü değiştir* (sunucu kapalıyken). İşlem öncesi otomatik yedek alınır.
8. **Silmek için:** *Ayarlar* sayfasının altındaki *"Tehlikeli bölge"* (dünya dahil kalıcı siler; onay için sunucu adı yazılır).

Sunucu oluştururken *Minecraft EULA* kutusu işaretlenirse panel `eula.txt` dosyasını sizin adınıza `eula=true` olarak yazar; bu kutuyu işaretlemeden önce [EULA](https://aka.ms/MinecraftEULA)'yı okuyun.

### Profil biçimi

`profiles/` klasörüne eklenen her `.json` dosyası bir profildir:

    {
      "id": "fabric-temel",
      "name": "Fabric Temel",
      "description": "Hafif modlar için temiz bir başlangıç.",
      "mc_version": "latest",
      "loader": "fabric",
      "jvm_preset": "aikar",
      "default_ram_gb": 4,
      "server_properties": { "view-distance": 8 },
      "mods": ["fabric-api", "lithium", "ferrite-core"]
    }

`mods`, Modrinth proje adresindeki adlardır. `mc_version: "latest"` en yeni sürümü seçer. Panelin kendisinin yönettiği anahtarlar (`server-port`, `rcon.*` vb.) profillerde kullanılamaz. Hatalı profil dosyaları `/profiles` sayfasında hata mesajıyla gösterilir.

## Güvenlik

Panel, çalıştığı bilgisayarda süreç başlatıp dosya yazdığı için güvenlik baştan düşünülmüştür:

- **Giriş:** tek yönetici hesabı; parolalar `scrypt` ile saklanır, oturum belirteçlerinin yalnızca özeti tutulur, çerez HttpOnly + SameSite=Strict; art arda hatalı girişte artan bekleme. İlk hesap yalnızca konsolda görünen tek kullanımlık kurulum koduyla oluşturulabilir.
- Varsayılan olarak yalnızca `127.0.0.1`'e bağlanır; *Ayarlar → Panel ayarları → Ev ağı* (ya da `PANEL_HOST=0.0.0.0`) ile ev ağına açılabilir. Bağlantı henüz şifrelenmediği (HTTP) için **paneli doğrudan internete açmayın**; Minecraft sunucusunu internete açmak için playit.gg entegrasyonunu kullanın.
- Tarayıcı kaynaklı saldırılara karşı Host/Origin/Sec-Fetch-Site denetimi (cross-site istekler, WebSocket ve DNS rebinding engellenir), clickjacking koruması; `/docs` kapalıdır.
- JVM argümanları beyaz listeyle doğrulanır (`-XX:OnError`, `-javaagent` gibi komut çalıştırabilenler yasaktır); özel Java yolu yalnızca `java`/`java.exe` olabilir. Panel hiçbir `run.bat` / `run.sh` çalıştırmaz.
- İndirilen her şey (Java, sunucu jar'ları, kurucular, modlar, modpack dosyaları) resmi adreslerden alınır ve SHA-256/SHA-512 ile doğrulanır; arşivlerde yol kaçışı engellenir.
- Modpack'lerde tehlikeli yollar (`../`, mutlak yol) ve çalıştırılabilir uzantılar (`.exe`, `.bat`, `.sh`, `.dll` vb.) atlanır; `eula.txt`'ye dokunulmaz.
- Arama sonuçları sayfaya düz metin olarak basılır; ikonlar yalnızca `modrinth.com` adreslerinden gösterilir.
- Dosya yöneticisi sunucu klasörüne kilitlidir (`..`, mutlak yol ve dışarı işaret eden bağlantılar engellenir); panelin kendi dosyaları salt okunurdur; `.exe`, `.bat`, `.sh` gibi çalıştırılabilir dosyalar yüklenemez. Yazma işlemleri yalnızca sunucu kapalıyken yapılır.
- Yedek geri yüklemede güvensiz yollar reddedilir ve yalnızca panelin oluşturduğu yedekler kabul edilir.
- Sunucular ekransız (headless) Java ile çalışır: mod ya da modpack kodu masaüstünde pencere veya tarayıcı açamaz.
- Ayar kaydetme, `server.properties` ve silme yalnızca sunucu kapalıyken çalışır. Silme yalnızca `instances/<ad>` klasörünü siler (konum doğrulanır).
- **RCON:** Minecraft, RCON'u tüm ağ arayüzlerinde dinler. Panel her sunucuya rastgele port ve şifre verir; güvenlik duvarı sorarsa **genel ağa izin vermeyin** ve bu portu yönlendirmeyin.

Bir güvenlik açığı bulursanız lütfen herkese açık bir *issue* yerine depo sahibine özel olarak bildirin (GitHub'daki *Security → Report a vulnerability* ya da profildeki iletişim bilgisi).

## Durum ve yol haritası

Ayrıntılı plan, tasarım notları ve açık işler: [`roadmap.md`](roadmap.md)

**Tamamlananlar**
- [x] Süreç yönetimi, canlı konsol, çökme tespiti
- [x] İzleme: CPU/RAM, oyuncu, TPS, grafikler
- [x] Java, Paper, Fabric, Forge, NeoForge otomatik kurulumu
- [x] Profiller, Modrinth mod kurulumu, mod tarayıcı, `.mrpack` içe aktarma
- [x] Sunucu ayarları, `server.properties` formu, güvenli silme
- [x] Dosya yöneticisi, yedekleme ve geri yükleme
- [x] Zamanlanmış yeniden başlatma/yedek, yedek saklama sınırı, sunucu simgesi, açılır pencere arayüzü
- [x] Arayüz yenilemesi: yeni sunucu sihirbazı, vulu teması ve logo, Ayarlar'da tema seçimi, panel ayarları
- [x] Ayarlar sayfası: disk kullanımı, Java yönetimi, önbellek temizleme
- [x] Minecraft sürüm yükseltme/düşürme (otomatik yedekle)
- [x] Eksik bağımlılık tespiti, çökme analizcisi, oyuncu yönetimi, mod güncelleme denetleyicisi
- [x] playit.gg entegrasyonu (gerçek ortamda doğrulama bekliyor)
- [x] Güvenlik katmanı (Host/Origin denetimi, girdi ve indirme doğrulaması)

**Planlananlar**
- [ ] Discord bildirimleri, Chunky düğmesi, modpack sürüm güncelleme
- [x] Giriş sistemi ve ev ağından erişim
- [ ] `systemd`/`tmux` desteği (panel kapansa da sunucular açık kalsın), HTTPS ile yayınlama
- [x] İngilizce arayüz ve çoklu dil altyapısı
- [x] Çift tıkla başlatıcılar (`baslat.bat` / `baslat.sh`) ve GitHub release paketi
- [ ] Otomatik testlerin depoya eklenmesi

## Proje yapısı

    baslat.bat / baslat.sh # çift tıkla başlatıcılar (kurulum + başlatma)
    tools/launcher.py      # başlatıcıların asıl işi: sanal ortam, paket kurulumu (ilerleme çubuğuyla)
    tools/build_release.py # release paketi (dist/vulu-panel-v<sürüm>.zip)
    .github/workflows/     # her release'te paketi otomatik oluşturup ekler
    run.py                 # python run.py [--dev] [--open]
    profiles/              # profil şablonları (.json)
    roadmap.md             # yol haritası ve tasarım notları
    app/
      main.py  config.py  db.py  ui.py  templating.py  security.py
      routers/             # instances, settings, files, backups, schedules, system, console, java, paper, loader,
                           # stats, profiles, mods, modpacks
      services/            # process/ (süreç yönetimi), launcher, jobs, download,
                           # minecraft, java_manager, paper, fabric, forge,
                           # jvm, modrinth, modpack, profiles, rcon, stats,
                           # properties, propschema, files, backup, scheduler, system
      templates/  static/  # arayüz (css/themes, js, vendor/chart.js)
    data/                  # panel.db ve önbellekler       (git'e girmez)
    instances/             # sunucu klasörleri             (git'e girmez)
    runtimes/              # indirilen Java'lar            (git'e girmez)

**Teknoloji:** Python, FastAPI, Jinja2, Bootstrap 5, düz JavaScript, SQLite, `httpx`, `psutil`, Chart.js.

## Arayüzü özelleştirme

| Yapılmak istenen | Bakılacak yer |
|---|---|
| Renkleri değiştirmek | `app/static/css/themes/<tema>.css` (varsayılan: `vulu.css`) |
| Yeni tema eklemek | `themes/` altına yeni bir `.css` dosyası (ilk satır: `/* name: Ad \| mode: dark */`) |
| Köşe yuvarlaklığı, font, boşluk | `app/static/css/tokens.css` |
| Bileşen görünümü (kart, buton…) | `app/static/css/components.css` |
| Bileşen HTML'i (kart, rozet, kutucuk…) | `app/templates/components/ui.html` |
| Menüye sayfa eklemek, marka adı, varsayılan tema | `app/ui.py` |
| Logo ve varsayılan sunucu simgesi | `app/static/img/vl.svg`, `app/static/img/default-icon.png` (64×64 PNG) |
| Genel yerleşim | `app/templates/base.html` ve `partials/` |
| Kişisel ince ayar | `app/static/css/custom.css` |
| Çeviriyi düzeltmek, yeni dil eklemek | `app/i18n/<dil>.json` (anahtar: Türkçe metin, değer: çeviri) ve `app/i18n/__init__.py` içindeki `LANGS` |

Kural: `components.css` içinde sabit renk yazılmaz, yalnızca `var(--...)` kullanılır. Hazır temalar: **vulu** (varsayılan), **Açık**, **Neon**, **Violet**. Tema seçimi *Ayarlar → Görünüm*'den yapılır ve tarayıcıda saklanır.

## Bilinen kısıtlar

- Panel kapanırsa sunucular da kapanır (kapanırken `stop` komutuyla düzgünce durdurulur). Bağımsız çalışma planlanmaktadır.
- Geliştirme modunda (`python run.py --dev`) `app/` içindeki bir Python dosyası değiştirilirse panel yeniden başlar ve çalışan sunucular durur.
- Yükleyici (Paper/Fabric/Forge…) sunucu oluşturulduktan sonra değiştirilemez; Minecraft sürümü değiştirilebilir ama modpack ile kurulan sunucularda değiştirilemez. Elle eklenen modlar sürüm değişiminde güncellenmez.
- Mod ekleme/silme/açıp kapatma ve ayar değişiklikleri yalnızca sunucu kapalıyken yapılabilir.
- NeoForge yalnızca Minecraft 1.20.2 ve üstünde desteklenir. Yalnızca Modrinth kaynağı desteklenir (CurseForge desteklenmez).
- Modpack kurulumu yalnızca ilk başlatmada yapılır; modpack sürüm güncellemesi henüz yoktur. Modrinth'te bulunmayan modlar içeren paketlerde bu modlar eksik kalır (bazı paketler bunları indirmek için yardımcı bir mod içerir; sunucuda pencere açamadığı için çalışmaz).
- RAM kutucuğu sürecin gerçek bellek kullanımını gösterir; `-Xmx` yalnızca heap'i sınırladığından değer, heap limitinden %10-25 yüksek olabilir (normaldir).

## Katkıda bulunma

- **Hata bildirimi:** bir *issue* açın; panelin gösterdiği hata mesajını, Minecraft sürümünü, yükleyiciyi ve işletim sisteminizi ekleyin (şifre ve kişisel bilgileri çıkarın).

## Lisans

[AGPL-3.0](LICENSE). Paneli özgürce kullanabilir, değiştirebilir ve dağıtabilirsiniz; değiştirilmiş bir sürümü dağıtan ya da web üzerinden hizmet olarak sunan, kaynak kodunu da aynı lisansla açmalıdır.

"vulu" adı ve VL logosu lisansa dahil değildir: kendi sürümünüzü dağıtırken farklı bir ad ve logo kullanın.
