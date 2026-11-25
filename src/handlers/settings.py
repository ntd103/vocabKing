"""/settings — target/ngày, kiểu nhắc, giờ yên tĩnh, chế độ ôn. One screen."""

import texts
from keyboards import MODE_KB, QUIET_KB, REMINDER_KB, SETTINGS_MENU_KB, kb_back_menu
from telegram import edit_message, send_message, tg_call

MODE_LABELS = {"definition": "📖 Definition", "cloze": "🧩 Fill in the blank", "mix": "🎲 Mixed"}
REMINDER_LABELS = {"quiz": "🧩 Quiz", "full": "📄 Full"}


async def clean_input(do, chat_id, message_id):
    if message_id:
        try:
            await tg_call(do.env, "deleteMessage", {"chat_id": chat_id, "message_id": message_id})
        except Exception:
            pass  # Cleanup is optional; a network failure must not discard the setting.


def _quiet_label(do) -> str:
    try:
        s, e = int(do.setting("quiet_start")), int(do.setting("quiet_end"))
    except ValueError:
        return "off"
    return "off" if s == e else f"{s:02d}:00 – {e:02d}:00"


def _overview(do) -> str:
    return (
        texts.SETTINGS_MENU + "\n\n"
        f"🎯 Daily target: <b>{do.setting('daily_target')}</b>\n"
        "🔔 Quiz: Vietnamese to English\n"
        f"🌙 Quiet hours: <b>{_quiet_label(do)}</b>"
    )


async def show(do, chat_id, message_id=None):
    do.set_fsm(chat_id, None)
    if message_id:
        await edit_message(do.env, chat_id, message_id, _overview(do), reply_markup=SETTINGS_MENU_KB)
    else:
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
        do.set_fsm(chat_id, None)
        await edit_message(do.env, chat_id, message_id,
                           texts.SETTINGS_QUIET.format(current=_quiet_label(do)),
                           reply_markup=QUIET_KB)
    elif section == "mode":
        await edit_message(do.env, chat_id, message_id,
                           texts.SETTINGS_MODE.format(
                               current=MODE_LABELS.get(do.setting("mode"), "?")),
                           reply_markup=MODE_KB)


async def begin_quiet_input(do, chat_id, message_id):
    do.set_fsm(chat_id, {"flow": "set_quiet_start", "message_id": message_id})
    await edit_message(do.env, chat_id, message_id, texts.QUIET_START_ASK.format(
        current=_quiet_label(do)), reply_markup=kb_back_menu())


async def _quiet_input_prompt(do, chat_id, fsm, text):
    try:
        hour = int(text)
        if not 0 <= hour <= 23 or text.strip() != str(hour):
            raise ValueError
    except ValueError:
        prompt = texts.QUIET_START_INVALID if fsm["flow"] == "set_quiet_start" else texts.QUIET_END_INVALID
        await edit_message(do.env, chat_id, fsm["message_id"], prompt, reply_markup=kb_back_menu())
        return

    if fsm["flow"] == "set_quiet_start":
        fsm.update(flow="set_quiet_end", quiet_start=hour)
        do.set_fsm(chat_id, fsm)
        await edit_message(do.env, chat_id, fsm["message_id"], texts.QUIET_END_ASK,
                           reply_markup=kb_back_menu())
        return

    do.put_setting("quiet_start", str(fsm["quiet_start"]))
    do.put_setting("quiet_end", str(hour))
    do._reschedule()
    do.set_fsm(chat_id, None)
    await show_section(do, chat_id, fsm["message_id"], "quiet")


async def on_quiet_input(do, chat_id, fsm, text: str):
    await _quiet_input_prompt(do, chat_id, fsm, text.strip())


async def on_target_input(do, chat_id, text: str):
    fsm = do.storage.kv.get(f"fsm:{chat_id}") or {}
    mid = fsm.get("message_id")
    t = text.strip()
    if not (t.isascii() and t.isdigit()) or int(t) < 1:
        if mid:
            await edit_message(do.env, chat_id, mid, texts.TARGET_INVALID, reply_markup=kb_back_menu())
        else:
            await send_message(do.env, chat_id, texts.TARGET_INVALID, reply_markup=kb_back_menu())
        return
    do.put_setting("daily_target", t)
    do.set_fsm(chat_id, None)
    do._reschedule()
    await do.on_menu(chat_id, "home", mid)


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
    if spec == "custom":
        await begin_quiet_input(do, chat_id, message_id)
        return
    if spec == "off":
        do.put_setting("quiet_start", "1")
        do.put_setting("quiet_end", "1")
    else:
        parts = spec.split(":")
        if len(parts) == 2 and all(p.isdigit() and 0 <= int(p) <= 23 for p in parts):
            do.put_setting("quiet_start", str(int(parts[0])))
            do.put_setting("quiet_end", str(int(parts[1])))
        else:
            return
    do._reschedule()
    await show_section(do, chat_id, message_id, "quiet")
