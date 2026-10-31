# Giao thức WebSocket (thế giới chung)

Đường dẫn: `ws://<máy chủ>/ws` (hoặc `wss://` khi máy chủ chạy HTTPS, ví dụ qua Cloudflare Tunnel).
Mỗi gói tin là **một object JSON**, trường `t` cho biết loại. Phiên bản giao thức hiện tại: **3**
(3 = giai đoạn 4: chiến đấu; `me` và trạng thái thực thể có thêm máu/khiên)
(`server/app/config.py` và `client/config.py`; `/server/info` trả `protocol_version`).

Định nghĩa trong code: `server/app/realtime/protocol.py` (kiểm tra gói tin từ client), xử lý ở
`world.py`, `zone.py`, `chat.py`, `combat.py`, `ai.py`. Mọi con số dưới đây nằm trong
`server/data/balance/world.json`, `social.json` và `combat.json`.

## Kết nối

1. Client mở WebSocket, gói tin **đầu tiên** phải là `hello` (trong 10 giây):

   ```json
   {"t": "hello", "v": 4, "token": "<JWT lấy từ /auth/login>"}
   ```

2. Server trả `welcome`, hoặc `error` rồi đóng kết nối:

   | `code` | mã đóng | ý nghĩa |
   |---|---|---|
   | `version` | 4002 | client cũ, cần cập nhật |
   | `bad_token`, `token_expired` | 4003 | đăng nhập lại |
   | `no_character` | 4004 | chưa tạo nhân vật |
   | `banned` | 4003 | tài khoản bị khóa |

   ```json
   {"t": "welcome", "v": 4, "you": {"uid": 7, "id": "p7", "name": "Tiểu Trúc"},
    "zone": "abode", "st": 1234.5, "day": 0.42, "day_length": 7200}
   ```

   `zone` là nơi nhân vật đang đứng: `abode` (động phủ, riêng tư, không đi qua WebSocket) hoặc một vùng của
   thế giới (nếu lần trước thoát ở đó, hoặc vừa rớt mạng chưa quá 30 giây). `st` là đồng hồ server (giây),
   `day` là vị trí trong ngày của game (0 = nửa đêm, 0,5 = giữa trưa; một ngày game = 2 giờ thật).

3. **Một tài khoản một kết nối**: kết nối mới làm kết nối cũ nhận `{"t":"kicked","reason":"elsewhere"}` (mã 4001).

4. **Heartbeat**: client gửi `{"t":"ping","c":<giờ client>}` mỗi 15 giây khi không có gì khác để gửi; server trả
   `{"t":"pong","c":...,"st":...}`. Im lặng quá 45 giây thì server ngắt (`kicked`, `reason: timeout`, mã 4005).

5. **Giới hạn**: tối đa 30 gói tin/giây (vượt thì `kicked`, `reason: flood`, mã 4008), mỗi gói tối đa 4 KB.

6. **Rớt mạng**: nhân vật đứng yên 30 giây rồi mới rời khỏi vùng. Kết nối lại trong lúc đó thì gửi
   `join` với `via: "resume"` để nhận lại đúng chỗ. Client tự kết nối lại, chờ 1, 2, 4… tối đa 30 giây.

## Client → server

| `t` | Trường | Ý nghĩa |
|---|---|---|
| `ping` | `c` (số, tùy chọn) | heartbeat |
| `join` | `zone`, `via`: `abode` \| `portal` \| `resume` | vào một vùng (xem dưới) |
| `in` | `s` (số thứ tự tăng dần), `k`: `[[dx, dy, ms], …]` | ý định di chuyển |
| `face` | `f`: `down` \| `up` \| `left` \| `right` | quay mặt, không đi |
| `channel` | `n` | đổi kênh trong vùng hiện tại (`n` = số kênh có sẵn, hoặc số lớn nhất + 1 để mở kênh mới) |
| `chat` | `ch`: `world` \| `zone` \| `friend` \| `party`, `text`, `to` (đạo hiệu của bạn, khi `friend`) | chat |
| `atk` | `id` (quái) | đánh thường (giai đoạn 4); server kiểm tra tầm vũ khí và thời gian hồi |
| `skill` | `k`: `hoa` \| `thuy` \| `moc` \| `son`, `id` (quái, với pháp đánh một mục tiêu) | dùng Pháp Chữ |

### Vào vùng (`join`)

