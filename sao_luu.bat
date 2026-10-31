@echo off
chcp 65001 >nul
rem Sao luu co so du lieu (server\dev.db hoac DATABASE_URL trong server\.env) vao thu muc backups\, giu 7 ban
cd /d %~dp0
python tools\backup_db.py %*
pause
