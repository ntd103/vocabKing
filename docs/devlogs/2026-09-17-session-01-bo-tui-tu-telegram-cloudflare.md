# Devlog #1 — Vocaboss: bot học từ vựng Telegram trên Cloudflare Workers (Python)

> **Ngày:** 17/09/2026 · **Session:** brainstorming → plan → code (bị ngắt giữa chừng do compacting treo)
> **Trạng thái cuối session:** 66 tests, **65 pass / 1 fail** (flaky vì giờ thật). Runtime Cloudflare đã load được Python nhưng **chưa verify xong webhook end-to-end**.
> Mọi code dưới đây trích nguyên văn từ transcript session (`~/.claude/projects/-home-lin-repos-vocabking/df73c3a1-*.jsonl`).

---

## 1. Tiến độ

**Đã xong:** plan (lưu `docs/plans/`), module thuần hàm + tests (`cloze`, `word_parser`, `fsrs_service`), DO chính (`vocab_do.py` — 5 bảng SQL, router, alarm + quiet hours), handlers (add/edit/delete/review/settings), entrypoint + telegram client, integration test suite (conftest stub module `workers` + fake DO storage + capture Telegram calls).

**Chưa xong:** 1 test flaky (§2.2), chưa smoke-test lại sau đợt đổi import, chưa deploy/webhook thật, chưa có `/help` + error handler.

---

## 2. Bug #1 — Test flaky đọc đồng hồ thật ⚠️ CHƯA SỬA

### Hiện tượng
`test_alarm_tick_quiet_sends_nothing` **pass lúc 23h VN nhưng fail lúc 12h VN** (tôi chạy lại xác nhận: fail lúc 01:06 EDT):

```python
# tests/test_vocab_do.py — BUG ĐANG TỒN TẠI
def test_alarm_tick_quiet_sends_nothing(self):
    do = _fresh()
    feed_msg(do, "/add w1|m1")
    feed_cb(do, "add:confirm")
    do.env.sent.clear()
    asyncio.run(do._alarm_tick())  # right now (23h VN) it's quiet by default
    assert send_count(do) == 0     # ❌ FAIL ban ngày: is_quiet()=False → alarm gửi tin → count=1
```

### Root cause
Test dựa vào **đồng hồ thật**: comment "right now (23h VN)" chỉ đúng khi viết test. Quiet window mặc định 23:00–07:00 (`vocab_do.py:47`) — ban ngày `is_quiet()` trả `False` → `_alarm_tick` gửi prompt → assert fail.

Logic bị test (đúng):
```python
async def _alarm_tick(self):
    now = now_utc()
    if self.is_quiet(now):
        return  # _reschedule() sets the wake-up alarm
    ...

def local_hour(self, dt: datetime) -> int:
    return (dt.hour + self._tz_offset()) % 24   # TZ_OFFSET_HOURS=7 (VN)
```

### Cách sửa đề xuất (chưa làm)
Inject đồng hồ: `_alarm_tick(now=None)` hoặc monkeypatch `vocab_do.now_utc` trong test:
```python
def test_alarm_tick_quiet_sends_nothing(self, monkeypatch):
    do = _fresh()
    feed_msg(do, "/add w1|m1"); feed_cb(do, "add:confirm")
    do.env.sent.clear()
    quiet_time = dt.datetime(2026, 9, 17, 23, 30, tzinfo=dt.timezone.utc)  # 23:30 UTC → 06:30+7... tự chọn mốc trong window
    monkeypatch.setattr("vocab_do.now_utc", lambda: quiet_time)
    asyncio.run(do._alarm_tick())
    assert send_count(do) == 0
```

### Bài học
**Test phụ thuộc thời gian phải kiểm soát thời gian, không được đọc đồng hồ thật.** Test "pass" khi viết lúc 23h đêm là bẫy kinh điển — nó chỉ pass trong khung giờ nhất định trong ngày.

---

## 3. Bug #2 — Heuristic gộp dòng wrap: đi vòng 3 lần rồi quay về quy tắc đơn giản nhất

Bài toán: Telegram tự wrap tin nhắn dài; user bulk-add nhiều từ mỗi dòng dạng `word|phonetic|meaning|example|note` → cần biết dòng nào là bản ghi mới, dòng nào là phần bị wrap.

### V1 (ban đầu) — đơn giản, nhưng sai trường hợp note tự bắt đầu bằng `|`
```python
def join_wrapped_lines(text: str) -> list[str]:
    """Split input into logical records. A line without `|` continues the
    previous record (Telegram hard-wraps long messages)."""
    records: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "|" in line or not records:
            records.append(line)
        else:
            records[-1] += " " + line
    return records
```

