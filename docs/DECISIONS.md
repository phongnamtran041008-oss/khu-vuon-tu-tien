# Quyết định thiết kế

Ghi lại những chỗ đặc tả để mở và phương án đã chọn. Mỗi mục: quyết định — lý do.

## Chung

- **Tên game là "Khu Vườn Tu Tiên"** (theo yêu cầu của người dùng, thay cho "Vườn Chữ: Tu Tiên Lộ" trong đặc tả). Phụ đề tiếng Trung 字园仙途 giữ từ đặc tả; đây là tên sáng tác, không dùng làm câu hỏi từ vựng.
- **Thời gian lưu dưới dạng UTC không kèm múi giờ** trong DB (SQLite không lưu múi giờ). Mốc reset hằng ngày tính theo UTC+7 (`app/clock.py`). Mọi thời gian lấy từ `clock.now()` để test có thể "tua" thời gian.
- **Từ vựng được đồng bộ vào bảng `words`** lúc server khởi động (nguồn sự thật vẫn là các file JSON) để các bảng khác có khóa ngoại tới từ.

## Dữ liệu từ vựng (mục 5)

- **CC-CEDICT lấy từ bản export gốc của MDBG đóng gói trong gói PyPI `pycccedict` khi không tải được mdbg.net.** Máy dựng dữ liệu lần đầu bị chặn truy cập mdbg.net; file trong gói là bản export nguyên vẹn (ngày 2023-11-07, đúng header và số mục của MDBG). Script luôn thử mdbg.net trước; chạy lại `build_wordlist.py --refresh` trên máy có mạng thường sẽ lấy bản mới nhất. Nguồn và mã băm ghi trong `tools/raw/SOURCES.md`.
- **Danh sách từ được chọn tay trong `tools/curation/words.json`, kèm âm đọc muốn dùng; còn pinyin, nghĩa tiếng Anh, lượng từ và cấu tạo chữ thì script lấy từ nguồn.** Lý do: danh sách HSK của repo gộp mọi âm đọc của CC-CEDICT (ví dụ 听 có cả *yǐn* "mỉm cười (cổ)"), nên cần người chỉ định âm nào được dạy; script kiểm tra âm đó có trong cả danh sách HSK lẫn CC-CEDICT, lệch là ghi vào `pinyin_conflicts.csv` và bỏ từ đó ra.
- **Tier 1 có 83 từ học + 6 chữ ẩn (好 吗 明 林 森 休) + 3 thành ngữ.** 苹果 (HSK 3) và 个 được thêm vào 80 từ gốc vì câu mẫu của đặc tả (我喜欢吃苹果) và hầu hết câu có số đếm cần chúng. 好 và 吗 là chữ HSK 1 nhưng thành chữ ẩn vì đặc tả cho chúng mở khóa qua phản ứng kề ô.
- **Chữ bắt buộc không có trong danh sách HSK (木) không có tần suất HSK**, nên được xếp như từ phổ biến nhất (Common), tránh việc chữ cơ bản cho phản ứng 林/森 lại thành Epic.
- **Câu ví dụ chỉ dùng từ có trong dữ liệu game** (không chỉ "trong phạm vi HSK 1–2"), để pinyin của câu được ghép từ pinyin đã kiểm chứng của từng từ và để câu nào cũng ghép được bằng quả chữ.
- **Chữ ghép bằng bộ thủ biến thể** (休 = 亻 + 木) được coi là khớp công thức 人 + 木 qua bảng biến thể bộ thủ trong `build_wordlist.py`. Cả 6 công thức ghép chữ hiện tại đều khớp cấu tạo thật trong makemeahanzi.
- **makemeahanzi `dictionary.txt` có giấy phép LGPL-3.0+** (đã kiểm tra file COPYING): game chỉ dùng các trường bộ thủ/cấu tạo, ghi công trong `CREDITS.md`.

## Gacha (mục 6.1, 13)

- **Pity ép "ít nhất" độ hiếm đó**: lần thứ 40 không có Epic+ sẽ ra Epic hoặc Legendary theo tỉ lệ tương đối 7:1; lần thứ 90 ra Legendary. Ra Legendary cũng reset bộ đếm Epic.
- **Đảm bảo của gói 10 lần** chỉ can thiệp ở lượt thứ 10 nếu 9 lượt trước toàn Common.
- **Tỉ lệ hiển thị gồm cả tỉ lệ gốc và tỉ lệ thực tế khi tính pity** (Legendary gốc 1%, thực tế ≈1,68%), cho minh bạch.
- **Giới hạn 15 hạt/ngày tính theo số lượt quay** (kể cả hạt trùng và lượt miễn phí). Gói 10 lần bị từ chối nếu không còn đủ 10 lượt, thay vì chỉ quay một phần.
- **Quay ra từ mới thì từ vào `collection` ngay (chưa "được giới thiệu")**; chỉ khi xem thẻ giới thiệu và bấm "Đã nhớ" thì từ mới tính là đã học và mới được dùng làm câu hỏi ở nơi khác.
- **Hạt trùng bán được 20 Linh Thạch, hoặc gieo lại** để trồng lại một chữ đã thu hoạch (lấy thêm quả cho Ghép Câu, ôn lại từ). Một chữ có thể mọc ở nhiều ô cùng lúc (cần cho 林 = 木 + 木 và 森 = 3 × 木); mỗi ô có lịch ôn riêng. (Giai đoạn 2 đổi từ "chỉ để bán": nếu không, sau khi thu hoạch hết vườn không còn gì để trồng, và không thể ghép 林/森.)
- **Chữ ẩn và thành ngữ không bao giờ làm đáp án nhiễu**, để không lộ trước phát hiện.
- **Quầy Trứng Ong và Linh Thú đã cấu hình** trong `balance/gacha.json` nhưng `enabled: false` cho tới giai đoạn 5 và 8.
- Người chơi mới nhận sẵn hạt 水 (hướng dẫn của Trúc Lão) và 1 lượt quay miễn phí mỗi ngày.

## SRS và sương mực (mục 6.2, 6.3)

- **`TIME_SCALE` chia mọi thời gian chờ SRS và tốc độ sương mực**, không chia thời hạn trả lời câu hỏi. Server từ chối `TIME_SCALE ≠ 1` ngoài môi trường dev.
- **Sương mực tính lười nhưng "phát lại" chính xác**: nếu người chơi vắng mặt lâu, mỗi lần cây lùi giai đoạn được tính tại đúng thời điểm nó xảy ra, nên tải vườn trễ cho cùng kết quả như theo dõi liên tục (có test).
- **Khi wither chạm 100**: cây lùi 1 giai đoạn (không thấp hơn Nảy mầm), wither đặt lại 60, cây đến hạn ôn ngay. Trả lời sai cũng có thể đẩy wither tới 100.
- **Cây Chín không bị sương mực** (không còn lịch ôn).
- **Một ô chỉ có một câu hỏi vườn đang mở**: hỏi lại trả về đúng câu cũ, không cho "đổi câu" đến khi gặp câu dễ.
- **Giai đoạn 4 hỏi Q5 (gõ pinyin) trước, Q7 nếu không tạo được**; nếu một chữ không tạo được dạng câu của giai đoạn (vd 吗 không có biến thể thanh cho Q3), dùng Q1/Q2 thay thế.

## Câu hỏi (mục 8.2)

- **Câu nghe (Q4) lấy âm qua `/quiz/{session}/audio`**, không gửi tên file theo mã từ, vì mã từ chính là đáp án. Không có file âm thì câu hiện pinyin thay (đúng đặc tả).
- **Đáp án nhiễu Q3 không bao giờ là một âm đọc khác có thật của chữ** (vd 只 có cả zhī và zhǐ), lấy từ toàn bộ âm đọc CC-CEDICT. Thanh nhẹ chỉ dùng làm đáp án nhiễu khi hết lựa chọn khác.
- **Q4 không có hai đáp án đồng âm** (他/它 đều là tā).
- **Q6 không bao giờ dùng 个 làm đáp án nhiễu** (lượng từ chung dùng được với rất nhiều danh từ), chỉ hỏi những danh từ có lượng từ riêng trong CC-CEDICT. Nếu từ được hỏi là một lượng từ (只, 条…), câu hỏi dùng một danh từ trong dữ liệu đi với nó.
- **Q7, Q9 có kèm nghĩa tiếng Việt của câu** để chỉ một đáp án hợp lý.
- **Q8 chỉ hỏi chữ hội ý / hình thanh** (theo trường `etymology` của makemeahanzi). Chữ tượng hình như 木, 日 có "cấu tạo" chỉ là nét vẽ (木 = 十 + 八) nên không hỏi.
- **Q11 bỏ qua chữ đa âm có thanh khác nhau** (vd 只), vì cả hai thanh đều đúng.
- **Câu chưa duyệt (`reviewed: false`) chỉ dùng khi `ALLOW_UNREVIEWED` bật** (mặc định bật ở dev, tắt ở production). Hiện mọi câu đều chưa duyệt, nên ở production Q7/Q9/Q10 sẽ không xuất hiện tới khi duyệt.
- **Hết giờ = sai**; giới hạn giờ trên server cộng 1,5 giây bù độ trễ. Câu vườn có hạn 10 phút.
- Mức cảnh giới tối thiểu của từng dạng câu đặt trong `balance/quiz.json` (`min_tier`).

## Tài khoản và chống gian lận (mục 15.4, 17)

- **Mã khôi phục 12 ký tự** chia nhóm `XXXX-XXXX-XXXX`, bỏ ký tự dễ nhầm (I, O, 0, 1); dùng xong thì cấp mã mới và đăng xuất mọi thiết bị.
- **Tên đăng nhập không phân biệt hoa thường** khi kiểm tra trùng và khi đăng nhập.
- **Giới hạn tần suất giữ trong RAM** của một tiến trình server (đúng với kiến trúc một tiến trình của đặc tả); nhiều tiến trình thì cần đổi sang lưu chung.
- **Cộng/trừ tiền dùng một câu `UPDATE … WHERE số dư + delta >= 0`** nên hai yêu cầu chi tiền chạy song song không thể làm số dư âm (có test).

## Giai đoạn 2 — client và vườn đầy đủ

- **Phông chữ giao diện là VT323** (SIL OFL, đủ dấu tiếng Việt). Fusion/Ark Pixel Font không tải được từ máy dựng (GitHub Releases bị chặn) và các font pixel khác trên Google Fonts thiếu dấu tiếng Việt. Ký tự VT323 không có (chữ Hán, một số dấu pinyin, mũi tên) tự chuyển sang **Noto Sans SC** trong cùng một dòng (`client/engine/text.py`).
- **Noto Sans SC được cắt gọn (subset)** còn ~1,9 MB: toàn bộ GB2312 (6.763 chữ thông dụng) + mọi ký tự trong dữ liệu game + chữ Latin/tiếng Việt/pinyin. `tools/fetch_assets.py --full` giữ bản đầy đủ 8 MB.
- **Hình vẽ**: nhân vật, Trúc Lão, ngựa, hạt giống, biểu tượng là lưới ký tự trong `client/art/sprites/`; ô đất, cây trồng, đạo cụ được vẽ bằng code (`client/art/build.py`) để đủ 6 giai đoạn × 4 độ hiếm × mức sương mực mà không cần hàng trăm lưới. Không dùng asset ngoài.
- **Chữ Hán của cây hiện trên một thẻ giấy cắm cạnh gốc** thay vì trên thân: ở độ phân giải 480×270, chữ 10 px trên nền giấy dễ đọc hơn chữ đè lên lá. Rê chuột vào ô sẽ hiện chữ to, pinyin, giai đoạn, thời gian ôn.
- **Vườn rộng tối đa 5×5**, mở đầu 3×3 như bản 1. Ô mới phải nằm cạnh ô đã có; giá khai hoang tăng dần (150, 200, 250…). Người chơi đi lại được trên các luống đất (giống game nông trại), bấm E hoặc bấm chuột vào ô.
- **Phản ứng kề ô**: 水 nhân thời gian chờ ôn ×0,8 (cộng dồn nếu kề nhiều cây), "lớn nhanh hơn 10%" của 火 cài là ×0,9. Lửa làm cháy gỗ được tung xúc xắc mỗi ngày (theo giờ UTC+7) với hạt giống cố định theo ô và ngày, nên tải lại vườn không bao giờ "tung lại" một ngày.
- **Giâm cành**: mua thêm một hạt của chữ đã học (60 Linh Thạch). Cần thiết vì 林 (木 + 木) và 森 (3 × 木) đòi nhiều cây cùng một chữ, và hạt trùng từ gacha chỉ đến khi đã có hết từ cùng độ hiếm.
- **Ghép câu không lộ đáp án**: người chơi chỉ thấy nghĩa tiếng Việt và số ô; chỉ những câu đã đủ quả mới hiện ra. Sai thứ tự thì không mất quả, Trúc Lão chỉ ra ô sai đầu tiên.
- **Sự cố thanh điệu được kiểm tra ở mọi ngữ cảnh** (không chỉ vườn), và câu Q3 ưu tiên cho xuất hiện đáp án nhiễu gây sự cố để chúng thật sự xảy ra. Trừ Linh Thạch tối đa 10 và không bao giờ âm.
- **Tên nhân vật**: 2–16 ký tự chữ/số (mọi bảng chữ, gồm tiếng Việt và chữ Hán), không trùng (không phân biệt hoa thường), qua bộ lọc từ tục. Bộ lọc phân biệt có dấu/không dấu để "Lớn" không bị nhầm với từ tục.
- **Hướng dẫn tân thủ do server lưu bước** (`users.flags.tutorial`), chỉ tiến không lùi, nên thoát giữa chừng vào lại không phải xem lại từ đầu.
- **Vị trí nhân vật trong động phủ** được lưu mỗi 60 giây và khi thoát game (REST). Thế giới chung ở giai đoạn 3 sẽ đi qua WebSocket.
- **Câu hỏi trong vườn không có đồng hồ đếm ngược** (chỉ hết hạn sau 10 phút như đặc tả); câu ở nơi khác hiện thanh thời gian.
- **Âm thanh hiệu ứng được tổng hợp bằng code** (sóng sin/vuông/nhiễu), không dùng file âm thanh có bản quyền. Phát âm từ vựng chỉ có khi chạy `tools/generate_audio.py` (cần mạng tới dịch vụ edge-tts, máy dựng không truy cập được).
- **Server làm tròn lên thời gian còn lại** (`seconds_until_due`), để client không bao giờ báo "đến giờ ôn" sớm hơn server.

