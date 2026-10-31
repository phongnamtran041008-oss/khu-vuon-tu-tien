# API REST

Mọi endpoint trừ `/auth/register`, `/auth/login`, `/auth/reset_password`, `/server/info` cần header
`Authorization: Bearer <token>`. Lỗi luôn có dạng:

```json
{"error": {"code": "not_due", "message_vi": "Chưa đến giờ ôn, còn 412 giây nữa."}}
```

`message_vi` hiển thị thẳng cho người chơi; `code` để client xử lý.

## Tài khoản

| Method | Đường dẫn | Body | Trả về |
|---|---|---|---|
| POST | `/auth/register` | `{username, password}` | `{token, user_id, recovery_code}` — mã khôi phục chỉ hiện **một lần** |
| POST | `/auth/login` | `{username, password}` | `{token, user_id}` |
| POST | `/auth/reset_password` | `{username, recovery_code, new_password}` | `{token, recovery_code}` (mã mới) |
| POST | `/auth/change_password` | `{old_password, new_password}` | `{token}` |
| POST | `/auth/logout_all` | — | đăng xuất mọi thiết bị |
| GET | `/server/info` | — | phiên bản giao thức, giờ server, `time_scale`, thông báo bảo trì (chi tiết ở mục Giai đoạn 10) |
| GET | `/me` | — | Linh Thạch, Tiên Ngọc, lượt quay còn lại hôm nay |

## Gacha

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/gacha/banners` | — | tỉ lệ gốc, tỉ lệ thực tế có pity, bộ đếm pity của bạn |
| POST | `/gacha/roll` | `{banner: "seeds", count: 1\|10, free: false}` | `results[]`: `{seed_id, rarity, duplicate, word:{id, hanzi}}` |

## Vườn

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/garden` | — | 9 ô; mỗi ô có `stage`, `wither`, `due`, `seconds_until_due` |
| GET | `/seeds` | — | túi hạt |
| POST | `/garden/plant` | `{plot_id, seed_id}` | gieo hạt (giai đoạn 0) |
| GET | `/garden/intro/{plot_id}` | — | thẻ giới thiệu: chữ, pinyin, nghĩa, ví dụ, `has_audio` |
| POST | `/garden/learn` | `{plot_id}` | "Đã nhớ": 0 → 1 |
| POST | `/garden/review` | `{plot_id}` | tạo (hoặc trả lại) câu hỏi ôn của ô, chỉ khi đến hạn |
| POST | `/garden/harvest` | `{plot_id}` | cây chín → 3 quả chữ |
| GET | `/fruits` · POST `/fruits/sell` | `{word_id, count}` | bán quả |
| POST | `/seeds/sell` | `{seed_id}` | bán hạt trùng (20 Linh Thạch) |
| GET | `/collection` | — | từ đã có; chi tiết chỉ hiện sau thẻ giới thiệu |

## Câu hỏi (dùng chung cho mọi hệ thống)

Câu hỏi trả về có dạng:

```json
{"session_id": "…", "context": "garden", "qtype": "Q3", "instruction_vi": "Chọn pinyin đúng",
 "prompt": {"hanzi": "妈"}, "input": "choice",
 "options": [{"id": "a", "text": "mā"}, {"id": "b", "text": "mǎ"}, …],
 "time_limit": 10.0, "expires_at": "…Z", "server_time": "…Z"}
```

`input` cho biết cách trả lời:

| input | dạng | gửi lên |
|---|---|---|
| `choice` | Q1–Q4, Q6–Q8, Q10 | `{"option": "b"}` |
| `tone` | Q11 (nút thanh 1–4) | `{"option": "3"}` |
| `text` | Q5 (gõ pinyin số, `v` = ü, thanh nhẹ có thể bỏ số 5) | `{"text": "ma1ma5"}` |
| `order` | Q9 | `{"order": ["t3", "t1", "t2"]}` |

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| POST | `/quiz/answer` | `{session_id, answer}` | `{correct, timed_out, correct_option, reveal, …}` + kết quả theo ngữ cảnh (vd `plot`, `reward`) |
| GET | `/quiz/{session_id}/audio` | — | âm thanh cho câu Q4 |
| POST | `/quiz/practice` | `{qtype?, word_id?}` | luyện tập ngoài vườn (mastery ±2) |

Đáp án không bao giờ nằm trong câu hỏi; chỉ được tiết lộ trong kết quả `/quiz/answer`. Mỗi câu chỉ trả lời
được một lần; quá hạn tính là sai.

## Giai đoạn 2

