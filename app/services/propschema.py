"""server.properties: panelden düzenlenebilen alanlar (şema) ve değer doğrulaması.
Panelin kendisinin yönettiği anahtarlar (server-port, rcon.*, server-ip, query.port) burada YOKTUR."""
import re

MANAGED = {"server-port", "enable-rcon", "rcon.port", "rcon.password", "server-ip", "query.port"}
TEXT_OK = re.compile(r"^[^\x00-\x1f\\]{0,200}$")


def _f(key, typ, label, default, help="", **kw):
    return {"key": key, "type": typ, "label": label, "default": default, "help": help, **kw}


GROUPS = [
    ("Genel", [
        _f("motd", "text", "Sunucu açıklaması (motd)", "A Minecraft Server", "Oyuncuların sunucu listesinde gördüğü yazı."),
        _f("max-players", "int", "En fazla oyuncu", "20", min=1, max=1000),
        _f("difficulty", "enum", "Zorluk", "easy", options=["peaceful", "easy", "normal", "hard"]),
        _f("gamemode", "enum", "Varsayılan oyun modu", "survival", options=["survival", "creative", "adventure", "spectator"]),
        _f("force-gamemode", "bool", "Girişte oyun modunu zorla", "false"),
        _f("hardcore", "bool", "Hardcore", "false", "Ölünce oyuncu izleyiciye döner."),
        _f("pvp", "bool", "Oyuncular birbirine hasar verebilsin (PvP)", "true"),
    ]),
    ("Dünya", [
        _f("level-seed", "text", "Dünya tohumu (seed)", "", "Yalnızca dünya ilk oluşturulurken geçerli."),
        _f("allow-nether", "bool", "Nether açık", "true"),
        _f("spawn-monsters", "bool", "Canavarlar doğsun", "true"),
        _f("spawn-animals", "bool", "Hayvanlar doğsun", "true"),
        _f("spawn-npcs", "bool", "Köylüler doğsun", "true"),
        _f("spawn-protection", "int", "Doğma noktası koruması (blok)", "16", "0 = kapalı.", min=0, max=1000),
        _f("allow-flight", "bool", "Uçmaya izin ver", "false", "Bazı modlar için gerekir."),
        _f("enable-command-block", "bool", "Komut blokları açık", "false"),
    ]),
    ("Performans", [
        _f("view-distance", "int", "Görüş mesafesi (chunk)", "10", "Düşürmek sunucuyu hızlandırır.", min=2, max=32),
        _f("simulation-distance", "int", "Simülasyon mesafesi (chunk)", "10", min=3, max=32),
        _f("entity-broadcast-range-percentage", "int", "Varlık gönderim menzili (%)", "100", min=10, max=500),
        _f("sync-chunk-writes", "bool", "Chunk yazımını eşzamanlı yap", "true", "Kapatmak hızlandırır ama çökmede veri kaybı riski."),
        _f("network-compression-threshold", "int", "Ağ sıkıştırma eşiği (bayt)", "256", "-1 = kapalı.", min=-1, max=1024),
    ]),
    ("Erişim ve güvenlik", [
        _f("online-mode", "bool", "Hesap doğrulaması (online-mode)", "true", "Kapatmak kimliksiz/korsan girişe izin verir: güvenlik riski.", warn=True),
        _f("white-list", "bool", "Beyaz liste (whitelist)", "false"),
        _f("enforce-whitelist", "bool", "Beyaz listeyi zorla (listede olmayanları at)", "false"),
        _f("op-permission-level", "int", "OP yetki seviyesi", "4", min=1, max=4),
        _f("player-idle-timeout", "int", "Boşta kalma süresi (dk)", "0", "0 = kapalı.", min=0, max=10080),
    ]),
]
FIELDS = {f["key"]: f for _, fs in GROUPS for f in fs}


def validate_value(key: str, raw) -> tuple[str | None, str | None]:
    """(geçerli değer metni, hata) döndürür."""
    f = FIELDS.get(key)
    if not f:
        return None, f"Bilinmeyen ya da panelin yönettiği ayar: {key}"
    t = f["type"]
    if t == "bool":
        if raw in (True, "true"):
            return "true", None
        if raw in (False, "false"):
            return "false", None
        return None, f"{f['label']}: evet/hayır olmalı."
    if t == "int":
        try:
            n = int(str(raw).strip())
        except ValueError:
            return None, f"{f['label']}: sayı olmalı."
        if not f["min"] <= n <= f["max"]:
            return None, f"{f['label']}: {f['min']} ile {f['max']} arasında olmalı."
        return str(n), None
    if t == "enum":
        return (str(raw), None) if raw in f["options"] else (None, f"{f['label']}: geçersiz seçim.")
    s = str(raw)
    return (s, None) if TEXT_OK.match(s) else (None, f"{f['label']}: geçersiz karakter ya da çok uzun (en fazla 200).")
