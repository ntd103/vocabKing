"""/edit — search, pick a word, pick a field, send new value."""

import texts
from keyboards import EDIT_FIELDS_KB
from telegram import edit_message, send_message

FIELD_LABELS = {
    "word": "Từ",
    "phonetic": "Phiên âm",
    "meaning": "Nghĩa",
    "example": "Ví dụ",
    "note": "Note",
}


def _result_kb(rows, prefix: str):
    from telegram import kb

    if not rows:
        return None
    return kb([[(f"{r.word}", f"{prefix}:{r.id}")] for r in rows])


async def start(do, chat_id, kw: str):
    if kw:
        return await search(do, chat_id, kw)
    do.set_fsm(chat_id, {"flow": "edit_search"})
    await send_message(do.env, chat_id, texts.EDIT_ASK_SEARCH)


async def search(do, chat_id, kw: str):
    do.set_fsm(chat_id, None)
    rows = do.search_words(kw)
    if not rows:
        await send_message(do.env, chat_id, texts.EDIT_NOT_FOUND.format(kw))
        return
    kb_ = _result_kb(rows, "editw")
    if len(rows) == 1:
        return await pick_word(do, chat_id, rows[0]["id"])
    await send_message(do.env, chat_id, texts.EDIT_PICKED, reply_markup=kb_)


async def pick_word(do, chat_id, word_id: int):
    word = do.word_row(word_id)
    if word is None:
        return
    body = (
        f"✏️ Sửa từ: <b>{word.word}</b>\n"
        f"Phụ đề: {word.meaning or '—'}\n\n"
        "Chọn trường cần sửa:"
    )
    kb_ = [
        [
            {"text": "🔤 Từ", "callback_data": f"editf:{word_id}:word"},
            {"text": "🔊 Phiên âm", "callback_data": f"editf:{word_id}:phonetic"},
        ],
        [
            {"text": "🇻🇳 Nghĩa", "callback_data": f"editf:{word_id}:meaning"},
            {"text": "📝 Ví dụ", "callback_data": f"editf:{word_id}:example"},
        ],
        [{"text": "ℹ️ Note", "callback_data": f"editf:{word_id}:note"}],
    ]
    await send_message(do.env, chat_id, body, reply_markup=kb_)


async def pick_field(do, chat_id, word_id: int, field: str):
    if field not in FIELD_LABELS:
        return
    word = do.word_row(word_id)
    if word is None:
        return
    do.set_fsm(chat_id, {"flow": "edit_value", "word_id": word_id, "field": field})
    await send_message(
        do.env,
        chat_id,
        texts.EDIT_FIELD_ASK.format(field=FIELD_LABELS[field], word=word.word),
    )


async def on_value(do, chat_id, fsm, text: str):
    word_id, field = fsm["word_id"], fsm["field"]
    if field not in FIELD_LABELS:
        do.set_fsm(chat_id, None)
        return
    value = None if text.strip().lower() in ("-", "null", "none") else text.strip()
    do.storage.sql.exec(
        f"UPDATE words SET {field} = ? WHERE id = ?", value, word_id
    )
    do.set_fsm(chat_id, None)
    word = do.word_row(word_id)
    label = value if value is not None else "(xoá trắng)"
    await send_message(
        do.env,
        chat_id,
        texts.EDIT_SAVED.format(field=FIELD_LABELS[field], value=label),
    )