### Nhân vật và hướng dẫn

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/character/options` | — | màu tóc, kiểu tóc, dáng người được phép |
| POST | `/character/create` | `{display_name, appearance: {hair_color, hair_style, body}}` | 1 tài khoản 1 nhân vật; tên qua bộ lọc từ cấm |
| GET | `/character` | — | cảnh giới, vị trí, ngoại hình, trang phục |
| POST | `/character/position` | `{zone_id: "abode", x, y, facing}` | lưu vị trí trong động phủ |
| POST | `/tutorial` | `{step}` | bước hướng dẫn (chỉ tăng) |

`GET /me` có thêm `has_character`, `tutorial_step`, `daily_rolls_left`, `free_rolls_left`.

### Vườn mở rộng

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/garden` | — | thêm `width`, `height` (5×5), `discoveries`, `fire_events`, `decorations`; ô khóa có `can_unlock`, `unlock_cost`; ô có cây có `auras` |
| POST | `/garden/expand` | `{plot_id}` | khai hoang ô cạnh ô đã có |
| POST | `/garden/cutting` | `{word_id}` | giâm cành: thêm 1 hạt của chữ đã học (60 Linh Thạch) |
| GET | `/discoveries` | — | Sổ Phát Hiện: `{found[], total}` |
| GET | `/sentences` | — | câu ghép được (chỉ nghĩa tiếng Việt và số ô, không lộ đáp án) |
| POST | `/sentences/craft` | `{sentence_id, word_ids[]}` | đúng: dùng quả, thưởng 2× giá quả; sai: `first_wrong_slot` |

`/garden/learn` và kết quả `/quiz/answer` trong vườn có thể kèm `discoveries` (công thức vừa phát hiện).
Kết quả `/quiz/answer` có thể kèm `mishap` (sự cố thanh điệu: `effect`, `line_vi`, `wrong_hanzi`, `wrong_pinyin`,
`wrong_vi`, `stones_lost`).

## Giai đoạn 3

Thế giới thời gian thực (đi lại, kênh, chat) đi qua WebSocket `/ws`: xem `docs/PROTOCOL.md`.

### Bạn bè, chặn, báo cáo

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/friends` | — | `{friends[], incoming[], outgoing[], helps_left, max}`; mỗi người: `user_id`, `display_name`, `realm`, `online`, `zone_id`, `zone_name` |
| POST | `/friends/request` | `{display_name}` | gửi lời mời; nếu người kia đã mời mình thì thành bạn luôn |
| POST | `/friends/accept` | `{user_id}` | đồng ý lời mời của `user_id` |
| POST | `/friends/decline` | `{user_id}` | từ chối |
| POST | `/friends/remove` | `{user_id}` | hủy kết bạn (cả hai phía) |
| GET | `/blocks` | — | danh sách đã chặn |
| POST | `/blocks` | `{user_id}` | chặn (đồng thời hủy kết bạn; tin nhắn của người đó không đến nữa) |
| POST | `/blocks/remove` | `{user_id}` | bỏ chặn |
| POST | `/reports` | `{user_id, message, reason}` | báo cáo người chơi (tối đa 20 lần/ngày) |

### Thăm động phủ và tưới giúp

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/friends/{friend_id}/garden` | — | chỉ bạn bè; xem vườn (chỉ đọc, không làm thay đổi gì). Chữ mình chưa học thì không hiện pinyin/nghĩa. Ô có `helpable` |
| POST | `/friends/help` | `{friend_id, plot_id}` | mở một câu hỏi (ngữ cảnh `help`) về chữ trong ô đó; chỉ chữ mình đã học; tối đa 5 lượt/ngày (tính cả lượt sai) |

Trả lời bằng `/quiz/answer` như mọi câu khác. Đúng: cả hai được `help_reward` (10) Linh Thạch, chủ vườn nhận
tin `friend`/`helped` qua WebSocket. Đúng hay sai đều cập nhật thông thạo (±2) của người tưới, **cây của chủ
vườn không đổi**.

### Máy chủ

| Method | Đường dẫn | Ghi chú |
|---|---|---|
| GET | `/server/stats` | số người online, kênh, thời gian tick (trung bình, p99, lớn nhất) và độ trễ tick; dùng cho `tools/load_bots.py` |

`POST /character/position` (động phủ) bị bỏ qua (`{"ok": false, "ignored": "in_world"}`) khi nhân vật đang đứng
trong thế giới chung, để một lần lưu đến muộn không kéo nhân vật về động phủ.

## Giai đoạn 4

Chiến đấu diễn ra qua WebSocket (`atk`, `skill`, câu hỏi `q`, xem `docs/PROTOCOL.md`); câu hỏi chiến đấu vẫn trả lời
bằng `POST /quiz/answer`, kết quả có thêm `combat`:
`{correct: true, shield_broken, damage, crit}` hoặc `{correct: false, mac_kich, hp, dead}`.

Mọi câu trả lời đúng có thêm `xp`: `{gained, xp, need, realm, stage, stage_up, bottleneck}` (Tu Vi theo ngữ cảnh,
số trong `balance/cultivation.json` → `xp_per_correct`).

