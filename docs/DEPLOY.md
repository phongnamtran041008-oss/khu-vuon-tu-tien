# Triển khai Khu Vườn Tu Tiên (0 đồng)

> Thông tin các gói miễn phí lấy theo đặc tả (kiểm tra tháng 10/2026) và **có thể đã thay đổi**. Trước khi triển khai,
> đọc lại trang giá chính thức của Oracle Cloud, Render, Neon, Cloudflare và sửa tài liệu này nếu khác.

> **Không muốn thuê máy chủ?** Từ bản 1.1, chỉ cần game: người chơi tự mở thế giới trên máy mình và bạn bè cùng mạng LAN
> vào chơi (kiểu Minecraft, tài khoản Firebase) — xem README, mục "Chơi kiểu Minecraft". Tài liệu này dành cho ai muốn một
> máy chủ chạy 24/7 cho mọi người. Máy chủ riêng có thể dùng tài khoản Firebase luôn: đặt `FIREBASE_API_KEY`.

Cùng một mã nguồn chạy được cả ba phương án; chỉ đổi biến môi trường.

| | A. Oracle Cloud Always Free | B. Render + Neon | C. Máy nhà + Cloudflare Tunnel |
|---|---|---|---|
| Chạy 24/7 | ✅ | ❌ ngủ sau 15 phút không ai chơi, ~1 phút để thức | chỉ khi máy bật |
| Cần thẻ ngân hàng | có (chỉ để xác minh) | không | không |
| Cơ sở dữ liệu | PostgreSQL trong máy ảo | Neon Free (0,5 GB, 100 giờ tính toán/tháng) | PostgreSQL hoặc SQLite trên máy bạn |
| Địa chỉ | tên miền DuckDNS + HTTPS tự động | `https://<tên>.onrender.com` | quick tunnel đổi mỗi lần chạy |
| Hợp với | game chạy thật cho nhiều người | thử với bạn bè | chơi tối nay với vài người bạn |

Các file liên quan:

```
server/Dockerfile           image máy chủ (build được cho linux/amd64 và linux/arm64)
deploy/docker-compose.yml   máy chủ + PostgreSQL + Caddy (HTTPS) + sao lưu hằng ngày
deploy/Caddyfile            reverse proxy HTTPS (WebSocket đi qua tự động)
deploy/.env.example         mọi biến môi trường của phương án A và C
deploy/server_list.json     danh sách máy chủ mà game tự đọc (server_list_url)
render.yaml                 Blueprint cho phương án B
tools/backup_db.sh|.py      sao lưu, giữ 7 bản
tools/build_exe.py          đóng gói VuonChu.exe (dong_goi_exe.bat trên Windows)
.github/workflows/          build exe khi đẩy tag, build image arm64+amd64, chạy test
```

---

## 0. Chuẩn bị chung

1. **Đưa mã nguồn lên GitHub** (repo công khai hoặc riêng tư đều được). Không đưa `server/.env`, `server/dev.db`,
   `deploy/.env` lên — `.gitignore` đã chặn sẵn.
2. **Tạo chuỗi bí mật** cho `JWT_SECRET` (ít nhất 32 ký tự; máy chủ `ENV=prod` từ chối khởi động nếu thiếu):
   ```bash
   python -c "import secrets;print(secrets.token_hex(32))"
   ```
3. **Chọn tài khoản quản trị**: đặt `ADMIN_USERNAMES=ten_dang_nhap_cua_ban` trong biến môi trường. Tài khoản đó có quyền
   gõ `/admin ...` trong chat (xem mục 6). Có thể đăng ký tài khoản sau khi máy chủ chạy; quyền được cấp lúc đăng ký.

Sau khi máy chủ chạy, mở `https://<địa chỉ>/server/info` trên trình duyệt: phải thấy trang "Máy chủ đang chạy" với số
người online, phiên bản, và nút tải game (nếu đặt `CLIENT_DOWNLOAD_URL`).

---

## A. Oracle Cloud Always Free (khuyến nghị cho 24/7)

Theo đặc tả, tài khoản mới có khoảng **2 OCPU / 12 GB RAM** máy ARM Ampere A1 miễn phí, chạy liên tục. Đăng ký cần thẻ
để xác minh (không bị trừ tiền nếu ở trong hạn mức); một số vùng hay hết máy ARM — thử lại vào giờ khác hoặc vùng khác.

### A1. Tạo máy ảo

