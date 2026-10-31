# Cân bằng kinh tế — dòng Linh Thạch vào và ra

Giai đoạn 8 (đặc tả 12.1, 12.4, 20). Mọi con số nằm trong `server/data/balance/*.json` và các file dữ liệu
(`items/*.json`, `recipes.json`, `creatures/*.json`, `quests.json`); tài liệu này giải thích chúng ăn khớp với nhau
thế nào. Số trong bảng dưới là **kết quả chạy `python tools/economy_sim.py`** trên đúng dữ liệu hiện tại — sửa số liệu
thì chạy lại script, đừng sửa tay bảng này.

## Hai loại tiền

| Tiền | Có từ đâu | Tiêu vào đâu |
|---|---|---|
| **Linh Thạch** (tiền chính) | trả lời đúng (ôn vườn), bán quả chữ / cá / mật / đồ, hạ quái, ải Thủ Vườn, nhiệm vụ (cốt truyện, hằng ngày), tưới giúp bạn, mốc phổ | gacha, mở ô đất, mở ô tổ ong, nâng tổ, cường hóa, lò đan, cần câu, phí luyện đan, khắc văn, sạp tạp hóa, giâm cành |
| **Tiên Ngọc** (hiếm) | Thiên Kiếp, nhiệm vụ cốt truyện, mốc Tàng Thư Các / Ong Phổ / Ngư Phổ, sao đầu ải, quà xong cả ngày (1/ngày) | gacha Trứng Ong, Linh Thú (giá thay thế); không mua được bằng tiền thật, không đổi qua lại với Linh Thạch |

Không có giao dịch giữa người chơi (v1). Bạn bè chỉ tặng nhau **vật phẩm** không ràng buộc (5 lần/ngày, mỗi lần tối đa
5 cái) — không bao giờ tặng tiền hay trang bị.

## Nguyên tắc: tiền chỉ đến từ thời gian chơi và câu trả lời

1. **Mọi nguồn vào đều bị giới hạn bởi thời gian hoặc câu hỏi.** Ôn vườn theo lịch SRS (10 phút, 1, 3, 7 ngày); quái
   chỉ chết khi trả lời đúng; cá cắn theo thời gian thực; mật làm theo giờ và tổ có sức chứa; thưởng chơi lại ải tối
   đa 5 lần/ngày; nhiệm vụ hằng ngày 3 việc/ngày; tưới giúp 5 lần/ngày; mốc phổ và nhiệm vụ cốt truyện chỉ một lần.
2. **Không có "lãi".** Không nguồn nào lớn lên theo số dư. Đầu tư (ô đất, ô tổ, cấp tổ, lò đan, cần câu) làm nguồn
   vào nhích lên nhưng mỗi thứ có mức tối đa, nên thu nhập một ngày có trần.
3. **Mọi phép đổi tức thời đều lỗ.** Bất cứ thứ gì mua được bằng Linh Thạch đều bán lại rẻ hơn nhiều (thường 10–25%
   giá mua). Luyện đan, cắt mồi, cường hóa rồi bán, mở gacha rồi bán đồ trùng — giá trị trung bình nhận về luôn thấp
   hơn bỏ ra. Đan dược bán cho làng thấp hơn giá nguyên liệu (kể cả nguyên liệu chỉ có được bằng cách chơi).

## Kiểm tra "không có vòng lặp tạo tiền vô hạn"

`tools/economy_sim.py` (và `server/tests/test_economy.py`) xây một đồ thị từ dữ liệu thật:

- **Đỉnh**: mọi vật phẩm, `fruit:<độ hiếm>`, `fish_<loài>`, `equip:<độ hiếm>:<cấp cường hóa>`, hạt trùng.
- **Cạnh**: mua ở Sạp Tạp Hóa, Ngư Ông, Tàng Thư Các; luyện đan (ở lò tốt nhất, chất lượng cao nhất, cộng 1 viên của
  lò Tử Kim); cắt mồi; cường hóa (chi phí kỳ vọng = chi phí / tỉ lệ thành công); gacha theo **giá trị trung bình**.
- **Giá có được**: với mỗi món, cách rẻ nhất để có nó chỉ bằng Linh Thạch (điểm bất động trên đồ thị).

Nếu có món nào bán được bằng hoặc hơn giá có được, đó là vòng lặp tạo tiền. Kết quả hiện tại: **không có**. Món
"lời" nhất là Trúc Diệp Thảo, giun đất và hạt trùng (bán lại được 25% giá có được). Quả chữ, cá, mật, Linh Quả, đồ
rơi không có giá Linh Thạch (chỉ có bằng thời gian + câu trả lời), nên không thể khép một vòng lặp.