## Giai đoạn 3 — thế giới online

- **Một tiến trình, trạng thái thế giới trong RAM** (`server/app/realtime/`): `World` giữ các phiên kết nối, mỗi
  vùng có danh sách kênh (`ChannelZone`), vòng tick 20 Hz chạy trong cùng event loop với FastAPI. Không dùng
  Redis (đúng mục 2). Muốn chạy nhiều tiến trình thì phải đổi kiến trúc, ghi rõ ở đây để không ai bật `--workers`.
- **Di chuyển theo kiểu "gửi phím, phát lại"**: client gửi các bước `(dx, dy, ms)` của từng khung hình; server áp
  dụng bằng cùng một hàm (`movement.py` có hai bản giống hệt nhau ở server và client, có test so sánh từng dòng
  code và 3.000 bước ngẫu nhiên). Nhờ vậy dự đoán ở client luôn khớp, chỉ bị kéo lại khi gian lận hoặc mạng quá
  tệ. Đây vẫn là "client chỉ gửi ý định" (mục 15.1), và đồng thời đúng mục 17 "server kiểm tra tốc độ và va chạm".
- **Chống hack tốc độ bằng ngân sách thời gian**: mỗi người tích thời gian thật đã trôi (tối đa 600 ms để chịu
  được mạng giật), gói di chuyển chỉ chạy khi đủ ngân sách; một gói tối đa 250 ms; hàng đợi quá 1,5 giây thì bỏ.
  Chạy nhanh gấp đôi là không thể; tích được tối đa ~0,6 giây đi "bù".
- **Gói đi qua cổng**: client gửi `join` ngay khi dự đoán mình đã đứng trong cổng; nếu server chưa chạy hết các
  bước cuối, nó chờ (tối đa 1 giây) thay vì từ chối. Vùng cổng trên bản đồ kéo dài ra ngoài mép bản đồ vài pixel để
  người chơi không thể "đi quá" cổng.
- **Snapshot**: 10 lần/giây, chỉ phần thay đổi so với lần trước gửi cho chính người đó; vùng quan tâm 3 × 3 ô lưới
  16 tile. Thực thể không đổi thì client tự thêm mẫu "đứng yên" để nội suy không bị kéo dài. Vị trí của chính mình
  gửi chính xác (không làm tròn) vì client phát lại từ đó.
- **Quái ở giai đoạn 3 chỉ đi lang thang** trong vùng của mình (`monster_area` trên bản đồ), có tên và hình riêng
  (Mực Con, Thanh Điệu Yêu), kênh không có người thì quái "ngủ". Bấm vào quái chỉ hiện lời nhắn: chiến đấu Vấn Đạo
  thuộc giai đoạn 4. `creatures/monsters.json` đã khai báo dạng câu hỏi của từng loài (mục 8.2).
- **Động phủ vẫn là cảnh riêng của từng người, chạy qua REST** như giai đoạn 2 (không có trong WebSocket). Thăm động
  phủ của bạn là **xem**: người thăm đi lại trong bản sao động phủ của bạn và tưới giúp, nhưng chủ nhà không thấy
  người thăm đi lại theo thời gian thực (chỉ nhận thông báo "đã tưới giúp"). Thăm từ trong làng thì nhân vật ở làng
  đứng yên tại chỗ cho đến khi quay lại.
- **Tưới giúp** chỉ hỏi chữ mà **người thăm đã học** (nguyên tắc "câu hỏi luôn công bằng"); hỏi Q1/Q2/Q3. Mỗi lượt
  mở câu hỏi đều tính vào giới hạn 5 lượt/ngày (kể cả trả lời sai), để không thể bỏ câu khó rồi chờ câu dễ. Đúng
  thì cả hai +10 Linh Thạch qua `inventory` (có `audit_log`); cây của chủ vườn **không** lớn thêm, vì giai đoạn cây
  chỉ đổi khi chính chủ ôn (mục 8.3). Xem vườn không bao giờ ghi gì vào vườn của chủ (sương mực tính trên bản sao).
- **Bạn bè lưu hai dòng** khi đã đồng ý (A→B, B→A); lời mời là một dòng `pending`. Hai người cùng mời nhau thì
  thành bạn luôn. Chặn ai thì hủy kết bạn, chặn lời mời, và lọc tin nhắn của người đó ở mọi kênh (kể cả lịch sử).
- **Chat bạn bè gửi theo đạo hiệu** (`/w Tên nội dung`, tên có dấu cách được nhận ra bằng cách so với danh sách bạn).
  Kênh Tổ Đội trả lời "chưa ở trong tổ đội nào" cho tới khi có tổ đội (giai đoạn 9).
- **Bộ lọc chat**: dùng chung bộ lọc tên nhân vật; từ cấm bị thay bằng `***`, cụm từ cấm nhiều chữ thì cả tin thành
  `***`. Danh sách chỉnh được trong `server/data/banned_words.txt`.
- **Enter để chat** (đặc tả 7.2), nên trong động phủ Enter không còn là phím tương tác: tương tác là E (hoặc bấm chuột).
  Khi đang gõ chat, các phím tắt (Tab, G, B, C, P) và di chuyển bị tắt.
- **Ngày/đêm**: một ngày game = 2 giờ thật theo đồng hồ server (UTC); trời tối dần từ 18 giờ game và sáng lại lúc 6 giờ.
  Ở giai đoạn này chỉ là hình ảnh; cá, quái, 明 phát sáng dùng tới sau.
- **Cảnh giới chặn vùng** theo `recommended_realm` trong `data/zones.json` với biên 1 bậc (Phàm Nhân vào được Rừng
  Mực Loang dành cho Luyện Khí, nhưng chưa vào được nơi dành cho Trúc Cơ).
- **Lưu vị trí theo lô** (mục 15.2, 19): ghi ngay khi đổi vùng và khi nhân vật rời thế giới, mỗi 60 giây cho người
  đã di chuyển, và khi tắt máy chủ; tất cả trong một câu `UPDATE` nhiều dòng. Lưu từ REST của động phủ bị bỏ qua khi
  nhân vật đang ở thế giới (tránh lần lưu đến muộn kéo nhân vật về động phủ).
- **Đăng nhập lại khi đang ở ngoài thế giới** thì quay lại đúng vùng, đúng chỗ (`zone_id` của nhân vật). Vị trí lưu
  bị chặn (ví dụ bản đồ đã đổi) thì xuất hiện ở điểm `spawn` của vùng.
- **bcrypt chạy trên luồng phụ** (`auth.ahash/acheck`): mỗi lần băm ~70 ms; chạy thẳng trong event loop sẽ làm tick trễ
  mỗi khi có người đăng nhập. **Sau khi khởi động gọi `gc.freeze()`**: dữ liệu từ vựng và bản đồ sống suốt đời tiến trình,
  không cần bộ gom rác quét lại (một lượt quét đầy đủ từng làm tick trễ ~60 ms khi nhiều người vào cùng lúc).
  Bản đồ được nạp sẵn lúc khởi động vì lý do tương tự.
- **`ACCOUNTS_PER_IP`** (biến môi trường) cho phép tăng giới hạn 5 tài khoản mới/IP/ngày để chạy `tools/load_bots.py`.
  Khi chạy sau Cloudflare Tunnel, mọi yêu cầu đến từ `127.0.0.1`, nên `chay_server_choi_chung.bat` bật `--proxy-headers`
  để giới hạn tính theo IP thật của từng người.
- **`/server/stats` công khai** nhưng chỉ có số đếm và thời gian tick, không có thông tin cá nhân.

## Giai đoạn 4 — chiến đấu Vấn Đạo, tu luyện, Thiên Kiếp

- **Câu trả lời chiến đấu đi qua REST `/quiz/answer`** như mọi câu hỏi khác (một đường chấm duy nhất, đáp án không bao
  giờ rời server), rồi handler `combat` áp kết quả vào trận đấu trong bộ nhớ ngay. Câu hỏi được tạo bằng tác vụ DB
  chạy nền khi đòn đầu tiên trúng quái; tới lúc câu tới, nhân vật được **Hộ Thể** cho tới hạn trả lời (không bị đánh,
  input di chuyển bị bỏ). Hết giờ thì vòng tick chấm sai, nên treo máy giữa trận không né được Mặc Kích.
- **Mặc Thuẫn không bao giờ để quái chết**: còn khiên thì mỗi đòn chỉ 1 sát thương và máu bị giữ ≥ 1. Một người phá khiên
  là khiên vỡ cho mọi người đang đánh con đó (câu hỏi của họ bị hủy bằng `q_end: broken`).
- **Quái tinh anh mọc lại khiên ở ngưỡng** (Mặc Hồ: 50%): máu bị chặn đúng ở ngưỡng kể cả khi một đòn lớn lẽ ra
  vượt qua, nên không thể "một đòn xuyên ngưỡng" bỏ qua câu hỏi thứ hai.
- **Mặc Kích = Sinh Lực tối đa × 10/15/20% (thường/tinh anh/boss) × (1 − Kháng Mực)**, Kháng Mực tối đa 60%. Mặc Kích
  bỏ qua Hộ Thể (đó là cái giá của câu sai) nhưng vẫn bị Sơn Chữ Quyết giảm.
- **Sơn Chữ Quyết (山) là "giữ thế" giảm 50% sát thương trong 5 giây**, không dựng tường như gợi ý trong đặc tả: tường
  cần va chạm động đồng bộ cho mọi client và có thể dùng để chặn người khác ở cổng. Để sau nếu cần.
- **Bậc Pháp Chữ theo độ thuộc chữ** (50/70/90/100 → bậc 1–4); quên chữ thì pháp yếu đi. Học pháp bằng bí kíp rơi từ quái
  và cần chữ đó ≥ 50%.
- **Tầng trong một cảnh giới tự lên** khi đủ Tu Vi; chỉ **bước sang cảnh giới mới** mới cần đan dược và Thiên Kiếp
  (Tu Vi dừng ở mức đầy, gọi là "bình cảnh"). Tu Vi đến từ mọi câu đúng theo ngữ cảnh (`xp_per_correct`: vườn 10,
  đánh quái 6, tưới giúp 4, luyện tập 2, đả tọa 15, câu Thiên Kiếp 0), thu hoạch 15, nhiệm vụ và hạ quái.
- **Thiên Kiếp lưu trong bảng `tribulation_runs`**: 20 chữ chọn sẵn từ toàn bộ chữ đã học, thoát giữa chừng thì tiếp tục
  đúng câu đang dở (câu quá hạn tính sai). Qua thì dùng mất đan dược; trượt thì giữ đan, mất 10% Tu Vi của tầng, chờ
  30 phút (chia `TIME_SCALE`).
- **Chết mất Tu Vi bằng 5% lượng cần cho tầng hiện tại**, không bao giờ tụt tầng; hồi sinh ở Trúc Lâm Thôn sau 3 giây.
- **Máu/linh lực sống trong thế giới**, ghi vào DB theo lô cùng vị trí. Về động phủ thì hồi đầy, ở vùng an toàn hồi
  nhanh gấp 3. **Đan dược chỉ dùng được trong thế giới chung** (máu ở động phủ luôn đầy), thời gian chờ 15 giây.
- **Trang bị là bản thể riêng** (`equipment_instances`: độ hiếm, cấp cường hóa) thay vì chồng trong túi; vật phẩm
  thường vẫn là số lượng. Cường hóa thất bại chỉ mất nguyên liệu + Linh Thạch, không tụt cấp, không vỡ đồ.
- **Tiêu hao vật phẩm lấy cả bản khóa (bound) lẫn bản thường** (`inventory.consume_item`, ưu tiên bản khóa vì bản đó
  không giao dịch được), để đan dược nhận từ nhiệm vụ dùng được như đan mua.
- **Nói chuyện với NPC cho nhiệm vụ** (`/quests/talk`) kiểm tra khoảng cách trên server bằng vị trí trong thế giới, nên
  không thể hoàn thành nhiệm vụ "gặp Trúc Lão" từ xa.
- **`BALANCE_PROFILE=dev`** đè `server/data/balance/dev/*.json` lên số liệu thật (gộp sâu) để thử nhanh từ Phàm Nhân lên
  Trúc Cơ; bị từ chối khi `ENV` không phải `dev`. Số liệu thật không đổi.
