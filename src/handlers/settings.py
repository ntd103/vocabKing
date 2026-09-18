"""/settings — quiet hours and default review mode."""

import texts
from keyboards import MODE_KB, QUIET_KB
from telegram import edit_message, send_message

MODE_LABELS = {"definition": "📖 Định nghĩa", "cloze": "🧩 Điền khuyết", "mix": "🎲 Trộn ngẫu nhiên"}


def _quiet_label(do) -> str:
    try:
        s, e = int(do.setting("quiet_start")), int(do.setting("quiet_end"))
    except ValueError:
        return "tắt"
    if s == e:
        return "tắt"
    return f"{s:02d}:00 – {e:02d}:00"


async def show(do, chat_id):
    body = texts.SETTINGS_HEADER + "\n" + f"Hiện tại: {MODE_LABELS.get(do.setting('mode'), '?')}"
    await send_message(do.env, chat_id, body, reply_markup=MODE_KB)
    await send_message(do.env, chat_id, texts.SETTINGS_QUIET.format(_quiet_label(do)), reply_markup=QUIET_KB)


async def set_mode(do, chat_id, message_id, mode: str):
    if mode not in MODE_LABELS:
        return
    do.storage.kv.put("set:mode", mode)
    await edit_message(do.env, chat_id, message_id, texts.SETTINGS_MODE_SAVED.format(MODE_LABELS[mode]))


async def set_quiet(do, chat_id, message_id, spec: str):
    if spec == "off":
        do.storage.kv.put("set:quiet_start", "1")
        do.storage.kv.put("set:quiet_end", "1")
    else:
        parts = spec.split(":")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            do.storage.kv.put("set:quiet_start", str(int(parts[0])))
            do.storage.kv.put("set:quiet_end", str(int(parts[1])))
        else:
            return
    await edit_message(do.env, chat_id, message_id, texts.SETTINGS_QUIET_SAVED.format(_quiet_label(do)))
