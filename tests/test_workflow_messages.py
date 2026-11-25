"""Add workflows retain one bot message across input and callbacks."""
import asyncio

import pytest

from tests.conftest import _install_workers_stub, make_update_cb, make_update_msg

_install_workers_stub()
from handlers import add
from services import dict_service


def run(coro):
    return asyncio.run(coro)


def state(do):
    return do.storage.kv.get("fsm:111")


def assert_one_message(do, message_id):
    sends = [call for call in do.env.sent if call["method"] == "sendMessage"]
    assert len(sends) <= 1
    assert all(call["payload"]["message_id"] == message_id
               for call in do.env.sent if call["method"] == "editMessageText")
    if state(do):
        assert state(do)["message_id"] == message_id


def assert_finished(do, message_id):
    assert_one_message(do, message_id)
    assert state(do)["flow"] == "vocab_select"
    assert "vact:edit" in str(do.env.sent[-1]["payload"]["reply_markup"])


@pytest.mark.parametrize("entry", ["command", "menu"])
def test_manual_add_reuses_message_and_preserves_six_fields(do, entry):
    line = "hello|hə|a greeting|xin chào|Hello there|note"
    if entry == "command":
        run(add.start(do, 111, line))
        mid = state(do)["message_id"]
    else:
        run(add.start(do, 111, "", message_id=500))
        mid = state(do)["message_id"]
        assert state(do)["flow"] == "add_ask_word"
        # Force format path without dictionary (bulk paste after ask-word).
        run(add.on_input(do, 111, line))
    assert_one_message(do, mid)
    run(add.on_input(do, 111, line + " revised"))
    assert_one_message(do, mid)
    run(add.on_confirm(do, 111, mid, "confirm"))
    row = do.word_row(1)
    assert (row.word, row.phonetic, row.define_en, row.meaning, row.example, row.note) == (
        "hello", "hə", "a greeting", "xin chào", "Hello there", "note revised")
    assert do.get_card(1) and do.daily_counts() == (1, 0)
    assert_finished(do, mid)


def test_consequence_preview_separates_every_attribute_in_telegram_payload(do):
    definition = "a result of a particular action or situation, often one that is bad or not convenient"
    example = "To have a serious consequence"
    phonetic = "/ˈkɑːn.sə.kwəns/"
    line = f"consequence|{phonetic}|{definition}|Hậu quả|{example}|a note"
    run(do.on_message(make_update_msg("/add " + line)["message"]))
    mid = state(do)["message_id"]
    payload = do.env.sent[-1]["payload"]
    lines = payload["text"].splitlines()
    attributes = ["consequence", phonetic, definition, "Hậu quả", example, "a note"]
    indices = [next(i for i, text in enumerate(lines) if attribute in text) for attribute in attributes]
    assert indices == sorted(set(indices))
    assert " — EN:" not in payload["text"] and " — VI:" not in payload["text"]
    assert payload["parse_mode"] == "HTML"
    assert do.count_words() == 0
    assert_one_message(do, mid)


def test_add_auto_en_reuses_message(do, monkeypatch):
    async def fake_lookup(word):
        return {"word": word, "phonetic": "/hə/", "pos": "noun",
                "definition": "a greeting", "example": "Hello there"}

    monkeypatch.setattr(dict_service, "lookup", fake_lookup)
    run(do.on_message(make_update_msg("/add hello")["message"]))
    mid = state(do)["message_id"]
    assert state(do)["flow"] == "add_confirm_en"
    assert_one_message(do, mid)
    run(do.on_callback(make_update_cb("add:en_ok", message_id=mid)["callback_query"]))
    assert state(do)["flow"] == "add_input"
    assert "hello||a greeting|||" in do.env.sent[-1]["payload"]["text"]
    assert_one_message(do, mid)
    run(do.on_message(make_update_msg("hello||a greeting|xin chào|Hello there|note")["message"]))
    assert state(do)["flow"] == "add_confirm"
    assert_one_message(do, mid)
    run(add.on_confirm(do, 111, mid, "confirm"))
    row = do.word_row(1)
    assert (row.define_en, row.meaning, row.example, row.note) == (
        "a greeting", "xin chào", "Hello there", "note")
    assert_finished(do, mid)


def test_cancel_button_finishes_same_message(do):
    run(add.start(do, 111, "hello||a greeting|xin chào"))
    mid = state(do)["message_id"]
    run(add.on_confirm(do, 111, mid, "cancel"))
    assert do.count_words() == 0
    assert_finished(do, mid)
