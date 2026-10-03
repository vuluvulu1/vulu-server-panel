# vulu Server Panel

Kullanıcıların Minecraft sunucularını tek bir web arayüzünden yönetebilmesini sağlayan, sıfırdan geliştirilmiş bir sunucu yönetim paneli.

Proje, **Crafty Controller'a alternatif** olacak şekilde tasarlanmıştır. Özellikle modlu Minecraft sunucularının kurulumunu ve yönetimini kolaylaştırmaya odaklanır.

Sunucu oluşturma, başlatma, durdurma, canlı konsol, kaynak kullanımı, Java kurulumu ve Paper kurulumu gibi işlemler tek bir arayüz üzerinden gerçekleştirilebilir.

> **Durum:** Aktif geliştirme aşamasındadır. Kimlik doğrulama sistemi henüz uygulanmamıştır.

## Özellikler

* Minecraft sunucusu oluşturma
* Sunucu başlatma, durdurma, yeniden başlatma ve zorla kapatma
* WebSocket üzerinden canlı konsol
* Konsoldan komut gönderme
* CPU ve RAM kullanımı takibi
* Oyuncu sayısı ve oyuncu listesi
* RCON üzerinden TPS takibi
* Sunucu çalışma süresi takibi
* Minecraft sürümüne göre otomatik Java sürümü tespiti
* Eclipse Temurin JRE otomatik kurulumu
* Paper sürüm ve build seçimi
* Paper otomatik indirme ve güncelleme
* İndirilen dosyalar için SHA-256 doğrulaması
* Paper build önbelleği
* Çoklu arayüz teması
* CSS tokenları ve bileşenler üzerinden özelleştirilebilir arayüz
* Girdi doğrulama ve süreç güvenliği

## Teknoloji Yığını

| Bileşen                 | Teknoloji                        |
| ----------------------- | -------------------------------- |
| Backend                 | Python 3.11+ / FastAPI           |
| Şablon sistemi          | Jinja2                           |
| Arayüz                  | Bootstrap 5 / Vanilla JavaScript |
| Veritabanı              | SQLite                           |
| Gerçek zamanlı iletişim | WebSocket                        |
| Süreç yönetimi          | `subprocess.Popen`               |
| Sistem izleme           | `psutil`                         |
| HTTP istemcisi          | `httpx`                          |
| Grafikler               | Chart.js                         |

## Ekran Görüntüleri

Arayüz tamamlandıkça ekran görüntüleri eklenecektir.

<!--
![Ana Sayfa](docs/screenshots/dashboard.png)
![Sunucu Konsolu](docs/screenshots/console.png)
![Sunucu Oluşturma](docs/screenshots/server-creation.png)
-->

## Proje Durumu

### Tamamlananlar

* [x] Proje yapısı ve SQLite veritabanı
* [x] Tema sistemi ve yeniden kullanılabilir arayüz bileşenleri
* [x] Sunucu oluşturma ve yönetme
* [x] Başlatma / durdurma / yeniden başlatma / zorla kapatma
* [x] Çökme tespiti
* [x] WebSocket canlı konsolu
* [x] Komut geçmişi
* [x] CPU / RAM takibi
* [x] Oyuncu ve TPS takibi
* [x] Çalışma süresi takibi
* [x] Canlı Chart.js grafikleri
* [x] Otomatik Java kurulumu
* [x] Minecraft sürümüne göre Java sürümü tespiti
* [x] SHA-256 doğrulaması
* [x] Paper kurucusu
* [x] Paper build önbelleği
* [x] Paper güncelleme
* [x] Host / Origin koruması
* [x] JVM argümanı doğrulaması
* [x] Java yolu doğrulaması
* [x] Gerçek Paper sunucusuyla test

### Geliştirme Aşamasında

