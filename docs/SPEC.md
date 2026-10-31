# PROMPT: Xây dựng game "Vườn Chữ: Tu Tiên Lộ" (字园仙途 Zì Yuán Xiān Tú) — game tu tiên 2D pixel online nhiều người chơi, học tiếng Trung

> Bản 2. Kế thừa toàn bộ hệ thống vườn chữ, SRS, gacha, nguồn dữ liệu của bản 1, rồi mở rộng thành một thế giới tu tiên 2D pixel online: nhân vật đi lại, đánh quái bằng câu đố, ải thủ vườn (tower defense), ong linh, câu cá, luyện đan, bí cảnh hợp tác. Các mục 5 và 6 giữ gần như nguyên văn bản 1.

## 0. Vai trò và cách làm việc

Bạn là một lập trình viên game Python giàu kinh nghiệm (mạng thời gian thực, game 2D) kiêm game designer. Nhiệm vụ: xây dựng game "Vườn Chữ: Tu Tiên Lộ" theo đặc tả bên dưới, gồm **client Pygame (pixel art)** và **server FastAPI + WebSocket**, chạy được thật, nhiều người chơi cùng lúc, có tài khoản và lưu tiến trình trên server, triển khai được **hoàn toàn miễn phí** (mục 19).

Quy tắc làm việc:
- Làm **theo từng giai đoạn** ở mục 20. Hoàn thành, chạy thử và viết test cho giai đoạn hiện tại trước khi sang giai đoạn tiếp theo. Cuối mỗi giai đoạn, tóm tắt đã làm gì, cách chạy thử, và những gì còn thiếu so với đặc tả.
- Code phải **chạy được ngay**, không để `TODO` hay hàm rỗng trong phần đã nói là hoàn thành.
- Nếu đặc tả có chỗ mơ hồ, chọn phương án hợp lý nhất, ghi lại quyết định trong `docs/DECISIONS.md` rồi làm tiếp, không dừng lại hỏi trừ khi thật sự bế tắc.
- **Mọi con số cân bằng game** (máu, sát thương, giá, tỉ lệ rơi, thời gian) đặt trong file dữ liệu `server/data/balance/*.json`, không viết cứng trong code, để chỉnh mà không sửa logic.
- Không dùng asset ảnh/âm thanh có bản quyền. Pixel art vẽ bằng code hoặc lấy từ gói asset **CC0** (xem mục 18), ghi nguồn trong `CREDITS.md`.
- Không sao chép tên, hình, thiết kế của game khác (kể cả Bee Swarm Simulator, Plants vs. Zombies). Chỉ lấy cảm hứng cơ chế; mọi loài ong, cây, quái, vật phẩm đều tự thiết kế.
- Toàn bộ giao diện hiển thị bằng **tiếng Việt**, nội dung học là **tiếng Trung giản thể + pinyin có dấu thanh**.
- Code, tên biến, comment viết bằng tiếng Anh; chuỗi hiển thị cho người chơi tách riêng vào `client/strings_vi.py`.

---

## 1. Tổng quan game

**Thể loại:** MMO 2D pixel nhìn từ trên xuống (top-down), tu tiên, kết hợp nông trại, gacha, tower defense, câu cá, nuôi ong; **mọi trận đánh và mọi phần thưởng lớn đều đi qua câu hỏi tiếng Trung**.

**Cốt truyện (phiên bản tu tiên):** Thiên địa vận hành nhờ **Chữ Đạo**: vạn vật có tên thì có linh khí. Ngàn năm trước, một thiếu niên thiên tài muốn giữ hết chữ cho riêng mình, luyện ra **Mặc Ma Ấn**, phong ấn bị vỡ, **Mặc Quái (墨怪)** tràn ra nuốt chữ; vật nào mất tên thì mất màu, linh mạch khô cạn. Tu sĩ đời nay tu theo **Chữ Đạo**: học một chữ là thu một tia linh khí, hiểu một câu là ngộ một tầng pháp. Người chơi là một phàm nhân vừa nhập môn, được **Trúc Lão** (gấu trúc thư pháp gia, ẩn sĩ lẩm cẩm, hài hước) nhận làm đệ tử, giao một mảnh động phủ hoang và hạt giống chữ đầu tiên. Bí mật cuối cùng (giữ từ bản 1): thiếu niên năm xưa chính là Trúc Lão.

**Vòng lặp chính:**
1. **Động phủ** (khu riêng của mỗi người): trồng cây chữ (học từ theo SRS), nuôi ong, xây tổ ong → ra linh quả, linh mật, nguyên liệu.
2. **Thế giới chung**: đi lại, gặp người chơi khác, đánh quái (mỗi trận có câu đố), câu cá, làm nhiệm vụ → kiếm Linh Thạch, Tu Vi, vật phẩm.
3. **Mạnh lên**: luyện đan, rèn và khắc chữ lên trang bị, quay gacha (hạt, ong, pet), đột phá cảnh giới (thi Thiên Kiếp bằng từ vựng).
4. **Thử thách**: ải Thủ Vườn (tower defense bằng cây của mình), bí cảnh hợp tác nhiều người lấy bảo vật.

**Nguyên tắc thiết kế cốt lõi:**
1. **Học là cách duy nhất để mạnh lên.** Cây chỉ lớn khi ôn đúng; kỹ năng chiến đấu là chữ đã thuộc; đột phá cảnh giới là bài thi từ vựng.
2. **Quên từ thì thấy bằng mắt:** từ quá hạn ôn bị sương mực lan vào ô đất, cây xám dần, và cây đó yếu đi trong ải Thủ Vườn.
3. **Không có tiền thật.** Không nạp, không bán vật phẩm, gacha chỉ dùng tiền trong game.
4. **Câu hỏi luôn công bằng:** chỉ hỏi những gì người chơi đã được dạy (đã có trong collection) hoặc nằm đúng cấp độ khu vực; đáp án chỉ nằm trên server.
5. **Ai cũng bắt đầu giống nhau:** nhân vật pixel cơ bản, bộ "Áo Vải Phàm Nhân" như nhau; mọi khác biệt về ngoại hình và sức mạnh phải tự cày ra.

---

## 2. Công nghệ

**Client:**
- Python 3.11+, `pygame-ce`
- `httpx` cho REST, `websockets` (chạy trong một thread asyncio riêng, giao tiếp với vòng lặp game qua `queue.Queue`) cho thế giới thời gian thực
- Bản đồ vẽ bằng **Tiled** (miễn phí), xuất `.tmj` (JSON); đọc bằng code tự viết hoặc `pytmx`
- Font: chữ Hán trong thẻ câu hỏi dùng **Noto Sans SC** cỡ lớn (đọc rõ quan trọng hơn phong cách pixel); chữ giao diện dùng một font pixel có giấy phép SIL OFL hỗ trợ cả tiếng Việt có dấu và chữ Hán giản thể (ứng viên: Fusion Pixel Font hoặc Ark Pixel Font — **kiểm tra giấy phép và độ phủ ký tự tiếng Việt trước khi dùng**, nếu thiếu dấu tiếng Việt thì dùng font pixel riêng cho chữ Latin). Script `tools/fetch_assets.py` tải font về `client/assets/fonts/`.
- Âm thanh phát âm: `tools/generate_audio.py` dùng `edge-tts` giọng `zh-CN-XiaoxiaoNeural`, lưu `client/assets/audio/{word_id}.mp3`. Game vẫn chạy được nếu thiếu file âm (ẩn nút loa, câu hỏi nghe đổi sang dạng xem pinyin).
- Đóng gói: PyInstaller, ra `VuonChu.exe`.

**Server:**
- FastAPI + Uvicorn; REST cho tài khoản, túi đồ, cửa hàng, vườn; **WebSocket `/ws`** cho thế giới (di chuyển, chiến đấu, chat, bí cảnh)
- SQLAlchemy 2.x (async) + Alembic; SQLite khi phát triển, PostgreSQL khi triển khai (`DATABASE_URL`)
- Mật khẩu băm `bcrypt`, JWT (`python-jose` hoặc `PyJWT`), token hết hạn 30 ngày
- Không dùng Redis hay dịch vụ trả phí; trạng thái thế giới giữ trong RAM của tiến trình server, chỉ dữ liệu bền mới ghi DB
- Test: `pytest`, `pytest-asyncio`, `httpx`; có bot giả lập người chơi (`tools/load_bots.py`) để thử tải
- Đóng gói server: `Dockerfile` + `docker-compose.yml` (server + postgres + reverse proxy)

**Cấu hình:** `.env` cho server. Client đọc `config.json` cạnh exe; nếu `config.json` có `server_list_url` thì tải danh sách máy chủ từ URL đó (vd một file JSON trong repo GitHub) để đổi địa chỉ server mà không cần phát hành exe mới.

---

## 3. Cấu trúc thư mục

```
vuon-chu/
├── server/
│   ├── app/
│   │   ├── main.py, config.py, db.py, models.py, schemas.py, auth.py
│   │   ├── learning/          # srs.py, quiz.py (sinh/chấm mọi dạng câu hỏi), question_bank.py
│   │   ├── garden/            # garden.py, combos.py, mishaps.py, letters.py, crafting.py
│   │   ├── realtime/
│   │   │   ├── ws.py          # endpoint /ws, xác thực, phân luồng message
│   │   │   ├── protocol.py    # định nghĩa message (pydantic), version giao thức
│   │   │   ├── world.py       # quản lý zone/channel, tick loop
│   │   │   ├── zone.py        # một bản đồ: entity, va chạm, vùng quan tâm (AOI)
│   │   │   ├── combat.py      # chiến đấu + Vấn Đạo (mục 8)
│   │   │   ├── ai.py          # hành vi quái
│   │   │   └── chat.py        # kênh chat, lọc từ, chặn spam
│   │   ├── systems/
│   │   │   ├── cultivation.py # Tu Vi, cảnh giới, Thiên Kiếp
│   │   │   ├── tower_defense.py
│   │   │   ├── bees.py, fishing.py, alchemy.py, forging.py, inventory.py
│   │   │   ├── gacha.py       # mọi loại gacha, pity
│   │   │   ├── secret_realm.py
│   │   │   ├── quests.py
│   │   │   └── social.py      # bạn bè, tổ đội, thăm động phủ
│   │   └── routers/
│   ├── data/
│   │   ├── words/             # words_hsk1.json, words_hsk2.json ... (mục 5)
│   │   ├── combos.json, sentences.json, letters.json, tone_mishaps.json
│   │   ├── items/             # equipment.json, pills.json, materials.json, rods.json, baits.json
│   │   ├── creatures/         # monsters.json, bees.json, fish.json, pets.json
│   │   ├── plants/            # plant_roles.json (vai trò tower defense theo chữ)
│   │   ├── td_levels/         # ải Thủ Vườn
│   │   ├── realms/            # bí cảnh
│   │   ├── quests.json, recipes.json, realms_cultivation.json
│   │   └── balance/           # mọi hằng số cân bằng
│   ├── maps/                  # file Tiled .tmj dùng chung cho server (va chạm, điểm sinh quái)
│   ├── alembic/, tests/, requirements.txt, Dockerfile
├── client/
│   ├── main.py                # vòng lặp game, quản lý scene
│   ├── net/                   # rest.py, ws_client.py, interpolation.py
│   ├── engine/                # camera, tilemap, sprite, animation, input, pixel scaling
│   ├── scenes/                # menu, login, world, abode (động phủ), quiz overlay, td, fishing, hive, alchemy, codex, gacha...
│   ├── ui/                    # button, textbox, panel, popup, tooltip, hotbar, chat box, font loader
│   ├── art/                   # bảng màu, định nghĩa sprite pixel bằng code, sinh spritesheet
│   ├── strings_vi.py
│   └── assets/                # fonts, audio, sprites đã sinh, maps (.tmj), tilesets
├── tools/                     # build_wordlist.py, apply_review.py, fetch_assets.py, generate_audio.py,
│                              # gen_sprites.py, build_exe.py, load_bots.py, backup_db.sh
├── deploy/                    # docker-compose.yml, Caddyfile, hướng dẫn Oracle/Render/Neon
├── docs/                      # DECISIONS.md, API.md, PROTOCOL.md, BALANCE.md, DEPLOY.md
├── CREDITS.md
└── README.md
```

