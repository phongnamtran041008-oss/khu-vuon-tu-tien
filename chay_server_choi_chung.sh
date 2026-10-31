#!/usr/bin/env bash
# Mở máy chủ cho các máy khác trong cùng mạng (hoặc qua Cloudflare Tunnel)
cd "$(dirname "$0")/server" || exit 1
python3 -m pip install -r requirements.txt || exit 1
[ -f .env ] || cp .env.example .env
echo "Địa chỉ của máy này:"; (hostname -I 2>/dev/null || ipconfig getifaddr en0) | tr ' ' '\n' | sed '/^$/d; s/.*/    http:\/\/&:8000/'
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