### V2 (edit #10) — heuristic "thông minh hơn": đếm pipe
```python
def join_wrapped_lines(text: str) -> list[str]:
    """A record is complete once it contains FIELD_COUNT-1 pipes. Any following
    line while the current record is incomplete is a wrap continuation."""
    records: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not records:
            records.append(line)
        elif records[-1].count("|") < FIELD_COUNT - 1:
            records[-1] += " " + line   # record chưa đủ cột → dòng tiếp là wrap
        else:
            records.append(line)
    return records
```
Vẫn fail test: dòng wrap **chứa `|`** (vd note bị wrap giữa hai trường) vẫn bị tách nhầm.

### V3 (edit #14, bản cuối) — quay về V1 và **document hóa giới hạn**
```python
def join_wrapped_lines(text: str) -> list[str]:
    """Rule (kept simple & predictable — documented in /help):
    - a line containing `|` starts a new record
    - a line WITHOUT `|` is a Telegram wrap continuation of the previous record
    (so wrapped content itself must not contain `|`).
    """
    records: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "|" in line or not records:
            records.append(line)
        else:
            records[-1] += " " + line
    return records
```

### Bài học
Heuristic "đủ cột mới coi là record" **không giải được** trường hợp dòng wrap tự chứa `|` — không có thông tin nào phân biệt được. Chọn quy tắc **đơn giản, đoán được, document được trong /help** ("nội dung wrap không được chứa `|`") thay vì heuristic thông minh nhưng khó đoán. 2 fixture test được sửa cho khớp quy tắc.

---

## 4. Bug #3 — py-fsrs 6.x bỏ `scheduled_days`

### Hiện tượng
Code dựa trên trí nhớ về API cũ:
```python
# TRƯỚC — crash/luôn ra 0 trên py-fsrs 6.x
scheduled_days = getattr(updated, "scheduled_days", 0)
return updated, int(scheduled_days)
```

### SAU (edit #24) — tự tính từ `due - last_review`
```python
def review(card: Card, rating_key: str, when: datetime | None = None) -> tuple[Card, int]:
    """Apply a rating to a card. Returns (updated_card, scheduled_days).

    `when` defaults to now(UTC). `scheduled_days` is the interval until next
    due, in whole days (0 for minute-level learning steps).
    """
    rating = RATINGS[rating_key]
    updated, _log = _SCHEDULER.review_card(
        card, rating, review_datetime=when or datetime.now(timezone.utc),
    )
    scheduled_days = 0
    if updated.last_review:
        scheduled_days = max(0, (updated.due - updated.last_review).days)
    return updated, scheduled_days
```

Kèm theo: test `test_repeated_good_grows_interval` viết sai hành vi FSRS — 1–2 lần Good đầu chỉ schedule theo **phút** (learning steps), không phải ngày.

```python
# TRƯỚC — giả định sai: Good đầu tiên đã ra ngày
d1, days1 = review(card, "good", when=now)
d2, days2 = review(d1, "good", when=now + timedelta(days=days1))
assert days2 > days1   # ❌ days1=0 (learning step theo phút)

# SAU — mô phỏng tiến trình học thật: review ĐÚNG LÚC DUE, đi qua đủ 8 lần
card = Card()
when = datetime.now(timezone.utc)
days_seen = []
for _ in range(8):
    card, days = review(card, "good", when=when)
    days_seen.append(days)
    when = card.due  # review at exactly due time each round
assert max(days_seen) > 0        # eventually leaves learning steps
assert days_seen[-1] > days_seen[0]  # interval grows
```

### Bài học
1. **Đọc SDK đã cài trong venv trước khi code** — đừng tin trí nhớ API (thư viện version 6.x đã đổi so với thời được train).
2. Test phải phản ánh **hành vi thật của thư viện**, không phải hành vi mình *muốn*. Với spaced repetition, "review ngay lập tức liên tục" ≠ "review theo lịch" — phải `when = card.due`.

---

## 5. Bug #4 — DO SQLite: `cur.one()` vs rows / dict vs attribute

### Hiện tượng
`AttributeError` hàng loạt khi truy cập row. API thật của DO SQL trả row truy cập bằng **attribute** (`row.word`), không phải dict (`row["word"]`); và cursor cần `list()` hoá trước khi index.