- **Giao thức WebSocket lên bản 3**: `me` và trạng thái thực thể có thêm máu/khiên, nên game bản cũ được báo "cần
  cập nhật" thay vì vẽ sai.
- **Màu độ hiếm Phàm/Thiên đậm hơn** (`#7D7468`, `#C99A3A`) để đọc được trên nền giấy; màu trong
  `data/items/equipment.json`.

## Giai đoạn 5 — Linh Phong (ong linh)

- **18 loài ong, mỗi loài gắn một chữ trong dữ liệu từ vựng đã kiểm chứng** (`tools/curation/bees.json`). Tên Hán là
  chữ đó + 蜂. `tools/build_bees.py` lấy pinyin của chữ từ danh sách từ, pinyin của 蜂 (fēng) từ CC-CEDICT, rồi tra
  cả cụm trong CC-CEDICT: chỉ 黄蜂 là từ có thật (nghĩa "ong vò vẽ", game ghi rõ điều đó), các tên khác đánh dấu
  `real_word: false` và hiện "(tên sáng tác)". Tên ong không bao giờ được dùng làm câu hỏi. Không dùng chữ ẩn
  (林, 明…) để khỏi lộ phát hiện. Đủ 5 độ hiếm: Phàm 5, Linh 5, Huyền 4, Địa 2, Thiên 2.
- **Thụ phấn chỉ cắt tối đa 25% thời gian chờ ôn — và chỉ một lần cho mỗi lần cây được thụ phấn.** Lịch lặp lại ngắt
  quãng (10 phút / 1 / 3 / 7 ngày) là thứ làm người chơi nhớ lâu; nếu ong rút ngắn nhiều hơn, người chơi có thể "mua"
  lịch ôn dày đặc bằng ong và tưởng là đã thuộc. 25% đủ để thấy ong có ích (cây 3 ngày thành ~2,25 ngày) mà khoảng
  cách giữa các lần ôn vẫn tăng dần. Giới hạn này là hằng số trong code (`MAX_REVIEW_CUT`), file cân bằng có ghi số
  lớn hơn thì vẫn bị chặn ở 25% (có test). Cắt vào **lượt chờ đang chạy** lúc thanh phấn đầy (tính trên độ dài lượt
  chờ đầy đủ, kể cả hiệu ứng kề ô 水/火), không bao giờ sớm hơn lúc đầy; nếu cây đang đến hạn ôn thì để dành cho lượt
  chờ kế tiếp sau câu trả lời đúng. Câu sai (chờ 5 phút ôn lại) không được cắt.
- **Thụ phấn không bao giờ đổi giai đoạn cây.** Chỉ thanh `pollen` và cờ `pollinated` thay đổi; giai đoạn chỉ đổi
  trong `srs.apply_correct/apply_wrong` (có test chạy ong nhiều ngày liền). Cây dưới Ra hoa (giai đoạn < 3) không nhận phấn.
- **Phấn hoa tính lười, phát lại theo sự kiện**: từ lần tính trước tới nay, mỗi ong chia đều sức của nó cho các cây
  đang ra hoa chưa đầy; khi một cây đầy, thời điểm đầy được tính chính xác rồi phần sức đó chia lại cho các cây còn
  lại. Ong cùng hệ với chính cây hoặc một cây kề bên (水 雨 海… là Thủy; 火 日 红… là Hỏa — bảng trong
  `balance/bees.json`) thụ phấn nhanh ×1,5. Phấn được tính tới hiện tại trước mọi thao tác có thể đổi tập cây đang
  ra hoa (tải vườn, trả lời ôn, thu hoạch, đổi vai trò ong). Một cây lùi giai đoạn vì sương mực khi vắng mặt vẫn
  được tính như đang ra hoa trong khoảng vắng đó (sai số nhỏ, chấp nhận được).
- **Mật và phấn chạy theo `TIME_SCALE`** giống lịch ôn, để thử nhanh trọn vòng nuôi ong.
- **Mỗi con ong luôn chiếm một ô tổ, kể cả khi đang thụ phấn hay hộ vệ** (đặc tả: "mỗi ong chiếm một ô"), nên số ô là
  giới hạn số ong. 30 ô xếp 6 × 5 lục giác (hàng lẻ lệch nửa ô), mở dần từ giữa ra; ô 11+, 16+, 21+, 26+ cần 3/6/9/12
  loài trong Ong Phổ. Đồng hệ cộng hưởng: +5% mỗi ong cùng hệ ở ô kề, tối đa 3 (+15%), áp cho mật, phấn và chỉ số hộ vệ.
- **Trứng ong là vật phẩm trong túi** (gacha, nhiệm vụ, mốc Ong Phổ), loài chỉ quyết định lúc **nở** ở tổ (cùng độ
  hiếm, loài chưa có nặng ×2) để có khoảnh khắc mở trứng. Người chơi nào cũng nhận một Trứng Ong Phàm (khóa) ở lần
  mở tổ đầu tiên, kèm chuỗi nhiệm vụ "Linh Phong" (nở → cho ăn → thụ phấn → hộ vệ → Ong Phổ 4 loài). Chuỗi nhiệm vụ mới
  tự mở cho cả tài khoản cũ (`quests.on_event` gọi `ensure` trước).
- **Gacha Trứng Ong**: 300 Linh Thạch hoặc 5 Tiên Ngọc một lượt, 2.700 / 45 cho 10 lượt (10 lượt chắc chắn có ít nhất
  một trứng Linh). Bảo hiểm Huyền ở lượt 30, Thiên ở lượt 90. Không tính vào giới hạn 15 hạt/ngày; lượt miễn phí hằng
  ngày chỉ dành cho Hạt Chữ.
- **Ong lên cấp** bằng cho ăn (Linh Mật 25, quả chữ 12–60 theo độ hiếm, Linh Quả 90, cá nhỏ 35 kinh nghiệm), thụ phấn
  (12 mỗi cây đầy) và hạ quái (8). Cấp tối đa 20, mỗi cấp +8% chỉ số. Món thích: kinh nghiệm ×2, thân thiết +8 (thường
  +2); thân thiết 100 = +10%. Lần đầu cho đúng món thích thì món đó hiện trong Ong Phổ; trước đó chỉ có một câu gợi ý.
- **Học chữ làm ong mạnh hơn**: mỗi loài gắn một chữ, độ thuộc chữ đó cộng tối đa +10% (100%). Đây là cách "Chữ Đạo"
  chạm tới ong mà không biến ong thành đường tắt bỏ qua câu hỏi.
- **Số ong hộ vệ theo cảnh giới** (Phàm Nhân 0, Luyện Khí 2, Trúc Cơ 3, Kim Đan 4, Nguyên Anh 5) đặt trong
  `balance/bees.json` và kiểm tra ở server cả lúc gán vai trò lẫn lúc đưa ong ra thế giới.
- **Ong hộ vệ không bao giờ gây sát thương cho quái còn Mặc Thuẫn**, kể cả lửa đang cháy (`guard.bee_hurt` từ chối);
  với quái tinh anh, đòn ong cũng dừng ở ngưỡng khiên mọc lại như đòn người. Ong chích làm quái quay sang đánh chủ
  (chủ được tính là đã giao chiến), nên phần thưởng khi hạ quái luôn thuộc về chủ. Đòn báo trước của quái khi rơi xuống
  trúng mọi ong đang chích nó (50% công của quái); ong hết máu về tổ nghỉ 60 giây rồi quay lại đầy máu.
- **Vị trí ong không đi qua mạng**: snapshot chỉ mang loài, %máu, mục tiêu và trạng thái nghỉ; client tự vẽ đường bay
  cong quanh chủ hoặc quanh quái (`client/engine/beeflock.py`). Giao thức lên **bản 4**.
- **Kỹ năng bị động**: đốt (Hỏa Diệm, Kim Ô), làm chậm (Thảo, Vũ, Thủy Linh, Băng Tâm, Hải Triều), choáng (Sơn Thạch,
  Lôi Vân — quái đứng yên, đòn đang báo trước bị hủy), hồi máu cho chủ (Dược Sư, Nguyệt Quang), nhặt đồ rơi (Ngọc Bích:
  +25% Linh Thạch và tỉ lệ rơi đồ của quái nó đã chích), chích nhanh (Phong Hành), nét bút ×3 mỗi 4 cú (Thư Pháp).
- **Tổ ong nâng cấp 5 cấp** bằng Linh Thạch + Sáp Ong (ong làm mật tiết ra, 0,1 sáp mỗi mật) + Gỗ Linh Mộc (rơi từ quái
  ở Rừng Mực Loang). Mỗi cấp tăng sức chứa và tốc độ làm mật và mở một món trang trí (đèn lồng, chậu sen, chuông gió,
  cờ phướn) đặt quanh tổ trong động phủ; bật/tắt được.
- **Làng mua lại Linh Mật, Sáp Ong, Gỗ, Linh Quả, Mực Tinh** với giá thấp (`sell_price` trong `items/materials.json`)
  để mật có chỗ dùng trước khi có luyện đan (giai đoạn 8). Giá cố ý thấp; dòng tiền tổng thể sẽ cân lại ở giai đoạn 8.
- **Thả ong** (giải phóng ô) trả lại Sáp Ong theo độ hiếm, có hỏi xác nhận.
- **Cá Nhỏ** đã có trong dữ liệu (ong ăn được) nhưng chưa có nguồn cho tới giai đoạn 6 (câu cá).
- **Khi thăm động phủ bạn bè** thấy ong của bạn bay quanh tổ và vườn (trừ ong hộ vệ, vì chúng đi theo chủ).

## Giai đoạn 6 — Câu cá

- **Câu cá đi qua REST, không qua WebSocket** (đặc tả 16 gợi ý WebSocket). Cả ao động phủ (vốn chạy REST) lẫn hồ ngoài
  thế giới dùng chung một đường; với hồ, máy chủ đọc **vị trí thật trong thế giới** của nhân vật (như `/quests/talk`)
  để biết có đứng sát nước không, nên không câu từ xa được. Ao động phủ chỉ câu được khi nhân vật không đứng ngoài thế
  giới. Lượt câu đang dở nằm trong RAM (một tiến trình, như thế giới chung); khởi động lại máy chủ thì mất lượt đó
  (mồi đã dùng không trả lại).
- **Máy chủ quyết định mọi thứ**: thời điểm cá cắn (lúc quăng), loài và kích thước (lúc giật, không gửi cho client tới
  khi câu được). Trò kéo cá là một mô phỏng tất định (`fishing_sim.py`, hai bản giống hệt từng byte ở server và client,
  có test): client gửi **các bước mà nút đổi trạng thái**, máy chủ chạy lại đúng trò đó bằng hạt giống của nó để biết câu
  được hay không. Kết quả cần N bước thì phải có ít nhất ~85% × N × 20 ms thời gian thật trôi qua (`too_fast`). Chỉ dùng
  cộng trừ nhân chia và `random.Random.random()` nên hai bên tính ra số thực giống hệt nhau. Một client tự viết có thể
  chơi "hoàn hảo" (vì biết hạt giống) — chấp nhận được: đó vẫn là kỹ năng kéo cá, không đổi được loài, kích thước hay tỉ
  lệ, và vẫn phải chờ đủ thời gian.
- **Trò kéo cá**: thanh dọc, cá (vùng xanh) bơi lên xuống theo những đoạn ngẫu nhiên, móc câu lên khi giữ nút và chìm khi
  nhả. "Dây căng quá lâu thì đứt" = giữ nút trong lúc móc đã vượt lên trên con cá làm thanh Dây đầy dần. Cá hiếm hơn:
  vùng xanh hẹp hơn, bơi nhanh hơn, khỏe hơn (cá to cũng khỏe hơn). Độ khó chỉnh bằng một bot có độ trễ phản xạ 180 ms:
  với Cần Trúc Thô bắt được ~99% cá Phàm, ~87% cá Linh, ~50% cá Huyền; Cần Long Cốt thì ~70% cá Địa.
- **Tỉ lệ cá**: trọng số độ hiếm 70 / 21 / 6,5 / 2 / 0,5; độ hiếm r được nhân `1 + may_mắn × hệ_số_r` (hệ số 0 / 0,6 /
  1,2 / 1,8 / 2,5), may mắn = cần + mồi. Độ hiếm không có loài nào cắn được (sai nơi, sai giờ, sai mồi) bị bỏ rồi chia lại.
  Trong một độ hiếm các loài chia đều, loài được mồi "dụ" tính gấp đôi. Công thức này (`rarity_odds`, `species_odds`)
  được test so với 100.000 lần quay cho 5 tổ hợp cần/mồi/nơi/giờ (sai số < 1%).
- **Câu không mồi được** nhưng cắn chậm ×1,5 và chỉ ra cá Phàm/Linh, để người mới hết tiền vẫn câu được. Mồi trừ lúc quăng.
  Mồi Mực chỉ dụ cá có nhãn "mực" và bị từ chối ban ngày (đặc tả: "chỉ câu được cá Mực ở đêm"); vì vậy có cá Mực ở nhiều
  độ hiếm (Chạch, Lóc, Mực Nang, Nghiên Linh Ngư) để Mồi Mực không thành đường tắt ra cá Huyền.
