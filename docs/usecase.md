# Use cases + mô tả hoạt động — Vocabking

> Tài liệu cho tester: mỗi use case có user story, ví dụ cụ thể, và cơ chế
> hoạt động bên trong. Đọc theo thứ tự cũng chính là thứ tự trải nghiệm thật.

---

## Nghiệm thu hiện tại — ưu tiên hơn ví dụ lịch sử bên dưới

- UI tiếng Anh; phím tắt xem [docs/guide.md](guide.md).
- `/settings` → **Daily target** → nhập `250`: lưu mục tiêu, dọn tin chứa số nếu Telegram cho phép và sửa tin cũ thành menu chính.
- **Quiet hours** → **Custom hours**: nhập lần lượt giờ bắt đầu, giờ kết thúc (0–23). Kiểm tra bước nhập sai không ghi đè cài đặt và kết quả vẫn nằm trong cùng tin.
- **Games** → **Story challenge**: nhập số 1–20; kết quả là bảng `# | Word | Meaning`, không phải danh sách gạch đầu dòng.
- **Vocabulary**: mở thẳng bảng 10 dòng/trang (Prev/Next); chỉ còn **Edit** / **Delete** / **Search** (Add nằm ở menu chính). Chọn dòng bằng STT hoặc tên từ.
- Dialog chờ nhập tự đóng sau **15s** không phản hồi. Tin nhắc FSRS **không** dùng timeout đó; đang trong FSM thì không chen quiz.

### Kiểm tra quiz, lịch và tệp

1. Thêm `continent`, nghĩa `châu lục`, ví dụ `Africa is a vast continent.`. Thẻ mới được seed **Hard** (khoảng ~5.5 phút trên lịch mặc định). Về menu chính trước khi đợi nhắc; kiểm tra với kho chỉ có một từ.
2. Khi đến hạn, `/study` hoặc tin nhắc hiển thị `Africa is a vast c _ _ _ _ _ _ _ _.`. Gõ `?` để mở thêm chữ. Gõ từ để xem đúng/sai, sau đó bấm nút có thời gian (`Again (1m)` …) hoặc gõ `1`–`4`. `/help` và [guide.md](guide.md) có phím tắt.
3. Với câu khác, gõ `???` hoặc bấm nút xem đáp án: hiện đầy đủ từ và tự chấm **Again** đúng một lần. Nếu đang nhập trong luồng khác, reply trực tiếp vào câu quiz (alarm không chen khi FSM còn mở).
4. **Import / Export**: xuất tệp `.csv` hoặc `.json` có dấu thời gian; import bằng cách reply đúng tin nhắc với tệp UTF-8 hoặc dán nội dung rồi xác nhận. Cột bắt buộc: `word`, `define_en`, `meaning`; cột tuỳ chọn: `phonetic`, `example`, `note`, `pos`.

## Ghi chép lịch sử — 08/11/2026

Các mục từ đây trở xuống là ghi chép các phiên trước; dùng checklist nghiệm thu hiện tại ở đầu tài liệu khi có khác biệt.

- `/add` / Menu Add: hỏi từ → lookup chỉ EN → Đồng ý(1)/Manual(2) → template pipe (điền phần thiếu) → preview. Miss API → thẳng template. Bulk: `/add từ|IPA|defineEN|nghĩaVI|ví dụ|note`. Không còn submenu Dictionary/Manual hay bare-word lookup.
- `hello||greeting|xin chào|hello its me||`: IPA/note trống, EN=`greeting`, VI=`xin chào`, ví dụ=`hello its me`. Trim từng trường; không dịch chuyển trường trống. Dấu `|` trong note có nội dung được giữ.
- SQLite: `define_en` chứa EN, `meaning` chứa VI. DB cũ được thêm cột EN nếu thiếu, giữ nguyên dữ liệu cũ. Preview, sửa từ, chi tiết và đáp án ôn tách EN/VI.
- Quiz có nút **Gợi ý thêm chữ** và **Xem đáp án**; reply `?`/`???` vẫn hỗ trợ. Quiz gợi ý chữ của vocab EN, chỉ che vocab trong ví dụ. Chữ đã mở không bị che lại.
- Reveal giữ session, chưa chấm FSRS. Chỉ rating hợp lệ trên đúng tin nhắn/session đã reveal  mới cập nhật card, log và lượt ôn. Bấm lặp sau khi chấm bị bỏ qua; lỗi ghi log rollback thay đổi card.
- Chấm một card xong hiển thị menu ngay trong tin nhắn kết quả; chọn Ôn ngay để tiếp tục, không tự gửi card tiếp. Thêm tay, lưu/huỷ lookup, sửa xong và `/cancel` cũng có menu.
- Chạy hồi quy: `uv run pytest -q`. Đây là kiểm thử SQLite/Telegram giả lập, không phải kiểm chứng production.