- `via: "abode"`: từ cổng tre của động phủ, chỉ dẫn tới `truc_lam_thon` (xuất hiện ở điểm `from_abode`).
- `via: "portal"`: nhân vật phải **đứng trong cổng** (vùng `portal` của bản đồ Tiled) dẫn tới vùng đó. Nếu
  vài bước cuối còn trong hàng đợi, server chờ chúng (tối đa 1 giây) rồi mới quyết định. Cổng `to_abode`
  đưa về động phủ: server trả `zone` với `"zone": "abode"`.
- `via: "resume"`: quay lại vùng đã lưu (hoặc nhân vật còn đứng đó sau khi rớt mạng).
- **Cảnh giới**: không vào được vùng có cảnh giới khuyến nghị cao hơn mình quá 1 bậc (`data/zones.json`,
  `realm_gate_margin`), lỗi `realm_too_low`.
- Mỗi vùng chia **kênh**, tối đa 40 người/kênh; vào vùng thì được xếp vào kênh số nhỏ nhất còn chỗ, đầy hết
  thì tự mở kênh mới (tối đa 20). Kênh phụ trống tự đóng.

### Di chuyển (`in`)

Mỗi khung hình client ghi lại phím hướng đang giữ (`dx`, `dy` ∈ {-1, 0, 1}) và số mili giây của khung đó, rồi
gom lại gửi tối đa 20 lần/giây:

```json
{"t": "in", "s": 41, "k": [[0, -1, 17], [1, -1, 16], [1, -1, 17]]}
```

Server là bên quyết định vị trí: mỗi tick (20 lần/giây) nó áp dụng các bước bằng **đúng cùng hàm**
`movement.step` (tốc độ 74 px/giây, đi chéo × 0,7071, va chạm theo từng trục với khung chân 10 × 6 px).
Chống hack tốc độ: mỗi người có một "ngân sách thời gian" tăng theo giờ thật (tối đa 600 ms tích lũy); một
gói chỉ được áp dụng khi ngân sách đủ, một gói tối đa 250 ms, hàng đợi tối đa 1,5 giây. Bước sai luật bị bỏ,
và client tự kéo về vị trí đúng nhờ snapshot. Gói trùng hoặc số thứ tự cũ bị bỏ qua.

## Server → client

| `t` | Trường | Khi nào |
|---|---|---|
| `welcome` | xem trên | sau `hello` |
| `zone` | `zone`, `name_vi`, `safe`, `channel`, `channels` [`{n, players, cap}`], `x`, `y`, `f`, `ack`, `st`, `day` | vừa vào vùng / đổi kênh / về động phủ |
| `snap` | `st`, `ack`, `me` [`x`, `y`, `facing`, …, ong], `add`, `e`, `rm`, `fx` | 10 lần/giây khi đang ở trong vùng |
| `chat` | `ch`, `from` {`uid`, `id`, `name`}, `text`, `ts`, `to` (friend), `zone`/`channel` (zone) | tin nhắn |
| `chat_history` | `ch` (`world` \| `zone`), `items` [chat] | sau `welcome` và khi vào vùng |
| `friend` | `event`: `online` \| `offline` \| `request` \| `accepted` \| `helped`, `user` {`uid`, `name`}, `reward` | bạn bè |
| `pong` | `c`, `st` | trả `ping` |
| `error` | `code`, `message_vi` | thao tác bị từ chối |
| `kicked` | `reason` (`elsewhere`, `timeout`, `flood`, `banned`, `admin`), `message_vi` | sắp bị ngắt |
| `notice` | `text`, `kind` (`announce` \| `maintenance`, chỉ khi quản trị viên gửi) | thông báo |
| `admin` | `ok`, `lines` [chuỗi] | trả lời lệnh `/admin` (giai đoạn 10) |
| `q` | `mid` (quái), `q` (câu hỏi như REST, `context: "combat"`), `first_meet` | **Vấn Đạo**: câu hỏi phá Mặc Thuẫn. Từ lúc gửi tới hạn trả lời nhân vật có **Hộ Thể** (không bị đánh, không di chuyển) |
| `q_end` | `sid`, `reason`: `broken` (người khác vừa phá khiên) \| `killed` \| `gone` \| `dead` | câu hỏi không cần trả lời nữa |
| `dead` | `respawn_in` | hết máu; sau đó server tự đưa về điểm hồi sinh (một gói `zone` mới) |
| `xp_lost` | `lost` | Tu Vi mất do chết |
| `loot` | `monster`, `stones`, `spirit_stones` (số dư mới), `items`, `equipment` [trang bị], `kills`, `xp`, `quests` | phần thưởng khi hạ quái (gửi cho mọi người đã đánh trúng) |
| `stats` | `realm`, `stage`, `stats`, `stage_up`, `hp`, `max_hp` | chỉ số đổi (lên tầng, đổi trang bị) |
| `skills` | `skills` [{`id`, `learned`, `level`, …}] | học Pháp Chữ / độ thuộc chữ đổi bậc pháp |
| `quest` | `event: "done"`, `quest` | một nhiệm vụ vừa đủ điều kiện |
| `act_fail` | `code`: `too_far` \| `no_target` | đòn đánh bị từ chối (đang hồi chiêu thì bỏ qua im lặng) |
| `cast` | `k`, `ok`, `code` (`not_learned`, `no_qi`, `cooldown`, `too_far`, `no_target`, `answering`), `ready_in` | kết quả dùng Pháp Chữ |

