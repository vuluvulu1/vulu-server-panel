# vulu Server Panel — Yol Haritası

> Crafty Controller'a alternatif olarak geliştirilen, Minecraft sunucularının web paneli üzerinden yönetilmesini ve modlu sunucu kurulumunun kolaylaştırılmasını amaçlayan bir kontrol paneli.
>
> **Son güncelleme:** 2 Ekim 2026

Durum göstergeleri:

- `[x]` Tamamlandı
- `[~]` Kısmen tamamlandı
- `[ ]` Planlandı

---

## 0. Güncel Durum

| Faz | Durum |
|---|---|
| Faz 0 — Temel yapı | ✅ Tamamlandı |
| Faz 1 — Sunucu yönetimi ve canlı konsol | ✅ Tamamlandı ve gerçek Paper sunucusuyla doğrulandı |
| Faz 2 — İzleme | ✅ Kod tamamlandı, gerçek sunucuyla doğrulama yapıldı |
| Faz 3 — Profil ve modlu sunucu sistemi | 🔶 Devam ediyor |
| Faz 4 — Dosya, mod ve yedek yönetimi | ⏳ Başlanmadı |
| Faz 5 — Yardımcı özellikler | ⏳ Başlanmadı |
| Faz 6 — Yayına alma | ⏳ Başlanmadı |

### Tamamlanan temel özellikler

- Java sürümünün otomatik tespiti ve kurulumu
- Java indirme ve SHA-256 doğrulaması
- Paper sürüm/build seçimi ve kurulumu
- Paper build önbelleği ve güncelleme
- Sunucu oluşturma ve yönetme
- Başlatma, durdurma, yeniden başlatma ve zorla kapatma
- Çökme tespiti
- WebSocket tabanlı canlı konsol
- Konsoldan komut gönderme
- CPU/RAM izleme
- Oyuncu ve TPS bilgileri
- Çalışma süresi
- Chart.js grafikleri
- Tema sistemi
- Temel güvenlik kontrolleri

---

## 1. Amaç ve Kapsam

### Ana hedef

Minecraft sunucularını tek bir web panelinden yönetmek:

- Sunucu oluşturma
- Başlatma / durdurma
- Canlı konsol
- Kaynak kullanımı ve sunucu durumu
- Dosya ve mod yönetimi
- Yedekleme ve geri yükleme
- Sunucu ayarları

### Temel fark

vulu Launcher'daki mod paketi profillerini panel içerisinde kullanılabilir hale getirerek, hazır bir profil üzerinden modlu Minecraft sunucusu kurulmasını sağlamak.

Hedeflenen akış:

```text
Profil seçimi
    ↓
Minecraft sürümü
    ↓
Gerekli Java
    ↓
Sunucu yazılımı
    ↓
Modlar ve yapılandırma
    ↓
İlk başlatma
    ↓
Çalışan sunucu
```

### Tasarım yaklaşımı

Arayüz baştan özelleştirilebilir olacak. Renkler ve ölçüler CSS tokenları ve tema dosyaları üzerinden yönetilecek, tekrar eden arayüz parçaları ortak bileşenler olarak tutulacak.

### Kapsam dışında

Şimdilik:

- Çoklu kullanıcı ticari hosting sistemi
- Mobil uygulama
- Minecraft dışındaki oyunlar

---

## 2. Teknoloji Yığını

| Katman | Teknoloji | Durum |
|---|---|---|
| Backend | Python 3.11+ / FastAPI | Kullanılıyor |
| Arayüz | Jinja2 + Bootstrap 5 + Vanilla JavaScript | Kullanılıyor |
| Veritabanı | SQLite | Kullanılıyor |
| Süreç yönetimi | `subprocess.Popen` + okuyucu thread | Kullanılıyor |
| HTTP istemcisi | `httpx` | Kullanılıyor |
| Sistem izleme | `psutil` | Kullanılıyor |
| İkonlar | Bootstrap Icons | Kullanılıyor |
| Grafikler | Chart.js | Kullanılıyor |
| Zamanlama | APScheduler | Faz 4 |
| Reverse proxy | Caddy | Faz 6 |

