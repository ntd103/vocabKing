"""/add — auto EN definition → agree/manual → pipe format → preview + confirm."""

from html import escape

import texts
from handlers.vocab_list import display, finish
from keyboards import ADD_EN_KB, ADD_INPUT_KB, CONFIRM_ADD_KB, kb_back_menu
from services import dict_service
from services.word_parser import format_preview, parse_add_input

PREVIEW_LIMIT = 20  # keep messages well under Telegram's 4096-char cap


def is_add_flow(flow: str | None) -> bool:
    return bool(flow) and str(flow).startswith("add_")


def pipe_template(word: str, define_en: str | None = None) -> str:
    """Prefill word (+ EN when accepted); leave other fields empty for the user."""
    w = (word or "").strip()
    return f"{w}||{define_en}|||" if define_en else f"{w}|||||"


def _format_prompt(word: str, define_en: str | None = None, *, notice: str = "") -> str:
    tip = pipe_template(word, define_en)
    head = f"{notice}\n\n" if notice else ""
    return (
        f"{head}{texts.ADD_ASK_INPUT}\n\n"
        f"Fill in the blanks (copy & edit):\n<code>{escape(tip)}</code>"
    )


async def _show_format(do, chat_id, word: str, define_en: str | None, message_id,
                       *, notice: str = ""):
    do.set_fsm(chat_id, {
        "flow": "add_input",
        "word": word,
        "define_en": define_en,
        "message_id": message_id,
    })
    await display(do, chat_id, _format_prompt(word, define_en, notice=notice),
                  ADD_INPUT_KB, message_id)


async def start(do, chat_id, arg: str = "", message_id=None):
    arg = (arg or "").strip()
    if arg and "|" in arg:
        return await on_input(do, chat_id, arg)
    if arg:
        return await offer_en(do, chat_id, arg, message_id=message_id)
    do.set_fsm(chat_id, {"flow": "add_ask_word", "message_id": message_id})
    await display(do, chat_id, texts.ADD_ASK_WORD, kb_back_menu(), message_id)


async def offer_en(do, chat_id, word: str, message_id=None):
    """Fetch EN definition only; ask Use/Manual, or jump to empty format on miss."""
    word = (word or "").strip()
    if not word:
        do.set_fsm(chat_id, {"flow": "add_ask_word", "message_id": message_id})
        await display(do, chat_id, texts.ADD_ASK_WORD, kb_back_menu(), message_id)
        return
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    mid = message_id if message_id is not None else state.get("message_id")
    info = await dict_service.lookup(word)
    if info is None:
        await _show_format(
            do, chat_id, word, None, mid,
            notice=texts.ADD_DICT_MISS.format(word=escape(word)),
        )
        return
    define_en = (info.get("definition") or "").strip()
    shown = info.get("word") or word
    do.set_fsm(chat_id, {
        "flow": "add_confirm_en",
        "word": shown,
        "define_en": define_en,
        "message_id": mid,
    })
    body = (
        f"🔍 <b>{escape(shown)}</b>\n\n"
        f"🇬🇧 {escape(define_en)}\n\n"
        f"{texts.ADD_ASK_EN}"
    )
    await display(do, chat_id, body, ADD_EN_KB, mid)


async def on_en_choice(do, chat_id, message_id, choice: str):
    """choice: ok | manual  (also wired from typed 1 / 2)."""
    fsm = do.storage.kv.get(f"fsm:{chat_id}") or {}
    if fsm.get("flow") != "add_confirm_en":
        return
    word = fsm.get("word") or ""
    define_en = (fsm.get("define_en") or None) if choice == "ok" else None
    mid = message_id or fsm.get("message_id")
    await _show_format(do, chat_id, word, define_en, mid)


async def on_input(do, chat_id, text: str):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    flow = state.get("flow")
    mid = state.get("message_id")

    if flow == "add_ask_word" and "|" not in text:
        return await offer_en(do, chat_id, text, message_id=mid)

    if flow == "add_confirm_en":
        choice = {"1": "ok", "2": "manual"}.get(text.strip())
        if choice:
            return await on_en_choice(do, chat_id, mid, choice)
        await display(do, chat_id, texts.ADD_BUSY, ADD_EN_KB, mid)
        return

    entries = parse_add_input(text)
    if not entries:
        word = state.get("word") or ""
        define_en = state.get("define_en")
        if word:
            await _show_format(do, chat_id, word, define_en, mid, notice=texts.ADD_EMPTY)
        else:
            do.set_fsm(chat_id, {"flow": "add_input", "message_id": mid})
            await display(do, chat_id, f"{texts.ADD_EMPTY}\n\n{texts.ADD_ASK_INPUT}",
                          ADD_INPUT_KB)
        return

    do.set_fsm(chat_id, {"flow": "add_confirm", "entries": entries, "message_id": mid})
    shown = entries[:PREVIEW_LIMIT]
    extra = f"\n… and {len(entries) - PREVIEW_LIMIT} more" if len(entries) > PREVIEW_LIMIT else ""
    await display(do, chat_id, format_preview(shown) + extra, CONFIRM_ADD_KB)


async def on_confirm(do, chat_id, message_id, action: str):
    fsm = do.storage.kv.get(f"fsm:{chat_id}")
    if fsm and fsm.get("flow") == "add_confirm" and action == "confirm":
        entries = fsm.get("entries", [])
        n = do.insert_words_bulk(int(do.env.OWNER_ID), entries)
        do.daily_add(n)
        added, reviewed = do.daily_counts()
        do._reschedule()
        await finish(do, chat_id, texts.ADD_CONFIRMED.format(
            n=n, today=added + reviewed, target=do.target()), message_id)
    else:
        await finish(do, chat_id, texts.ADD_CANCELLED, message_id)
