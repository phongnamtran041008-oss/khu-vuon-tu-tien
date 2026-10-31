# Ghi công (Credits)

Khu Vườn Tu Tiên dùng các dữ liệu và công cụ mở sau. Cảm ơn những người đã xây dựng chúng.

## Dữ liệu ngôn ngữ

- **CC-CEDICT** — từ điển Trung–Anh do cộng đồng duy trì, phát hành bởi MDBG.
  Giấy phép: Creative Commons Attribution-ShareAlike 4.0 International
  (https://creativecommons.org/licenses/by-sa/4.0/).
  Trang chủ: https://cc-cedict.org/wiki/ · Tải về: https://www.mdbg.net/chinese/dictionary?page=cc-cedict
  Dựa trên CEDICT — Copyright (C) 1997, 1998 Paul Andrew Denisowski.
  Bản dùng trong lần dựng hiện tại: export ngày 2023-11-07 (xem `tools/raw/SOURCES.md`).
- **complete-hsk-vocabulary** (Yanis Zafirópulos, https://github.com/drkameleon/complete-hsk-vocabulary)
  — danh sách từ HSK 3.0. Giấy phép MIT.
- **Make Me a Hanzi** (Shaunak Kishore, https://github.com/skishore/makemeahanzi) — tệp `dictionary.txt`
  (bộ thủ, cấu tạo chữ), dẫn xuất từ Unihan và CJKlib. Giấy phép GNU LGPL phiên bản 3 trở lên.

**Giấy phép của dữ liệu từ vựng trong game:** các tệp `server/data/words/*.json`,
`server/data/sentences.json`, `combos.json`, `tone_mishaps.json`, `creatures/bees.json` (tên Hán và pinyin của ong), `creatures/fish.json` (tên Hán, pinyin, nghĩa tiếng Anh của cá) chứa nội dung dẫn xuất từ CC-CEDICT,
nên được phát hành theo cùng giấy phép **CC BY-SA 4.0**. Phần dẫn xuất từ Make Me a Hanzi giữ giấy phép
LGPL-3.0+.

Nghĩa tiếng Việt, câu ví dụ, câu luyện tập và truyện thành ngữ do AI viết dựa trên nghĩa tiếng Anh của
CC-CEDICT và **cần người duyệt** (cờ `meaning_vi_reviewed`, `example_reviewed`, `reviewed`).

## Phần mềm

FastAPI, SQLAlchemy, Alembic, bcrypt, PyJWT, Uvicorn, websockets, httpx, pygame-ce, pytest (các giấy phép
MIT/BSD/Apache/LGPL tương ứng).

## Phông chữ

- **Noto Sans SC** (Google / Adobe, https://github.com/notofonts/noto-cjk) — SIL Open Font License 1.1.
  Game dùng bản cắt gọn (subset) do `tools/fetch_assets.py` tạo; giấy phép đi kèm trong
  `client/assets/fonts/NotoSansSC-LICENSE.txt`.
- **VT323** (Peter Hull, The VT323 Project Authors, https://github.com/google/fonts/tree/main/ofl/vt323) —
  SIL Open Font License 1.1, giấy phép trong `client/assets/fonts/VT323-OFL.txt`.

## Hình ảnh và âm thanh

Toàn bộ hình pixel (nhân vật, dân làng, Mặc Quái gồm Mặc Hồ, vũ khí, hiệu ứng chiến đấu và sấm Thiên Kiếp, cây, nhà cửa, đạo cụ, bản đồ Trúc Lâm Thôn và Rừng Mực Loang) và âm thanh hiệu ứng được tạo bằng code trong dự án,
không dùng gói asset bên ngoài. Phát âm từ vựng (nếu có) tạo bằng `edge-tts` giọng `zh-CN-XiaoxiaoNeural`.
