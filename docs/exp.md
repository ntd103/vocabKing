# Kinh nghiệm phát triển — Vocabking (toàn bộ)

> Tổng hợp từ 3 session phát triển (17/09, 18/09, 07–08/11/2026) + docs/devlogs.
> Mục đích: lần sau gặp vấn đề tương tự thì tra đây trước.

## 1. Tổng quan dự án

Bot Telegram học từ vựng tiếng Anh cá nhân (1 user), **FSRS** spaced repetition,
chạy free 24/7 trên **Cloudflare Workers (Python/Pyodide)** + **Durable Object
SQLite**. Không framework bot (aiogram không chạy trên Pyodide) — tự viết
router + client Telegram Bot API bằng `fetch`.

**Stack chốt và lý do:**
- Workers Free: 100k req/ngày — bot 1 user dư sức; DO SQLite free 1GB.
- DO alarm API (`storage.setAlarm`) nhắc từ chính xác từng mốc, không cần cron.
- py-fsrs pure Python, chạy được trên Pyodide, serialize Card ↔ JSON sẵn.
- Webhook thay polling: Telegram đẩy update vào `*.workers.dev`, bảo mật bằng
  header `X-Telegram-Bot-Api-Secret-Token`.

## 2. Kiến trúc

```
Telegram ──webhook──> Worker (verify secret) ──RPC──> VocabularyDO
  (src/entrypoint.py)                     (src/vocab_do.py)
                                               ├─ SQLite: words, cards,
                                               │   reviews, daily
                                               ├─ KV: settings, fsm, session
                                               └─ alarm() → nhắc FSRS + quiet hours
```

- **FSM state** (dialog đang dở) lưu KV của DO — Worker stateless.
- **`wait_until`** ở entrypoint: trả 200 cho Telegram ngay, xử lý background —
  tránh Telegram retry gây duplicate update khi handler chậm.

## 3. Bài học về runtime Cloudflare (Python/Pyodide)

### 3.1 Fake ≠ runtime thật — nguồn bug lớn nhất, lặp lại 4 lần
| Bug | Hiện tượng | Nguyên nhân |
|---|---|---|
| `storage.get` vs `storage.kv.get` | confirm thêm từ im lặng | Runtime thật `storage.get` async → coroutine crash; fake alias 2 đường nên test xanh |
| `cur.last_insert_rowid` | từ "ma" không có card | DO SQL cursor không có API này (sqlite3 chuẩn có); fake giả lập được |
| `INSERT...RETURNING` không commit | test fail "cannot commit transaction" | RETURNING đọc như SELECT; fake chỉ commit sau INSERT/UPDATE/... — runtime thật tự xử |
| `OWNER_ID="0"` chặn mọi update | bot im lặng hoàn toàn | Biến "giá trị rác vẫn chạy" — cần fail-loud |

**Quy tắc rút ra:**
1. Grep bắt buộc trước commit: `grep -rn "storage\.\(get\|put\|delete\)(\" src/ | grep -v kv` — enforce nhất quán API.
2. Mọi API "tiện lợi" của sqlite3/Python chuẩn phải **đối chiếu docs DO SQLite** trước khi dùng.
3. **67 test xanh ≠ chạy được.** Bug nằm ở ranh giới code-platform, fake không mô phỏng được.

### 3.2 Chi phí setup mock + wrangler dev (~30 phút) đáng giá
Mock Telegram API = HTTPServer ~25 dòng log payload ra file; trỏ bot qua env
`TG_API_BASE`. Kết hợp **Local Explorer observability** xem traceback Python
không cần console:
```bash
curl -s -X POST http://localhost:8787/cdn-cgi/local/explorer/api/local/observability/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT rowid, message FROM logs ORDER BY rowid DESC LIMIT 20"}'
```
Điểm mù: `print()` từ Python không hiện trong logs — chỉ exception bị catch
rồi `print(repr(e))` mới xuất hiện. Smoke test này bắt được 3 bug runtime mà
67 test không thấy.

