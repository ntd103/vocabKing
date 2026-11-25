"""Gaps from TODO.md: Hard-on-add, idle close, FSM-safe reminders, vocab UX."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fsrs import Card

from services.fsrs_service import card_from_json, new_card_json, review
from tests.conftest import _install_workers_stub

_install_workers_stub()


def _fresh():
    from tests.test_vocab_do import _fresh as make

    return make()


def test_new_card_is_graded_hard_not_delay_only():
    when = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    card = card_from_json(new_card_json(when))
    expected, _ = review(Card(), "hard", when=when)
    assert card.state == expected.state
    assert card.difficulty == expected.difficulty
    assert card.due == expected.due
    assert card.last_review == when


def test_vocab_opens_paginated_table_without_add_or_view(do):
    from handlers import vocab_list

    do.insert_words_bulk(111, [
        {"word": f"w{i:02}", "phonetic": None, "define_en": "d", "meaning": "m",
         "example": None, "note": None}
        for i in range(25)
    ])
    asyncio.run(vocab_list.show_menu(do, 111, 500))
    payload = do.env.sent[-1]["payload"]
    md = payload.get("text") or payload.get("rich_message", {}).get("markdown", "")
    callbacks = [
        b["callback_data"]
        for row in payload["reply_markup"]["inline_keyboard"]
        for b in row
    ]
    assert vocab_list.PAGE_SIZE == 10
    assert "Page 1/3" in md
    assert "w00" in md and "w09" in md and "w10" not in md
    assert "menu:add" not in callbacks and "vact:view" not in callbacks
    assert "vact:edit" in callbacks and "vact:delete" in callbacks
    assert "vpg:1" in callbacks


def test_alarm_skips_quiz_while_fsm_active(monkeypatch):
    import src.vocab_do as vocab_do

    day = datetime(2026, 9, 17, 4, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(vocab_do, "now_utc", lambda: day)
    do = _fresh()
    do.insert_words_bulk(111, [
        {"word": "alpha", "phonetic": None, "define_en": "a", "meaning": "á",
         "example": None, "note": None},
    ])
    do.storage.sql.exec("UPDATE cards SET due = ?", day.isoformat())
    do.set_fsm(111, {
        "flow": "add_input", "message_id": 500,
        "expires_at": (day + timedelta(seconds=30)).isoformat(),
    })
    do.env.sent.clear()
    asyncio.run(do._alarm_tick())
    assert do.env.sent == []


def test_idle_fsm_expires_and_clears_without_touching_pending_review(monkeypatch):
    import src.vocab_do as vocab_do
    from handlers import review

    day = datetime(2026, 9, 17, 4, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(vocab_do, "now_utc", lambda: day)
    do = _fresh()
    do.insert_words_bulk(111, [
        {"word": "beta", "phonetic": None, "define_en": "b", "meaning": "bê",
         "example": None, "note": None},
    ])
    do.storage.sql.exec("UPDATE cards SET due = ?", (day - timedelta(minutes=1)).isoformat())
    # Seed expired FSM via KV — set_fsm() would refresh the idle window.
    do.storage.kv.put("fsm:111", {
        "flow": "add_input", "message_id": 500,
        "expires_at": (day - timedelta(seconds=1)).isoformat(),
    })
    do.storage.kv.put("review:pending", {
        "card_id": 1, "chat_id": "111", "message_id": 900,
    })
    do.env.sent.clear()
    asyncio.run(do._alarm_tick())
    assert do.storage.kv.get("fsm:111") is None
    assert do.storage.kv.get("review:pending")["message_id"] == 900
    assert any("Timed out" in (
        s["payload"].get("text") or s["payload"].get("rich_message", {}).get("markdown", "")
    ) for s in do.env.sent)
    # Pending review still blocks a new quiz prompt.
    assert not any(
        s["method"] == "sendMessage"
        and "Fill" in (s["payload"].get("text") or "")
        for s in do.env.sent
    )


def test_set_fsm_stamps_idle_expiry_and_reschedules_alarm(monkeypatch):
    import src.vocab_do as vocab_do

    day = datetime(2026, 9, 17, 4, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(vocab_do, "now_utc", lambda: day)
    do = _fresh()
    do.set_fsm(111, {"flow": "edit_search", "message_id": 500})
    state = do.storage.kv.get("fsm:111")
    assert state["expires_at"] == (day + timedelta(seconds=15)).isoformat()
    assert do.storage.getAlarm() == int((day + timedelta(seconds=15)).timestamp() * 1000)