1. Đăng ký tại cloud.oracle.com, chọn **Home Region** gần Việt Nam (Singapore, Tokyo...). Vùng nhà không đổi được.
2. **Compute → Instances → Create instance**:
   - Image: **Ubuntu 24.04** (hoặc 22.04), bản **aarch64**.
   - Shape: **Ampere → VM.Standard.A1.Flex**, 2 OCPU, 12 GB (hoặc theo hạn mức của bạn). Kiểm tra dòng "Always Free-eligible".
   - Tải về khóa SSH (private key) và giữ cẩn thận.
3. Ghi lại **Public IP** của máy.
4. Mở cổng: **Networking → Virtual Cloud Networks → (VCN của máy) → Security Lists → Default → Add Ingress Rules**:
   nguồn `0.0.0.0/0`, TCP cổng `80` và `443` (thêm UDP `443` nếu muốn HTTP/3).
5. SSH vào máy (`ssh -i khoa.key ubuntu@<IP>`). Ảnh Ubuntu của Oracle có sẵn luật iptables chặn mọi cổng trừ 22; mở 80/443:
   ```bash
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

### A2. Tên miền miễn phí (DuckDNS)

1. Vào duckdns.org, đăng nhập (GitHub/Google), tạo subdomain, ví dụ `vuonchu` → `vuonchu.duckdns.org`.
2. Điền **Public IP** của máy vào ô `current ip`, bấm **update ip**.
   (IP công khai của máy Oracle giữ nguyên khi khởi động lại; nếu bạn đổi máy thì cập nhật lại.)

Không muốn mở cổng? Dùng **Cloudflare Tunnel có tên** (cần một tên miền quản lý trên Cloudflare): bỏ qua bước mở cổng,
chạy `docker compose up -d` (không có `--profile https`) rồi tạo tunnel trỏ về `http://localhost:8000` theo hướng dẫn của
Cloudflare. Phần còn lại giống hệt.

### A3. Chạy máy chủ

```bash
# cài Docker (script chính thức, hỗ trợ ARM)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker

git clone https://github.com/<tai-khoan>/<repo>.git khuvuon && cd khuvuon/deploy
cp .env.example .env
nano .env        # POSTGRES_PASSWORD, JWT_SECRET, DOMAIN=vuonchu.duckdns.org, ADMIN_USERNAMES, CLIENT_DOWNLOAD_URL
docker compose --profile https up -d --build
docker compose logs -f server        # chờ dòng "server ready", Ctrl+C để thoát xem log
```

Lần đầu build mất vài phút (máy ARM tự build image `linux/arm64`). Muốn khỏi build trên máy: đẩy tag lên GitHub để
`.github/workflows/docker.yml` dựng image cho cả arm64 và amd64, rồi đặt
`SERVER_IMAGE=ghcr.io/<tai-khoan>/khu-vuon-tu-tien-server:latest` trong `.env` và chạy `docker compose pull && docker compose --profile https up -d`.
(Image trên GHCR mặc định là riêng tư: đặt public trong trang Packages, hoặc `docker login ghcr.io` trên máy.)

Caddy tự lấy chứng chỉ HTTPS trong vài giây. Kiểm tra: `https://vuonchu.duckdns.org/server/info`.

### A4. Cập nhật phiên bản mới

```bash
cd ~/khuvuon && git pull
# báo trước cho người chơi (trong game, tài khoản quản trị):  /admin maintenance Cập nhật lúc 23:00, khoảng 5 phút
cd deploy && docker compose --profile https up -d --build
```

Máy chủ lưu vị trí mọi người khi tắt, rồi tự nâng cấp cơ sở dữ liệu (Alembic) khi khởi động lại.
Gỡ thông báo: `/admin maintenance off`.

### A5. Thử tải trên máy chủ thật

Chạy `tools/load_bots.py` **từ một máy khác** (máy của bạn), không phải trên chính máy chủ:

```bash
# trên máy chủ: tạm cho phép nhiều tài khoản một IP rồi khởi động lại server
#   thêm vào deploy/.env:  ACCOUNTS_PER_IP=500  và  RATE_LIMIT=0   →  docker compose up -d
python tools/load_bots.py --server https://vuonchu.duckdns.org --bots 50 --minutes 10 --report ketqua.json
# xong thì xóa hai dòng đó khỏi .env và khởi động lại
```

Ghi kết quả vào bảng dưới. Kết quả đo trên máy dựng (container 2 nhân, máy chủ và bot chung máy) nằm ở `LOAD_TEST.md`:
50 bot, 10 phút, tick trung bình 2,3 ms, lâu nhất 38 ms.

| Ngày | Máy | Số bot | Tick TB / p99 / lâu nhất | Ping trung vị | Bị ngắt | Ghi chú |
|---|---|---|---|---|---|---|
| _(chưa chạy trên máy Oracle thật)_ | | | | | | |