* [ ] Başlatma komutu soyutlaması
* [ ] Fabric kurucusu
* [ ] Forge kurucusu
* [ ] NeoForge kurucusu
* [ ] JVM presetleri
* [ ] RAM kaydırıcısı
* [ ] Sunucu profil / manifest sistemi
* [ ] Modrinth ve ZIP kaynakları
* [ ] Tek tıkla modlu sunucu profilleri
* [ ] Dosya yöneticisi
* [ ] Mod yönetimi
* [ ] Yedekleme ve geri yükleme
* [ ] Zamanlanmış yeniden başlatmalar
* [ ] Çökme analizi
* [ ] Whitelist / OP yönetimi
* [ ] Discord bildirimleri
* [ ] Kimlik doğrulama
* [ ] VDS dağıtımı
* [ ] HTTPS ve alan adı desteği
* [ ] Çoklu kullanıcı desteği

Ayrıntılı geliştirme planı için [`roadmap.md`](roadmap.md) dosyasına bakılabilir.

## Kurulum

### Gereksinimler

* Python 3.11 veya üzeri
* Desteklenen bir Windows, Linux veya Python çalışma ortamı

### Kurulum

Sanal ortam oluşturun:

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Linux:

```bash
source .venv/bin/activate
```

Bağımlılıkları yükleyin:

```bash
pip install -r requirements.txt
```

`.env` dosyasını oluşturun:

```bash
# Windows
copy .env.example .env

# Linux
cp .env.example .env
```

Paneli başlatın:

```bash
python run.py
```

Panel varsayılan olarak şu adreste çalışır:

```text
http://127.0.0.1:8000
```

`uvicorn --reload` yerine `python run.py` kullanılır. Minecraft sunucuları `instances/` altında sürekli dosya değiştirdiği için yalnızca `app/` klasörünü izleyen ayrı çalıştırma yapısı kullanılmıştır.

## Yapılandırma

Yapılandırma `.env` dosyası üzerinden yapılır.

| Değişken              | Açıklama                                              |
| --------------------- | ----------------------------------------------------- |
| `PANEL_HOST`          | Panelin dinleyeceği adres. Varsayılan: `127.0.0.1`    |
| `PANEL_PORT`          | HTTP portu. Varsayılan: `8000`                        |
| `PANEL_CONTACT`       | PaperMC indirme servisi için gerekli iletişim bilgisi |
| `PANEL_ALLOWED_HOSTS` | İzin verilen alan adları, virgülle ayrılır            |
| `PANEL_SECRET_KEY`    | Kimlik doğrulama sistemi için ayrılmış anahtar        |

Kimlik doğrulama sistemi uygulanana kadar panelin `127.0.0.1` üzerinde tutulması gerekir.

## Java Yönetimi

Panel, seçilen Minecraft sürümüne göre gerekli Java sürümünü Mojang sürüm verilerinden belirler.

Gerekli Java sürümü sistemde bulunmuyorsa Eclipse Temurin JRE otomatik olarak indirilebilir ve kurulabilir.

Kurulum sürecinde:

* Java sürümü tespit edilir
* İndirme ilerlemesi gösterilir
* SHA-256 doğrulaması yapılır
* Arşiv çıkartılır
* `java -version` ile kurulum doğrulanır
* Hata durumunda geçici dosyalar temizlenir

Kurulan Java sürümleri:

```text
runtimes/java-<sürüm>/
```

altında tutulur.

Mevcut bir Java kurulumu da kullanılabilir.

## Paper Kurulumu

Paper sürümleri ve build bilgileri PaperMC API üzerinden alınır.

Paper kurucusu:

* Desteklenen Minecraft sürümlerini listeler
* Uygun build'i belirler
* Sunucu jar dosyasını indirir
* SHA-256 doğrulaması yapar
* Build'leri yerel önbellekte saklar
* Daha önce indirilen build'leri tekrar indirmez
* Sunucu kapalıyken Paper güncellemesine izin verir

PaperMC indirmeleri için `.env` içerisinde `PANEL_CONTACT` tanımlanmalıdır.

## İzleme

Sunucu izleme özellikleri:

* CPU kullanımı
* RAM kullanımı
* Oyuncu sayısı
* Oyuncu isimleri
* TPS
* Çalışma süresi
* Canlı grafikler

CPU ve RAM bilgileri `psutil` üzerinden alınır.

Oyuncu ve TPS bilgileri RCON üzerinden alınır.

RCON portları sunucu başına oluşturulur ve genel internete açılmamalıdır.

