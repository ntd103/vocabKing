"""/settings — target/ngày, kiểu nhắc, giờ yên tĩnh, chế độ ôn. One screen."""

import texts
from keyboards import MODE_KB, QUIET_KB, REMINDER_KB, SETTINGS_MENU_KB, kb_back_menu
from telegram import edit_message, send_message

MODE_LABELS = {"definition": "📖 Định nghĩa", "cloze": "🧩 Điền khuyết", "mix": "🎲 Trộn ngẫu nhiên"}
REMINDER_LABELS = {"quiz": "🧩 Quiz", "full": "📄 Full"}


def _quiet_label(do) -> str:
    try:
        s, e = int(do.setting("quiet_start")), int(do.setting("quiet_end"))
    except ValueError:
        return "tắt"
    return "tắt" if s == e else f"{s:02d}:00 – {e:02d}:00"


def _overview(do) -> str:
    return (
        texts.SETTINGS_MENU + "\n\n"
        f"🎯 Target/ngày: <b>{do.setting('daily_target')}</b>\n"
        f"🔔 Kiểu nhắc: <b>{REMINDER_LABELS.get(do.setting('reminder_mode'), '?')}</b>\n"
        f"🌙 Giờ yên tĩnh: <b>{_quiet_label(do)}</b>\n"
        f"🔀 Chế độ ôn: <b>{MODE_LABELS.get(do.setting('mode'), '?')}</b>"
    )


async def show(do, chat_id):
    await send_message(do.env, chat_id, _overview(do), reply_markup=SETTINGS_MENU_KB)


async def show_section(do, chat_id, message_id, section: str):
    if section == "target":
        do.set_fsm(chat_id, {"flow": "set_target", "message_id": message_id})
        await edit_message(do.env, chat_id, message_id,
                           texts.SETTINGS_TARGET.format(current=do.setting("daily_target")),
                           reply_markup=kb_back_menu())
    elif section == "reminder":
        await edit_message(do.env, chat_id, message_id,
                           texts.SETTINGS_REMINDER.format(
                               current=REMINDER_LABELS.get(do.setting("reminder_mode"), "?")),
                           reply_markup=REMINDER_KB)
    elif section == "quiet":
        await edit_message(do.env, chat_id, message_id,
                           texts.SETTINGS_QUIET.format(current=_quiet_label(do)),
                           reply_markup=QUIET_KB)
    elif section == "mode":
        await edit_message(do.env, chat_id, message_id,
                           texts.SETTINGS_MODE.format(
                               current=MODE_LABELS.get(do.setting("mode"), "?")),
                           reply_markup=MODE_KB)


async def on_target_input(do, chat_id, text: str):
    t = text.strip()
    if not t.isdigit() or int(t) < 1:
        await send_message(do.env, chat_id, texts.TARGET_INVALID)
        return
    do.put_setting("daily_target", t)
    do.set_fsm(chat_id, None)
    await send_message(do.env, chat_id, texts.TARGET_SET.format(t))


async def set_mode(do, chat_id, message_id, mode: str):
    if mode not in MODE_LABELS:
        return
    do.put_setting("mode", mode)
    await show_section(do, chat_id, message_id, "mode")


async def set_reminder_mode(do, chat_id, message_id, mode: str):
    if mode not in REMINDER_LABELS:
        return
    do.put_setting("reminder_mode", mode)
    await show_section(do, chat_id, message_id, "reminder")


async def set_quiet(do, chat_id, message_id, spec: str):
    if spec == "off":
        do.put_setting("quiet_start", "1")
        do.put_setting("quiet_end", "1")
    else:
        parts = spec.split(":")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            do.put_setting("quiet_start", str(int(parts[0])))
            do.put_setting("quiet_end", str(int(parts[1])))
        else:
            return
    await show_section(do, chat_id, message_id, "quiet")
