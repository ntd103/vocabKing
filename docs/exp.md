# Kinh nghiệm phát triển — Vocabking (toàn bộ)

> Tổng hợp từ 3 session phát triển (17/09, 18/09, 07–08/11/2026) + docs/devlogs.
> Mục đích: lần sau gặp vấn đề tương tự thì tra đây trước.

## Cập nhật kiểm chứng — Settings và Games

- Khi nhận số ở bước Daily target hoặc Quiet hours, router dùng `message_id` của tin **nhập liệu** để gọi `deleteMessage`. Tin **menu** có ID riêng dùng cho `editMessageText`. Không xoá lịch sử; nếu dọn tin thất bại vẫn xử lý giá trị.
- Đổi target phải gọi `_reschedule()` vì quota ảnh hưởng thời điểm nhắc. Test kiểm tra ID được xoá, ID được sửa và không tạo menu thứ hai.

### FSRS: tách thời điểm tạo, trả lời và chấm

- Thẻ mới: `new_card_json` gọi `review(Card(), "hard")` tại thời điểm tạo — seed Hard thật, không chỉ `due = created + learning_steps[0]`. Trên scheduler mặc định khoảng ~5.5 phút; JSON `due` = cột SQL `due`.
- FSRS có fuzzing: tính lại từ đầu khi bấm nút có thể cho khoảng khác với nhãn đã hiện. Lưu bốn kết quả dự kiến trong session khi nhận đáp án, dùng interval đã chọn khi chấm. Giờ yên tĩnh và quota vẫn có thể làm tin nhắc đến sau mốc `due`.
- Vocabulary mở thẳng bảng (`table=True`); mọi FSM chờ phản hồi có `expires_at` (+15s, refresh mỗi `set_fsm`). `_alarm_tick` hết hạn thì sửa tin “Timed out”; pending review **không** timeout. Có FSM thì không gửi quiz; `_reschedule` chỉ gắn due-card khi FSM trống.

## Cập nhật kiểm chứng — 24/11/2026 (đóng TODO còn lại)

- Vocabulary UX: bỏ hub Add/View trong vocab; `PAGE_SIZE = 10`; Edit/Delete trên footer bảng browse. Add chỉ từ menu chính/`/add`.
- Idle + anti-interrupt dùng chung một DO alarm: wake = min(idle expiry, next due đã clamp quiet). Pending review vẫn `deleteAlarm` và chờ user.
- UI English trong `texts.py` / `keyboards.py`. Bot API không có căn trái inline keyboard — giữ icon đầu nhãn.
- Verify: `uv run --offline pytest -q` — **229 passed**. Chưa UAT Telegram/deploy.

### Ghi và chuyển dữ liệu từ vựng

- Thêm cột `pos` nullable để giữ POS khi lưu từ từ điển mà không phá DB cũ. Khi thêm theo lô, dùng tối đa 11 từ × 9 tham số SQL mỗi lần ghi và một transaction cho toàn lô; lỗi ở nhóm sau phải rollback cả từ và thẻ ở các nhóm trước.
- File import/export dùng UTF-8, giới hạn 512 KiB hoặc 2.000 bản ghi. CSV/JSON có thể round-trip cả dấu phẩy, dấu ngoặc kép và xuống dòng. Upload phải reply đúng prompt; không ghi trước khi xác nhận. JSONL cũ vẫn đọc được nếu dữ liệu đáp ứng các trường bắt buộc.
- Kiểm chứng local: `uv run --offline pytest -q` — 224 test đạt. Chưa thử truyền file hoặc nhận alarm qua Telegram thật.

## Hiệu chỉnh kiểm chứng — 08/11/2026

- Tái hiện ban đầu: 65 test đạt, 7 lỗi; fixture 5 trường không còn phù hợp parser 6 trường. Sửa fixture phải giữ assertion về nghĩa/ví dụ, không hạ kỳ vọng để xanh.
- Lỗi độc lập được chứng minh bằng test mới: thiếu migration `define_en`, quiz không có nút hint, rating không ràng buộc session, `/cancel` chưa mở menu.
- Migration dùng `PRAGMA table_info(words)` rồi `ALTER TABLE ... ADD COLUMN` nếu thiếu; không đổi dữ liệu VI cũ. Có kiểm tra khởi tạo lặp.
- Rating giữ session đến khi chấm, kiểm tra card/message/chat và trạng thái reveal. `transactionSync` gom card + log + daily + xoá session; kiểm thử lỗi ghi log phải rollback. Thời gian log dùng chính `updated.last_review`, due cột SQL bằng due trong JSON.
- API tham chiếu: https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/#transactionsync — callback đồng bộ, lỗi thì rollback. Fake test được bổ sung transaction, không dùng SQL `BEGIN` trong production.
- Kiểm thử local không thay smoke test Workers/Telegram thật. Chưa deploy, không đọc hoặc thao tác secrets.
- Đính chính ghi chép cũ: `wait_until` không cung cấp deduplication hoặc bảo đảm không mất update; `MAX(id)` không mặc nhiên full scan; alarm bị quiet hours bỏ qua không phải phép đo I/O đại diện. Chưa có bằng chứng mọi bước trung gian đều edit tại chỗ; chưa xác minh độ bền local Wrangler trong task này.