---

## 3. Mimari

```text
Tarayıcı
   │
 HTTP / WebSocket
   │
   ▼
FastAPI
   │
   ├───────────────┬─────────────────┐
   ▼               ▼                 ▼
SQLite       InstanceLauncher    JobManager
             │                   ├─ Java kurulumu
             │                   └─ Paper indirme
             ▼
       ProcessBackend
             │
             ▼
      Minecraft süreci
             │
             ▼
      instances/<ad>/
```

### 3.1 Sunucu başlatma akışı

1. Sunucunun mevcut durumunun başlatmaya uygun olup olmadığı kontrol edilir.
2. Gerekli Java sürümü ve sunucu jar'ı kontrol edilir.
3. Eksik dosya varsa hazırlık süreci başlatılır.
4. Java veya Paper kurulumu gerekiyorsa ilgili iş oluşturulur.
5. İlerleme WebSocket üzerinden arayüze aktarılır.
6. Hazırlık tamamlandığında Minecraft süreci başlatılır.
7. Sunucu hazır olduğunda durum `running` olur.

### 3.2 Sunucu durumları

```text
stopped
preparing
starting
running
stopping
crashed
```

### 3.3 Konsol WebSocket olayları

```text
history
log
status
clear
error
progress
progress_end
```

İstemci komutları:

```json
{"cmd": "..."}
```

Son 1000 konsol satırı ring buffer içerisinde tutulur.

### 3.4 Mimari kararlar

#### `Popen` + thread

Windows ortamında `uvicorn --reload` ile kullanılan event loop yapısı nedeniyle `asyncio.create_subprocess_exec` sorun çıkardığından süreç yönetiminde `subprocess.Popen` ve okuyucu thread kullanılıyor.

#### `python run.py`

Geliştirme sunucusu yalnızca `app/` klasörünü izler. Tüm proje klasörünün izlenmesi Minecraft'ın oluşturduğu log, dünya ve diğer dosyaların paneli gereksiz yere yeniden başlatmasına neden olur.

#### JobManager

Java ve Paper indirme işleri şu anda bellekte tutuluyor. Panel kapanırsa devam eden iş bilgileri kaybolur. Uzun süreli işler için ileride veritabanına taşınabilir.

#### Paper kurucusunun öne alınması

Paper kurulumu, temel sunucu yönetiminin üzerine hızlı şekilde çalışan bir sunucu oluşturma imkanı verdiği için profil sisteminden önce tamamlandı.

---

## 4. Klasör Yapısı

```text
vulu-server-panel/
├─ run.py
├─ requirements.txt
├─ .env
├─ .env.example
│
├─ app/
│  ├─ main.py
│  ├─ config.py
│  ├─ db.py
│  ├─ ui.py
│  ├─ templating.py
│  │
│  ├─ routers/
│  │  ├─ instances.py
│  │  ├─ console.py
│  │  ├─ java.py
│  │  └─ paper.py
│  │
│  ├─ services/
│  │  ├─ container.py
│  │  ├─ process/
│  │  ├─ launcher.py
│  │  ├─ jobs.py
│  │  ├─ download.py
│  │  ├─ http.py
│  │  ├─ minecraft.py
│  │  ├─ java_manager.py
│  │  └─ paper.py
│  │
│  ├─ templates/
│  └─ static/
│
├─ data/
├─ instances/
└─ runtimes/
```

Planlanan servisler ve modüller:

```text
auth.py
security.py
rcon.py
modrinth.py
backup.py
crashlog.py
profiles/
installer/
files.py
mods.py
backups.py
stats.py
```

---

## 5. Veri Modeli

### `instances`

```text
id
name
path
port
java_path
jar_file
mc_version
loader
java_major
jvm_args
ram_mb
rcon_port
rcon_password
profile_id
status
created_at
```

### Mevcut kullanım

- `java_major` doluysa ilgili Java runtime otomatik çözülür.
- Özel Java kullanılıyorsa `java_path` kullanılır.
- `rcon_port`, `rcon_password` ve `profile_id` alanları hazırlanmıştır.
- `users` tablosu mevcut ancak henüz kullanılmıyor.

