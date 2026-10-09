"""Çökme analizcisi: sunucu çöktüğünde konsol çıktısını ve yeni crash raporunu okuyup bilinen
hata kalıplarına göre Türkçe neden + öneri üretir.

Yalnızca okuma yapar; dosya boyutları sınırlıdır. Her bulgu:
  {"key", "title", "detail", "fix"}  (aynı anahtar bir kez raporlanır)
"""
from __future__ import annotations

import re
import time
from pathlib import Path

REPORT_MAX = 512 * 1024           # crash raporundan okunacak en fazla bayt
CONSOLE_LINES = 600                # konsolun son kaç satırı incelenir
MAX_LIST = 12

_ID = r"[a-z0-9_.\-]{1,64}"


def _latest_report(folder: Path, since: float) -> tuple[str, str]:
    """Bu çalıştırmadan sonra yazılmış en yeni crash raporu (ad, içerik)."""
    d = folder / "crash-reports"
    if not d.is_dir():
        return "", ""
    best = None
    for p in d.glob("crash-*.txt"):
        try:
            st = p.stat()
        except OSError:
            continue
        if p.is_file() and st.st_mtime >= since - 5 and (best is None or st.st_mtime > best[0]):
            best = (st.st_mtime, p)
    if not best:
        return "", ""
    try:
        with open(best[1], "rb") as f:
            return best[1].name, f.read(REPORT_MAX).decode("utf-8", "replace")
    except OSError:
        return "", ""


def _uniq(items) -> list[str]:
    out = []
    for i in items:
        if i and i not in out:
            out.append(i)
    return out[:MAX_LIST]


