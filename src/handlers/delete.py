"""/delete — search, pick, confirm-delete (cascade card + reviews)."""

import texts
from telegram import edit_message, send_message


async def start(do, chat_id, kw: str):
    if kw:
        return await search(do, chat_id, kw)
    do.set_fsm(chat_id, {"flow": "delete_search"})
    await send_message(do.env, chat_id, texts.DELETE_ASK_SEARCH)


async def search(do, chat_id, kw: str):
    do.set_fsm(chat_id, None)
    rows = do.search_words(kw)
    if not rows:
        await send_message(do.env, chat_id, texts.EDIT_NOT_FOUND.format(kw))
        return
    kb_ = [[{"text": r.word, "callback_data": f"delw:{r.id}"}] for r in rows]
    if len(rows) == 1:
        return await pick_word(do, chat_id, rows[0]["id"])
    await send_message(do.env, chat_id, texts.DELETE_PICKED, reply_markup=kb_)


async def pick_word(do, chat_id, word_id: int):
    word = do.word_row(word_id)
    if word is None:
        return
    body = (
        f"🗑 Xoá từ: <b>{word.word}</b>\n"
        f"Nghĩa: {word.meaning or '—'}\n\n"
        "Xoá cả lịch sử ôn của từ này. Chắc chắn chứ?"
    )
    kb_ = [
        [
            {"text": "🗑 Xoá chắc chắn", "callback_data": f"del:confirm:{word_id}"},
            {"text": "❌ Giữ lại", "callback_data": "del:cancel"},
        ]
    ]
    await send_message(do.env, chat_id, body, reply_markup=kb_)


async def confirm(do, chat_id, word_id: int):
    word = do.word_row(word_id)
    if word is None:
        return
    # delete card + review history explicitly (DO SQLite may not enforce FK cascade)
    do.storage.sql.exec("DELETE FROM reviews WHERE card_id IN (SELECT id FROM cards WHERE word_id = ?)", word_id)
    do.storage.sql.exec("DELETE FROM cards WHERE word_id = ?", word_id)
    do.storage.sql.exec("DELETE FROM words WHERE id = ?", word_id)
    await send_message(do.env, chat_id, texts.DELETE_DONE.format(word.word))