### Planlanan tablolar

```text
backups
schedules
audit_log
jobs
```

Sunucu klasöründe ayrıca:

```text
.vulu-jar.json
```

dosyası tutulur. Bu dosya kurulu Paper sürümü, build ve kanal bilgilerini içerir.

---

## 6. Java ve Paper

### 6.1 Java otomatik kurulumu

Java sürümü Minecraft sürüm bilgilerinden belirlenir.

Kullanılan öncelik:

1. Mojang sürüm JSON'undaki `javaVersion.majorVersion`
2. Eski sürümler için yerleşik uyumluluk tablosu

Uyumluluk tablosunun mevcut karşılıkları:

```text
1.16.5 ve öncesi → Java 8
1.17 - 1.20.4    → Java 17
1.20.5 - 1.21.x  → Java 21
26.x             → Java 25
```

Java paketinde öncelik Eclipse Temurin JRE'dedir. JRE bulunamazsa uygun durumda JDK'ya düşülebilir.

Kurulum sırasında:

- İndirme ilerlemesi gösterilir
- SHA-256 doğrulaması yapılır
- Arşiv yolu güvenliği kontrol edilir
- Kurulum sonrası `java -version` çalıştırılır
- Hata durumunda geçici dosyalar temizlenir

### 6.2 Paper

Paper sürümleri:

```text
https://fill.papermc.io/v3
```

üzerinden alınır.

Build seçiminde kanal önceliği:

```text
RECOMMENDED
STABLE
BETA
ALPHA
```

Aynı build birden fazla sunucuda kullanılıyorsa `data/cache/paper/` içerisindeki önbellekten yararlanılır.

Paper güncellemesi yalnızca sunucu kapalıyken yapılır.

---

# 7. Geliştirme Fazları

## Faz 0 — Temel Yapı ✅

- [x] Proje iskeleti
- [x] Sanal ortam
- [x] `requirements.txt`
- [x] FastAPI + Jinja2
- [x] SQLite bağlantısı
- [x] İlk tablolar
- [x] Veritabanı göç mekanizması
- [x] Tema sistemi
- [x] 3 tema
- [x] Tema seçici
- [x] Kenar çubuğu
- [x] Bileşen makroları
- [x] `localhost:8000` üzerinden çalışma

---

## Faz 1 — Çekirdek Sunucu Yönetimi ✅

- [x] `ProcessBackend`
- [x] `SubprocessBackend`
- [x] Sunucu ekleme
- [x] Sunucu listeleme
- [x] Panelden sunucu kaldırma
- [x] Start
- [x] Stop
- [x] Restart
- [x] Force Kill
- [x] Süreç ağacı sonlandırma
- [x] Çökme tespiti
- [x] Durum göstergeleri
- [x] WebSocket canlı konsol
- [x] Konsol geçmişi
- [x] Komut gönderme
- [x] Komut geçmişi
- [x] Otomatik yeniden bağlanma
- [x] Form doğrulaması
- [x] Port çakışması kontrolü
- [x] EULA kontrolü
- [x] Gerçek Paper sunucusuyla doğrulama

---

## Faz 2 — İzleme ✅

- [x] `psutil` ile CPU kullanımı
- [x] `psutil` ile RAM kullanımı
- [x] Süreç ağacı toplam kaynak kullanımı
- [x] RCON altyapısı
- [x] Rastgele RCON portu
- [x] Güçlü RCON şifresi
- [x] RCON ile oyuncu listesi
- [x] RCON ile TPS
- [x] Dashboard kartları
- [x] Chart.js grafikleri
- [x] Çalışma süresi
- [x] `server-port` değerinin `server.properties` içine uygulanması

### RCON notu

RCON Minecraft tarafından tüm ağ arayüzlerinde dinlenebildiği için güvenlik; güçlü şifre, rastgele port ve dış erişimin güvenlik duvarında engellenmesi üzerinden sağlanır.

VDS dağıtımında RCON portu dışarı açılmamalıdır.

---