### Trạng thái nghiệm thu TODO — 24/11/2026

- Target/ngày, quiet hours (start/end), story table, preview từng field + icon, rating `1`–`4` / `?` / `???`, import/export file CSV+JSON, UI English — đã có.
- **Vocabulary**: mở thẳng bảng GFM (`sendRichMessage`), `PAGE_SIZE = 10`, Prev/Next; chỉ Edit/Delete/Search trên bảng (Add ở menu chính). Chọn bằng STT hoặc tên từ; sai giữ trang; trùng tên → lọc để chọn STT. Xoá tất cả chỉ trong Delete + xác nhận. Chi tiết từ có Edit/Delete; xong quay đúng trang/filter.
- Add: EN confirm → pipe format (word+EN+VI bắt buộc khi parse). FSM add không idle-timeout 15s.
- Thẻ mới: `new_card_json` seed **Hard** (không chỉ delay `learning_steps[0]`). Idle FSM **15s**; pending review không timeout; alarm không chen khi FSM mở.
- Xác minh local: `uv run --offline pytest -q` — **229 passed**.

**Còn giới hạn:** clipping nội dung dài; delivery Telegram mạng không xác định. Chưa deploy / UAT Telegram thật (reply nhắc, nhận/upload file export).

## UC1 — Thêm từ (auto EN + format pipe)

**User story:** Thêm từ với định nghĩa EN từ từ điển (tuỳ chọn), rồi điền nốt các trường theo format pipe.

1. Menu ➕ Add hoặc `/add` → hỏi từ. `/add hello` bỏ bước hỏi từ.
2. Lookup chỉ lấy định nghĩa EN. Hiện EN + nút Đồng ý(1) / Manual(2).
3. Đồng ý → template `word||EN|||`. Manual hoặc miss API → `word|||||`. User gõ dòng pipe (chỉ cần điền thiếu); EN+VI bắt buộc khi parse.
4. Preview → confirm/cancel. Một bot message edit-in-place; FSM add không idle-timeout; lệnh khác bị bỏ qua tới khi xong/`/cancel`.
5. Lưu ghi word/card, tăng daily.added và lên lịch.

**Test:** đồng ý/manual/`1`/`2`; miss → format; bulk `|` bỏ lookup; tin format không timeout; `/study` lúc đang add không chen.

---

## UC2 — Thêm từ thủ công (bulk)

**User story:** Tôi dán 1 danh sách từ theo format `từ|phiên âm|defineEN|nghĩaVI|ví dụ|note`,
bot xem trước rồi mới lưu.

**Ví dụ:**

```
User:  /add
Bot:   ➕ Thêm từ
       [🔍 Tra từ điển] [✍️ Nhập thủ công]
User:  (bấm ✍️)
Bot:   Gửi danh sách từ (mỗi dòng một từ):
       từ|phiên âm|defineEN|nghĩaVI|ví dụ|note
User:  dog|/dɒɡ/|a domestic animal|con chó|A dog barks|
       cat||a small animal|con mèo
Bot:   📋 Xem trước 2 từ: ...  [✅ Thêm] [❌ Huỷ]
User:  (bấm ✅)
Bot:   ✅ Đã thêm 2 từ! (Hôm nay: 3/200)
```