Test còn kiểm tra:

- mọi thứ sạp bán đều thu mua lại thấp hơn giá bán;
- mỗi đan phương: (số viên tối đa × giá bán đan) < (phí lò + giá bán nguyên liệu), kể cả nguyên liệu quý;
- gacha Linh Thú khi mọi con đã đủ cấp chỉ hoàn trung bình ~117 Linh Thạch trên 500;
- bán hạt trùng (20) < giá một lượt Hạt Chữ (100) hay Hạt Giống Thường (80).

## Mô hình 30 ngày, ba kiểu người chơi

| Kiểu | Thời gian | Hoạt động mỗi ngày (mô hình) |
|---|---|---|
| **Thong Thả** | 20 phút | mở vườn 1 lần (đúng 75%), 8 quái, 1/3 việc hằng ngày, chỉ quay lượt miễn phí |
| **Chăm Chỉ** | 1 giờ | mở vườn 2 lần (đúng 85%), 30 quái, 10 lần câu, 2 ải, 1 mẻ đan, gần đủ việc hằng ngày, 1 lượt Hạt Chữ, trứng ong 4 ngày/lần, Linh Thú 10 ngày/lần, cường hóa tới +5, khắc văn mỗi tuần |
| **Cày Cuốc** | 4 giờ | mở vườn 4 lần (đúng 90%), 140 quái, 50 lần câu, 6 ải, 4 mẻ đan, đủ việc hằng ngày, 4 lượt Hạt Chữ, trứng ong mỗi ngày, Linh Thú 3 ngày/lần, cường hóa tới +8, khắc văn 3 ngày/lần |

Giá trị mỗi hành động lấy thẳng từ dữ liệu: một lần hạ quái trung bình **16,1** Linh Thạch (gồm đồ rơi theo giá làng
mua), một con cá **30,4** (theo `rarity_weight`), một cây ra 140 Linh Thạch tiền ôn + 3 quả (~29 mỗi quả theo tỉ lệ
gacha), một lượt chơi lại ải 15, việc hằng ngày ~134 + 50 khi xong cả ngày, nhiệm vụ cốt truyện tổng 1.660 (một lần).

Kết quả sau 30 ngày (`python tools/economy_sim.py`, có bảng từng ngày):

| Kiểu | Vào | Ra (vòi xả) | % quay về vòi xả | Còn lại | Tiên Ngọc |
|---|---:|---:|---:|---:|---:|
| Thong Thả | 12.705 | 11.409 | 90% | 1.596 | 36 |
| Chăm Chỉ | 48.772 | 42.268 | 87% | 6.804 | 50 |
| Cày Cuốc | 139.193 | 95.865 | 69% | 43.628 | 80 |

Nguồn vào lớn nhất của người chơi thong thả là hạ quái và ôn vườn; người chơi nhiều giờ dựa vào quái, cá và mật — tức
là đều phải trả lời câu hỏi hoặc chờ thời gian thật. Vòi xả lớn nhất: mở ô đất (11–13 nghìn), mở ô tổ ong, gacha,
nâng tổ, cần câu, lò đan, cường hóa.

Điều test khẳng định (`test_thirty_days_of_three_kinds_of_player`, `test_money_does_not_breed_money`):

- không ngày nào số dư âm; ít nhất 60% Linh Thạch kiếm được quay về vòi xả;
- chơi nhiều giờ **không** kiếm nhanh hơn mỗi phút (Cày Cuốc ≈ 19,3/phút, Thong Thả ≈ 21,2/phút): vườn đi theo lịch
  ôn nên 4 giờ/ngày chỉ được tiền vườn gấp ~2,2 lần 20 phút/ngày;
- một người bắt đầu với 1 tỉ Linh Thạch, mua hết mọi nâng cấp ngay ngày đầu, vẫn chỉ kiếm tối đa ~1,6 lần một ngày
  tốt nhất của Cày Cuốc bình thường, và thu nhập phẳng hẳn sau khi đã mua hết: **tiền không đẻ ra tiền**.

Cày Cuốc vẫn dư ~43 nghìn sau 30 ngày (tăng tuyến tính ~1.500/ngày, không theo cấp số nhân). Đó là chỗ dành cho các vòi
xả lớn của giai đoạn sau: cần Long Cốt (4.000), tổ cấp 5 (4.000), lò Tử Kim (2.500), đan Kim Đan (phí 500 mỗi mẻ),
cường hóa +9/+10 (tỉ lệ 30%/20%), bí cảnh (giai đoạn 9).

