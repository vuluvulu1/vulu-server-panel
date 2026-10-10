"""vulu panel başlatıcısı: baslat.bat / baslat.sh bunu çalıştırır.

Yalnızca standart kütüphaneyi kullanır (paketler kurulmadan önce çalışır):
  1. sanal ortamı (.venv) oluşturur,
  2. requirements.txt değiştiyse paketleri ilerleme çubuğuyla kurar,
  3. .env yoksa .env.example'dan oluşturur,
  4. paneli başlatır (panel hazır olunca tarayıcı açılır).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIN = os.name == "nt"
VENV = ROOT / ".venv"
VPY = VENV / ("Scripts/python.exe" if WIN else "bin/python")
REQ = ROOT / "requirements.txt"
MARK = VENV / "requirements.installed"

# ---------------------------------------------------------------- dil
_LANG = "tr"
try:
    if (ROOT / "data" / "lang.txt").read_text(encoding="utf-8").strip() == "en":
        _LANG = "en"
except OSError:
    pass

_EN = {
    "Python {v}": "Python {v}",
    "Sanal ortam oluşturuluyor": "Creating virtual environment",
    "Sanal ortam hazır": "Virtual environment ready",
    "Sanal ortam oluşturulamadı.": "Couldn't create the virtual environment.",
    "Debian/Ubuntu'da şu paket gerekir:  sudo apt install python3-venv": "On Debian/Ubuntu you need:  sudo apt install python3-venv",
    "Paketler güncel": "Packages up to date",
    "Kurulacak paketler belirleniyor": "Working out which packages to install",
    "Paketler": "Packages",
    "Kuruluyor": "Installing",
    "{n} paket kuruldu ({s} sn)": "{n} packages installed ({s} s)",
    "Paketler yüklenemedi. İnternet bağlantını kontrol edip yeniden dene.": "Couldn't install packages. Check your internet connection and try again.",
    "pip çıktısının son satırları:": "Last lines of pip output:",
    "Ayar dosyası oluşturuldu (.env)": "Settings file created (.env)",
    "Panel başlatılıyor": "Starting the panel",
    "Panel hazır olunca tarayıcıda açılacak.": "The panel opens in your browser when it's ready.",
    "Python 3.11 ya da daha yeni bir sürüm gerekli (şu an: {v}).": "Python 3.11 or newer is required (current: {v}).",
}


def T(text: str, /, **kw) -> str:
    m = _EN.get(text, text) if _LANG == "en" else text
    return m.format(**kw) if kw else m


# ---------------------------------------------------------------- renkler
def _enable_vt() -> bool:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return False
    if WIN:
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(mode)):
                k.SetConsoleMode(h, mode.value | 0x0004)      # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            return False
    return True


COLOR = _enable_vt()
TTY = sys.stdout.isatty()
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# vulu paleti (logodaki kahve → kum)
BROWN, TAN, SAND = (101, 65, 39), (156, 112, 76), (201, 169, 146)
GREEN, RED, YELLOW, GREY = (120, 200, 120), (235, 100, 90), (230, 190, 90), (130, 125, 120)


def c(text: str, rgb: tuple[int, int, int], bold: bool = False) -> str:
    if not COLOR:
        return text
    return f"\x1b[{'1;' if bold else ''}38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{text}\x1b[0m"


def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(text: str, a=BROWN, b=SAND) -> str:
    if not COLOR:
        return text
    n = max(len(text) - 1, 1)
    return "".join(c(ch, _mix(a, b, i / n)) if ch != " " else ch for i, ch in enumerate(text))


LOGO = [
    "██╗   ██╗ ██╗     ",
    "██║   ██║ ██║     ",
    "╚██╗ ██╔╝ ██║     ",
    " ╚████╔╝  ███████╗",
    "  ╚═══╝   ╚══════╝",
]


def banner() -> None:
    version = "?"
    try:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "app" / "__init__.py").read_text(encoding="utf-8"))
        version = m.group(1) if m else "?"
    except OSError:
        pass
    print()
    for i, line in enumerate(LOGO):
        col = _mix(SAND, BROWN, i / (len(LOGO) - 1))
        tail = ""
        if i == 2:
            tail = "   " + c("vulu", SAND, bold=True) + " " + c("panel", TAN, bold=True)
        elif i == 3:
            tail = "   " + c(f"v{version}", GREY)
        print("  " + c(line, col) + tail)
    print()


def ok(msg: str) -> None:
    print("  " + c("✔", GREEN, bold=True) + " " + msg, flush=True)


def fail(msg: str) -> None:
    print("  " + c("✖", RED, bold=True) + " " + c(msg, RED), flush=True)


def info(msg: str) -> None:
    print("  " + c("›", SAND, bold=True) + " " + msg, flush=True)


SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Spinner:
    """Uzun süren bir işlem sırasında dönen simge gösterir."""

    def __init__(self, text: str) -> None:
        self.text, self._stop = text, threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        i = 0
        while not self._stop.wait(0.08):
            if TTY:
                sys.stdout.write(f"\r  {c(SPIN[i % len(SPIN)], SAND, bold=True)} {self.text}…\x1b[K" if COLOR else
                                 f"\r  {SPIN[i % len(SPIN)]} {self.text}...")
                sys.stdout.flush()
            i += 1

    def __enter__(self):
        if not TTY:
            print(f"  ... {self.text}", flush=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()
        if TTY:
            sys.stdout.write("\r\x1b[K" if COLOR else "\r" + " " * (len(self.text) + 8) + "\r")
            sys.stdout.flush()


def bar(frac: float, width: int = 30) -> str:
    frac = max(0.0, min(1.0, frac))
    full = int(frac * width)
    if not COLOR:
        return "[" + "#" * full + "-" * (width - full) + "]"
    cells = []
    for i in range(width):
        if i < full:
            cells.append(c("█", _mix(BROWN, SAND, i / max(width - 1, 1))))
        else:
            cells.append(c("░", (60, 55, 50)))
    return "".join(cells)


# ---------------------------------------------------------------- adımlar
def ensure_venv() -> None:
    if VPY.exists():
        return
    with Spinner(T("Sanal ortam oluşturuluyor")):
        r = subprocess.run([sys.executable, "-m", "venv", str(VENV)], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0 or not VPY.exists():
        fail(T("Sanal ortam oluşturulamadı."))
        if not WIN:
            info(T("Debian/Ubuntu'da şu paket gerekir:  sudo apt install python3-venv"))
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-5:]
        for line in tail:
            print("    " + c(line, GREY))
        sys.exit(1)
    ok(T("Sanal ortam hazır"))


def _plan() -> list[str] | None:
    """Kurulacak paketlerin adları (pip --dry-run --report). Bilinmiyorsa None."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        r = subprocess.run([str(VPY), "-m", "pip", "install", "--disable-pip-version-check", "--dry-run", "--quiet",
                            "--report", path, "-r", str(REQ)], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            return None
        data = json.loads(Path(path).read_text(encoding="utf-8") or "{}")
        return [str(i.get("metadata", {}).get("name", "?")) for i in data.get("install", [])]
    except (OSError, ValueError):
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def install_deps() -> None:
    try:
        if MARK.read_bytes() == REQ.read_bytes():
            ok(T("Paketler güncel"))
            return
    except OSError:
        pass

    with Spinner(T("Kurulacak paketler belirleniyor")):
        plan = _plan()
    total = len(plan) if plan is not None else 0
    if plan == []:
        MARK.write_bytes(REQ.read_bytes())
        ok(T("Paketler güncel"))
        return

    started = time.monotonic()
    state = {"done": 0, "name": "", "phase": "collect", "lines": []}
    p = subprocess.Popen([str(VPY), "-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "off",
                          "-r", str(REQ)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace")

    def reader() -> None:
        for line in p.stdout:
            line = line.rstrip()
            state["lines"] = (state["lines"] + [line])[-30:]
            if m := re.match(r"\s*Collecting ([A-Za-z0-9_.\-\[\]]+)", line):
                state["done"] += 1
                state["name"] = re.split(r"[\[<>=!~ ]", m.group(1))[0]
            elif line.startswith("Installing collected packages"):
                state["phase"] = "install"
                state["name"] = ""

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    i = 0
    last_plain = -1
    while t.is_alive() or p.poll() is None:
        if state["phase"] == "install":
            frac, label = 0.9, T("Kuruluyor")
        else:
            frac = (min(state["done"], total) / total * 0.85) if total else 0.0
            label = state["name"]
        count = f"{min(state['done'], total)}/{total}" if total else str(state["done"])
        if TTY:
            spin = SPIN[i % len(SPIN)]
            line = (f"\r  {c(spin, SAND, bold=True)} {T('Paketler'):<9} {bar(frac)} {c(f'{int(frac * 100):>3}%', SAND, bold=True)}"
                    f"  {c(count, GREY)}  {label[:24]}")
            sys.stdout.write(line + ("\x1b[K" if COLOR else "   "))
            sys.stdout.flush()
        elif int(frac * 10) != last_plain:
            last_plain = int(frac * 10)
            print(f"  {T('Paketler')} {int(frac * 100)}%", flush=True)
        i += 1
        time.sleep(0.08)
    p.wait()
    t.join()
    if TTY:
        sys.stdout.write("\r\x1b[K" if COLOR else "\r" + " " * 90 + "\r")
    if p.returncode != 0:
        fail(T("Paketler yüklenemedi. İnternet bağlantını kontrol edip yeniden dene."))
        print("    " + c(T("pip çıktısının son satırları:"), GREY))
        for line in state["lines"][-12:]:
            print("    " + c(line, GREY))
        sys.exit(1)
    MARK.write_bytes(REQ.read_bytes())
    n = total or state["done"]
    ok(f"{T('Paketler'):<9} {bar(1.0)} {c('100%', GREEN, bold=True)}")
    ok(T("{n} paket kuruldu ({s} sn)", n=n, s=int(time.monotonic() - started)))


def ensure_env() -> None:
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists() and example.exists():
        env.write_bytes(example.read_bytes())
        ok(T("Ayar dosyası oluşturuldu (.env)"))


def launch() -> int:
    print()
    info(c(T("Panel başlatılıyor"), SAND, bold=True))
    print("    " + c(T("Panel hazır olunca tarayıcıda açılacak."), GREY))
    print()
    args = [str(VPY), str(ROOT / "run.py"), "--open"]
    if not WIN:
        os.chdir(ROOT)
        os.execv(str(VPY), args)
    p = subprocess.Popen(args, cwd=ROOT)
    while True:
        try:
            return p.wait()
        except KeyboardInterrupt:          # Ctrl+C panele de gider; düzgün kapanmasını bekle
            continue


def main() -> int:
    if sys.version_info < (3, 11):
        fail(T("Python 3.11 ya da daha yeni bir sürüm gerekli (şu an: {v}).", v=sys.version.split()[0]))
        return 1
    banner()
    ok(T("Python {v}", v=sys.version.split()[0]))
    ensure_venv()
    install_deps()
    ensure_env()
    return launch()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