**Cơ chế:**
- Parser: dòng có `|` = bản ghi mới; dòng không có `|` = phần bị Telegram
  word-wrap, gộp vào dòng trước. Chỉ trường `word` bắt buộc.
- Dedup theo từ (lowercase, chuẩn hoá khoảng trắng).
- Confirm mới ghi DB (xem trước trước khi ghi — tránh rác dữ liệu).

**Test:** dán 5 dòng, 1 dòng dài bị wrap → vẫn parse đúng số từ. Dòng trùng
từ → chỉ 1. Bấm ❌ → không ghi gì.

---

## UC3 — Quiz vocab và chấm FSRS

**User story:** Nhận nghĩa tiếng Việt và câu ví dụ khuyết đúng vocab; nhập vocab tiếng Anh, sau đó tự chấm mức nhớ.

```text
Bot: 🇻🇳 quả táo
     Điền từ tiếng Anh:
     An _ _ _ _ _ a day keeps the doctor away
     [Gợi ý thêm chữ] [Xem đáp án]
User: apple
Bot: (edit cùng tin) ✅ Chính xác! + thông tin EN/VI
     [Again] [Hard] [Good] [Easy]
User: Good
Bot: (edit cùng tin) Kết quả + lịch tiếp theo + menu
```

- Chỉ vocab bị che, không che các từ khác trong ví dụ. Khớp không phân biệt hoa/thường, có ranh giới từ; mọi lần xuất hiện đều được che. Ví dụ không chứa vocab thì bỏ ví dụ khỏi câu hỏi, dùng nghĩa VI và ô trống; không kiểm tra câu ví dụ thay cho vocab.
- Ô trống hiển thị từng chữ cách 1 space; giữa hai từ cách 3 spaces: `make up` → `_ _ _ _   _ _`. Dùng monospace để giữ khoảng cách, kể cả sau hint.
- Reply hoặc gõ trực tiếp đều nhận khi không có workflow khác. Gợi ý mở dần chữ của vocab; `?`/`???` vẫn hỗ trợ. Không tự chấm dựa trên đúng/sai: luôn hỏi Again/Hard/Good/Easy.
- FSRS chỉ đổi sau rating hợp lệ; card JSON/due, log, daily count và đóng session trong cùng transaction. Bấm lặp không chấm lại. FSRS có fuzzing nên interval nhiều ngày có thể chênh nhẹ giữa hai phép tính độc lập.
- Session được giữ cả sau đáp án để bắt buộc chấm. `/study` khi đang chờ phục hồi cùng câu hoặc cùng bảng chấm, không tạo quiz mới.

## UC4 — Nhắc tự động, một câu đang chờ

- Chỉ một quiz đang chờ trên toàn bot. Lưu reservation KV trước khi gọi Telegram để alarm và `/study` đồng thời không gửi trùng.
- Có quiz chưa trả lời **hoặc chưa chấm**: xoá alarm, không gửi thêm, không timeout tự bỏ câu. Khởi tạo lại DO vẫn giữ pending trong KV.
- Chấm xong mới mở lại alarm: chọn ngẫu nhiên từ đã đến hạn; nếu chưa có thì chờ due gần nhất. Không nhắc từ vừa chấm trước due mới. Có nhiều từ quá hạn thì câu tiếp theo được nhắc khi slot hiện tại đã giải và chấm xong.
- Giờ yên tĩnh áp dụng cả từ quá hạn. Hết quota thì chờ ngày local tiếp theo (và hết giờ yên tĩnh).
- Target 200 là tổng số từ thêm + lượt chấm, **không** là số tin nhắc.
- Xoá từ đang được hỏi thì đóng session cũ và mở lại lịch cho các từ còn lại.
- Test hồi quy: 4 từ, gọi alarm 200 lần → chỉ 1 quiz; gọi lại sau restart vẫn 1; trả lời nhưng chưa chấm vẫn không có quiz tiếp.
- Giới hạn: nếu mạng lỗi không biết Telegram đã nhận chưa, giữ reservation để ưu tiên không spam; chưa có tự phục hồi trường hợp delivery không xác định. Tin spam cũ từ phiên bản trước không tự xoá.

