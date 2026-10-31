#!/usr/bin/env sh
# Chạy game (cần máy chủ đang chạy, xem chay_server.sh)
cd "$(dirname "$0")"
python3 -m pip install -r client/requirements.txt
[ -f client/assets/fonts/NotoSansSC-Game.otf ] || python3 tools/fetch_assets.py
python3 -m client.main