- **Câu hỏi khi cá cắn**: dạng câu theo độ hiếm (Linh: Q1/Q2/Q11; Huyền: Q3/Q4/Q2; Địa: Q5/Q6/Q7/Q3; Thiên: Q5/Q8/Q7/
  Q6/Q3), lọc theo `min_tier` của cảnh giới như chiến đấu, chữ chọn bằng `selection.pick_word` (ưu tiên chữ cần ôn).
  Đúng: vùng xanh ×1,3; sai: ×0,65; **không bao giờ mất máu**. Cá Thiên: đúng câu 1 thì có câu 2; sai bất kỳ câu nào là
  vào trò kéo với vùng hẹp. Chưa học chữ nào thì không hỏi (vùng bình thường). Câu đúng +6 Tu Vi, độ thuộc ±2 như mọi
  nơi ngoài vườn.
- **Tên cá**: 28 loài có thật lấy tên Hán, pinyin và nghĩa tiếng Anh từ CC-CEDICT (`tools/build_fish.py`); 鲲 (Côn) là từ
  có thật trong CC-CEDICT nên giữ nguyên, chỉ đánh dấu `mythical`. Hai tên sáng tác (化龙鲤, 砚灵鱼) đánh dấu `fictional`,
  từng âm được kiểm tra là một cách đọc của chữ đó. Tên cá không nằm trong danh sách từ nên không bao giờ thành câu hỏi.
  娃娃鱼 thật ra là kỳ giông khổng lồ, 黄鳝 là lươn — game ghi rõ trong mô tả.
- **Ngày/đêm của cá** dùng đúng đồng hồ thế giới (1 ngày game = 2 giờ thật, đêm từ 18 giờ tới 6 giờ). **Mưa** theo từng
  vùng, mỗi 30 phút thật tung một lần bằng hàm băm (vùng, chu kỳ): ai cũng thấy giống nhau, không cần lưu gì
  (Hồ Nghiên Mực mưa 35% thời gian, làng và động phủ 25%). Client hỏi `/world/weather` mỗi phút để vẽ mưa.
- **Cần câu là vật phẩm trong túi** (khóa, không giao dịch), cấp nâng cấp lưu trong `users.flags.fishing` cùng cần/mồi
  đang dùng. Nâng cấp ở Lò Rèn phải đứng cạnh Thợ Rèn, mua bán ở Ngư Ông phải đứng cạnh Ngư Ông (kiểm tra trên máy chủ).
  Cần Thiên Tơ chưa có cách lấy cho tới khi có nguyên liệu bí cảnh (giai đoạn 9).
- **Vảy Linh Ngư** (1/2/3/5 theo độ hiếm Linh→Thiên) là nguyên liệu mua cần cao cấp và nâng cấp cần, để câu cá hiếm
  dẫn tới cần tốt hơn mà không phải chỉ cày Linh Thạch.
- **Cá Nhỏ có nguồn**: cá Phàm nhỏ hơn 25% khoảng kích thước của loài thành `ca_nho` (ong ăn được) thay cho con cá,
  nhưng vẫn tính vào Ngư Phổ. Cá câu được là vật phẩm `fish_<loài>`, làng mua theo giá loài (Phàm 6–14, Thiên 1000–1500);
  dòng tiền sẽ cân lại ở giai đoạn 8 cùng luyện đan.
- **Ngư Phổ** dùng bảng `fish_catches` có sẵn từ migration đầu (số con, con to nhất, lần đầu), không cần migration mới.
  Mốc 5/10/20/30 loài: 200 Linh Thạch, 3/6/15 Tiên Ngọc (đặc tả 12.1: Tiên Ngọc từ mốc thư viện). **Kỷ lục**: 3 con to nhất
  mỗi loài trên toàn máy chủ (một dòng mỗi người), tính từ cùng bảng.
- **Hồ Nghiên Mực** nối với **cổng Tây** của Trúc Lâm Thôn (đặc tả không nói hồ nằm đâu; cổng Tây đang trống), cảnh giới
  khuyến nghị Luyện Khí như Rừng Mực Loang (Phàm Nhân vào được nhờ biên 1 bậc). Ngư Ông đứng ở chân bến gỗ; Mặc Quái chỉ
  đi lang thang ở bờ tây, bờ bắc và góc đông nam, xa bến. Ao trong làng giờ cũng câu được (cá ao như ở động phủ).
- **`BALANCE_PROFILE=dev`** thêm `dev/fishing.json`: cá cắn sau 1,5–3 giây và cá hiếm cắn nhiều hơn hẳn, để thử nhanh.
- **Chuỗi nhiệm vụ "Ngư Ông"** (chào Ngư Ông → câu 3 con → Ngư Phổ 5 loài) tự mở cho cả tài khoản cũ như chuỗi Linh Phong;
  bước "5 loài" tính cả những loài đã câu trước khi bước đó mở.
- **Test client dừng máy chủ thử bằng Ctrl+Break trên Windows** (trước đây `terminate()` giết tiến trình ngay nên máy chủ
  không kịp lưu vị trí, làm `test_reconnect` lỗi trên Windows dù game đúng). `test_tests_leave_no_settings_in_game_folder`
  giờ kiểm tra test **không đổi** `client/config.json`/`session.json` thay vì đòi hai file không tồn tại (máy người chơi
  thật có `session.json`).
- `tools/gen_maps.py` ghi bản đồ với xuống dòng LF trên mọi hệ điều hành (trước đây Windows ghi CRLF làm file đổi dù
  nội dung như cũ).

## Giai đoạn 7 — Ải Thủ Vườn và Tàng Thư Các

- **Trò thủ vườn chạy ở client, máy chủ chạy lại nhật ký** (đặc tả 16, 17) bằng `td_sim.py` — một file giống hệt từng
  byte ở `server/app/systems/` và `client/engine/` (có test), cùng kiểu với `fishing_sim.py`: chỉ cộng trừ nhân chia và
  `random.Random`, nên hai bên ra cùng số thực. Client ghi mọi hành động thành sự kiện `{s: bước, k: loại, ...}`; khi ải
  kết thúc nó gửi cả nhật ký và kết quả nó thấy (`result, core_hp, wave, steps`). Máy chủ chạy lại; nhật ký bị từ chối nếu
  có sự kiện trái luật (`bad_log`: cây không mang theo, trồng sai ô, thiếu Linh Khí, đi ngược thời gian, câu hỏi không có,
  dùng hai lần, sai loại, Tụ Khí chưa hồi...), nếu kết quả chơi lại khác kết quả gửi lên (`log_mismatch`), hoặc nếu số bước
  cần nhiều thời gian thật hơn đã trôi (`too_fast`, chia cho tốc độ tua tối đa ×2). Phép chạy lại nằm trên luồng phụ
  (`asyncio.to_thread`) để không làm trễ vòng tick thế giới.
- **Kết quả câu hỏi lấy từ máy chủ, không từ client.** Mỗi câu hỏi trong ải được tạo qua `/td/question` (ghi vào lượt
  chơi trong RAM) và chấm qua `/quiz/answer` như mọi câu khác; phép chạy lại dùng đúng/sai mà máy chủ đã chấm. Mọi câu
  máy chủ đã tạo trong lượt phải xuất hiện đúng một lần trong nhật ký (câu chưa trả lời tính là sai), nên không thể giấu
  một câu Tụ Khí trả lời sai để khỏi mất Linh Khí. Một client tự viết vẫn có thể chơi "hoàn hảo" (nó biết hạt giống và
  luật) — chấp nhận được: đó vẫn là cách đặt cây, không đổi được câu trả lời, phần thưởng hay thời gian.
- **Lượt đang chơi lưu trong bảng `td_runs`** (migration 0005) cùng nhật ký của nó. Client gửi phần nhật ký mới qua
  **`/td/event`** (đặc tả 16) sau mỗi câu hỏi, mỗi đợt, và ít nhất 2 giây một lần; thoát game hay khởi động lại máy chủ giữa
  ải thì lần sau bản đồ ải hiện "Lượt dở… Chơi tiếp": `/td/resume` trả lại tham số, nhật ký đã lưu và kết quả các câu hỏi,
  client dựng lại đúng trận bằng `td_sim.replay(..., finish=False)` (dừng ngay sau sự kiện cuối) rồi chơi tiếp.
  **Đoạn đã lưu không bao giờ sửa hay xóa được**: gửi lại một đoạn đã lưu phải giống hệt (`log_conflict`), không được bỏ
  cách (`log_gap`), và nhật ký gửi ở `/td/finish` phải bắt đầu bằng đúng đoạn đã lưu — nên tắt game không giúp "đi lại"
  một nước đã lưu. Chỉ những thao tác sau lần lưu cuối (tối đa ~2 giây) là mất khi tắt ngang. Câu hỏi được hỏi sau lần
  lưu cuối thì chưa từng được áp dụng: khi chơi tiếp chúng bị bỏ (một câu Tụ Khí trả lời sai rồi tắt game ngay trước khi
  lưu sẽ không bị trừ 10 Linh Khí — chấp nhận được). Lượt quá 3 giờ bị xóa.
- **Thời gian chỉ trôi trong đợt quái, và dừng khi thẻ câu hỏi đang mở.** Giữa các đợt người chơi bày cây thong thả;
  câu hỏi là để học, không phải để đua với quái. Linh Khí tự tăng theo thời gian trong đợt. Hồi chiêu Tụ Khí 10 giây tính
  theo thời gian trong ải. Trước mỗi đợt (cả đợt đầu) tự hiện 3 câu Linh Khí Vấn Đạo; sai không mất gì. Tụ Khí đúng +10,
  sai −10 (không âm). Nâng cấp: trả đủ Linh Khí rồi hỏi đúng chữ của cây; sai thì mất số Linh Khí đó (đặc tả 9.1).
- **Sức mạnh cây = hệ số độ thuộc × hệ số sương mực** (0 → 60%, 100 → 130%; wither 100 → −30%). Wither lấy ô **khỏe nhất**
  đang trồng chữ đó trong vườn thật (tính lười bằng `srs.refresh_wither` như khi tải vườn); chữ không còn trồng thì không
  có sương mực. Sức mạnh nhân vào sát thương, máu Mộc, Linh Khí sinh ra và sức hỗ trợ; tính lúc vào ải và gửi trong
  `params`, không đổi giữa ải.
- **Vai trò cây** (`server/data/plants/plant_roles.json`): chữ đặc biệt gán tay (`by_hanzi`), còn lại theo chủ đề
  (`by_topic`). Một số chữ ví dụ của đặc tả không có trong danh sách từ (金 刀 力 石 光 米), nên Kim nhận các chủ đề số
  đếm, hành động, con vật, đồ vật; 苹果 là Sinh Khí qua chủ đề đồ ăn; ngữ pháp, lượng từ và tính từ (大 小) là Sơn. Test
  kiểm tra mọi chữ đều có vai trò và mọi ví dụ của đặc tả có trong dữ liệu đều đúng vai.
- **"Tối đa 8 loại"** là 8 chữ khác nhau; mỗi loại trồng bao nhiêu cây cũng được nếu đủ Linh Khí. Chỉ mang được chữ đã
  học (`introduced`). **Thành ngữ không trồng** mà là tuyệt chiêu một lần mỗi ải: 一石二鸟 đánh mạnh 2 con nhiều máu nhất,
  画蛇添足 làm mọi quái chậm hẳn 8 giây, 对牛弹琴 làm cả đám đứng ngẩn 5 giây.
- **Mộc trồng trên đường** (chặn quái, máu cao, có gai làm mất máu con bị chặn), các vai khác trồng cạnh đường; ô cổng và
  ô Linh Mạch không trồng được. **Tầm bắn tính tới ô đường**: một con quái trong tầm khi ô đường gần nó nhất nằm trong
  bán kính (vừa tất định vừa rẻ); vùng nổ của Hỏa đo dọc theo đường. Kim nhắm con **nhiều máu nhất**, các vai khác nhắm
  con đi xa nhất.
- **Phản ứng kề ô trong ải** (`combos` trong `balance/td.json`): 女 cạnh 子 thành 好 (cả hai +30%), 日/太阳 cạnh 月/月亮 thành
  明 (vùng sáng ×2), 3 cây 木/林/森/树 liền nhau thành 森 (cả cụm +50% máu), 人 cạnh cây gỗ thành 休 (cây gỗ tự hồi máu).
  Hiện thông báo khi một phản ứng thành hình.
- **Quái của ải là 6 loài mới** (Mực Con, Mực Phi, Mực Đặc, Mực Ẩn, Thạch Mặc, Mặc Vương), kháng/yếu nguyên tố trong
  `balance/td.json`, thẻ thông tin khi rê chuột và ở bản đồ ải. Mực Ẩn chỉ bị đánh khi đứng trong vùng sáng (cây Quang),
  cây Mộc vẫn chặn được. Gặp/hạ quái của ải ghi vào **Yêu Quái Phổ** với mã `td_<loài>` (Yêu Quái Phổ giờ có trang).
- **30 ải sinh bằng `tools/gen_td_levels.py`** (bản đồ 12 × 7 từ các mẫu đường đi vẽ tay, đợt quái từ "ngân sách máu"
  tăng theo ải và theo đợt, số liệu trong `level_gen` của `balance/td.json`) vào `server/data/td/levels.json`; test kiểm
  tra file khớp với script. Chương 1/2/3 cần Phàm Nhân/Luyện Khí/Trúc Cơ và ải trước đó; Linh Khí khởi đầu theo chương
  (110/200/300). **Độ khó chỉnh bằng `tools/td_bot.py`**: một người chơi tham lam đơn giản (8 cây, độ thuộc 40–50, đúng 85%)
  thắng cả chương 1 (Linh Mạch còn ≥ 16 điểm), gần hết chương 2; cuối chương 3 cần cây mạnh hơn hoặc chơi khéo hơn.