---

## UC5 — Daily target (ngăn dồn đống)

**User story:** Tôi đặt mục tiêu N từ/ngày (mặc định 200) = tổng từ thêm + ôn.
Bot không bắt ôn quá con số đó để không "cháy tài nguyên não".

**Ví dụ:**

```
User:  /settings → 🎯 Target/ngày → gõ 50
User:  (thêm 20 từ mới trong ngày)
User:  /study
Bot:   (chỉ đưa tối đa 30 từ để ôn — 50 − 20 đã add)
       ... sau khi ôn đủ 30:
Bot:   ✅ Đã ôn đủ target hôm nay (50 từ). Nghỉ ngơi đi! 🎉
```

**Cơ chế:**
- Bảng `daily(date, added, reviewed)` — đếm theo **ngày local** (TZ +7).
- `quota ôn = target − added hôm nay − reviewed hôm nay` (floor 0).
- Alarm + `/study` chỉ chọn từ trong quota, chọn **random** từ pool đến hạn
  (xáo trộn — không theo thứ tự add).
- **Vượt target khi add vẫn được** (add tuỳ thời điểm, không chặn) — nhưng mỗi
  từ add làm quota ôn bớt 1.
- Sang ngày mới: hàng `daily` mới, quota reset đầy.

**Test:** target 3, add 2 từ → /study chỉ được 1 lượt ôn → hết → thông báo
nghỉ. Ngày hôm sau (đổi clock) → quota lại đầy.

---

## UC6 — Chế độ quiz thống nhất

Theo yêu cầu sửa ngày 08/11/2026, cả ôn thủ công và nhắc tự động dùng quiz VI → vocab EN. Tuỳ chọn Full và definition/cloze/mix cũ không còn hiển thị trong menu cài đặt; giá trị KV cũ không làm đảo chiều quiz.

---

## UC7 — Games: viết chuyện chêm

**User story:** Học chán, tôi muốn bot rút N từ ngẫu nhiên để tôi viết câu
chuyện chứa chúng — ôn bằng cách dùng.

**Ví dụ:**

```
User:  /games → ✍️ Viết chuyện chêm
Bot:   Muốn rút bao nhiêu từ?
User:  3
Bot:   ✍️ Viết chuyện chêm — 3 từ
       • dog — con chó
       • cherry — ?
       • apple — quả táo
       Viết một câu hoặc đoạn ngắn chứa tất cả các từ trên...
```

**Cơ chế:** `SELECT word, meaning FROM words ORDER BY RANDOM() LIMIT ?` (1 query, không đụng FSRS —
game không ảnh hưởng lịch ôn). Kết quả hiển thị bằng bảng GFM Markdown native (`| STT | Từ | Nghĩa |`) qua Rich Message trên cùng `message_id`; giới hạn 1–20 từ.

**Test:** kho rỗng → "Kho từ đang trống". Gõ 100 hoặc chữ → báo số không hợp lệ ngay trên tin nhắn hiện tại. Gõ 3
khi kho có 5 từ → bảng Markdown 3 từ ngẫu nhiên.

---

## UC8 — Bảng tra cứu, xem, sửa và xoá (CRUD Phương án B)

