"""Delete vocabulary entries after explicit confirmation."""

from html import escape

import texts
from handlers import vocab_list
from keyboards import delete_all_confirm_kb
from telegram import edit_message, kb


async def start(do, chat_id, kw: str = "", message_id=None):
    await vocab_list.show_page(do, chat_id, message_id=message_id, action="delete", query=kw, table=True)


async def confirm_all_prompt(do, chat_id, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    mid = message_id or state.get("message_id")
    await vocab_list.display(
        do, chat_id,
        "⚠️ <b>Delete all vocabulary?</b>\n\nPermanently delete all words, cards and review history?",
        delete_all_confirm_kb(), mid,
    )
    do.set_fsm(chat_id, {**state, "flow": "delete_all_confirm", "message_id": mid})


async def cancel_all(do, chat_id, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    if state.get("flow") != "delete_all_confirm":
        return
    await vocab_list.finish(do, chat_id, "↩️ Deletion cancelled. No words deleted.", message_id)


async def confirm_all(do, chat_id, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    if state.get("flow") != "delete_all_confirm":
        return
    pending = do.storage.kv.get("review:pending") or {}
    pending_message_id = pending.get("message_id")

    def remove_all():
        do.storage.sql.exec("DELETE FROM reviews")
        do.storage.sql.exec("DELETE FROM cards")
        do.storage.sql.exec("DELETE FROM words")
        do.storage.kv.delete("review:pending")
        if pending_message_id:
            do.pop_session(pending_message_id)

    do.storage.transactionSync(remove_all)
    do.storage.deleteAlarm()
    await vocab_list.finish(do, chat_id, "✅ Deleted all words and review history.", message_id)
    if pending_message_id and pending_message_id != message_id:
        await edit_message(
            do.env, pending.get("chat_id", chat_id), pending_message_id,
            "🗑 Vocabulary deleted. Review closed.", reply_markup=[],
        )


async def search(do, chat_id, kw: str, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    await start(do, chat_id, kw, message_id or state.get("message_id"))


async def pick_word(do, chat_id, word_id: int, message_id=None):
    word = do.word_row(word_id)
    if word is None:
        return
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    mid = message_id or state.get("message_id")
    do.set_fsm(chat_id, {
        **state, "flow": "delete_confirm", "action": "delete",
        "word_id": word_id, "message_id": mid,
    })
    phonetic = f"/{escape(word.phonetic.strip('/'))}/" if word.phonetic else "—"
    body = (
        f"🗑 <b>Delete word: {escape(word.word)}</b>\n\n"
        f"🔊 <b>IPA:</b> {phonetic}\n"
        f"🇬🇧 <b>Definition:</b> {escape(word.define_en or '—')}\n"
        f"🇻🇳 <b>Meaning:</b> {escape(word.meaning or '—')}\n"
        f"📝 <b>Example:</b> {escape(word.example or '—')}\n"
        f"ℹ️ <b>Note:</b> {escape(word.note or '—')}\n\n"
        "⚠️ Permanently delete this word and its review history?"
    )
    await vocab_list.display(do, chat_id, body, kb([
        [("🗑 Delete permanently", f"del:confirm:{word_id}"), ("↩️ Keep", "del:cancel")],
    ]), mid)


async def confirm(do, chat_id, word_id: int, message_id=None):
    word = do.word_row(word_id)
    if word is None:
        return await vocab_list.finish(do, chat_id, "⚠️ Word no longer exists.", message_id)
    pending = do.storage.kv.get("review:pending") or {}
    card = do.get_card(pending["card_id"]) if pending.get("card_id") else None
    clear_pending = bool(card and card.word_id == word_id)
    pending_mid = pending.get("message_id")

    def remove():
        do.storage.sql.exec(
            "DELETE FROM reviews WHERE card_id IN (SELECT id FROM cards WHERE word_id = ?)",
            word_id,
        )
        do.storage.sql.exec("DELETE FROM cards WHERE word_id = ?", word_id)
        do.storage.sql.exec("DELETE FROM words WHERE id = ?", word_id)
        if clear_pending:
            do.storage.kv.delete("review:pending")
            if pending_mid:
                do.pop_session(pending_mid)

    do.storage.transactionSync(remove)
    do._reschedule()
    await vocab_list.finish(do, chat_id, texts.DELETE_DONE.format(word.word), message_id)
    if clear_pending and pending_mid and pending_mid != message_id:
        await edit_message(
            do.env, pending.get("chat_id", chat_id), pending_mid,
            "🗑 Word deleted. Review closed.", reply_markup=[],
        )


async def cancel(do, chat_id, message_id=None):
    await vocab_list.finish(do, chat_id, "↩️ Word kept.", message_id)
