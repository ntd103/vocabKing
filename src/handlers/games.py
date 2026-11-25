"""Games. Currently: story-weaving (viết chuyện chêm)."""

import texts
from handlers.vocab_list import display
from keyboards import GAMES_MENU_KB
from telegram import kb, md_table, send_message

MAX_STORY_WORDS = 20
STORY_BACK_KB = kb([[("◀️ Games", "menu:games"), ("🏠 Menu", "menu:home")]])


async def show_menu(do, chat_id, message_id=None):
    do.set_fsm(chat_id, None)
    if message_id:
        await display(do, chat_id, texts.GAMES_MENU, GAMES_MENU_KB, message_id)
    else:
        await send_message(do.env, chat_id, texts.GAMES_MENU, reply_markup=GAMES_MENU_KB)


async def story_ask_count(do, chat_id, message_id):
    do.set_fsm(chat_id, {"flow": "game_story_count", "message_id": message_id})
    await display(do, chat_id, texts.STORY_ASK_COUNT, STORY_BACK_KB, message_id)


async def story_on_count(do, chat_id, text: str):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    mid = state.get("message_id")
    t = text.strip()
    if not (t.isascii() and t.isdigit()) or not (1 <= int(t) <= MAX_STORY_WORDS):
        await display(do, chat_id, texts.STORY_INVALID_COUNT, STORY_BACK_KB, mid)
        return
    n = int(t)
    rows = list(do.storage.sql.exec(
        "SELECT word, meaning FROM words ORDER BY RANDOM() LIMIT ?", n
    ))
    do.set_fsm(chat_id, None)
    if not rows:
        await display(do, chat_id, texts.STORY_EMPTY, STORY_BACK_KB, mid)
        return
    table = md_table(
        ["#", "Word", "Meaning"],
        [[str(i), r.word, r.meaning or "—"] for i, r in enumerate(rows, 1)],
        aligns=["right", "left", "left"],
        limits=[6, 28, 48],
    )
    message = texts.STORY_WORDS.format(n=len(rows), words=table)
    await display(do, chat_id, message, STORY_BACK_KB, mid, rich=True)