- **Sao theo điểm Linh Mạch còn lại** (≥ 16 / 8 / 1 trên 20). Thưởng lần đầu cho **từng sao mới đạt** (đạt 1 sao rồi sau
  đó 3 sao thì nhận phần của sao 2 và 3), cộng thưởng riêng ở vài ải (bí kíp, Gỗ Linh Mộc, Tiên Ngọc, một hạt giống của
  chữ đã học). Thắng lại một ải đã có sao: thưởng nhỏ, **tối đa 5 lần/ngày, dùng chung với Vô Tận Trận**.
- **Vô Tận Trận** mở sau ải c1_10. Hạt giống theo tuần (băm của tuần ISO, giờ UTC+7) nên cả máy chủ đánh cùng một trận
  trong tuần; đợt quái sinh vô hạn trong `td_sim.endless_wave` (tối đa 60). Kỷ lục tuần lưu trong `td_progress` với
  `level_id = endless_<năm>w<tuần>`, bảng xếp hạng lấy từ đó. Thưởng Linh Thạch theo số đợt giữ được (có trần).
- **Một migration mới (0005, bảng `td_runs`)** cho lượt đang chơi; `td_progress`, `td_loadout` đã có từ migration đầu;
  lượt thưởng trong ngày, mốc thư viện, danh hiệu, khung avatar lưu trong `users.flags`. Máy chủ tự nâng cấp `dev.db` khi
  khởi động như mọi lần.
- **`BALANCE_PROFILE=dev` chỉ đổi tốc độ tua tối đa** (×40 thay vì ×2) để thử nhanh và để test giao diện chơi hết chương 1
  trong vài phút; số liệu ải không đổi. Tốc độ tua chọn lần trước được giữ cho ải sau.
- **Thẻ câu hỏi trong ải bỏ qua cú bấm và phím số trong 0,3 giây đầu**: một đợt quái có thể kết thúc đúng lúc người chơi
  đang bấm lên bản đồ, thẻ hiện ra dưới con trỏ sẽ nhận nhầm cú bấm thành một đáp án.
- **Font không có ký tự ★** (hiện ô vuông) nên ngôi sao được vẽ bằng hình đa giác.
- **Tàng Thư Các** gom 6 phổ: Bách Thảo Phổ (mới), Yêu Quái Phổ, Ong Phổ, Ngư Phổ, Sổ Phát Hiện, Bảo Vật Phổ (mới), cùng
  Sổ Lỗi (đặc tả 8.3). Mở bằng Thủ Thư ở Trúc Lâm Thôn, phím **L**, hoặc nút trong Sổ Phát Hiện. Linh Thú Phổ chờ giai
  đoạn 8 (chưa có pet nào trong game).
- **Bảo Vật Phổ** = trang bị, đan dược và cần câu từng có. Không cần lưu thêm gì: lấy từ `audit_log` (mọi lần nhận vật
  phẩm, `item:<id>` / `equip:<id>:<độ hiếm>` với delta dương) cộng những gì đang giữ; dùng hết rồi vẫn còn trong phổ. Bí
  kíp, nguyên liệu, cá không tính (đã có phổ riêng hoặc không phải bảo vật).
- **Danh hiệu và khung avatar** (thưởng mốc thư viện) đeo được trong Tàng Thư Các (`/library/wear`), lưu trong
  `users.flags`, có trong `/me`. Danh hiệu hiện sau tên trên thẻ nhân vật (thế giới, động phủ, bảng Tu luyện), khung là
  viền màu quanh chân dung. Người chơi khác **chưa** thấy (phải đổi giao thức WebSocket; để giai đoạn sau).
- **Kệ bí kíp của Thủ Thư** (đặc tả 8.4: bí kíp "mua ở Tàng Thư Các"): 4 bí kíp Pháp Chữ, giá Linh Thạch trong
  `balance/library.json`. Xem được ở mọi nơi, nhưng chỉ mua được khi đứng cạnh Thủ Thư (máy chủ kiểm tra vị trí thật như
  Ngư Ông). Học bí kíp vẫn theo luật cũ (thuộc chữ ≥ 50%), đã học vẫn mua được (hiện "Đã học"). % = số mục đã có ÷ tổng (làm tròn xuống); mốc 25/50/75/100% của từng phổ trong `balance/library.json`
  (Linh Thạch, Tiên Ngọc, danh hiệu, khung avatar, một ô tổ ong không cần điều kiện). Các mốc riêng của Ngư Phổ (theo số
  loài) và Ong Phổ vẫn giữ, đây là mốc chung của thư viện.
- **Bách Thảo Phổ**: một trang cho mỗi chữ. "Đã có" = chữ nằm trong `collection` (kể cả hạt vừa quay chưa xem thẻ giới
  thiệu, vì trang chỉ chép lại thông tin của hạt); chưa có thì là bóng đen với dấu "?", **cây ẩn** (明 林 森 好 休 吗) chưa
  phát hiện chỉ là khung trống, máy chủ không gửi gì ngoài mã. Lời bình của Trúc Lão ghép từ độ thuộc và vai trò.
- **Tìm kiếm chỉ trong những gì đã phát hiện** (chữ, cá, ong, quái): gõ chữ Hán, pinyin có dấu, không dấu hoặc dạng số,
  nghĩa tiếng Việt có hoặc không dấu. Tìm một chữ chưa có không bao giờ làm lộ nó.
- `xp_per_correct.td = 4`: câu đúng trong ải cho Tu Vi như mọi nơi.
- **Test client không nạp gói `app` của máy chủ**: `app/config.py` đọc `server/.env` vào biến môi trường của tiến trình,
  và các máy chủ thử chạy sau đó trong cùng phiên test sẽ thừa hưởng (vd `BALANCE_PROFILE`). Test client dựng `params`
  của ải thẳng từ các file JSON.
- Sửa test câu cá `test_client_cannot_choose_the_fish_or_claim_a_catch` của giai đoạn 6 bị chập chờn: nó dùng "giữ nút
  suốt" làm đầu vào chắc chắn đứt dây, nhưng khi cá bơi sát mặt nước thì móc nằm trong vùng xanh và đôi khi câu được thật.
  Giờ dùng "không bấm gì" (móc nằm đáy, luôn dưới con cá) — chắc chắn sổng.

## Giai đoạn 8 — Luyện đan, khắc văn, Linh Thú, kinh tế

- **Đan phương là vật phẩm giữ mãi** (`dp_*` trong `items/materials.json`, kind `recipe`): có trong túi là luyện được,
  không mất khi luyện. Nguồn: nhiệm vụ "Đan Đạo", kệ sách Thủ Thư (mua một lần, mua lại bị từ chối), quái làm rơi
  (Thanh Điệu Yêu: Kháng Mực; Mặc Hồ: Trúc Cơ). Nút kệ đổi tên thành "Kệ sách" (bí kíp + đan phương).
- **Nguyên liệu** theo đặc tả: quả chữ (theo độ hiếm tối thiểu), Linh Quả, Linh Mật, Sáp Ong, cá (theo độ hiếm), Mực Tinh,
  và **dược thảo** mới: Trúc Diệp Thảo (sạp bán, quái rừng rơi) và Mặc Linh Chi (Thanh Điệu Yêu, Mặc Hồ). Đặc tả nói dược
  thảo hái ở "Núi Trúc" nhưng bản đồ chưa có vùng đó; tạm để quái rơi + sạp bán, Núi Trúc để giai đoạn sau.
  Máy chủ tự chọn quả/cá **ít quý nhất** thỏa điều kiện (loại nhiều nhất trước), người chơi không phải chọn từng quả.
- **Lò**: Đan Lô trong động phủ (đặt gần bàn đả tọa, `tools/gen_maps.py`) nâng được 3 cấp (vùng văn hỏa rộng +3/+5,
  cấp 3 có 25% ra thêm 1 viên); lò công cộng của Đan Sư ở làng luôn cấp 1. Máy chủ kiểm tra vị trí như Ngư Ông: không ở
  thế giới chung = ở nhà; trong làng phải đứng cạnh Đan Sư. Sạp Vải giờ là biển "đóng cửa" (Bà Chủ Sạp ngay cạnh).
- **Canh lửa** (`alchemy_fire.py` chung cho máy chủ và client, như `td_sim.py`): kim chạy 0 → 100 → 0, mỗi lần bấm kim
  chạy lại từ 0, chu kỳ ngắn dần qua 3 lần và theo độ khó của đan. Nguyên liệu và phí trừ khi **nhóm lửa**
  (`/alchemy/start`) — bỏ dở là mất (không "thử lại tới khi đẹp"). Máy chủ chọn chỗ vùng văn hỏa; client gửi thời gian
  kim chạy trước mỗi lần bấm, máy chủ tính lại vị trí kim và từ chối nếu tổng thời gian dài hơn thời gian thật đã trôi
  (`too_fast`, cho 2 giây mạng). Một client tự viết vẫn bấm "hoàn hảo" được (nó biết vùng) — chấp nhận được như ải thủ
  vườn: đó chỉ là kỹ năng bấm, không đổi được câu trả lời pinyin hay phần thưởng.
- **Chữ trên tên đan**: tên Hán đúng nghĩa Hán-Việt (回血丹 Hồi Huyết Đan, 聚灵丹 Tụ Linh Đan...), pinyin kiểm bằng
  CC-CEDICT trong test. Phần lớn các chữ này không có trong HSK 1–2, nên "chữ đã học" = chữ nằm trong **bất kỳ** từ đã học
  (气 có trong 天气, 空气). Chữ chưa học thì hiện chữ + pinyin + âm Hán-Việt để học (đặc tả: bỏ bước gõ). Phẩm chất tính
  theo **tỉ lệ** điểm / điểm tối đa (bấm: tuyệt hảo 2, văn hỏa 1, trượt 0; pinyin đúng +1, sai −1): từ 85% thượng, 60%
  trung, 30% hạ, dưới nữa là phế đan — người chưa học chữ nào vẫn luyện được thượng phẩm bằng 3 lần bấm tuyệt hảo, còn
  người đã học thì gõ sai bị trừ. Phẩm chất đổi **số viên** (đan thường: hạ 1, trung 2, thượng 3; đan đột phá luôn 1),
  không đẻ thêm loại vật phẩm.
- **Đan dược**: Hồi Huyết / Hồi Khí như cũ. **Tụ Linh Đan không cho Tu Vi trực tiếp** (luật cũ: không có Tu Vi nếu không
  trả lời) mà là bùa 10 phút: mỗi câu đúng +50% Tu Vi. Kháng Mực: +15 Kháng Mực 10 phút. Ngộ Tính: +3 giây cho mọi câu có
  giờ trong 10 phút (cộng vào `time_limit` khi tạo phiên). Bùa lưu trong `users.flags.buffs` (hạn tuyệt đối), uống thêm
  thì cộng dồn tối đa 2 liều; ngoài thế giới dùng chung hồi chiêu 15 giây với Hồi Huyết Đan. Phong Vương Đan cho ong ăn
  (400 kinh nghiệm, +15 thân thiết). Kim Đan Đan luyện được từ Trúc Cơ (cảnh giới Kim Đan để giai đoạn 11).
- **Khắc Văn**: 3 câu liên tiếp về đúng chữ đó (context `forge` của đặc tả mục 4), dạng câu xoay vòng Q1/Q2/Q3/Q5/Q4 để
  không ba lần cùng một kiểu; sai một câu là hỏng, phí (60 Linh Thạch + 2 Mực Tinh) trả khi bắt đầu. Ô khắc: Phàm/Linh 1,
  Huyền/Địa 2, Thiên 3. Thuộc tính theo chữ của đặc tả (火 công, 山 thủ, 心 Linh Lực, 人 Sinh Lực, 日/月 bạo kích); **水
  "kháng làm chậm"** đổi thành Kháng Mực vì người chơi chưa bao giờ bị làm chậm; chữ khác theo vai trò Thủ Vườn của nó
  (`plant_roles.json`), nhân hệ số độ hiếm. Giá trị cố định lúc khắc. Mài chữ 30 Linh Thạch. Chữ khắc hiện nhỏ cạnh tên
  trang bị ở Lò Rèn. Câu khắc văn cho mastery ±2 và Tu Vi như mọi câu ngoài vườn.
- **Linh Thú**: 12 con giáp theo thứ tự Việt Nam (**Mèo** thay Thỏ, **Dê** cho 羊), chữ Hán và pinyin kiểm bằng CC-CEDICT.
  Độ hiếm theo bảng gacha (Thường 4, Hiếm 4, Quý 3, Huyền thoại 1 = Rồng). Bốn kỹ năng của bản 1 giữ nguyên (Chuột +5%
  Hiếm — lấy 5% từ phần Thường; Trâu +20% tiền ôn đúng; Hổ sương mực chậm 50%; Rồng gấp đôi câu thứ 5 liên tiếp); tám con
  còn lại mỗi con một kỹ năng tự thiết kế, móc vào đúng chỗ nó tác động (Gà Tu Vi ôn vườn, Chó đồ rơi, Lợn bán quả, Mèo
  may mắn câu cá, Dê mật khi thu, Rắn Mặc Kích, Khỉ Linh Khí đầu ải, Ngựa Linh Thạch hạ quái). Không kỹ năng nào trả lời
  hay bỏ qua câu hỏi. Chuỗi của Rồng tính mọi câu ôn vườn (đúng +1, sai về 0), lưu `users.flags.garden_streak`.
