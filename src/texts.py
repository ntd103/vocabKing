"""Message templates (Vietnamese). Keep messages short — Telegram truncates
at 4096 chars, so previews are capped."""

MENU = "👋 <b>Vocaboss</b> — trợ giúp học từ vựng!\n\nChọn thao tác:"

HINT_ROOT = "Mình chưa hiểu 🤔\n/menu để mở menu."

HELP = (
    "<b>❓ Hướng dẫn</b>\n\n"
    "<b>Lệnh tắt</b>\n"
    "/menu — mở menu chính\n"
    "/add — thêm từ (tra từ điển hoặc nhập tay)\n"
    "/study — ôn ngay các từ đến hạn\n"
    "/edit [từ khoá] — sửa từ\n"
    "/delete [từ khoá] — xoá từ\n"
    "/games — trò chơi với từ vựng\n"
    "/settings — cài đặt\n"
    "/cancel — huỷ thao tác đang dở\n\n"
    "<b>Chức năng</b>\n"
    "• <b>Tra từ điển</b>: gõ 1 từ tiếng Anh → bot lấy phiên âm IPA + định nghĩa EN từ từ điển. "
    "Bạn tự thêm nghĩa tiếng Việt (để nhớ sâu hơn) và ví dụ.\n"
    "• <b>Ôn tập FSRS</b>: bot tự nhắc đúng lịch. Reply <code>?</code> để gợi ý thêm chữ, "
    "<code>???</code> để xem đáp án. Chấm Again/Hard/Good/Easy để thuật toán tính lần nhắc tiếp.\n"
    "• <b>Target/ngày</b>: tổng từ thêm + ôn mỗi ngày. Thêm 1 từ = trừ 1 slot ôn.\n"
    "• <b>Games</b>: viết chuyện chêm — bot rút ngẫu nhiên vài từ, bạn viết câu/đoạn chứa chúng."
)

# --- add flow ---
ADD_MENU = "➕ <b>Thêm từ</b>\n\nTra từ điển tự động lấy IPA + nghĩa EN, hoặc nhập tay:"
ADD_ASK_INPUT = (
    "Gửi danh sách từ (mỗi dòng một từ):\n"
    "<code>từ|phiên âm|nghĩa|ví dụ|note</code>\n"
    "Chỉ <code>từ</code> là bắt buộc. Gõ /cancel để huỷ."
)
ADD_CONFIRMED = "✅ Đã thêm {n} từ! (Hôm nay: {today}/{target})"
ADD_CANCELLED = "Đã huỷ, không thêm từ nào."
ADD_EMPTY = "Không đọc được từ nào. Định dạng: <code>từ|phiên âm|nghĩa|ví dụ|note</code>"

# --- dictionary lookup flow ---
LOOKUP_ASK = "🔍 Gõ từ tiếng Anh cần tra:"
LOOKUP_NOT_FOUND = "Không tìm thấy \"{word}\" trong từ điển. Kiểm tra chính tả hoặc thử từ khác."
LOOKUP_ASK_VI = "🇻🇳 Gõ nghĩa tiếng Việt cho <b>{word}</b>:"
LOOKUP_ASK_EXAMPLE = "📝 Thêm ví dụ cho <b>{word}</b>:"
LOOKUP_ASK_EXAMPLE_MANUAL = "✍️ Gõ câu ví dụ chứa <b>{word}</b>:"
LOOKUP_NO_EXAMPLE_IN_DICT = "⚠️ Từ điển không có ví dụ cho từ này. Tự nhập nhé:"
LOOKUP_PREVIEW = (
    "📋 <b>{word}</b> {phonetic}\n"
    "<i>{pos}</i>\n\n"
    "💡 EN: {definition}\n"
    "🇻🇳 VI: {meaning}\n"
    "📝 {example}\n\n"
    "Lưu từ này?"
)

# --- edit / delete ---
EDIT_ASK_SEARCH = "Nhập từ khoá cần tìm để sửa. Gõ /cancel để huỷ."
EDIT_NOT_FOUND = "Không tìm thấy từ nào khớp \"{}\"."
EDIT_PICKED = "Sửa từ nào?"
EDIT_FIELD_ASK = "Gửi nội dung mới cho <b>{field}</b> của từ <b>{word}</b> (/cancel để huỷ):"
EDIT_SAVED = "✅ Đã cập nhật <b>{field}</b> = {value}"