## Faz 3 — Profil Sistemi 🔶

### Tamamlananlar

- [x] Java yöneticisi
- [x] Java sürümü tespiti
- [x] Java indirme
- [x] SHA-256 doğrulaması
- [x] Job sistemi
- [x] WebSocket üzerinden ilerleme
- [x] Paper kurucusu
- [x] Paper build seçimi
- [x] Paper önbelleği
- [x] Paper güncelleme

### Kalan işler

#### Başlatma komutu soyutlaması

Forge ve NeoForge sunucuları her zaman doğrudan `-jar` ile başlatılmadığından sunucu modeline başlatma türü eklenmesi gerekiyor.

Planlanan türler:

```text
jar
args-file
script
```

- [ ] Başlatma türü desteği
- [ ] Fabric kurucusu
- [ ] Forge kurucusu
- [ ] NeoForge kurucusu
- [ ] Manifest şeması
- [ ] Pydantic doğrulaması
- [ ] `profiles/` yapısı
- [ ] Hazır profil kartları
- [ ] Modrinth kaynakları
- [ ] ZIP kaynakları
- [ ] `server_mods_exclude`
- [ ] `extra_mods`
- [ ] JVM presetleri
- [ ] RAM kaydırıcısı
- [ ] İlk açılış testi

### Faz 3 tamamlanma kriteri

Hazır bir profil seçildiğinde gerekli Minecraft sürümü, Java, sunucu yazılımı, modlar ve yapılandırmalar otomatik olarak kurulup çalışan bir modlu sunucu oluşturulabilmeli.

---

## Faz 4 — Dosya ve Mod Yönetimi ⏳

- [ ] `safe_path` yol kısıtlaması
- [ ] Dosya gezgini
- [ ] Metin editörü
- [ ] `server.properties` düzenleme formu
- [ ] Mod listesi
- [ ] Mod açma / kapatma
- [ ] Mod yükleme
- [ ] ZIP / TAR.GZ yedekleme
- [ ] Yedekten geri yükleme
- [ ] Güncelleme öncesi otomatik yedek
- [ ] Zamanlanmış yeniden başlatma
- [ ] Zamanlanmış yedek
- [ ] Sunucu ayarları sayfası
- [ ] RAM değiştirme
- [ ] Java değiştirme
- [ ] Port değiştirme
- [ ] Jar değiştirme
- [ ] JVM argümanlarını değiştirme
- [ ] Java runtime yönetimi
- [ ] Kullanılmayan Java sürümlerini silme
- [ ] Dosyalarla birlikte sunucu silme

---

## Faz 5 — Yardımcı Özellikler ⏳

- [ ] Çökme analizcisi
- [ ] `crash-reports/` analizi
- [ ] `latest.log` analizi
- [ ] Yanlış Java sürümü tespiti
- [ ] Eksik bağımlılık tespiti
- [ ] OutOfMemory tespiti
- [ ] Chunky ön üretim düğmesi
- [ ] Chunky ilerleme durumu
- [ ] Whitelist yönetimi
- [ ] OP yönetimi
- [ ] Port erişim testi
- [ ] Launcher bağlantı profili oluşturma
- [ ] Discord webhook bildirimleri
- [ ] Mod güncelleme denetleyicisi
- [ ] Paper Minecraft sürüm yükseltmesi

---

## Faz 6 — Yayına Alma ⏳

Genel erişime açılmadan önce aşağıdaki bileşenlerin tamamlanması gerekiyor.

### Kimlik doğrulama

- [ ] Giriş sistemi
- [ ] Argon2 / bcrypt parola hashleme
- [ ] Oturum yönetimi
- [ ] Rate limiting
- [ ] CSRF koruması
- [ ] WebSocket Origin kontrolü

### Sunucu süreçleri

- [ ] `SystemdBackend` veya `TmuxBackend`
- [ ] Panel yeniden başlatıldığında Minecraft sunucularının çalışmaya devam etmesi
- [ ] Minecraft süreçleri için ayrı kısıtlı kullanıcı

### Dağıtım