---

## 4. Mô hình dữ liệu (database)

Giữ các bảng của bản 1 (đổi `coins` thành `spirit_stones` — Linh Thạch):
- **users**: id, username (unique), password_hash, recovery_code_hash, spirit_stones (mặc định 300), pity_* (theo từng loại gacha, lưu JSON), daily_new_seeds_count, daily_reset_date, current_letter_id, created_at, last_login_at, banned_until
- **words**, **plots**, **seeds**, **collection**, **fruits**, **crafted_sentences**, **quiz_sessions**, **friendships**: như bản 1 (`quiz_sessions` thêm cột `context` = `garden|combat|td|fishing|realm|tribulation|forge` và `expires_at`)

Thêm mới:
- **characters**: user_id (1 người 1 nhân vật ở v1), display_name (unique, kiểm duyệt từ cấm), realm (cảnh giới), realm_stage (tầng), cultivation_xp (Tu Vi), hp, max_hp, qi (Linh Lực), stats JSON (công, thủ, tốc, bạo kích, kháng mực), zone_id, x, y, appearance JSON (màu tóc, kiểu tóc chọn khi tạo nhân vật), hotbar JSON
- **inventory_items**: id, user_id, item_id, quantity, bound (bool)
- **equipment_instances**: id, user_id, item_id, rarity, enhance_level, inscriptions JSON (chữ đã khắc), equipped_slot (nullable)
- **skills**: user_id, skill_id, level, unlocked_at (kỹ năng gắn với chữ, mục 8.4)
- **bees**: id, user_id, bee_type, level, xp, hive_slot (nullable), role (`hive|pollinate|guard`), bond
- **hive**: user_id, layout JSON (ô tổ), level, decorations JSON
- **pets**: id, user_id, pet_type, level, equipped
- **fish_catches**: user_id, fish_id, count, best_size_cm, first_caught_at (dùng cho Ngư Phổ và bảng kỷ lục)
- **codex_entries**: user_id, codex (`plant|fish|bee|monster|pet|item`), entry_id, discovered_at, progress JSON
- **td_progress**: user_id, level_id, stars, best_wave, cleared_at
- **td_loadout**: user_id, slots JSON (tối đa 8 loại cây mang vào ải)
- **quests**: user_id, quest_id, state, progress JSON
- **realm_runs**: id, realm_id, started_at, ended_at, result, members JSON
- **realm_loot**: run_id, user_id, item_id, quantity (chia loot riêng từng người)
- **chat_reports**, **blocks**: báo cáo và chặn người chơi
- **audit_log**: mọi thay đổi tiền/vật phẩm hiếm (user_id, delta, reason, ref_id, created_at) để truy vết lỗi và gian lận

Mọi thao tác cộng/trừ tiền và vật phẩm đi qua **một service duy nhất** (`inventory.py`), trong transaction, ghi `audit_log`, không cho số âm.

---

## 5. Từ vựng: nguồn dữ liệu và quy trình xây dựng

**Nguyên tắc: KHÔNG tự viết danh sách từ, pinyin hay nghĩa từ trí nhớ.** Mọi dữ liệu ngôn ngữ phải lấy từ nguồn mở đã được kiểm chứng, qua script có thể chạy lại. Sai pinyin là lỗi nghiêm trọng nhất của một game học ngôn ngữ.

### 5.1 Nguồn dữ liệu

| Dữ liệu | Nguồn | Giấy phép | Ghi chú |
|---|---|---|---|
| Danh sách từ theo cấp HSK | `drkameleon/complete-hsk-vocabulary` trên GitHub, file `wordlists/inclusive/new/1.json` (HSK 3.0 cấp 1) | MIT | Tổng hợp từ danh sách HSK 3.0 chính thức (2021); có hanzi, pinyin, tần suất, từ loại |
| Pinyin và nghĩa tiếng Anh | **CC-CEDICT** (tải bản export mới nhất từ mdbg.net / cc-cedict.org) | CC BY-SA | Từ điển Trung–Anh cộng đồng duy trì lâu năm, có biên tập viên kiểm duyệt |
| Cấu tạo chữ, bộ thủ (để kiểm tra công thức ghép chữ ở mục 6.5) | `skishore/makemeahanzi`, file `dictionary.txt` | Kiểm tra giấy phép trong repo trước khi dùng | Có trường `decomposition` mô tả chữ ghép từ thành phần nào |
| Phát âm | `edge-tts` giọng `zh-CN-XiaoxiaoNeural` | — | Sinh từ hanzi, không tự đánh vần |

Nguồn nào tải không được thì dừng lại báo cho người dùng, **không thay bằng dữ liệu tự nghĩ ra**.

### 5.2 Quy trình (script `tools/build_wordlist.py`)

1. Tải danh sách HSK 3.0 cấp 1 và CC-CEDICT vào `tools/raw/` (không commit file thô lớn; ghi nguồn và ngày tải vào `tools/raw/SOURCES.md`).
2. Với mỗi từ HSK: lấy hanzi, pinyin, cấp độ, tần suất từ danh sách HSK; tra CC-CEDICT để lấy nghĩa tiếng Anh và **đối chiếu pinyin**. Nếu pinyin hai nguồn không khớp (sau khi chuẩn hóa dấu thanh, bỏ qua biến điệu thanh), ghi từ đó vào `tools/reports/pinyin_conflicts.csv` để người dùng tự quyết, không tự chọn.
3. Chọn khoảng **80 từ** thuộc HSK 3.0 cấp 1, ưu tiên tần suất cao, chia theo chủ đề: chào hỏi, gia đình, số đếm, đồ ăn, thiên nhiên, hành động cơ bản. Bắt buộc có các chữ đơn dùng cho phản ứng kề ô: 木, 火, 水, 日, 月, 女, 子, 人, 口, 山, 大, 小, 马, 妈, 买, 卖, 问 (chữ nào không thuộc HSK 1 thì vẫn lấy dữ liệu từ CC-CEDICT và đánh dấu `hsk_level` thực tế).
4. Phân bổ độ hiếm theo tần suất: khoảng 60 common, 15 rare, 5 epic. **3 thành ngữ legendary** (vd 一石二鸟, 画蛇添足, 对牛弹琴) cũng lấy pinyin và nghĩa từ CC-CEDICT; câu chuyện tiếng Việt kể lại bằng lời văn riêng.
5. **Nghĩa tiếng Việt**: chưa có từ điển Trung–Việt mở đủ uy tín được xác nhận, nên dịch từ nghĩa tiếng Anh của CC-CEDICT sang tiếng Việt, đặt `meaning_vi_reviewed = false`. Tương tự, câu ví dụ do AI viết phải dùng từ trong phạm vi HSK 1–2, đặt `example_reviewed = false`.
6. Xuất `server/data/words_hsk1.json` và một file `tools/reports/review_sheet.csv` (hanzi, pinyin, nghĩa Anh, nghĩa Việt, câu ví dụ) để người dùng mở bằng Excel duyệt lại từng dòng. Script `tools/apply_review.py` đọc file đã duyệt và bật cờ `reviewed`.
7. Với các công thức ghép chữ ở `combos.json`, đối chiếu với trường `decomposition` của makemeahanzi; công thức nào không khớp cấu tạo thật thì ghi chú trong game là "ghép vui" chứ không trình bày như từ nguyên học.

### 5.3 Ghi công nguồn

- Thêm màn **Ghi công (Credits)** trong menu và file `CREDITS.md`, ghi rõ CC-CEDICT (kèm giấy phép CC BY-SA và đường link), complete-hsk-vocabulary, makemeahanzi, Noto Sans SC.
- Vì CC-CEDICT là CC BY-SA, file dữ liệu từ vựng phát hành kèm game phải giữ cùng giấy phép; ghi điều này trong `CREDITS.md`.

### 5.4 Test bắt buộc

- Mọi từ có đủ trường, pinyin không rỗng, pinyin có dấu và pinyin dạng số khớp nhau khi chuyển đổi.
- Mọi từ có `source` hợp lệ; không có từ nào không truy được về nguồn.
- Số ký tự trong hanzi bằng số âm tiết trong pinyin.
- Cảnh báo (không làm test fail) nếu còn từ có `meaning_vi_reviewed = false`.

---

### 5.5 Mở rộng sang HSK 2–3
- Chạy lại cùng quy trình cho `wordlists/inclusive/new/2.json` (Trúc Cơ) và `3.json` (Kim Đan, giai đoạn mở rộng), xuất `words_hsk2.json`, `words_hsk3.json`.
- Thêm trường `measure_words` (từ mục `CL:` của CC-CEDICT, rỗng nếu không có), `radical` và `components` (từ makemeahanzi) cho mọi chữ.
- Tên tiếng Trung của ong, cá, quái, đan dược: nếu là từ có thật thì tra CC-CEDICT như từ vựng; nếu là tên sáng tác thì đặt `fictional: true` và **không** dùng làm câu hỏi từ vựng.
- Ghi công thêm font pixel, gói asset CC0 (nếu dùng) trong `CREDITS.md`.

---

## 6. Vườn chữ trong động phủ (hệ thống của bản 1)

Toàn bộ mục này giữ nguyên từ bản 1, đặt trong khu **Động Phủ** của mỗi người chơi (mục 7.1). Vườn là nơi **học từ mới và ôn tập theo SRS**; mọi hệ thống khác (chiến đấu, ải, bí cảnh) chỉ dùng lại những từ đã học ở đây.

