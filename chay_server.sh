#!/usr/bin/env sh
# Chạy máy chủ trên máy của bạn (http://127.0.0.1:8000)
cd "$(dirname "$0")/server"
python3 -m pip install -r requirements.txt || exit 1
[ -f .env ] || cp .env.example .env
python3 -m uvicorn app.main:app --port 8000
