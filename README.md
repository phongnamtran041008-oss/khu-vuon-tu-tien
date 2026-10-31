# Khu Vườn Tu Tiên · 字园仙途

**Tải game (Windows):** [trang Releases](https://github.com/phongnamtran041008-oss/khu-vuon-tu-tien/releases/latest) →
tải `VuonChu-<phiên bản>-windows.zip` → giải nén → chạy `VuonChu\VuonChu.exe`. Có bản mới thì game tự báo lúc mở.

Game tu tiên 2D pixel online để học tiếng Trung (giản thể + pinyin), giao diện tiếng Việt.
Trồng cây chữ theo lịch ôn ngắt quãng, quay gacha hạt giống, đánh quái bằng câu đố, nuôi ong linh,
câu cá, giữ vườn trước Mặc Quái, luyện đan, vượt bí cảnh cùng bạn bè — học là cách duy nhất để mạnh lên.

> **Bản 1.1 — Thế giới LAN, không cần thuê máy chủ (kiểu Minecraft).**
> Đăng ký/đăng nhập bằng **email + mật khẩu qua Firebase Authentication** (tài khoản dùng chung cho mọi thế giới, lần sau
> game tự đăng nhập). **Thế giới lưu ngay trên máy**: tab *Thế giới của tôi* → Tạo → **Mở thế giới** — game tự chạy máy
> chủ của thế giới đó trên máy bạn (ẩn, trong cùng exe) và mở cho mạng LAN. Bạn bè cùng Wi-Fi/LAN vào tab *Tham gia mạng
> LAN*: game tự tìm thấy thế giới (tín hiệu UDP), hoặc gõ `192.168.x.x:8000`. Mọi dữ liệu của người vào chơi nằm trên máy
> người mở thế giới (`worlds/<tên>/world.db`); người mở là quản trị viên (`/admin ...`). Xem mục
> [Chơi kiểu Minecraft](#chơi-kiểu-minecraft-thế-giới-lan-bản-11). Máy chủ riêng (giai đoạn 10, `docs/DEPLOY.md`) vẫn dùng được.
>
> **Giai đoạn 10/10 — Phát hành (bản 1.0.0).**
> Game đóng gói thành **`VuonChu.exe`** (`dong_goi_exe.bat` hoặc tự động bằng GitHub Actions khi đẩy tag, đính vào GitHub
> Releases); exe tự chạy thử sau khi build. Máy chủ có **Docker** (chạy được trên máy ARM `linux/arm64` của Oracle),
> `docker-compose` với PostgreSQL + Caddy (HTTPS tự động) + **sao lưu hằng ngày giữ 7 bản**, Blueprint cho **Render + Neon**,
> và hướng dẫn đủ **3 phương án triển khai miễn phí** trong [`docs/DEPLOY.md`](docs/DEPLOY.md). Trang **`/server/info`**
> mở bằng trình duyệt thấy trạng thái máy chủ và nút tải game; game kiểm tra phiên bản lúc mở và hiện thông báo bảo trì.
> `server_list_url` giờ tự đổi sang địa chỉ máy chủ mới (quick tunnel) mà không cần exe mới. **Lệnh quản trị** gõ trong
> chat: `/admin ban|mute|kick|announce|maintenance|who|flagged|reports|timescale ...`; tài khoản trả lời nhanh bất thường
> 200 câu liền bị đánh dấu cho quản trị viên xem.
>
> Giai đoạn 9 (vẫn đầy đủ): **Tổ đội** 2–5 người (phím **Y**, hoặc bấm vào người chơi khác → Mời vào tổ đội): thấy máu nhau, đánh quái gần nhau được
> chia Tu Vi, kênh chat Tổ Đội (`/d`). **Cổng Bí Cảnh** giữa quảng trường Trúc Lâm Thôn mở **Mặc Ảnh Động** (Trúc Cơ) ba lần
> mỗi ngày — 12:00, 19:00, 21:00 giờ Việt Nam, mỗi lần 15 phút — và **Khe Nứt Mực** (Luyện Khí) thỉnh thoảng rách ra ở Rừng
> Mực Loang, Hồ Nghiên Mực trong 5 phút, chỉ người ở gần mới thấy. Đội trưởng dẫn đội vào, hoặc vào **hàng chờ ghép đội**.
> Bên trong: 3–5 gian câu đố hợp tác — **Cửa Ghép Chữ** (mỗi người cầm một mảnh chữ chỉ mình thấy, đứng đúng bệ), **Câu Văn
> Đứt Đoạn** (lần lượt bước lên ô số đúng vị trí mảnh câu của mình), **Trụ Thanh Điệu** (đánh đúng trụ thanh, 8 lần liền),
> **Gương Nghĩa** (ai có chữ mang nghĩa trong gương thì bước vào), **Mê Cung Mực** (người đã học 明 soi đường) — rồi boss
> **Nghiên Ma** 4 pha: mỗi pha cần **mỗi người còn sống trả lời đúng một câu** mới vỡ Mặc Thuẫn lớn, né vùng Mặc Triều. Gục
> thì thành hồn ma theo đội, qua phòng sau được hồi sinh. **Mỗi người nhận phần thưởng riêng** (không ai giành của ai, không
> nhận hai lần), cả đội cùng nhận **Mảnh Bảo Vật** để ghép đồ bộ **Mặc Ảnh** phẩm Thiên; **Thiên Tằm Ti** làm Cần Thiên Tơ.
> Rớt mạng thì có 60 giây để vào lại đúng chỗ cũ. 2 lượt mỗi bí cảnh mỗi ngày.
>
> Giai đoạn 8 (vẫn đầy đủ): **Luyện đan** ở Đan Lô trong động phủ (nâng cấp được) hoặc lò của **Đan Sư** trong làng: có đan phương và nguyên liệu
> (quả chữ, Linh Mật, Linh Quả, cá, Mực Tinh, dược thảo) là nhóm lửa, rồi **canh lửa** — kim chạy qua lại trên thanh
> nhiệt, bấm đúng lúc kim vào vùng văn hỏa 3 lần; mỗi lần bấm hiện một chữ trong tên đan (回 血 丹...), chữ đã học thì
> gõ pinyin, chữ chưa học thì hiện cách đọc và âm Hán-Việt. Ra phế đan / hạ / trung / thượng phẩm. 8 loại đan: Hồi Huyết,
> Hồi Khí, Tụ Linh (thêm Tu Vi cho câu đúng), Kháng Mực, Ngộ Tính (+3 giây mỗi câu), Trúc Cơ, Kim Đan, Phong Vương (cho ong).
> **Khắc Văn** ở Lò Rèn: khắc chữ đã thuộc từ 70% lên trang bị (火 công, 山 thủ, 心 Linh Lực...) bằng 3 câu đúng liền.
> **Linh Thú**: 12 con giáp ở Thiên Cơ Các (tab Linh Thú), mỗi con một kỹ năng (Trâu +20% tiền ôn, Hổ sương mực chậm
> một nửa, Rồng gấp đôi câu thứ 5 liên tiếp...), chạy theo nhân vật, người khác cũng thấy. **Sạp Tạp Hóa** của Bà Chủ Sạp,
> **nhiệm vụ hằng ngày**, **tặng quà** cho bạn bè, và `docs/BALANCE.md` + `tools/economy_sim.py` chứng minh không có
> vòng lặp tạo tiền (mô phỏng 30 ngày của 3 kiểu người chơi).
>
> Giai đoạn 7: 30 ải Thủ Vườn + Vô Tận Trận, Tàng Thư Các. Giai đoạn 6: câu cá, 30 loài cá. Giai đoạn 5:
> Linh Phong Sào, 18 loài ong. Giai đoạn 4: Mặc Thuẫn và câu hỏi Vấn Đạo, Tu Vi, Thiên Kiếp, trang bị, lò rèn, Pháp Chữ.

## Chơi kiểu Minecraft: thế giới LAN (bản 1.1)

**Một lần, người làm game:** bật đăng nhập email trong Firebase — vào https://console.firebase.google.com → chọn dự án →
**Authentication** → **Get started** → tab **Sign-in method** → **Email/Password** → **Enable** → Save. (Chưa bật thì
game báo "Dự án Firebase chưa bật Authentication".) API key của dự án nằm trong `client/config.example.json`
(`firebase_api_key`) và được chép vào `config.json` cạnh exe khi đóng gói. Đây là khóa công khai của Firebase cho ứng dụng
(không phải mật khẩu); nên vào Google Cloud Console → APIs & Services → Credentials giới hạn khóa đó chỉ cho
"Identity Toolkit API" và "Token Service API".

**Người chơi:**

1. Chạy `VuonChu.exe` (hoặc `chay_game.bat`) → **Bắt đầu** → **Đăng ký** bằng email + mật khẩu (≥ 6 ký tự). Quên mật
   khẩu: tab *Quên mật khẩu* → Firebase gửi thư đặt lại. Cần Internet lúc đăng nhập.
2. **Làm chủ thế giới**: tab *Thế giới của tôi* → đặt tên → **Tạo** → **Mở thế giới**. Lần đầu Windows hỏi tường lửa: bấm
   **Allow** (mạng Private) để bạn bè vào được. Địa chỉ cho bạn bè hiện trong khung chat và trong **Cài đặt**.
3. **Vào thế giới của bạn**: cùng Wi-Fi/LAN → tab *Tham gia mạng LAN* → chọn thế giới → **Tham gia** (hoặc gõ địa chỉ).
   Lần đầu mở tab này Windows cũng hỏi tường lửa: bấm **Allow**, không thì game không nghe được tín hiệu LAN.
   Lần đầu vào mỗi thế giới thì tạo nhân vật cho thế giới đó.
4. Người chủ **Rời thế giới** (Cài đặt) hoặc tắt game là thế giới đóng (tự lưu); mở lại lúc nào cũng được.

Thế giới nằm ở `worlds/<tên>/` cạnh exe (chạy từ mã nguồn: `client/worlds/`): `world.db` là toàn bộ dữ liệu, chép thư
mục là sao lưu hoặc chuyển máy. `server.log` ghi những gì máy chủ của thế giới in ra.
Chơi qua Internet (khác mạng) thì vẫn dùng được cách cũ: Cloudflare Tunnel tới cổng của thế giới, hoặc máy chủ riêng.

## Ra bản cập nhật (game tự báo cho người đã tải)

Mỗi bản game biết repo GitHub nó được build từ (`update_repo` trong `config.json`). Lúc mở, game hỏi
`api.github.com/repos/<repo>/releases/latest` một lần (luồng riêng, không có Internet thì im lặng): release mới hơn
bản đang chạy thì hiện hộp **"Có bản cập nhật!"** kèm nút **Tải về** (mở link tải file zip trong trình duyệt) và cách
cài; màn hình chính giữ một nút vàng *Có bản mới v… — bấm để tải*. Đang chơi dở thì chỉ hiện một dòng nhắc.

**Người làm game, mỗi lần ra bản mới:**

1. Sửa `GAME_VERSION` trong `client/config.py` **và** `server/app/config.py` (vd `1.1.1` → `1.2.0`). Đổi cách game
   nói chuyện với máy chủ thì tăng cả `PROTOCOL_VERSION` (người bản cũ sẽ không vào được thế giới bản mới).
2. Commit rồi đẩy tag trùng phiên bản:
   ```bash
   git commit -am "Bản 1.2.0: ..."
   git push
   git tag v1.2.0
   git push origin v1.2.0
   ```
3. GitHub Actions (`.github/workflows/release.yml`) tự build `VuonChu.exe` trên Windows, chạy thử, tạo Release `v1.2.0`
   và đính file zip vào (khoảng 10 phút, xem tab **Actions**). Vào Release đó bấm **Edit** để viết vài dòng "có gì mới":
   game hiện câu đầu trong hộp thông báo.

**Người chơi cập nhật:** bấm **Tải về** → tắt game → giải nén file vừa tải **đè** lên thư mục game cũ (Windows hỏi thì
chọn *Replace*). Thế giới (`worlds/`) và đăng nhập (`session.json`) không nằm trong file zip nên được giữ nguyên.

## Chơi thử nhanh (Windows)

Cần **Python 3.11 trở lên** (khi cài, tích "Add python.exe to PATH").

Nháy đúp `chay_game.bat` → **Bắt đầu** → đăng ký bằng email → **Tạo** rồi **Mở thế giới** (mục trên). Không cần chạy
máy chủ riêng.

Muốn chơi kiểu cũ với **một máy chủ riêng** (tài khoản tên đăng nhập + mật khẩu, dùng `TIME_SCALE`/`BALANCE_PROFILE` để
thử nhanh như dưới đây): tạo `client/config.json` với `{"firebase_api_key": "", "server_url": "http://127.0.0.1:8000"}`, rồi

1. Nháy đúp `chay_server.bat` — mở máy chủ trên máy bạn (để cửa sổ này chạy).
2. Nháy đúp `chay_game.bat` — mở game, bấm **Bắt đầu**, đăng ký tài khoản.

Trên macOS/Linux dùng `./chay_server.sh` và `./chay_game.sh`.

Muốn cây lớn nhanh khi thử: mở `server/.env`, đặt `TIME_SCALE=1440` (1 ngày trong game = 1 phút) rồi chạy lại server.
`TIME_SCALE` cũng làm ong làm mật và thụ phấn nhanh tương ứng.
Muốn thử nhanh đường từ Phàm Nhân lên Trúc Cơ: thêm dòng `BALANCE_PROFILE=dev` (Tu Vi mỗi tầng chỉ cần 10, đả tọa
10 giây một câu, cá cắn câu sau 1,5–3 giây và cá hiếm cắn nhiều hơn hẳn, ải thủ vườn tua được tới ×32, Mặc Ảnh Động mở
suốt ngày, Khe Nứt Mực hay xuất hiện, hàng chờ ghép đội nhanh). Chỉ dùng để thử — xóa dòng đó đi là trở lại số liệu thật, tài khoản vẫn giữ nguyên.

### Dữ liệu của bạn nằm ở đâu, cập nhật có mất không?

Mọi tài khoản, vườn, Linh Thạch… nằm trong **một file: `server/dev.db`** (cạnh đó còn `server/.env`).
Gói cập nhật không bao giờ chứa hai file này, và máy chủ tự nâng cấp cơ sở dữ liệu khi khởi động, nên:

- **Giải nén bản mới đè lên thư mục đang dùng** (chọn "Replace") là giữ nguyên dữ liệu; hoặc
- nếu giải nén ra thư mục mới, **tắt máy chủ rồi chép `server\dev.db` (và `server\.env`) từ thư mục cũ sang** trước khi chạy.

## Chơi cùng bạn bè

Một người mở máy chủ, những người khác chỉ cần game.

**Cùng mạng Wi-Fi / LAN**: người mở máy chủ chạy `chay_server_choi_chung.bat` (thay cho `chay_server.bat`). Cửa sổ sẽ
in địa chỉ dạng `http://192.168.1.5:8000`; Windows hỏi tường lửa thì bấm **Allow**. Người khác mở game →
**Cài đặt** → ô **Máy chủ** → gõ địa chỉ đó → **Lưu**, rồi đăng ký tài khoản của mình.

**Qua Internet, miễn phí, không cần mở cổng (Cloudflare Tunnel)**:

1. Người mở máy chủ chạy `chay_server_choi_chung.bat`.
2. Tải `cloudflared` (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/),
   mở một cửa sổ lệnh khác và chạy: `cloudflared tunnel --url http://localhost:8000`
3. Nó in ra một địa chỉ `https://….trycloudflare.com`. Gửi địa chỉ đó cho bạn bè; mọi người (kể cả máy chủ) gõ nó
   vào **Cài đặt → Máy chủ**. WebSocket của thế giới chung tự chuyển sang `wss://`.
4. Địa chỉ quick tunnel đổi mỗi lần chạy lại `cloudflared`; để game tự nhận địa chỉ mới, dùng `server_list_url`
   (xem [`docs/DEPLOY.md`](docs/DEPLOY.md) mục C3).

Khi dùng tunnel, nên đặt `TRUST_PROXY_HEADERS=1` trong `server/.env` để giới hạn tài khoản/IP tính theo IP thật.

## Phát hành và chạy máy chủ thật (giai đoạn 10)

Hướng dẫn đầy đủ: **[`docs/DEPLOY.md`](docs/DEPLOY.md)** — Oracle Cloud Always Free (24/7), Render + Neon (không cần thẻ),
hoặc máy nhà + Cloudflare Tunnel; phát hành exe qua GitHub Releases; sao lưu/khôi phục; quản trị.

**Đóng gói game** (Windows): `dong_goi_exe.bat --server-url https://dia-chi-may-chu` → `dist/VuonChu/VuonChu.exe` và
`dist/VuonChu-1.0.0-windows.zip` (gửi file zip này cho người chơi, hoặc để GitHub Actions làm khi đẩy tag `v1.0.0`).

**Máy chủ bằng Docker** (Oracle ARM hoặc máy nhà):

```bash
cd deploy && cp .env.example .env      # sửa mật khẩu, JWT_SECRET, tên miền
docker compose --profile https up -d --build      # có HTTPS qua Caddy; bỏ --profile https nếu dùng Cloudflare Tunnel
```

**Quản trị**: đặt `ADMIN_USERNAMES=ten_cua_ban` (hoặc `cd server && python -m app.admin_cli grant ten_cua_ban`), rồi gõ
`/admin help` trong khung chat của game.

**Sao lưu** (máy chủ chạy bằng `chay_server.bat`): nháy đúp `sao_luu.bat` → thư mục `backups/`, giữ 7 bản. Bản Docker tự
sao lưu mỗi ngày vào `deploy/backups/`.

### Điều khiển

| Phím | Việc |
|---|---|
| WASD / mũi tên | Đi lại |
| E | Tương tác (ô đất, Trúc Lão, Thiên Cơ Đài, bia đá, bàn gỗ, cổng tre, dân làng, biển chỉ đường, lò rèn, bảng nhiệm vụ, bồ đoàn đả tọa, Cổng Thủ Vườn, Thủ Thư, Đan Lô, Đan Sư, Bà Chủ Sạp); ở rừng: đánh quái gần nhất |
| Chuột trái / Space | Đánh quái (bấm vào quái, hoặc Space để đánh con gần nhất) |
| 1–4 (khi không có câu hỏi) | Dùng Pháp Chữ 火 水 木 山 đã học |
| Q | Uống Hồi Huyết Đan |
| F | Câu cá khi đứng sát mép nước; F / Space để giật khi phao chìm; **giữ chuột (hoặc Space)** để kéo cá |
| K | Tu luyện (cảnh giới, Tu Vi, chỉ số, trang bị, Pháp Chữ, nút Đột phá) |
| J | Nhiệm vụ (tab Cốt truyện / Hằng ngày) |
| O | Linh Thú (đeo pet, Linh Thú Phổ) |
| Space / chuột khi canh lửa | Bấm khi kim vào vùng văn hỏa; gõ pinyin rồi Enter |
| Enter | Chat (Enter lần nữa để gửi, Esc để thôi). `/w Tên nội dung` nhắn riêng bạn bè, `/t` Thế giới, `/k` Khu vực, `/d` Tổ Đội |
| Y | Tổ đội (mời bằng đạo hiệu, lời mời đang chờ, rời đội, mời ra, nhường đội trưởng) |
| E ở Cổng Bí Cảnh / Khe Nứt Mực | Xem bí cảnh, giờ mở, lượt còn lại; vào cùng đội; hàng chờ; Ghép Bảo Vật |
| Trong bí cảnh | Đi lên bệ / ô số / vào gương bằng WASD; **E** đánh trụ thanh điệu; **chuột phải** đặt dấu cho đội (Shift: mũi tên); nút **Rời bí cảnh** góc phải |
| P | Bạn bè (kết bạn, lời mời, nhắn, thăm động phủ, chặn) |
| Chuột trái | Bấm vào ô đất / đồ vật / người chơi khác, chọn đáp án; bấm tên trong khung chat để kết bạn/chặn/báo cáo |
| 1–4 | Chọn đáp án câu hỏi |
| Tab | Túi đồ (hạt, quả chữ, sổ chữ, vật phẩm, trang bị) |
| C | Bàn Ghép Câu |
| B | Sổ Phát Hiện (có nút sang Yêu Quái Phổ, Ong Phổ, Ngư Phổ, Tàng Thư Các) |
| L | Tàng Thư Các (mọi phổ, tìm kiếm, mốc thưởng, Sổ Lỗi) |
| Trong ải thủ vườn | Bấm thẻ cây (hoặc phím 1–8) rồi bấm ô để trồng; bấm cây đã trồng để nâng cấp/nhổ; chuột phải bỏ chọn; Space bắt đầu đợt; Q Tụ Khí; Esc rời ải |
| G | Thiên Cơ Các (gacha Hạt Chữ, Trứng Ong, Linh Thú) |
| H | Linh Phong Sào (tổ ong, trong động phủ) |
| Esc | Đóng / Cài đặt |

## Có gì trong game hiện tại

**Động Phủ**: bản đồ pixel (làm bằng code, mở được bằng Tiled), nhà tranh của Trúc Lão, ao, Thiên Cơ Đài,
bia Phát Hiện, bàn Ghép Câu, cổng tre (đường xuống làng sẽ mở ở giai đoạn 3).

**Vườn chữ** (mục 6 của đặc tả):
- 5 giai đoạn cây, mỗi giai đoạn một dạng câu hỏi (nghĩa → pinyin → nghe → gõ pinyin/điền chỗ trống),
  lịch ôn 10 phút / 1 / 3 / 7 ngày, thời gian theo đồng hồ server.
- Sương mực: bỏ quên cây thì cây xám dần, có đốm mực trôi, quá 100 thì lùi một giai đoạn (không mất chữ).
- Phản ứng kề ô: 水 tưới mát, 火 sưởi ấm (và có thể làm cháy 木), 6 chữ ẩn 明 林 森 好 休 吗 — không liệt kê
  trước, phát hiện thì hiện "Phát hiện mới!" và ghi vào Sổ Phát Hiện.
- Sự cố sai thanh điệu: chọn mǎ thay vì mā thì ngựa chạy qua vườn, chọn mài thay vì mǎi thì "rao bán cái cuốc"…
- Ghép quả chữ thành câu, khai hoang thêm ô đất (tới 5×5), giâm cành.
- Thẻ giới thiệu chữ: chữ to, pinyin, nghĩa, câu ví dụ, cấu tạo chữ, lượng từ, tích xưa của thành ngữ.

**Gacha Hạt Chữ**: tỉ lệ công khai (kèm tỉ lệ thực tế khi tính bảo hiểm), hiệu ứng hạt rung — nứt — tỏa sáng theo
độ hiếm, 15 hạt/ngày, 1 lượt miễn phí mỗi ngày. Mọi phép quay và trừ tiền chạy trên server.

**Trúc Lão** dẫn tân thủ từng bước và nói đùa khi bạn trả lời đúng/sai.

**Thế giới chung** (giai đoạn 3, mục 7.1 và 15):
- **Trúc Lâm Thôn**: quảng trường, Thiên Cơ Các (gacha), Tàng Thư Các, nhà Trúc Lão, sạp chợ, lò luyện đan, lò rèn,
  bảng nhiệm vụ, Cổng Thủ Vườn (các nơi chưa mở có lời nhắn khi bấm), cô Tiểu Lan chỉ đường.
- **Rừng Mực Loang**: rừng nhiễm mực với Mực Con và Thanh Điệu Yêu đi lang thang.
- Thấy người chơi khác đi lại mượt (nội suy 100 ms), nhân vật mình phản hồi ngay (dự đoán phía client, server
  kiểm tra tốc độ và va chạm). Tên và bong bóng chat trên đầu, bản đồ nhỏ góc phải, ngày/đêm theo giờ server.
- **Kênh**: mỗi vùng tối đa 40 người/kênh, tự mở kênh mới khi đầy, bấm tên kênh trên đầu màn hình để đổi.
- **Chat** Thế giới / Khu vực / Bạn bè, lọc từ tục, 1 tin/2 giây, tối đa 200 ký tự, chặn và báo cáo người chơi.
- **Bạn bè**: kết bạn theo đạo hiệu, thấy ai đang online và ở đâu, **thăm động phủ** của bạn và **tưới giúp**
  (trả lời một câu về chữ trong vườn bạn mà mình đã học: đúng thì cả hai +10 Linh Thạch, tối đa 5 lần/ngày).
- Rớt mạng: game tự kết nối lại, nhân vật đứng chờ 30 giây; đăng nhập ở máy khác thì máy cũ bị thoát ra.

**Chiến đấu Vấn Đạo** (giai đoạn 4, mục 8 của đặc tả):
- Quái mang **Mặc Thuẫn**: đòn đánh chỉ gây 1 sát thương và không bao giờ hạ được quái còn khiên.
- Đánh trúng lần đầu thì hiện **thẻ câu hỏi** ở nửa dưới màn hình (trận đấu vẫn thấy phía trên). Trong lúc trả lời,
  nhân vật có **Hộ Thể** — không bị đánh. Dạng câu hỏi tùy loại quái (Mực Con hỏi nghĩa/chữ/pinyin, Thanh Điệu Yêu
  hỏi thanh điệu), chỉ lấy những chữ bạn đã học.
- **Đúng**: khiên vỡ (với mọi người đang đánh con đó), đòn **Ngộ Đạo** ×2 sát thương, trả lời nhanh thì chí mạng; +Linh Lực.
- **Sai hoặc hết giờ**: **Mặc Kích** = 10% Sinh Lực tối đa (quái tinh anh 15%, boss 20%), giảm theo Kháng Mực;
  3 giây sau có câu mới.
- Quái đánh có báo trước (vòng đỏ dưới chân), đuổi quá xa thì quay về; **Mặc Hồ** (tinh anh) mọc lại khiên ở 50% máu.
- Hết máu: mất Tu Vi bằng 5% lượng cần cho tầng hiện tại, sau 3 giây về Trúc Lâm Thôn; về làng/động phủ thì hồi máu nhanh.
- **Pháp Chữ** học từ bí kíp rơi ra (cần thuộc chữ đó ≥ 50%): 火 Hỏa Chữ Quyết (sát thương), 水 Thủy (làm chậm),
  木 Mộc (hồi máu), 山 Sơn (giảm 50% sát thương trong 5 giây). Độ thuộc chữ càng cao, pháp càng mạnh.

**Tu luyện** (mục 7.3, 7.4):
- Mọi câu trả lời đúng đều cho Tu Vi (ở vườn, khi đánh quái, luyện tập, tưới giúp, đả tọa), thu hoạch cây cũng có.
- Trong một cảnh giới, đủ Tu Vi thì tự lên tầng. Cuối cảnh giới phải có **đan dược** và vượt **Thiên Kiếp**:
  20 câu trộn mọi dạng, 30 giây/câu, đúng từ 80% thì đột phá (+50 Tiên Ngọc). Trượt mất 10% Tu Vi, chờ 30 phút
  mới thử lại, đan dược không mất.
- **Đả tọa** trên bồ đoàn trong động phủ: cứ 2 phút một câu, đúng thì +15 Tu Vi (không treo máy lấy Tu Vi được).

**Trang bị và vật phẩm** (mục 12): 6 ô (vũ khí, áo, mũ, giày, ngọc bội, nhẫn), 5 độ hiếm Phàm → Thiên, 4 loại vũ khí
(bút lông, kiếm, quạt, gậy — tầm và tốc độ đánh khác nhau). **Lò rèn** ở làng cường hóa +1 → +10: thất bại chỉ mất
nguyên liệu, không mất đồ. Hồi Huyết Đan / Hồi Khí Đan dùng khi đang ở làng hoặc rừng (có thời gian chờ 15 giây).

**Linh Phong — ong linh** (giai đoạn 5, mục 10 của đặc tả):
- **Linh Phong Sào** đặt cạnh vườn: lưới lục giác 6 × 5. Mở đầu 5 ô, mở thêm bằng Linh Thạch (ô 11, 16, 21, 26 cần đủ
  3/6/9/12 loài trong Ong Phổ). Mỗi con ong chiếm một ô; **kéo thả** (hoặc bấm ong rồi bấm ô trống) để đổi chỗ.
  Ong cùng hệ nằm kề nhau được **đồng hệ cộng hưởng** (+5% mỗi con, tối đa +15%).
- **18 loài** từ Phàm tới Thiên, tên song ngữ: Ong Mực 黑蜂, Ong Hoa 花蜂, Ong Trà 茶蜂, Ong Hỏa Diệm 火蜂, Ong Hoàng
  Kim 黄蜂 (từ có thật: ong vò vẽ), Ong Băng Tâm 雪蜂, Ong Lôi Vân 云蜂, Ong Ngọc Bích 绿蜂, Ong Thư Pháp 笔蜂, Ong Kim Ô 日蜂…
  Tên Hán được kiểm chứng qua CC-CEDICT bằng `tools/build_bees.py`. Con càng thuộc chữ của loài ong, ong càng mạnh.
- **Ba vai trò** (mỗi con một việc):
  - **Ở tổ**: làm Linh Mật (và Sáp Ong) theo thời gian, cả khi con không chơi; tổ đầy thì ngừng, bấm **Thu mật**.
  - **Thụ phấn** (tối đa 6): ong bay giữa các cây từ giai đoạn **Ra hoa**, để lại hạt phấn vàng, làm đầy thanh phấn.
    Đầy 100%: cây "Đã thụ phấn" → thu hoạch **5 quả** thay vì 3 và có thể ra **Linh Quả**; lượt chờ ôn đang chạy rút
    ngắn **tối đa 25%**. Ong hệ Thủy thụ phấn nhanh hơn cạnh cây 水 (tương tự cho các hệ khác).
    **Không bao giờ thay câu hỏi ôn**: cây chỉ lên giai đoạn khi con trả lời đúng.
  - **Hộ vệ** (Phàm Nhân 0, Luyện Khí 2, Trúc Cơ 3, Kim Đan 4, Nguyên Anh 5 con): bay theo nhân vật ngoài thế giới,
    tự chích quái **đã mất Mặc Thuẫn** (không phá khiên thay con). Mỗi loài một kỹ năng: đốt lửa, làm chậm, gây choáng,
    hồi máu cho chủ, nhặt thêm đồ rơi, chích nhanh, nét bút thư pháp. Ong có thanh máu (góc trên trái); bị hạ thì bay
    về tổ nghỉ 60 giây.
- **Cho ăn** Linh Mật, quả chữ, Linh Quả để lên cấp (tối đa 20). Mỗi loài có **món thích** (có gợi ý): cho đúng thì
  gấp đôi kinh nghiệm và thân thiết tăng mạnh, món đó được ghi vào Ong Phổ.
- **Nâng cấp tổ** (Linh Thạch + Sáp Ong + Gỗ Linh Mộc rơi ở Rừng Mực Loang): chứa nhiều mật hơn, làm mật nhanh hơn,
  mở trang trí (đèn lồng, chậu sen, chuông gió, cờ phướn) đặt quanh tổ.
- **Gacha Trứng Ong** ở Thiên Cơ Các (tab "Trứng Ong"): 300 Linh Thạch hoặc 5 Tiên Ngọc, tỉ lệ và bảo hiểm công khai.
  Trứng vào túi, mang tới tổ để **ấp** (trứng rung — nứt — ong bay ra).
- **Ong Phổ** (trong tổ ong, hoặc Sổ Phát Hiện → Ong Phổ): mọi loài, loài đã gặp có chữ, pinyin, kỹ năng, chỉ số gốc,
  món thích; mốc 3/6/9/12/15/18 loài có thưởng.
- Chuỗi nhiệm vụ **"Linh Phong"**: ấp trứng → cho ăn → thụ phấn một cây → đặt ong hộ vệ → Ong Phổ 4 loài.
- Làng mua lại Linh Mật, Sáp Ong, Gỗ, Linh Quả (Túi đồ → Vật phẩm → Bán).

**Câu cá** (giai đoạn 6, mục 11 của đặc tả):
- **Hồ Nghiên Mực** (cổng Tây Trúc Lâm Thôn): hồ lớn có bến gỗ, lều và **Ngư Ông**, Mặc Quái đi lang thang ven bờ,
  bảng Ngư Phổ. Ao trong làng và ao trong động phủ cũng câu được (chỉ có cá nhỏ: cá Phàm và vài loài Linh).
- **Quăng câu → chờ → giật**: phao chìm thì bấm F/Space trong khoảng 1,3 giây; giật sớm cá sợ chạy, chậm thì mất mồi.
- **Kéo cá**: thanh dọc bên phải — vùng xanh là con cá bơi lên xuống, vạch vàng là móc câu (giữ chuột thì lên, nhả thì
  chìm). Móc trong vùng xanh thì thanh **Bắt** đầy dần, ra ngoài thì tụt; giữ quá tay khi móc đã vượt lên trên con cá thì
  thanh **Dây** căng dần và đứt. Cá càng hiếm càng nhanh, càng khỏe, vùng xanh càng hẹp.
- **Cá từ Linh trở lên cắn câu thì hỏi một câu** (Linh: nghĩa/chữ/thanh điệu; Huyền: pinyin/nghe; Địa: gõ pinyin,
  lượng từ, điền chỗ trống; Thiên: khó nhất và phải **đúng 2 câu liên tiếp**). Đúng thì vùng xanh rộng ×1,3, sai thì
  hẹp ×0,65 — **không bao giờ mất máu**. Câu đúng cho Tu Vi như mọi nơi khác.
- **30 loài, 5 độ hiếm**: Cá Diếc 鲫鱼, Cá Chép 鲤鱼, Cá Trắm Cỏ 草鱼, Cá Vàng 金鱼, Cá Koi 锦鲤, Cá Quế 鳜鱼, Lươn Đồng
  黄鳝, Cá Tầm 鲟鱼, Cá Nóc 河豚, Mực Nang 墨鱼, Cá Yên Chi 胭脂鱼, Cá Oa Oa 娃娃鱼, Côn 鲲… và hai cá huyền thoại tên
  sáng tác (Cá Chép Hóa Long 化龙鲤, Nghiên Linh Ngư 砚灵鱼). Mỗi loài có điều kiện riêng: nơi câu, ngày/đêm, mưa/quang,
  mồi (vd Cá Chép Hóa Long chỉ ở Hồ Nghiên Mực, đêm mưa, mồi Linh Quả Vụn). **Mưa** đến rồi tạnh theo từng vùng
  (giống nhau với mọi người), trong game thấy mưa rơi.
- **5 cần câu** (Cần Trúc Thô tặng sẵn → Tre Già → Ngọc Bích → Long Cốt; Cần Thiên Tơ cần nguyên liệu bí cảnh): lực kéo,
  độ bền dây, may mắn (cá hiếm), tốc cắn, độ rộng vùng xanh. **Nâng cấp ở Lò Rèn** (nút "Cần câu") bằng Linh Thạch +
  **Vảy Linh Ngư** (có từ cá Linh trở lên).
- **4 loại mồi**: Giun Đất (Ngư Ông bán), Bánh Mật (từ Linh Mật), Linh Quả Vụn (từ Linh Quả), Mồi Mực (từ Mực Tinh — chỉ
  cá Mực cắn, chỉ dùng ban đêm). Câu không mồi được nhưng chậm và chỉ ra cá Phàm/Linh.
- **Kích thước ngẫu nhiên**, con to hiếm. Cá Phàm quá nhỏ thành **Cá Nhỏ** (cho ong ăn). Cá bán được trong Túi đồ.
- **Ngư Phổ** (Sổ Phát Hiện → Ngư Phổ, bảng đá ở bến, hoặc nút trong cửa hàng Ngư Ông): loài đã câu có chữ, pinyin,
  số con, con to nhất; loài chưa câu chỉ có bóng đen và gợi ý nơi/giờ/mồi. Mốc 5/10/20/30 loài thưởng Linh Thạch,
  Tiên Ngọc. Tab **Kỷ lục**: con to nhất mỗi loài trên toàn máy chủ và tên người câu.
- Chuỗi nhiệm vụ **"Ngư Ông"**: chào Ngư Ông → câu 3 con cá → Ngư Phổ 5 loài.
- **Chống gian lận**: máy chủ quyết định lúc cá cắn, loài cá và kích thước; game chỉ gửi những thời điểm bấm/nhả nút,
  máy chủ chạy lại đúng trò kéo cá đó (cùng một file `fishing_sim.py`) để biết có câu được không, và từ chối kết quả
  nhanh hơn thời gian thật.

**Ải Thủ Vườn** (giai đoạn 7, mục 9 của đặc tả):
- **Cổng Thủ Vườn** ở Trúc Lâm Thôn → bản đồ ải: 3 chương × 10 ải (chương 2 cần Luyện Khí, chương 3 cần Trúc Cơ) và
  **Vô Tận Trận** (mở sau ải 10 chương 1): đợt quái vô hạn, cả máy chủ đánh cùng một trận trong tuần, bảng xếp hạng tuần.
- **Bộ cây mang theo**: tối đa 8 loại, chỉ chữ đã học. Mỗi chữ có vai trò theo `server/data/plants/plant_roles.json`:
  Hỏa (nổ lan), Thủy (chậm 40%), Mộc (trồng trên đường, chặn quái, có gai), Sơn (choáng), Kim (kim châm con khỏe nhất),
  Quang (vùng sáng để đánh được Mực Ẩn), Sinh Khí (tạo Linh Khí), Hỗ Trợ (cây kề bên bắn nhanh, Mộc kề bên hồi máu),
  Thành Ngữ (tuyệt chiêu một lần mỗi ải: 一石二鸟, 画蛇添足, 对牛弹琴).
- **Sức mạnh cây** = độ thuộc chữ (0 → 60%, 100 → 130%) × độ tươi của cây đó trong vườn thật (sương mực trừ tới 30%).
- **Linh Khí**: có sẵn một ít, tăng dần trong đợt, thêm khi hạ quái, và nhiều nhất từ câu hỏi: **3 câu Linh Khí Vấn Đạo**
  trước mỗi đợt, nút **Tụ Khí** trong đợt (hồi 10 giây; đúng thêm, sai mất một ít). **Nâng cấp** (3 cấp) phải trả lời đúng
  câu về chữ của cây đó; sai thì mất Linh Khí đã bỏ ra. Khi thẻ câu hỏi mở, trận đứng yên.
- **6 loại Mặc Quái** có kháng/yếu nguyên tố (Mực Đặc kháng Thủy yếu Hỏa, Thạch Mặc không choáng được, Mực Ẩn tàng hình,
  Mặc Vương là thủ lĩnh); rê chuột lên quái để xem thẻ thông tin.
- **Phản ứng kề ô**: 女+子 → 好 (cả hai mạnh hơn), 日+月 → 明 (vùng sáng gấp đôi), ba cây 木 liền nhau → 森 (thêm máu),
  人+木 → 休 (cây gỗ tự hồi máu).
- **Tắt game giữa ải** không mất lượt: nhật ký được lưu liên tục, lần sau bản đồ ải có nút **Chơi tiếp**.
- **1–3 sao** theo điểm Linh Mạch còn lại (trên 20). Lần đầu đạt mỗi sao có thưởng (Linh Thạch, một số ải có bí kíp, Gỗ Linh
  Mộc, Tiên Ngọc, hạt giống); chơi lại thắng được thưởng nhỏ, tối đa 5 lần/ngày. Tua ×1/×2.
- **Chống gian lận**: máy chủ chọn hạt giống và gửi mọi số liệu; client gửi nhật ký hành động, máy chủ chạy lại đúng trận
  đó (cùng file `td_sim.py`) bằng kết quả câu hỏi do chính nó chấm, và từ chối nhật ký giả, kết quả không khớp hoặc
  nhanh hơn thời gian thật.

**Tàng Thư Các** (giai đoạn 7, mục 9.3): Thủ Thư ở làng, phím L, hoặc nút trong Sổ Phát Hiện.
- **Bách Thảo Phổ**: mỗi chữ một trang — cây 5 giai đoạn, chữ to, pinyin, nút nghe (khi có âm), nghĩa, câu ví dụ, cấu tạo
  chữ, vai trò và chỉ số trong ải, độ thuộc, lời bình của Trúc Lão. Chữ chưa có là bóng đen "?", cây ẩn chỉ là khung trống.
- Gom **Yêu Quái Phổ** (giờ có cả quái của ải), **Ong Phổ**, **Ngư Phổ**, **Sổ Phát Hiện**; mỗi phổ có % hoàn thành và quà ở
  mốc 25/50/75/100% (Linh Thạch, Tiên Ngọc, danh hiệu, khung avatar, thêm ô tổ ong).
- **Tìm kiếm** theo chữ Hán, pinyin có/không dấu, nghĩa tiếng Việt (chỉ trong những gì đã phát hiện).
- **Bảo Vật Phổ**: trang bị, đan dược, cần câu con từng có.
- **Danh hiệu, khung avatar** nhận từ các mốc: chọn đeo trong Tàng Thư Các, hiện trên thẻ nhân vật.
- **Kệ bí kíp**: đứng cạnh Thủ Thư để mua bí kíp Pháp Chữ (Mộc, Thủy, Hỏa, Sơn) bằng Linh Thạch.
- **Sổ Lỗi**: những chữ hay trả lời sai nhất, mỗi chữ có nút luyện.

**Luyện đan** (giai đoạn 8, mục 12.3 của đặc tả):
- **Đan Lô** ở động phủ (cạnh bàn đả tọa) và lò của **Đan Sư** ở phía nam Trúc Lâm Thôn. Đan Lô nâng được: Đất Nung →
  Đồng Xanh (vùng văn hỏa rộng hơn) → Tử Kim (rộng hơn nữa, 25% ra thêm 1 viên). Lò làng luôn là lò thường.
- **Đan phương** là vật phẩm giữ mãi: nhiệm vụ "Đan Đạo", kệ sách của Thủ Thư, hoặc quái làm rơi. Bảng luyện đan cho thấy
  nguyên liệu đang có / cần, phí lò, số viên theo phẩm chất; đan chưa có đan phương ghi nơi tìm.
- **Canh lửa**: nhóm lửa là mất nguyên liệu và phí; kim chạy qua lại, bấm Space (hoặc chuột) khi kim vào vùng vàng — giữa
  vùng sáng là "tuyệt hảo". Ba lần bấm, kim mỗi lần nhanh hơn. Sau mỗi lần bấm hiện một chữ của tên đan: chữ con đã học
  (trong bất kỳ từ nào, vd 气 trong 天气) thì gõ pinyin; chữ chưa học thì hiện chữ, pinyin, âm Hán-Việt để nhớ.
  **Phế đan / Hạ / Trung / Thượng phẩm** tính theo điểm bấm và pinyin; thượng phẩm ra nhiều viên nhất.
- **Đan dược**: Hồi Huyết, Hồi Khí; **Tụ Linh** (10 phút: câu đúng +50% Tu Vi — vẫn phải trả lời), **Kháng Mực** (10 phút:
  +15 Kháng Mực), **Ngộ Tính** (10 phút: +3 giây mỗi câu hỏi), **Trúc Cơ / Kim Đan** (đột phá), **Phong Vương** (cho ong ăn:
  rất nhiều kinh nghiệm). Không đan nào trả lời hay bỏ qua câu hỏi.
- Máy chủ chọn vùng văn hỏa, tự chấm pinyin và chạy lại kim (cùng một file `alchemy_fire.py` với game) để biết phẩm chất.

**Khắc Văn** (mục 12.2): ở Lò Rèn, nút **Khắc** cạnh mỗi trang bị. Chọn một chữ đã thuộc từ 70%, trả lời đúng **liền 3 câu**
về chữ đó (sai một câu là hỏng, phí không hoàn) thì chữ được khắc lên đồ: 火 +Công, 山 +Thủ, 水 +Kháng Mực, 心 +Linh Lực,
人 +Sinh Lực; chữ khác theo vai trò của nó trong ải. Đồ Phàm/Linh 1 ô, Huyền/Địa 2, Thiên 3; mài bớt chữ được. Chữ khắc
hiện nhỏ cạnh tên trang bị.

**Linh Thú** (mục 13): Thiên Cơ Các → tab **Linh Thú** (500 Linh Thạch hoặc 10 Tiên Ngọc; tỉ lệ và bảo hiểm công khai).
12 con giáp vẽ bằng code: Chuột 鼠, Trâu 牛, Hổ 虎, Mèo 猫, Rồng 龙, Rắn 蛇, Ngựa 马, Dê 羊, Khỉ 猴, Gà 鸡, Chó 狗, Lợn 猪.
Mỗi con một kỹ năng và một chút chỉ số; chỉ đeo một con (phím **O**). Trùng thì lên cấp (tối đa 5), quá cấp thì thành
Linh Thạch. Pet chạy theo nhân vật trong động phủ và ngoài thế giới, người khác cũng thấy. **Linh Thú Phổ** trong Tàng Thư Các.

| Linh Thú | Kỹ năng |
|---|---|
| Chuột | +5% ra hạt Hiếm khi quay Hạt Chữ |
| Trâu | +20% Linh Thạch khi ôn đúng trong vườn |
| Hổ | Sương mực phủ cây chậm một nửa |
| Mèo | Câu cá may mắn hơn |
| Rồng | Ôn đúng 5 câu liên tiếp thì câu thứ 5 gấp đôi Linh Thạch |
| Rắn | Mặc Kích (trả lời sai khi đánh quái) nhẹ đi 20% |
| Ngựa | Hạ quái thêm 15% Linh Thạch |
| Dê | Thu mật ở tổ thêm 15% |
| Khỉ | Vào ải Thủ Vườn có thêm 20 Linh Khí |
| Gà | Ôn đúng trong vườn thêm 10% Tu Vi |
| Chó | Quái rơi đồ nhiều hơn 15% |
| Lợn | Bán quả chữ thêm 10% |

**Kinh tế** (mục 12.1, 12.4):
- **Sạp Tạp Hóa** của Bà Chủ Sạp ở Trúc Lâm Thôn: đan dược, Trúc Diệp Thảo, Mực Tinh, giun, **Hạt Giống Thường** (tính vào
  15 hạt mới/ngày) — mỗi món có giới hạn mỗi ngày; đồ Phàm/Linh mọi loại; tab **Bán lại** thu mua vật phẩm, quả và trang bị.
- **Nhiệm vụ hằng ngày**: mỗi ngày "Ôn 15 chữ" + 2 việc ngẫu nhiên (đánh quái, câu cá, thụ phấn, luyện đan, thắng ải, đả
  tọa, ôn vườn); xong cả ba thêm 50 Linh Thạch + 1 Tiên Ngọc. Chuỗi nhiệm vụ mới **"Đan Đạo"** với Đan Sư.
- **Tặng quà**: danh sách bạn bè → **Tặng quà**: vật phẩm không ràng buộc, tối đa 5 cái một lần, 5 lần một ngày. Không có
  giao dịch tiền giữa người chơi.
- `docs/BALANCE.md` mô tả mọi nguồn vào và vòi xả; `python tools/economy_sim.py` kiểm tra không có vòng lặp tạo tiền và in
  dòng tiền 30 ngày của 3 kiểu người chơi (20 phút, 1 giờ, 4 giờ mỗi ngày).

**Tổ đội và bí cảnh** (giai đoạn 9, mục 14 của đặc tả):
- **Tổ đội** tối đa 5 người. Mời bằng đạo hiệu trong bảng Tổ đội (phím Y) hoặc bấm vào người chơi khác. Khung máu đồng đội
  dưới thẻ nhân vật; đánh quái cùng nhau thì đồng đội đứng gần nhận một nửa Tu Vi của con quái.
- **Mặc Ảnh Động** (cần Trúc Cơ, chữ HSK 1–2, 5 gian câu đố + boss, 20 phút) mở ở **Cổng Bí Cảnh** lúc 12:00, 19:00,
  21:00 (giờ Việt Nam) trong 15 phút; cả máy chủ được báo trước 10 phút. **Khe Nứt Mực** (cần Luyện Khí, chữ HSK 1, 3 gian +
  boss, 15 phút) rách ra ngẫu nhiên gần người chơi ở Rừng Mực Loang / Hồ Nghiên Mực, sống 5 phút. Mỗi bí cảnh 2 lượt/ngày.
- Vào: đội trưởng đứng ở cổng (hoặc sát khe nứt) bấm **Vào cùng tổ đội**; đi một mình thì vào **hàng chờ** — máy chủ ghép
  người cùng cảnh giới thành đội (đủ 5 người hoặc sau 20 giây đủ 2 người).
- Câu đố chỉ dùng chữ **ít nhất một người trong đội đã học**; mỗi người chỉ thấy phần của mình (mảnh chữ, mảnh câu, chữ của
  mình trước gương), nên phải nói với nhau (chat Tổ Đội, dấu chuột phải). Sai thì người sai (hoặc cả đội ở Gương Nghĩa) mất
  máu. Quái trong gian (Mặc Ảnh, Bút Yêu) cũng phải hạ hết thì cửa mới mở; đánh như ngoài thế giới, bằng câu Vấn Đạo.
- **Boss Nghiên Ma**: Mặc Thuẫn lớn mỗi pha cần đủ số người còn sống trả lời đúng (mỗi người một câu); vùng đỏ Mặc Triều
  dưới chân ai đó thì chạy ra.
- **Phần thưởng**: mỗi gian qua được ai cũng tự nhận Linh Thạch, Tu Vi, đôi khi Mực Tinh, Thiên Tằm Ti, Hồi Huyết Đan;
  rương cuối: Linh Thạch, Tiên Ngọc, Mảnh Bảo Vật chung (thêm 1 mảnh cho mỗi gian không sai lần nào), Thiên Tằm Ti, trứng ong
  Huyền/Địa/Thiên, đan phương Kim Đan, đồ bộ Mặc Ảnh. Xong nhanh (trong nửa thời gian) được thêm. **Ghép Bảo Vật** ở cổng:
  12 mảnh + 600 Linh Thạch → một món Mặc Ảnh phẩm Thiên (2 món: +8 Kháng Mực, 4 món: +40 Sinh Lực, +6 Công).
  **Cần Thiên Tơ** ở Ngư Ông: 12 Thiên Tằm Ti + 30 Vảy Linh Ngư + 6.000 Linh Thạch.
- Gục trong bí cảnh: thành **hồn ma** đi theo đội, không mất Tu Vi, hồi sinh khi sang gian sau. Cả đội gục là thua. Rời giữa
  chừng hoặc mất kết nối quá 60 giây thì về làng, vẫn giữ phần thưởng các gian đã qua.

**Nhiệm vụ "Nhập Môn"**: gặp Trúc Lão → hạ Mực Con → hạ Thanh Điệu Yêu → đả tọa → hạ Mặc Hồ (nhận Trúc Cơ Đan)
→ vượt Thiên Kiếp. **Yêu Quái Phổ**: quái đã gặp hiện tên, dạng câu hay hỏi, điểm yếu, đồ rơi, số lần hạ.

## Cấu trúc

```
server/            FastAPI + SQLAlchemy + Alembic (xem docs/API.md)
  app/learning/    pinyin, wordbank, srs, question_bank (11 dạng câu), quiz, selection
  app/garden/      vườn, phản ứng kề ô (combos), ghép câu (crafting)
  app/realtime/    WebSocket /ws: protocol, world (tick 20 Hz, kênh), zone, movement, ai, chat (docs/PROTOCOL.md)
  app/realtime/combat.py  Mặc Thuẫn, câu hỏi chiến đấu, Mặc Kích, Pháp Chữ, chết/hồi sinh
  app/systems/     gacha, inventory (mọi thay đổi tiền/vật phẩm), character, social (bạn bè, thăm, tưới giúp),
                   cultivation (Tu Vi, Thiên Kiếp, đả tọa), items (trang bị, cường hóa, đan dược), quests, codex,
                   bees (tổ ong, mật, thụ phấn, cho ăn, Ong Phổ),
                   fishing (cần, mồi, quăng/giật/kéo, Ngư Phổ, kỷ lục, mưa), fishing_sim (trò kéo cá, chung với client),
                   td (ải thủ vườn: ải, bộ cây, câu hỏi, chạy lại nhật ký, thưởng, bảng tuần), td_sim (trận thủ vườn,
                   chung với client), library (Tàng Thư Các, Bách Thảo Phổ, tìm kiếm, mốc thưởng, Sổ Lỗi),
                   alchemy (đan phương, lò, canh lửa), alchemy_fire (kim canh lửa, chung với client), buffs (bùa đan),
                   inscription (khắc văn), pets (Linh Thú), shop (Sạp Tạp Hóa)
  app/realtime/guard.py   ong hộ vệ trong thế giới chung
  app/realtime/party.py   tổ đội (giai đoạn 9)
  app/realtime/realm.py   bí cảnh: lịch mở, khe nứt, hàng chờ ghép đội, instance, 5 câu đố hợp tác, boss nhiều pha
  app/systems/secret_realm.py  lượt vào mỗi ngày, phần thưởng (mỗi người một lần), Ghép Bảo Vật
  app/admin.py     lệnh /admin trong chat (khóa, cấm chat, thông báo, bảo trì...), app/admin_cli.py bản dòng lệnh
  app/routers/server_routes.py  /server/info (JSON cho game, trang HTML cho trình duyệt), /healthz
  Dockerfile       image máy chủ (amd64 + arm64)
  maps/            bản đồ Tiled dùng chung với client (va chạm, cổng, điểm xuất hiện, vùng quái)
  data/            từ vựng, câu, công thức ghép chữ, sự cố thanh điệu, balance/*.json,
                   plants/plant_roles.json (vai trò cây), td/levels.json (30 ải, sinh bằng tools/gen_td_levels.py)
client/            pygame-ce
  engine/          hiển thị pixel phóng nguyên, chữ Việt + Hán, tilemap Tiled, âm thanh, hiệu ứng
  net/rest.py      gọi server trên luồng riêng (không làm đứng game)
  net/ws_client.py WebSocket trên luồng asyncio riêng, tự kết nối lại; net/interpolation.py nội suy
  scenes/          menu, đăng nhập, tạo nhân vật, động phủ, vườn, câu hỏi, gacha, túi đồ, ghép câu, sổ,
                   world (thế giới chung), social (bạn bè), visit (thăm động phủ),
                   rpg (thẻ câu hỏi chiến đấu, tu luyện, Thiên Kiếp, đả tọa, lò rèn, nhiệm vụ, Yêu Quái Phổ),
                   hive (Linh Phong Sào, ấp trứng, cho ăn, Ong Phổ),
                   fishing (câu cá, kéo cá, Ngư Ông, nâng cần ở lò rèn, Ngư Phổ, kỷ lục),
                   td (bản đồ ải, chọn bộ cây, trận thủ vườn, kết quả), library (Tàng Thư Các, Bách Thảo Phổ, Sổ Lỗi),
                   alchemy (luyện đan, canh lửa), inscribe (khắc văn), pets (Linh Thú, Linh Thú Phổ), shop (Sạp Tạp Hóa),
                   realm (Cổng Bí Cảnh, Tổ đội, mọi thứ trong bí cảnh)
  engine/beeflock.py  đường bay cong của ong
  engine/fishing_sim.py  trò kéo cá (bản sao y hệt của server)
  engine/td_sim.py       trận thủ vườn (bản sao y hệt của server)
  engine/alchemy_fire.py kim canh lửa (bản sao y hệt của server); engine/petfollow.py pet chạy theo chủ
  ui/chat.py       khung chat
  art/             bảng màu, sprite dạng lưới ký tự, vẽ bằng code (art/realm_art.py: quái, cổng và đồ vật bí cảnh)
  assets/          font (đã tải sẵn), sprite PNG, bản đồ .tmj
tools/             build_wordlist, build_bees, build_fish, apply_review, fetch_assets, generate_audio, gen_sprites, gen_maps,
                   gen_td_levels (30 ải), td_bot (người chơi thử để cân độ khó), load_bots,
                   economy_sim (kiểm tra vòng lặp tiền + dòng tiền 30 ngày), realm_bots (bot cùng vượt bí cảnh qua WebSocket)
docs/              DECISIONS.md, API.md, PROTOCOL.md, LOAD_TEST.md, BALANCE.md (kinh tế), DEPLOY.md (triển khai)
deploy/            docker-compose.yml (máy chủ + PostgreSQL + Caddy + sao lưu), Caddyfile, .env.example, server_list.json
render.yaml        Blueprint cho Render (phương án B)
.github/workflows/ build exe khi đẩy tag và đính vào Release, build image arm64/amd64, chạy test
tools/build_exe.py đóng gói VuonChu.exe (dong_goi_exe.bat); tools/backup_db.sh|.py sao lưu giữ 7 bản (sao_luu.bat)
```

## Chạy từ dòng lệnh

```bash
# máy chủ
cd server
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --port 8000          # http://localhost:8000/docs để thử API

# game (thư mục gốc dự án)
python -m pip install -r client/requirements.txt
python -m client.main
```

Địa chỉ máy chủ đổi được trong **Cài đặt** của game hoặc trong `client/config.json`
(xem `client/config.example.json`; có hỗ trợ `server_list_url` để tự lấy địa chỉ máy chủ từ một file JSON online).

## Kiểm tra

```bash
cd server && python -m pytest -q          # test máy chủ (gồm WebSocket thật với nhiều client)
cd .. && python -m pytest client/tests -q # test client: lượt tân thủ, hai người chơi, đánh quái + Thiên Kiếp qua giao diện
python -m client.tests.driver anh/        # chạy lượt chơi tự động và lưu ảnh chụp màn hình vào anh/
python -m client.tests.visual_tour anh/   # chụp các màn còn lại (quay 10, ghép câu, mọi dạng câu hỏi)
python -m client.tests.test_linh_phong_flow anh/   # tổ ong, ấp trứng, cho ăn, ong thụ phấn, gacha trứng, ong hộ vệ
python -m client.tests.test_fishing_flow anh/      # câu ở ao động phủ, câu hỏi khi cá hiếm cắn, Ngư Phổ, Ngư Ông, câu ở bến hồ
python -m client.tests.test_td_flow anh/           # Cổng Thủ Vườn, chọn bộ cây, chơi hết 10 ải chương 1 qua giao diện, Tàng Thư Các
python -m client.tests.test_td_resume_flow anh/    # Thủ Thư: danh hiệu, khung, mua bí kíp, Bảo Vật Phổ; tắt game giữa ải rồi chơi tiếp
python tools/td_bot.py                             # người chơi thử đánh cả 30 ải (kết quả từng ải), để cân độ khó
python -m client.tests.test_stage8_flow anh/      # luyện đan + canh lửa, Linh Thú đi theo, gacha Linh Thú, khắc văn, việc hằng ngày, Sạp Tạp Hóa
python tools/economy_sim.py                        # không có vòng lặp tạo tiền + dòng Linh Thạch 30 ngày của 3 kiểu người chơi
python -m client.tests.test_realm_flow anh/        # Cổng Bí Cảnh, lập tổ đội, vào bí cảnh cùng 2 bot, rời; phát lại cả lượt chơi
python tools/build_exe.py                          # đóng gói exe rồi tự chạy thử exe (--smoke-test)
```

Giai đoạn 10: `server/tests/test_admin.py` (mọi lệnh /admin, quyền, nhật ký, /server/info, /healthz, đánh dấu bot),
`server/tests/test_release.py` (chuỗi kết nối Neon, sao lưu Python và shell, file Docker/Render), một test WebSocket thật
khóa người chơi bằng /admin trong `test_ws.py`, và `client/tests/test_release.py` (server_list_url, kiểm tra phiên bản,
đường dẫn khi chạy từ exe).

Ba bot cùng vượt một bí cảnh qua WebSocket thật (máy chủ chạy với `BALANCE_PROFILE=dev` để Mặc Ảnh Động luôn mở; bot đọc
đáp án Vấn Đạo trong file cơ sở dữ liệu nên chỉ chạy cạnh máy chủ cục bộ):

```bash
cd server && BALANCE_PROFILE=dev python -m uvicorn app.main:app --port 8000   # cửa sổ 1
python tools/realm_bots.py --url http://127.0.0.1:8000 --db server/dev.db     # cửa sổ 2
```

`server/tests/test_journey.py` cho một bot WebSocket tự đi từ Phàm Nhân lên Trúc Cơ (làm nhiệm vụ, đánh quái,
đả tọa, vượt Thiên Kiếp) với `BALANCE_PROFILE=dev`, mất khoảng một phút rưỡi.

Thử tải thế giới chung với 50 bot đi lại và chat trong 10 phút (kết quả trong `docs/LOAD_TEST.md`):

```bash
cd server && ACCOUNTS_PER_IP=500 RATE_LIMIT=0 python -m uvicorn app.main:app --port 8000   # cửa sổ 1
python tools/load_bots.py --bots 50 --minutes 10                                         # cửa sổ 2
```

## Tài nguyên

```bash
python tools/fetch_assets.py     # tải font (đã có sẵn trong gói này)
python tools/generate_audio.py   # sinh âm phát âm bằng edge-tts (cần mạng); game chạy được khi không có
python tools/gen_sprites.py      # xuất sprite ra PNG
python tools/gen_maps.py         # dựng lại bản đồ động phủ, Trúc Lâm Thôn, Rừng Mực Loang, Hồ Nghiên Mực (.tmj, mở được bằng Tiled)
python tools/gen_td_levels.py    # dựng lại 30 ải thủ vườn + bản đồ Vô Tận Trận (server/data/td/levels.json)
```

## Dữ liệu từ vựng và việc duyệt nghĩa

Loài ong: sửa `tools/curation/bees.json` rồi chạy `python tools/build_bees.py` — script kiểm tra chữ của mỗi loài có
trong danh sách từ, lấy pinyin từ dữ liệu đã kiểm chứng và CC-CEDICT, đánh dấu tên nào là từ có thật.

Loài cá: sửa `tools/curation/fish.json` rồi chạy `python tools/build_fish.py` — tên cá có thật phải có trong CC-CEDICT
(pinyin và nghĩa lấy từ đó), tên sáng tác (`fictional`) thì từng âm phải là một cách đọc của chữ đó trong CC-CEDICT.

```bash
python tools/build_wordlist.py            # dựng lại từ nguồn đã tải trong tools/raw/
python tools/build_wordlist.py --refresh  # tải lại nguồn mới nhất
```

Nghĩa tiếng Việt, câu ví dụ và câu luyện tập do AI viết nên **cần người duyệt**:
mở `tools/reports/review_sheet.csv` và `sentences_review.csv` bằng Excel, đánh `x` vào dòng đúng hoặc gõ
bản sửa vào cột `*_fixed`, rồi chạy `python tools/apply_review.py`. Câu chưa duyệt chỉ được dùng khi
`ALLOW_UNREVIEWED=1` (mặc định ở môi trường dev).

## Lộ trình

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| 1 | Dữ liệu + server học tập lõi | ✅ |
| 2 | Client pixel + Động phủ, vườn đầy đủ | ✅ |
| 3 | Thế giới online (WebSocket, nhiều người chơi, chat, bạn bè) | ✅ |
| 4 | Chiến đấu Vấn Đạo, tu luyện, Thiên Kiếp | ✅ |
| 5 | Ong linh | ✅ |
| 6 | Câu cá | ✅ |
| 7 | Thủ Vườn (tower defense) + Tàng Thư Các | ✅ |
| 8 | Luyện đan, khắc văn, pet, kinh tế | ✅ |
| 9 | Bí cảnh hợp tác | ✅ |
| 10 | Phát hành (exe, Docker, triển khai miễn phí) | ✅ (còn: triển khai thật bằng tài khoản của bạn, `docs/DEPLOY.md` mục G) |

## Giấy phép dữ liệu

Dữ liệu từ vựng dẫn xuất từ CC-CEDICT nên phát hành theo **CC BY-SA 4.0**. Font theo SIL OFL 1.1.
Xem `CREDITS.md`.