### 6.1 Gacha
- Giá: 100 Linh Thạch/lần, 900 cho 10 lần (10 lần đảm bảo ít nhất 1 Rare trở lên).
- Tỉ lệ: Common 70%, Rare 22%, Epic 7%, Legendary 1%.
- Pity: không ra Epic+ sau 40 lần thì lần 40 chắc chắn Epic; không ra Legendary sau 90 lần thì lần 90 chắc chắn Legendary. Reset bộ đếm tương ứng khi ra.
- Ưu tiên từ người chơi **chưa có** trong collection; nếu đã có hết từ ở độ hiếm đó thì cho hạt trùng (có thể bán lấy 20 Linh Thạch).
- Giới hạn **15 hạt mới mỗi ngày** (theo ngày UTC+7). Hết lượt thì gacha báo "Hạt giống cần nghỉ ngơi, mai quay lại nhé".
- **Toàn bộ random và trừ tiền diễn ra trên server.**
- Client làm hiệu ứng mở hạt: hạt rung, nứt ra, ánh sáng màu theo độ hiếm (xám, xanh dương, tím, vàng kim).

### 6.2 SRS và giai đoạn cây
| Giai đoạn | Tên | Ôn tiếp sau | Dạng câu hỏi để lên giai đoạn kế |
|---|---|---|---|
| 0 | Hạt vừa gieo | ngay | Màn giới thiệu từ: chữ to, pinyin, nghĩa, ví dụ, nút nghe. Bấm "Đã nhớ" lên giai đoạn 1 |
| 1 | Nảy mầm | 10 phút | Nhìn chữ Hán → chọn nghĩa đúng (4 đáp án) |
| 2 | Cây non | 1 ngày | Nhìn chữ Hán → chọn pinyin đúng (đáp án nhiễu khác dấu thanh) |
| 3 | Ra hoa | 3 ngày | Nghe âm (hoặc xem pinyin nếu không có âm) → chọn chữ Hán |
| 4 | Kết trái | 7 ngày | Gõ pinyin dạng số (vd `ma1`) hoặc điền từ vào chỗ trống trong câu ví dụ |
| 5 | Chín | — | Thu hoạch được |

- Trả lời đúng: lên một giai đoạn, cộng tiền (10 × số giai đoạn mới), mastery +10.
- Trả lời sai: không lên giai đoạn, `next_review_at` đặt lại sau 5 phút, wither +20, mastery −5.
- Chỉ được trả lời khi `now >= next_review_at`; trước đó cây hiện đồng hồ đếm ngược.
- Đáp án nhiễu lấy từ các từ khác trong data, ưu tiên từ cùng chủ đề hoặc cùng âm khác thanh.
- Thêm hằng số `TIME_SCALE` trong config server để rút ngắn thời gian khi test (vd 1 ngày = 1 phút).
- **Thời gian luôn lấy theo đồng hồ server.**

### 6.3 Mặc Quái (sương mực)
- Nếu quá `next_review_at` hơn 1 ngày, wither tăng dần 10/ngày. Tính lười (lazy) khi người chơi tải vườn, không cần job chạy nền.
- wither 0–30: cây bình thường; 30–70: cây nhạt màu, có vệt mực; 70–100: cây gần như xám, sương mực đen phủ ô.
- wither đạt 100: cây lùi một giai đoạn (không chết, không mất từ).
- Ôn đúng: wither giảm 50, kèm hiệu ứng sương mực tan thành hạt sáng.
- Trên màn vườn, sương mực vẽ bằng các vòng tròn đen trong suốt chuyển động chậm.

### 6.4 Thu hoạch, bán, ghép câu
- Cây chín bấm vào thu hoạch được 3 quả chữ của từ đó; ô đất trống lại; từ vẫn ở collection.
- Bán quả: common 15, rare 40, epic 100, legendary 300 Linh Thạch.
- **Ghép câu** (`sentences.json`, khoảng 25 câu dùng từ HSK1, vd 我喜欢吃苹果): màn Ghép Câu cho người chơi kéo quả chữ vào các ô theo đúng thứ tự. Đúng thứ tự thì tạo được câu, tiêu tốn quả, nhận thưởng = 2 × tổng giá trị quả. Sai thứ tự thì Trúc Lão nhận xét hài hước và gợi ý vị trí sai.

### 6.5 Phản ứng kề ô (định nghĩa trong `combos.json`)
Ô kề = 4 ô trên/dưới/trái/phải. Phản ứng kích hoạt khi cả các cây liên quan đều ở giai đoạn 1 trở lên.
- **水**: các ô kề giảm 20% thời gian chờ ôn.
- **火**: ô kề lớn nhanh hơn 10%; nếu ô kề có **木** thì có 20% khả năng mỗi ngày làm cây 木 tăng wither 30 (hiệu ứng lửa).
- **日 + 月** kề nhau: sinh cây ẩn **明** (phát sáng ban đêm), cho người chơi hạt 明.
- **木** ở 3 ô hình chữ L hoặc thẳng hàng: mở khóa hạt **森** và trang trí "Rừng nhỏ".
- **木 + 木** kề nhau: mở khóa hạt **林**.
- **女 + 子** kề nhau: mở khóa hạt **好**, cộng 50 Linh Thạch một lần.
- **人 + 木** kề nhau: mở khóa hạt **休** (người tựa cây = nghỉ ngơi).
- **口 + 马** kề nhau: mở khóa hạt **吗**.

Trò chơi **không liệt kê** sẵn các công thức. Khi phát hiện, hiện popup "Phát hiện mới!" giải thích cấu tạo chữ, và ghi vào Sổ Phát Hiện. Dữ liệu tách ra JSON để thêm công thức dễ dàng.

### 6.6 Sự cố sai thanh điệu (`tone_mishaps.json`)
Khi người chơi chọn sai đáp án pinyin mà đáp án sai đó là một từ có thật, có nghĩa buồn cười, kích hoạt sự cố (ngoài việc tính sai thông thường):
- Chọn **mǎ (马, ngựa)** thay vì **mā (妈, mẹ)**: một con ngựa chạy ngang vườn (hoạt ảnh), Trúc Lão: "Con gọi mẹ hay gọi ngựa vậy?"
- Chọn **mài (卖, bán)** thay vì **mǎi (买, mua)**: hiện thông báo "Bạn vừa rao bán cái cuốc của mình!", trừ 10 Linh Thạch (không âm).
- Chọn **wěn (吻, hôn)** thay vì **wèn (问, hỏi)**: một dân làng đỏ mặt bỏ chạy.
- Thêm ít nhất 5 sự cố khác cùng phong cách, dùng từ trong data.
Sự cố chỉ mang tính hài hước, không phạt nặng.

### 6.7 Bức thư bí ẩn
- `letters.json` gồm 5 lá thư tiếng Trung, mỗi lá 15–30 chữ, chỉ dùng chữ có trong data. Cốt truyện: thư từ một người không rõ danh tính; lá cuối tiết lộ người viết chính là Trúc Lão thời trẻ, người vô tình thả Mặc Quái ra khi cố giữ chữ cho riêng mình.
- Hiển thị: chữ đã có trong collection hiện rõ; chữ chưa học hiện thành vết mực tròn.
- Thanh tiến độ "Đã giải mã x%". Giải mã 100% nhận thưởng lớn và mở lá thư kế tiếp.
- Có nút xem bản dịch tiếng Việt chỉ khi giải mã 100%.

### 6.8 Pet
Chuyển sang mục 13 (gacha Linh Thú). Kỹ năng pet giữ như bản 1.

### 6.9 Trúc Lão
NPC hướng dẫn, xuất hiện ở góc màn hình với hộp thoại. Có hướng dẫn chơi lần đầu (tutorial) dẫn người chơi qua: nhận 1 hạt miễn phí, gieo, học, trả lời câu hỏi giai đoạn 1. Có kho câu thoại ngẫu nhiên hài hước khi người chơi trả lời đúng/sai.

---
- Trúc Lão giờ là sư phụ của người chơi: tutorial mở rộng thêm đi lại, đánh con quái đầu tiên ở Rừng Mực Loang, câu con cá đầu tiên, nở quả trứng ong đầu tiên.

---

## 7. Thế giới tu tiên, nhân vật và cảnh giới

### 7.1 Bản đồ thế giới
Thế giới gồm nhiều **zone** (mỗi zone một bản đồ Tiled), nối nhau bằng cổng dịch chuyển ở rìa bản đồ:

| Zone | Loại | Cảnh giới khuyến nghị | Nội dung |
|---|---|---|---|
| **Trúc Lâm Thôn** | an toàn (hub) | mọi cấp | Trúc Lão, cửa hàng, lò luyện đan công cộng, lò rèn, Thiên Cơ Các (gacha), bảng nhiệm vụ, Tàng Thư Các (thư viện), cổng vào ải Thủ Vườn, quảng trường chat |
| **Động Phủ** | riêng (instance mỗi người) | mọi cấp | Vườn chữ (mục 6), tổ ong, ao cá nhỏ, bàn đả tọa; bạn bè được mời vào thăm |
| **Rừng Mực Loang** | có quái | Luyện Khí | quái HSK1, nơi làm quen chiến đấu |
| **Hồ Nghiên Mực** | có quái + câu cá | Luyện Khí – Trúc Cơ | hồ câu chính, quái ven hồ |
| **Núi Trúc** | có quái | Trúc Cơ | quái HSK2, dược thảo hiếm |
| **Phố Mì Đêm, Chợ Nổi, Thành Cổ** | có quái | Kim Đan trở lên | để dành cho giai đoạn mở rộng, HSK3+ |

- Mỗi zone công cộng có **kênh (channel)** tối đa 40 người; đầy thì tự mở kênh mới. Người chơi đổi kênh được.
- Chết trong zone: mất 5% Tu Vi của tầng hiện tại (không tụt tầng), hồi sinh ở Trúc Lâm Thôn. Không rơi đồ.
- Ngày/đêm theo giờ server (1 ngày game = 2 giờ thật) ảnh hưởng loại cá, quái, cây 明 phát sáng.

### 7.2 Nhân vật
- Tạo nhân vật: đặt tên hiển thị, chọn màu tóc và kiểu tóc (vài lựa chọn), giới tính ngoại hình. **Quần áo khởi đầu giống hệt nhau**: Áo Vải Phàm Nhân, không vũ khí (đánh tay không) cho tới khi nhận Bút Lông Gỗ ở nhiệm vụ đầu.
- Sprite 16×24 pixel, 4 hướng, hoạt ảnh đứng / đi / tấn công / thi pháp / bị đánh / ngồi đả tọa / câu cá. Trang bị đổi được ngoại hình (lớp áo, mũ, vũ khí vẽ đè lên thân).
- Điều khiển: WASD/mũi tên di chuyển, chuột trái tấn công thường, phím 1–4 kỹ năng, E tương tác, F câu cá (khi đứng cạnh nước), Tab túi đồ, Enter chat, Esc menu. Câu hỏi trả lời bằng phím 1–4 hoặc chuột, gõ pinyin bằng bàn phím.
- Chỉ số: Sinh Lực (HP), Linh Lực (dùng kỹ năng), Công, Thủ, Tốc, Bạo Kích, Kháng Mực (giảm sát thương khi trả lời sai).