- **Trùng pet** thì lên cấp (tối đa 5, chỉ số +25% mỗi cấp); quá cấp 5 thành Linh Thạch (60/120/250/600 — trung bình chỉ
  ~117 trên 500 mỗi lượt). Gacha Linh Thú 500 / 4.500 cho 10 (giảm 10% như các quầy khác), 10 / 90 Tiên Ngọc, 10 lượt có
  ít nhất 1 Hiếm. Pity như cấu hình sẵn từ giai đoạn 1 (Quý 20, Huyền thoại 60).
- **Pet đi theo**: hình vẽ bằng code (`art/build.py pet_frames`, 4 dáng: thú bốn chân, gà, rắn, rồng; tai/đuôi/sừng/bờm/
  mào theo `look` trong `pets.json`). Ở động phủ và thế giới chung con vật chạy theo sau chủ; người khác cũng thấy (trường
  `pet` của người chơi trong snapshot, không đổi số phiên bản giao thức). Phím **O** mở bảng Linh Thú; trong làng có nút
  "Linh Thú" ở thanh dưới; ở động phủ thanh nút đã đầy nên có nút trong bảng Tu luyện (K).
- **Sạp Tạp Hóa** (`balance/shop.json`): đan cơ bản, Trúc Diệp Thảo, Mực Tinh, giun, **Hạt Giống Thường** (hạt Thường
  ngẫu nhiên, ưu tiên chữ chưa có, tính vào 15 hạt mới/ngày), đồ Phàm/Linh mọi loại; giới hạn mỗi món mỗi ngày (UTC+7)
  lưu trong `users.flags`. Bán lại: vật phẩm và quả qua API cũ (`/inventory/sell`, `/fruits/sell`, bán ở đâu cũng được như
  trước), trang bị qua `/shop/sell_equipment` (phải tới sạp, không bán đồ đang mặc). Giá thu mua trang bị theo độ hiếm,
  +10% mỗi cấp cường hóa — luôn thấp xa chi phí.
- **Tặng quà** (đặc tả 12.4): chỉ vật phẩm **không ràng buộc** thuộc loại ăn được, nguyên liệu, dược thảo, mồi, đan, cá,
  trứng; 1–5 cái mỗi lần, 5 lần mỗi ngày mỗi người tặng; không tặng tiền, trang bị, bí kíp, đan phương. Người nhận được
  thông báo ngay nếu đang online. Nút "Tặng quà" trong danh sách bạn bè.
- **Nhiệm vụ hằng ngày**: mỗi ngày 1 việc cố định ("Ôn 15 chữ" = 15 câu đúng ở bất cứ đâu, vì vườn theo lịch SRS không đủ
  15 lần ôn/ngày cho người mới) + 2 việc chọn từ bảng (đánh 10 quái, câu 3 cá, thụ phấn 2 cây, luyện 2 mẻ, thắng 2 ải, đả
  tọa 3 câu, ôn vườn 4 lần), chọn cố định theo (người chơi, ngày) nên mở lại không đổi. Lưu cùng bảng `quests` (id
  `d<ngày>:<việc>`), việc hôm qua bị xóa khi tạo việc hôm nay; xong cả 3 thì thêm 50 Linh Thạch + 1 Tiên Ngọc một lần.
  `GET /me` tạo sẵn việc của ngày để mọi sự kiện đều được tính. Bảng Nhiệm vụ có hai tab và cuộn được.
- **Chuỗi nhiệm vụ "Đan Đạo"**: gặp Đan Sư (nhận đan phương Hồi Huyết + dược thảo) → luyện mẻ đầu → khắc văn một lần →
  luyện thêm 5 mẻ (10 Tiên Ngọc, đan phương Phong Vương).
- **Kinh tế** (`docs/BALANCE.md`): `tools/economy_sim.py` tính "giá có được" rẻ nhất của mọi món chỉ bằng Linh Thạch qua
  mọi phép đổi tức thời (mua, luyện, cắt mồi, cường hóa, gacha theo kỳ vọng) và báo vòng lặp nếu có món bán được ≥ giá đó;
  mô hình 30 ngày cho 3 kiểu người chơi in dòng tiền từng ngày. `server/tests/test_economy.py` chạy cả hai. Đan dược giờ
  bán được cho làng (6–120) nhưng luôn rẻ hơn nguyên liệu.
- **Một migration mới (0006, bảng `alchemy_sessions`)**: mẻ đan đang luyện (vùng văn hỏa, chữ phải gõ kèm đáp án) sống sót
  qua khởi động lại máy chủ; mở lò lần nữa thì "Luyện tiếp" đúng mẻ đó. Những thứ khác (cấp lò, bùa, lượt mua trong ngày,
  lượt tặng quà, chuỗi Rồng, lần khắc văn đang làm) nằm trong `users.flags`; pet dùng bảng `pets` có từ migration đầu.
- Test cũ được cập nhật theo thiết kế mới: `test_closed_banner` (quầy Linh Thú giờ mở; quầy tắt vẫn bị từ chối, kiểm bằng
  cách tắt tạm trong cấu hình) và hai test Tàng Thư Các (thêm Linh Thú Phổ, kệ có đan phương).

## Giai đoạn 9 — Bí cảnh hợp tác

- **Tổ đội** sống trong bộ nhớ của máy chủ (`realtime/party.py`), như cả thế giới: khởi động lại là mất, không cần bảng
  mới. Mời bằng đạo hiệu (người đó phải online, không chặn nhau), chỉ đội trưởng mời/mời ra/nhường; đội còn 1 người là
  giải tán; ngoại tuyến quá 60 giây thì rời đội. Trạng thái đội (máu %, vùng, online, hồn ma) gửi lại khi có thay đổi,
  tối đa 1 lần/giây. Kênh chat **Tổ Đội** (`/d`, tab riêng; trong bí cảnh là kênh mặc định). **Chia Tu Vi**: khi quái chết,
  đồng đội trong cùng kênh, cách quái ≤ 220 px mà không đánh nó vẫn nhận 50% Tu Vi của quái (không nhận Linh Thạch/đồ rơi).
- **Hai bí cảnh** (`data/realms.json`): **Khe Nứt Mực** (khe nứt ngẫu nhiên, Luyện Khí, HSK 1, 3 phòng câu đố + boss,
  15 phút, boss 70% máu) và **Mặc Ảnh Động** (định kỳ, Trúc Cơ — đúng bảng 7.3 "Trúc Cơ: bí cảnh cấp 1", HSK 2, 5 phòng +
  boss, 20 phút). Có khe nứt để người Luyện Khí cũng được chơi. "Đúng cấp bí cảnh" hiểu là chữ có cấp ≤ cấp bí cảnh.
- **Lịch** (`balance/realm.json`): 12:00, 19:00, 21:00 giờ Việt Nam, mở 15 phút, thông báo toàn máy chủ trước 10 phút và
  lúc mở (tin `notice`). `BALANCE_PROFILE=dev` thì Mặc Ảnh Động luôn mở, khe nứt xuất hiện thường hơn và hàng chờ ghép
  nhanh hơn — để thử. **Vào Mặc Ảnh Động** phải đứng ở **Cổng Bí Cảnh** (giữa quảng trường Trúc Lâm Thôn); thành viên khác
  ở đâu ngoài thế giới cũng được kéo vào (không ở trong động phủ, không đang gục, đủ cảnh giới).
- **Khe Nứt Mực**: mỗi 60 giây, mỗi kênh có người của Rừng Mực Loang / Hồ Nghiên Mực có 12% mọc một khe nứt cách một
  người chơi 70–170 px, sống 5 phút, tối đa 2 khe cả máy chủ. Khe là một thực thể (`k: "r"`) trong vùng quan tâm như quái,
  nên chỉ ai ở gần mới thấy; người ở gần nhận thông báo. Đội trưởng đứng sát khe (≤ 56 px) dẫn đội vào; người đi một mình
  bấm "Chờ người cùng vào" để vào hàng chờ của chính khe đó (phải đứng gần). Một khe dùng được cho nhiều đội tới khi khép.
- **Hàng chờ ghép đội**: chỉ cho người đi một mình (đội thì đội trưởng bấm vào). Ghép theo **đúng cảnh giới**; đủ 5 người
  thì vào ngay, đủ 2 người mà người đợi lâu nhất đã chờ 20 giây thì vào; nếu sau 40 giây vẫn không ghép được vì lệch cảnh
  giới (ít người online) thì trộn cảnh giới. Ghép xong là một tổ đội bình thường.
- **2 lượt/ngày/bí cảnh** (UTC+7), đếm trong bảng mới `realm_members` (migration 0007). Lượt bị tính khi vào; nếu cả đội
  không vào được vì có người vừa đi khỏi trong lúc mở cửa thì lượt được trả lại (xóa lượt chơi). Rời giữa chừng vẫn mất
  lượt.
- **Instance**: mỗi lượt là một `RealmInstance` — chính là một `ChannelZone` riêng trên bản đồ `bi_canh` (6 gian kín: Ghép
  Chữ, Đứt Đoạn, Thanh Điệu, Gương, Mê Cung, hang boss), nên di chuyển có kiểm tra, Vấn Đạo, ong hộ vệ, Linh Thú, snapshot
  đều dùng lại nguyên vẹn. Các gian **không nối nhau**: phòng xong thì sau 4 giây máy chủ chuyển cả đội sang phòng kế (gửi
  lại `zone`), thứ tự phòng ngẫu nhiên, chỉ chọn loại câu đố mà đội chơi được bằng chữ đã học (Ghép Chữ cần một chữ ⿰/⿱
  có người đã học; Đứt Đoạn cần một câu mà mọi từ đều có người đã học). Mê cung cố định (sinh bằng code, mở bằng Tiled
  được). Client chỉ thấy gian đang đứng (camera cố định giữa gian, ngoài gian tô đen).
- **Phòng xong = câu đố giải + quái trong phòng (Mặc Ảnh, Bút Yêu — không mọc lại) bị hạ.** Câu đố do máy chủ quyết định
  từ vị trí đứng và lệnh `ract` (đánh trụ); mỗi người chỉ nhận phần riêng của mình (`mine`): mảnh chữ, mấy mảnh câu (xáo
  thứ tự, không lộ vị trí), chữ trước gương. Nước đi trong câu đố về một chữ cũng tính như trả lời ngoài vườn (mastery ±2,
  sai thì đánh dấu cần ôn) nếu người đó có chữ ấy.
  - **Cửa Ghép Chữ**: chữ có cấu tạo 2 phần trái-phải (⿰) hoặc trên-dưới (⿱) theo makemeahanzi, ví dụ 好 = 女 + 子. Bốn bệ
    hình chữ thập, sáng 2 bệ theo kiểu ghép. Hai người cầm đúng mảnh, người còn lại cầm mảnh nhiễu. Đứng đủ hai bệ: đúng
    thì mở; sai thì **người đứng sai** mất 10% máu, chia mảnh lại, nghỉ 2,5 giây. 10 giây tính từ lúc có người bước lên;
    hết giờ thì ai đang đứng mất 5%; mọi người bước xuống hết thì bỏ qua không phạt. Còn một người thì chỉ cần một bệ.
  - **Câu Văn Đứt Đoạn**: câu 3–8 từ (sàn có 8 ô số), mỗi mảnh giao cho người đã học từ đó nếu có. Bước lên ô k+1 mà mình
    giữ mảnh thứ k+1: đúng; người khác bước lên ô đó: mất 10% máu. Bước sớm lên ô của mình: chỉ nhắc "chưa tới lượt".
    Người giữ mảnh rời đi/gục thì mảnh chuyển cho người khác.
  - **Trụ Thanh Điệu**: không phát âm (mã âm thanh chứa số thanh, sẽ lộ đáp án) mà hiện **chữ Hán + pinyin không dấu** như
    đặc tả cho phép. Máy chủ chọn thanh trước, rồi chọn chữ mang thanh đó **trong số chữ người đứng gần trụ đó nhất đã
    học** (để "người phải trả lời đã học chữ đó"). Ai đánh đúng trụ trong 5 giây (+1 giây mạng) cũng tính; đánh nhầm thì
    người đánh mất máu; hết giờ thì người gần trụ đúng nhất lúc tượng đọc mất máu; sai hay hết giờ chuỗi về 0. 8 lần đúng
    liền thì xong.
  - **Gương Nghĩa**: mỗi người được một từ đã học, nghĩa không trùng nhau; gương hiện nghĩa từ của một người. Phải **bước
    vào** gương (đang đứng sẵn trong đó thì ra rồi vào lại). Sai người: cả đội mất 6%; 25 giây không ai vào: cả đội mất 3%.
    Đúng 3 lần thì xong.
  - **Mê Cung Mực**: người đã học **明** (hoặc 光 nếu sau này có trong danh sách từ) tỏa sáng bán kính 64 px. Đặc tả nói
    "có kỹ năng Quang" — chưa có Pháp Chữ Quang nên dùng "đã học chữ". Không ai học thì người học nhiều chữ nhất cầm
    **đèn lồng** sáng yếu (40 px) để mê cung luôn qua được. Đứng ngoài ánh sáng: mất 2% máu mỗi giây. Mọi người còn đứng
    tới cửa ra là xong.