### 3.3 DB nằm ở đâu (câu hỏi hay gặp)
SQLite nhúng **trong Durable Object**, sống trên hạ tầng Cloudflare — không có
file `.db` trên máy dev. `wrangler dev` dùng SQLite in-memory của workerd,
xoá mỗi restart. Do đó dữ liệu test local không tồn tại lâu; production chỉ
truy cập được qua code chạy trên Worker.

## 4. Bài học về test

### 4.1 Test phụ thuộc thời gian phải pin đồng hồ — và pin TRƯỚC setup
Test alarm pass lúc 23h, fail lúc 12h. Cạm bẫy kép:
- Patch đồng hồ **sau** khi thêm từ → `due` ghi bằng đồng hồ thật → logic so
  sánh lệch. **Phải patch trước khi setup** — mọi timestamp ghi trong setup
  cũng phải đi qua đồng hồ giả.

### 4.2 Test phải phản ánh hành vi thật của thư viện
py-fsrs 6.x: vài lần Good đầu schedule theo **phút** (learning steps), không
phải ngày. Test viết theo trí nhớ API cũ (`scheduled_days` — đã bị bỏ) fail.
- **Đọc SDK trong venv trước khi code.**
- Review đúng lịch = `when = card.due` mỗi vòng, không review liên tục ngay
  lập tức.

### 4.3 Conftest fake phải sát API thật
- Fake `_Cur` phải: split SQL theo `;`, chạy từng statement, **drain + đóng
  cursor sau mỗi statement rồi commit ngay** (không commit 1 lần cuối) — nếu
  không `INSERT...RETURNING` giữ transaction mở → statement kế fail.
- Row access: runtime DO dùng **attribute** (`row.word`), không phải dict —
  chọn 1 convention, áp toàn codebase bằng script, đừng sửa tay từng chỗ.

### 4.4 Settings cache + test ghi trực tiếp KV
Cache settings trong RAM DO → test ghi `do.storage.kv.put("set:x")` trực tiếp
bỏ qua cache → giá trị cũ được phục vụ. Fix hai lớp:
1. Test dùng `do.put_setting()` (đi qua cache).
2. `put_setting` tự refresh cache kể cả khi chưa load (anti stale snapshot).

## 5. Tối ưu I/O (session 07–08/11) — số đo thực tế

Đo bằng instrument conftest fake (đếm `sql.exec`, `kv.*`, `tg.fetch`):

| Flow | Trước | Sau | Fix |
|---|---:|---:|---|
| `/add` 200 từ confirm | **602 ops** | **4** | `INSERT...VALUES(...),(...) RETURNING id` multi-row cho words + cards |
| `/settings` mỗi call | 3 KV get | 0 | cache settings dict trong RAM DO (single-writer → safe) |
| `alarm()` tick | 6 ops | 0 | settings đã cache |
| `_reschedule()` | 2 SELECT | 1 | `SELECT MIN(due)` qua index `idx_cards_due` |
| webhook | await full flow | 200 ngay | `wait_until` |

Bài học:
- **Đo trước khi tối ưu.** Bảng số đo chỉ ra bulk-add là 99% vấn đề — đoán
  bằng trực giác sẽ đi sai chỗ.
- **DO billing = rows read/written + duration** → giảm round-trip là giảm
  tiền/CPU quota, không chỉ giảm latency.
- Settings cache chỉ đúng vì DO **single-writer** (1 owner). Nếu sau này có
  admin tool ghi KV từ ngoài, cache sẽ stale.
- Alarm phải `_reschedule()` ngay sau `rate()` — không thì alarm cũ tick thừa
  không có gì để gửi (vẫn tốn 1 invocation + query).

## 6. Chọn API từ điển (research 2026-11, live-test)