### 7.3 Cảnh giới (gắn với cấp HSK)
| Cảnh giới | Tầng | Phạm vi từ vựng | Ô ong hộ vệ | Mở khóa |
|---|---|---|---|---|
| Phàm Nhân | — | tutorial | 0 | động phủ, vườn 3×3 |
| Luyện Khí | 1–9 | HSK 1 | 2 | Rừng Mực Loang, Hồ Nghiên Mực, ải Thủ Vườn chương 1 |
| Trúc Cơ | sơ / trung / hậu kỳ | HSK 2 | 3 | Núi Trúc, bí cảnh cấp 1, chương 2 |
| Kim Đan | sơ / trung / hậu kỳ | HSK 3 | 4 | zone mở rộng, chương 3 |
| Nguyên Anh | sơ / trung / hậu kỳ | HSK 4 | 5 | (mở rộng) |

- **Tu Vi** (kinh nghiệm) kiếm từ: trả lời đúng ở mọi nơi (nguồn chính), đánh quái, thu hoạch, hoàn thành ải và nhiệm vụ, **đả tọa** tại bàn đả tọa trong động phủ (mỗi 2 phút hiện một câu ôn tập từ đã học, đúng thì nhận Tu Vi; không có cách treo máy nhận Tu Vi mà không trả lời).
- **Đột phá** sang cảnh giới mới cần: đầy Tu Vi + 1 viên **Trúc Cơ Đan / Kim Đan Đan...** (luyện được, mục 12) + vượt **Thiên Kiếp**: bài thi 20 câu trộn mọi dạng câu hỏi lấy từ toàn bộ từ vựng cấp HSK hiện tại, giới hạn 30 giây/câu, cần đúng ≥ 80%. Vừa thi vừa có hiệu ứng sét pixel; mỗi câu sai là một tia sét đánh trúng nhân vật (chỉ hiệu ứng). Trượt: mất 10% Tu Vi, chờ 30 phút (theo `TIME_SCALE`) mới thi lại, đan dược không mất. Đột phá giữa các tầng trong cùng cảnh giới không cần thi.
- Server chặn: không ai vào zone/ải vượt quá 1 cảnh giới so với mình.

### 7.4 Nhiệm vụ
- Chuỗi nhiệm vụ chính kể cốt truyện (Trúc Lão, các bức thư bí ẩn ở mục 6.7 trở thành nhiệm vụ chính), nhiệm vụ hằng ngày (đánh 10 quái, câu 3 cá, ôn 15 từ, thụ phấn 5 hoa...), nhiệm vụ ẩn kích hoạt khi phát hiện công thức ghép chữ.
- Hội thoại NPC hiển thị song ngữ ở chỗ phù hợp: NPC nói một câu tiếng Trung ngắn chỉ dùng từ người chơi đã học, bên dưới là tiếng Việt.

---

## 8. Chiến đấu và câu đố "Vấn Đạo"

### 8.1 Cơ chế trận đánh
Chiến đấu thời gian thực, server tính toàn bộ sát thương. Mỗi quái có một **Mặc Thuẫn** (khiên mực). Câu hỏi là cách phá khiên:

1. Người chơi tấn công quái lần đầu (hoặc quái chủ động áp sát) → bước vào **giao chiến** với quái đó.
2. Ngay khi giao chiến, server gửi một **câu Vấn Đạo** riêng cho người chơi. Thẻ câu hỏi hiện ở nửa dưới màn hình, chữ Hán lớn rõ. Trong lúc trả lời, nhân vật được **Hộ Thể** (không nhận sát thương, không di chuyển, không tấn công) tối đa bằng thời gian giới hạn của câu.
3. **Đúng:** phá Mặc Thuẫn, gây một đòn "Ngộ Đạo" (sát thương ×2), hồi một ít Linh Lực; trả lời càng nhanh càng có thêm bạo kích. Sau đó quái không còn khiên, đánh thường cho đến khi chết hoặc khiên hồi lại.
4. **Sai hoặc hết giờ:** quái tung **Mặc Kích** gây sát thương theo % máu tối đa (quái thường 10%, tinh anh 15%, boss 20%; trừ theo Kháng Mực), khiên vẫn còn, và hiện đáp án đúng kèm giải thích ngắn 2 giây. Câu kế tiếp hiện sau 3 giây.
5. Quái tinh anh hồi khiên khi máu xuống 50%; boss hồi khiên ở 75/50/25% (mỗi lần một câu khó hơn). Quái thường chỉ có 1 khiên.
6. Khi đánh theo tổ đội, mỗi thành viên giao chiến với quái nhận câu hỏi riêng; ai trả lời đúng trước thì phá khiên cho cả đội.

Ngoài ra là chiến đấu hành động bình thường: né đòn quái (quái có đòn báo trước bằng vùng đỏ pixel), kỹ năng, ong hộ vệ (mục 10) tự đánh quái đã mất khiên. **Không thể giết quái còn khiên** (đòn đánh chỉ gây 1 sát thương), nên không bỏ qua câu hỏi được.

### 8.2 Ngân hàng câu hỏi
`question_bank.py` sinh câu hỏi theo **dạng** và **độ khó**, từ dữ liệu đã kiểm chứng ở mục 5. Nguồn từ cho câu hỏi chiến đấu: 70% từ trong collection của người chơi (ưu tiên từ sắp đến hạn ôn để chiến đấu cũng là ôn tập), 30% từ thuộc cấp HSK của zone mà người chơi **đã được giới thiệu** (đã xem màn giới thiệu từ). Không bao giờ hỏi một từ người chơi chưa từng thấy.

| Mã | Dạng câu | Ví dụ | Cảnh giới dùng | Giới hạn giờ |
|---|---|---|---|---|
| Q1 | Chữ Hán → chọn nghĩa (4 đáp án) | 水 → nước / lửa / núi / cây | Luyện Khí+ | 10 s |
| Q2 | Nghĩa tiếng Việt → chọn chữ Hán | "mẹ" → 妈 / 马 / 吗 / 骂 | Luyện Khí+ | 10 s |
| Q3 | Chữ Hán → chọn pinyin (nhiễu khác thanh) | 买 → mǎi / mài / māi / mái | Luyện Khí+ | 10 s |
| Q4 | Nghe âm → chọn chữ Hán | (audio) → 你好 | Luyện Khí+ | 12 s |
| Q5 | Chữ Hán → gõ pinyin dạng số | 妈 → `ma1` | Trúc Cơ+ | 15 s |
| Q6 | Chọn lượng từ đúng | 一 __ 书 → 本 / 个 / 只 / 张 | Trúc Cơ+ | 12 s |
| Q7 | Điền chữ vào chỗ trống trong câu ví dụ | 我 __ 中国人 → 是 | Trúc Cơ+ | 15 s |
| Q8 | Tìm bộ thủ / thành phần của chữ | 好 gồm? → 女 + 子 | Trúc Cơ+ | 12 s |
| Q9 | Sắp xếp các chữ thành câu đúng | 苹果 / 我 / 吃 / 喜欢 | Kim Đan+ | 25 s |
| Q10 | Đọc câu ngắn → chọn nghĩa câu | 他明天去北京。 | Kim Đan+ | 25 s |
| Q11 | Chọn thanh điệu đúng (bấm 1 trong 4 nút thanh, có hình đường cong) | 山 → thanh 1 | Luyện Khí+ (quái "Thanh Điệu Yêu") | 8 s |

Quy tắc sinh câu:
- **Đáp án nhiễu** lấy từ data thật, ưu tiên cùng chủ đề, cùng âm khác thanh, hoặc nhìn giống nhau (cùng bộ thủ); không có hai đáp án cùng đúng (kiểm tra trùng nghĩa/trùng chữ).
- **Lượng từ (Q6)** chỉ lấy từ trường `CL:` của CC-CEDICT, không tự nghĩ. Từ nào CC-CEDICT không có lượng từ thì không dùng cho Q6.
- **Bộ thủ (Q8)** lấy từ makemeahanzi (`radical`, `decomposition`).
- **Câu (Q7, Q9, Q10)** chỉ dùng câu trong `sentences.json` hoặc câu ví dụ đã có cờ `reviewed = true`. Câu chưa duyệt thì chỉ dùng ở môi trường dev.
- Mỗi quái trong `monsters.json` khai báo danh sách dạng câu nó dùng (vd "Thanh Điệu Yêu" chỉ hỏi Q3, Q11; "Mặc Thư Sinh" hỏi Q7, Q9), để mỗi loại quái có "tính cách" riêng.
- Không lặp lại cùng một từ trong 5 câu liên tiếp của cùng người chơi.
- Câu hỏi có hiệu ứng thời gian: thời gian giới hạn tính theo đồng hồ server (cộng 1,5 s bù độ trễ mạng).

### 8.3 Ảnh hưởng tới việc học
- Mọi câu trả lời ở chiến đấu/ải/bí cảnh đều cập nhật `collection` (times_correct/wrong, mastery ±2) nhưng **không đổi giai đoạn cây** trong vườn. Giai đoạn cây chỉ đổi khi ôn ở vườn (đúng lịch SRS của bản 1).
- Từ bị trả lời sai ở chiến đấu được đánh dấu "cần ôn", hiện chấm đỏ trên cây tương ứng trong vườn.
- Màn **Sổ Lỗi** (trong Tàng Thư Các) liệt kê các từ hay sai nhất kèm nút luyện riêng.

### 8.4 Kỹ năng = chữ
- Kỹ năng chiến đấu là các **Pháp Chữ**: mỗi kỹ năng gắn với một chữ trong data, mở khóa khi chữ đó có mastery ≥ 50 và người chơi có bí kíp tương ứng (rơi từ quái, mua ở Tàng Thư Các).
- Ví dụ (con số trong balance): 火 Hỏa Chữ Quyết (cầu lửa đơn mục tiêu), 水 Thủy Chữ Quyết (làm chậm vùng), 山 Sơn Chữ Quyết (tường đá chặn đường), 木 Mộc Chữ Quyết (hồi máu nhỏ), 日 Nhật Chữ Quyết (gây mù, quái đánh trượt), 人 Nhân Chữ Quyết (tăng tốc chạy).
- Cấp kỹ năng tăng theo mastery của chữ (50/70/90/100 → cấp 1–4). Quên chữ (mastery giảm) thì kỹ năng yếu đi tương ứng.
- Khi thi pháp, chữ Hán của kỹ năng hiện to bằng pixel phía trên đầu nhân vật trong 1 giây, kèm pinyin.

