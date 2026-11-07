# Use cases + mô tả hoạt động — Vocabking

> Tài liệu cho tester: mỗi use case có user story, ví dụ cụ thể, và cơ chế
> hoạt động bên trong. Đọc theo thứ tự cũng chính là thứ tự trải nghiệm thật.

---

## UC1 — Thêm từ bằng tra từ điển

**User story:** Với tư cách người học, tôi gõ 1 từ tiếng Anh, bot tự tra IPA +
định nghĩa gốc, tôi tự gõ nghĩa tiếng Việt (để bắt buộc não phải xử lý từ),
chọn ví dụ, và từ đó vào lịch ôn FSRS.

**Ví dụ:**

```
User:  apple
Bot:   🔍 apple /ˈæp.əl/ — noun
       💡 A common, firm, round fruit produced by a tree of the genus Malus.
       🇻🇳 Gõ nghĩa tiếng Việt cho apple:
User:  quả táo
Bot:   📝 Thêm ví dụ cho apple:
       [📖 Lấy ví dụ từ điển] [✍️ Tự nhập ví dụ] [⏭ Bỏ qua ví dụ]
User:  (bấm 📖)
Bot:   (edit chính tin nhắn đó) → preview tổng hợp + [✅ Lưu từ] [❌ Huỷ]
User:  (bấm ✅)
Bot:   ✅ Đã thêm 1 từ! (Hôm nay: 1/200)
```

**Cơ chế:**
1. Tin nhắn không có lệnh `/`, không có dialog đang dở, toàn ký tự ASCII chữ
   cái → được coi là từ cần tra → gọi `freedictionaryapi.com/api/v1/entries/en/{word}`
   (fetch thật ra ngoài; lỗi/mất mạng → "Không tìm thấy").
2. Bot lưu FSM `lookup_vi` (chứa kết quả API) trong KV — Worker stateless.
3. Ý nghĩa VI user gõ tay — **không** dịch tự động (quyết định sản phẩm: tự gõ
   = nhớ sâu hơn; IPA/def EN thì máy làm vì khách quan).
4. Chọn ví dụ: `📖` lấy example trong response API (nếu API không có → tự
   nhập), `✍️` hỏi user gõ, `⏭` bỏ qua.
5. Lưu: 1 lần INSERT multi-row vào `words` + 1 lần vào `cards` (card FSRS mới,
   `due = now`) → `daily.added` +1 → reschedule alarm.

**Test kiểm tra:** gõ từ sai chính tả (`applee`) → "Không tìm thấy". Gõ từ có
nghĩa → flow 4 bước. Mất mạng → không crash, chỉ báo không tìm thấy.

---

## UC2 — Thêm từ thủ công (bulk)

**User story:** Tôi dán 1 danh sách từ theo format `từ|phiên âm|nghĩa|ví dụ|note`,
bot xem trước rồi mới lưu.

**Ví dụ:**

```
User:  /add
Bot:   ➕ Thêm từ
       [🔍 Tra từ điển] [✍️ Nhập thủ công]
User:  (bấm ✍️)
Bot:   Gửi danh sách từ (mỗi dòng một từ):
       từ|phiên âm|nghĩa|ví dụ|note
User:  dog|/dɒɡ/|con chó|A dog barks| 
       cat||con mèo
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

## UC3 — Ôn theo lịch FSRS (quiz mode)

**User story:** Đến giờ, bot nhắc 1 từ; tôi trả lời, chấm mức nhớ, thuật toán
FSRS tính lần nhắc tiếp theo.

**Ví dụ (chế độ định nghĩa):**

```
Bot:   📖 elephant
       Nghĩa là gì? 👇
       (user reply tin nhắn này)
User:  con voi
Bot:   (edit tin nhắn) ✅ Chính xác! "elephant" 💡 con voi
       [😖 Again] [🙁 Hard] [🙂 Good] [😎 Easy]
User:  (bấm 🙂)
Bot:   🔖 elephant — đã chấm Good
       ⏰ Nhắc lại sau: vài phút (đang trong bước học)
       📊 Hôm nay: 2/200
       (bot tự gửi prompt từ kế tiếp nếu còn quota)
```

**Ví dụ (chế độ điền khuyết — cloze):**

```
Bot:   Điền từ vào chỗ trống:
       An a____ a day keeps the d____ a____
       Gợi ý: quả táo
       (user reply)