---

## B. Render (free web service) + Neon (Postgres miễn phí) — không cần thẻ

Render free: hỗ trợ WebSocket nhưng **ngủ sau 15 phút** không có request/tin nhắn WebSocket, ~1 phút để thức, đĩa không
giữ lại khi khởi động lại, 750 giờ/tháng cho cả workspace. **Không dùng Postgres của Render** (hết hạn sau 30 ngày).
Neon Free: không cần thẻ, không hết hạn, dung lượng nhỏ (~0,5 GB/project), **100 giờ tính toán (CU-hour)/tháng**, tự tạm
dừng khi rảnh.

### B1. Neon

1. Đăng ký neon.tech, **Create project**, vùng **AWS Asia Pacific (Singapore)**, Postgres 16 hoặc 17.
2. **Connect** → chọn kết nối **trực tiếp** (tắt "Connection pooling"), sao chép chuỗi dạng
   `postgresql://user:pass@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`.
   Máy chủ tự đổi `sslmode`/`channel_binding` sang dạng asyncpg hiểu; chuỗi "pooled" (`-pooler`) cũng chạy được.

### B2. Render

1. Đăng ký render.com bằng GitHub. **New → Blueprint** → chọn repo; Render đọc `render.yaml`.
2. Điền khi được hỏi: `DATABASE_URL` (chuỗi Neon ở trên), `ADMIN_USERNAMES`, `CLIENT_DOWNLOAD_URL`.
   `JWT_SECRET` Render tự sinh.
3. Chờ build (5–10 phút lần đầu). Địa chỉ: `https://khu-vuon-tu-tien.onrender.com` (hoặc tên Render đặt).
   Mở `/server/info` để kiểm tra.

### B3. Điều chỉnh cho gói miễn phí (đã làm sẵn trong code)

- Gom ghi: vị trí/máu ghi 60 giây một lần trong một transaction; không truy vấn DB trong tick (mục 15.2).
- Pool nhỏ: `DB_POOL_SIZE=2`.
- `DB_IDLE_CLOSE_SECONDS=240`: không ai chơi 4 phút thì máy chủ đóng các kết nối đang mở, để Neon tạm dừng và không
  tính giờ. Người tiếp theo vào thì kết nối lại (chậm thêm ~1 giây).
- `/healthz` (Render dùng để kiểm tra sống) không chạm DB, nên không đánh thức Neon.
- Không ghi file nào lên đĩa máy chủ.
- Game: khi Render đang ngủ, màn đăng nhập hiện "Máy chủ đang khởi động, chờ khoảng 1 phút..." và tự thử lại.

Ước lượng: Neon tính 100 CU-giờ; chạy ở 0,25 CU là khoảng 400 giờ có người chơi mỗi tháng (~13 giờ/ngày).
Nhiều hơn thì nên chuyển sang phương án A.

### B4. Quản trị và sao lưu trên Render

Gói free không có shell, nên tài khoản quản trị cấp bằng `ADMIN_USERNAMES` (đổi trong Environment rồi deploy lại).
Sao lưu Neon từ máy của bạn (cần `pg_dump` — cài "PostgreSQL command line tools"):

```bash
python tools/backup_db.py --database-url "postgresql://...neon.tech/neondb?sslmode=require" --dir D:/sao-luu-vuonchu
```

Neon còn có tính năng khôi phục về một thời điểm gần đây trong trang quản lý (độ dài lịch sử tùy gói — xem trang Neon).

---

## C. Máy của chính mình + Cloudflare Tunnel

Cách nhanh nhất để chơi cùng bạn bè tối nay. Máy chủ chỉ sống khi máy bật.

### C1. Chạy máy chủ

Cách đơn giản (Windows, SQLite): nháy đúp `chay_server_choi_chung.bat`.

Hoặc bằng Docker (PostgreSQL + sao lưu hằng ngày, giống phương án A nhưng không có Caddy):

```bash
cd deploy && cp .env.example .env     # điền POSTGRES_PASSWORD, JWT_SECRET; để trống DOMAIN
docker compose up -d --build
```

### C2. Mở ra Internet

Tải `cloudflared` (trang Downloads của Cloudflare), chạy:

```bash
cloudflared tunnel --url http://localhost:8000
```

Nó in một địa chỉ `https://<tên-ngẫu-nhiên>.trycloudflare.com`. Đặt `TRUST_PROXY_HEADERS=1` (đã có trong
`deploy/.env.example`; với `chay_server_choi_chung.bat` thì sửa `server/.env`) để giới hạn tài khoản/IP tính đúng IP thật.

