# Preprocessing

Kiểm tra các nhiệm vụ trong TODO.md, nếu đã hoàn thành thì đánh dấu, chuyển thành kiến thức vào [docs/usecase.md](docs/usecase.md), [docs/guide.md](docs/guide.md) và [docs/exp.md](docs/exp.md); dọn dẹp TODO.md. Nếu chưa thì tiếp tục hoàn thành.

# Trạng thái

- Local: đã triển khai + `uv run --offline pytest -q` — **229 passed** (24/11/2026).
- Kiến thức đã ghi: usecase (nghiệm thu đầu file), guide (phím tắt/menu), exp (Hard-on-add, idle 15s, FSM-safe alarm, vocab PAGE_SIZE=10).
- Giới hạn: Telegram inline keyboard không hỗ trợ căn trái — giữ icon đầu nhãn.
- Còn lại dưới đây — chưa deploy / chưa UAT Telegram thật.

## Còn mở — nghiệm thu Telegram

1. Trả lời tin nhắc FSRS trên bot thật (gõ từ / `?` / `???` / `1`–`4`).
2. Export nhận đúng tệp `export_YYYY-MM-DD_HH-MM.{csv|json}`; import bằng **reply** kèm file UTF-8.
3. Quan sát idle 15s đóng dialog; xác nhận nhắc không chen khi đang trong menu.
4. Deploy khi UAT ổn.