| API | Kết luận |
|---|---|
| freedictionaryapi.com | **Chọn** — IPA + POS + def + examples, no-key, schema sạch |
| dictionaryapi.dev | Origin đang chết (audio 502 toàn bộ) — chỉ làm fallback |
| Cambridge | Trả phí, không free tier |
| Wiktionary | Bền nhất, nhưng IPA phải regex parse wikitext |
| Glosbe (en→vi) | **Đã shut down vĩnh viễn** |
| MyMemory (en→vi) | Chỉ là MT, từ đơn tạm được — không dùng vì user tự gõ VI |
| Google TTS | mp3 free nhưng unofficial — user yêu cầu bỏ audio |

Quyết định sản phẩm: **user tự gõ nghĩa tiếng Việt** (buộc nhớ sâu hơn), API
chỉ cung cấp IPA + def EN (phần "chuẩn xác thì không cần user").

Rate limit tính theo **egress IP của Cloudflare dùng chung** → khi cache lại
kết quả lookup thì bắt buộc KV cache, không phải tùy chọn.

## 7. Thuật toán hint (research + quyết)

Repo dùng **max-min-distance** (mỗi hint rơi vào khoảng trống lớn nhất —
"spaced reveal"/maximin dispersion). Là lựa chọn đúng:
- **Monotone**: thêm hint không làm hint cũ "di chuyển" — bắt buộc vì bot
  **edit message tại chỗ**.
- Thuật toán stride/modulo rẻ hơn nhưng KHÔNG monotone → bỏ.
- Nâng cấp ~5 dòng: **vowel-first tiebreak** — khi nhiều vị trí xa nhau ngang
  nhau, lộ nguyên âm (chứa "khung xương" từ — lineage Wordle solver).
- Bug gặp khi thêm tiebreak: sort key `(distance, vowel, rng, i)` nhưng lấy
  `best[2]` (rng) làm index → `list.remove` ValueError. Tuple dài thì đặt
  index ở cuối hoặc dùng key dict.

## 8. Bài học thiết kế UX bot Telegram

- **Menu trung gian edit message tại chỗ**, không gửi tin mới — tránh làm loãng
  lịch sử chat. Mọi sub-menu có nút quay lại menu chính.
- **callback_data 64 bytes limit** — `rate:{id}:{name}` hiện an toàn; thêm
  state vào callback thì phải xem lại.
- Tin nhắn Telegram cắt ở 4096 chars → preview `/add` giới hạn 20 từ + clip
  từng trường 200–300 chars.
- Webhook flow nhiều bước (lookup → VI → example → confirm) dùng FSM trong KV
  — mỗi bước chỉ 1 message mới, các bước có nút thì edit tại chỗ.
- **Word-wrap Telegram**: dòng không chứa `|` là continuation của dòng trước
  (đi vòng 3 heuristic rồi quay về quy tắc đơn giản + document trong /help).
  Bài học: heuristic "thông minh nhưng khó đoán" thua "đơn giản + documented".

## 9. Quy trình verify chuẩn (trước mỗi lần deploy)

```bash
uv run pytest -q                          # 67/67
uv run python scripts/tg_mock.py &        # mock Telegram API
# .dev.vars: TG_API_BASE=http://127.0.0.1:9999
npx wrangler dev                          # runtime thật
# curl /telegram với header secret → full flow: menu, lookup (fetch thật ra
# ngoài!), add, study, rate, games, settings
```

Deploy (user tự làm phần secret — không đưa token vào conversation):
1. `npx wrangler login` → `npx wrangler secret put BOT_TOKEN` + `WEBHOOK_SECRET`
2. `wrangler.jsonc` điền `OWNER_ID` thật
3. `npx wrangler deploy` → setWebhook qua curl với `secret_token` trùng
4. `npx wrangler tail` xem log khi debug production

**Vô tình lộ token trong chat = revoke ngay ở @BotFather.** Mọi output agent
đi qua proxy thứ 3 — coi như đã lộ.

## 10. Việc để dành

- `/export` CSV — backup dữ liệu (DB nằm trên Cloudflare, không có file local)
- `storage.batch()` cho delete (3 DELETE tuần tự)
- Cache session ở RAM DO
- Telemetry `rowsRead`/`rowsWritten` khi có traffic thật
- KV cache kết quả dictionary lookup (rate limit shared-IP)
