import asyncio

import pytest

from tests.test_vocab_do import _fresh, feed_cb, feed_msg


def last_visible_call(do):
    return next(call for call in reversed(do.env.sent)
                if call["method"] in ("sendMessage", "sendRichMessage", "editMessageText"))


def callback_data(call):
    return [button.get("callback_data")
            for row in call["payload"].get("reply_markup", {}).get("inline_keyboard", [])
            for button in row]


def seed_vocabulary(do):
    do.insert_words_bulk(111, [
        {"word": "hello", "phonetic": "/hə/", "define_en": "greeting",
         "meaning": "xin chào", "example": "Hello", "note": "first"},
        {"word": "world", "phonetic": None, "define_en": "earth",
         "meaning": "thế giới", "example": None, "note": None},
    ])
    do.storage.sql.exec("INSERT INTO reviews(card_id,rating,reviewed_at) VALUES(1,3,'2025-01-01')")
    do.storage.sql.exec("INSERT INTO reviews(card_id,rating,reviewed_at) VALUES(2,2,'2025-01-02')")


def counts(do):
    return tuple(list(do.storage.sql.exec(f"SELECT COUNT(*) AS n FROM {table}"))[0].n
                 for table in ("words", "cards", "reviews"))


def open_confirmation(do):
    feed_msg(do, "/delete")
    mid = last_visible_call(do)["result"].get("message_id") or last_visible_call(do)["payload"].get("message_id", 500)
    if "del:all" not in callback_data(last_visible_call(do)):
        feed_cb(do, "menu:delete", message_id=mid)
    if "del:all" in callback_data(last_visible_call(do)):
        feed_cb(do, "del:all", message_id=mid)


def test_delete_all_requires_a_separate_confirmation(do):
    seed_vocabulary(do)
    feed_msg(do, "/delete")
    markup = callback_data(last_visible_call(do))
    if "del:all" not in markup:
        feed_cb(do, "menu:delete")
        markup = callback_data(last_visible_call(do))
    assert "del:all" in markup
    assert counts(do) == (2, 2, 2)


def test_confirmation_callback_without_prompt_does_not_delete(do):
    seed_vocabulary(do)
    feed_cb(do, "delall:confirm")
    assert counts(do) == (2, 2, 2)


def test_cancel_preserves_words_cards_reviews_and_pending_review(do):
    seed_vocabulary(do)
    session = {"card_id": 1, "word_id": 1, "chat_id": "111"}
    pending = {"card_id": 1, "chat_id": "111", "message_id": 700}
    do.put_session(700, session)
    do.storage.kv.put("review:pending", pending)
    before = counts(do)

    open_confirmation(do)
    prompt = last_visible_call(do)
    assert "permanently delete all words" in prompt["payload"]["text"].lower()
    assert {"delall:confirm", "delall:cancel"}.issubset(set(callback_data(prompt)))
    feed_cb(do, "delall:cancel")

    assert counts(do) == before == (2, 2, 2)
    assert do.storage.kv.get("review:pending") == pending
    assert do.get_session(700) == session


def test_confirm_atomically_clears_words_cards_reviews_and_pending_state(do):
    seed_vocabulary(do)
    session = {"card_id": 1, "word_id": 1, "chat_id": "111"}
    pending = {"card_id": 1, "chat_id": "111", "message_id": 700}
    do.put_session(700, session)
    do.storage.kv.put("review:pending", pending)
    do.storage.setAlarm(123456)

    open_confirmation(do)
    feed_cb(do, "delall:confirm")

    assert counts(do) == (0, 0, 0)
    assert do.storage.kv.get("review:pending") is None
    assert do.get_session(700) is None
    # Empty vocabulary screen keeps an idle-timeout alarm; no review due remains.
    fsm = do.storage.kv.get("fsm:111")
    assert fsm and fsm.get("expires_at")
    assert do.storage.alarm == int(
        __import__("datetime").datetime.fromisoformat(fsm["expires_at"]).timestamp() * 1000
    )
    assert any("Review closed" in call["payload"].get("text", "") for call in do.env.sent)


def test_delete_failure_rolls_back_tables_and_pending_review(do, monkeypatch):
    from handlers import delete

    seed_vocabulary(do)
    pending = {"card_id": 1, "chat_id": "111", "message_id": 700}
    session = {"card_id": 1, "word_id": 1, "chat_id": "111"}
    do.put_session(700, session)
    do.storage.kv.put("review:pending", pending)
    before = counts(do)
    do.set_fsm(111, {"flow": "delete_all_confirm", "action": "delete", "message_id": 500})
    original_exec = do.storage.sql.exec

    def fail_on_cards_delete(sql, *args):
        if sql.startswith("DELETE FROM cards"):
            raise RuntimeError("simulated storage failure")
        return original_exec(sql, *args)

    monkeypatch.setattr(do.storage.sql, "exec", fail_on_cards_delete)
    with pytest.raises(RuntimeError, match="simulated storage failure"):
        asyncio.run(delete.confirm_all(do, 111))

    assert counts(do) == before == (2, 2, 2)
    assert do.storage.kv.get("review:pending") == pending
    assert do.get_session(700) == session