- `/vocab` mở menu `📚 Kho từ vựng` với đủ 4 thao tác: `➕ Thêm từ`, `👁 Xem`, `✏️ Sửa`, `🗑 Xoá`, `🔎 Tìm kiếm`.
- Chọn `👁 Xem`, `✏️ Sửa` (hoặc `/edit [kw]`), `🗑 Xoá` (hoặc `/delete [kw]`) hiển thị bảng GFM Markdown 30 từ/trang với 5 cột `#`, `Từ`, `IPA`, `Nghĩa`, `Hạn`, kèm nút `⬅️ Trước`, `➡️ Sau`, `🔎 Tìm kiếm`, `✖️ Bỏ lọc` (khi có filter), `◀️ Từ vựng`, `🏠 Menu`.
- Chọn bản ghi bằng cách gõ **STT toàn cục** hoặc **tên từ** (kể cả khi chỉ có 1 kết quả vẫn hiển thị bảng trước). Gõ sai giữ nguyên bảng trang hiện tại kèm cảnh báo; trùng tên từ hiển thị các dòng trùng để chọn theo STT.
- Xem: hiện đầy đủ 6 thuộc tính kèm icon + hạn ôn, có nút `✏️ Sửa` / `🗑 Xoá` cho chính bản ghi đang xem và `◀️ Danh sách`.
- Sửa: chọn dòng → xem đủ 6 thuộc tính hiện tại kèm icon → dùng `✨ Điền thông tin thiếu` hoặc chọn trường `🔤 Từ` / `🔊 Phiên âm` / `🇬🇧 Nghĩa EN` / `🇻🇳 Nghĩa VI` / `📝 Ví dụ` / `ℹ️ Ghi chú` rồi nhập giá trị. Xong hoặc huỷ đều quay về đúng trang & bộ lọc của bảng trước đó.
- Xoá: chọn dòng → xem chi tiết → `🗑 Xoá vĩnh viễn` hoặc `↩️ Giữ lại` (hoặc `🗑 Xoá tất cả` từ bảng Xoá). Xoá dòng cuối ở trang cuối tự động kẹp về trang hợp lệ trước đó.
- Mọi bước bảng, tìm kiếm, chọn, xác nhận, huỷ đều edit cùng tin workflow (`text` ↔ `rich_message` tại chỗ), không xả tin nhắn mới.

## UC9 — Cài đặt và dọn giao diện tạm

Menu cài đặt hiện Target/ngày và Giờ yên tĩnh. Quiz dùng một hướng VI → EN. Add thủ công và tra dictionary giữ `message_id` xuyên suốt các bước để edit; `/cancel` sửa tin workflow thành menu nếu có ID. Không tự xoá tin người học hoặc lịch sử cũ.

---

## UC10 — Bảo mật & whitelist

- Webhook Telegram phải mang header `X-Telegram-Bot-Api-Secret-Token` trùng
  `WEBHOOK_SECRET` (đặt khi `setWebhook`) → không thì 403.
- Mọi update từ user khác `OWNER_ID` bị **bỏ qua im lặng**.
- Token bot + secret chỉ nằm trong Cloudflare secrets, không trong code/git.

**Test:** gửi update với user_id lạ → không có phản hồi gì. Curl thiếu header
secret → "forbidden".

---

## Phụ lục: bảng dữ liệu

| Bảng | Nội dung | Ai ghi |
|---|---|---|
| `words` | từ, IPA, nghĩa VI, ví dụ, note | add/edit/delete |
| `cards` | card FSRS JSON + `due` (copy để index) | review |
| `reviews` | log mỗi lần chấm (card, rating, thời điểm) | review |
| `daily` | đếm added/reviewed theo ngày local | add + review |
| KV `set:*` | settings (mode, quiet, target, reminder_mode) | settings |
| KV `fsm:*` | dialog đang dở (add, lookup, edit...) | mọi flow nhiều bước |
| KV `session:*` | trạng thái prompt ôn gắn với message_id | review |

**Lưu ý cho tester về môi trường:**
- Test tự động: `uv run pytest` (67 test, fake toàn bộ Workers runtime).
- Test runtime thật: `wrangler dev` + `scripts/tg_mock.py` + `.dev.vars` có
  `TG_API_BASE=http://127.0.0.1:9999`; giả lập update bằng curl POST
  `/telegram` với header secret.
- DB production nằm trong Durable Object trên Cloudflare — không có file
  local để xem; local dev là SQLite in-memory (mất khi restart).