## Các vòi xả mới của giai đoạn 8

| Vòi xả | Giá | File |
|---|---|---|
| Phí lò luyện đan | 10–500 mỗi mẻ (theo đan) | `recipes.json` |
| Nâng Đan Lô | 800 + 10 Mực Tinh + 8 Gỗ; 2.500 + 25 Mực Tinh + 5 Mặc Linh Chi | `balance/alchemy.json` |
| Khắc Văn | 60 Linh Thạch + 2 Mực Tinh mỗi lần thử (sai là mất); mài chữ 30 | `balance/inscription.json` |
| Gacha Linh Thú | 500 / 4.500 cho 10 (hoặc 10 / 90 Tiên Ngọc) | `balance/gacha.json` |
| Sạp Tạp Hóa | đan 40, Trúc Diệp Thảo 8, Mực Tinh 15, giun 5, hạt thường 80; đồ Phàm 120, Linh 450 | `balance/shop.json` |
| Đan phương ở Tàng Thư Các | 150–4.000 (mỗi loại một lần) | `balance/library.json` |

Sạp có **giới hạn mỗi ngày** cho từng món (10 đan, 30 dược thảo, 20 Mực Tinh, 3 hạt...) để không ai mua sạch Mực Tinh
mà cường hóa thay cho việc đánh quái, và Hạt Giống Thường tính vào giới hạn 15 hạt mới/ngày của gacha.

## Linh Thú và kinh tế

Kỹ năng pet chỉ chỉnh phần thưởng quanh một câu hỏi, không bao giờ thay câu hỏi: Trâu +20% tiền ôn đúng, Rồng gấp đôi
câu thứ 5 liên tiếp, Lợn +10% khi bán quả, Ngựa +15% Linh Thạch hạ quái, Chó +15% đồ rơi, Dê +15% mật khi thu, Mèo
+0,1 may mắn câu cá, Chuột +5% hạt Hiếm, Gà +10% Tu Vi khi ôn, Hổ sương mực chậm một nửa, Rắn Mặc Kích nhẹ 20%,
Khỉ +20 Linh Khí khởi đầu ở ải. Phép kiểm tra vòng lặp đã tính sẵn Lợn (giá quả cao nhất có thể). Chỉ đeo một con.

## Bí cảnh (giai đoạn 9)

Bí cảnh là một **nguồn vào có giới hạn** chứ không phải vòng lặp: mỗi bí cảnh 2 lượt/ngày (UTC+7), phải giải đố bằng chữ
đã học và hạ boss bằng câu trả lời đúng của từng người. Linh Thạch trung bình mỗi lượt thắng (`balance/realm.json`):

| Bí cảnh | Mỗi gian (×số gian) | Rương | Một lượt | Xong nhanh (rương ×1,5) | Tối đa/ngày (2 lượt) |
|---|---|---|---|---|---|
| Khe Nứt Mực (3 câu đố + boss) | 22,5 × 4 | 110 | ~200 | ~255 | ~510 (nếu gặp được khe nứt) |
| Mặc Ảnh Động (5 câu đố + boss) | 22,5 × 6 | 210 | ~345 | ~450 | ~900 |

Tiên Ngọc 0–2 / 1–4 mỗi rương. Những thứ không mua được bằng Linh Thạch — **Thiên Tằm Ti**, **Mảnh Bảo Vật**, đồ bộ
**Mặc Ảnh** — chỉ đến từ bí cảnh, nên không thể tạo vòng lặp với cửa hàng: phép kiểm tra vòng lặp ở trên chỉ đi qua các
phép đổi bắt đầu bằng Linh Thạch. Hai vòi xả mới gắn với chúng: **Ghép Bảo Vật** (12 mảnh + 600 Linh Thạch một món phẩm
Thiên) và **Cần Thiên Tơ** (12 Thiên Tằm Ti + 30 Vảy + 6.000 Linh Thạch). Làng mua lại Thiên Tằm Ti 25, Mảnh Bảo Vật 10
— bán đi là bỏ phí: một món Thiên ghép từ 12 mảnh (120 nếu bán) đáng giá hơn nhiều. Chia Tu Vi trong tổ đội không cho
Linh Thạch.

## Khi chỉnh số liệu

1. Sửa file JSON.
2. `python tools/economy_sim.py` — đọc dòng "KHÔNG có vòng lặp tạo tiền" và bảng 30 ngày.
3. `cd server && python -m pytest tests/test_economy.py -s` — in lại dòng tiền và kiểm tra các điều kiện ở trên.
4. Cập nhật bảng trong tài liệu này bằng số mới.