- **Boss Nghiên Ma** (48×48): Mặc Thuẫn hồi ở 75/50/25% → 4 pha. Mỗi pha khiên lớn chỉ vỡ khi **N người khác nhau trả lời
  đúng**, N = số người còn sống và còn kết nối (người gục giữa pha làm N giảm ngay). Ai đúng rồi thì không bị hỏi thêm pha
  đó (đánh thường vẫn chỉ 1 sát thương). Mỗi 8 giây một vùng **Mặc Triều** đỏ bán kính 44 px dưới chân một người, 1,6 giây
  sau trúng 15% máu (đang trả lời — Hộ Thể — thì không trúng). Máu boss ×(1 + 40% mỗi người thêm). Boss tỉnh sau 3 giây.
- **Hồn ma**: hết máu trong bí cảnh không mất Tu Vi, không về làng: thành hồn ma (vẽ mờ) vẫn đi theo đội nhưng không đánh,
  không giải đố, không bị đánh; hồi sinh 50% máu khi đội sang phòng kế (hoặc khi kết thúc). Cả đội là hồn ma = thất bại.
- **Kết thúc**: thắng (hạ boss), thất bại, hết giờ, hoặc mọi người đã rời. Màn kết quả 30 giây rồi cả đội về Cổng Bí Cảnh.
  Vị trí trong bí cảnh **không bao giờ được lưu**: lưu định kỳ hay rời thế giới đều ghi chỗ Cổng Bí Cảnh, nên khởi động lại
  máy chủ giữa chừng thì người chơi đứng ở làng.
- **Rớt mạng** (đặc tả 14.3): trong bí cảnh nhân vật chờ 60 giây (ngoài thế giới 30). Vào lại kịp thì máy chủ gửi lại toàn
  bộ (`start`, `room` kèm phần riêng, `end` nếu đã xong). Quá hạn thì rời bí cảnh, `realm_members.result = "disconnected"`,
  vẫn giữ phần thưởng các phòng đã qua. Người đang rớt mạng không tính vào "người chơi được" (không chia mảnh cho họ,
  không tính vào N của boss).
- **Phần thưởng riêng, không nhận hai lần**: mỗi lần nhận là một dòng `realm_claims(run_id, user_id, stage)` (khóa chính)
  ghi **cùng giao dịch** với tiền/đồ. Gọi lại hay hai yêu cầu cùng lúc thì yêu cầu sau vi phạm khóa chính và không được gì.
  Mỗi phòng xong: mỗi người còn trong lượt tự tung xúc xắc (15–30 Linh Thạch, Mực Tinh, Thiên Tằm Ti, Hồi Huyết Đan, 20 Tu
  Vi). Rương cuối: Linh Thạch, Tiên Ngọc, **Mảnh Bảo Vật chung** (cùng số cho cả đội = gốc + 1 cho mỗi phòng câu đố không
  sai lần nào), 2–3 lần mở bảng đồ (Thiên Tằm Ti, Mặc Linh Chi, trứng ong Huyền/Địa/Thiên, đan phương Kim Đan, đồ bộ Mặc
  Ảnh), Tu Vi. Xong trong nửa thời gian: ×1,5 Linh Thạch và thêm một lần mở bảng.
- **Đồ bộ Mặc Ảnh** (Quan, Bào, Ngoa, Bội): rơi từ rương (phẩm Linh/Huyền trở lên) hoặc **Ghép Bảo Vật** ở Cổng Bí Cảnh:
  12 Mảnh Bảo Vật + 600 Linh Thạch → một món phẩm Thiên tự chọn. Thưởng bộ: 2 món +8 Kháng Mực, 4 món +40 Sinh Lực, +6 Công
  (`equipment.json → sets`, cộng trong `stats_for`). **Cần Thiên Tơ** giờ mua được ở Ngư Ông bằng 12 Thiên Tằm Ti + 30 Vảy
  Linh Ngư + 6.000 Linh Thạch.
- **Ping biểu tượng**: chuột phải trong bí cảnh đặt dấu "!" (giữ Shift: "→") cho cả đội thấy 3 giây (1 lần/giây).
- **Giao thức lên bản 5** (thêm `party`, `realm`, `ract`, `mark`; snapshot `me` có thêm cờ hồn ma; thực thể khe nứt).
- **Kiểm thử**: `server/tests/test_realm.py` (27 test, máy chủ trong tiến trình với đồng hồ giả: 3 bot đi bằng gói tin thật
  qua cả 5 câu đố + boss, và từng luật: lượt/ngày, cảnh giới, giờ mở, hàng chờ, khe nứt, giá của mỗi sai lầm, hồn ma, N của
  boss, rớt mạng, nhận thưởng một lần kể cả khi gọi đồng thời, ghép đồ bộ). `server/tests/test_realm_ws.py`: máy chủ thật +
  3 bot trên 3 kết nối WebSocket (`tools/realm_bots.py`) vượt Mặc Ảnh Động. `client/tests/test_realm_flow.py`: game thật mở
  cổng, lập đội bằng bảng Tổ đội, vào bí cảnh cùng 2 bot rồi rời; 2 bot vượt nốt; rồi phát lại cả lượt chơi trên game để
  vẽ mọi phòng. Bot biết đáp án Vấn Đạo bằng cách đọc cơ sở dữ liệu (chỉ trong test).
- Test cũ cập nhật: số quái trong Yêu Quái Phổ (thêm 3 quái bí cảnh), phiên bản giao thức 5, Cần Thiên Tơ giờ báo
  `realm_too_low` thay vì `not_sold` với người chưa Trúc Cơ.

## Giai đoạn 10 — Phát hành

- **Exe một thư mục, không một file**: `tools/build_exe.py` mặc định build PyInstaller dạng thư mục
  (`dist/VuonChu/VuonChu.exe` + `_internal/`) rồi nén thành `VuonChu-<bản>-windows.zip` (~30 MB). Bản một file phải tự giải
  nén vào thư mục tạm mỗi lần mở (chậm vài giây) và bị phần mềm diệt virus báo nhầm nhiều hơn hẳn; `--onefile` vẫn có cho ai
  cần. Đặc tả gọi tên `VuonChu.exe` — vẫn đúng tên đó, chỉ nằm trong thư mục. `client/main.py` dùng import tương đối nên
  PyInstaller không lần theo được từ chính file đó (một lần build ra exe thiếu cả package `client` mà vẫn "thành công");
  build dùng một file khởi động hai dòng `from client.main import main`. Vì lỗi kiểu này im lặng, build **tự chạy exe** với
  `--smoke-test <mọi module>`: nạp mọi module của game, font và bản đồ từ trong gói, lỗi thì build báo hỏng.
  Biểu tượng exe vẽ bằng chính code sprite (cây chữ huyền thoại chín trên nền giấy dó), lưu dạng PNG-trong-ICO.
- **Exe chạy không có cửa sổ lệnh**, nên lỗi làm game tắt được ghi vào `vuonchu_loi.txt` cạnh exe và báo bằng hộp thoại
  Windows. `config.json`/`session.json` nằm cạnh exe như đặc tả; nếu thư mục không ghi được (giải nén vào Program Files)
  thì ghi vào `%LOCALAPPDATA%\KhuVuonTuTien`, nhưng vẫn đọc `config.json` đi kèm exe nếu người chơi chưa lưu cái riêng.
- **`server_list_url` là nguồn sự thật**, trừ khi người chơi tự gõ máy chủ trong Cài đặt (`session.json → server_manual`).
  Trước đây game bỏ qua danh sách hễ đã từng đăng nhập (đã lưu `server_url`), nên với quick tunnel (địa chỉ đổi mỗi lần)
  người cũ kẹt ở địa chỉ chết. Giờ: địa chỉ đã lưu còn trong danh sách thì giữ (danh sách có nhiều máy), không còn thì
  chuyển sang mục đầu tiên. Xóa trống ô Máy chủ rồi Lưu để quay về danh sách. Địa chỉ dán vào được chuẩn hóa (thêm
  `http://`, bỏ `/server/info` và `/` cuối), nên dán cả link trang trạng thái cũng được.
- **Kiểm tra phiên bản khi mở game** (mục 15.5): menu gọi `/server/info`; lệch giao thức thì không cho Bắt đầu, báo cập nhật
  kèm `client_download_url`. Exe mới hơn (`LATEST_CLIENT_VERSION`) chỉ nhắc nhẹ, vẫn chơi được. Menu và màn đăng nhập hiện
  thông báo bảo trì / thông báo chung. Trước giai đoạn này `check_version` có sẵn nhưng không nơi nào gọi.
- **`/server/info` vừa là API vừa là trang**: game nhận JSON; trình duyệt (`Accept: text/html`) nhận trang trạng thái nhỏ
  (online, phiên bản, đã chạy bao lâu, thông báo, nút tải game) — một địa chỉ để gửi cho người chơi. `/` chuyển về đó.
  `/healthz` riêng cho kiểm tra sống, không chạm DB, để Render gọi liên tục mà Neon vẫn ngủ được.
- **Lệnh admin qua chat** (`app/admin.py`): dòng bắt đầu `/admin` bị chặn ở `ChatService` trước mọi kiểm tra khác, không bao
  giờ phát ra kênh nào, kể cả khi gõ sai hay không có quyền. Quyền đọc lại từ DB mỗi lệnh (thu hồi quyền có hiệu lực ngay
  với kết nối đang mở). Tên người chơi có dấu cách nên `<tên> <thời hạn> [lý do]` tách ở token đầu tiên đọc được là thời
  hạn; `@username` để chỉ đích danh tài khoản. SQLite chỉ hạ chữ hoa ASCII nên tên có chữ hoa tiếng Việt được so bằng
  `casefold()` trong Python khi truy vấn không ra. Không dùng `ilike` cho username (dấu `_` là ký tự đại diện của LIKE).
  Có tên lệnh tiếng Việt không dấu (`camchat`, `khoa`, `thongbao`...). Quản trị viên trong game không tác động được lên mình
  hay quản trị viên khác; dòng lệnh máy chủ (`python -m app.admin_cli`) thì được — đó là chủ máy chủ.
- **Khóa/cấm chat dùng cột có sẵn** (`banned_until`, `chat_banned_until`, từ giai đoạn 1) — chặn ở `/auth/login`, mọi
  request có token và WebSocket. Khóa thì đá kết nối ngay (mã đóng 4010; 4005 đã là `timeout`). Mọi lệnh làm thay đổi gì đều
  ghi bảng mới `admin_actions` (migration 0008), lưu cả tên để còn đọc được khi tài khoản đã xóa. Thời gian trong lệnh admin
  hiển thị theo giờ Việt Nam.
- **Không có gì tự cấm**: đặc tả 17 yêu cầu đánh dấu tài khoản trả lời bất thường; cột `suspicious_flag` có từ giai đoạn 1
  nhưng chưa nơi nào ghi. Giờ mỗi câu trả lời cập nhật `flags.fast_streak` (đúng và nhanh hơn `fast_ms` thì +1, ngược lại về
  0; chỉ ghi khi đổi); chạm `streak` (200 câu dưới 500 ms, `balance/quiz.json → bot_watch`) thì đánh dấu. Thời gian đo ở
  máy chủ (gồm cả mạng), nên người thật gần như không thể chạm ngưỡng. `/admin flagged`, `/admin who`, `/admin unflag`.
- **`ADMIN_USERNAMES`**: Render free không có shell để chạy lệnh cấp quyền, nên tên trong biến này được cấp `is_admin` lúc
  khởi động và lúc đăng ký. Bỏ tên khỏi biến không thu hồi (tránh mất quyền vì gõ nhầm biến); thu hồi bằng `admin_cli revoke`.
- **`TIME_SCALE` đổi lúc chạy** (`/admin timescale`) chỉ khi `ENV=dev`, giống ràng buộc lúc khởi động. Mọi nơi đọc
  `settings.time_scale` tại thời điểm dùng nên đổi là có hiệu lực ngay; mất khi khởi động lại. Thông báo bảo trì/thông báo
  chung cũng chỉ ở trong RAM (`server_state.py`) — không cần bảng mới cho hai chuỗi.
- **Chuỗi kết nối của Neon**: Neon đưa `?sslmode=require&channel_binding=require`, asyncpg không hiểu cả hai (nó dùng
  `ssl=`), nên `normalize_database_url` dịch/bỏ chúng; host `-pooler` (PgBouncer chế độ transaction) thì tắt bộ đệm
  prepared statement của asyncpg. Khuyên dùng kết nối trực tiếp.
- **Để Neon ngủ**: pool SQLAlchemy giữ kết nối mở mãi, làm Neon không tạm dừng và tính giờ cả khi không ai chơi.
  `DB_IDLE_CLOSE_SECONDS` (mặc định 300, Render 240): không có truy vấn trong khoảng đó thì `engine.dispose()` đóng hết;
  truy vấn sau tự kết nối lại. Không đổi sang `NullPool` vì mỗi request phải bắt tay TLS với Neon lại từ đầu.
- **`ENV=prod` bắt buộc `JWT_SECRET` ≥ 32 ký tự**: trước chỉ chặn đúng chuỗi mặc định, còn để trống (dòng `JWT_SECRET=`
  trong file .env mẫu) thì lọt.
