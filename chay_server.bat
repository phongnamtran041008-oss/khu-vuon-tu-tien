@echo off
chcp 65001 >nul
rem Chay may chu Khu Vuon Tu Tien tren may cua ban (http://127.0.0.1:8000)
cd /d %~dp0server
python --version
echo Dang cai thu vien cho may chu...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [LOI] Cai thu vien that bai. Hay chup man hinh cua so nay gui lai.
  pause
  exit /b 1
)
if not exist .env copy .env.example .env
echo.
echo May chu dang chay tai http://127.0.0.1:8000  - DE CUA SO NAY MO trong luc choi.
python -m uvicorn app.main:app --port 8000
echo.
echo [!] May chu da dung. Neu ben tren co chu "Error" hoac "Traceback", hay chup man hinh gui lai.
pause
