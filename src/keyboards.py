"""Inline keyboard layouts. Consistent leading icons across all screens."""

from telegram import kb

BACK_MENU = ("🏠 Menu", "menu:home")


def with_back(rows: list[list[tuple[str, str]]]) -> list[list[dict]]:
    """Append a back-to-menu row under any keyboard."""
    return kb(rows + [[BACK_MENU]])


MENU_KB = kb(
    [
        [("📖 Review", "menu:study"), ("➕ Add words", "menu:add")],
        [("📚 Vocabulary", "menu:vocab"), ("🎮 Games", "menu:games")],
        [("⚙️ Settings", "menu:settings"), ("❓ Help", "menu:help")],
        [("📤 Import / Export", "menu:import_export")],
    ]
)

ADD_EN_KB = kb(
    [
        [("✅ Use EN definition (1)", "add:en_ok"), ("✍️ Manual (2)", "add:en_manual")],
        [BACK_MENU],
    ]
)

ADD_INPUT_KB = kb(
    [
        [("❌ Cancel", "add:cancel"), BACK_MENU],
    ]
)

GAMES_MENU_KB = with_back(
    [
        [("✍️ Story challenge", "game:story")],
    ]
)

SETTINGS_MENU_KB = with_back(
    [
        [("🎯 Daily target", "set:target"), ("🌙 Quiet hours", "set:quiet")],
    ]
)

MODE_KB = kb(
    [
        [("📖 Definition", "mode:definition"), ("🧩 Fill in the blank", "mode:cloze")],
        [("🎲 Mixed", "mode:mix")],
        [("◀️ Settings", "menu:settings")],
    ]
)

QUIET_KB = kb(
    [
        [("🌙 23:00–07:00", "quiet:23:7"), ("🌄 00:00–06:00", "quiet:0:6")],
        [("✏️ Custom hours", "quiet:custom")],
        [("☀️ Turn off", "quiet:off")],
        [("◀️ Settings", "menu:settings")],
    ]
)

REMINDER_KB = kb(
    [
        [("🧩 Quiz", "remmode:quiz")],
        [("📄 Full answer", "remmode:full")],
        [("◀️ Settings", "menu:settings")],
    ]
)

CONFIRM_ADD_KB = kb(
    [
        [("✅ Add", "add:confirm"), ("❌ Cancel", "add:cancel")],
    ]
)


def delete_all_confirm_kb() -> list[list[dict]]:
    return kb(
        [
            [("🗑 Delete permanently", "delall:confirm"), ("↩️ Keep", "delall:cancel")],
        ]
    )


def kb_back_menu() -> list[list[dict]]:
    return kb([[BACK_MENU]])


def fmt_rate_kb(card_id, intervals) -> list[list[dict]]:
    ratings = (("😖", "again"), ("🙁", "hard"), ("🙂", "good"), ("😎", "easy"))
    buttons = [(f"{icon} {rating.title()} ({intervals[rating]})", f"rate:{card_id}:{rating}")
               for icon, rating in ratings]
    return kb([buttons[:2], buttons[2:], [BACK_MENU]])