- **Docker**: `python:3.12-slim` (đa kiến trúc), chạy bằng người dùng thường, cổng lấy từ `PORT` (Render tự đặt).
  Không bật `--proxy-headers` của uvicorn: IP người chơi sau proxy do ứng dụng tự đọc khi `TRUST_PROXY_HEADERS=1`, để chỉ có
  một chỗ quyết định có tin header hay không. `docker-compose.yml` dùng cho cả A và C: Caddy nằm trong profile `https`; cổng
  8000 chỉ mở cho `127.0.0.1`. Mọi image (python, postgres:16-alpine, caddy:2-alpine) có bản arm64.
  `.github/workflows/docker.yml` build `linux/amd64,linux/arm64` bằng buildx + QEMU lên GHCR.
  **Chưa build thử được image trên máy làm giai đoạn này** (Docker Desktop không khởi động); file Docker được test đọc và đối
  chiếu (`server/tests/test_release.py`), còn build thật chạy trên GitHub Actions.
- **Sao lưu**: `tools/backup_db.sh` (POSIX sh, chạy trong container `postgres:16-alpine` có sẵn `pg_dump`; dịch vụ `backup`
  của compose sao lưu khi khởi động rồi mỗi ngày 20:00 UTC = 3:00 sáng VN) và `tools/backup_db.py` (Windows/SQLite dùng API
  backup của SQLite nên sao lưu được khi máy chủ đang chạy; PostgreSQL thì gọi `pg_dump`). Cùng tên file
  `khuvuon-YYYYmmdd-HHMMSS.*`, sắp theo tên là theo thời gian, giữ 7. Đường dẫn có dấu cách (như "khu vườn tu tiên") được
  xử lý. `pg_dump` ghi ra file tạm rồi mới nén (sh POSIX không có `pipefail`, ống `pg_dump | gzip` sẽ nuốt lỗi).
- **`ALLOW_UNREVIEWED=1` trong file mẫu triển khai**: 44 câu luyện tập chưa câu nào được đánh dấu đã duyệt, mà `ENV=prod` mặc
  định tắt câu chưa duyệt — các dạng câu dùng câu ví dụ sẽ không có câu nào. Ghi chú trong `.env.example`: đặt 0 khi đã duyệt.
- **GitHub Actions**: đẩy tag `v*` → build exe trên Windows (kèm chạy thử), đính zip vào Release; build image đa kiến trúc;
  test máy chủ + client mỗi lần đẩy. Địa chỉ máy chủ của exe lấy từ biến repo `SERVER_URL`/`SERVER_LIST_URL`.
- **Phiên bản 1.0.0** (`GAME_VERSION` ở cả hai phía). Giao thức vẫn **5**: chỉ thêm gói `admin` và trường `notice.kind`,
  client cũ bỏ qua được, không cần buộc mọi người cập nhật.
- **Tiêu chí "triển khai thật, hai người trên hai mạng tải exe từ GitHub Releases"** cần tài khoản Oracle/Render/Neon/GitHub
  của chủ dự án nên không làm thay được; `docs/DEPLOY.md` mục G là danh sách kiểm tra cho lần đó. Phần đã làm ở đây: build
  exe thật, exe tự chạy thử, exe chạy thật nối vào máy chủ cục bộ (gọi `/server/info`), và test WebSocket thật cho lệnh admin.

## Bản 1.1 — Thế giới LAN kiểu Minecraft, tài khoản Firebase

Yêu cầu: không thuê máy chủ; dữ liệu lưu trên máy người mở thế giới, người khác cùng mạng LAN vào chơi; tài khoản đăng ký
một lần, lần sau chỉ đăng nhập, dùng Firebase (dự án và API key do chủ dự án tạo).

- **Không viết lại game**: máy chủ FastAPI có sẵn chính là "thế giới". Game mở một thế giới bằng cách chạy máy chủ đó
  trên máy người chơi, như một **tiến trình con** (`VuonChu.exe --host-server`, hoặc `python -m client.main --host-server`
  khi chạy từ mã nguồn). Tiến trình riêng thay vì một luồng: vòng tick 20 Hz của thế giới không tranh GIL với vòng vẽ 60
  khung hình, mỗi lần mở thế giới có cấu hình riêng (`settings` của máy chủ đọc biến môi trường lúc import), và lỗi của máy
  chủ không làm đổ game. Mọi luật chống gian lận (máy chủ có thẩm quyền, câu hỏi chấm ở máy chủ...) giữ nguyên — kể cả người
  chủ cũng chơi qua máy chủ của mình như người khác. Người chủ đương nhiên sửa được file dữ liệu của chính mình; đó là bản
  chất của kiểu Minecraft.
- **Tắt êm**: game giữ stdin của tiến trình con; ghi `stop` (hoặc game chết và stdin đóng) thì uvicorn dừng bình thường,
  `world.stop()` lưu vị trí mọi người. Không dùng `TerminateProcess`/`os.kill` (trên Windows `os.kill(pid, 0)` còn giết
  luôn tiến trình). Có `kill` dự phòng sau 10 giây.
- **Thế giới là một thư mục** `worlds/<slug>/` trong `data_dir()` (cạnh exe; `client/worlds/` khi chạy từ mã nguồn):
  `world.json` (tên, ngày, khóa ký token riêng của thế giới — để token còn hiệu lực sau khi mở lại), `world.db` (SQLite),
  `server.log`. Nhiều thế giới, tạo/chọn trong game; chép thư mục là sao lưu. SQLite vì không cần cài gì; máy chủ chạy
  `ENV=prod` (khóa token bắt buộc, không `TIME_SCALE`) với `ALLOW_UNREVIEWED=1` như file mẫu triển khai.
- **Tài khoản Firebase, dữ liệu theo thế giới**: game đăng nhập Firebase Authentication bằng REST (email + mật khẩu —
  đăng nhập Google trong một game pygame cần luồng OAuth qua trình duyệt, phức tạp hơn nhiều mà không thêm gì cho việc
  chơi LAN). Refresh token lưu trong `session.json` nên lần sau không phải gõ; ID token (1 giờ) được làm mới khi còn dưới 5
  phút. Khi vào một thế giới, game gửi ID token tới `POST /auth/firebase` của thế giới đó; thế giới hỏi Firebase
  (`accounts:lookup`) xem token của ai — chỉ cần API key công khai, không cần service account, nên máy ai cũng làm chủ được
  — rồi tìm/tạo tài khoản cục bộ gắn `firebase_uid` (migration 0009) và trả token phiên của chính nó. Mọi API cũ dùng
  token đó như trước, không đổi gì. Giống Minecraft: một danh tính, mỗi thế giới một nhân vật và một túi đồ riêng.
- **Tên đăng nhập cục bộ** sinh từ phần trước `@` của email (`ban.be@…` → `ban_be`, trùng thì `ban_be2`), vì cột
  `username` là khóa của nhiều thứ (admin, báo cáo). Mật khẩu cục bộ là chuỗi không băm được (`!firebase`) nên tài khoản
  Firebase không bao giờ đăng nhập được bằng `/auth/login`. Thế giới mở từ game đặt `LOCAL_ACCOUNTS=0`: `/auth/register` và
  `/auth/login` trả `local_off`, mọi người trong thế giới đều là tài khoản Firebase.
- **Người mở thế giới là quản trị viên** (`HOST_FIREBASE_UID` = uid của người chủ), dùng được `/admin ...` của giai đoạn 10.
- **Tác giả game là quản trị viên ở mọi thế giới** (1.1.2): tài khoản Firebase có email trong `OWNER_EMAILS`
  (`server/app/config.py`, tài khoản phongfoxyd) hoặc `ADMIN_EMAILS` được `is_admin` khi vào bất kỳ thế giới nào. Khớp theo
  email chứ không theo tên đăng nhập: tên trong thế giới lấy từ phần trước `@` nên ai cũng chiếm được, còn email thì Firebase
  giữ duy nhất. Vì thế thế giới mở từ game đặt `ADMIN_USERNAMES=""` (không lấy từ `server/.env` của máy chủ).
- **Tìm thế giới trên LAN**: thế giới phát gói UDP broadcast nhỏ (`{"g": "khuvuon-lan", v, name, host, port, online}`) tới
  `255.255.255.255:47654` mỗi 1,5 giây (và tới `127.0.0.1` để máy không có mạng vẫn thấy chính mình); tab *Tham gia mạng LAN*
  nghe cổng đó (`SO_REUSEADDR`, nhiều game cùng máy vẫn nghe được) và quên thế giới im lặng quá 5 giây. Không dùng
  multicast/mDNS: broadcast đủ cho mạng nhà, không cần thư viện. Router chặn broadcast (một số Wi-Fi khách) thì vẫn gõ
  địa chỉ được; địa chỉ LAN của người chủ hiện trong chat và Cài đặt. Cổng TCP bắt đầu từ `host_port` (8000), bận thì thử
  cổng sau.
- **Broadcast ra từng card mạng** (sửa lỗi 1.1.0): Windows gửi `255.255.255.255` từ socket không gắn địa chỉ ra **một** card
  duy nhất — card có metric thấp nhất, thường là card ảo (WSL/Hyper-V/VPN) — nên bạn bè trên Wi-Fi thật không thấy thế
  giới. Thế giới mở một socket gắn vào từng địa chỉ IPv4 của máy (bỏ 127.x, 169.254.x; làm mới mỗi 30 giây) và gửi qua
  từng cái. Máy có cả Wi-Fi lẫn dây được nghe từ hai IP: tab LAN gộp theo (tên, chủ, cổng), chọn cố định một IP, ưu tiên
  `192.168.*` rồi `10.*` (dải `172.16–31` thường là card ảo).
- **Kiểm tra phiên bản khi vào thế giới** (`/server/info` có thêm `auth` và `local_accounts`): khác giao thức thì báo hai
  máy cần cùng bản game; địa chỉ là máy chủ riêng (không phải thế giới LAN) thì báo rõ. Bản game 1.1.0 (giao thức vẫn 5).
- **Cần Internet lúc đăng nhập** (Firebase), cả ở máy người vào lẫn máy người chủ (để hỏi Firebase). Chơi thì chỉ cần LAN.
  Chế độ hoàn toàn offline không làm: không có cách nào kiểm tra danh tính mà không có máy chủ chung.
- **Chế độ máy chủ riêng vẫn còn**: `firebase_api_key` rỗng trong `config.json` → game quay về màn đăng nhập tên + mật khẩu
  với một `server_url` cố định (giai đoạn 10, `docs/DEPLOY.md`). Test client cũ dựng `Config(...)` trong code (không có
  key) nên vẫn chạy luồng đó. Khi chạy từ mã nguồn mà chưa có `client/config.json`, game đọc `client/config.example.json`
  (có key của dự án).
- **Firebase Auth Emulator**: cả máy chủ lẫn game đọc `FIREBASE_AUTH_EMULATOR_HOST` (quy ước của Firebase), dùng cho test
  trọn vòng `client/tests/test_lan_worlds.py`: game mở thế giới thật (tiến trình con), thế giới phát tín hiệu LAN và được
  nghe thấy, người chủ vào bằng token qua một "emulator" giả, được làm quản trị viên, rồi tắt thế giới êm (mã thoát 0).
- **Exe mang theo máy chủ**: `build_exe.py` thêm package `app` của máy chủ, `data/`, `maps/`, `alembic/` (migration được
  đọc như file), `uvicorn`/`alembic` (nạp module theo tên lúc chạy), bỏ những gói kéo theo vô ích (jedi, PIL,
  cryptography... ≈ 45 MB). Chạy thử sau build có thêm bước mở một thế giới bằng chính exe (`--host-server`), chờ
  `/server/info` báo `auth: firebase`, gửi `stop` và kiểm tra thoát 0, `world.db` được tạo. Zip ≈ 36 MB.
- **Dự án Firebase của chủ dự án chưa bật Authentication** lúc làm bản này: mọi lời gọi trả `CONFIGURATION_NOT_FOUND`
  (key đúng, chưa bấm *Get started* / chưa bật Email/Password). Game hiện thông báo tiếng Việt chỉ đúng bước cần làm.
- **Báo bản mới qua GitHub Releases** (1.1.1): thế giới LAN không có máy chủ chung để hỏi `latest_client_version`, nên
  game hỏi thẳng `GET api.github.com/repos/<update_repo>/releases/latest` lúc mở (không cần token; giới hạn 60 lần/giờ mỗi
  IP là quá đủ cho một lần mỗi lần mở game). Chạy trên luồng riêng bằng `httpx` chứ không qua `Api`: lỗi mạng ở đó sẽ bật
  thanh "mất kết nối" dù chơi LAN không cần Internet. Bỏ qua draft/prerelease; so phiên bản theo số (`1.10.0` > `1.9.0`).
  Nút Tải về mở thẳng link file zip của release (không có zip thì trang release). `update_repo` do `tools/build_exe.py`
  ghi vào `config.json` (lấy từ `--update-repo`, mặc định là remote `origin`); workflow release truyền
  `github.repository`. Không tự cài đè: exe đang chạy không ghi đè được chính nó trên Windows, và giải nén đè thủ công
  giữ nguyên `worlds/` + `session.json` vì chúng không có trong zip.
- **MessageBox tự đo chiều cao chữ** (sửa lỗi): trước tính mỗi dòng 10 đơn vị trong khi chữ cỡ 8 cao ~13,4 (kể cả giãn
  dòng 1,15), nên thông báo dài từ 4–5 dòng trở lên bị hai nút đè lên chữ.

