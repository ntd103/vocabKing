import asyncio
import json
import re

import pytest


from tests.conftest import make_update_cb, make_update_msg, sent_texts


def run(coro):
    return asyncio.run(coro)


def test_import_rejects_malformed_jsonl_without_writes(do):
    run(do.on_message(make_update_msg("/import")["message"]))
    run(do.on_message(make_update_msg('{"word":"hello"}\nnot-json')["message"]))
    assert do.count_words() == 0
    assert any("invalid" in text.lower() or "không hợp lệ" in text.lower()
               for text in sent_texts(do.env))


def test_import_rejects_oversize_message_without_writes(do):
    run(do.on_message(make_update_msg("/import")["message"]))
    run(do.on_message(make_update_msg("{" + " " * 4096 + "}")["message"]))
    assert do.count_words() == 0
    assert any("4096" in text for text in sent_texts(do.env))


def test_import_requires_confirmation_and_cancel_discards_valid_records(do):
    run(do.on_message(make_update_msg("/import")["message"]))
    line = json.dumps({"word": "hello", "define_en": "greeting", "meaning": "xin chào"})
    run(do.on_message(make_update_msg(line)["message"]))
    assert do.count_words() == 0
    pending = do.storage.kv.get("fsm:111")
    assert pending["flow"] == "import_confirm"
    run(do.on_callback(make_update_cb("io:cancel", message_id=pending["message_id"])["callback_query"]))
    assert do.count_words() == 0
    assert do.storage.kv.get("fsm:111")["flow"] == "vocab_select"


def test_import_writes_only_after_confirmation(do):
    run(do.on_message(make_update_msg("/import")["message"]))
    line = json.dumps({"word": "hello", "define_en": "greeting", "meaning": "xin chào"})
    run(do.on_message(make_update_msg(line)["message"]))
    assert do.count_words() == 0
    pending = do.storage.kv.get("fsm:111")
    run(do.on_callback(make_update_cb("io:confirm", message_id=pending["message_id"])["callback_query"]))
    assert do.count_words() == 1
    assert do.word_row(1).meaning == "xin chào"
    assert do.get_card(1) is not None


def test_import_export_ignored_outside_owner_private_chat(do):
    group = make_update_msg("/export", chat_id=-100, user_id=111)["message"]
    group["chat"]["type"] = "group"
    run(do.handle_update({"message": group}))
    assert do.env.sent == []

    other_private = make_update_msg("/export", chat_id=222, user_id=111)["message"]
    other_private["chat"]["type"] = "private"
    run(do.handle_update({"message": other_private}))
    assert do.env.sent == []

    non_owner = make_update_msg("/export", chat_id=111, user_id=222)["message"]
    non_owner["chat"]["type"] = "private"
    run(do.handle_update({"message": non_owner}))
    assert do.env.sent == []

    private_owner = make_update_msg("/import", chat_id=111, user_id=111)["message"]
    private_owner["chat"]["type"] = "private"
    run(do.handle_update({"message": private_owner}))
    assert do.storage.kv.get("fsm:111")["flow"] == "import_input"


@pytest.mark.parametrize("fmt", ["csv", "json"])
def test_dated_document_roundtrip(do, monkeypatch, fmt):
    from handlers import import_export as io
    word = dict(word="hello", define_en="a greeting", meaning="xin chào", pos="noun",
                phonetic="hə", example='Hello, "world"', note="line 1\n" + "x" * 5000)
    do.insert_words_bulk(111, [word])
    captured = {}

    async def upload(env, chat, name, content, mime):
        captured["args"] = (name, content, mime)
        # Exercise real multipart builder + fetch path used in production.
        return await __import__("telegram", fromlist=["send_document"]).send_document(
            env, chat, name, content, mime,
        )

    monkeypatch.setattr(io, "send_document", upload)
    run(do.on_message(make_update_msg("/export " + fmt)["message"]))
    name, content, mime = captured["args"]
    assert re.fullmatch(r"export_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\." + fmt, name)
    assert mime == ("application/json" if fmt == "json" else "text/csv")
    assert io.parse_records(content) == [word]
    doc_calls = [c for c in do.env.sent if c["method"] == "sendDocument"]
    assert len(doc_calls) == 1
    assert doc_calls[0]["payload"]["document"] == name
    assert doc_calls[0]["payload"]["chat_id"] == "111"
    assert "multipart/form-data; boundary=" in (doc_calls[0]["payload"]["content_type"] or "")
    assert not any(call["method"] == "sendMessage" for call in do.env.sent)

    async def download(env, doc, limit):
        assert doc["file_id"] == "sample"
        return content

    monkeypatch.setattr(io, "read_document", download)
    run(do.on_message(make_update_msg("/import")["message"]))
    prompt = do.storage.kv.get("fsm:111")["message_id"]
    message = make_update_msg("")["message"]
    message.update(document={"file_id": "sample", "file_name": name})
    run(do.on_message(message))
    assert do.storage.kv.get("fsm:111")["flow"] == "import_input"
    message["reply_to_message"] = {"message_id": prompt}
    run(do.on_message(message))
    assert do.storage.kv.get("fsm:111")["entries"] == [word]
    assert do.count_words() == 1
    run(do.on_callback(make_update_cb("io:confirm", message_id=prompt)["callback_query"]))
    assert do.count_words() == 2
    assert do.word_row(2).pos == "noun"


@pytest.mark.parametrize("source", ['{"word":"hello"}', 'word,define_en,meaning\nhi,,xin chào',
                                    'x' * (512 * 1024 + 1)])
def test_reject_incomplete_or_oversize(do, source):
    from handlers import import_export as io
    with pytest.raises(ValueError):
        io.parse_records(source)


def test_legacy_jsonl_accepted(do):
    from handlers import import_export as io
    line = json.dumps(dict(word="hello", define_en="greeting", meaning="xin chào"))
    assert len(io.parse_records(line + "\n" + line)) == 2


def test_multipart_document_embeds_utf8_payload():
    from telegram import _multipart_document

    body, ctype = _multipart_document(6608549738, "export_x.json", '{"a":"à"}'.encode(), "application/json")
    assert ctype.startswith("multipart/form-data; boundary=")
    assert b'name="chat_id"' in body and b"6608549738" in body
    assert b'filename="export_x.json"' in body
    assert b'{"a":"\xc3\xa0"}' in body
    assert body.endswith(b"--\r\n") or body.rstrip().endswith(b"--")
