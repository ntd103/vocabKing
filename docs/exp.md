# Kinh nghiệm tối ưu hiệu năng + I/O — Vocabking

> Ngày: 2026-11-08. Mục tiêu: giảm storage I/O của Durable Object (bottleneck
> chính của bot) và latency webhook, giữ nguyên 67/67 test xanh.

## Cách đo (trước khi sửa)

Instrument conftest fake (đếm `sql.exec`, `kv.get/put/delete`, `tg.fetch`) chạy
qua từng flow. Bảng "ops" = tổng storage ops cho 1 thao tác:

| Flow | Trước | Sau | Ghi chú |
|---|---:|---:|---|
| `/add` 200 từ → confirm | **602** | **4** | −99.3%, fix lớn nhất |
| `/settings` | 3 KV get | 0 | settings cache trong RAM DO |
| `alarm()` tick | 6 ops | 0 | không còn đọc settings KV mỗi tick |
| `_reschedule()` | 2 SELECT | 1 SELECT | gộp MIN(due) qua index |
| rate:good | 9 | 9 | +`_reschedule()` ngay sau rate (đổi alarm đúng giờ) |
| webhook → Telegram | await hết flow | 200 ngay | `wait_until` background |

## Bottleneck tìm được (theo thứ tự impact)

1. **Bulk add N từ = 3N round-trip SQL** (`INSERT words` + `SELECT MAX(id)` +
   `INSERT cards` mỗi từ). 200 từ = 602 ops trong một lần confirm — dễ vượt
   CPU/storage-time limit của DO free tier. → **fix**: `INSERT ... VALUES
   (?,..),(?,..) RETURNING id` 1 lần cho words + 1 lần cho cards.
2. **Settings đọc lại KV mỗi lần** — `is_quiet`, `_pick_mode` gọi
   `do.setting()` liên tục. Mỗi `kv.get` là 1 storage op; DO SQLite billing
   tính theo rows read/written + duration. → **fix**: cache `dict` settings
   trong RAM instance (DO single-writer, instance long-lived → safe).
3. **`_reschedule` 2 query tuần tự** (pick due + next future due) chạy sau
   mỗi alarm + mỗi confirm. → **fix**: `SELECT MIN(due)` 1 query, so sánh
   string ISO với `now`.
4. **Webhook await toàn bộ flow** — Telegram chờ response, handler chậm →
   Telegram retry (duplicate update) + tốn wall-time. → **fix**:
   `wait_until(stub.handle_update(update))` trả 200 ngay.
5. **Alarm không realign sau khi rate** — đánh Good đẩy due ra 1 ngày nhưng
   alarm cũ vẫn ở mốc cũ → tick thừa không có gì để gửi (vẫn tốn 1 alarm
   invocation + ít nhất 1 query). → **fix**: gọi `_reschedule()` ngay trong
   `review.rate`.

## Bẫy gặp phải khi áp dụng (bài học)

- **`INSERT ... RETURNING` vẫn là write**: conftest `_Cur` chỉ commit sau
  statement bắt đầu bằng INSERT/UPDATE/DELETE/CREATE/DROP → RETURNING không
  được commit → multi-statement tiếp theo nổ `OperationalError: cannot commit
  transaction - SQL statements in progress`. Fix fake: đóng/drain cursor sau
  mỗi statement + commit ngay, thay vì commit 1 lần cuối.
- **Conftest fake lệch runtime thật** là nguồn bug lặp lại (devlog #1, #2,
  giờ thêm cái này). Mỗi lần đổi SQL access pattern phải nghĩ "runtime thật
  có API này không" — DO SQLite **có** `RETURNING` (SQLite ≥3.35), an toàn.
- **Settings cache chỉ đúng vì DO là single-writer**: chỉ có 1 owner, 1 DO
  instance ghi settings. Nếu sau này có admin tool ghi trực tiếp KV từ ngoài,
  cache sẽ stale → cần `storage.kv.delete` + reset `_settings = None`.

## Cách verify

```bash
uv run pytest -q                # 67/67
# đo lại I/O
uv run python /tmp/vkbench/count_io.py   # script đếm ops (xem git history)
# smoke thật
uv run python scripts/tg_mock.py &
TG_API_BASE=http://127.0.0.1:9999 npx wrangler dev
# curl /add 5 từ → confirm → /study → rate, grep log mock
```

## Việc chưa làm / cân nhắc sau

- **Batch `storage.batch()` / transaction** cho `delete` (3 DELETE tuần tự) —
  impact nhỏ (delete hiếm), nhưng đúng pattern.
- **Giới hạn callback_data 64 bytes** của Telegram — hiện `rate:{id}:{name}`
  ngắn, chưa vấn đề; nếu sau này đính kèm thêm state vào callback thì phải
  xem lại.
- **`get_session` JSON parse mỗi reply** — session nhỏ, nhưng nếu ôn nhanh
  liên tiếp có thể cache ở tầng DO RAM (1 key/1 instance).
- **Telemetry**: thêm `console.log` rows_read/rows_written (DO SQL cursor
  expose `rowsRead`/`rowsWritten`) vào 1 chu kỳ deploy thật để kiểm chứng con
  số đo bằng fake khớp production.
