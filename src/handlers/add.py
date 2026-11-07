"""/add — menu: dictionary lookup OR manual bulk input with preview + confirm."""

import texts
from keyboards import ADD_MENU_KB, CONFIRM_ADD_KB
from services.word_parser import format_preview, parse_add_input
from telegram import edit_message, send_message

PREVIEW_LIMIT = 20  # keep messages well under Telegram's 4096-char cap


async def show_menu(do, chat_id, message_id=None):
    if message_id:
        await edit_message(do.env, chat_id, message_id, texts.ADD_MENU,
                           reply_markup=ADD_MENU_KB)
    else:
        await send_message(do.env, chat_id, texts.ADD_MENU, reply_markup=ADD_MENU_KB)


async def start(do, chat_id, arg: str):
    if arg:
        return await on_input(do, chat_id, arg)
    await show_menu(do, chat_id)


async def on_mode_pick(do, chat_id, message_id, mode: str):
    if mode == "lookup":
        do.set_fsm(chat_id, None)  # user just types a bare word
        await edit_message(do.env, chat_id, message_id, texts.LOOKUP_ASK)
    elif mode == "manual":
        do.set_fsm(chat_id, {"flow": "add_input"})
        await edit_message(do.env, chat_id, message_id, texts.ADD_ASK_INPUT)


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
        do.env, chat_id, format_preview(shown) + extra,
        reply_markup=CONFIRM_ADD_KB,
    )


async def on_confirm(do, chat_id, message_id, action: str):
    fsm = do.storage.kv.get(f"fsm:{chat_id}")
    if fsm and fsm.get("flow") == "add_confirm" and action == "confirm":
        entries = fsm.get("entries", [])
        n = do.insert_words_bulk(int(do.env.OWNER_ID), entries)
        do.daily_add(n)
        do.set_fsm(chat_id, None)
        added, reviewed = do.daily_counts()
        await edit_message(do.env, chat_id, message_id,
                           texts.ADD_CONFIRMED.format(n=n, today=added + reviewed,
                                                      target=do.target()))
        # newly added cards are due immediately — schedule a reminder
        do._reschedule()
    else:
        do.set_fsm(chat_id, None)
        await edit_message(do.env, chat_id, message_id, texts.ADD_CANCELLED)
