import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id   INTEGER NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,                 -- restart | backup
    time_hm       TEXT NOT NULL,                 -- "04:00" (yerel saat)
    days          TEXT NOT NULL DEFAULT '1234567',  -- 1=Pzt ... 7=Paz
    warn_minutes  INTEGER NOT NULL DEFAULT 5,    -- restart: oyunculara kaç dk önce uyarı
    backup_mode   TEXT NOT NULL DEFAULT 'world', -- backup: full | world
    keep          INTEGER NOT NULL DEFAULT 7,    -- backup: kaç otomatik yedek saklansın
    enabled       INTEGER NOT NULL DEFAULT 1,
    last_run      TEXT,                          -- "2026-10-10 04:00" (aynı dilimde iki kez çalışmasın)
    last_result   TEXT,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'admin',
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS instances (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    path          TEXT NOT NULL,
    port          INTEGER NOT NULL DEFAULT 25565,
    java_path     TEXT NOT NULL DEFAULT 'java',
    jar_file      TEXT NOT NULL DEFAULT 'server.jar',
    mc_version    TEXT,
    loader        TEXT NOT NULL DEFAULT 'vanilla',
    java_major    INTEGER,
    launch_type   TEXT NOT NULL DEFAULT 'jar',
    args_file     TEXT,
    jvm_preset    TEXT NOT NULL DEFAULT 'none',
    jvm_args      TEXT NOT NULL DEFAULT '',
    ram_mb        INTEGER NOT NULL DEFAULT 4096,
    rcon_port     INTEGER,
    rcon_password TEXT,
    profile_id    TEXT,
    modpack_slug  TEXT,
    backup_limit  INTEGER,
    modpack_version TEXT,
    status        TEXT NOT NULL DEFAULT 'stopped',
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Eski veritabanlarına sonradan eklenen sütunları ekler."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(instances)")}
    if "jar_file" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN jar_file TEXT NOT NULL DEFAULT 'server.jar'")
    if "mc_version" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN mc_version TEXT")
    if "loader" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN loader TEXT NOT NULL DEFAULT 'vanilla'")
    if "java_major" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN java_major INTEGER")
    if "launch_type" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN launch_type TEXT NOT NULL DEFAULT 'jar'")
    if "args_file" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN args_file TEXT")
    if "backup_limit" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN backup_limit INTEGER")
    if "modpack_slug" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN modpack_slug TEXT")
    if "modpack_version" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN modpack_version TEXT")
    if "jvm_preset" not in cols:
        conn.execute("ALTER TABLE instances ADD COLUMN jvm_preset TEXT NOT NULL DEFAULT 'none'")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def get_instance(instance_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM instances WHERE id = ?", (instance_id,)).fetchone()
    return dict(row) if row else None


def used_ports() -> set[int]:
    with get_conn() as conn:
        rows = conn.execute("SELECT port, rcon_port FROM instances").fetchall()
    return {p for r in rows for p in (r["port"], r["rcon_port"]) if p}


def update_instance(instance_id: int, **fields) -> None:
    allowed = {"rcon_port", "rcon_password", "launch_type", "jar_file", "args_file", "port", "ram_mb", "jvm_preset", "jvm_args", "java_path", "java_major", "backup_limit", "mc_version"}          # sütun adları beyaz listeden (SQL enjeksiyonu yok)
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"izin verilmeyen sütun: {bad}")
    sets = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE instances SET {sets} WHERE id = ?", (*fields.values(), instance_id))