Câu trả lời của `q` gửi qua REST `POST /quiz/answer` như mọi câu hỏi khác; server chấm, rồi áp kết quả vào trận
đấu trong bộ nhớ ngay lập tức. Hết giờ mà không trả lời thì vòng tick tự chấm là sai.

### Snapshot

```json
{"t": "snap", "st": 1290.15, "ack": 41, "me": [452.0, 512.3, 1, 88.0, 120.0, 40.0, 60.0],
 "add": [{"id": "p9", "k": "p", "uid": 9, "n": "Lão Mai", "ap": {"hair_color": "#8E8E8E", "hair_style": "ngan", "body": "nam"},
          "realm": "pham_nhan", "x": 470.0, "y": 500.0, "f": 0, "m": 0, "hp": 100, "wp": "brush"},
         {"id": "m1_3", "k": "m", "type": "ink_slime", "n": "Mực Con", "rank": "normal",
          "x": 300.5, "y": 260.1, "f": 2, "m": 1, "hp": 100, "sh": 1, "alive": 1}],
 "e": [["p12", 520.25, 410.0, 3, 1, 100], ["m1_3", 301.0, 262.4, 2, 1, 64, 0, 1]],
 "rm": ["p4"],
 "fx": [{"k": "hit", "id": "m1_3", "v": 46, "c": 1, "by": "p7", "x": 301.0, "y": 262.4, "sh": 0}]}
```

- `me` = `[x, y, hướng, máu, máu tối đa, linh lực, linh lực tối đa, ong]`; `ong` (bản 4) là danh sách ong hộ vệ của
  mình `[id, loài, máu, máu tối đa, giây còn nghỉ trong tổ, id quái đang chích]`.
- Trong `e`, người chơi là `[id, x, y, hướng, đang đi, %máu, ong]` với `ong` = `[[loài, %máu, id quái đang chích hoặc "", đang nghỉ 0/1], …]`
  (cũng có trong `add` dưới khóa `bees`); quái là `[id, x, y, hướng, đang đi, %máu, khiên, còn sống]`.
- `fx` (chỉ có khi có chuyện xảy ra, lọc trong bán kính `event_radius`): `hit` (quái trúng đòn, `c` = chí mạng),
  `shield` (`on` 0 = vỡ, 1 = mọc lại), `atk` (vung vũ khí), `tele` (quái sắp đánh vào vòng `r` sau `d` giây),
  `mk` (người chơi trúng Mặc Kích; đòn thường của quái vào người chơi cũng là `hit`), `heal` (`q` = 1 nếu là linh lực), `skill` (`s` = pháp),
  `die`. Bản 4 thêm: `hit` có `b` = loài ong khi ong hộ vệ chích (`by` là chủ ong), `ink` (Ong Thư Pháp viết chữ,
  `s` = loài), `stun` (quái bị choáng `d` giây), `bee_down` (ong của `id` bị hạ, bay về tổ 60 giây), `heal` có `b` = 1
  khi ong hồi máu cho chủ.

### Ong hộ vệ (bản 4, giai đoạn 5)

Server mô phỏng ong như mọi thứ khác: client không gửi gì về ong, chỉ vẽ. Mỗi người mang theo các ong vai trò
`guard` (số lượng theo cảnh giới). Ong chỉ chích quái **đã mất Mặc Thuẫn** trong bán kính `guard.range` quanh chủ
(ưu tiên con chủ đang đánh); con quái bị chích quay sang đánh chủ, và phần thưởng khi hạ thuộc về chủ. Đòn của quái
khi rơi xuống cũng trúng những con ong đang chích nó; ong hết máu bay về tổ nghỉ 60 giây. Vị trí bay của ong
(đường cong quanh chủ hoặc quanh quái) do client tự vẽ (`client/engine/beeflock.py`).
- `me`: vị trí thật của chính mình sau khi server áp dụng đến gói `ack` (số chính xác, không làm tròn).
  Client đặt nhân vật về đó rồi **áp dụng lại** các gói chưa được xác nhận: vì cùng một hàm, kết quả trùng với
  vị trí đã dự đoán, nên bình thường không thấy giật.