### Tu luyện và Thiên Kiếp

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/cultivation` | — | `realm`, `realm_name`, `stage`, `label`, `xp`, `need`, `next_realm`, `pill`, `pill_name`, `has_pill`, `can_tribulation`, `tribulation_ready_in`, `stats` {`max_hp`, `max_qi`, `atk`, `def`, `crit`, `ink_res`, `weapon`}, `skills[]` |
| POST | `/cultivation/meditate` | — | một câu đả tọa (ngữ cảnh `meditate`), chỉ trong động phủ, mỗi 2 phút một câu. Lỗi: `not_home`, `meditate_wait`, `nothing_learned` |
| POST | `/cultivation/breakthrough/start` | — | bắt đầu (hoặc tiếp tục) Thiên Kiếp: `{question, resumed}`; câu có `number`, `total`. Lỗi: `no_tribulation`, `xp_not_full`, `no_pill`, `tribulation_wait` |

Thiên Kiếp: trả lời từng câu bằng `/quiz/answer`; kết quả có `next` (câu kế) cho tới câu 20, câu cuối có
`tribulation`: `{passed, correct, total, pass_pct}` + khi qua `{realm, label, jade}`, khi trượt `{xp_lost, retry_in}`; mỗi câu có `number`, `total`, `correct_so_far`. Câu quá hạn tính là sai; thoát
giữa chừng rồi gọi lại `start` thì tiếp tục từ câu đang dở.

### Túi đồ, trang bị, lò rèn

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/inventory` | — | `items[]` {`item_id`, `name_vi`, `kind`, `qty`, `desc_vi`, `usable`, `sell_price`}, `equipment[]` {`id`, `item_id`, `name_vi`, `slot`, `slot_vi`, `rarity`, `rarity_vi`, `color`, `enhance`, `stats`, `equipped`, `next_enhance`} |
| POST | `/inventory/use` | `{item_id}` | đan dược (chỉ khi đang ở thế giới chung; lỗi `not_in_world`, `pill_cooldown`) hoặc bí kíp Pháp Chữ (`already_learned`, `mastery_low`) |
| POST | `/equipment/equip` | `{instance_id}` | mặc vào ô của món đó (món cũ tự tháo); trả `stats` mới |
| POST | `/equipment/unequip` | `{slot}` | tháo |
| POST | `/forge/enhance` | `{instance_id}` | `{success, item, spirit_stones, stats}`; thất bại chỉ mất nguyên liệu và Linh Thạch. Lỗi: `max_level`, `no_material`, `insufficient_funds` |

### Nhiệm vụ và Yêu Quái Phổ

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/quests` | — | `quests[]` {`id`, `chain`, `chain_vi`, `title_vi`, `desc_vi`, `state` (`active` \| `done`), `objective` {`type`, `target`, `n`, `target_vi`}, `progress`, `rewards_vi[]`} |
| POST | `/quests/talk` | `{npc}` | nói chuyện với NPC (phải đứng gần trong thế giới; lỗi `too_far`) → `{finished[]}` |
| POST | `/quests/claim` | `{quest_id}` | nhận thưởng nhiệm vụ đã xong → `{claimed, rewards, next}`. Lỗi: `no_quest`, `not_done` |
| GET | `/codex/monster` | — | `{found, total, entries[]}`; quái chưa gặp chỉ có `id`, `sprite`, `found: false` |

## Giai đoạn 5 — Linh Phong (ong linh)

Ong hộ vệ đánh quái trong thế giới chung (xem `docs/PROTOCOL.md`); mọi thứ khác qua REST. Mật và phấn hoa được
**tính lười**: mỗi lần mở tổ / tải vườn / đổi vai trò, server tính phần làm ra từ lần trước tới nay (nhân
`TIME_SCALE` như lịch ôn).

### Tổ ong

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/bees/species` | — | công khai: `{species: {id: {name_vi, hanzi, rarity, element, skill, look}}}` (client vẽ ong của người khác) |
| GET | `/hive` | — | lần đầu tạo tổ và tặng 1 Trứng Ong Phàm. `level`, `level_max`, `cells`, `cells_max`, `columns`, `rows`, `open_cells[]` (ô theo thứ tự mở từ giữa ra), `next_cell` {`cell`, `spirit_stones`, `species_required`, `ok`}, `honey`, `wax`, `capacity`, `honey_per_hour`, `next_level` {chi phí, `capacity`, `honey_mult`, `decoration_vi`}, `decorations[]` {`id`, `name_vi`, `on`}, `bees[]`, `eggs[]` {`item_id`, `rarity`, `qty`}, `foods[]` {`food`, `name_vi`, `qty`}, `guard_slots`, `guard_used`, `pollinate_max`, `pollinate_used`, `species_found`, `species_total` |
| POST | `/hive/collect` | — | chuyển mật/sáp trong tổ (phần nguyên) vào túi: `{honey, wax, totals}`. Lỗi `no_honey` |
| POST | `/hive/hatch` | `{item_id}` | ấp một quả trứng: `{bee, new_species, milestones[]}`. Loài được chọn lúc nở (cùng độ hiếm, loài chưa có nặng gấp đôi). Lỗi `not_egg`, `no_egg`, `hive_full` |
| POST | `/hive/unlock_cell` | — | mở ô kế tiếp (Linh Thạch + mốc Ong Phổ). Lỗi `need_species`, `hive_max`, `insufficient_funds` |
| POST | `/hive/upgrade` | — | nâng cấp tổ (Linh Thạch, Sáp Ong, Gỗ Linh Mộc). Lỗi `no_material`, `hive_max_level` |
| POST | `/hive/decoration` | `{decoration, on}` | bật/tắt trang trí đã mở. Lỗi `decoration_locked` |

