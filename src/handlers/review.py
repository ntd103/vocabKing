"""Review flows: prompts, replies (? / ??? / answer), rating buttons."""

import random

import texts
from keyboards import SHOW_ANSWER_KB, fmt_rate_kb
from services import cloze, fsrs_service
from telegram import edit_message, send_message


def _pick_mode(do) -> str:
    mode = do.setting("mode")
    if mode == "mix":
        return random.choice(["definition", "cloze"])
    return mode


def _pick_due(do):
    now = do._now().isoformat()
    rows = list(
        do.storage.sql.exec(
            "SELECT id, word_id, card_json, due FROM cards WHERE due <= ? ORDER BY due LIMIT 1",
            now,
        )
    )
    return rows[0] if rows else None


async def start_study(do, chat_id):
    card_row = _pick_due(do)
    if card_row is None:
        await send_message(do.env, chat_id, texts.STUDY_NONE_DUE)
        return
    word = do.word_row(card_row.word_id)
    await send_prompt(do, chat_id, card_row, word)


async def send_prompt(do, chat_id, card_row, word):
    """Send a review prompt for one card; store the session on the message."""
    mode = _pick_mode(do)
    if mode == "cloze" and word.example:
        masked = cloze.mask_word(word.example)
        hint = word.meaning or word.word
        text = cloze.render_cloze_prompt(masked, hint) + "\n\n" + texts.REPLY_HINT
        session = {
            "card_id": card_row.id,
            "word_id": word.id,
            "mode": "cloze",
            "masked": masked,
            "reveals": 0,
        }
    else:
        text = texts.DEFINITION_PROMPT.format(
            word=word.word, phonetic=f"/{word.phonetic.strip('/')}/" if word.phonetic else "",
        ) + "\n\n" + texts.REPLY_HINT
        session = {
            "card_id": card_row.id,
            "word_id": word.id,
            "mode": "definition",
            "masked": None,
            "reveals": 0,
        }
    sent = await send_message(
        do.env, chat_id, text,
        reply_markup=SHOW_ANSWER_KB if session["mode"] == "definition" else None,
    )
    message_id = sent.get("result", {}).get("message_id")
    if message_id:
        session["message_id"] = message_id
        do.put_session(message_id, session)


async def on_reply(do, chat_id, reply_to_id, text) -> bool:
    """Handle a reply to an active review prompt. Returns True if handled."""
    session = do.get_session(reply_to_id)
    if session is None:
        return False
    word = do.word_row(session["word_id"])
    if word is None:
        do.pop_session(reply_to_id)
        return False

    t = text.strip()
    if t in ("?", "???"):
        if t == "???":
            session["masked"] = cloze.reveal_letters(
                word.example, session["masked"], count=999, seed=session["card_id"]
            )
        else:
            session["reveals"] += 1
            n_revealed = max(1, cloze.count_masked(word.example, session["masked"]) // 4)
            session["masked"] = cloze.reveal_letters(
                word.example, session["masked"], count=n_revealed,
                seed=session["card_id"] * 100 + session["reveals"],
            )
        do.put_session(reply_to_id, session)
        hint = word.meaning or word.word
        body = cloze.render_cloze_prompt(session["masked"], hint)
        if cloze.fully_revealed(word.example, session["masked"]):
            do.pop_session(reply_to_id)
            body += "\n\n" + texts.CLOZE_FULL.format(
                word=word.word, phonetic=_phon(word), example=word.example, meaning=word.meaning or "—",
            )
            await edit_message(do.env, chat_id, reply_to_id, body, reply_markup=fmt_rate_kb(session["card_id"]))
            return True
        body += "\n\n" + texts.REPLY_HINT
        await edit_message(do.env, chat_id, reply_to_id, body)
        return True

    # a plain answer: score it (cloze) or just reveal (definition)
    if session["mode"] == "cloze" and session["masked"]:
        ok = cloze.check_answer(word.example, t)
        body = (texts.CLOZE_CORRECT if ok else texts.CLOZE_WRONG).format(
            word=word.word, meaning=word.meaning or "—",
        )
    else:
        body = texts.DEFINITION_ANSWER.format(
            word=word.word, phonetic=_phon(word),
            meaning=word.meaning or "—", example=word.example or "—", note=word.note or "",
        )
    do.pop_session(reply_to_id)
    await edit_message(do.env, chat_id, reply_to_id, body, reply_markup=fmt_rate_kb(session["card_id"]))
    return True


def _phon(word) -> str:
    return f"/{word.phonetic.strip('/')}/" if word.phonetic else ""


async def show_answer(do, chat_id, message_id, card_id):
    session = do.get_session(message_id)
    word = do.word_row(session["word_id"]) if session else None
    if word is None:
        return
    body = texts.DEFINITION_ANSWER.format(
        word=word.word, phonetic=_phon(word),
        meaning=word.meaning or "—", example=word.example or "—", note=word.note or "",
    )
    await edit_message(do.env, chat_id, message_id, body, reply_markup=fmt_rate_kb(card_id))


async def rate(do, chat_id, message_id, card_id, rating_name: str):
    card_row = do.get_card(card_id)
    if card_row is None:
        return
    card = fsrs_service.card_from_json(card_row.card_json)
    updated, days = fsrs_service.review(card, rating_name)
    do.save_card(card_id, updated)
    do.log_review(card_id, rating_name)
    do.pop_session(message_id)

    word = do.word_row(card_row.word_id)
    body = texts.RATED_FEEDBACK.format(
        word=word.word if word else "?",
        rating=texts.RATE_NAMES.get(rating_name, rating_name),
        interval=texts.interval_human(days),
    )
    await edit_message(do.env, chat_id, message_id, body)

    # continuous studying: immediately prompt the next due card, if any
    nxt = _pick_due(do)
    if nxt is not None and nxt.id != card_id:
        nw = do.word_row(nxt.word_id)
        if nw is not None:
            await send_prompt(do, chat_id, nxt, nw)