```python
# TRƯỚC — giả định cur.one() tồn tại + row là dict
def word_row(self, word_id: int):
    cur = self.storage.sql.exec(
        "SELECT id, word, phonetic, meaning, example, note FROM words WHERE id = ?",
        word_id,
    )
    return cur.one() if cur else None
# ... dùng nơi khác: word["word"] → AttributeError

# SAU — bulk-patch sang rows + attribute access
def word_row(self, word_id: int):
    rows = list(self.storage.sql.exec(
        "SELECT id, word, phonetic, meaning, example, note FROM words WHERE id = ?",
        word_id,
    ))
    return rows[0] if rows else None
# ... word.word
```

Cả handler `_pick_due` cũng sửa cùng pattern:
```python
# TRƯỚC (src/handlers/review.py)
cur = do.storage.sql.exec("SELECT ... WHERE due <= ? ORDER BY due LIMIT 1", now)
return cur.one() if cur else None

# SAU
rows = list(do.storage.sql.exec("SELECT ... WHERE due <= ? ORDER BY due LIMIT 1", now))
return rows[0] if rows else None
```

### Bài học
**Tra docs một lần, chọn một convention, sửa nhất quán toàn bộ codebase** (bằng script, đừng sửa tay từng chỗ). Trộn lẫn `cur.one()`/`rows[0]` hay `row["x"]`/`row.x` là mỏ lỗi.

---

## 6. Bug #5 — Conftest stub SQL bị return sớm → chỉ tạo 1/5 bảng

### Hiện tượng
Hàng loạt test DO fail: `RuntimeError: expected 1 row, got 0` (`tests/conftest.py:79`). Triệu chứng nhìn như bug nghiệp vụ.

### Root cause
Stub của `storage.sql.exec` **return ngay sau statement đầu tiên** — script `SCHEMA` gồm nhiều `CREATE TABLE` cách nhau bởi `;`, nên chỉ bảng `words` được tạo.

```python
# TRƯỚC (tests/conftest.py) — chỉ chạy statement đầu rồi return
def _execute(self):
    cur = self._conn.execute(self._sql, self._args)   # "CREATE TABLE words...; CREATE TABLE cards...;" → chạy cả cụm? Không — sqlite3.execute chỉ chạy lệnh đầu
    ...

# SAU (edit #41-43) — split theo ";" và chạy từng statement, trả Row chuẩn
def _execute(self):
    statements = [s.strip() for s in self._sql.split(";") if s.strip()]
    cur = None
    wrote = False
    for stmt in statements:
        ...
```

### Hành trình debug (đáng học)
Đây là chuỗi iterate dài nhất session — từ **20 failed** xuống 1:
```
20 failed → "synced KV fake" (storage.put → storage.kv.put) → 14 failed
→ "vocab_do helpers now tolerate empty results" → 9 failed
→ "fixed result order" / "appended correct result to sent entry" → 9 failed
→ "fixed remaining test issues" / "added OWNER_CHAT_ID to FakeEnv" → 7 failed
→ "fixed fake json to be awaitable" (Response.json() là coroutine — phải await) → 4 failed
→ "conftest now splits statements" → 1 failed (test flaky §2)
```
Kèm script debug đáng học — tái lập đúng những gì `__init__` của DO làm, in ra bảng nào tồn tại:
```bash
uv run python -c "
import sys, types; sys.path.insert(0, '.'); sys.path.insert(0, 'tests')
import conftest; conftest._install_workers_stub()
from conftest import _Ctx
from src.vocab_do import SCHEMA
ctx = _Ctx()
cur = ctx.storage.sql.exec(SCHEMA)
print('tables:', [r.name for r in ctx.storage.sql.exec(\"SELECT name FROM sqlite_master WHERE type='table'\")])
"
# → chỉ thấy 'words' → tới ngay root cause
```

### Bài học
1. **Fixture/stub là nơi nghi ngờ đầu tiên** khi nhiều test fail cùng lúc với triệu chứng lạ — đừng mò sửa code nghiệp vụ.
2. **Viết script tái lập tối thiểu** (in state trung gian: bảng nào tồn tại, session key gì) nhanh hơn đoán mò nhiều lần chạy full test suite.
3. Chi tiết API dễ trượt: `sqlite3.execute()` chỉ chạy **một** statement; `Response.json()` là async.

---

## 7. Bug #6 — `stub.fetch(request)` nổ JsException trong Python Workers

### Hiện tượng (log thật từ `wrangler dev`)
```
pyodide.ffi.JsException: Error: internal error; reference = cvfh41d06lub3ulda13cp27a
  File "/session/metadata/python_modules/workers/rpc.py", line 295, in await_and_convert
[wrangler:info] POST /telegram 500 Internal Server Error (57ms)
```
EntryPoint forward raw HTTP request vào DO qua `stub.fetch(request)` — pattern chuẩn của JS Workers — nhưng **known limitation** của Python Workers.