- **Vùng quan tâm**: chỉ gửi những thứ nằm trong 3 × 3 ô lưới, mỗi ô 16 × 16 tile (256 px) quanh người chơi.
- **Chỉ gửi phần thay đổi**: `add` là thứ mới lọt vào tầm nhìn (đủ thông tin), `e` là `[id, x, y, hướng, đang đi]`
  của thứ đã biết mà vừa đổi, `rm` là thứ đã ra khỏi tầm nhìn hoặc rời vùng. Hướng: 0 xuống, 1 lên, 2 trái, 3 phải.
- Người chơi khác và quái được vẽ **trễ 100 ms**, nội suy giữa hai snapshot (`client/net/interpolation.py`).
- `id` người chơi là `p<user_id>`; quái `m<kênh>_<số>`.
- Quái chết vẫn nằm trong snapshot với `alive = 0` cho tới khi mọc lại (client làm mờ).

## Chat

- `world`: mọi người đang online; `zone`: những ai ở cùng kênh của vùng; `friend`: một người bạn đang online
  (theo đạo hiệu, không phân biệt hoa thường); `party`: chưa có tổ đội (`no_party`).
- Tối đa 200 ký tự, mỗi người một tin mỗi 2 giây (`chat_too_fast`, có `wait`), bộ lọc từ tục
  (`server/data/banned_words.txt`, từ bị thay bằng `***`), người bị cấm chat nhận `chat_banned`.
- Người bạn đã chặn (`POST /blocks`) không bao giờ đến được bạn, ở mọi kênh, kể cả lịch sử chat.

## Lưu dữ liệu

Vị trí và vùng của nhân vật ghi vào bảng `characters` theo lô: ngay khi đổi vùng, khi nhân vật rời thế giới
(sau 30 giây rớt mạng), mỗi 60 giây cho những ai đã di chuyển, và khi tắt máy chủ. Không có truy vấn DB nào
trong vòng tick.


## Giai đoạn 8

- Thực thể người chơi trong `snap.add` có thêm `"pet"`: loài Linh Thú đang đeo (`null` nếu không). Client vẽ con vật
  chạy theo sau người đó (hình lấy từ `looks` của `GET /pets`). Đổi pet thì máy chủ gửi lại `add` của người đó cho mọi
  người đang nhìn thấy. Phiên bản giao thức không đổi (trường mới, client cũ bỏ qua).
- Thông báo bạn bè mới: `{t: "friend", event: "gift", item, name_vi, qty, user{uid, name}}`.
- Kháng Mực Đan đang có hiệu lực làm Mặc Kích nhẹ đi ngay (máy chủ giữ hạn của bùa theo đồng hồ của vòng thế giới).

## Giai đoạn 9 — Tổ đội và bí cảnh (giao thức bản 5)

Client → server:

| `t` | Trường | Việc |
|---|---|---|
| `party` | `op`: `invite` (`name` = đạo hiệu) \| `accept` / `decline` (`uid` = người mời) \| `leave` \| `kick` (`uid`) \| `promote` (`uid`) | tổ đội, tối đa 5 người |
| `realm` | `op`: `enter` \| `queue` \| `unqueue` \| `leave`; `realm` (id bí cảnh định kỳ) hoặc `rift` (id khe nứt) | đội trưởng dẫn đội vào; người đi một mình vào hàng chờ; rời bí cảnh |
| `ract` | `obj` (tên đồ vật câu đố trên bản đồ, vd `tone_pillar3`) | dùng đồ vật câu đố đứng cạnh (đánh trụ thanh điệu) |
| `mark` | `x`, `y`, `i` (0–3) | ping cho đội, tối đa 1 lần/giây |
| `chat` | `ch: "party"` | kênh Tổ Đội |

Server → client:

- `{t: "party", event: "state", party{id, leader, max, members[{uid, name, realm, online, zone, hp, ghost, dead}]}}` khi có
  thay đổi (máu: tối đa 1 lần/giây); `event: "invite", from{uid, name, realm}`; `"invited", to{}`; `"declined", by{}`;
  `"left", reason: leave|kicked|disbanded|offline`.