Mỗi ong trong `bees[]`: `id`, `species`, `name_vi`, `hanzi`, `pinyin`, `rarity`, `rarity_vi`, `rarity_color`,
`element`, `element_vi`, `level`, `xp`, `xp_next`, `bond`, `role` (`hive` \| `pollinate` \| `guard`), `slot`,
`resonance_pct`, `word` {`hanzi`, `pinyin`, `vi`}, `word_mastery`, `honey_per_hour`, `pollen_per_hour`,
`guard` {`hp`, `atk`, `cd`}, `skill`, `skill_vi`, `favorite_known`, `favorite`, `favorite_hint_vi`, `look`.

### Ong

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| POST | `/bees/move` | `{bee_id, slot}` | đặt vào ô đã mở; ô có ong thì đổi chỗ. Trả lại `/hive`. Lỗi `cell_locked` |
| POST | `/bees/role` | `{bee_id, role}` | `hive` / `pollinate` (tối đa 6) / `guard` (số ô theo cảnh giới: Phàm Nhân 0, Luyện Khí 2, Trúc Cơ 3, Kim Đan 4, Nguyên Anh 5). Lỗi `no_guard_slot`, `guard_full`, `pollinate_full` |
| POST | `/bees/feed` | `{bee_id, food}` | `food` = `linh_mat` \| `linh_qua` \| `ca_nho` \| `fruit:<word_id>` → `{xp_gained, favorite, favorite_discovered, favorite_vi, levels_gained, level, xp, xp_next, bond, bond_gained}`. Món thích: kinh nghiệm ×2, thân thiết +8 (thường +2). Lỗi `no_food`, `bad_food` |
| POST | `/bees/release` | `{bee_id}` | thả ong, nhận Sáp Ong theo độ hiếm |
| GET | `/codex/bee` | — | Ong Phổ: `{found, total, entries[], milestones[]}`; loài chưa gặp chỉ có `id`, `rarity`, `found: false` |

### Vườn, gacha, túi đồ

- `GET /garden`: mỗi ô có thêm `pollen` (0–100) và `pollinated`; gói có `pollinated[]` (cây vừa thụ phấn đầy
  `{plot_id, hanzi}`), `bees[]` {`id`, `sp`, `role`} và `hive` {`level`, `decorations`} để vẽ ong bay.
- `POST /garden/harvest`: thêm `pollinated`, `spirit_fruit` (số Linh Quả), `spirit_fruit_total`. Cây đã thụ phấn cho 5 quả.
- `POST /gacha/roll`: `banner: "bees"` mở; thêm `currency` (`spirit_stones` \| `immortal_jade`). Kết quả mỗi lượt
  `{rarity, item, name_vi, total}` (trứng vào túi). Lượt miễn phí chỉ cho Hạt Chữ (`no_free_roll`).
- `POST /inventory/sell` `{item_id, qty}`: làng mua vật phẩm có `sell_price` (Linh Mật, Sáp Ong, Gỗ, Linh Quả, Mực Tinh).
  Lỗi `not_sellable`, `not_enough`.
- `GET /friends/{id}/garden` cũng có `bees`, `hive`, và `pollen`/`pollinated` của từng cây.

## Giai đoạn 6 — Câu cá (mục 11)

