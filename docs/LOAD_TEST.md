# Thử tải thế giới chung (giai đoạn 3)

Tiêu chí của đặc tả (mục 20, giai đoạn 3): `tools/load_bots.py` chạy **50 bot di chuyển + chat ổn định 10 phút**,
**tick không trễ quá 50 ms**.

## Cách chạy

```bash
# cửa sổ 1: máy chủ cho phép nhiều tài khoản từ một IP và tắt giới hạn tần suất REST
cd server
ACCOUNTS_PER_IP=500 RATE_LIMIT=0 python -m uvicorn app.main:app --port 8000
# cửa sổ 2
python tools/load_bots.py --server http://127.0.0.1:8000 --bots 50 --minutes 10 --report ketqua.json
```

Mỗi bot: đăng ký (hoặc đăng nhập lại), tạo nhân vật, ra Trúc Lâm Thôn, đi ngẫu nhiên (gửi phím 20 lần/giây như game
thật), chat trung bình mỗi 20 giây (Khu vực hoặc Thế giới), ping mỗi 10 giây. Công cụ đọc `/server/stats` mỗi 2 giây.
**Đạt** khi không tick nào chạy quá 50 ms hoặc bắt đầu trễ quá 50 ms, cả 50 bot vào được làng và không bot nào bị ngắt.

## Kết quả (30/10/2026)

Máy dựng: container Linux 2 nhân, Python 3.13, SQLite; máy chủ và 50 bot chạy **trên cùng một máy**.

| | Lần 1 | Lần 2 |
|---|---|---|
| Thời gian | 10 phút | 10 phút |
| Bot vào làng | 50/50 (tự chia kênh 40 + 10) | 50/50 (40 + 10) |
| Số tick | 12 350 | 12 338 (≈ 20,6 tick/giây) |
| Tick trung bình / p99 | 2,1 / 5,8 ms | 2,3 / 6,2 ms |
| Tick lâu nhất | 63,2 ms | **38,4 ms** |
| Tick bắt đầu trễ nhất | 194,7 ms | **43,6 ms** (lúc khởi động, trước khi bot vào) |
| Snapshot nhận được | 9,9 /bot/giây | 9,9 /bot/giây |
| Tin chat gửi / nhận | 1 505 / 59 150 | 1 482 / 58 473 |
| Ping (trung vị / lớn nhất) | 1,2 / 258 ms | 1,3 / 65 ms |
| Bị ngắt kết nối | 0 | 0 |
| Kết luận | không đạt | **đạt** |

Lần 1 có hai đợt trễ ở phút thứ 8–9, đúng lúc trên cùng máy đang chạy thêm các lệnh nặng khác (máy chủ và bot tranh
CPU với chúng). Lần 2 chạy khi máy rảnh. Trước hai lần này đã sửa ba nguyên nhân làm tick trễ mà lần thử đầu tìm ra
(xem `DECISIONS.md`): bcrypt chạy trong event loop (~70 ms mỗi lần đăng nhập), bản đồ đọc lúc người đầu tiên bước vào,
và lượt dọn rác đầy đủ của Python (`gc.freeze()` sau khi khởi động; trong 10 phút lần 2 không có lượt dọn rác đầy đủ nào
ngoài lượt cố ý lúc khởi động).

Máy chủ thật nên chạy riêng một máy, không chung với bot; khi triển khai (giai đoạn 10) chạy lại công cụ này trên máy chủ
đó và ghi kết quả vào `DEPLOY.md`.
