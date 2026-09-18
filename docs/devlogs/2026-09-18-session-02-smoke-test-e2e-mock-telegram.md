# Devlog #2 — Hoàn thiện test + smoke-test E2E qua mock Telegram API

> **Ngày:** 18/09/2026 · **Session:** tiếp nối devlog #1 (checklist §14)
> **Trạng thái cuối session:** **67/67 tests pass** · smoke-test E2E qua `wrangler dev` **pass toàn bộ flow** (add → confirm → study → reply → rate → settings → help) · **3 bug runtime thật được tìm ra nhờ smoke test** (không test nào bắt được).

---

## 1. Checklist §14 của session trước — đã xong

- [x] Sửa test flaky `test_alarm_tick_quiet_sends_nothing` (inject đồng hồ giả qua monkeypatch `now_utc`)
- [x] `uv run pytest` → 67/67 (thêm 1 test mới: daytime counterpart)
- [x] Smoke test `wrangler dev` sau đợt đổi import — **phát hiện thêm 3 bug runtime** (§3)
- [ ] Thu hồi bot token cũ (@BotFather) — **user tự làm**
- [ ] `wrangler secret put` + `wrangler deploy` + setWebhook — **cần token thật, user tự làm**
- [ ] E2E thật trên Telegram — **chờ deploy**
- [x] Git commit đầu tiên (`.dev.vars` đã được ignore từ trước, kiểm tra bằng `git check-ignore`)

---

## 2. Fix test flaky — hai cạm bẫy trong một test

Fix theo hướng devlog #1 đề xuất (monkeypatch `now_utc`), nhưng vấp **cạm bẫy thứ hai** không nằm trong đề xuất ban đầu:

```python
# SAI NGẦM — patch đồng hồ SAU khi thêm từ:
do = _fresh()
feed_msg(do, "/add w1|m1")   # due được ghi bằng ĐỒNG HỒ THẬT (2026-09-18)
feed_cb(do, "add:confirm")
monkeypatch.setattr(vocab_do, "now_utc", lambda: pinned_past)  # pin về quá khứ
asyncio.run(do._alarm_tick())
# → _pick_due() so due (tương lai của pinned clock) <= now → KHÔNG thấy card → assert sai kiểu khác

# ĐÚNG — patch đồng hồ TRƯỚC KHI thêm từ:
monkeypatch.setattr(vocab_do, "now_utc", lambda: quiet_time)
do = _fresh()
feed_msg(do, "/add w1|m1")   # due giờ cũng nằm trên pinned clock
feed_cb(do, "add:confirm")
```

**Bài học:** khi inject đồng hồ giả, mọi timestamp được ghi trong lúc setup test cũng phải đi qua đồng hồ giả. Patch **trước**, setup **sau**.

Thêm test đối xứng `test_alarm_tick_daytime_sends_prompt` (pin giờ ban ngày → phải gửi prompt) để phủ cả hai nhánh, không chỉ nhánh quiet.

---

## 3. Smoke test tìm ra 3 bug mà 67 test không bắt được

Setup: chạy `wrangler dev`, curl giả lập update Telegram với header `X-Telegram-Bot-Api-Secret-Token`, và **mock Telegram API** (HTTP server thuần Python trên `127.0.0.1:9999`, ghi log mọi call ra `/tmp/tg_calls.log`). Bot trỏ tới mock qua `TG_API_BASE` env var (`src/telegram.py` đọc env này; không set → dùng API thật).

Cách xem lỗi của Python Workers mà không cần console: **Local Explorer observability API** của wrangler:
```bash
curl -s -X POST http://localhost:8787/cdn-cgi/local/explorer/api/local/observability/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT rowid, message FROM logs ORDER BY rowid DESC LIMIT 20"}'
# Traceback Python nằm trong `message`; wasm noise cắt tại "at new_error"
```
Điểm mù: `print()` từ Python **không hiện** trong logs này — chỉ exception bị catch rồi `print(repr(e))` mới xuất hiện (qua console API của runtime).

### Bug A — `do.storage.get()` vs `do.storage.kv.get()` (add confirm chết im lặng)

`handlers/add.py:36` dùng `do.storage.get("fsm:111")` trong khi toàn codebase dùng `do.storage.kv.get(...)`. Trên runtime thật `storage.get` là **async** → trả coroutine → `fsm.get(...)` nổ `AttributeError: 'coroutine' object has no attribute 'get'` → `handle_update` catch và print → **confirm thêm từ im lặng không hoạt động**. Test fake (`conftest._Storage`) alias `kv = self` nên cả hai đường đều "chạy được" → test không bắt được.

Fix: `add.py` + `settings.py` (5 chỗ `storage.put`) đồng bộ hết sang `.kv`.

