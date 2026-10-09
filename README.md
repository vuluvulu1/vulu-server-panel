# vulu Server Panel

**vulu Server Panel**, Minecraft sunucularını tek bir web arayüzünden kurmak, yönetmek ve izlemek için geliştirilen açık kaynaklı bir kontrol panelidir. Odak noktası **modlu sunucu kurulumunu kolaylaştırmaktır**: Java, sunucu jar'ı ve yükleyici (Paper / Fabric / Forge / NeoForge) otomatik bulunup kurulur; Modrinth'ten mod ve modpack tek tıkla eklenir.

> *English summary:* A self-hosted web panel for creating and managing Minecraft servers. It auto-installs Java and Paper/Fabric/Forge/NeoForge, installs mods and modpacks from Modrinth, and shows live console, CPU/RAM, players and TPS. FastAPI + Jinja2 + vanilla JS. The interface is currently in Turkish.

> **Durum:** Aktif geliştirme aşamasında (erken sürüm). Panel şu an yalnızca yerel kullanım (`127.0.0.1`) için tasarlanmıştır ve **henüz giriş sistemi yoktur**; internete açılmamalıdır.

*Bu proje Mojang Studios, Microsoft, Modrinth, PaperMC, FabricMC, Minecraft Forge veya NeoForge ile bağlantılı değildir; yalnızca bu hizmetlerin herkese açık API'lerini kullanır.*

## Özellikler

- **Sunucu yönetimi:** oluşturma, başlatma, durdurma, yeniden başlatma, zorla kapatma; canlı konsol ve komut gönderme.
- **İzleme:** CPU/RAM, oyuncu listesi, TPS, çalışma süresi ve canlı grafikler.
- **Otomatik kurulum:** Java (Eclipse Temurin JRE), Paper, Fabric, Forge ve NeoForge; yüzdeli ilerleme çubuğu ve sağlama toplamı doğrulamasıyla.
- **Profiller:** `profiles/*.json` ile hazır ayar şablonları (JVM ayarı, RAM, `server.properties`, mod listesi); tek tıkla önceden doldurulmuş sunucu formu.
- **Mod tarayıcı:** Modrinth'te arama, bağımlılıklarıyla tek tıkla kurulum, kurulu modları açma/kapatma/silme.
- **Modpack içe aktarma:** Modrinth `.mrpack` paketlerinden sunucu kurulumu; yalnızca istemci dosyaları otomatik atlanır.
- **Ayarlar:** port, RAM, Java ve JVM ayarları; açıklamalı `server.properties` formu; onaylı kalıcı silme.
- **Özelleştirilebilir arayüz:** token tabanlı tema sistemi (3 hazır tema); yeni tema eklemek tek bir `.css` dosyasıdır.

## Gereksinimler