## Tema ve Özelleştirme

Arayüz, CSS değişkenleri ve ayrı tema dosyaları üzerine kuruludur.

| Değiştirilecek bölüm   | Dosya / klasör                     |
| ---------------------- | ---------------------------------- |
| Tema renkleri          | `app/static/css/themes/`           |
| Tasarım tokenları      | `app/static/css/tokens.css`        |
| Bileşenler             | `app/static/css/components.css`    |
| Özel CSS               | `app/static/css/custom.css`        |
| Arayüz bileşenleri     | `app/templates/components/ui.html` |
| Menü / marka bilgileri | `app/ui.py`                        |
| Ana yerleşim           | `app/templates/base.html`          |

Mevcut temalar:

* vulu Violet
* Neon Cyberpunk
* Açık

`components.css` içerisinde tema renkleri doğrudan yazılmak yerine CSS değişkenleri kullanılır.

## Güvenlik

Panel, ana sistem üzerinde süreç başlatabildiği ve dosya yazabildiği için güvenlik kontrolleri projenin temel parçalarından biridir.

### Uygulanan kontroller

* `127.0.0.1` üzerinden çalışma
* Host / Origin doğrulaması
* DNS rebinding koruması
* Clickjacking koruması
* `/docs` erişiminin kapatılması
* JVM argümanı beyaz listesi
* Java yolu doğrulaması
* SHA-256 doğrulaması
* Arşivlerde yol kaçışı koruması
* `shell=True` kullanılmaması
* Komut girişlerinde satır sonu ve uzunluk kontrolü

### Genel erişimden önce yapılması gerekenler

* Kimlik doğrulama
* Oturum yönetimi
* CSRF koruması
* WebSocket Origin kısıtlamaları
* `safe_path` dosya sistemi kısıtlamaları
* RCON'un yalnızca yerel ağda tutulması
* Rate limiting
* Minecraft süreçleri için ayrı ve kısıtlı kullanıcı

## Proje Yapısı

```text
vulu-server-panel/
├── run.py
├── requirements.txt
├── .env
├── .env.example
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── ui.py
│   ├── templating.py
│   │
│   ├── routers/
│   │   ├── instances.py
│   │   ├── console.py
│   │   ├── java.py
│   │   └── paper.py
│   │
│   ├── services/
│   │   ├── process/
│   │   ├── launcher.py
│   │   ├── jobs.py
│   │   ├── download.py
│   │   ├── http.py
│   │   ├── minecraft.py
│   │   ├── java_manager.py
│   │   └── paper.py
│   │
│   ├── templates/
│   └── static/
│
├── data/
├── instances/
└── runtimes/
```

`data/`, `instances/` ve `runtimes/` oluşturulan yerel verileri içerir ve Git deposuna eklenmemelidir.

## Bilinen Kısıtlamalar

* Panel kapatıldığında çalışan Minecraft sunucuları da kapanır
* `app/` altında Python dosyalarının kaydedilmesi geliştirme sunucusunun yeniden başlamasına neden olur
* Kimlik doğrulama sistemi henüz bulunmuyor
* Oluşturulan sunucuların RAM, Java, port ve JVM ayarları henüz arayüzden değiştirilemiyor
* Forge ve NeoForge kurulumu henüz uygulanmadı
* Dosya yönetimi henüz uygulanmadı
* Yedekleme ve geri yükleme henüz uygulanmadı
* Genel erişime açık dağıtım henüz hazır değil

## Yol Haritası

Ayrıntılı yol haritası ayrı bir dosyada tutulmaktadır:

[`roadmap.md`](roadmap.md)

Roadmap içerisinde:

* Güncel proje durumu
* Mimari kararlar
* Fazlara ayrılmış geliştirme planı
* API planı
* Güvenlik gereksinimleri
* VDS ve alan adı dağıtım planı
* Bilinen sorunlar ve çözümleri
* Test durumu
* Önerilen geliştirme sırası

yer almaktadır.

## Lisans

Henüz bir lisans belirtilmemiştir.

Lisans eklenene kadar proje **tüm hakları saklıdır** şeklinde değerlendirilmelidir.