Mọi kết quả do máy chủ quyết định. Một lượt câu: `cast` → (chờ `bite_in` giây) → `hook` → câu hỏi nếu cá từ Linh trở
lên (trả lời qua `/quiz/answer` như mọi câu khác, `context: "fishing"`) → chơi trò kéo cá → `reel`.

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/fishing` | — | `{rod, bait, rods[], baits[], scales, conditions{zone, night, rain, hour}, casting}`. Lần đầu tặng Cần Trúc Thô. Mỗi cần: `id, name_vi, rarity, owned, equipped, level, stats{pull, line, luck, bite, zone}, price, min_realm, upgrade_cost`. Mỗi mồi: `id, name_vi, qty, buy, craft{from, makes, have}, equipped` |
| POST | `/fishing/equip` | `{rod?, bait?, no_bait?}` | chọn cần/mồi đang dùng. Lỗi `no_rod`, `no_bait` |
| POST | `/fishing/buy` | `{item_id, qty}` | mua cần (một lần) hoặc Giun Đất; phải đứng cạnh Ngư Ông. Lỗi `too_far`, `owned`, `not_sold`, `realm_too_low`, `not_enough` |
| POST | `/fishing/craft` | `{bait_id, times}` | Bánh Mật ← Linh Mật, Linh Quả Vụn ← Linh Quả, Mồi Mực ← Mực Tinh; cạnh Ngư Ông |
| POST | `/fishing/upgrade` | `{rod_id}` | nâng cần một cấp (tối đa 5) ở Lò Rèn (cạnh Thợ Rèn): Linh Thạch + Vảy Linh Ngư |
| POST | `/fishing/cast` | `{spot}` | `spot` = `abode` (ao động phủ, khi không đứng ngoài thế giới) \| `world` (máy chủ kiểm tra vị trí thật của nhân vật có sát mép nước). Dùng 1 mồi. → `{cast_id, bite_in, window, zone, pool, rod, bait, conditions, bait_left}`. Lỗi `not_here`, `no_bait`, `bait_needs_night`, `nothing_bites` |
| POST | `/fishing/hook` | `{cast_id}` | giật câu: `{stage: "early"}` (sớm), `"late"` (muộn), `"quiz"` + `{rarity, need, question}` hoặc `"reel"` + `{rarity, params, quiz_mult}`. Loài và kích thước chọn lúc này, không gửi cho client |
| POST | `/fishing/reel` | `{cast_id, toggles[]}` | `toggles`: các số bước (20 ms) mà nút đổi trạng thái, tăng dần, bắt đầu từ "nhả". Máy chủ chạy lại `fishing_sim.replay` → `{result: caught\|escaped\|snapped, steps}`; câu được thì thêm `fish{...}, size_cm, small, items[], new_species, personal_record, server_record, milestones[]`. Lỗi `too_fast` (nhanh hơn thời gian thật), `bad_input`, `no_cast`, `wrong_step` |
| POST | `/fishing/cancel` | — | thu cần |
| GET | `/codex/fish` | — | Ngư Phổ `{found, total, species[], milestones[]}`; loài chưa câu chỉ có `id, rarity, shape, hint_vi` |
| GET | `/fishing/records` | — | `{records: [{id, name_vi, hanzi, rarity, top: [{name, size_cm, me}]}]}` — 3 con to nhất mỗi loài toàn máy chủ |
| GET | `/world/weather?zone=` | — | `{zone, night, rain, hour}` |

Khi trả lời câu hỏi câu cá, `/quiz/answer` có thêm `fishing`: `{stage: "quiz", next_question, right, need}` (cá Thiên
cần đúng 2 câu liên tiếp) hoặc `{stage: "reel", params, quiz_mult, right, need, rarity}`. Sai không bao giờ trừ máu.

`params` của trò kéo cá: `seed, zone, agility, range, seg_ms, gain, loss, start, lift, gravity, vmax, strain_up,
strain_down, max_ms` — đầu vào của `fishing_sim.Reel` (file giống hệt nhau ở `server/app/systems/` và `client/engine/`).
Cá câu được vào túi là `fish_<loài>` (bán được); cá Phàm quá nhỏ thành `ca_nho`; cá từ Linh trở lên cho `vay_linh_ngu`.

## Giai đoạn 7 — Ải Thủ Vườn và Tàng Thư Các (mục 9)

Trò thủ vườn chạy ở client bằng `td_sim.py` (file giống hệt nhau ở `server/app/systems/` và `client/engine/`). Máy chủ
chọn hạt giống, gửi mọi số liệu, tự hỏi và chấm mọi câu hỏi, rồi chạy lại nhật ký của client trước khi trao thưởng.

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/td/levels` | — | `{active_run{run_id, level_id, name_vi, waves}?, chapters[], levels[{id, chapter, index, name_vi, waves, unlocked, locked_vi, stars, best_wave, monsters[], first_rewards[3]}], endless{unlocked, locked_vi, week, best_wave}, loadout[], loadout_max, plants[{word_id, hanzi, pinyin, meaning_vi, rarity, role, mastery, wither, power, skill?}], roles, role_stats, stars_need, daily_left, daily_max}` |
| POST | `/td/loadout` | `{slots[]}` | tối đa 8 `word_id` đã học (trùng thì bỏ). Lỗi `too_many`, `not_learned` |
| POST | `/td/start` | `{level_id, loadout?}` | `level_id` = `c1_01`…`c3_10` hoặc `endless`. → `{run_id, params, step_ms, max_speed, name_vi, monsters[]}`. Lỗi `locked`, `no_level`, `empty_loadout` |
| POST | `/td/question` | `{run_id, kind, word_id?}` | `kind` = `break` (3 câu giữa các đợt), `tu_khi` (nút Tụ Khí), `upgrade` (luôn hỏi đúng chữ `word_id` của cây). → một phiên câu hỏi `context: "td"`, trả lời qua `/quiz/answer` |
| POST | `/td/finish` | `{run_id, events[], claim{result, core_hp, wave, steps}}` | máy chủ chạy lại `td_sim.replay`. → `{result, core_hp, wave, steps, waves_cleared, stars, prev_stars, new_stars[], rewards, daily_left, next_level}` (Vô Tận Trận: `waves_cleared, record, rewards, board`). Lỗi `bad_log` (sự kiện trái luật, câu hỏi không có hoặc dùng hai lần, bỏ sót câu đã trả lời), `log_mismatch` (kết quả khác khi chơi lại), `too_fast`, `unfinished`, `no_run` |
| POST | `/td/event` | `{run_id, start, events[]}` | lưu phần nhật ký từ chỉ số `start` → `{saved}`. Gửi lại đoạn đã lưu phải giống hệt. Lỗi `log_conflict`, `log_gap`, `bad_log`, `too_many` |
| POST | `/td/resume` | — | chơi tiếp lượt dở: như `/td/start` cộng `events[]` (đã lưu) và `answers{session_id: {kind, word, ok}}`. Lỗi `no_run` |
| POST | `/td/cancel` | — | bỏ lượt đang chơi (không thưởng) |
| GET | `/td/endless/board` | — | `{week, top[{rank, name, waves, me}]}` — giữ được nhiều đợt nhất trong tuần |
| GET | `/library` | — | Tàng Thư Các: `{books[{id, name_vi, found, total, pct, milestones[{pct, reward, reward_vi, ready, claimed}]}], titles[], frames[], title, frame, shop[{item_id, name_vi, desc_vi, price, have, learned}], at_desk}`; `id` = `plant, monster, bee, fish, discovery, treasure` |
| POST | `/library/wear` | `{title?, frame?}` | đeo danh hiệu/khung đã có (`""` = bỏ). Lỗi `no_title`, `no_frame` |
| POST | `/library/buy` | `{item_id}` | mua bí kíp ở kệ Thủ Thư (phải đứng cạnh bà ở Trúc Lâm Thôn). Lỗi `too_far`, `not_sold`, `not_enough` |
| GET | `/codex/treasure` | — | Bảo Vật Phổ `{found, total, entries[{id, kind, kind_vi, found, name_vi?, desc_vi?, first_at?}]}` |
| POST | `/library/claim` | `{book, pct}` | nhận mốc 25/50/75/100%. Lỗi `not_yet`, `claimed`, `bad_milestone` |
| GET | `/codex/plant` | — | Bách Thảo Phổ `{found, total, plants[]}`: cây đã có có đủ trang (chữ, pinyin, nghĩa, ví dụ, cấu tạo, vai trò + chỉ số, mastery, `quip_vi`); cây chưa có chỉ `word_id, found:false, hidden:false, rarity, tier, role`; cây ẩn chưa phát hiện chỉ `word_id, found:false, hidden:true, tier` |
| GET | `/library/search?q=` | — | tìm theo chữ Hán, pinyin có/không dấu/dạng số, nghĩa tiếng Việt có/không dấu, tên cá/ong/quái; chỉ trong những gì đã phát hiện. `{q, results[{book, id, title, sub}], more}` |
| GET | `/library/mistakes` | — | Sổ Lỗi `{words[{word_id, hanzi, pinyin, meaning_vi, times_wrong, times_correct, accuracy, mastery, needs_review}]}`; luyện bằng `POST /quiz/practice {word_id}` |

