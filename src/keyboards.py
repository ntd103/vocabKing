"""Inline keyboard layouts. Every sub-screen has a back-to-menu button."""

from telegram import kb

BACK_MENU = ("◀️ Menu", "menu:home")


def with_back(rows: list[list[tuple[str, str]]]) -> list[list[dict]]:
    """Append a back-to-menu row under any keyboard."""
    return kb(rows + [[BACK_MENU]])


MENU_KB = kb(
    [
        [("📖 Ôn tập", "menu:study"), ("➕ Thêm từ", "menu:add")],
        [("✏️ Sửa", "menu:edit"), ("🗑 Xoá", "menu:delete")],
        [("🎮 Games", "menu:games")],
        [("⚙️ Cài đặt", "menu:settings"), ("❓ Trợ giúp", "menu:help")],
    ]
)

ADD_MENU_KB = with_back(
    [
        [("🔍 Tra từ điển", "add:lookup"), ("✍️ Nhập thủ công", "add:manual")],
    ]
)

GAMES_MENU_KB = with_back(
    [
        [("✍️ Viết chuyện chêm", "game:story")],
    ]
)

SETTINGS_MENU_KB = with_back(
    [
        [("🎯 Target/ngày", "set:target"), ("🔔 Kiểu nhắc", "set:reminder")],
        [("🌙 Giờ yên tĩnh", "set:quiet"), ("🔀 Chế độ ôn", "set:mode")],
    ]
)

MODE_KB = kb(
    [
        [("📖 Định nghĩa", "mode:definition"), ("🧩 Điền khuyết", "mode:cloze")],
        [("🎲 Trộn ngẫu nhiên", "mode:mix")],
        [("◀️ Cài đặt", "menu:settings")],
    ]
)

QUIET_KB = kb(
    [
        [("🌙 23:00–07:00", "quiet:23:7"), ("🌄 00:00–06:00", "quiet:0:6")],
        [("☀️ Không yên tĩnh", "quiet:off")],
        [("◀️ Cài đặt", "menu:settings")],
    ]
)

REMINDER_KB = kb(
    [
        [("🧩 Quiz (trả lời câu hỏi)", "remmode:quiz")],
        [("📄 Full (xem luôn, vẫn chấm)", "remmode:full")],
        [("◀️ Cài đặt", "menu:settings")],
    ]
)

CONFIRM_ADD_KB = kb(
    [
        [("✅ Thêm", "add:confirm"), ("❌ Huỷ", "add:cancel")],
    ]
)

EDIT_FIELDS_KB = kb(
    [
        [("🔤 Từ", "editf:{word}:word"), ("🔊 Phiên âm", "editf:{word}:phonetic")],
        [("🇻🇳 Nghĩa", "editf:{word}:meaning"), ("📝 Ví dụ", "editf:{word}:example")],
        [("ℹ️ Note", "editf:{word}:note")],
        [BACK_MENU],
    ]
)

LOOKUP_EXAMPLE_KB = kb(
    [
        [("📖 Lấy ví dụ từ điển", "lkex:api"), ("✍️ Tự nhập ví dụ", "lkex:manual")],
        [("⏭ Bỏ qua ví dụ", "lkex:skip")],
    ]
)

CONFIRM_LOOKUP_KB = kb(
    [
        [("✅ Lưu từ", "lksv:ok"), ("❌ Huỷ", "lksv:no")],
    ]
)

SHOW_ANSWER_KB = kb([[("👁 Hiện đáp án", "show:{card}")]])


def kb_back_menu() -> list[list[dict]]:
    return kb([[BACK_MENU]])


def fmt_rate_kb(card_id) -> list[list[dict]]:
    return [
        [
            {"text": "😖 Again", "callback_data": f"rate:{card_id}:again"},
            {"text": "🙁 Hard", "callback_data": f"rate:{card_id}:hard"},
        ],
        [
            {"text": "🙂 Good", "callback_data": f"rate:{card_id}:good"},
            {"text": "😎 Easy", "callback_data": f"rate:{card_id}:easy"},
        ],
        [{"text": "◀️ Menu", "callback_data": "menu:home"}],
    ]
