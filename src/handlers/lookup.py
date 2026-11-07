"""Dictionary lookup flow: gõ từ → IPA + def EN → user gõ VI → example → save."""

import texts
from keyboards import CONFIRM_LOOKUP_KB, LOOKUP_EXAMPLE_KB, kb_back_menu
from services import dict_service
from telegram import edit_message, send_message

MAX_DEF_LEN = 200
MAX_EX_LEN = 300


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


async def start(do, chat_id, word: str):
    """Entry: user typed a bare English word, or chose 'Tra từ điển'."""
    info = await dict_service.lookup(word)
    if info is None:
        await send_message(do.env, chat_id,
                           texts.LOOKUP_NOT_FOUND.format(word=word),
                           reply_markup=kb_back_menu())
        return
    do.set_fsm(chat_id, {"flow": "lookup_vi", "info": info})
    pos_part = f" — <i>{info['pos']}</i>" if info["pos"] else ""
    phon_part = f" <b>{info['phonetic']}</b>" if info["phonetic"] else ""
    body = (
        f"🔍 <b>{info['word']}</b>{phon_part}{pos_part}\n\n"
        f"💡 {_clip(info['definition'], MAX_DEF_LEN)}\n\n"
        + texts.LOOKUP_ASK_VI.format(word=info["word"])
    )
    await send_message(do.env, chat_id, body, reply_markup=kb_back_menu())


async def on_text_input(do, chat_id, fsm, text: str):
    """User typed the Vietnamese meaning or a manual example."""
    flow = fsm["flow"]
    info = fsm["info"]
    if flow == "lookup_vi":
        info["meaning_vi"] = _clip(text, 200)
        do.set_fsm(chat_id, {"flow": "lookup_example", "info": info})
        await send_message(do.env, chat_id,
                           texts.LOOKUP_ASK_EXAMPLE.format(word=info["word"]),
                           reply_markup=LOOKUP_EXAMPLE_KB)
    elif flow == "lookup_example_manual":
        info["example_final"] = _clip(text, MAX_EX_LEN)
        do.set_fsm(chat_id, {"flow": "lookup_save", "info": info})
        await _show_preview(do, chat_id, info)


async def on_example_choice(do, chat_id, message_id, choice: str):
    fsm = do.storage.kv.get(f"fsm:{chat_id}")
    if not fsm or fsm.get("flow") != "lookup_example":
        return
    info = fsm["info"]
    if choice == "api":
        ex = info.get("example", "")
        if not ex:
            do.set_fsm(chat_id, {"flow": "lookup_example_manual", "info": info})
            await edit_message(do.env, chat_id, message_id,
                               texts.LOOKUP_NO_EXAMPLE_IN_DICT)
            return
        info["example_final"] = _clip(ex, MAX_EX_LEN)
        do.set_fsm(chat_id, {"flow": "lookup_save", "info": info})
        await edit_message(do.env, chat_id, message_id, _preview_body(info),
                           reply_markup=CONFIRM_LOOKUP_KB)
    elif choice == "manual":
        do.set_fsm(chat_id, {"flow": "lookup_example_manual", "info": info})
        await edit_message(do.env, chat_id, message_id,
                           texts.LOOKUP_ASK_EXAMPLE_MANUAL.format(word=info["word"]))
    elif choice == "skip":
        info["example_final"] = ""
        do.set_fsm(chat_id, {"flow": "lookup_save", "info": info})
        await edit_message(do.env, chat_id, message_id, _preview_body(info),
                           reply_markup=CONFIRM_LOOKUP_KB)


def _preview_body(info) -> str:
    phon = f" {info['phonetic']}" if info.get("phonetic") else ""
    return texts.LOOKUP_PREVIEW.format(
        word=info["word"], phonetic=phon, pos=info.get("pos") or "",
        definition=_clip(info.get("definition", ""), MAX_DEF_LEN),
        meaning=info.get("meaning_vi", ""),
        example=info.get("example_final") or "—",
    )


async def _show_preview(do, chat_id, info):
    await send_message(do.env, chat_id, _preview_body(info), reply_markup=CONFIRM_LOOKUP_KB)


async def on_save(do, chat_id, message_id, action: str):
    fsm = do.storage.kv.get(f"fsm:{chat_id}")
    if not fsm or fsm.get("flow") != "lookup_save":
        return
    if action != "ok":
        do.set_fsm(chat_id, None)
        await edit_message(do.env, chat_id, message_id, texts.ADD_CANCELLED)
        return
    info = fsm["info"]
    n = do.insert_words_bulk(int(do.env.OWNER_ID), [{
        "word": info["word"],
        "phonetic": (info.get("phonetic") or "").strip("/") or None,
        "meaning": info.get("meaning_vi"),
        "example": info.get("example_final") or None,
        "note": None,
    }])
    do.daily_add(n)
    do.set_fsm(chat_id, None)
    added, reviewed = do.daily_counts()
    await edit_message(do.env, chat_id, message_id,
                       texts.ADD_CONFIRMED.format(n=n, today=added + reviewed,
                                                  target=do.target()))
    do._reschedule()
