"""Games. Currently: story-weaving (viết chuyện chêm)."""

import random

import texts
from keyboards import GAMES_MENU_KB, kb_back_menu
from telegram import edit_message, send_message

MAX_STORY_WORDS = 20


async def show_menu(do, chat_id):
    await send_message(do.env, chat_id, texts.GAMES_MENU, reply_markup=GAMES_MENU_KB)


async def story_ask_count(do, chat_id, message_id):
    do.set_fsm(chat_id, {"flow": "game_story_count", "message_id": message_id})
    await edit_message(do.env, chat_id, message_id, texts.STORY_ASK_COUNT,
                       reply_markup=kb_back_menu())


async def story_on_count(do, chat_id, text: str):
    t = text.strip()
    if not t.isdigit() or not (1 <= int(t) <= MAX_STORY_WORDS):
        await send_message(do.env, chat_id, texts.STORY_INVALID_COUNT)
        return
    n = int(t)
    rows = list(do.storage.sql.exec("SELECT word, meaning FROM words"))
    if not rows:
        do.set_fsm(chat_id, None)
        await send_message(do.env, chat_id, texts.STORY_EMPTY)
        return
    picked = random.sample(rows, min(n, len(rows)))
    lines = "\n".join(f"• <b>{r.word}</b> — {r.meaning or '?'}" for r in picked)
    do.set_fsm(chat_id, None)
    await send_message(do.env, chat_id, texts.STORY_WORDS.format(n=len(picked), words=lines),
                       reply_markup=kb_back_menu())