---

## 9. Ải "Thủ Vườn" (tower defense) và Bách Thảo Phổ

Thủ Vườn là **một chế độ chơi riêng** (vào từ cổng ở Trúc Lâm Thôn), không thay thế thế giới chính. Đơn người chơi ở v1 (có thể mở co-op 2 người ở giai đoạn mở rộng).

### 9.1 Luật chơi
- Mỗi ải là một bản đồ lưới (vd 12×7 ô) có đường đi; Mặc Quái đi theo đường từ cổng mực tới **Linh Mạch** (lõi vườn). Linh Mạch có 20 điểm, mỗi quái lọt vào trừ điểm theo loại.
- Trước ải, người chơi chọn **bộ cây mang theo** (tối đa 8 loại) từ các cây đã mở trong Bách Thảo Phổ.
- Đặt cây tốn **Linh Khí** (tài nguyên trong ải): có sẵn một ít, tăng dần theo thời gian, nhận thêm khi diệt quái, và nhận nhiều nhất bằng **Linh Khí Vấn Đạo**: giữa các đợt quái hiện 3 câu hỏi nhanh, mỗi câu đúng +Linh Khí. Trong đợt quái, người chơi có thể bấm nút "Tụ Khí" để nhận một câu hỏi bất kỳ lúc nào (hồi chiêu 10 giây), đúng thì +Linh Khí, sai thì mất một ít.
- **Nâng cấp cây** trong ải: trả lời một câu về đúng chữ của cây đó (vd nâng cây 火 phải trả lời câu về 火); đúng thì lên cấp, sai thì mất Linh Khí đã bỏ ra.
- Sức mạnh gốc của cây = theo vai trò (9.2) × hệ số theo **mastery** của chữ trong collection (mastery 0 → 60%, 100 → 130%) × hệ số **wither** (cây bị sương mực trong vườn thật thì yếu đi, tối đa −30%). Đây là sợi dây nối giữa vườn học tập và ải.
- Kết quả: 1–3 sao theo điểm Linh Mạch còn lại. Thưởng lần đầu theo sao (Linh Thạch, nguyên liệu, hạt giống, bí kíp); chơi lại nhận thưởng nhỏ hơn, tối đa 5 lần nhận thưởng mỗi ngày.
- 30 ải chia 3 chương (theo cảnh giới) + **Vô Tận Trận** (đợt quái vô hạn, bảng xếp hạng tuần).

### 9.2 Vai trò cây (`plants/plant_roles.json`)
Mỗi chữ trong data được gán một vai trò. Chữ đặc biệt gán tay, chữ còn lại gán theo chủ đề:

| Vai trò | Ví dụ chữ | Chức năng |
|---|---|---|
| Hỏa (sát thương vùng) | 火, 日, 热 | bắn cầu lửa nổ lan |
| Thủy (làm chậm) | 水, 雨, 河 | phun nước làm chậm 40% |
| Mộc (chặn đường) | 木, 林, 森 | thân cây chặn quái, máu cao |
| Sơn (choáng) | 山, 石, 大 | rung đất làm choáng định kỳ |
| Kim (đơn mục tiêu mạnh) | 金, 刀, 力 | bắn kim châm sát thương lớn |
| Quang (lộ quái tàng hình) | 明, 月, 光 | quái "Mực Ẩn" chỉ bị đánh khi đứng trong vùng sáng |
| Sinh khí (kinh tế) | chủ đề đồ ăn: 米, 茶, 苹果 | định kỳ tạo Linh Khí |
| Hỗ trợ | chủ đề gia đình, chào hỏi: 妈妈, 你好, 朋友 | tăng tốc bắn / hồi máu cho cây kề |
| Thành ngữ (legendary) | 一石二鸟 ... | kỹ năng đặc biệt, dùng 1 lần/ải (vd 一石二鸟: một phát bắn trúng 2 mục tiêu mạnh nhất) |

- Phản ứng kề ô của vườn (mục 6.5) cũng có tác dụng trong ải: 女 cạnh 子 → cả hai được buff "好"; 日 cạnh 月 → vùng sáng "明" rộng gấp đôi; ba cây 木 → hiệu ứng "森" tăng máu cho cả cụm.
- Quái trong ải có kháng/yếu nguyên tố (vd "Mực Đặc" kháng Thủy, yếu Hỏa), thể hiện trên thẻ thông tin quái.

### 9.3 Tàng Thư Các và Bách Thảo Phổ
**Tàng Thư Các** là thư viện chung trong game (một tòa nhà ở Trúc Lâm Thôn và một nút trên menu), chứa các "phổ" (bộ sưu tập):
- **Bách Thảo Phổ** (cây): mỗi trang một loại cây — sprite pixel theo 5 giai đoạn, chữ Hán to, pinyin, nút nghe, nghĩa tiếng Việt, câu ví dụ, vai trò và chỉ số tower defense, mastery hiện tại, cấu tạo chữ (nếu có), lời bình của Trúc Lão. Cây chưa có hiện bóng đen với dấu "?". Cây ẩn (明, 林, 森, 好, 休, 吗...) chỉ hiện khung trống cho đến khi phát hiện.
- **Ngư Phổ** (cá, mục 11), **Ong Phổ** (mục 10), **Yêu Quái Phổ** (quái đã gặp: tên, dạng câu hay hỏi, điểm yếu, vật phẩm rơi), **Linh Thú Phổ** (pet), **Bảo Vật Phổ** (trang bị, đan dược đã từng có), **Sổ Phát Hiện** (công thức ghép chữ), **Sổ Lỗi**.
- Mỗi phổ có % hoàn thành và mốc thưởng (25/50/75/100%): danh hiệu, khung avatar, Linh Thạch, ô tổ ong thêm.
- Có ô tìm kiếm theo chữ Hán, pinyin (có hoặc không dấu) hoặc nghĩa tiếng Việt.

---

## 10. Linh Phong (ong linh) và tổ ong

### 10.1 Có ong và tổ ong
- Ong nở từ **Trứng Ong** nhận qua gacha ong (mục 13), nhiệm vụ, bí cảnh. Độ hiếm: Phàm, Linh, Huyền, Địa, Thiên.
- **Tổ ong (Linh Phong Sào)** đặt trong động phủ, giao diện là lưới ô lục giác pixel. Bắt đầu 5 ô, mở thêm bằng Linh Thạch và mốc Ong Phổ, tối đa 30 ô. Mỗi ong chiếm một ô; kéo thả để sắp xếp. Ong cùng hệ nằm kề nhau trong tổ được cộng nhỏ chỉ số ("đồng hệ cộng hưởng").
- Nâng cấp tổ ong (vật liệu: sáp ong, gỗ, Linh Thạch) tăng tốc sản xuất mật và mở trang trí.
- Thiết kế **ít nhất 15 loài ong tự sáng tạo**, mỗi loài gắn một chữ/từ tiếng Trung (tên hiện song ngữ, vd Ong Hỏa Diệm 火蜂). Gợi ý: Ong Mực (Phàm), Ong Trúc, Ong Gạo, Ong Hỏa Diệm, Ong Băng Tâm, Ong Sấm, Ong Ngọc, Ong Thư Pháp (Thiên, bay để lại vệt mực vẽ chữ)... Tên tiếng Trung đi qua quy trình kiểm chứng của mục 5.

### 10.2 Ba vai trò của ong (mỗi con chỉ một vai trò tại một thời điểm)
1. **Ở tổ:** sản xuất **Linh Mật** theo thời gian (tính lười khi người chơi tải động phủ). Linh Mật dùng luyện đan, cho ong ăn, bán.
2. **Thụ phấn:** gán ong vào vườn. Ong bay giữa các cây đang ở giai đoạn **Ra hoa (3)** trở lên, làm đầy thanh **Phấn Hoa** của từng cây. Khi đầy 100%:
   - cây được đánh dấu "Đã thụ phấn": lần thu hoạch cho thêm quả (3 → 5) và có tỉ lệ ra **Linh Quả** (nguyên liệu luyện đan hiếm);
   - thời gian chờ ôn của **lần ôn kế tiếp** giảm tối đa 25% (giới hạn này cố ý nhỏ để không phá lịch lặp lại ngắt quãng; ghi lý do vào DECISIONS.md);
   - **thụ phấn không bao giờ thay thế câu hỏi ôn tập**, cây vẫn chỉ lên giai đoạn khi trả lời đúng.
   Tốc độ thụ phấn phụ thuộc loài và cấp ong; ong hệ Thủy thụ phấn nhanh hơn cạnh cây 水...
3. **Hộ vệ:** 2–5 con (theo cảnh giới, mục 7.3) **bay theo nhân vật** ngoài thế giới và bí cảnh. Ong tự động tấn công quái **đã mất Mặc Thuẫn** (không phá được khiên thay người chơi), có kỹ năng bị động theo loài (đốt lửa, làm chậm, gây choáng, hồi máu nhỏ cho chủ, nhặt đồ rơi). Ong hộ vệ có thanh máu; bị hạ thì bay về tổ hồi phục 60 giây.
- Ong lên cấp bằng cách cho ăn (Linh Mật, quả chữ, cá nhỏ) và khi tham gia chiến đấu/thụ phấn. Mức **thân thiết** tăng khi cho ăn đúng món ưa thích (mỗi loài có món thích, ghi trong Ong Phổ khi phát hiện).
- Hiển thị: ong pixel 8×8 có hoạt ảnh vỗ cánh 2 khung, bay theo đường cong mượt quanh chủ; ong thụ phấn bay giữa các hoa, để lại hạt phấn vàng.

---

## 11. Câu cá

### 11.1 Cơ chế
- Đứng cạnh nước (hồ, sông, ao trong động phủ) bấm F để quăng câu. Chờ cá cắn (thời gian ngẫu nhiên, giảm theo chỉ số cần và mồi).
- Khi cá cắn, hiện **minigame kéo cá**: một thanh căng dây; giữ chuột để kéo, nhả để thả dây; giữ con trỏ trong vùng xanh di chuyển theo cá cho tới khi đầy thanh bắt. Dây căng quá lâu thì đứt.
- **Cá từ Linh trở lên khi cắn câu sẽ hiện một câu hỏi** (dạng tùy độ hiếm, cá càng hiếm câu càng khó). Đúng: vào minigame với vùng xanh rộng hơn. Sai: cá dễ thoát hơn (vùng xanh hẹp) nhưng **không mất máu** — câu cá là hoạt động thư giãn. Cá Thiên (huyền thoại) yêu cầu trả lời đúng **2 câu liên tiếp**.
- Toàn bộ kết quả (cá gì, kích thước) server quyết định khi cá cắn; client chỉ chạy minigame và gửi các mốc thao tác, server kiểm tra hợp lý theo thời gian.

