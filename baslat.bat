@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title vulu panel

rem ============================================================
rem  vulu panel başlatıcı (Windows)
rem  Python'u bulur, gerisini tools\launcher.py yapar:
rem  sanal ortam, paket kurulumu, paneli başlatma.
rem ============================================================

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if defined PY goto run
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=py -3"
if defined PY goto run
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
if defined PY goto run

echo.
echo  [vulu] Python 3.11 ya da daha yeni bir sürüm bulunamadı.
echo.
where winget >nul 2>nul
if errorlevel 1 goto nopython
choice /c EH /n /m " Python 3.12 şimdi kurulsun mu? [E/H] "
if errorlevel 2 goto nopython
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto nopython
echo.
echo  [vulu] Python kuruldu. Bu pencereyi kapatıp baslat.bat'ı yeniden çalıştır.
echo.
pause
exit /b 0

:nopython
echo  Python'u https://www.python.org/downloads/ adresinden indirip kur.
echo  Kurulumda "Add python.exe to PATH" kutusunu işaretlemeyi unutma,
echo  ardından baslat.bat'ı yeniden çalıştır.
echo.
pause
exit /b 1

:run
%PY% tools\launcher.py
if errorlevel 1 if not errorlevel 130 pause
