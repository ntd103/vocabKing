"""/add — add words (single or bulk) with preview + confirm."""

import texts
from keyboards import CONFIRM_ADD_KB
from services.word_parser import format_preview, parse_add_input
from telegram import edit_message, send_message

PREVIEW_LIMIT = 30


async def start(do, chat_id, arg: str):
    if arg:
        return await on_input(do, chat_id, arg)
    do.set_fsm(chat_id, {"flow": "add_input"})
    await send_message(do.env, chat_id, texts.ADD_ASK_INPUT)


async def on_input(do, chat_id, text: str):
    entries = parse_add_input(text)
    if not entries:
        do.set_fsm(chat_id, {"flow": "add_input"})
        await send_message(do.env, chat_id, texts.ADD_EMPTY)
        return
    do.set_fsm(chat_id, {"flow": "add_confirm", "entries": entries})
    shown = entries[:PREVIEW_LIMIT]
    extra = f"\n… và {len(entries) - PREVIEW_LIMIT} từ nữa" if len(entries) > PREVIEW_LIMIT else ""
    await send_message(
        do.env,
        chat_id,
        format_preview(shown) + extra,
        reply_markup=CONFIRM_ADD_KB,
    )


async def on_confirm(do, chat_id, message_id, action: str):
    fsm = do.storage.kv.get(f"fsm:{chat_id}")
    if fsm and fsm.get("flow") == "add_confirm" and action == "confirm":
        entries = fsm.get("entries", [])
        for e in entries:
            do.insert_word(int(do.env.OWNER_ID), e)
        n = len(entries)
        do.set_fsm(chat_id, None)
        await edit_message(do.env, chat_id, message_id, texts.ADD_CONFIRMED.format(n))
        # newly added cards are due immediately — schedule a reminder
        do.storage.setAlarm(int(__import__("time").time() * 1000) + 60_000)
    else:
        do.set_fsm(chat_id, None)
        await edit_message(do.env, chat_id, message_id, texts.ADD_CANCELLED)
