"""server.properties: panelden düzenlenebilen alanlar (şema) ve değer doğrulaması.
Panelin kendisinin yönettiği anahtarlar (server-port, rcon.*, server-ip, query.port) burada YOKTUR."""
import re
from ..i18n import _t

MANAGED = {"server-port", "enable-rcon", "rcon.port", "rcon.password", "server-ip", "query.port"}
TEXT_OK = re.compile(r"^[^\x00-\x1f\\]{0,200}$")


def _f(key, typ, label, default, help="", **kw):
    return {"key": key, "type": typ, "label": label, "default": default, "help": help, **kw}


GROUPS = [
    ("Genel", [
        _f("motd", "text", "Sunucu açıklaması (MOTD)", "A Minecraft Server",
           "Oyuncuların sunucu listesinde, sunucu adının altında gördüğü kısa yazı. Renk kodları (§a, §l…) kullanılabilir."),
        _f("max-players", "int", "En fazla oyuncu", "20",
           "Aynı anda bağlanabilecek oyuncu sayısı. OP'ler bu sınırı aşabilir.", min=1, max=1000),
        _f("difficulty", "enum", "Zorluk", "easy",
           "Canavarların verdiği hasarı ve açlığın etkisini belirler. Barışçıl'da canavar doğmaz.",
           options=["peaceful", "easy", "normal", "hard"],
           labels={"peaceful": "Barışçıl", "easy": "Kolay", "normal": "Normal", "hard": "Zor"}),
        _f("gamemode", "enum", "Varsayılan oyun modu", "survival",
           "Sunucuya ilk kez giren oyuncuların başlayacağı mod.",
           options=["survival", "creative", "adventure", "spectator"],
           labels={"survival": "Hayatta kalma", "creative": "Yaratıcı", "adventure": "Macera", "spectator": "İzleyici"}),
        _f("force-gamemode", "bool", "Girişte oyun modunu zorla", "false",
           "Açıkken oyuncular her girişte, değiştirilmiş olsa bile varsayılan oyun moduna döner."),
        _f("hardcore", "bool", "Hardcore", "false",
           "Zorluk en yükseğe kilitlenir; ölen oyuncu yeniden doğamaz ve izleyici moduna geçer."),
        _f("pvp", "bool", "Oyuncular birbirine hasar verebilsin (PvP)", "true",
           "Kapalıyken oyuncular birbirine doğrudan saldıramaz; tuzak ve lav gibi dolaylı hasar yine işler."),
    ]),
    ("Dünya", [
        _f("level-seed", "text", "Dünya tohumu (seed)", "",
           "Dünyanın nasıl oluşacağını belirleyen sayı ya da yazı. Boş bırakılırsa rastgele seçilir; yalnızca dünya ilk kez oluşturulurken etkilidir."),
        _f("allow-nether", "bool", "Nether açık", "true",
           "Kapalıyken Nether portalları çalışmaz ve oyuncular Nether'a geçemez."),
        _f("spawn-monsters", "bool", "Canavarlar doğsun", "true",
           "Zombi, iskelet gibi düşman yaratıkların doğal olarak doğmasını açar ya da kapatır."),
        _f("spawn-animals", "bool", "Hayvanlar doğsun", "true",
           "İnek, koyun gibi hayvanların doğal olarak doğmasını açar ya da kapatır."),
        _f("spawn-npcs", "bool", "Köylüler doğsun", "true",
           "Köylerde köylü doğmasını açar ya da kapatır."),
        _f("spawn-protection", "int", "Doğma noktası koruması (blok)", "16",
           "Doğma noktasının çevresinde, OP olmayan oyuncuların blok kırıp koyamayacağı alanın yarıçapı. 0 yazarsan koruma kapanır.",
           min=0, max=1000),
        _f("allow-flight", "bool", "Uçmaya izin ver", "false",
           "Kapalıyken havada kalan oyuncular hile şüphesiyle atılır. Uçuş sağlayan modlar ya da eklentiler kullanıyorsan aç."),
        _f("enable-command-block", "bool", "Komut blokları açık", "false",
           "Komut bloklarının çalışmasına izin verir. Harita ve mini oyunlar için gerekir; ihtiyacın yoksa kapalı tut."),
    ]),
    ("Performans", [
        _f("view-distance", "int", "Görüş mesafesi (chunk)", "10",
           "Oyunculara gönderilen dünya alanının yarıçapı. Düşürmek sunucuyu ve ağı en çok rahatlatan ayardır; 6-10 arası çoğu sunucu için yeterlidir.",
           min=2, max=32),
        _f("simulation-distance", "int", "Simülasyon mesafesi (chunk)", "10",
           "Oyuncunun çevresinde yaratıkların, ekinlerin ve makinelerin çalıştığı alan. Görüş mesafesinden küçük tutmak işlemciyi rahatlatır.",
           min=3, max=32),
        _f("entity-broadcast-range-percentage", "int", "Varlık gösterim menzili (%)", "100",
           "Yaratıkların ve eşyaların oyunculara hangi uzaklıktan gösterileceği. Kalabalık sunucularda düşürmek ağı rahatlatır.",
           min=10, max=500),
        _f("sync-chunk-writes", "bool", "Dünyayı diske beklemeli yaz", "true",
           "Açıkken dünya her kayıtta diske tam yazılmadan devam edilmez. Kapatmak kaydı hızlandırır ama ani kapanmada dünya bozulabilir."),
        _f("network-compression-threshold", "int", "Ağ sıkıştırma eşiği (bayt)", "256",
           "Bu boyuttan büyük paketler sıkıştırılır. Yerel ağda daha yüksek değer işlemciyi rahatlatır; -1 sıkıştırmayı kapatır.",
           min=-1, max=1024),
    ]),
    ("Erişim ve güvenlik", [
        _f("online-mode", "bool", "Hesap doğrulaması (online-mode)", "true",
           "Oyuncuların gerçek Minecraft hesabıyla girdiğini Mojang'a sorarak doğrular. Kapatırsan herkes istediği adla girebilir; başkasının adıyla girip OP yetkisi bile alabilir.",
           warn=True),
        _f("white-list", "bool", "Beyaz liste", "false",
           "Açıkken yalnızca listedeki oyuncular girebilir. Listeyi sunucu sayfasındaki Oyuncular sekmesinden yönetebilirsin."),
        _f("enforce-whitelist", "bool", "Beyaz listeyi anında uygula", "false",
           "Açıkken listeden çıkarılan oyuncu sunucudaysa hemen atılır; kapalıyken yalnızca bir sonraki girişinde engellenir."),
        _f("op-permission-level", "int", "OP yetki seviyesi", "4",
           "OP'lerin kullanabileceği komutlar: 1 doğma korumasını aşma, 2 hile komutları, 3 oyuncu yönetimi (ban, kick), 4 tüm komutlar (sunucuyu durdurma dahil).",
           min=1, max=4),
        _f("player-idle-timeout", "int", "Boşta kalma süresi (dakika)", "0",
           "Bu süre boyunca hareket etmeyen oyuncular sunucudan atılır. 0 yazarsan kimse atılmaz.",
           min=0, max=10080),
    ]),
]
FIELDS = {f["key"]: f for _, fs in GROUPS for f in fs}


def validate_value(key: str, raw) -> tuple[str | None, str | None]:
    """(geçerli değer metni, hata) döndürür."""
    f = FIELDS.get(key)
    if not f:
        return None, _t('Bilinmeyen ya da panelin yönettiği ayar: {key}', key=key)
    t = f["type"]
    if t == "bool":
        if raw in (True, "true"):
            return "true", None
        if raw in (False, "false"):
            return "false", None
        return None, _t('{label}: evet/hayır olmalı.', label=_t(f['label']))
    if t == "int":
        try:
            n = int(str(raw).strip())
        except ValueError:
            return None, _t('{label}: sayı olmalı.', label=_t(f['label']))
        if not f["min"] <= n <= f["max"]:
            return None, _t('{label}: {min} ile {max} arasında olmalı.', label=_t(f['label']), min=f['min'], max=f['max'])
        return str(n), None
    if t == "enum":
        return (str(raw), None) if raw in f["options"] else (None, _t('{label}: geçersiz seçim.', label=_t(f['label'])))
    s = str(raw)
    return (s, None) if TEXT_OK.match(s) else (None, _t('{label}: geçersiz karakter ya da çok uzun (en fazla 200).', label=_t(f['label'])))