### 11.2 Cần câu và mồi (`items/rods.json`, `items/baits.json`)
- Cần câu (ví dụ): Cần Trúc Thô (khởi đầu, miễn phí) → Cần Tre Già → Cần Ngọc Bích → Cần Long Cốt → Cần Thiên Tơ (Thiên, chế tạo từ nguyên liệu bí cảnh). Chỉ số: Lực kéo, Độ bền dây, May mắn (tăng tỉ lệ cá hiếm), Tốc cắn, Vùng xanh.
- Mồi tiêu hao: Giun Đất, Bánh Mật (từ Linh Mật), Linh Quả Vụn, Mồi Mực (chỉ câu được cá Mực ở đêm)...
- Cần câu nâng cấp được ở lò rèn.

### 11.3 Cá
- **Ít nhất 30 loài cá** chia 5 độ hiếm, mỗi loài có tên tiếng Việt + tên tiếng Trung thật nếu là cá có thật (鲤鱼 cá chép, 金鱼 cá vàng, 草鱼 cá trắm...; lấy từ CC-CEDICT) hoặc tên sáng tác cho cá huyền thoại (đánh dấu `fictional: true`, không đem ra làm câu hỏi từ vựng).
- Điều kiện xuất hiện: zone, ngày/đêm, thời tiết (mưa ngẫu nhiên theo zone), mồi. Ví dụ: Cá Chép Hóa Long chỉ ở Hồ Nghiên Mực, đêm mưa, mồi Linh Quả.
- Mỗi con có kích thước ngẫu nhiên; Ngư Phổ lưu kỷ lục to nhất; bảng xếp hạng cá to nhất mỗi loài trên toàn server.
- Công dụng: bán, làm nguyên liệu đan dược, thức ăn cho ong/pet, nộp nhiệm vụ.

---

## 12. Trang bị, đan dược và kinh tế

### 12.1 Tiền tệ
- **Linh Thạch** (thay cho Mực Vàng của bản 1): tiền chính. Nguồn: trả lời đúng, bán quả/cá/mật, nhiệm vụ, ải, bí cảnh.
- **Tiên Ngọc**: tiền hiếm chỉ kiếm từ mốc thư viện, Thiên Kiếp, bí cảnh, nhiệm vụ chính; dùng cho gacha cao cấp và mở ô tổ ong. Không có cách mua bằng tiền thật.
- Có "vòi xả" tiền (sink) để không lạm phát: phí rèn, phí luyện đan, sửa trang bị, mở ô đất, mở ô tổ.

### 12.2 Trang bị
- Ô: Vũ khí (bút lông, kiếm, quạt, trượng — mỗi loại một kiểu đánh thường), Áo, Mũ, Giày, Ngọc Bội, Nhẫn.
- Độ hiếm: Phàm, Linh, Huyền, Địa, Thiên (màu xám, xanh lá, xanh dương, tím, vàng kim).
- Nguồn: quái rơi, cửa hàng (chỉ đồ Phàm/Linh), rèn ở lò rèn từ nguyên liệu, bí cảnh (đồ Địa/Thiên và bộ trang bị).
- **Cường hóa** +1 → +10 bằng nguyên liệu và Linh Thạch, tỉ lệ thành công giảm dần, thất bại không mất đồ chỉ mất nguyên liệu.
- **Khắc Văn**: khắc một chữ đã học (mastery ≥ 70) lên trang bị để nhận thuộc tính theo chữ (火: +công hỏa, 山: +thủ, 水: +kháng làm chậm, 心: +Linh Lực...). Muốn khắc phải vượt 3 câu hỏi liên tiếp về chữ đó. Mỗi trang bị tối đa 1–3 ô khắc theo độ hiếm. Chữ khắc hiện nhỏ trên icon trang bị.
- Bộ trang bị (set) từ bí cảnh có hiệu ứng khi mặc đủ 2/4 món.

### 12.3 Luyện đan (`recipes.json`)
- Lò luyện đan ở động phủ (nâng cấp được) và lò công cộng ở Trúc Lâm Thôn.
- Đan phương (công thức) là vật phẩm: nhặt được, mua ở Tàng Thư Các, thưởng nhiệm vụ. Mỗi đan phương ghi tên đan bằng tiếng Việt kèm chữ Hán, và nguyên liệu.
- Nguyên liệu: quả chữ, Linh Quả, Linh Mật, cá, vật phẩm từ quái, dược thảo hái ở Núi Trúc.
- Minigame **canh lửa**: một kim chạy qua lại trên thanh nhiệt, bấm đúng lúc kim vào vùng "văn hỏa" 3 lần. Mỗi lần bấm hiện một chữ của tên đan để người chơi gõ pinyin (chỉ dùng các chữ đã học; chữ chưa học thì bỏ qua bước gõ). Kết quả: phế đan / hạ phẩm / trung phẩm / thượng phẩm.
- Các loại đan: Hồi Huyết Đan, Hồi Khí Đan, Tụ Linh Đan (tăng Tu Vi), Kháng Mực Đan (tăng Kháng Mực 10 phút), Ngộ Tính Đan (thêm 3 giây cho mỗi câu hỏi trong 10 phút), Trúc Cơ Đan / Kim Đan Đan (đột phá), Phong Vương Đan (cho ong).
- Đan dược dùng trong trận có hồi chiêu chung 15 giây; không có đan nào tự trả lời câu hỏi hay bỏ qua câu hỏi.

### 12.4 Cửa hàng và giao dịch
- Cửa hàng NPC ở Trúc Lâm Thôn bán đồ cơ bản, mồi câu, hạt giống thường, mua lại vật phẩm.
- **v1 không có giao dịch trực tiếp giữa người chơi** (tránh lừa đảo, buôn bán tài khoản). Chỉ có tặng quà nhỏ giữa bạn bè (vật phẩm không ràng buộc, giới hạn 5 lần/ngày). Chợ người chơi để giai đoạn mở rộng.

---

## 13. Gacha và pet (Thiên Cơ Các)

Tất cả gacha nằm ở Thiên Cơ Các, dùng chung thuật toán có pity ở mục 6.1 nhưng mỗi loại có bảng tỉ lệ và bộ đếm pity riêng (cấu hình trong `balance/gacha.json`):

| Gacha | Giá | Ra gì |
|---|---|---|
| Hạt Chữ | 100 Linh Thạch / 900 cho 10 | hạt giống từ vựng (giữ nguyên quy tắc bản 1, kể cả giới hạn 15 hạt mới/ngày) |
| Trứng Ong | 300 Linh Thạch hoặc 5 Tiên Ngọc | trứng ong 5 độ hiếm |
| Linh Thú | 500 Linh Thạch hoặc 10 Tiên Ngọc | pet 12 con giáp (bản 1, mục 6.8) |

- Mọi gacha hiển thị tỉ lệ rõ ràng trong game, toàn bộ random trên server.
- **Pet**: 12 con giáp vẽ pixel, đi theo nhân vật (cùng lúc với ong hộ vệ), mỗi con một kỹ năng như bản 1 (Chuột +5% tỉ lệ Rare, Trâu +20% tiền ôn đúng, Hổ wither chậm 50%, Rồng nhân đôi tiền câu thứ 5 trong chuỗi 5 câu đúng) cộng thêm một chỉ số chiến đấu nhỏ. Chỉ đeo 1 pet. Pet **không bao giờ** bỏ qua bước trả lời câu hỏi.
- Hằng ngày đăng nhập nhận 1 lượt gacha hạt miễn phí.

---

## 14. Bí cảnh (secret realm) hợp tác

### 14.1 Mở bí cảnh
- **Bí cảnh định kỳ:** theo lịch server (vd 3 lần/ngày, giờ cố định theo UTC+7), thông báo toàn server trước 10 phút, cửa mở 15 phút.
- **Khe nứt ngẫu nhiên:** thỉnh thoảng một khe nứt mực xuất hiện ở zone công cộng, ai ở gần thấy và rủ nhau vào; tồn tại 5 phút.
- Vào theo tổ đội 2–5 người (tạo tổ, hoặc dùng hàng chờ ghép đội tự động theo cảnh giới). Yêu cầu cảnh giới tối thiểu. Mỗi người vào được mỗi bí cảnh tối đa 2 lần/ngày.
- Mỗi lượt vào tạo một **instance** riêng cho tổ (zone tạm trên server, xóa khi kết thúc).

### 14.2 Bên trong
Bí cảnh là chuỗi 3–5 phòng + phòng boss, giới hạn 20 phút. Mỗi phòng có quái và **câu đố hợp tác** buộc cả đội phối hợp (chat hoặc ping biểu tượng):

| Câu đố | Cách chơi |
|---|---|
| **Cửa Ghép Chữ** | Cánh cửa khắc nghĩa một chữ ghép (vd "tốt"). Mỗi người cầm một mảnh thành phần (女, 子, 木, 日...), phải cùng đứng lên các bệ đá đúng vị trí trong 10 giây. Mảnh của mỗi người chỉ người đó thấy. |
| **Câu Văn Đứt Đoạn** | Một câu tiếng Trung bị chia nhỏ, mỗi người chỉ thấy vài chữ của mình kèm nghĩa câu tiếng Việt. Cả đội lần lượt bước lên ô số thứ tự để ghép câu đúng thứ tự. |
| **Trụ Thanh Điệu** | 4 trụ đá ứng với 4 thanh. Tượng đá đọc một âm tiết (audio hoặc pinyin không dấu kèm chữ Hán), người gần trụ đúng nhất phải đánh trụ đó trong 5 giây. Chuỗi 8 lần đúng mở cửa. |
| **Gương Nghĩa** | Mỗi người thấy một chữ Hán, gương ở giữa hiện một nghĩa; ai có chữ khớp phải bước vào gương. Sai người bước vào thì cả đội mất máu. |
| **Mê Cung Mực** | Mê cung tối, chỉ người đã học chữ 明/光 (có kỹ năng Quang) mới soi đường được; người khác phải đi theo. |

- Sai câu đố: người sai nhận sát thương (theo mục 8.1), đôi khi cả đội nhận sát thương nhỏ. Hết máu thì thành hồn ma đi theo đội, được hồi sinh khi đội qua phòng kế tiếp.
- Câu đố sinh từ dữ liệu, chỉ dùng chữ mà **ít nhất một thành viên đã học** và đúng cấp bí cảnh; ai nhận vai trả lời được chọn sao cho họ đã học chữ đó.
- **Boss bí cảnh**: nhiều pha; mỗi pha boss dựng Mặc Thuẫn lớn cần **N câu đúng của N người khác nhau** (N = số thành viên còn sống) để phá. Boss có đòn diện rộng báo trước để né.

