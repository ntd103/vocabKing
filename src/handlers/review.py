"""Session-bound quiz hints, reveals and exactly-once FSRS grading."""

import re
from html import escape

import texts
from keyboards import MENU_KB, fmt_rate_kb
from services import cloze, fsrs_service
from telegram import edit_message, send_message


def _quiz_kb(card_id):
    return [[{"text": "💡 Hint (?)", "callback_data": f"hint:{card_id}"},
             {"text": "🔓 Reveal (???)", "callback_data": f"show:{card_id}"}],
            [{"text": "🏠 Menu", "callback_data": "menu:home"}]]


def _answer(word):
    fields = [f"📖 <b>{escape(word.word)}</b>"]
    if word.phonetic:
        fields.append(f"/{escape(word.phonetic.strip('/'))}/")
    for icon, value in (("🏷", getattr(word, "pos", None)), ("🇬🇧", word.define_en),
                        ("🇻🇳", word.meaning), ("📝", word.example), ("ℹ️", word.note)):
        if value:
            fields.append(f"{icon} {escape(value)}")
    return "\n".join(fields)


def _interval(delta):
    seconds = int(delta.total_seconds())
    for unit, scale in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= scale and seconds % scale == 0:
            return f"{seconds // scale}{unit}"
    return f"{seconds}s"


def _rating_keyboard(do, mid, session):
    # Freeze all four FSRS outcomes at recall time. Drawing fuzz again on tap
    # could promise one interval and save another, especially for mature cards.
    if not session.get("choices"):
        card = fsrs_service.card_from_json(do.get_card(session["card_id"]).card_json)
        when = do._now()
        session["choices"] = {rating: fsrs_service.review(card, rating, when)[0].to_json()
                              for rating in fsrs_service.RATINGS}
        do.put_session(mid, session)
    labels = {}
    for rating, raw in session["choices"].items():
        outcome = fsrs_service.card_from_json(raw)
        labels[rating] = _interval(outcome.due - outcome.last_review)
    return fmt_rate_kb(session["card_id"], labels)


def _quiz_body(word, masked):
    pattern = re.compile(r"(?<!\w)" + re.escape(word.word) + r"(?!\w)", re.IGNORECASE)
    spaced = '   '.join(' '.join(part) for part in masked.split())
    example, matches = pattern.subn(lambda _: spaced, word.example or "")
    if not matches:
        example = spaced
    return (f"🇻🇳 {escape(word.meaning or '—')}\n\n"
            f"Type the missing word:\n<pre>{escape(example)}</pre>")


async def start_study(do, chat_id):
    do.set_fsm(chat_id, None)
    pending = do.storage.kv.get("review:pending")
    if pending:
        mid = pending.get("message_id")
        session = do.get_session(mid) if mid else None
        if session and session.get("chat_id") == str(chat_id):
            word = do.word_row(session["word_id"])
            body = _answer(word) if session.get("ready") else _quiz_body(word, session["masked"])
            await edit_message(do.env, chat_id, mid, body,
                               reply_markup=_rating_keyboard(do, mid, session) if session.get("ready") else _quiz_kb(session["card_id"]))
            return
        if pending.get("sending"):
            # In-flight reserve from send_prompt — do not start a second quiz.
            return
        # Stale reservation (session lost / prior delivery failed): recover.
        do.storage.kv.delete("review:pending")
        if mid:
            do.pop_session(mid)
        do._reschedule()
    if do.review_quota_left() <= 0:
        await send_message(do.env, chat_id,
                           texts.STUDY_QUOTA_DONE.format(target=do.target()),
                           reply_markup=MENU_KB)
        return
    card = do._pick_due_random()
    if card is None:
        _, reviewed = do.daily_counts()
        await send_message(do.env, chat_id,
                           texts.STUDY_NONE_DUE.format(done=reviewed, target=do.target()),
                           reply_markup=MENU_KB)
        return
    await send_prompt(do, chat_id, card, do.word_row(card.word_id))


async def send_prompt(do, chat_id, card_row, word):
    if do.storage.kv.get("review:pending"):
        return
    original = word.word
    masked = cloze.mask_word(original)
    body = _quiz_body(word, masked)
    # Reserve before network I/O: concurrent /study or alarm cannot send again.
    do.storage.kv.put("review:pending", {
        "card_id": card_row.id, "chat_id": str(chat_id), "sending": True,
    })
    do.storage.deleteAlarm()
    try:
        sent = await send_message(do.env, chat_id, body, reply_markup=_quiz_kb(card_row.id))
        mid = sent.get("result", {}).get("message_id")
        if not mid:
            do.storage.kv.delete("review:pending")
            do._reschedule()
            raise RuntimeError("Quiz delivery not confirmed")
        do.put_session(mid, {"card_id": card_row.id, "word_id": word.id,
                            "chat_id": str(chat_id), "mode": "vocab",
                            "original": original, "masked": masked,
                            "reveals": 0, "ready": False})
        do.storage.kv.put("review:pending", {"card_id": card_row.id,
                           "chat_id": str(chat_id), "message_id": mid})
    except Exception:
        if (do.storage.kv.get("review:pending") or {}).get("sending"):
            do.storage.kv.delete("review:pending")
            do._reschedule()
        raise


