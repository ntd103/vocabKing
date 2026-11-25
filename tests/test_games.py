import asyncio
from tests.test_vocab_do import _fresh, feed_cb, feed_msg


def test_story_word_list_renders_rich_markdown_table_and_reuses_message():
    do = _fresh()
    do.insert_words_bulk(111, [
        {"word": f"<漢字😀{i}>", "phonetic": None, "define_en": None,
         "meaning": "fruit | food & *fresh*", "example": None, "note": None}
        for i in range(20)
    ])

    feed_msg(do, "/menu")
    mid = do.env.sent[-1]["result"]["message_id"]
    feed_cb(do, "menu:games", message_id=mid)
    feed_cb(do, "game:story", message_id=mid)
    feed_msg(do, "abc")  # invalid -> edits in place, no extra sendMessage
    assert "whole number" in (do.env.sent[-1]["payload"].get("text") or "").lower()
    assert do.env.sent[-1]["payload"]["message_id"] == mid

    feed_msg(do, "20")
    last = do.env.sent[-1]
    assert last["method"] == "editMessageText"
    assert last["payload"]["message_id"] == mid
    md = last["payload"]["rich_message"]["markdown"]
    assert "| # | Word | Meaning |" in md
    assert "<pre>" not in md
    assert "\\<漢字😀" in md and "fruit \\| food" in md
    assert len(md.encode("utf-8")) <= 32768
    assert sum(c["method"] in ("sendMessage", "sendRichMessage") for c in do.env.sent) == 1


def test_story_word_list_caps_long_cells_within_rich_message_limit():
    from handlers import games

    do = _fresh()
    do.insert_words_bulk(111, [
        {"word": "w" * 10000, "phonetic": None, "define_en": None,
         "meaning": "m" * 10000, "example": None, "note": None}
    ])
    asyncio.run(games.story_on_count(do, 111, "1"))
    md = do.env.sent[-1]["payload"]["rich_message"]["markdown"]
    assert "| # | Word | Meaning |" in md
    assert len(md.encode("utf-8")) <= 32768


def test_story_rejects_unicode_superscript_digit():
    from handlers import games

    do = _fresh()
    do.set_fsm(111, {"flow": "game_story_count", "message_id": 500})
    asyncio.run(games.story_on_count(do, 111, "²"))
    assert "whole number" in do.env.sent[-1]["payload"]["text"].lower()