### SAU — chuyển sang kiến trúc RPC (rewrite `src/entrypoint.py`)
```python
"""Worker entrypoint: verify the Telegram webhook secret, forward to the DO.

Uses RPC (a plain method call on the DO stub) instead of forwarding the raw
HTTP request — RPC is the recommended way to talk to a DO from a Worker.
"""
from workers import Response, WorkerEntrypoint

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        expected = self.env.WEBHOOK_SECRET
        if not expected or secret != expected:
            return Response("forbidden", status=403)
        update = await request.json()
        stub = self.env.VOCAB_DO.getByName("owner")
        await stub.handle_update(update)      # RPC method — KHÔNG forward request
        return Response("ok")
```

### Bài học
Pattern "chuẩn" của platform JS không tự áp dụng được sang Python Workers. Khi runtime nổ lỗi mù mờ (`internal error; reference = ...`), **tra docs tìm pattern được khuyến nghị** — kiến trúc RPC cuối cùng còn sạch hơn (entrypoint parse JSON 1 lần, DO nhận dict).

---

## 8. Bug #7 — "no such Durable Object" → DO class phải re-export ở entrypoint

### Hiện tượng
Wrangler báo không tìm thấy `VocabularyDO` dù class có trong `src/vocab_do.py`.

### SAU (edit #49)
```python
# The DO class must be re-exported from the worker's main module.
from vocab_do import VocabularyDO  # noqa: F401 — re-export for wrangler
```
Kèm config `wrangler.jsonc` (đã đúng từ đầu):
```jsonc
"durable_objects": { "bindings": [{ "name": "VOCAB_DO", "class_name": "VocabularyDO" }] },
"migrations": [{ "tag": "v1", "new_sqlite_classes": ["VocabularyDO"] }]
```

### Bài học
Wrangler chỉ quét export ở **main module** (`"main": "src/entrypoint.py"`). Class định nghĩa file khác → phải re-export. `noqa: F401` vì import "vô dụng" này là chủ đích.

---

## 9. Bug #8 — `ModuleNotFoundError: No module named 'src'` (runtime chết khi start)

### Hiện tượng
Sau khi thêm re-export, `wrangler dev` chết ngay khi khởi động:
```
✘ [ERROR] service core:user:vocabking: Uncaught Error: PythonError:
  File "/session/metadata/entrypoint.py", line 10, in <module>
    from src.vocab_do import VocabularyDO
ModuleNotFoundError: No module named 'src'
```

### Root cause
Khi entrypoint nằm trong `src/`, **wrangler bundle các module trong `src/` thành root** — import phải là `from vocab_do import ...` chứ không phải `from src.vocab_do import ...`. pytest thì ngược lại (chạy từ repo root, thấy `src/` là package).

### SAU — bulk patch một lần cho toàn `src/` (9 file):
```bash
python3 - <<'EOF'
import pathlib, re
for p in pathlib.Path("src").rglob("*.py"):
    s = p.read_text()
    s2 = re.sub(r"\bfrom src\.([a-zA-Z_][\w.]*)", r"from \1", s)
    s2 = re.sub(r"\bimport src\.([a-zA-Z_][\w.]*)", r"import \1", s2)
    if s2 != s:
        p.write_text(s2); print("patched", p)
EOF
```
Và conftest thêm path shim để test import được cả hai tên:
```python
# tests/conftest.py
sys.path.insert(0, ".")
sys.path.insert(0, "src")
# ... và đổi "import src.telegram as tg" → "import telegram as tg" trong _patch_telegram_fetch
```

### Hệ quả dây chuyền
Đổi module name → conftest patch nhầm tên → 27 test fail → shim → còn 1 (flaky §2). Session dừng đúng lúc này.

### Bài học
1. **Import path trong runtime bundler (workerd/Pyodide) ≠ import path pytest.** Đặt entrypoint ở root repo có thể tránh hẳn vấn đề này — cân nhắc từ đầu cấu trúc dự án.
2. Đổi import hàng loạt = luôn chạy lại **toàn bộ** test suite ngay sau đó, đừng để dồn.

---

## 10. Bug #9 — Delete không cascade: card còn sót sau khi xoá word

### Hiện tượng (`test_delete_flow` fail)
```
assert do.word_row(1) is None      # ✓ word đã xoá
> assert do.get_card(1) is None    # ✗ card vẫn còn!
E  assert <...Row object...> is None
```

