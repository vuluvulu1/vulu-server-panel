"""Paneli başlatır:  python run.py

reload_dirs=["app"] ÖNEMLİ: Minecraft sunucuları instances/ içine sürekli
log/dünya dosyası yazar. Tüm klasörü izlersek panel durmadan yeniden başlar.
"""
import uvicorn

from app.config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True, reload_dirs=["app"])
