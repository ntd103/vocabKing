# Vocabking (Vocaboss)

Bot Telegram cá nhân hoá học từ vựng tiếng Anh với lịch ôn **FSRS** (spaced repetition), chạy hoàn toàn miễn phí 24/7 trên **Cloudflare Workers (Python)** + Durable Object SQLite.

## Tính năng

- **Thêm từ**: `/add từ|phiên âm|nghĩa|ví dụ|note` — thêm 1 hoặc hàng loạt, có xem trước + confirm
- **Ôn 2 chế độ**: định nghĩa (nghĩa là gì?) hoặc điền khuyết (cloze, gợi ý dần chữ cái bằng `?`, xem đáp án bằng `???`)
- **Nhắc tự động 24/7**: DO alarm bắn 1 từ/lần đúng lịch FSRS, tôn trọng giờ yên tĩnh (mặc định 23:00–07:00, đổi được qua `/settings`)
- **Quản lý từ**: `/edit`, `/delete` với search + inline keyboard
- **Whitelist**: chỉ OWNER_ID được dùng bot

## Cấu trúc

```
wrangler.jsonc          # config: DO binding, migrations, vars
src/
  entrypoint.py         # webhook: verify secret → RPC vào DO
  vocab_do.py           # Durable Object: 5 bảng SQL, router, alarm + quiet hours
  telegram.py           # Telegram Bot API client (TG_API_BASE env để mock khi test)
  handlers/             # add / edit / delete / review / settings
  services/             # fsrs_service, cloze, word_parser (thuần hàm, dễ test)
  keyboards.py, texts.py
tests/                  # pytest với conftest stub module `workers`
docs/
  plans/                # plan gốc
  devlogs/              # nhật ký dev (bug + bài học)
```

## Chạy test

```bash
uv run pytest          # 67 tests
```

## Chạy local (mock Telegram API)

```bash
# .dev.vars: BOT_TOKEN, WEBHOOK_SECRET, TG_API_BASE=http://127.0.0.1:9999
uv run python scripts/tg_mock.py &   # (script mock đơn giản, xem devlog #2 §4)
npx wrangler dev
# giả lập update:
curl -s -X POST http://localhost:8787/telegram \
  -H 'Content-Type: application/json' \
  -H 'X-Telegram-Bot-Api-Secret-Token: <WEBHOOK_SECRET>' \
  -d '{"message":{"chat":{"id":111},"from":{"id":111},"text":"/menu"}}'
```

## Deploy

1. Thu hồi/ tạo bot token qua @BotFather → `wrangler secret put BOT_TOKEN`
2. `wrangler secret put WEBHOOK_SECRET` (chuỗi random: `openssl rand -hex 32`)
3. Sửa `OWNER_ID` trong `wrangler.jsonc` = Telegram user ID của bạn (@userinfobot)
4. `wrangler deploy` → gọi `setWebhook` với `secret_token` trùng WEBHOOK_SECRET

Chi tiết bug + bài học: xem `docs/devlogs/`.
