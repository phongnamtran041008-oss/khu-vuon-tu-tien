@echo off
chcp 65001 >nul
rem Chay game (can may chu dang chay, xem chay_server.bat)
cd /d %~dp0
python -m pip install -r client\requirements.txt
if errorlevel 1 (
  echo [LOI] Cai thu vien cho game that bai. Hay chup man hinh gui lai.
  pause
  exit /b 1
)
if not exist client\assets\fonts\NotoSansSC-Game.otf python tools\fetch_assets.py
python -m client.main
if errorlevel 1 pause
