# Vocaboss — Telegram bot học từ vựng trên Cloudflare Workers (Python)

## Context

Xây bot Telegram cá nhân hoá học từ vựng tiếng Anh: nhắc từ theo lịch **FSRS** (spaced repetition), 2 chế độ ôn (định nghĩa / điền khuyết), quản lý từ (thêm bulk/sửa/xoá). Yêu cầu: **miễn phí hoàn toàn, 24/24**. Đã loại bỏ phương án chạy local (user xác nhận local chỉ là phương án cuối). Chốt stack: **Cloudflare Workers + Python** — đã kiểm tra docs:

- Python Workers (beta, Python 3.14) hỗ trợ `WorkerEntrypoint` với `fetch` + `scheduled`
- **Durable Objects SQLite có trên Free plan** (limit 1GB — dư sức)
- **DO alarm API** (`storage.setAlarm`) — nhắc từ chính xác đến từng mốc, không cần cron polling
- **py-fsrs là pure Python** (không phụ thuộc numpy/torch ở phần core), serialize Card ↔ JSON có sẵn, yêu cầu UTC (Workers mặc định UTC — khớp)
- Workers Free: 100.000 requests/ngày — bot 1 user dùng không hết

## Kiến trúc

```
Telegram ──webhook──> Worker (fetch handler, kiểm tra secret token)
                          │
                    VocabularyDO (Durable Object, SQLite storage)
                      ├─ words / cards / reviews / settings / fsm (5 bảng SQL)
                      ├─ alarm() → quét từ đến hạn → gửi nhắc qua Telegram API → setAlarm(kế tiếp)
                      └─ sau mỗi review: setAlarm(due mới, clamp theo quiet hours)
```

- **Webhook thay vì polling**: Telegram đẩy update vào URL `*.workers.dev` của Worker. Bảo mật: dùng `secret_token` khi setWebhook, Worker kiểm tra header `X-Telegram-Bot-Api-Secret-Token`.
- **FSM state** (flow confirm thêm từ, sửa từ...) lưu bảng `fsm` trong DO storage — Worker stateless nên không giữ trong RAM.
- Không dùng framework bot (aiogram không chạy được trên Pyodide) — gọi Telegram Bot API trực tiếp qua `fetch`, tự viết router tin nhắn/text command đơn giản (bot 1 user, đủ dùng, ít dependency).

## Cấu trúc thư mục

```
vocabking/
├── wrangler.jsonc          # cấu hình: python_workers flag, DO binding, migrations, secrets
├── pyproject.toml          # deps: fsrs (pure python); dev: pytest
├── src/
│   ├── entrypoint.py       # class Default(WorkerEntrypoint): fetch → forward vào DO
│   ├── vocab_do.py         # class VocabularyDO(DurableObject): router, SQL, alarm handler
│   ├── telegram.py         # client Telegram Bot API (fetch wrapper: send, edit, answerCallback)
│   ├── handlers/
│   │   ├── menu.py         # /start /menu /help
│   │   ├── add.py          # thêm 1 dòng / bulk + preview confirm
│   │   ├── edit.py         # search → chọn từ → chọn trường → nhập mới
│   │   ├── delete.py       # search → chọn → confirm xoá
│   │   ├── review.py       # trả lời ôn, nút chấm điểm, reply "?" / "???"
│   │   └── settings.py     # quiet hours, mode mặc định
│   ├── services/
│   │   ├── fsrs_service.py # bọc py-fsrs: review_card, serialize/deserialize Card JSON
│   │   └── cloze.py        # masking + reveal letters (thuần hàm, dễ test)
│   ├── keyboards.py        # InlineKeyboard builders
│   └── texts.py            # template tin nhắn tiếng Việt
└── tests/                  # pytest cho cloze, parser bulk, fsrs serialize
```

## Data model (DO SQLite — SQL API `ctx.storage.sql.exec`)

```sql
words (id INTEGER PK, user_id INTEGER, word TEXT NOT NULL, phonetic TEXT,
       meaning TEXT, example TEXT, note TEXT, created_at TEXT)
cards (id INTEGER PK, word_id INTEGER UNIQUE REFERENCES words(id) ON DELETE CASCADE,
       card_json TEXT NOT NULL,          -- Card py-fsrs serialize to_dict
       due TEXT NOT NULL)                -- cột copy của due để query/index
reviews (id INTEGER PK, card_id INTEGER, rating INTEGER, reviewed_at TEXT)
settings (key TEXT PK, value TEXT)        -- quiet_start/quiet_end/default_mode
fsm (chat_id TEXT PK, state TEXT)         -- JSON state của dialog đang dở
```

## Flow nghiệp vụ (giữ nguyên như đã thống nhất)