### C3. Địa chỉ đổi mỗi lần — để game tự nhận

Quick tunnel cho địa chỉ mới mỗi lần chạy. Thay vì nhắn địa chỉ mới cho mọi người:

1. Build exe một lần với `--server-list-url` trỏ vào link raw của `deploy/server_list.json` trong repo GitHub:
   `https://raw.githubusercontent.com/<tai-khoan>/<repo>/main/deploy/server_list.json`
2. Mỗi lần chạy tunnel, sửa `url` trong `deploy/server_list.json` trên GitHub thành địa chỉ mới (sửa ngay trên web GitHub
   được) và commit.
3. Lần mở game sau, game đọc danh sách, thấy địa chỉ đã lưu không còn trong danh sách thì chuyển sang địa chỉ mới.
   (GitHub có thể lưu đệm link raw vài phút.) Ai đã tự gõ máy chủ trong **Cài đặt** thì game giữ địa chỉ đó; xóa trống ô
   **Máy chủ** rồi **Lưu** để quay về danh sách.

Muốn địa chỉ cố định: dùng tunnel có tên với tên miền của bạn trên Cloudflare (miễn phí, cần có tên miền).

---

## D. Phát hành game (exe) qua GitHub Releases

### D1. Build trên máy Windows

```bat
dong_goi_exe.bat --server-url https://vuonchu.duckdns.org --server-list-url https://raw.githubusercontent.com/<tai-khoan>/<repo>/main/deploy/server_list.json
```

(hoặc `python tools/build_exe.py ...`). Kết quả:

- `dist/VuonChu/VuonChu.exe` + `_internal/` (Python, pygame, font, bản đồ, âm thanh nếu đã sinh), `config.json`,
  `DOC_TRUOC.txt` (hướng dẫn cho người chơi), `CREDITS.md`, `LICENSES.md`.
- `dist/VuonChu-<phiên bản>-windows.zip` — file đưa lên Releases (~30 MB).

Script tự **chạy thử exe** (`VuonChu.exe --smoke-test`): mọi module của game phải nạp được và font, bản đồ phải đọc được
từ trong gói; nếu thiếu gì, build báo lỗi thay vì tạo ra một gói hỏng. Muốn có giọng đọc phát âm trong gói, chạy
`python tools/generate_audio.py` trước khi build.

### D2. Build tự động bằng GitHub Actions

1. Repo → **Settings → Secrets and variables → Actions → Variables**: thêm `SERVER_URL` và (nếu dùng) `SERVER_LIST_URL`.
2. Đổi `GAME_VERSION` trong `client/config.py` và `server/app/config.py` nếu ra bản mới, commit, rồi:
   ```bash
   git tag v1.0.0 && git push origin v1.0.0
   ```
3. `.github/workflows/release.yml` build exe trên Windows (kèm chạy thử) và đính zip vào Release của tag.
   Link cho người chơi: `https://github.com/<tai-khoan>/<repo>/releases/latest` — đặt vào `CLIENT_DOWNLOAD_URL` để
   trang `/server/info` và game hiện nút/đường dẫn tải.

### D3. Người chơi

Tải zip, giải nén, chạy `VuonChu.exe`. Exe chưa ký số nên lần đầu Windows SmartScreen có thể chặn: **More info → Run
anyway**. `config.json`/`session.json` nằm cạnh exe; nếu thư mục không ghi được (vd giải nén vào Program Files), game ghi
vào `%LOCALAPPDATA%\KhuVuonTuTien`. Lỗi làm game tắt được ghi vào `vuonchu_loi.txt` và báo bằng hộp thoại.

Khi máy chủ có giao thức mới hơn game, menu báo "Phiên bản game đã cũ" kèm link tải (từ `CLIENT_DOWNLOAD_URL`); khi
chỉ có exe mới hơn (`LATEST_CLIENT_VERSION`), menu nhắc nhẹ "Đã có bản v...".

---

## E. Sao lưu và khôi phục

**Docker (A, C):** dịch vụ `backup` trong `docker-compose.yml` sao lưu ngay khi khởi động rồi mỗi ngày lúc
`BACKUP_HOUR_UTC` (mặc định 20 giờ UTC = 3 giờ sáng VN), giữ `BACKUP_KEEP` bản (mặc định 7) trong `deploy/backups/`
(file `khuvuon-YYYYmmdd-HHMMSS.sql.gz`). Nên chép thư mục này ra ngoài máy chủ định kỳ:
`scp -r ubuntu@<IP>:khuvuon/deploy/backups ./`.

Khôi phục vào cơ sở dữ liệu trống:

```bash
cd deploy
docker compose stop server
docker compose exec -T db psql -U khuvuon -d postgres -c "DROP DATABASE khuvuon;" -c "CREATE DATABASE khuvuon OWNER khuvuon;"
gunzip -c backups/khuvuon-20261101-200000.sql.gz | docker compose exec -T db psql -U khuvuon -d khuvuon
docker compose start server
```

**SQLite (chạy bằng `chay_server.bat`):** nháy đúp `sao_luu.bat` (hoặc `python tools/backup_db.py`) → `backups/`, giữ 7
bản; sao lưu được cả khi máy chủ đang chạy. Chạy tự động mỗi ngày bằng Task Scheduler:

```bat
schtasks /Create /SC DAILY /ST 03:00 /TN "KhuVuon sao luu" /TR "\"C:\duong\dan\khu-vuon-tu-tien\sao_luu.bat\""
```

Khôi phục: tắt máy chủ, chép file `.db` đã sao lưu đè lên `server\dev.db` (xóa `dev.db-wal` và `dev.db-shm` nếu có),
mở lại máy chủ.

**Linux không Docker:** `DATABASE_URL=... BACKUP_DIR=... sh tools/backup_db.sh` trong cron:
`0 20 * * * cd /home/ubuntu/khuvuon && DATABASE_URL=postgresql://... sh tools/backup_db.sh >> backup.log 2>&1`.

---

## F. Quản trị

Cấp quyền: `ADMIN_USERNAMES` (mọi phương án), hoặc trên máy có shell:

```bash
docker compose exec server python -m app.admin_cli grant ten_dang_nhap     # Docker
cd server && python -m app.admin_cli grant ten_dang_nhap                   # chạy trực tiếp
python -m app.admin_cli admins                                             # ai đang là quản trị
```

Trong game, tài khoản quản trị gõ trong khung chat (dòng `/admin` không bao giờ hiện cho người khác):

| Lệnh | Việc |
|---|---|
| `/admin help` | danh sách lệnh |
| `/admin mute <tên> <thời hạn> [lý do]` | cấm chat (`30m`, `2h`, `7d`, `1w`, `vinhvien`) |
| `/admin unmute <tên>` | bỏ cấm chat |
| `/admin ban <tên> <thời hạn> [lý do]` | khóa tài khoản có thời hạn, đá khỏi game ngay |
| `/admin unban <tên>` | mở khóa |
| `/admin kick <tên>` | ngắt kết nối (vào lại được) |
| `/admin announce <nội dung>` / `announce off` | thông báo toàn máy chủ (hiện cả ở menu và `/server/info`) |
| `/admin maintenance <nội dung>` / `maintenance off` | thông báo bảo trì ở màn đăng nhập |
| `/admin online` | ai đang online |
| `/admin who <tên>` | cảnh giới, ngày tạo, lần đăng nhập, khóa/cấm chat, số lần bị báo cáo |
| `/admin flagged` / `unflag <tên>` | tài khoản bị nghi dùng bot (200 câu đúng liền, mỗi câu dưới 0,5 giây) |
| `/admin reports` | 10 báo cáo chat gần nhất |
| `/admin log` | 10 lệnh quản trị gần nhất (mọi lệnh đều ghi vào bảng `admin_actions`) |
| `/admin timescale <số>` | tua thời gian — chỉ máy chủ `ENV=dev` |

`<tên>` là đạo hiệu (có dấu cách cũng được) hoặc `@tên_đăng_nhập`. Tên tiếng Việt cũng gõ được: `/admin camchat`,
`khoa`, `mokhoa`, `thongbao`, `baotri`, `xem`... Quản trị viên không dùng được lệnh với chính mình hay quản trị viên khác;
từ dòng lệnh máy chủ (`app.admin_cli`) thì được. Không có gì tự động cấm ai: hệ thống chỉ đánh dấu để người xem.

---

## G. Kiểm tra sau khi triển khai (tiêu chí giai đoạn 10)

1. `https://<địa chỉ>/server/info` mở được trên điện thoại (mạng di động) — trang "Máy chủ đang chạy".
2. Tạo Release; **hai người ở hai mạng khác nhau** tải zip từ GitHub Releases, giải nén, chạy `VuonChu.exe`.
3. Mỗi người đăng ký một tài khoản, tạo nhân vật, ra Trúc Lâm Thôn: thấy nhau đi lại, chat được, lập tổ đội.
4. Tài khoản quản trị gõ `/admin announce Chào mừng!` → cả hai thấy thông báo.
5. Sau một ngày: có file sao lưu mới trong `deploy/backups/` (A, C) hoặc đã chạy `tools/backup_db.py` (B).