DELETE_ASK_SEARCH = "Nhập từ khoá cần tìm để xoá. Gõ /cancel để huỷ."
DELETE_PICKED = "Xoá từ nào?"
DELETE_DONE = "🗑 Đã xoá \"{}\" (kèm lịch sử ôn)."

# --- settings ---
SETTINGS_MENU = "⚙️ <b>Cài đặt</b>"
SETTINGS_MODE = "🔀 <b>Chế độ ôn</b>\nHiện tại: <b>{current}</b>"
SETTINGS_QUIET = "🌙 <b>Giờ yên tĩnh</b> (không nhắc trong khung này)\nHiện tại: <b>{current}</b>"
SETTINGS_REMINDER = (
    "🔔 <b>Kiểu nhắc khi đến hạn</b>\nHiện tại: <b>{current}</b>\n\n"
    "• Quiz: bot hỏi, bạn trả lời rồi chấm\n"
    "• Full: bot gửi luôn toàn bộ thông tin, bạn tự chấm mức nhớ"
)
SETTINGS_TARGET = (
    "🎯 <b>Target mỗi ngày</b>\nHiện tại: <b>{current}</b> từ/ngày\n\n"
    "Tổng số từ thêm + ôn trong ngày. Gõ con số mới (VD: <code>150</code>):"
)
SETTINGS_SAVED = "✅ Đã lưu: {label}"
TARGET_SET = "✅ Target mỗi ngày: <b>{}</b> từ"
TARGET_INVALID = "Con số không hợp lệ. Gõ một số nguyên dương (VD: <code>200</code>):"

# --- study / review ---
STUDY_NONE_DUE = "🎉 Hết từ đến hạn! (Hôm nay đã ôn {done}/{target})"
STUDY_QUOTA_DONE = "✅ Đã ôn đủ target hôm nay ({target} từ). Nghỉ ngơi đi! 🎉"

REPLY_HINT = (
    "Trả lời bằng cách <b>reply</b> tin nhắn này:\n"
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
    "Chấm mức nhớ 👇"
)
CLOZE_CORRECT = "✅ <b>Chính xác!</b> \"{word}\"\n\n💡 {meaning}\n\nChấm mức nhớ 👇"
CLOZE_WRONG = "❌ Chưa đúng. Đáp án: <b>{word}</b>\n\n💡 {meaning}\n\nChấm mức nhớ 👇"
CLOZE_FULL = "🔓 <b>{word}</b> {phonetic}\n\n📝 {example}\n💡 <b>{meaning}</b>\n\nChấm mức nhớ 👇"

# Full-info reminder: show everything up-front, still rate FSRS.
FULL_REMINDER = (
    "🔔 <b>Ôn: {word}</b> {phonetic}\n\n"
    "💡 <b>Nghĩa:</b> {meaning}\n"
    "📝 {example}\n\n"
    "Tự chấm mức nhớ 👇"
)

RATED_FEEDBACK = "🔖 <b>{word}</b> — đã chấm {rating}\n⏰ Nhắc lại sau: {interval}\n📊 Hôm nay: {done}/{target}"
RATE_NAMES = {"again": "Again 😖", "hard": "Hard 🙁", "good": "Good 🙂", "easy": "Easy 😎"}

# --- games ---
GAMES_MENU = "🎮 <b>Games</b>\n\nChọn trò chơi:"
STORY_ASK_COUNT = "✍️ <b>Viết chuyện chêm</b>\n\nMuốn rút bao nhiêu từ? (gõ một số, VD: <code>5</code>)"
STORY_INVALID_COUNT = "Số không hợp lệ. Gõ số nguyên từ 1 đến 20:"
STORY_EMPTY = "Kho từ đang trống. /add vài từ trước đã!"
STORY_WORDS = "✍️ <b>Viết chuyện chêm — {n} từ</b>\n\n{words}\n\nViết một câu hoặc đoạn ngắn chứa tất cả các từ trên. Gửi cho bạn bè hoặc tự đọc lại để nhớ!"


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