### 14.3 Bảo vật
- Kết thúc: rương bảo vật. **Mỗi người nhận loot riêng** (roll riêng trên server, không giành nhau), cộng thêm "Mảnh Bảo Vật" chung để ghép trang bị Thiên/đồ bộ. Thưởng theo thời gian hoàn thành và số câu đố không sai.
- Bí cảnh là nguồn chính của: nguyên liệu Cần Thiên Tơ, trứng ong Địa/Thiên, đan phương hiếm, đồ bộ, Tiên Ngọc.
- Ngắt kết nối giữa chừng: có 60 giây để vào lại, quá hạn thì rời đội nhưng vẫn giữ loot các phòng đã qua.

---

## 15. Multiplayer, mạng và đồng bộ

### 15.1 Kiến trúc
- **Server có thẩm quyền (authoritative):** client chỉ gửi **ý định** (hướng di chuyển, tấn công mục tiêu, dùng kỹ năng, trả lời câu hỏi). Server tính vị trí, va chạm, sát thương, rơi đồ, thời gian.
- Một tiến trình Python asyncio, mỗi zone/channel/instance là một object với vòng **tick 20 Hz**; zone không có người chơi thì ngủ (không mô phỏng quái).
- **Vùng quan tâm (AOI):** chỉ gửi cho client các entity trong bán kính màn hình + biên (chia lưới ô 16 tile).
- Server gửi **snapshot** 10 lần/giây (chỉ phần thay đổi), client **nội suy** vị trí người chơi khác (trễ 100 ms) và **dự đoán** chuyển động của chính mình rồi điều chỉnh mượt khi lệch.
- Giao thức JSON có `type` và `v` (version), định nghĩa trong `protocol.py`, tài liệu ở `docs/PROTOCOL.md`. Có thể đổi sang msgpack sau nếu cần.
- WebSocket xác thực bằng JWT ngay message đầu; một tài khoản chỉ một kết nối (kết nối mới đá kết nối cũ).
- Heartbeat 15 giây; mất kết nối thì nhân vật đứng yên 30 giây rồi rời zone; client tự kết nối lại với backoff.

### 15.2 Lưu dữ liệu
- Trạng thái quan trọng (tiền, vật phẩm, Tu Vi, kết quả câu hỏi, loot) ghi DB **ngay khi xảy ra**, trong transaction.
- Vị trí nhân vật, máu, Linh Lực ghi định kỳ 60 giây và khi rời zone/ngắt kết nối.
- Gom ghi (batch) khi có thể, để DB miễn phí không bị quá tải (xem giới hạn ở mục 19).
- Script sao lưu DB hằng ngày (`tools/backup_db.sh`, giữ 7 bản).

### 15.3 Xã hội
- Chat: kênh Thế Giới, Zone, Tổ Đội, Bạn Bè (riêng tư). Bộ lọc từ tục tiếng Việt cơ bản (danh sách có thể chỉnh), giới hạn 1 tin/2 giây, tối đa 200 ký tự, nút chặn và báo cáo người chơi. Chat bong bóng pixel trên đầu nhân vật.
- Tổ đội tối đa 5 người, thấy máu nhau, chia Tu Vi khi đánh quái gần nhau.
- Bạn bè: kết bạn, xem trạng thái online, thăm động phủ (chỉ xem; có thể "tưới giúp" như bản 1: trả lời một câu về chữ trong vườn bạn, cả hai nhận 10 Linh Thạch, tối đa 5 lần/ngày).
- Bảng xếp hạng: cảnh giới, Vô Tận Trận, cá to nhất, % thư viện.

### 15.4 Tài khoản
- Đăng ký bằng username + mật khẩu (không cần email). Khi đăng ký hiển thị **một lần duy nhất** một **mã khôi phục** 12 ký tự để tự đặt lại mật khẩu khi quên; server chỉ lưu bản băm.
- Đổi mật khẩu, đăng xuất mọi thiết bị.
- Một IP tối đa 5 tài khoản mới/ngày để hạn chế clone.

### 15.5 Xử lý mạng ở client
- REST đi qua `client/net/rest.py`: timeout 10 giây, thử lại 2 lần với lỗi mạng, không chặn vòng lặp game (thread), hiện biểu tượng đang tải.
- Mất kết nối: banner "Mất kết nối máy chủ, đang thử lại...", khóa mọi thao tác thay đổi dữ liệu. Không lưu tiến trình cục bộ thay server.
- Lưu token vào `session.json` cạnh exe để tự đăng nhập.
- Server đang "ngủ" (gói miễn phí, mục 19): màn đăng nhập hiện "Máy chủ đang khởi động, chờ khoảng 1 phút..." và tự thử lại, thay vì báo lỗi.
- Client kiểm tra version giao thức với `/server/info`; lệch version thì báo cần cập nhật game.

---

## 16. API REST (tất cả trừ auth đều cần JWT)

Giữ toàn bộ API của bản 1 (đổi `coins` → `spirit_stones`), thêm:

```
POST /auth/reset_password    {username, recovery_code, new_password}
GET  /server/info            -> version giao thức, giờ server, thông báo bảo trì
POST /character/create       {display_name, appearance}
GET  /character              -> chỉ số, cảnh giới, trang bị, kỹ năng, hotbar

GET  /inventory              POST /inventory/use {item_id}
POST /equipment/equip        {instance_id, slot}
POST /forge/enhance          {instance_id}
POST /forge/inscribe/start   {instance_id, word_id} -> chuỗi câu hỏi
POST /alchemy/start          {recipe_id} -> phiên luyện đan
POST /alchemy/finish         {session_id, timings, pinyin_answers}

GET  /hive                   POST /hive/arrange {layout}
POST /bees/assign            {bee_id, role}
POST /bees/feed              {bee_id, item_id}

GET  /td/levels              POST /td/start {level_id, loadout} -> seed ải + câu hỏi đầu
POST /td/event               {run_id, events[]}   (đặt cây, nâng cấp, trả lời câu, kết thúc đợt)
POST /td/finish              {run_id}

POST /cultivation/breakthrough/start   -> phiên Thiên Kiếp
GET  /codex/{type}           -> dữ liệu Tàng Thư Các
POST /gacha/roll             {banner: seeds|bees|pets, count}
GET  /quests                 POST /quests/claim {quest_id}
GET  /leaderboard/{board}
```

**Tower defense chạy ở client nhưng server kiểm tra:** server sinh seed ngẫu nhiên và đợt quái; client gửi log sự kiện; server mô phỏng lại (deterministic, cùng seed) để xác nhận kết quả trước khi trao thưởng. Câu hỏi trong ải vẫn do server sinh và chấm.

Thế giới thời gian thực (di chuyển, chiến đấu, Vấn Đạo ngoài thế giới, câu cá, bí cảnh, chat) đi qua WebSocket, tài liệu trong `docs/PROTOCOL.md`.

---

## 17. Chống gian lận và tính toàn vẹn dữ liệu

Giữ toàn bộ quy tắc của bản 1:
- Server là nguồn sự thật duy nhất cho tiền, vật phẩm, giai đoạn cây, Tu Vi, máu, vị trí, thời gian.
- Client không bao giờ nhận đáp án đúng trước khi trả lời. Mỗi phiên câu hỏi chỉ trả lời được một lần và có hạn (câu chiến đấu theo giới hạn giờ + 1,5 s; câu vườn 10 phút).
- Mọi thay đổi tiền/vật phẩm dùng transaction, không âm, có `audit_log`.
- Giới hạn tần suất cho REST (vd 60 request ghi/phút/user) và WebSocket (vd 30 message/giây, vượt thì ngắt).
- Mật khẩu tối thiểu 6 ký tự, username 3–20 ký tự chữ/số/gạch dưới.

Thêm:
- **Di chuyển:** server kiểm tra tốc độ tối đa và va chạm; vị trí sai thì kéo client về vị trí đúng.
- **Chiến đấu:** server kiểm tra tầm đánh, hồi chiêu, Linh Lực; client chỉ hiển thị.
- **Câu hỏi bằng bot:** theo dõi tỉ lệ đúng và thời gian trả lời bất thường (vd 100% đúng dưới 0,5 giây trong 200 câu) → đánh dấu tài khoản để admin xem, không tự cấm.
- **Câu cá, luyện đan, tower defense:** server quyết định kết quả ngẫu nhiên, kiểm tra thời gian thao tác hợp lý, mô phỏng lại log ải.
- Lệnh admin (chỉ tài khoản có cờ `is_admin`, qua chat `/admin ...`): cấm chat, cấm tài khoản có thời hạn, thông báo toàn server, đặt `TIME_SCALE` trên server dev.

---

## 18. Đồ họa pixel và giao diện

- **Độ phân giải gốc 480×270** (16:9), vẽ lên surface nhỏ rồi phóng to **theo bội số nguyên** (×2, ×3, ×4) để pixel sắc nét; viền đen nếu cửa sổ không chia hết. Thẻ câu hỏi và chữ Hán lớn vẽ ở độ phân giải màn hình thật (lớp UI riêng) để chữ rõ.
- Tile 16×16, nhân vật 16×24, ong 8×8, quái 16×16 đến 32×32 (boss 48×48).
- **Bảng màu cố định** ~32 màu theo phong cách thủy mặc + pastel của bản 1: giấy dó `#F4EBD9`, mực `#2B2B2B`, xanh trúc `#6A994E`, đỏ son `#BC4749`, vàng kim `#E9C46A`, cộng các sắc độ đất, nước, đá. Định nghĩa trong `client/art/palette.py`.
- **Sprite sinh bằng code:** mỗi sprite định nghĩa trong `client/art/sprites/*.py` dạng lưới ký tự (mỗi ký tự là một màu trong bảng màu), `tools/gen_sprites.py` xuất ra spritesheet PNG. Được phép thay bằng gói asset **CC0** (ví dụ các gói pixel của Kenney.nl) nếu tiện hơn; ghi rõ nguồn, giấy phép trong `CREDITS.md` và `client/assets/LICENSES.md`.
- Cây trong vườn và trong ải vẽ theo 5 giai đoạn như bản 1; **chữ Hán của từ hiện trên thân hoặc quả** (font pixel, kèm tooltip chữ lớn khi rê chuột). Màu cây pha xám theo wither. Sương mực là các đốm đen mờ chuyển động chậm.
- Hiệu ứng: hạt sáng bay lên khi trả lời đúng, rung màn hình nhẹ + chớp đỏ khi trúng Mặc Kích, chữ kỹ năng hiện to trên đầu khi thi pháp, sét khi Thiên Kiếp, mực tan thành hạt sáng khi phá khiên.
- Trúc Lão: gấu trúc pixel cầm bút lông, có chân dung lớn hơn trong hộp thoại.
- **HUD thế giới:** góc trên trái chân dung + máu + Linh Lực + cảnh giới; góc trên phải bản đồ mini; dưới giữa hotbar kỹ năng 1–4 và đan dược; dưới trái khung chat; biểu tượng ong hộ vệ và pet.
- **Màn hình cần có:** Menu → Đăng nhập/Đăng ký/Khôi phục → Tạo nhân vật → Thế giới (màn chính) → Động phủ (vườn, tổ ong, lò đan, ao), Túi đồ & trang bị, Kỹ năng, Thiên Cơ Các (gacha), Tàng Thư Các (các phổ), Thủ Vườn (chọn ải, chọn bộ cây, màn chơi), Câu cá (minigame), Luyện đan (minigame), Lò rèn, Tổ đội & bạn bè, Bảng xếp hạng, Cài đặt (âm lượng, tỉ lệ phóng, phím), Ghi công.
- Chuột + bàn phím; Enter xác nhận, Esc quay lại; mọi nút có tooltip tiếng Việt.