def analyze(folder: Path, console: list[str], started_at: float | None = None) -> dict:
    report_name, report = _latest_report(folder, started_at or (time.time() - 600))
    text = "\n".join(console[-CONSOLE_LINES:]) + "\n" + report
    found: list[dict] = []

    def add(key, title, detail, fix):
        if not any(f["key"] == key for f in found):
            found.append({"key": key, "title": title, "detail": detail, "fix": fix})

    # --- Java sürümü ---
    if m := re.search(r"UnsupportedClassVersionError.*?class file version (\d+)\.0", text):
        need = int(m.group(1)) - 44
        add("java", f"Java {need} gerekiyor",
            f"Sunucu dosyası Java {need} ile derlenmiş, ama daha eski bir Java ile başlatıldı.",
            f"Ayarlar → Java'dan \"Otomatik\" ya da Java {need} seç.")

    # --- bellek ---
    if "insufficient memory for the Java Runtime" in text or "Could not reserve enough space for object heap" in text:
        add("ram-start", "Bilgisayarda yeterli boş bellek yok",
            "Java, ayarlanan RAM'i işletim sisteminden alamadı.",
            "Diğer programları kapat ya da sunucunun RAM ayarını düşür.")
    elif re.search(r"java\.lang\.OutOfMemoryError: (Java heap space|GC overhead)", text):
        add("ram-heap", "Sunucunun belleği doldu",
            "Oyun sırasında ayrılan RAM yetmedi (çok mod, geniş görüş mesafesi ya da çok oyuncu).",
            "Ayarlar'dan RAM'i artır ya da server.properties'te view-distance/simulation-distance değerlerini düşür.")

    # --- port ---
    if re.search(r"FAILED TO BIND TO PORT|BindException|Address already in use", text):
        add("port", "Port kullanımda",
            "Sunucunun portunu başka bir program (ya da başka bir sunucu) kullanıyor.",
            "Diğer sunucuyu kapat ya da Ayarlar'dan farklı bir port seç.")

    # --- EULA ---
    if "You need to agree to the EULA" in text:
        add("eula", "EULA kabul edilmemiş",
            "Minecraft sunucusu eula.txt içinde eula=true görmeden açılmaz.",
            "Dosyalar'dan eula.txt'yi aç ve eula=true yap (Minecraft EULA'sını kabul etmiş olursun).")

    # --- dünya kilidi / bozuk dünya ---
    if "session.lock" in text and ("already locked" in text or "LevelStorageException" in text):
        add("lock", "Dünya başka bir süreç tarafından kullanılıyor",
            "Aynı dünya klasörünü kullanan başka bir sunucu ya da kapanmamış eski bir Java süreci var.",
            "Görev Yöneticisi'nde kalan java.exe süreçlerini kapat ve yeniden dene.")
    if re.search(r"(Failed to load level|Exception reading .*level\.dat|Corrupted chunk)", text):
        add("world", "Dünya verisi okunamadı",
            "level.dat ya da bazı bölge dosyaları bozuk olabilir.",
            "Yedekler'den son sağlam yedeği geri yükle.")

    # --- eksik bağımlılık: Fabric ---
    fab = []
    for m in re.finditer(r"Mod '([^'\n]{1,80})' \([^)\n]{1,64}\)[^\n]{0,40}? requires ([^\n]{1,200}?), which is missing", text):
        tail = m.group(2)
        ids = re.findall(r"\((" + _ID + r")\)", tail)              # "... of mod 'Cloth Config' (cloth-config)"
        dep = ids[-1] if ids else tail.split()[-1].strip("'")      # "... any version of fabric-api"
        fab.append((m.group(1), dep))
    # --- eksik bağımlılık: Forge / NeoForge ---
    forge = re.findall(r"Mod ID: '(" + _ID + r")', Requested by: '(" + _ID + r")'", text)
    forge += re.findall(r"Missing (?:mandatory )?dependenc(?:y|ies)[^\n]{0,40}?'?(" + _ID + r")'?[^\n]{0,40}?(?:for|required by) '?(" + _ID + r")'?", text)
    missing = _uniq([f"{dep} (isteyen: {who.strip()})" for who, dep in fab] + [f"{dep} (isteyen: {who})" for dep, who in forge])
    if missing or re.search(r"Incompatible mods? found|Missing or unsupported mandatory dependencies", text):
        add("deps", "Eksik ya da uyumsuz mod bağımlılığı",
            ("Eksik: " + "; ".join(missing)) if missing else "Bazı modlar, bulunmayan ya da yanlış sürümdeki başka modları istiyor.",
            "Modlar penceresinde eksik bağımlılık listesine bak; eksik modu Modrinth'ten kur ya da sürümü uyumlu olanla değiştir.")

    # --- istemci modu sunucuda ---
    if re.search(r"(Attempted to load class net/minecraft/client|for invalid dist DEDICATED_SERVER|"
                 r"Environment type CLIENT is not allowed|net/minecraft/client/Minecraft)", text):
        files = _uniq(re.findall(r"Mod File: (?:.*[/\\])?([^/\\\n]{1,120}\.jar)", report))
        add("client", "İstemciye özel bir mod sunucuda yüklenmeye çalıştı",
            ("Şüpheli: " + ", ".join(files)) if files else "Bir mod yalnızca oyuncu tarafında çalışan kodu sunucuda çağırdı.",
            "Bu modu Modlar penceresinden kapat (sunucuda gerekmez).")

    # --- mixin ---
    mix = _uniq(re.findall(r"Mixin apply (?:for mod|failed) ([A-Za-z0-9_.\-]{1,64})", text) +
                re.findall(r"from mod ([a-z0-9_.\-]{1,64})\]?", text) if "Mixin" in text else [])
    if re.search(r"MixinApplyError|Mixin apply failed|InvalidMixinException|MixinTransformerError", text):
        add("mixin", "Modlar arasında uyumsuzluk (Mixin hatası)",
            ("İlgili mod(lar): " + ", ".join(mix)) if mix else "Bir mod, oyunun ya da başka bir modun kodunu değiştiremedi.",
            "Bu modun sunucu sürümüne (MC ve yükleyici) uygun sürümünü kur ya da modu geçici olarak kapatıp dene.")

    # --- aynı mod iki kez ---
    if re.search(r"[Dd]uplicate mods? found|DuplicateModsFoundException|Found a duplicate mod", text):
        dups = _uniq(re.findall(r"(?:Mod ID|mod) '(" + _ID + r")'[^\n]{0,40}from mod files?", text))
        add("dup", "Aynı mod iki kez kurulu",
            ("Mod: " + ", ".join(dups)) if dups else "mods klasöründe aynı modun iki farklı dosyası var.",
            "Modlar penceresinden eski sürümü sil.")

    # --- donma ---
    if re.search(r"A single server tick took [\d.,]+ seconds|ServerHangWatchdog", text):
        add("watchdog", "Sunucu dondu ve kendini kapattı",
            "Tek bir oyun döngüsü 60 saniyeden uzun sürdü (çok yük, sonsuz döngüye giren bir mod ya da yavaş disk).",
            "Son eklenen modları kontrol et; gerekirse server.properties'te max-tick-time=-1 yapılabilir (sorunu gizler, çözmez).")

    # --- crash raporunun "Suspected Mods" satırı ---
    if m := re.search(r"Suspected Mods?: ([^\n]{1,300})", report):
        s = m.group(1).strip()
        if s and s.lower() not in ("none", "unknown"):
            add("suspect", "Raporun şüphelendiği mod(lar)", s, "Bu modu kapatıp sunucuyu yeniden başlatarak dene.")

    desc = ""
    if m := re.search(r"^Description: ([^\n]{1,200})", report, re.M):
        desc = m.group(1).strip()
    return {"items": found[:8], "report": report_name, "description": desc}


def console_lines(res: dict) -> list[str]:
    out = []
    if res.get("report"):
        out.append(f"[panel] Crash raporu: crash-reports/{res['report']}" + (f" ({res['description']})" if res.get("description") else ""))
    for f in res["items"]:
        out.append(f"[panel] Neden: {f['title']}. {f['detail']}")
        out.append(f"[panel]   Öneri: {f['fix']}")
    if not res["items"]:
        out.append("[panel] Bilinen bir çökme nedeni bulunamadı; konsolun son satırlarına ve crash-reports klasörüne bak.")
    return out