User:  ?
Bot:   An app__ a day ...   ← lộ thêm ~25% số chữ còn ẩn
User:  ???
Bot:   🔓 full answer + nghĩa + [4 nút chấm]
```

**Cơ chế FSRS (quan trọng cho tester):**
- Mỗi từ có 1 **Card FSRS** (state: stability, difficulty, due, last_review)
  serialize JSON trong bảng `cards`.
- **Again** → nhắc lại trong vài phút (cùng ngày).
- **Hard/Good** vài lần đầu → learning steps, interval theo **phút** (không
  phải ngày!) → đây là hành vi đúng của FSRS, không phải bug.
- Sau khi ra khỏi learning steps, interval tăng theo ngày: ~1 → ~3 → ~7 →
  ~15+... tùy lịch sử chấm.
- **Easy** nhảy interval dài hơn so với Good cùng thời điểm.
- Mỗi lần chấm: `reviews` +1 hàng (log), `cards.card_json` + `cards.due`
  update, `daily.reviewed` +1.

**Cơ chế hint `?`:** thuật toán **max-min-distance** — chữ mới lộ luôn nằm ở
khoảng trống xa nhất so với chữ đã lộ (không dồn cụm). Khi nhiều vị trí xa
nhau ngang nhau → **nguyên âm được ưu tiên** (a/e/i/o/u/y — lộ "khung" từ
trước). Deterministic theo seed = card_id + số lần reveal → cùng trạng thái
luôn render giống nhau. `?` mỗi lần lộ ~25% số chữ còn ẩn. `???` lộ hết.

**Test kiểm tra:** chấm Again → nhắc lại rất sớm. Chấm Good 2 lần đầu →
interval "vài phút". `?` nhiều lần → mỗi lần thấy thêm chữ, không bao giờ
bớt chữ đã lộ. `???` → hiện đủ + nút chấm.

---

## UC4 — Nhắc tự động 24/7 (alarm)

**User story:** Tôi không cần nhớ ôn — bot tự gửi 1 từ đúng lịch, kể cả khi
tôi không mở app Telegram.

**Ví dụ:** 09:00 sáng bot tự nhắn prompt ôn từ `elephant` (đến hạn lúc 08:45).

**Cơ chế:**
- DO alarm API: sau mỗi review/add, `setAlarm(mốc due kế tiếp)`. Khi đến giờ,
  runtime gọi `alarm()` → gửi prompt 1 từ (đúng 1, không spam).
- **Giờ yên tĩnh** (mặc định 23:00–07:00 VN, đổi được): từ đến hạn ban đêm
  bị dồn sang 7:00 sáng hôm sau.
- Alarm chỉ retry 6 lần nếu handler fail — code catch + reschedule trong
  `finally` để không mất nhắc.

**Test:** set giờ yên tĩnh 00:00–06:00, chấm 1 từ Again lúc 01:00 → bot im
lặng, 06:00 sáng nhận nhắc.

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

## UC6 — Nhắc kiểu Full (lướt nhanh)

**User story:** Khi từ đã khá thuộc, tôi muốn bot gửi thẳng toàn bộ thông tin
(nghĩa + ví dụ), tôi chỉ chấm mức nhớ mà không phải trả lời.

**Ví dụ:**

```
Bot:   🔔 Ôn: apple
       💡 Nghĩa: quả táo
       📝 I eat an apple every morning
       Tự chấm mức nhớ 👇
       [😖 Again] [🙁 Hard] [🙂 Good] [😎 Easy]
```

**Cơ chế:** `reminder_mode = full` → `send_prompt` render full info + nút rate
ngay (session mode `full` không nhận reply `?`/`???`). Chấm vẫn update FSRS
đầy đủ như quiz mode.

**Test:** đổi mode full trong /settings → /study → tin nhắn có sẵn nghĩa.
Reply `?` vào tin full → bị bỏ qua (không phải cloze).

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

**Cơ chế:** `random.sample` trên toàn bộ `words` (1 query, không đụng FSRS —
game không ảnh hưởng lịch ôn). Giới hạn 1–20 từ.

**Test:** kho rỗng → "Kho từ đang trống". Gõ 100 → báo số không hợp lệ. Gõ 3
khi kho có 5 từ → 3 từ ngẫu nhiên khác nhau mỗi lần gọi.

---

## UC8 — Sửa / xoá từ

**Ví dụ:**

```
User:  /edit app
Bot:   (nếu 1 kết quả) ✏️ Sửa từ: apple — Chọn trường cần sửa: [Từ][Phiên âm][Nghĩa][Ví dụ][Note]
User:  (bấm Nghĩa)
Bot:   Gửi nội dung mới cho Nghĩa của apple:
User:  quả táo đỏ
Bot:   ✅ Đã cập nhật Nghĩa = quả táo đỏ
```

**Cơ chế:** search LIKE trên `word` + `meaning`, ≤10 kết quả, 1 kết quả thì
thẳng sang chọn trường. Nhập `-` / `null` / `none` = xoá trắng trường đó.
Xoá từ: cascade card + toàn bộ lịch sử review.

---

## UC9 — Cài đặt

`/settings` 1 màn hình tổng quan → 4 mục (mỗi mục edit tại chỗ, có nút quay
lại): Target/ngày (gõ số), Kiểu nhắc (quiz/full), Giờ yên tĩnh (3 preset),
Chế độ ôn (definition/cloze/mix).

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