## Sửa nguyên nhân spam và quiz — 08/11/2026

- Root cause: mỗi alarm chọn lại card quá hạn và lên alarm sau 60 giây; không có pending gate, gửi tin không tăng daily.reviewed, nên 4 từ vẫn có thể tạo hàng trăm tin. Không phải FSRS tự tạo 200 lần review.
- Thêm KV `review:pending`, reserve trước network await, giữ đến rating; alarm bị xoá khi chờ. Repeated alarm, restart và /study cùng lúc phải không tạo thêm quiz. Reservation lỗi mạng không xác định được giữ để tránh retry mù.
- Quiz phải test `word`, không phải `example` hoặc nghĩa VI. Regex escape + word boundaries, case-insensitive thay chỉ vocab trong ví dụ; không match thì dùng nghĩa VI + ô trống. Hint mở chữ của word, answer so với word.
- Tất cả rating đối chiếu kết quả FSRS, JSON due = SQL due = alarm khi chỉ một card đến hạn; FSRS fuzzing được cố định random state trong test để không nhầm sai khác interval ngẫu nhiên thành lỗi.
- Transient UI: giữ message_id trong FSM và edit bảng/preview/field prompt/rating/result; không gửi tin mới mỗi công đoạn. CRUD dùng chung bảng có filter/pagination, không nhảy thẳng vào sửa khi chỉ có một kết quả.
- Kiểm thử local không chứng minh Telegram/Workers production; chưa deploy. Không tự xoá tin spam đã tồn tại trước bản sửa.

## Hiển thị ô trống và chọn IPA US — 08/11/2026

- Mask nội bộ không đổi để hint hoạt động theo vị trí; chỉ render mỗi ký tự cách nhau 1 space, giữa từ 3 spaces. Ví dụ `make up` → `_ _ _ _   _ _`. Dùng `<pre>` giữ khoảng cách Telegram.
- Schema dictionary thực dùng `entries[].pronunciations[]` với `type/text/tags`, không phải top-level phonetics. Đối chiếu OpenAPI https://freedictionaryapi.com/api/v1/openapi.json và response public `hello`.
- Chỉ chọn IPA gắn US/United States/General American/American English; bỏ dạng viết tắt `/-.../` hoặc `/...-/`. Không có nhãn US thì để trống, không suy đoán từ UK hoặc untagged. Dữ liệu cũ/nhập tay chưa được kiểm chứng accent, không tự đổi.

## Thuộc tính tuỳ chọn trong add qua nút — 08/11/2026

- (Cũ) Dictionary wizard VI/example/note + lkfield — đã gỡ 25/11/2026; `/add` giờ chỉ offer EN rồi pipe format. Xem guide/usecase hiện tại.
- Test route thật lkfield và text input xác minh lưu đúng EN/VI/note, không chỉ gọi handler. Dữ liệu IPA nhập tay/đã có không thể cam kết en-US từ nhãn; API chỉ được nhận IPA gắn US rõ ràng.

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

## Điền thuộc tính thiếu trong sửa từ và preview add — 10/11/2026

- Nút `Điền thông tin thiếu` dùng lại contract dictionary hiện có: chỉ IPA US, định nghĩa EN và ví dụ. Nghĩa VI/note không có từ nguồn hiện tại nên không tự đoán hoặc ghi đè.
- Đọc lại hàng sau `await lookup`; chỉ update cột vẫn trống, để không ghi đè sửa đổi đồng thời. Ràng buộc callback bằng flow/action/word/message ID chống callback cũ; không sửa card, review, daily hoặc alarm.
- Preview manual vốn nối từng field bằng newline. Regression test qua router cho cả lệnh inline, nhập tay và lookup xác minh payload Telegram cho mẫu `consequence`; nguồn lỗi gạch nối trước đây chưa tái hiện trong mã hiện tại.
- Verify `uv run pytest -q` — 193 passed; dùng dictionary/Telegram fake, không request live và không deploy.

## Kiểm chứng hoàn tất TODO — 10/11/2026