- **Ôn — Định nghĩa**: bot gửi `word /phonetic/ → ?` + nút «Hiện đáp án» → hiện nghĩa + 4 nút **Again/Hard/Good/Easy** → FSRS cập nhật lịch.
- **Ôn — Điền khuyết** (`cloze.py` thuần hàm): `H_____ <Xin chào>, Paul. ...` (giữ chữ đầu, ký tự không phải chữ cái giữ nguyên). Reply đáp án → đúng/sai đều hiện đáp án + nút chấm. Reply **`?`** lộ thêm ~25–30% chữ còn ẩn, vị trí ngẫu nhiên **cách xa chữ đã lộ** (seed = card_id + số lần reveal). Reply **`???`** lộ đáp án + nghĩa + ví dụ. Tin nhắn đầu luôn kèm hướng dẫn `?`/`???`.
- **Thêm từ** `/add`: `word|phonetic|meaning|example|note` (khuyết → NULL, chỉ `word` bắt buộc). Bulk nhiều dòng; **dòng không chứa `|` gộp vào dòng trước** (xử lý wrap tự động của Telegram). Parse xong → preview + nút Confirm/Cancel → confirm mới ghi DB, tạo Card với `due = now`.
- **Sửa/Xoá** `/edit`, `/delete`: search LIKE → inline list ≤10 → chọn → sửa trường bằng nút / xoá có confirm → cascade card + reviews.
- **Nhắc tự động**: `alarm()` lấy các card due (clamp theo quiet hours, mặc định 07:00–23:00), gửi **1 từ/lần alarm** rồi re-set alarm cho từ kế tiếp (tránh spam).
- **/study**: ôn ngay các từ đến hạn không đợi alarm.
- **Settings**: quiet hours, mode mặc định (định nghĩa / điền khuyết / trộn ngẫu nhiên).
- **Whitelist**: mọi handler check `user_id == OWNER_ID` (var), người lạ bị bỏ qua im lặng.

## Hướng dẫn lấy thông tin setup (từng bước)

**1. Token Telegram bot** — bạn đã có bot (file `security_env.md`).
⚠️ **Quan trọng**: token này đã nằm trong file thường + đã từng xuất hiện trong hội thoại → nên **thu hồi và tạo token mới**: mở Telegram → **@BotFather** → `/mybots` → chọn bot → **API Token** → **Revoke current token** → copy token mới. Sau đó:
- Xoá file `security_env.md` (hoặc đưa vào `.gitignore` — sẽ làm).
- Lưu token vào secret Cloudflare (bước 5) — **không** ghi vào file nào trong repo.

**2. Telegram user ID của bạn** (dùng làm `OWNER_ID` whitelist):
- Nhắn tin cho **@userinfobot** trên Telegram → nó trả lời ngay dòng `Id: 123456789` → đó là user ID của bạn.

**3. Tài khoản Cloudflare (miễn phí, không cần thẻ)**:
- Vào `dash.cloudflare.com` → Sign up bằng email → xác nhận email.
- Free plan bao gồm: Workers 100k req/ngày + DO SQLite 1GB.

**4. Node.js + Wrangler CLI (công cụ deploy)**:
```bash
# cài Node LTS (nếu chưa có): dùng nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && source ~/.bashrc
nvm install --lts
# cài wrangler
npm install -g wrangler
# đăng nhập (mở browser OAuth)
wrangler login
```

**5. Đưa secret vào Worker** (không lưu trong code/config):
```bash
wrangler secret put BOT_TOKEN      # dán token mới từ Bước 1 khi được hỏi
wrangler secret put WEBHOOK_SECRET # tự nghĩ 1 chuỗi random dài (vd: openssl rand -hex 32)
```
`OWNER_ID` từ Bước 2 ghi vào `wrangler.jsonc` mục `vars` (không phải secret — chỉ là ID).

**6. Deploy + bật webhook** (sau khi code xong):
```bash
wrangler deploy    # in ra URL dạng https://vocabking.<subdomain>.workers.dev
# set webhook — đọc token từ file tạm để không đưa vào shell history:
curl -s "https://api.telegram.org/bot$(cat /tmp/tok)/setWebhook?url=<URL>/telegram&secret_token=<WEBHOOK_SECRET>"
rm /tmp/tok
```
Trong đó `<URL>/telegram` là route webhook của Worker, `<WEBHOOK_SECRET>` trùng secret ở Bước 5.

**7. Chạy thử local trước khi deploy**: `wrangler dev` — Workers Python chạy được local qua workerd, test webhook bằng curl hoặc dùng cloudflared tunnel nếu muốn test với Telegram thật.

## Testing

- **pytest (local, uv)**: `cloze.py` (masking IPA/unicode, reveal `?` không trùng + cách xa chữ đã lộ, `???` lộ hết), parser bulk (gộp dòng wrap, trường khuyết → NULL), fsrs_service (Card ↔ JSON round-trip).
- **E2E thủ công qua Telegram**: thêm bulk 5 từ (có dòng wrap) → confirm → `/study` → ôn cả 2 chế độ → `?` nhiều lần → `???` → chấm 4 nút → kiểm tra `cards.due` đổi → `/edit` → `/delete` → set quiet hours → chờ alarm thử.
- **Alarm test**: review 1 từ rating Again (due trong vài phút) → chờ alarm bắn nhắc.

## Verification cuối

1. `uv run pytest` pass
2. `wrangler dev` → curl giả lập update Telegram → router trả lời đúng
3. `wrangler deploy` + set webhook → flow E2E trên Telegram thật
4. Đổi giờ máy / rating Again để xác nhận alarm nhắc đúng giờ, đúng quiet hours

## Milestones

1. **M1 — Khung**: wrangler config, entrypoint + DO, telegram client, /start /menu, whitelist
2. **M2 — Quản lý từ**: add (1 + bulk + confirm), edit, delete
3. **M3 — FSRS + ôn + nhắc**: fsrs_service, flow định nghĩa + 4 nút, alarm + quiet hours, /study
4. **M4 — Điền khuyết + settings + polish**: cloze.py, `?`/`???`, settings menu, error handler, /help