### TRƯỚC — chỉ xoá words, trông mong FK cascade
```python
async def confirm(do, chat_id, word_id: int):
    word = do.word_row(word_id)
    if word is None:
        return
    do.storage.sql.exec("DELETE FROM words WHERE id = ?", word_id)
    await send_message(do.env, chat_id, texts.DELETE_DONE.format(word.word))
```

### SAU — xoá tường minh cả 3 bảng (2 nơi: `handlers/delete.py` + flow xoá trong `vocab_do.py`)
```python
# delete card + review history explicitly (DO SQLite may not enforce FK cascade)
do.storage.sql.exec("DELETE FROM reviews WHERE card_id IN (SELECT id FROM cards WHERE word_id = ?)", word_id)
do.storage.sql.exec("DELETE FROM cards WHERE word_id = ?", word_id)
do.storage.sql.exec("DELETE FROM words WHERE id = ?", word_id)
```

### Bài học
**Đừng tin FK ON DELETE CASCADE khi chưa verify trên platform thật** (DO SQLite kh gelegen giả LiteFS/khác SQLite thường). Xoá tường minh rõ ràng hơn và test được. Một bug hợp lý được test suite bắt — giá trị của integration test đúng chỗ này.

---

## 11. Các lỗi môi trường nhỏ (triệu chứng → cách xử lý)

| Lỗi | Nguyên nhân | Xử lý |
|---|---|---|
| `Error: No module named 'js'` khi pytest | pytest thuần không có `js` của Pyodide | Tách lớp: module thuần hàm test trực tiếp; module đụng `workers` chỉ test qua conftest stub |
| `RuntimeError: There is no current event loop in thread 'MainThread'` | Gọi async method của DO trong test sync | Bọc `asyncio.run(...)` trong helper `feed()` |
| `wrangler dev` thoát ngay | Bọc `timeout 120` — Pyodide load mất ~30s+ | Chạy không timeout, `setsid nohup ... & disown`, đọc log file |
| 500 "thiếu secret" khi `wrangler dev` | Chưa set secrets | Tạo `.dev.vars` local (không commit!) |
| Fake `Response.json` không await được | Quên json() là coroutine | Sửa fake trả awaitable ("fixed fake json to be awaitable") |

---

## 12. Bảo mật

- Token bot từng nằm trong `security_env.md` (file thường) — plan yêu cầu **thu hồi token qua @BotFather** rồi dùng `wrangler secret put BOT_TOKEN`. File `security_env.md` sau đó biến mất khỏi đĩa (điều tốt, nhưng đừng dựa may mắn).
- `.gitignore` phải che `.dev.vars` **trước commit đầu tiên**.

---

## 13. Bài học quy trình

1. **Compacting không sinh docs** — plan duy nhất nằm ở `~/.claude/plans/`, ngoài version control. Copy về repo ngay khi sinh ra.
2. **Git chưa có commit nào** = mọi thứ ngoài vùng an toàn. Commit sớm, commit thường.
3. **Transcript JSONL là nguồn sự thật** — devlog này trích 100% từ transcript 1.9 MB. Session chết không mất lịch sử.
4. **TDD theo milestone (thuần hàm trước, glue sau) cứu cả session** — đợt đổi import hàng loạt chỉ tốn vài phút vì test suite đủ dày bắt lỗi ngay.
5. Chiến thuật debug hiệu quả nhất session: **script tái lập tối thiểu in state trung gian** (bảng nào tồn tại, session key gì) thay vì chạy lại full suite rồi đọc đoán.

---

## 14. Checklist tiếp tục (session sau)

- [ ] Sửa test flaky §2 (inject đồng hồ giả qua monkeypatch `now_utc`)
- [ ] `uv run pytest` → 66/66
- [ ] Smoke test lại `wrangler dev` sau đợt đổi import §9 (curl giả lập update có header `X-Telegram-Bot-Api-Secret-Token`)
- [ ] Thu hồi bot token cũ (@BotFather) nếu chưa
- [ ] `wrangler secret put BOT_TOKEN` / `WEBHOOK_SECRET`; `OWNER_ID` vào `wrangler.jsonc` vars (đang là "0")
- [ ] `wrangler deploy` + `setWebhook` với `secret_token`
- [ ] E2E thật: add bulk → /study → 2 chế độ → `?`/`???` → 4 nút rating → kiểm tra `cards.due` đổi → alarm đúng quiet hours
- [ ] **Git commit đầu tiên** (sau khi chắc `.dev.vars` bị ignore)