- Nguyên nhân lỗi CRUD: router/FSM và bảng không cùng một contract; bảng dựng callback riêng cho từng dòng, trong khi yêu cầu là nhập STT hoặc tên từ. Dùng một bảng với filter/pagination, số thứ tự global hiển thị, picker nhập liệu và action state rõ ràng. Xoá tất cả chỉ xuất hiện trong action Delete và vẫn cần xác nhận riêng.
- Các luồng tra từ được nối qua cùng router: nhập VI, chọn ví dụ từ điển/nhập tay/bỏ qua, nhập note hoặc bỏ qua, preview và lưu. Gõ trực tiếp ở bước ví dụ/note được nhận như nhập giá trị. Giá trị người dùng được escape trước khi render HTML; ví dụ và note có thể để trống.
- Kết thúc add/import vào menu Từ vựng; hoàn thành/hủy Edit/Delete trả về bảng action tương ứng. Giữ message ID để các bước edit tại chỗ.
- FSRS: bổ sung vector tham chiếu độc lập dựa trên công thức retrievability/stability/difficulty và kiểm tra Good/Easy với interval literal; test reminder xác minh alarm không gửi trước due và gửi khi đến hạn. Fake runtime không thay thế kiểm chứng Workers/Telegram production.
- Xác minh trước thay đổi hiện tại: `uv run pytest -q` — **175 passed**. `git diff --check` sạch. Không deploy hoặc thao tác secrets.
- Telegram inline keyboard căn chỉnh nhãn phụ thuộc client; Bot API không có cờ căn trái. Icon đã được bổ sung cho các action mới liên quan đến các luồng này; không thể áp đặt căn trái chỉ từ payload.

## Chuẩn hoá CRUD Phương án B, Rich Markdown Table & Tối ưu tốc độ — 11/11/2026

- **Telegram Bot API 10.1+ Rich Messages**: thay toàn bộ bảng ASCII/box-drawing trong `<pre>` ở `vocab_list.py` và `games.py` bằng GFM Markdown Table native (`sendRichMessage` / `editMessageText` với `rich_message={"markdown": ..., "skip_entity_detection": True}`). `editMessageText` cho phép chuyển đổi tại chỗ hai chiều giữa `text` (HTML) và `rich_message` (Markdown) trên cùng `message_id` mà không cần xoá/gửi lại tin mới.
- **Escape an toàn Rich Markdown**: mọi ô dữ liệu đi qua `md_cell` / `md_escape` (chuẩn hoá newline/tab thành khoảng trắng, escape `\_*|~`[]()<>&=$!`) để nội dung có chứa `|`, `<tag>`, `*bold*`, `$` không làm vỡ cột hoặc tiêm định dạng. Không escape `#` vì `skip_entity_detection: True` đã tắt hashtag và dòng bảng bắt đầu bằng `|`.
- **CRUD Phương án B**: menu `📚 Kho từ vựng` gom đủ 4 hành động `➕ Thêm từ`, `👁 Xem`, `✏️ Sửa`, `🗑 Xoá` + `🔎 Tìm kiếm`. Chọn hành động mở bảng Markdown tương ứng; thao tác trên bản ghi bằng cách gõ **STT toàn cục** hoặc **tên từ**. Gõ sai không xoá mất bảng (render lại đúng trang + filter hiện tại kèm cảnh báo); trùng tên từ (`> 1` bản ghi) hiển thị bảng lọc các dòng trùng để gõ STT chính xác. Từ màn chi tiết Xem có nút `✏️ Sửa` / `🗑 Xoá` cho chính bản ghi đang xem, hoàn tất/huỷ quay lại đúng trang bảng Xem.
- **Tối ưu phản hồi & I/O**:
  1. `on_callback` dùng `asyncio.gather(answer_callback(...), _dispatch_callback(...))` — cắt ~1 RTT mạng HTTPS mỗi lần bấm nút.
  2. Phân trang dùng 1 câu SQL CTE `ROW_NUMBER() OVER (ORDER BY w.id) AS stt` + `COUNT(*) OVER () AS total` (`O(N)` thay cho 2 câu correlated subquery `O(N²)`).
  3. Game chuyện chêm dùng `SELECT word, meaning FROM words ORDER BY RANDOM() LIMIT ?` thay vì tải cả bảng vào RAM, đồng thời edit trên cùng `message_id`.
  4. Cờ KV `schema:v2` bỏ qua 10 lệnh DDL/`PRAGMA`/seed KV trên mỗi lần DO wake-up kế tiếp; `on_message` chỉ đọc `fsm` 1 lần.
  5. `dict_service.lookup` có LRU cache 128 mục + `urllib.parse.quote` an toàn cho cụm từ/ký tự đặc biệt (trả bản sao `dict` cô lập để caller gán `meaning_vi`/`note` không làm bẩn cache; tự reset khi `fetch` bị monkeypatch trong test).
- **An toàn trạng thái khi xoá / gọi lệnh mới**: xoá đơn lẻ 1 từ dọn `review:pending` + `session` ngay trong `transactionSync` và `_reschedule()` trước `await` mạng; các lệnh `/` mới (`/vocab`, `/edit`, `/delete`, `/add`, `/import`) xoá `fsm` cũ để luôn mở tin nhắn mới đúng chế độ.
- **Đồng bộ UI**: toàn bộ nút và thông báo chuyển sang tiếng Việt nhất quán, 100% nút có icon đầu nhãn (`🏠 Menu` cho về thẳng Menu chính, `◀️ ...` cho lùi 1 cấp, bộ icon thuộc tính `🔤 🔊 🏷 🇬🇧 🇻🇳 📝 ℹ️ ⏰`). Verify: `uv run pytest -q` — **215 passed**, `git diff --check` sạch.