Khi trả lời câu hỏi thủ vườn, `/quiz/answer` có thêm `td: {kind, ok, qi}` (`qi` là Linh Khí được/mất; câu nâng cấp
`qi = 0`). `GET /me` có thêm `title`, `frame`. `GET /codex/monster` giờ có cả quái của ải (`id` bắt đầu bằng `td_`, `td: true`).

**Sự kiện trong nhật ký** (mỗi sự kiện có `s` = số bước 50 ms lúc nó xảy ra; giữa các đợt thời gian không trôi):
`{k: "place", x, y, w}`, `{k: "sell", x, y}`, `{k: "up", x, y, q}`, `{k: "qi", q}`, `{k: "skill", w}`, `{k: "wave"}`.
`q` là `session_id` của câu hỏi; máy chủ dùng kết quả đúng/sai mà nó đã chấm, không dùng của client.

## Giai đoạn 8 — Luyện đan, khắc văn, Linh Thú, kinh tế (mục 12, 13)

Cân bằng tiền vào/ra: `docs/BALANCE.md`. Minigame canh lửa dùng `alchemy_fire.py` (file giống hệt nhau ở
`server/app/systems/` và `client/engine/`): kim chạy 0 → `bar` → 0 mỗi `period_ms`; client chỉ gửi kim đã chạy bao lâu
trước mỗi lần bấm, máy chủ tính lại vị trí kim, tự chấm pinyin và quyết định phẩm chất.

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/alchemy` | — | `{recipes[{id, name_vi, hanzi, desc_vi, chars[{c, hv}], known, difficulty, fee, yield{ha, trung, thuong}, have_pills, min_realm, min_realm_vi, realm_ok, ingredients[{name_vi, qty, have}]?, ready?, sources_vi[]?}], furnace{level, name_vi, max, next{level, name_vi, cost, materials[], zone_bonus, extra_chance}?}, where: home\|public\|far, level_here, open (mẻ đang luyện)?, buffs[], quality[]}` |
| POST | `/alchemy/start` | `{recipe_id}` | lấy nguyên liệu + phí ngay, nhóm lửa → `{fire{session_id, recipe_id, name_vi, hanzi, bar, periods[3], zones[3]{center, width, perfect}, chars[3]{c, hv, ask, pinyin? (chỉ khi ask=false)}, furnace_level, expires_at}, resumed, used[]}`. Đang có mẻ dở cùng đan thì trả lại mẻ đó. Lỗi `no_recipe`, `no_ingredient`, `insufficient_funds`, `realm_low`, `too_far`, `fire_busy` |
| POST | `/alchemy/finish` | `{session_id, timings[3] (ms kim chạy), pinyin_answers[3] (chuỗi hoặc null)}` | → `{quality: phe\|ha\|trung\|thuong, quality_vi, points, best, hits[], positions[], chars[{c, pinyin, hv, right (null = không hỏi)}], made, extra, pill, total, xp}`. Hết hạn (15 phút) → `{quality: "phe", expired: true, made: 0}`. Lỗi `bad_timings`, `too_fast` (kim không thể chạy nhanh hơn thời gian thật), `bad_answers`, `finished` (409), `no_session` |
| POST | `/alchemy/furnace/upgrade` | — | nâng Đan Lô trong động phủ (chỉ ở nhà). Lỗi `not_home`, `max_level`, `no_material`, `insufficient_funds` |
| GET | `/forge/inscribe/{instance_id}` | — | `{item, slots, used, inscriptions[{word_id, hanzi, stat, value}], mastery_min, questions, fee_vi, erase_fee, words[{word_id, hanzi, pinyin, meaning_vi, mastery, ok, carved, stat, stat_vi, value}], running?}` |
| POST | `/forge/inscribe/start` | `{instance_id, word_id}` | trừ phí, → `{question (context "forge", number, total), item}`. Trả lời qua `/quiz/answer`: kết quả có `inscribe{done, success, right, total, item?, carved{hanzi, stat, stat_vi, value}?, stats?}` và `next` (câu tiếp) khi chưa đủ 3. Sai một câu là hỏng. Lỗi `mastery_low`, `not_learned`, `already_carved`, `no_slot`, `insufficient_funds`, `no_item` |
| POST | `/forge/inscribe/erase` | `{instance_id, index}` | mài một chữ (30 Linh Thạch) |
| GET | `/pets` | — | `{pets[{id, pet_type, name_vi, zodiac_vi, hanzi, pinyin, rarity, rarity_vi, level, max_level, equipped, skill_vi, stats, look}], equipped, book[12]{id, found, zodiac_vi, rarity, (đã gặp:) name_vi, hanzi, pinyin, skill_vi, look}, found, total, looks{loài: look}}` |
| POST | `/pets/equip` | `{pet_id \| null}` | đeo một con (hoặc tháo); trả lại như `GET /pets`. Lỗi `no_pet` |
| GET | `/shop` | — | `{stock[{item_id, name_vi, desc_vi, price, daily, left, have}], equipment[{item_id, rarity, rarity_vi, color, name_vi, slot_vi, price, stats}], at_shop, sell_items[], sell_equipment[], spirit_stones}` |
| POST | `/shop/buy` | `{item_id, qty, rarity?}` | phải đứng cạnh Bà Chủ Sạp. `rarity` (`pham`/`linh`) để mua trang bị. `hat_giong_thuong` → `seeds[]` (tính vào 15 hạt mới/ngày). Lỗi `too_far`, `not_sold`, `sold_out`, `daily_limit`, `insufficient_funds`, `bad_count` |
| POST | `/shop/sell_equipment` | `{instance_id}` | bán lại trang bị không mặc. Lỗi `equipped`, `too_far` |
| POST | `/friends/gift` | `{friend_id, item_id, qty}` | tặng bạn bè 1–5 món không ràng buộc, 5 lần/ngày. Người nhận được thông báo WebSocket `{t: "friend", event: "gift", item, name_vi, qty, user}`. Lỗi `not_friend`, `blocked`, `not_giftable`, `bad_count`, `gift_limit`, `not_enough` |

Thay đổi ở API cũ:

- `POST /gacha/roll {banner: "pets"}` đã mở: kết quả `[{rarity, pet_type, name_vi, hanzi, pinyin, zodiac_vi, look, pet_id, new, level, level_up?, stones?}]`.
- `POST /inventory/use` dùng được Tụ Linh / Kháng Mực / Ngộ Tính Đan → `{used, left, buff, seconds, buffs[]}`; Phong
  Vương Đan cho ong ăn qua `POST /bees/feed {food: "phong_vuong_dan"}`.
- `GET /cultivation` có thêm `buffs[{id, name_vi, seconds_left}]` và `pet` (con đang đeo). `GET /inventory`: mỗi
  trang bị có `inscriptions[]`, `inscribe_slots`, `sell_price`; mỗi vật phẩm có `hanzi` (đan dược).
- `GET /quests` có thêm `daily[]` (việc hằng ngày, `chain: "daily"`, id `d<ngày>:<việc>`) và `daily_bonus{rewards_vi,
  claimed}`; nhận việc cuối cùng của ngày trả thêm `rewards.bonus`. Kiểu mục tiêu mới: `brew`, `inscribe`, `review`,
  `answer`, `td_win`; `target: "*"` là bất kỳ.
- Câu trả lời ôn vườn đúng có `streak` và có thể có `pet_bonus{pet: trau|rong, extra, streak?}`.
- `GET /library`: thêm sổ `pet` (Linh Thú Phổ); `shop[]` có `kind` (`manual`/`recipe`), mua đan phương đã có → `already_have`.

## Giai đoạn 9 — Bí cảnh (mục 14)

Vào bí cảnh, tổ đội và mọi thứ trong lượt chơi đi qua WebSocket (`docs/PROTOCOL.md`). REST chỉ có:

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| GET | `/realms` | — | `{realms[{id, name_vi, hanzi, kind: scheduled\|rift, min_realm, min_realm_vi, realm_ok, tier, puzzles, time_limit_minutes, desc_vi, entries_left, daily, open, opens_in, closes_in}], party, queue{key, realm, waiting}?, puzzles{kind: {name_vi, hanzi, how_vi}}, forge{fragments, stones, have, rarity, rarity_vi, set_vi, bonus_vi, pieces[{id, name_vi, slot_vi}]}}` |
| POST | `/realm/forge` | `{piece}` | 12 Mảnh Bảo Vật + 600 Linh Thạch → một món Mặc Ảnh phẩm Thiên → `{equipment, spirit_stones}`. Lỗi `not_enough`, `bad_piece` |

Thay đổi ở API cũ: `GET /fishing` — Cần Thiên Tơ có giá (Thiên Tằm Ti + Vảy Linh Ngư + Linh Thạch, cần Trúc Cơ). Chỉ số
nhân vật cộng thưởng đồ bộ (`equipment.json → sets`). Yêu Quái Phổ có thêm 3 quái bí cảnh.

## Giai đoạn 10 — Phát hành

| Method | Đường dẫn | Ghi chú |
|---|---|---|
| GET | `/server/info` | `{name, version, protocol_version, server_time, local_date, time_scale, env, maintenance_message, announcement, online, uptime_seconds, latest_client_version, client_download_url}`. Trình duyệt (`Accept: text/html`) nhận trang trạng thái HTML; `?format=json` / `?format=html` để ép kiểu |
| GET | `/` | chuyển tới `/server/info` |
| GET | `/healthz` | `{"ok": true}` cho kiểm tra sống của nơi chạy (Render, Docker); không chạm cơ sở dữ liệu |

`maintenance_message` và `announcement` đổi được lúc chạy bằng `/admin maintenance` và `/admin announce` (chat, xem
`docs/DEPLOY.md` mục F); `MAINTENANCE_MESSAGE` là giá trị sau khi khởi động lại. `latest_client_version` lấy từ
`LATEST_CLIENT_VERSION` (mặc định bằng `version`), `client_download_url` từ `CLIENT_DOWNLOAD_URL`.

Thay đổi ở API cũ: `POST /auth/register` cấp `is_admin` cho tên có trong `ADMIN_USERNAMES`. Tài khoản bị khóa nhận
`403 banned` ở mọi request có token và ở `/auth/login`. Câu trả lời Vấn Đạo (`/quiz/answer` và mọi nơi khác) được theo dõi:
200 câu đúng liền mỗi câu dưới 0,5 giây (`balance/quiz.json → bot_watch`) thì tài khoản bị đánh dấu (`suspicious_flag`) cho
quản trị viên xem, không tự cấm.

## Bản 1.1 — Thế giới LAN (tài khoản Firebase)

| Method | Đường dẫn | Body | Ghi chú |
|---|---|---|---|
| POST | `/auth/firebase` | `{id_token}` | ID token Firebase Authentication → `{token, user_id, username, created, is_admin}` (token phiên của thế giới này, dùng như token của `/auth/login`). Lần đầu tạo tài khoản cục bộ (kèm hạt 水). Lỗi: `firebase_off` (404, máy chủ không đặt `FIREBASE_API_KEY`), `firebase_invalid_id_token` (401), `firebase_network` / `firebase_configuration_not_found` (503), `banned` (403) |

`GET /server/info` có thêm `auth` (`firebase` | `local`), `local_accounts` (bool) và `world_name` (thế giới LAN).
Khi `LOCAL_ACCOUNTS=0`, `/auth/register` và `/auth/login` trả `403 local_off`.
Biến môi trường mới: `FIREBASE_API_KEY`, `HOST_FIREBASE_UID` (người chủ thành quản trị viên), `LOCAL_ACCOUNTS`,
`LAN_BEACON`, `LAN_WORLD_NAME`, `LAN_HOST_NAME`, `FIREBASE_AUTH_EMULATOR_HOST` (thử nghiệm).

Tín hiệu LAN (không phải HTTP): UDP broadcast tới cổng 47654 mỗi 1,5 giây, nội dung JSON
`{"g": "khuvuon-lan", "v": <giao thức>, "name", "host", "port", "online"}`.

