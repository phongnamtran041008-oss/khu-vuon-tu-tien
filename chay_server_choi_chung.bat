@echo off
chcp 65001 >nul
rem Mo may chu cho ca nha / ban be cung choi (cung mang Wi-Fi, hoac qua Cloudflare Tunnel)
cd /d %~dp0server
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [LOI] Cai thu vien that bai. Hay chup man hinh cua so nay gui lai.
  pause
  exit /b 1
)
if not exist .env copy .env.example .env
echo.
echo ===============================================================
echo  May chu mo cho moi may trong cung mang. Dia chi cua may nay:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=*" %%b in ("%%a") do echo     http://%%b:8000
echo  Ban be vao game - Cai dat - Dia chi may chu, go dia chi tren
echo  (vi du http://192.168.1.5:8000). Windows co hoi tuong lua thi bam "Allow".
echo  Choi qua Internet: xem muc "Choi cung ban be" trong README.md
echo ===============================================================
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
echo.
echo [!] May chu da dung. Neu ben tren co chu "Error" hoac "Traceback", hay chup man hinh gui lai.
pause