- Python 3.11 veya üstü
- İnternet bağlantısı (Java, sunucu jar'ları ve modlar ilk kullanımda indirilir)
- Windows, Linux veya macOS (geliştirme ve testler ağırlıklı olarak Windows üzerinde yapılmaktadır)

## Kurulum

Windows / PowerShell:

    git clone <depo-adresi>
    cd vulu-server-panel
    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env
    python run.py

Linux / macOS:

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    python run.py

Panel varsayılan olarak http://127.0.0.1:8000 adresinde açılır.

> `uvicorn ... --reload` yerine **`python run.py`** kullanılmalıdır. Minecraft `instances/` klasörüne sürekli dosya yazdığı için tüm klasörü izleyen bir yeniden yükleyici paneli gereksiz yere yeniden başlatır; `run.py` yalnızca `app/` klasörünü izler.

### Yapılandırma (`.env`)

| Değişken | Açıklama |
|---|---|
| `PANEL_CONTACT` | **Gereklidir.** PaperMC ve Modrinth, istek başlığında iletişim bilgisi bekler: e-posta adresi veya proje/GitHub adresi. |
| `PANEL_HOST` / `PANEL_PORT` | Dinlenen adres ve port (varsayılan `127.0.0.1:8000`). Giriş sistemi gelene kadar `PANEL_HOST` değiştirilmemelidir. |
| `PANEL_ALLOWED_HOSTS` | Panele hangi alan adlarıyla erişilebileceği (virgülle ayrılmış). Yerelde boş bırakılır. |
| `PANEL_SECRET_KEY` | Şimdilik kullanılmıyor (giriş sistemi için ayrılmıştır). |

## Hızlı başlangıç

1. **Boş sunucu:** *Sunucular → Yeni sunucu* → Minecraft sürümü ve yükleyiciyi seçin → *Oluştur* → *Başlat*. Java ve sunucu jar'ı ilk başlatmada otomatik indirilir.
2. **Profille:** *Profiller* sayfasında bir kartta *"Bu profille sunucu oluştur"*. Form profildeki değerlerle dolar; profildeki modlar ilk başlatmada kurulur.
3. **Modpack ile:** *Modpack'ler* sayfasında arayın → *"Sunucu oluştur"* → *Başlat*. Yükleyici, modlar ve ayarlar paketten gelir.
4. **Mod eklemek için:** sunucu sayfasında *"Modlar / Ekle"* → arayın → *Kur* (sunucu kapalıyken; sonra başlatın).
5. **Ayarlar:** sunucu sayfasında *"Ayarlar"* (port, RAM, Java, JVM) ve *"server.properties"* (zorluk, görüş mesafesi, whitelist…). Değişiklikler sunucu kapalıyken kaydedilir ve yeniden başlatınca geçerli olur.
6. **Silmek için:** *Ayarlar* sayfasının altındaki *"Tehlikeli bölge"* (dünya dahil kalıcı siler; onay için sunucu adı yazılır).

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

`mods`, Modrinth proje adresindeki adlardır. `mc_version: "latest"` en yeni sürümü seçer. Panelin kendisinin yönettiği anahtarlar (`server-port`, `rcon.*` vb.) profillerde kullanılamaz. Hatalı profil dosyaları *Profiller* sayfasında hata mesajıyla gösterilir.

## Güvenlik

Panel, çalıştığı bilgisayarda süreç başlatıp dosya yazdığı için güvenlik baştan düşünülmüştür:

- Yalnızca `127.0.0.1`'e bağlanır. **Giriş sistemi henüz yoktur; paneli internete açmayın.**
- Tarayıcı kaynaklı saldırılara karşı Host/Origin/Sec-Fetch-Site denetimi (cross-site istekler, WebSocket ve DNS rebinding engellenir), clickjacking koruması; `/docs` kapalıdır.
- JVM argümanları beyaz listeyle doğrulanır (`-XX:OnError`, `-javaagent` gibi komut çalıştırabilenler yasaktır); özel Java yolu yalnızca `java`/`java.exe` olabilir. Panel hiçbir `run.bat` / `run.sh` çalıştırmaz.
- İndirilen her şey (Java, sunucu jar'ları, kurucular, modlar, modpack dosyaları) resmi adreslerden alınır ve SHA-256/SHA-512 ile doğrulanır; arşivlerde yol kaçışı engellenir.
- Modpack'lerde tehlikeli yollar (`../`, mutlak yol) ve çalıştırılabilir uzantılar (`.exe`, `.bat`, `.sh`, `.dll` vb.) atlanır; `eula.txt`'ye dokunulmaz.
- Arama sonuçları sayfaya düz metin olarak basılır; ikonlar yalnızca `modrinth.com` adreslerinden gösterilir.
- Ayar kaydetme, `server.properties` ve silme yalnızca sunucu kapalıyken çalışır. Silme yalnızca `instances/<ad>` klasörünü siler (konum doğrulanır).
- **RCON:** Minecraft, RCON'u tüm ağ arayüzlerinde dinler. Panel her sunucuya rastgele port ve şifre verir; güvenlik duvarı sorarsa **genel ağa izin vermeyin** ve bu portu yönlendirmeyin.

Bir güvenlik açığı bulursanız lütfen herkese açık bir *issue* yerine depo sahibine özel olarak bildirin (GitHub'daki *Security → Report a vulnerability* ya da profildeki iletişim bilgisi).

## Durum ve yol haritası

Ayrıntılı plan, tasarım notları ve açık işler: [`docs/ROADMAP.md`](docs/ROADMAP.md)

**Tamamlananlar**
- [x] Süreç yönetimi, canlı konsol, çökme tespiti
- [x] İzleme: CPU/RAM, oyuncu, TPS, grafikler
- [x] Java, Paper, Fabric, Forge, NeoForge otomatik kurulumu
- [x] Profiller, Modrinth mod kurulumu, mod tarayıcı, `.mrpack` içe aktarma
- [x] Sunucu ayarları, `server.properties` formu, güvenli silme
- [x] Güvenlik katmanı (Host/Origin denetimi, girdi ve indirme doğrulaması)

**Planlananlar**
- [ ] Dosya yöneticisi, yedekleme/geri yükleme, zamanlanmış restart, Java yönetimi
- [ ] Çökme analizcisi, whitelist/OP yönetimi, Chunky düğmesi, Discord bildirimleri
- [ ] Giriş sistemi, `systemd`/`tmux` desteği (panel kapansa da sunucular açık kalsın), HTTPS ile yayınlama
- [ ] Otomatik testlerin depoya eklenmesi, çoklu dil desteği

## Proje yapısı

    run.py                 # python run.py
    profiles/              # profil şablonları (.json)
    docs/                  # yol haritası ve notlar
    app/
      main.py  config.py  db.py  ui.py  templating.py  security.py
      routers/             # instances, settings, console, java, paper, loader,
                           # stats, profiles, mods, modpacks
      services/            # process/ (süreç yönetimi), launcher, jobs, download,
                           # minecraft, java_manager, paper, fabric, forge,
                           # jvm, modrinth, modpack, profiles, rcon, stats,
                           # properties, propschema
      templates/  static/  # arayüz (css/themes, js, vendor/chart.js)
    data/                  # panel.db ve önbellekler       (git'e girmez)
    instances/             # sunucu klasörleri             (git'e girmez)
    runtimes/              # indirilen Java'lar            (git'e girmez)

**Teknoloji:** Python, FastAPI, Jinja2, Bootstrap 5, düz JavaScript, SQLite, `httpx`, `psutil`, Chart.js.

## Arayüzü özelleştirme

| Yapılmak istenen | Bakılacak yer |
|---|---|
| Renkleri değiştirmek | `app/static/css/themes/<tema>.css` |
| Yeni tema eklemek | `themes/` altına yeni bir `.css` dosyası (ilk satır: `/* name: Ad \| mode: dark */`) |
| Köşe yuvarlaklığı, font, boşluk | `app/static/css/tokens.css` |
| Bileşen görünümü (kart, buton…) | `app/static/css/components.css` |
| Bileşen HTML'i (kart, rozet, kutucuk…) | `app/templates/components/ui.html` |
| Menüye sayfa eklemek, marka adı | `app/ui.py` |
| Genel yerleşim | `app/templates/base.html` ve `partials/` |
| Kişisel ince ayar | `app/static/css/custom.css` |

Kural: `components.css` içinde sabit renk yazılmaz, yalnızca `var(--...)` kullanılır. Hazır temalar: **vulu Violet**, **Neon Cyberpunk**, **Açık**.

## Bilinen kısıtlar

- Panel kapanırsa sunucular da kapanır (kapanırken `stop` komutuyla düzgünce durdurulur). Bağımsız çalışma planlanmaktadır.
- Sunucu çalışırken `app/` içindeki bir Python dosyası değiştirilirse panel yeniden başlar ve sunucu durur; geliştirme sırasında sunucuyu kapatın.
- Minecraft sürümü ve yükleyici, sunucu oluşturulduktan sonra değiştirilemez (sürüm yükseltme yedekleme ile birlikte planlanmaktadır).
- Mod ekleme/silme/açıp kapatma ve ayar değişiklikleri yalnızca sunucu kapalıyken yapılabilir.
- NeoForge yalnızca Minecraft 1.20.2 ve üstünde desteklenir. Yalnızca Modrinth kaynağı desteklenir (CurseForge desteklenmez).
- Modpack kurulumu yalnızca ilk başlatmada yapılır; modpack sürüm güncellemesi henüz yoktur.
- RAM kutucuğu sürecin gerçek bellek kullanımını gösterir; `-Xmx` yalnızca heap'i sınırladığından değer, heap limitinden %10-25 yüksek olabilir (normaldir).

## Katkıda bulunma

Katkılar memnuniyetle karşılanır:

- **Hata bildirimi:** bir *issue* açın; panelin gösterdiği hata mesajını, Minecraft sürümünü, yükleyiciyi ve işletim sisteminizi ekleyin (şifre ve kişisel bilgileri çıkarın).
- **Profil paylaşımı:** işe yarayan `profiles/*.json` dosyalarınızı *pull request* ile gönderebilirsiniz.
- **Çeviri ve arayüz:** arayüz şu an Türkçedir; çoklu dil desteği için yardım aranıyor.
- **Kod:** büyük değişikliklerden önce bir *issue* ile konuşmak iyi olur. Yeni dış indirme kaynakları eklerken sağlama toplamı doğrulaması ve adres beyaz listesi zorunludur (bkz. `app/services/download.py`, `modrinth.py`).

## Lisans

Bu depo için henüz bir lisans eklenmemiştir.