- [ ] Panel için systemd servisi
- [ ] Caddy
- [ ] HTTPS
- [ ] Güvenlik duvarı
- [ ] Alan adı
- [ ] VDS yapılandırması

### Kullanıcı sistemi

- [ ] Çoklu kullanıcı
- [ ] Yetkilendirme
- [ ] Denetim günlüğü
- [ ] Yedek saklama politikası

---

# 8. API

## Sayfalar

```text
GET    /                              Sunucu listesi
GET    /instances/new                 Yeni sunucu formu
POST   /instances                     Sunucu oluşturma
GET    /instances/{id}                Sunucu sayfası
POST   /instances/{id}/delete         Panelden kaldırma
```

## Sunucu işlemleri

```text
POST   /api/instances/{id}/start
POST   /api/instances/{id}/stop
POST   /api/instances/{id}/restart
POST   /api/instances/{id}/kill
POST   /api/instances/{id}/paper/update

WS     /ws/instances/{id}/console
```

## Katalog ve kurulum

```text
GET    /api/minecraft/versions
GET    /api/java/resolve
GET    /api/java/installed
POST   /api/java/install
GET    /api/paper/resolve
POST   /api/paper/download

WS     /ws/jobs/{job_id}
```

## Diğer

```text
GET    /api/health
```

### Planlanan API'ler

```text
/api/instances/{id}/stats
/api/instances/{id}/properties
/api/instances/{id}/files
/api/instances/{id}/mods
/api/instances/{id}/backups

/api/profiles/*
/api/auth/*
```

---

# 9. Güvenlik

### Uygulananlar

- Sunucu adı doğrulaması
- Jar adı doğrulaması
- Port aralığı doğrulaması
- RAM doğrulaması
- Minecraft sürümü doğrulaması
- JVM argümanı doğrulaması
- Java yolu doğrulaması
- `shell=True` kullanılmaması
- `Popen` liste argümanları
- Konsol çıktısında HTML enjeksiyonunun engellenmesi
- SHA-256 doğrulaması
- Arşivlerde yol kaçışı koruması
- Komutlarda satır sonu temizleme
- Komut uzunluğu sınırı
- Host / Origin kontrolü
- Panelin `127.0.0.1` üzerinde çalışması

### Genel erişimden önce zorunlu

- Kimlik doğrulama
- CSRF
- WebSocket Origin kontrolü
- RCON'un yalnızca yerel erişimde tutulması
- `safe_path`
- Rate limiting
- Ayrı ve kısıtlı Minecraft kullanıcısı

---

# 10. Dağıtım Planı

Hedef ortam:

```text
Debian / Ubuntu
    │
    ├── UFW
    │    ├── 22
    │    ├── 80
    │    ├── 443
    │    └── 25565
    │
    ├── Ayrı kullanıcı
    ├── Python ortamı
    ├── vulu Server Panel
    │       └── systemd
    │
    └── Caddy
            └── HTTPS
```

Alan adı yapısı:

```text
panel.example.com
        │
        ▼
      Caddy
        │
        ▼
127.0.0.1:8000
```

Caddy reverse proxy:

```text
panel.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

Linux tarafında Java paketleri `.tar.gz` formatında işlenir. VDS ortamında `PANEL_CONTACT` gereksinimi devam eder.

---

# 11. Bilinen Sorunlar ve Çözümler

| Sorun | Durum |
|---|---|
| Yanlış Java sürümü nedeniyle sunucunun çökmesi | ✅ Otomatik Java tespiti |
| `--reload` nedeniyle Minecraft dosyalarının paneli yeniden başlatması | ✅ `run.py` ile yalnızca `app/` izleniyor |
| Windows'ta asyncio alt süreç hatası | ✅ `Popen` + thread |
| Bozuk veya değiştirilmiş indirme | ✅ SHA-256 |
| Yarım kalan kurulumun dosya bırakması | ✅ `finally` ile temizlik |
| Aynı Java/Paper dosyasının tekrar indirilmesi | ✅ Paylaşılan işler + Paper önbelleği |
| PaperMC'den 403 alınması | ⚠ `PANEL_CONTACT` gerekli |
| İstemci modlarının sunucuyu çökertmesi | ⏳ Profil sistemi |
| Forge/NeoForge'un `-jar` ile başlatılamaması | ⏳ Başlatma komutu soyutlaması |
| Panel kapanınca sunucunun kapanması | ⏳ Faz 6 |
| Disk alanının yedek/log/Java dosyalarıyla dolması | ⏳ Faz 4 |
| Spigot BuildTools gibi araçların JDK istemesi | ⏳ Gerekirse JDK seçeneği |
| Whitelist için UUID çözümleme sorunları | ⏳ Faz 5 |
| CurseForge modlarının doğrudan indirilememesi | ⏳ Profil sistemi / manuel yükleme |

---

# 12. Test Durumu

Geliştirme sırasında sahte Mojang, Adoptium ve PaperMC servisleri kullanılarak testler gerçekleştirildi.

Mevcut test kapsamı:

- Faz 1 uçtan uca: 20 kontrol
- Java kurulumu: 45 kontrol
- Paper kurulumu: 34 kontrol

Test edilen konular arasında:

- Sunucu oluşturma
- Başlatma / durdurma
- Komut gönderme
- Çökme
- Force Kill
- Panel kapanışı
- Java sürüm tespiti
- İndirme ilerlemesi
- Bozuk checksum
- İptal
- Çift indirme
- ZIP path traversal
- Paper build seçimi
- Paper önbelleği
- Paper güncellemesi

Gerçek internet bağlantısıyla Mojang / Adoptium / PaperMC üzerinden Java ve Paper indirme, ardından sunucu başlatma işlemi 2 Ekim 2026 tarihinde doğrulandı.

### Sonraki test adımı

Testlerin `tests/` altında `pytest` kullanılarak repoya eklenmesi planlanıyor.

Amaç:

```text
Her faz sonrası
    ↓
pytest
    ↓
Regresyon kontrolü
```

---

# 13. Sonraki Geliştirme Sırası

Mevcut hedef doğrultusunda önerilen geliştirme sırası:

### 1. Başlatma komutu soyutlaması

Forge ve NeoForge desteğinin temelini oluşturacak.

### 2. Fabric kurucusu

Profil sisteminin ilk gerçek modlu sunucu kurulumu için en basit kurulum akışı.

### 3. JVM presetleri ve RAM yönetimi

Hazır JVM ayarları ve arayüz üzerinden RAM seçimi.

### 4. Forge / NeoForge

Başlatma altyapısı tamamlandıktan sonra diğer mod yükleyicilerinin eklenmesi.

### 5. Manifest ve profil sistemi

Hazır sunucu profillerinin tanımlanması ve panel üzerinden kurulması.

### 6. Modrinth entegrasyonu

Profil ve mod kurulum sisteminin dış kaynaklarla genişletilmesi.

### Paralel küçük işler

- Sunucu ayarları sayfası
- Java yönetimi
- `tests/` klasörü
- Güvenlik kontrollerinin genişletilmesi

---

## 14. Geliştirme Notları

### `run.py` kullanımı

```bash
python run.py
```

Geliştirme ortamında önerilen çalıştırma şeklidir.

### Panel adresi

```text
http://127.0.0.1:8000
```

### Git

Çalışan sürümlerin düzenli olarak commitlenmesi ve roadmap'teki önemli aşamaların sürüm geçmişinde takip edilmesi önerilir.

---

## 15. Yol Haritası Özeti

```text
Faz 0  ████████████████████  Tamamlandı
Faz 1  ████████████████████  Tamamlandı
Faz 2  ████████████████████  Tamamlandı
Faz 3  ███████████░░░░░░░░░  Devam ediyor
Faz 4  ░░░░░░░░░░░░░░░░░░░░  Planlandı
Faz 5  ░░░░░░░░░░░░░░░░░░░░  Planlandı
Faz 6  ░░░░░░░░░░░░░░░░░░░░  Planlandı
```

Ana hedef:

> **Hazır bir mod paketi profilinden çalışan Minecraft sunucusuna mümkün olduğunca az manuel işlemle ulaşmak.**