async def on_reply(do, chat_id, reply_to_id, text) -> bool:
    session = do.get_session(reply_to_id)
    if not session or session.get("chat_id") != str(chat_id):
        return False
    if session.get("ready"):
        await rate_text(do, chat_id, reply_to_id, text.strip())
        return True  # Await a grade; extra text must not start dictionary lookups.
    word = do.word_row(session["word_id"])
    if word is None:
        return False
    t = text.strip()
    if t == "?":
        original = session["original"]
        session["reveals"] += 1
        remaining = cloze.count_masked(original, session["masked"])
        count = min(max(0, remaining - 1), max(2, remaining // 4))
        session["masked"] = cloze.reveal_letters(
            original, session["masked"], count=count,
            seed=session["card_id"] * 100 + session["reveals"])
        do.put_session(reply_to_id, session)
        body = _quiz_body(word, session["masked"])
        if count == 0:
            body += "\nType the word or choose Reveal."
        await edit_message(do.env, chat_id, reply_to_id, body,
                           reply_markup=_quiz_kb(session["card_id"]))
        return True
    prefix = ""
    if t != "???":
        prefix = "✅ Correct!\n\n" if cloze.check_answer(word.word, t) else "❌ Incorrect.\n\n"
    await show_answer(do, chat_id, reply_to_id, session["card_id"], prefix)
    return True


async def show_answer(do, chat_id, message_id, card_id, prefix=""):
    session = do.get_session(message_id)
    if (not session or session["card_id"] != card_id
            or session.get("chat_id") != str(chat_id)):
        return
    word = do.word_row(session["word_id"])
    if word is None:
        return
    if session.get("ready"):
        return
    if not prefix:
        await rate(do, chat_id, message_id, card_id, "again", revealed=True)
        return
    session["ready"] = True
    keyboard = _rating_keyboard(do, message_id, session)
    await edit_message(do.env, chat_id, message_id, prefix + _answer(word), reply_markup=keyboard)


async def rate_text(do, chat_id, message_id, text):
    session = do.get_session(message_id)
    pending = do.storage.kv.get("review:pending") or {}
    if (text not in ("1", "2", "3", "4") or not session
            or pending.get("message_id") != message_id
            or pending.get("chat_id") != str(chat_id)
            or session.get("chat_id") != str(chat_id)
            or not session.get("ready")):
        if (session and session.get("ready")
                and pending.get("message_id") == message_id
                and pending.get("chat_id") == str(chat_id)
                and session.get("chat_id") == str(chat_id)):
            word = do.word_row(session["word_id"])
            if word is not None:
                await edit_message(do.env, chat_id, message_id,
                                   _answer(word) + "\n\nEnter a rating from 1 to 4.",
                                   reply_markup=_rating_keyboard(do, message_id, session))
        return
    rating = ("again", "hard", "good", "easy")[int(text) - 1]
    await rate(do, chat_id, message_id, session["card_id"], rating)


async def rate(do, chat_id, message_id, card_id, rating_name: str, *, revealed=False):
    session = do.get_session(message_id)
    pending = do.storage.kv.get("review:pending") or {}
    if (pending.get("message_id") != message_id
            or rating_name not in fsrs_service.RATINGS or not session
            or session["card_id"] != card_id or (not revealed and not session.get("ready"))
            or session.get("chat_id") != str(chat_id)):
        return
    card_row = do.get_card(card_id)
    if card_row is None:
        return
    card = fsrs_service.card_from_json(card_row.card_json)
    when = do._now()
    cached = session.get("choices", {}).get(rating_name)
    if cached:
        updated = fsrs_service.card_from_json(cached)
        interval = updated.due - updated.last_review
        updated.last_review = when
        updated.due = when + interval
    else:
        updated, _ = fsrs_service.review(card, rating_name, when=when)
        interval = updated.due - updated.last_review

    def persist():
        do.save_card(card_id, updated)
        do.storage.sql.exec(
            "INSERT INTO reviews(card_id,rating,reviewed_at) VALUES(?,?,?)",
            card_id, int(fsrs_service.RATINGS[rating_name]), updated.last_review.isoformat())
        do.daily_review(1)
        do.pop_session(message_id)
        pending = do.storage.kv.get("review:pending")
        if pending and pending.get("message_id") == message_id:
            do.storage.kv.delete("review:pending")

    do.storage.transactionSync(persist)
    do._reschedule()
    word = do.word_row(card_row.word_id)
    added, reviewed = do.daily_counts()
    body = texts.RATED_FEEDBACK.format(
        word=escape(word.word if word else "?"),
        rating=texts.RATE_NAMES[rating_name], interval=_interval(interval),
        done=added + reviewed, target=do.target())
    if revealed and word:
        body = _answer(word) + "\n\n" + body
    await edit_message(do.env, chat_id, message_id, body + "\n\n" + texts.MENU,
                       reply_markup=MENU_KB)