**Bài học:** khi fixture fake cho phép 2 API trông giống nhau, nhất quán phải được enforce bằng review/grep, không thể dựa vào test. `grep -rn "storage\.\(get\|put\|delete\)(" src/ | grep -v "\.kv"` giờ là check bắt buộc trước khi commit.

### Bug B — `cur.last_insert_rowid` không tồn tại trên DO SQL thật

`vocab_do.insert_word` dùng `cur.last_insert_rowid` (API của sqlite3/Python chuẩn). Runtime thật: `AttributeError('last_insert_rowid')` → word được INSERT nhưng **card không được tạo** → từ "ma" không bao giờ đến hạn ôn. Docs DO SQLite (SqlStorageCursor) chỉ có `columnNames`/`rowsRead`/`rowsWritten` — **không có last rowid**.

Fix — đọc lại bằng SELECT (an toàn vì SQL của DO là sync + private, không race):
```python
self.storage.sql.exec("INSERT INTO words ... VALUES (...)", ...)
rows = list(self.storage.sql.exec("SELECT MAX(id) AS id FROM words"))
word_id = rows[0].id if rows else 0
```
Conftest fake vẫn giả lập `last_insert_rowid` (giữ cho cursor fake giống sqlite3), nhưng code production không dùng nữa.

**Bài học:** giống bug #4/#5 devlog #1 — fake SQL API nào cũng lệch thật ở đâu đó. Mọi API "tiện lợi" của sqlite3 phải đối chiếu docs DO trước khi dùng.

### Bug C — whitelist chặn mọi update khi `OWNER_ID="0"` (silent)

`wrangler.jsonc` để `OWNER_ID: "0"` → `str(from.id) != "0"` đúng với mọi user → mọi update bị bỏ qua im lặng (thiết kế đúng, cấu hình sai). Không có lỗi nào trong log vì đây là behavior.

Fix: set `OWNER_ID`/`OWNER_CHAT_ID` = "111" (test) + TODO comment trong `wrangler.jsonc` nhắc thay ID thật trước deploy.

**Bài học:** biến whitelist dạng "giá trị rác vẫn chạy" cần fail-loud: cân nhắc log warning 1 lần khi `OWNER_ID` không parse được thành int ≠ 0. (Chưa làm — ghi vào việc cần.)

### Bài học chung lớn nhất của session

**67 test xanh ≠ chạy được.** Cả 3 bug đều nằm ở ranh giới giữa code và platform (async KV, SQL cursor, env config) — đúng chỗ mà fake không mô phỏng được. Chi phí setup mock + wrangler dev + observability query (~30 phút) đổi lại bắt 3 bug sẽ rất khó debug trên production thật (đặc biệt Bug A/B: hiện tượng là "bot im lặng", không có traceback đâu cả).

---

## 4. Hạ tầng test mới (giữ lại cho session sau)

- **Mock Telegram API** — script ~25 dòng (HTTPServer), log payload ra file. Đặt ở `/tmp` là đủ; muốn giữ thì copy vào `scripts/tg_mock.py`.
- **`TG_API_BASE` env** (`src/telegram.py`) — redirect toàn bộ Bot API call. Không set trong production = không ảnh hưởng.
- **Observability query** — xem traceback Python của `wrangler dev` mà không cần mở console.

Chuỗi E2E đã verify qua mock (tất cả pass):
```
/menu → keyboard ok
/add w2|... → preview + Confirm/Cancel
add:confirm → "✅ Đã thêm 1 từ" + alarm set +60s
/study → prompt định nghĩa + REPLY_HINT
reply sai → "❌ Chưa đúng. Đáp án: w2"
reply "e2" đúng → "✅ Chính xác!" + 4 nút rating
rate:1:good → "🔖 w2 — đã chấm Good 🙂 / ⏰ vài phút" (FSRS learning step)
/help → full hướng dẫn
/settings → mode + quiet hours
quiet:off → "✅ Giờ yên tĩnh: tắt"
```

---

## 5. Việc còn lại (cho session deploy)

1. User: thu hồi token cũ qua @BotFather (devlog #1 §12).
2. `wrangler.jsonc`: thay `OWNER_ID` = Telegram user ID thật (lấy từ @userinfobot).
3. `wrangler secret put BOT_TOKEN` + `wrangler secret put WEBHOOK_SECRET`.
4. `wrangler deploy` → `setWebhook` với `secret_token`.
5. E2E trên Telegram thật (cùng chuỗi flow như §4).
6. Test alarm thật: review Again → chờ ~1 phút → bot nhắc.
7. Cân nhắc: fail-loud warning khi OWNER_ID=0 (§3 Bug C).
