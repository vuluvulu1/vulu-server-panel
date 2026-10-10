"""Paneli başlatır:  python run.py   (ya da baslat.bat / baslat.sh)

Bu betik paneli bir alt süreç olarak çalıştırır ve gözetir: panel içinden "yeniden başlat" istenince
(ör. adres/port değişince) paneli yeni ayarlarla yeniden açar. Ctrl+C ile tamamen kapanır.

Seçenekler:
  --open   panel hazır olunca tarayıcıda aç (başlatıcılar bunu kullanır)
  --dev    geliştirme modu: app/ klasöründeki kod değişince panel kendini yeniden yükler

--dev'de reload_dirs=["app"] ÖNEMLİ: Minecraft sunucuları instances/ içine sürekli
log/dünya dosyası yazar. Tüm klasörü izlersek panel durmadan yeniden başlar.
"""
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
FLAG = BASE / "data" / "restart.flag"
COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(text: str, rgb: str, bold: bool = False) -> str:
    return f"\x1b[{'1;' if bold else ''}38;2;{rgb}m{text}\x1b[0m" if COLOR else text


SAND, TAN, LIGHT, GREY, GREEN = "201;169;146", "156;112;76", "230;220;210", "130;125;120", "120;200;120"


def _tr(text: str, **kw) -> str:
    try:
        from app.i18n import _t
        return _t(text, **kw)
    except Exception:
        return text.format(**kw) if kw else text


def _say(msg: str) -> None:
    """[vulu] mesajı (terminalde vulu renkleriyle)."""
    print(f"\n{_c('[vulu]', SAND, True)} {_c(msg, LIGHT)}\n", flush=True)


def serve(dev: bool) -> None:
    import uvicorn
    from app.config import HOST, PORT
    if dev:
        uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True, reload_dirs=[str(BASE / "app")])
    else:
        # Günlük kullanımda her isteği yazmaya gerek yok: yalnızca uyarı ve hatalar görünür.
        uvicorn.run("app.main:app", host=HOST, port=PORT, access_log=False, log_level="warning")


def _settings() -> tuple[str, int]:
    """Güncel adres ve port (panel ayarları yeniden başlatmada değişmiş olabilir)."""
    import importlib
    import app.config as cfg
    cfg = importlib.reload(cfg)
    return cfg.HOST, cfg.PORT


def _lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))                # paket gönderilmez; yalnızca çıkış arayüzü seçilir
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def _when_ready(open_browser: bool) -> None:
    """Panel portu yanıt verince "çalışıyor" kutusunu yaz, istenirse tarayıcıyı aç (en fazla ~60 sn bekler)."""
    try:
        host, port = _settings()
    except Exception:
        return
    for _ in range(120):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.5)
    else:
        return
    url = f"http://127.0.0.1:{port}/"
    lines = [(_tr("Bu bilgisayardan"), url)]
    if host not in ("127.0.0.1", "localhost", "::1") and (ip := _lan_ip()):
        lines.append((_tr("Ev ağından"), f"http://{ip}:{port}/"))
    width = max(len(a) for a, _ in lines) + 2
    rule = _c("─" * 58, TAN)
    print(f"\n  {rule}", flush=True)
    print(f"  {_c('●', GREEN, True)} {_c(_tr('vulu panel çalışıyor'), SAND, True)}")
    for label, u in lines:
        print(f"    {_c(label.ljust(width), GREY)}{_c(u, LIGHT, True)}")
    print(f"    {_c(_tr('Kapatmak için bu pencerede Ctrl+C. Hatalar ve önemli olaylar burada görünür.'), GREY)}")
    print(f"  {rule}\n", flush=True)
    if not open_browser:
        return
    try:
        if os.name == "nt":
            os.startfile(url)                         # varsayılan tarayıcı (webbrowser'dan daha güvenilir)
        else:
            webbrowser.open(url)
    except Exception:
        try:
            webbrowser.open(url)
        except Exception:
            pass


def _kill_tree(p: subprocess.Popen) -> None:
    try:
        import psutil
        procs = psutil.Process(p.pid).children(recursive=True)
    except Exception:
        procs = []
    for c in procs:
        try:
            c.terminate()
        except Exception:
            pass
    p.terminate()
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        p.kill()


def supervise(dev: bool, open_browser: bool) -> None:
    env = {**os.environ, "VULU_SUPERVISED": "1"}
    args = [sys.executable, str(Path(__file__).resolve()), "--serve"] + (["--dev"] if dev else [])
    first = True
    while True:
        FLAG.unlink(missing_ok=True)
        p = subprocess.Popen(args, cwd=BASE, env=env)
        threading.Thread(target=_when_ready, args=(open_browser and first,), daemon=True).start()
        first = False
        try:
            while p.poll() is None:
                time.sleep(1)
                if FLAG.exists():                     # panel yeniden başlatma istedi (sunucuları önceden kapattı)
                    _say(_tr("Panel yeniden başlatılıyor…"))
                    _kill_tree(p)
                    break
            else:
                return                                # panel kendiliğinden kapandı
        except KeyboardInterrupt:
            try:
                p.wait(30)                            # Ctrl+C alt sürece de gider; düzgün kapanmasını bekle
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                _kill_tree(p)
            _say(_tr("Panel kapatıldı."))
            return
        time.sleep(1)


if __name__ == "__main__":
    dev = "--dev" in sys.argv
    if "--serve" in sys.argv:
        try:
            serve(dev)
        except KeyboardInterrupt:
            pass
    else:
        supervise(dev, "--open" in sys.argv)
