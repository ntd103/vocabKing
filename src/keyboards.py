"""Inline keyboard layouts for all bot flows."""

from telegram import kb

RATE_KB = kb(
    [
        [("😖 Again", "rate:{card}:again"), ("🙁 Hard", "rate:{card}:hard")],
        [("🙂 Good", "rate:{card}:good"), ("😎 Easy", "rate:{card}:easy")],
    ]
)

SHOW_ANSWER_KB = kb([[("👁 Hiện đáp án", "show:{card}")]])

CONFIRM_ADD_KB = kb(
    [
        [("✅ Thêm", "add:confirm"), ("❌ Huỷ", "add:cancel")],
    ]
)

CONFIRM_DELETE_KB = kb(
    [
        [("🗑 Xoá chắc chắn", "del:confirm:{word}"), ("❌ Giữ lại", "del:cancel")],
    ]
)

EDIT_FIELDS_KB = kb(
    [
        [("🔤 Từ", "editf:{word}:word"), ("🔊 Phiên âm", "editf:{word}:phonetic")],
        [("🇻🇳 Nghĩa", "editf:{word}:meaning"), ("📝 Ví dụ", "editf:{word}:example")],
        [("ℹ️ Note", "editf:{word}:note")],
    ]
)

MODE_KB = kb(
    [
        [("📖 Định nghĩa", "mode:definition"), ("🧩 Điền khuyết", "mode:cloze")],
        [("🎲 Trộn ngẫu nhiên", "mode:mix")],
    ]
)

QUIET_KB = kb(
    [
        [("🌙 23:00–07:00", "quiet:23:7"), ("🌄 00:00–06:00", "quiet:0:6")],
        [("☀️ Không yên tĩnh", "quiet:off")],
    ]
)

MENU_KB = kb(
    [
        [("📖 Ôn ngay (/study)", "menu:study"), ("➕ Thêm từ (/add)", "menu:add")],
        [("✏️ Sửa (/edit)", "menu:edit"), ("🗑 Xoá (/delete)", "menu:delete")],
        [("⚙️ Cài đặt (/settings)", "menu:settings"), ("❓ Trợ giúp (/help)", "menu:help")],
    ]
)


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
    ]
