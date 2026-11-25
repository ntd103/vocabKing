"""Edit through the shared vocabulary table, then choose a field and value."""

from html import escape

import texts
from handlers import vocab_list
from services import dict_service
from telegram import kb

FIELD_LABELS = {
    "word": "🔤 Word",
    "phonetic": "🔊 IPA",
    "define_en": "🇬🇧 Definition",
    "meaning": "🇻🇳 Meaning",
    "pos": "🏷 Part of speech",
    "example": "📝 Example",
    "note": "ℹ️ Note",
}


async def start(do, chat_id, kw: str = "", message_id=None):
    await vocab_list.show_page(do, chat_id, message_id=message_id, action="edit", query=kw, table=True)


async def search(do, chat_id, kw: str, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    await start(do, chat_id, kw, message_id or state.get("message_id"))


def _word_summary(word) -> str:
    phonetic = f"/{escape(word.phonetic.strip('/'))}/" if word.phonetic else "—"
    return (
        f"✏️ <b>Edit word: {escape(word.word)}</b>\n\n"
        f"🔤 <b>Word:</b> {escape(word.word)}\n"
        f"🔊 <b>IPA:</b> {phonetic}\n"
        f"🇬🇧 <b>Definition:</b> {escape(word.define_en or '—')}\n"
        f"🇻🇳 <b>Meaning:</b> {escape(word.meaning or '—')}\n"
        f"🏷 {escape(word.pos or '—')}\n"
        f"📝 <b>Example:</b> {escape(word.example or '—')}\n"
        f"ℹ️ <b>Note:</b> {escape(word.note or '—')}\n\n"
        "Choose a field:"
    )


async def pick_word(do, chat_id, word_id: int, message_id=None):
    word = do.word_row(word_id)
    if word is None:
        return
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    mid = message_id or state.get("message_id")
    do.set_fsm(chat_id, {
        **state, "flow": "edit_pick_field", "action": "edit",
        "word_id": word_id, "message_id": mid,
    })
    await vocab_list.display(do, chat_id, _word_summary(word), _edit_picker_kb(word_id), mid)


async def fill_missing(do, chat_id, word_id: int, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    if (state.get("flow") != "edit_pick_field" or state.get("action") != "edit"
            or state.get("word_id") != word_id
            or state.get("message_id") != message_id):
        return

    word = do.word_row(word_id)
    if word is None:
        return await vocab_list.finish(do, chat_id, "⚠️ Word no longer exists.", message_id)
    missing = [field for field in ("phonetic", "define_en", "example")
               if not (getattr(word, field) or "").strip()]
    if not missing:
        await vocab_list.display(
            do, chat_id, "ℹ️ No missing fields.\n\n" + _word_summary(word),
            _edit_picker_kb(word_id), message_id,
        )
        return

    info = await dict_service.lookup(word.word)
    current = do.storage.kv.get(f"fsm:{chat_id}") or {}
    if (current.get("flow") != "edit_pick_field" or current.get("action") != "edit"
            or current.get("word_id") != word_id or current.get("message_id") != message_id):
        return
    latest = do.word_row(word_id)
    if latest is None:
        return await vocab_list.finish(do, chat_id, "⚠️ Word no longer exists.", message_id)
    if (latest.word or "").casefold() != word.word.casefold():
        await vocab_list.display(
            do, chat_id, "⚠️ Word changed during lookup. No changes saved.",
            _edit_picker_kb(word_id), message_id,
        )
        return
    if info is None:
        await vocab_list.display(
            do, chat_id, "⚠️ Word not found in the dictionary.",
            _edit_picker_kb(word_id), message_id,
        )
        return

    values = {"phonetic": info.get("phonetic"), "define_en": info.get("definition"),
              "example": info.get("example")}
    updates = {field: (value.strip("/") if field == "phonetic" else value.strip())
               for field, value in values.items()
               if not (getattr(latest, field) or "").strip()
               and isinstance(value, str) and value.strip()}
    if updates:
        assignments = ", ".join(f"{field} = ?" for field in updates)
        do.storage.sql.exec(f"UPDATE words SET {assignments} WHERE id = ?",
                            *updates.values(), word_id)
        refreshed = do.word_row(word_id)
        detail = ", ".join(FIELD_LABELS[field] for field in updates)
        body = f"✅ Filled: {escape(detail)}.\n\n" + _word_summary(refreshed)
    else:
        body = "ℹ️ No dictionary data for the missing fields."
    await vocab_list.display(do, chat_id, body, _edit_picker_kb(word_id), message_id)


def _edit_picker_kb(word_id):
    fields = list(FIELD_LABELS)
    rows = [[(FIELD_LABELS[field], f"editf:{word_id}:{field}")
             for field in fields[i:i + 2]] for i in range(0, len(fields), 2)]
    rows += [[("✨ Fill missing fields", f"editfill:{word_id}")]]
    return kb(rows + [[("◀️ Back", "edit:cancel")]])


async def pick_field(do, chat_id, word_id: int, field: str, message_id=None):
    if field not in FIELD_LABELS:
        return
    word = do.word_row(word_id)
    if word is None:
        return
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    mid = message_id or state.get("message_id")
    do.set_fsm(chat_id, {
        **state, "flow": "edit_value", "action": "edit",
        "word_id": word_id, "field": field, "message_id": mid,
    })
    await vocab_list.display(
        do, chat_id,
        texts.EDIT_FIELD_ASK.format(field=FIELD_LABELS[field], word=escape(word.word)),
        kb([[("❌ Cancel", "edit:cancel")]]), mid,
    )


async def on_value(do, chat_id, fsm, text: str):
    word_id, field = fsm["word_id"], fsm["field"]
    if field not in FIELD_LABELS:
        do.set_fsm(chat_id, None)
        return
    value = None if text.strip().lower() in ("-", "null", "none") else text.strip()
    if field in ("word", "define_en", "meaning") and not value:
        await vocab_list.display(
            do, chat_id, "⚠️ Enter a nonempty value.",
            kb([[("❌ Cancel", "edit:cancel")]]), fsm.get("message_id"),
        )
        return
    if do.word_row(word_id) is None:
        return await vocab_list.finish(do, chat_id, "⚠️ Word no longer exists.", fsm.get("message_id"))
    do.storage.sql.exec(f"UPDATE words SET {field} = ? WHERE id = ?", value, word_id)
    preview = " ".join(value.split()) if value else "(cleared)"
    if len(preview) > 80:
        preview = preview[:79] + "…"
    await vocab_list.finish(
        do, chat_id,
        texts.EDIT_SAVED.format(field=FIELD_LABELS[field], value=preview),
        fsm.get("message_id"),
    )


async def cancel(do, chat_id, message_id=None):
    await vocab_list.finish(do, chat_id, "↩️ Edit cancelled.", message_id)
