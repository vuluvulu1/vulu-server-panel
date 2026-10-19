r"""Unutulan panel şifresini sıfırlar. Panelin kurulu olduğu bilgisayarda, panel klasöründen çalıştırılır:

    Windows:        .venv\Scripts\python tools\reset_password.py [kullanıcı adı]
    Linux / macOS:  .venv/bin/python tools/reset_password.py [kullanıcı adı]

Yeni şifre ekrana yazılmadan iki kez sorulur; o kullanıcının açık oturumları kapanır.
Kullanıcı adı verilmezse paneldeki kullanıcılar listelenir. Panel açıkken de çalıştırılabilir.
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from app.auth import password_problem, set_password  # noqa: E402
    from app.db import get_conn  # noqa: E402
except ModuleNotFoundError:
    print("Panelin kütüphaneleri bulunamadı. Bu aracı panelin kendi Python'uyla, panel klasöründen çalıştır:")
    print(r"  Windows:        .venv\Scripts\python tools\reset_password.py")
    print("  Linux / macOS:  .venv/bin/python tools/reset_password.py")
    sys.exit(1)


def main() -> int:
    with get_conn() as c:
        users = c.execute("SELECT id, username FROM users ORDER BY id").fetchall()
    if not users:
        print("Panelde henüz kullanıcı yok; paneli açıp ilk kurulumu yap.")
        return 1

    name = sys.argv[1] if len(sys.argv) > 1 else None
    if not name:
        print("Kullanıcılar: " + ", ".join(u["username"] for u in users))
        name = users[0]["username"] if len(users) == 1 else input("Kullanıcı adı: ").strip()
    user = next((u for u in users if u["username"].lower() == name.lower()), None)
    if not user:
        print(f'"{name}" adında bir kullanıcı yok.')
        return 1

    print(f"{user['username']} için yeni şifre:")
    password = getpass.getpass("Yeni şifre: ")
    problem = password_problem(password, user["username"])
    if problem:
        print(problem)
        return 1
    if getpass.getpass("Tekrar: ") != password:
        print("Şifreler aynı değil.")
        return 1

    set_password(user["id"], password)
    with get_conn() as c:
        closed = c.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],)).rowcount
    print(f"Şifre değişti. {closed} açık oturum kapatıldı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