---

## 19. Triển khai miễn phí (0 đồng)

> Thông tin các gói miễn phí kiểm tra vào tháng 10/2026 và **có thể thay đổi**. Trước khi triển khai, đọc lại trang giá chính thức và cập nhật `docs/DEPLOY.md`.

Viết hướng dẫn chi tiết cho cả 3 phương án trong `docs/DEPLOY.md`, code phải chạy được trên cả 3 mà không sửa logic (chỉ đổi biến môi trường):

**Phương án A — khuyến nghị cho game chạy 24/7: Oracle Cloud Always Free (VM ARM)**
- Gói Always Free có máy ảo ARM Ampere A1 chạy liên tục; theo các nguồn cập nhật giữa năm 2026, hạn mức ARM miễn phí cho tài khoản mới là khoảng **2 OCPU / 12 GB RAM** (trước đây 4 OCPU / 24 GB). Đăng ký **cần thẻ ngân hàng để xác minh** (không trừ tiền nếu ở trong hạn mức), một số vùng hay hết chỗ cho máy ARM.
- Chạy `docker compose` gồm: server FastAPI, PostgreSQL (cùng máy, không giới hạn giờ chạy), Caddy làm reverse proxy HTTPS tự động.
- Tên miền miễn phí: subdomain DuckDNS trỏ về IP của VM, Caddy tự lấy chứng chỉ HTTPS; hoặc dùng Cloudflare Tunnel nếu không muốn mở cổng.
- Docker image phải build được cho `linux/arm64`.
- Đủ cho khoảng vài chục đến ~100 người online cùng lúc nếu code hiệu quả; ghi kết quả thử tải bằng `tools/load_bots.py` vào `docs/DEPLOY.md`.

**Phương án B — không cần thẻ: Render (free web service) + Neon (Postgres miễn phí)**
- Render free web service hỗ trợ WebSocket nhưng **tự ngủ sau 15 phút không có request/tin nhắn WebSocket**, mất khoảng 1 phút để thức dậy, ổ đĩa không lưu lại khi khởi động lại, và giới hạn 750 giờ/tháng cho cả workspace. Postgres miễn phí của Render **hết hạn sau 30 ngày**, nên không dùng.
- Database dùng **Neon Free**: không cần thẻ, không hết hạn, giới hạn dung lượng nhỏ (khoảng 0,5–1 GB/project) và **100 giờ tính toán (CU-hour)/tháng/project**, tự tạm dừng khi rảnh. Vì vậy server phải gom ghi (mục 15.2), dùng connection pool nhỏ, và không truy vấn DB trong mỗi tick.
- Không lưu file nào trên đĩa server (mọi thứ trong DB). Client xử lý trạng thái "máy chủ đang khởi động" (mục 15.5).
- Phù hợp để thử nghiệm với bạn bè, không phù hợp chạy 24/7 cho đông người.

**Phương án C — chạy trên máy của chính mình + Cloudflare Tunnel**
- `docker compose up` trên máy cá nhân, `cloudflared tunnel --url http://localhost:8000` cho đường dẫn công khai miễn phí (đường dẫn quick tunnel đổi mỗi lần chạy).
- Dùng `server_list_url` (mục 2) để client tự nhận địa chỉ mới, không phải gửi lại exe.
- Server chỉ sống khi máy bật.

**Phát hành client miễn phí:** GitHub Releases cho `VuonChu.exe` (kèm font, audio, `config.json`); `server_list.json` để trong repo GitHub và client đọc qua link raw. README hướng dẫn: chạy server cục bộ, chạy client từ source, đóng gói exe, chọn và làm theo một trong 3 phương án.

---

## 20. Các giai đoạn và tiêu chí hoàn thành

Mỗi giai đoạn: chạy được, có test, cập nhật README và DECISIONS.md. Không sang giai đoạn sau khi tiêu chí chưa đạt.

**Giai đoạn 1 — Dữ liệu và server học tập lõi** *(như giai đoạn 1 bản 1, mở rộng)*
`tools/build_wordlist.py` cho HSK 3.0 cấp 1 **và cấp 2** (cấp 2 dùng cho Trúc Cơ; cùng quy trình mục 5), trích lượng từ `CL:` từ CC-CEDICT, bộ thủ từ makemeahanzi. Models, migration, auth (kèm mã khôi phục), gacha có pity (cấu hình nhiều banner), SRS, `question_bank` đủ 11 dạng câu.
✅ `pytest` qua hết: tỉ lệ gacha (100.000 lần, sai số < 1%), pity, chuyển giai đoạn SRS, không trả lời trước hạn, không tiêu tiền âm, mỗi dạng câu hỏi sinh đúng (không trùng đáp án đúng, đáp án nằm trong options, không lộ đáp án ra response).

**Giai đoạn 2 — Client pixel nền tảng + Động phủ**
Engine pixel (scale nguyên, camera, tilemap Tiled, sprite, animation), menu, đăng nhập, tạo nhân vật, động phủ đi lại được, vườn 3×3 với gacha hạt, 4 dạng câu ôn của vườn, thu hoạch, bán, tutorial Trúc Lão. Sau đó thêm chiều sâu vườn của bản 1: Mặc Quái, phản ứng kề ô + Sổ Phát Hiện, sự cố thanh điệu, ghép câu, mở rộng ô đất.
✅ Người chơi mới: đăng ký → tạo nhân vật → đi trong động phủ → nhận hạt → gieo → ôn tới chín (dùng `TIME_SCALE`) → thu hoạch → bán → quay gacha. Thoát vào lại giữ nguyên.

**Giai đoạn 3 — Thế giới online**
WebSocket, Trúc Lâm Thôn + 1 zone có quái, nhiều người chơi thấy nhau di chuyển mượt (nội suy/dự đoán), channel, chat có lọc từ, bạn bè, thăm động phủ, lưu vị trí.
✅ 2 client trên 2 máy (qua Cloudflare Tunnel) thấy nhau đi lại, chat được; `tools/load_bots.py` chạy 50 bot di chuyển + chat ổn định 10 phút, tick không trễ quá 50 ms.

**Giai đoạn 4 — Chiến đấu Vấn Đạo và tu luyện**
Quái + AI, Mặc Thuẫn, câu hỏi chiến đấu, sát thương khi sai, kỹ năng Pháp Chữ, túi đồ, trang bị cơ bản (rơi đồ, mặc, cường hóa), Tu Vi, đả tọa, Thiên Kiếp Luyện Khí → Trúc Cơ, nhiệm vụ chính đầu tiên, Yêu Quái Phổ.
✅ Có test server cho: không giết được quái còn khiên, sai thì mất máu đúng công thức, hết giờ tính là sai, Thiên Kiếp đậu/trượt đúng ngưỡng. Một người chơi đi được từ Phàm Nhân lên Trúc Cơ (dùng `TIME_SCALE` và balance dev).

**Giai đoạn 5 — Ong linh**
Gacha trứng ong, tổ ong lục giác, sản xuất mật, thụ phấn trong vườn, 2–5 ong hộ vệ bay theo và đánh quái, cho ăn/lên cấp, Ong Phổ.
✅ Test: thụ phấn không làm cây lên giai đoạn nếu không trả lời; giảm thời gian chờ không vượt 25%; số ong hộ vệ đúng theo cảnh giới.

**Giai đoạn 6 — Câu cá**
Minigame, cần câu, mồi, 30 loài cá, điều kiện ngày/đêm/thời tiết, câu hỏi khi cá hiếm cắn, Ngư Phổ, bảng kỷ lục.
✅ Test phân phối tỉ lệ cá theo cần/mồi; client không gian lận được kết quả.

**Giai đoạn 7 — Thủ Vườn và Tàng Thư Các**
Chế độ tower defense, `plant_roles.json`, 30 ải + Vô Tận Trận, liên kết mastery/wither, phản ứng kề ô trong ải, mô phỏng lại log ở server, Tàng Thư Các với Bách Thảo Phổ và mọi phổ khác, tìm kiếm, mốc thưởng.
✅ Test: mô phỏng lại log hợp lệ cho cùng kết quả, log giả bị từ chối; chơi qua được chương 1.

**Giai đoạn 8 — Luyện đan, khắc văn, pet, kinh tế**
Đan phương, minigame canh lửa, các loại đan, khắc văn, gacha pet, cửa hàng, nhiệm vụ hằng ngày, `docs/BALANCE.md` mô tả dòng tiền vào/ra.
✅ Test: không có vòng lặp tạo tiền vô hạn (script mô phỏng 30 ngày chơi của 3 kiểu người chơi, in dòng tiền).

**Giai đoạn 9 — Bí cảnh hợp tác**
Tổ đội, hàng chờ ghép đội, instance, 5 loại câu đố hợp tác, boss nhiều pha, loot riêng, vào lại khi rớt mạng.
✅ 3 client (hoặc bot) cùng vượt một bí cảnh; test loot riêng từng người, không nhận loot hai lần.

**Giai đoạn 10 — Phát hành**
Đóng gói exe, `server_list_url`, Docker arm64, hướng dẫn 3 phương án triển khai, sao lưu DB, trang `/server/info`, lệnh admin.
✅ Triển khai thật theo một phương án, hai người chơi trên hai mạng khác nhau tải exe từ GitHub Releases, tạo tài khoản và chơi cùng nhau.

**Giai đoạn 11 (mở rộng, chỉ làm khi được yêu cầu)**
Kim Đan + HSK 3 và các zone Phố Mì Đêm, Chợ Nổi, Thành Cổ; đấu chữ PvP; Thủ Vườn co-op 2 người; chợ người chơi; sự kiện Tết/Trung Thu; minigame câu cá chữ.

---

## 21. Bắt đầu

Hãy bắt đầu từ **Giai đoạn 1**. Trước khi code, trình bày ngắn gọn: kế hoạch file sẽ tạo, các quyết định kiến trúc chính (đặc biệt cách tách module học tập để dùng chung cho vườn, chiến đấu, ải, bí cảnh), và rủi ro lớn nhất bạn thấy. Sau đó viết code đầy đủ, chạy test và báo kết quả.