- `{t: "party_xp", xp}`: Tu Vi chia từ đồng đội đánh quái gần đó.
- `{t: "notice", text}`: thông báo (bí cảnh sắp mở/đã mở, khe nứt vừa xuất hiện gần đây).
- `{t: "realm", event: ...}`:
  - `entering{realm, name_vi}`, `queued{key, realm, waiting}`, `unqueued` (ngoài bí cảnh);
  - `start{run{id, realm, name_vi, hanzi, left (giây), rooms[{kind, name_vi}], members[{uid, name, in}]}}`;
  - `room{i, n, kind, name_vi, hanzi, how_vi, left, phase, puzzle, mine}`: vào phòng (ngay sau `zone`). `puzzle` là phần
    mọi người thấy, `mine` là phần riêng của người nhận: `compose` → `{piece}`, `sentence` → `{tokens[{t, py}]}` (đã xáo),
    `mirror` → `{hanzi, pinyin}`, loại khác `null`;
  - `puzzle{i, puzzle}` và `mine{i, mine}` khi đổi. `puzzle` theo loại: `compose{meaning, layout, slots[], window,
    answer (sau khi giải)}`, `sentence{vi, n, k, done[{t, py}]}`, `tone{streak, need, round{hanzi, syllable, left}}`,
    `mirror{meaning, correct, need, left}`, `maze{carriers[uid], radius, lantern, self_radius, in_exit, need}`, `boss{boss,
    hp, shield, phase, hits, need}`; loại nào cũng có `kind, solved, fails`. Không bao giờ có đáp án trước khi giải;
  - `tone{ok, tone, pinyin, hanzi, by}` và `mirror{ok, by, hanzi, pinyin, meaning}` sau mỗi lượt; `hint{code, text_vi}`;
  - `cleared{i, flawless, next_in}`; `loot{loot{stage: roomN|chest, stones, spirit_stones, items[], equipment[], jade?,
    immortal_jade?, fast?, xp?}}` (chỉ phần của người nhận); `member_left{uid, name, reason}`; `revived{hp}`;
  - `end{result: won|failed|timeout|abandoned, time, flawless, puzzles, fast, fragments, exit_in}`; `left` khi đã ra ngoài.
- `{t: "dead", ghost: 1}`: gục trong bí cảnh, thành hồn ma (không về làng).
- Snapshot: `me` có thêm phần tử thứ 9 (cờ hồn ma); thực thể người chơi có `gh`; khe nứt là thực thể `{id, k: "r", x, y,
  realm, n, left}` trong vùng quan tâm như quái.
- Hiệu ứng mới trong `fx`: `mark{by, x, y, i}`, `pz{e: solve|fail|step|strike|open|wave, x, y, ...}`, `gshield{id, n, need,
  by}` (tiến độ khiên lớn của boss); `tele` có thêm `big: 1` cho Mặc Triều.
- Lỗi mới (`error.code`): `need_party`, `not_leader`, `party_full`, `already_in_party`, `player_offline`, `no_invite`,
  `party_self`, `cannot_enter`, `realm_closed`, `daily_limit`, `too_far`, `rift_gone`, `no_realm`, `in_party`,
  `not_in_realm`, `realm_error`.
- Rớt mạng trong bí cảnh: nhân vật chờ 60 giây. `welcome.zone = "bi_canh"` thì client vào lại bằng `join{via: "resume"}` và
  nhận lại `zone`, `realm start`, `realm room` (và `end` nếu đã xong). Vùng `bi_canh` không vào được bằng cổng hay `resume`
  khi nhân vật đã rời thế giới.

## Giai đoạn 10 — Lệnh quản trị (giao thức vẫn là bản 5)

Thêm, không đổi gì cũ (client cũ bỏ qua gói lạ), nên `PROTOCOL_VERSION` vẫn là 5.

- Tin `chat` có `text` bắt đầu bằng `/admin` (ở bất kỳ kênh nào) **không bao giờ được phát** cho ai. Máy chủ đọc cờ
  `is_admin` trong cơ sở dữ liệu (không tin cờ của phiên), chạy lệnh rồi trả `{t: "admin", ok, lines}` cho người gõ.
  Người không có quyền nhận `ok: false`. Lệnh của quản trị viên không bị giới hạn 2 giây/tin và vẫn chạy khi đang bị cấm chat.
- `/admin ban`: người bị khóa nhận `{t: "kicked", reason: "banned", message_vi}` rồi bị đóng với mã **4010**; kết nối lại
  nhận `error{code: "banned"}`. `/admin kick`: `reason: "admin"`, mã **4011**.
- `/admin mute`: người bị cấm nhận `notice` ngay; tin chat sau đó nhận `error{code: "chat_banned"}`.
- `/admin announce` và `/admin maintenance`: mọi người online nhận `{t: "notice", text, kind}`.
