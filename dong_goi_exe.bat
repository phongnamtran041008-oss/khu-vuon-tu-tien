@echo off
chcp 65001 >nul
rem Dong goi game thanh dist\VuonChu\VuonChu.exe va dist\VuonChu-<phien ban>-windows.zip
rem Dia chi may chu: dong_goi_exe.bat --server-url https://ten-mien-cua-ban --server-list-url https://raw.githubusercontent.com/...
cd /d %~dp0
python -m pip install -r client\requirements.txt pyinstaller
if errorlevel 1 (
  echo [LOI] Cai thu vien that bai.
  pause
  exit /b 1
)
python tools\build_exe.py %*
pause
