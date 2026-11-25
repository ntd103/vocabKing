"""New /add flow: auto EN definition → agree/manual → pipe format → confirm."""

import asyncio

from tests.conftest import _install_workers_stub, make_update_cb, make_update_msg

_install_workers_stub()
from services import dict_service


def run(coro):
    return asyncio.run(coro)


def _msg(do, text):
    run(do.on_message(make_update_msg(text)["message"]))


def _cb(do, data, message_id=None):
    mid = message_id or (do.storage.kv.get("fsm:111") or {}).get("message_id") or 500
    run(do.on_callback(make_update_cb(data, message_id=mid)["callback_query"]))


def _text(do):
    for s in reversed(do.env.sent):
        t = s["payload"].get("text") or s["payload"].get("rich_message", {}).get("markdown", "")
        if t:
            return t
    return ""


def _fsm(do):
    return do.storage.kv.get("fsm:111")


def test_add_bare_command_asks_for_word(do):
    _msg(do, "/add")
    assert _fsm(do)["flow"] == "add_ask_word"
    assert "word" in _text(do).lower()
    assert "expires_at" not in _fsm(do)


def test_add_word_shows_en_and_accepts_1_then_format(do, monkeypatch):
    async def fake_lookup(word):
        return {"word": word, "phonetic": "/həˈloʊ/", "pos": "noun",
                "definition": "a greeting", "example": "Hello!"}

    monkeypatch.setattr(dict_service, "lookup", fake_lookup)
    _msg(do, "/add hello")
    assert _fsm(do)["flow"] == "add_confirm_en"
    body = _text(do)
    assert "a greeting" in body
    assert "hello" in body.lower()

    _msg(do, "1")
    assert _fsm(do)["flow"] == "add_input"
    tip = _text(do)
    assert "hello||a greeting|||" in tip

    _msg(do, "hello||a greeting|xin chào")
    assert _fsm(do)["flow"] == "add_confirm"
    _cb(do, "add:confirm")
    row = do.word_row(1)
    assert row.word == "hello"
    assert row.define_en == "a greeting"
    assert row.meaning == "xin chào"


def test_add_manual_button_clears_en_template(do, monkeypatch):
    async def fake_lookup(word):
        return {"word": word, "phonetic": "", "pos": "", "definition": "a greeting", "example": ""}

    monkeypatch.setattr(dict_service, "lookup", fake_lookup)
    _msg(do, "/add hello")
    _cb(do, "add:en_manual")
    assert _fsm(do)["flow"] == "add_input"
    assert "hello|||||" in _text(do)


def test_add_dict_miss_goes_straight_to_format(do, monkeypatch):
    async def missing(word):
        return None

    monkeypatch.setattr(dict_service, "lookup", missing)
    _msg(do, "/add missingword")
    assert _fsm(do)["flow"] == "add_input"
    assert "missingword|||||" in _text(do)


def test_bulk_pipe_still_skips_lookup(do, monkeypatch):
    called = []

    async def fake_lookup(word):
        called.append(word)
        return None

    monkeypatch.setattr(dict_service, "lookup", fake_lookup)
    _msg(do, "/add hello||a greeting|xin chào")
    assert called == []
    assert _fsm(do)["flow"] == "add_confirm"
    _cb(do, "add:confirm")
    assert do.word_row(1).word == "hello"


def test_bare_english_word_no_longer_starts_lookup(do, monkeypatch):
    called = []

    async def fake_lookup(word):
        called.append(word)
        return {"word": word, "definition": "x", "phonetic": "", "pos": "", "example": ""}

    monkeypatch.setattr(dict_service, "lookup", fake_lookup)
    _msg(do, "hello")
    assert called == []
    fsm = _fsm(do)
    assert fsm is None or not str(fsm.get("flow", "")).startswith(("lookup", "add_"))


def test_other_command_ignored_while_adding(do, monkeypatch):
    async def fake_lookup(word):
        return {"word": word, "definition": "a greeting", "phonetic": "", "pos": "", "example": ""}

    monkeypatch.setattr(dict_service, "lookup", fake_lookup)
    _msg(do, "/add hello")
    assert _fsm(do)["flow"] == "add_confirm_en"
    _msg(do, "/study")
    assert _fsm(do)["flow"] == "add_confirm_en"


def test_menu_add_asks_word_not_submenu(do):
    _cb(do, "menu:add", message_id=500)
    assert _fsm(do)["flow"] == "add_ask_word"
