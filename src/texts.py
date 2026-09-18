"""Message templates (Vietnamese). Keep formatting minimal & consistent."""

MENU = (
    "👋 <b>Vocaboss</b> — trợ giúp học từ vựng của bạn!\n\n"
    "Chọn một thao tác bên dưới, hoặc gõ lệnh:"
)

HINT_ROOT = (
    "Mình chưa hiểu tin nhắn này 🤔\n"
    "Gõ /menu để xem menu, /help để xem hướng dẫn."
)

HELP = (
    "<b>Hướng dẫn Vocaboss</b>\n\n"
    "<b>➕ Thêm từ</b> — /add\n"
    "Mỗi từ một dòng, các trường cách nhau bằng dấu |:\n"
    "<code>từ|phiên âm|nghĩa|ví dụ|note</code>\n"
    "Chỉ <code>từ</code> là bắt buộc, còn lại có thể bỏ trống.\n"
    "Có thể dán nhiều dòng một lần (thêm hàng loạt).\n"
    "⚠️ Nội dung bị xuống dòng phải không chứa dấu |; sau khi thêm, "
    "bot luôn hiển thị xem trước để bạn xác nhận.\n\n"
    "<b>📖 Ôn ngay</b> — /study: ôn các từ đến hạn ngay lập tức.\n\n"
    "<b>🔔 Nhắc tự động</b>: khi đến giờ, bot tự nhắc 1 từ. "
    "Trả lời (reply) tin nhắn ôn để làm bài:\n"
    "• Nhập đáp án → bot chấm đúng/sai\n"
    "• Reply <code>?</code> → lộ thêm vài chữ cái (lần nào cũng thêm)\n"
    "• Reply <code>???</code> → xem đáp án đầy đủ\n"
    "Sau đó chấm mức nhớ: 😖 Again / 🙁 Hard / 🙂 Good / 😎 Easy "
    "— thuật toán FSRS tự tính lần nhắc tiếp theo.\n\n"
    "<b>✏️ Sửa từ</b> — /edit &lt;từ cần tìm&gt;\n"
    "<b>🗑 Xoá từ</b> — /delete &lt;từ cần tìm&gt;\n"
    "<b>⚙️ Cài đặt</b> — /settings: giờ yên tĩnh, chế độ ôn mặc định.\n\n"
    "Huỷ thao tác đang dở: /cancel"
)

ADD_ASK_INPUT = (
    "Gửi danh sách từ (mỗi dòng một từ):\n"
    "<code>từ|phiên âm|nghĩa|ví dụ|note</code>\n"
    "Chỉ <code>từ</code> là bắt buộc. Gõ /cancel để huỷ."
)

ADD_CONFIRMED = "✅ Đã thêm {} từ vào kho từ vựng!"
ADD_CANCELLED = "Đã huỷ, không thêm từ nào."
ADD_EMPTY = "Không đọc được từ nào từ tin nhắn này. Định dạng: <code>từ|phiên âm|nghĩa|ví dụ|note</code>"

EDIT_ASK_SEARCH = (
    "Nhập từ khoá để tìm (phần sau lệnh, vd <code>/edit hello</code>), "
    "hoặc gõ từ khoá ngay bây giờ. Gõ /cancel để huỷ."
)
EDIT_NOT_FOUND = "Không tìm thấy từ nào khớp \"{}\"."
EDIT_PICKED = "Sửa từ nào?"
EDIT_FIELD_ASK = "Gửi nội dung mới cho <b>{field}</b> của từ <b>{word}</b> (gõ /cancel để huỷ):"
EDIT_SAVED = "✅ Đã cập nhật <b>{field}</b> = {value}"

DELETE_ASK_SEARCH = (
    "Nhập từ khoá để tìm (vd <code>/delete hello</code>), "
    "hoặc gõ từ khoá ngay bây giờ. Gõ /cancel để huỷ."
)
DELETE_PICKED = "Xoá từ nào?"
DELETE_DONE = "🗑 Đã xoá \"{}\" (kèm lịch sử ôn)."

SETTINGS_HEADER = "<b>⚙️ Cài đặt</b>\n\nChế độ ôn mặc định:"
SETTINGS_QUIET = (
    "<b>Giờ yên tĩnh</b> (không nhắc trong khung này; từ đến hạn sẽ dồn sang "
    "sáng hôm sau):\nhiện tại: <b>{}</b>"
)
SETTINGS_MODE_SAVED = "✅ Chế độ ôn mặc định: {}"
SETTINGS_QUIET_SAVED = "✅ Giờ yên tĩnh: {}"

STUDY_NONE_DUE = "🎉 Không có từ nào đến hạn! Từ kế tiếp sẽ được nhắc đúng lịch FSRS."

REPLY_HINT = (
    "Trả lời bằng cách <b>reply</b> tin nhắn ôn này:\n"
    "• nhập đáp án để chấm\n"
    "• <code>?</code> → gợi ý thêm chữ cái\n"
    "• <code>???</code> → xem đáp án"
)

DEFINITION_PROMPT = "📖 <b>{word}</b> {phonetic}\n\nNghĩa là gì? 👇"
DEFINITION_ANSWER = (
    "📖 <b>{word}</b> {phonetic}\n\n"
    "💡 <b>Nghĩa:</b> {meaning}\n"
    "📝 {example}\n"
    "ℹ️ {note}\n\n"
    "Bạn nhớ được không? Chấm mức nhớ 👇"
)

CLOZE_CORRECT = "✅ <b>Chính xác!</b> \"{word}\"\n\n💡 {meaning}\n\nChấm mức nhớ 👇"
CLOZE_WRONG = "❌ Chưa đúng. Đáp án: <b>{word}</b>\n\n💡 {meaning}\n\nChấm mức nhớ 👇"
CLOZE_FULL = (
    "🔓 <b>{word}</b> {phonetic}\n\n"
    "📝 {example}\n"
    "💡 <b>{meaning}</b>\n\nChấm mức nhớ 👇"
)

RATED_FEEDBACK = (
    "🔖 <b>{word}</b> — đã chấm {rating}\n"
    "⏰ Nhắc lại sau: {interval}"
)

RATE_NAMES = {"again": "Again 😖", "hard": "Hard 🙁", "good": "Good 🙂", "easy": "Easy 😎"}

def interval_human(days: int) -> str:
    if days <= 0:
        return "vài phút (đang trong bước học)"
    if days == 1:
        return "1 ngày"
    if days < 30:
        return f"{days} ngày"
    months = days / 30.44
    if months < 12:
        return f"~{months:.0f} tháng"
    return f"~{months / 12:.1f} năm"
