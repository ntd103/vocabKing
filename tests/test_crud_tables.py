"""CRUD table workflows and router integration."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.conftest import _install_workers_stub

_install_workers_stub()
from handlers import delete, edit, vocab_list


def run(coro):
    return asyncio.run(coro)


def seed(do, count=32):
    do.insert_words_bulk(111, [dict(word=f"word{i:02}", phonetic="/ipa/", define_en="definition", meaning="meaning", example="example", note="note") for i in range(count)])


def payload(do):
    return do.env.sent[-1]["payload"]


def rich_text(do):
    p = payload(do)
    return p.get("text") or p.get("rich_message", {}).get("markdown", "")


def callbacks(do):
    return [b["callback_data"] for row in payload(do)["reply_markup"]["inline_keyboard"] for b in row]


def test_md_table_escapes_pipes_newlines_and_markup():
    import re
    import telegram as tg

    table = tg.md_table(
        ["#", "Từ", "Nghĩa"],
        [["1", "a|b\nc", "<tag> *bold* $10"]],
        aligns=["right", "left", "left"],
    )
    lines = table.splitlines()
    assert lines[0] == "| # | Từ | Nghĩa |"
    assert lines[1] == "|---:|:---|:---|"
    assert lines[2].startswith("| 1 | ") and lines[2].endswith(" |")
    assert len(re.findall(r"(?<!\\)\|", lines[2])) == 4
    assert "\\|" in lines[2] and "\\<tag\\>" in lines[2] and "\\*bold\\*" in lines[2]


def test_rich_message_send_and_edit_payloads(do):
    import telegram as tg

    res = run(tg.send_rich_message(do.env, 111, "| A | B |\n|:---|:---|\n| 1 | 2 |"))
    mid = res["result"]["message_id"]
    sent = do.env.sent[-1]
    assert sent["method"] == "sendRichMessage"
    assert sent["payload"]["rich_message"] == {
        "markdown": "| A | B |\n|:---|:---|\n| 1 | 2 |",
        "skip_entity_detection": True,
    }
    run(tg.edit_message(do.env, 111, mid, markdown="**Cập nhật**"))
    edited = do.env.sent[-1]
    assert edited["method"] == "editMessageText"
    assert "text" not in edited["payload"]
    assert edited["payload"]["rich_message"] == {
        "markdown": "**Cập nhật**",
        "skip_entity_detection": True,
    }


def test_vocab_menu_has_full_crud_actions_and_renders_markdown_table(do):
    seed(do, 2)
    run(vocab_list.show_menu(do, 111, 500))
    assert {"vact:edit", "vact:delete", "vsrch", "menu:home"}.issubset(set(callbacks(do)))
    assert "menu:add" not in callbacks(do) and "vact:view" not in callbacks(do)
    md = payload(do)["rich_message"]["markdown"]
    assert "| # | Word | IPA | Meaning | Due |" in md
    assert "<pre>" not in md
    assert not any(d.startswith(("editw:", "delw:", "vword:")) for d in callbacks(do))


def test_invalid_selection_preserves_markdown_table_page_and_filter(do):
    seed(do, 35)
    run(vocab_list.show_page(do, 111, 3, 500, action="delete", query="word", table=True))
    run(vocab_list.select_word(do, 111, "999", 500))
    md = payload(do)["rich_message"]["markdown"]
    assert "No match" in md
    assert "| # | Word |" in md and "word30" in md and "Page 4/4" in md
    assert do.storage.kv.get("fsm:111")["action"] == "delete"
    assert do.storage.kv.get("fsm:111")["page"] == 3


def test_duplicate_word_selection_requires_stt_instead_of_guessing(do):
    do.insert_words_bulk(111, [
        {"word": "bank", "phonetic": None, "define_en": "river side", "meaning": "bờ sông", "example": None, "note": None},
        {"word": "bank", "phonetic": None, "define_en": "money place", "meaning": "ngân hàng", "example": None, "note": None},
    ])
    run(vocab_list.show_page(do, 111, 0, 500, action="delete", table=True))
    run(vocab_list.select_word(do, 111, "bank", 500))
    assert do.count_words() == 2
    assert do.storage.kv.get("fsm:111")["flow"] == "delete_select"
    md = payload(do)["rich_message"]["markdown"]
    assert "Multiple matches" in md and "bờ sông" in md and "ngân hàng" in md



def test_table_uses_action_picker_not_per_word_crud_buttons(do):
    seed(do, 2)
    run(vocab_list.show_page(do, 111, message_id=500))
    assert not any(data.startswith(("editw:", "delw:", "vword:")) for data in callbacks(do))
    assert {"vact:edit", "vact:delete"}.issubset(set(callbacks(do)))
    assert "vact:view" not in callbacks(do)


def test_view_selection_accepts_displayed_row_number_or_word(do):
    seed(do, 2)
    run(vocab_list.show_page(do, 111, message_id=500))
    run(vocab_list.select_word(do, 111, "2", message_id=500))
    assert "word01" in payload(do)["text"]
    run(vocab_list.show_page(do, 111, message_id=500, action="vocab"))
    run(vocab_list.select_word(do, 111, "word00", message_id=500))
    assert "word00" in payload(do)["text"]


def test_edit_and_delete_selection_accept_numbers_and_words(do):
    seed(do, 2)
    run(vocab_list.show_page(do, 111, message_id=500, action="edit"))
    run(vocab_list.select_word(do, 111, "word01", message_id=500))
    assert "Choose a field" in payload(do)["text"]
    run(vocab_list.show_page(do, 111, message_id=500, action="delete"))
    run(vocab_list.select_word(do, 111, "1", message_id=500))
    assert "Permanently delete this word" in payload(do)["text"]
    assert do.storage.kv.get("fsm:111")["word_id"] == 1


def test_invalid_selection_keeps_action_and_does_not_change_data(do):
    seed(do, 2)
    run(vocab_list.show_page(do, 111, message_id=500, action="delete"))
    run(vocab_list.select_word(do, 111, "999", message_id=500))
    assert do.word_row(1) is not None and do.word_row(2) is not None
    assert do.storage.kv.get("fsm:111")["action"] == "delete"
    assert "No match" in rich_text(do)


def test_crud_entry_points_live_in_vocab_menu(do):
    from keyboards import MENU_KB

    data = [button["callback_data"] for row in MENU_KB for button in row]
    assert "menu:vocab" in data
    assert "menu:edit" not in data and "menu:delete" not in data
    seed(do, 2)
    run(do.on_menu(111, "vocab", 500))
    assert "vact:view" not in callbacks(do)
    assert "vact:edit" in callbacks(do)
    assert "vact:delete" in callbacks(do)
    assert "| # | Word |" in rich_text(do)


def test_router_view_edit_delete_select_and_return_same_message(do):
    seed(do, 2)
    from tests.test_vocab_do import feed_cb, feed_msg, last_text

    feed_msg(do, "/menu")
    mid = do.env.sent[-1]["result"]["message_id"]
    feed_cb(do, "menu:vocab", message_id=mid)
    assert "| # | Word |" in last_text(do)
    feed_msg(do, "2")
    assert "word01" in last_text(do)
    feed_cb(do, "menu:vocab", message_id=mid)
    feed_cb(do, "vact:edit", message_id=mid)
    feed_msg(do, "1")
    assert "editf:1:word" in callbacks(do)
    feed_cb(do, "edit:cancel", message_id=mid)
    assert "Edit vocabulary" in last_text(do)
    feed_cb(do, "vact:delete", message_id=mid)
    feed_msg(do, "word01")
    assert "del:confirm:2" in callbacks(do)
    feed_cb(do, "del:cancel", message_id=mid)
    assert "Delete vocabulary" in last_text(do)
    assert sum(call["method"] in ("sendMessage", "sendRichMessage") for call in do.env.sent) == 1
    assert all(call["payload"].get("message_id") == mid for call in do.env.sent
               if call["method"] == "editMessageText")


def test_search_single_and_multiple_are_tables(do):
    seed(do)
    run(edit.search(do, 111, "word01"))
    assert "| # | Word |" in rich_text(do)
    assert do.storage.kv.get("fsm:111")["query"] == "word01"
    run(edit.search(do, 111, "word"))
    run(vocab_list.show_page(do, 111, 1, 500))
    assert "Page 2/4" in rich_text(do)
    assert do.storage.kv.get("fsm:111")["query"] == "word"


def test_edit_value_updates_workflow_message(do):
    seed(do, 1)
    run(edit.start(do, 111, "", message_id=500))
    run(edit.pick_word(do, 111, 1, message_id=500))
    run(edit.pick_field(do, 111, 1, "meaning", message_id=500))
    fsm = do.storage.kv.get("fsm:111")
    assert fsm["message_id"] == 500
    run(edit.on_value(do, 111, fsm, "<new>"))
    assert do.word_row(1).meaning == "<new>"
    assert payload(do)["message_id"] == 500
    assert "Updated" in rich_text(do)
    assert "Edit vocabulary" in rich_text(do)
    assert do.storage.kv.get("fsm:111")["action"] == "edit"


def test_delete_confirm_and_cancel_update_workflow_message(do):
    seed(do, 2)
    run(delete.start(do, 111, "", message_id=500))
    run(delete.pick_word(do, 111, 1, message_id=500))
    run(delete.cancel(do, 111, message_id=500))
    assert do.word_row(1) is not None
    assert payload(do)["message_id"] == 500
    assert "del:all" in callbacks(do)
    assert "Delete vocabulary" in rich_text(do)
    run(delete.confirm(do, 111, 2, message_id=500))
    assert do.word_row(2) is None
    assert payload(do)["message_id"] == 500
    assert "Deleted" in rich_text(do)
    assert "Delete vocabulary" in rich_text(do)
    assert do.storage.kv.get("fsm:111")["action"] == "delete"


def test_vocab_search_tables_and_details(do):
    seed(do)
    run(vocab_list.start_search(do, 111, 500))
    run(vocab_list.on_search_input(do, 111, "word"))
    assert "| # | Word |" in rich_text(do)
    assert not any(data.startswith(("vword:", "editw:", "delw:")) for data in callbacks(do))
    assert "word00" in rich_text(do)
    run(vocab_list.show_page(do, 111, 1, 500))
    run(vocab_list.select_word(do, 111, "31", message_id=500))
    assert "🇬🇧 definition" in rich_text(do)
    assert "word30" in rich_text(do)


def test_no_results_escaped_and_edit_cancel(do):
    seed(do, 1)
    run(edit.search(do, 111, "<missing>", message_id=500))
    assert "&lt;missing&gt;" in rich_text(do)
    run(edit.cancel(do, 111, message_id=500))
    assert payload(do)["message_id"] == 500
    assert "vsrch" in callbacks(do)
    assert "menu:home" in callbacks(do)


def test_empty_and_clamped_filtered_pages(do):
    run(delete.start(do, 111, ""))
    assert "No vocabulary" in rich_text(do)
    seed(do)
    run(delete.search(do, 111, "word01"))
    run(vocab_list.show_page(do, 111, 999, 500))
    assert "Page 1/1" in rich_text(do)
    assert "Delete vocabulary" in rich_text(do)
    assert "word01" in rich_text(do)
    run(vocab_list.select_word(do, 111, "2", 500))
    assert "del:confirm:2" in callbacks(do)


def test_command_message_id_is_retained_through_text_input(do):
    seed(do, 1)
    run(edit.start(do, 111))
    message_id = do.storage.kv.get("fsm:111")["message_id"]
    assert message_id is not None
    run(edit.pick_word(do, 111, 1))
    run(edit.pick_field(do, 111, 1, "note"))
    run(edit.on_value(do, 111, do.storage.kv.get("fsm:111"), "updated"))
    assert payload(do)["message_id"] == message_id
    assert sum(call["method"] in ("sendMessage", "sendRichMessage") for call in do.env.sent) == 1


def test_filter_is_retained_and_literal_wildcards_do_not_match_everything(do):
    seed(do, 40)
    run(delete.search(do, 111, "word1", message_id=500))
    run(vocab_list.show_page(do, 111, 10, 500))
    assert "Page 1/1" in rich_text(do)
    assert "word10" in rich_text(do)
    assert "word00" not in rich_text(do)
    run(delete.search(do, 111, "%", message_id=500))
    assert "No match" in rich_text(do)


def test_delete_failure_rolls_back_cards_and_word(do, monkeypatch):
    seed(do, 1)
    execute = do.storage.sql.exec

    def fail_word_delete(sql, *args):
        if sql.startswith("DELETE FROM words"):
            raise RuntimeError("simulated write failure")
        return execute(sql, *args)

    monkeypatch.setattr(do.storage.sql, "exec", fail_word_delete)
    with pytest.raises(RuntimeError, match="simulated"):
        run(delete.confirm(do, 111, 1, message_id=500))
    assert do.word_row(1) is not None
    assert list(execute("SELECT id FROM cards WHERE word_id = ?", 1))
    assert not do.env.sent


def test_blank_word_is_rejected_without_data_loss(do):
    seed(do, 1)
    run(edit.pick_field(do, 111, 1, "word", message_id=500))
    fsm = do.storage.kv.get("fsm:111")
    run(edit.on_value(do, 111, fsm, "-"))
    assert do.word_row(1).word == "word00"
    assert do.storage.kv.get("fsm:111")["flow"] == "edit_value"


@pytest.mark.parametrize("existing", [None, "", " \t\n", "manual value"])
def test_fill_missing_uses_api_without_overwriting_data_or_fsrs(do, monkeypatch, existing):
    from services import dict_service
    from tests.conftest import make_update_cb, make_update_msg

    do.insert_words_bulk(111, [dict(word="consequence", phonetic=existing,
        define_en="manual definition", meaning="Hậu quả", example=None, note="manual note")])
    before_card = vars(do.get_card(1)).copy()
    before_counts, before_alarm = do.daily_counts(), do.storage.alarm
    lookup = AsyncMock(return_value={"phonetic": "/US/", "definition": "API definition",
                                     "example": "A <serious> consequence."})
    monkeypatch.setattr(dict_service, "lookup", lookup)
    run(do.on_message(make_update_msg("/edit")["message"]))
    mid = do.storage.kv.get("fsm:111")["message_id"]
    run(do.on_message(make_update_msg("1")["message"]))
    assert "editfill:1" in callbacks(do)
    assert "Fill missing fields" in str(payload(do)["reply_markup"])
    run(do.on_callback(make_update_cb("editfill:1", message_id=mid)["callback_query"]))

    lookup.assert_awaited_once_with("consequence")
    row = do.word_row(1)
    assert (row.phonetic, row.define_en, row.meaning, row.example, row.note) == (
        existing if existing and existing.strip() else "US", "manual definition",
        "Hậu quả", "A <serious> consequence.", "manual note")
    assert vars(do.get_card(1)) == before_card
    assert do.daily_counts() == before_counts
    # Idle FSM expiry may arm an alarm; fill must not change the card due/json.
    assert do.get_card(1).due == before_card["due"]
    assert "Example" in payload(do)["text"]
    assert "A <serious> consequence." in payload(do)["text"] or "&lt;serious&gt;" in payload(do)["text"]
    assert "<serious>" not in payload(do)["text"]
    assert "Filled" in payload(do)["text"]
    assert "editfill:1" in callbacks(do)
    assert do.storage.kv.get("fsm:111")["flow"] == "edit_pick_field"
    assert sum(call["method"] in ("sendMessage", "sendRichMessage") for call in do.env.sent) == 1
    assert all(call["payload"]["message_id"] == mid for call in do.env.sent
               if call["method"] == "editMessageText")


def test_fill_complete_word_skips_api(do, monkeypatch):
    from services import dict_service
    from tests.conftest import make_update_cb

    seed(do, 1)
    lookup = AsyncMock()
    monkeypatch.setattr(dict_service, "lookup", lookup)
    run(edit.pick_word(do, 111, 1, message_id=500))
    run(do.on_callback(make_update_cb("editfill:1")["callback_query"]))
    lookup.assert_not_awaited()
    assert "No missing fields" in payload(do)["text"]


@pytest.mark.parametrize("info,expected_en,notice", [
    (None, None, "Word not found"),
    ({"definition": "API definition", "phonetic": None, "example": " \t"},
     "API definition", "Filled"),
    ({"definition": "", "phonetic": "", "example": ""}, None, "No dictionary data"),
])
def test_fill_handles_missing_or_partial_api_data(do, monkeypatch, info, expected_en, notice):
    from services import dict_service
    from tests.conftest import make_update_cb

    do.insert_words_bulk(111, [dict(word="consequence", phonetic=None, define_en=None,
                                   meaning="Hậu quả", example=None, note=None)])
    monkeypatch.setattr(dict_service, "lookup", AsyncMock(return_value=info))
    run(edit.pick_word(do, 111, 1, message_id=500))
    run(do.on_callback(make_update_cb("editfill:1")["callback_query"]))
    row = do.word_row(1)
    assert (row.phonetic, row.define_en, row.meaning, row.example, row.note) == (
        None, expected_en, "Hậu quả", None, None)
    assert notice in payload(do)["text"]
    assert "editfill:1" in callbacks(do)


@pytest.mark.parametrize("change", ["message", "word", "flow"])
def test_fill_ignores_stale_callback(do, monkeypatch, change):
    from services import dict_service
    from tests.conftest import make_update_cb

    seed(do, 2)
    lookup = AsyncMock()
    monkeypatch.setattr(dict_service, "lookup", lookup)
    run(edit.pick_word(do, 111, 1, message_id=500))
    state = do.storage.kv.get("fsm:111").copy()
    key, value = {"message": ("message_id", 501), "word": ("word_id", 2),
                  "flow": ("flow", "edit_value")}[change]
    do.set_fsm(111, {**state, key: value})
    run(do.on_callback(make_update_cb("editfill:1")["callback_query"]))
    lookup.assert_not_awaited()
    got = {k: v for k, v in do.storage.kv.get("fsm:111").items() if k != "expires_at"}
    want = {k: v for k, v in {**state, key: value}.items() if k != "expires_at"}
    assert got == want


@pytest.mark.parametrize("change", ["example", "word", "deleted", "cancelled"])
def test_fill_rechecks_word_and_workflow_after_api_wait(do, monkeypatch, change):
    from services import dict_service
    from tests.conftest import make_update_cb

    do.insert_words_bulk(111, [dict(word="consequence", phonetic=None, define_en=None,
                                   meaning="Hậu quả", example=None, note=None)])
    run(edit.pick_word(do, 111, 1, message_id=500))

    async def lookup(word):
        if change == "cancelled":
            do.set_fsm(111, {"flow": "add_input", "message_id": 600})
        elif change == "deleted":
            do.storage.sql.exec("DELETE FROM words WHERE id = ?", 1)
        else:
            field, value = ("example", "manual example") if change == "example" else ("word", "different")
            do.storage.sql.exec(f"UPDATE words SET {field} = ? WHERE id = ?", value, 1)
        return {"phonetic": "/US/", "definition": "API definition", "example": "API example"}

    monkeypatch.setattr(dict_service, "lookup", lookup)
    edits_before = len(do.env.sent)
    run(do.on_callback(make_update_cb("editfill:1")["callback_query"]))
    row = do.word_row(1)
    if change == "example":
        assert (row.example, row.define_en, row.phonetic) == ("manual example", "API definition", "US")
    elif change == "deleted":
        assert row is None
    else:
        assert (row.example, row.define_en, row.phonetic) == (None, None, None)
    if change == "cancelled":
        fsm = do.storage.kv.get("fsm:111")
        assert fsm["flow"] == "add_input" and fsm["message_id"] == 600
        assert len(do.env.sent) == edits_before + 1  # callback acknowledgement only


def test_deleting_last_item_on_page_2_clamps_to_page_1(do):
    seed(do, 31)
    run(vocab_list.show_page(do, 111, 3, 500, action="delete", table=True))
    assert "Page 4/4" in rich_text(do)
    run(vocab_list.select_word(do, 111, "31", 500))
    run(delete.confirm(do, 111, 31, message_id=500))
    text = rich_text(do)
    assert "Page 3/3" in text and "word29" in text


def test_edit_pick_word_shows_all_six_fields_with_icons_and_preserves_page(do):
    seed(do, 35)
    run(vocab_list.show_page(do, 111, 3, 500, action="edit", table=True))
    run(vocab_list.select_word(do, 111, "31", 500))
    text = rich_text(do)
    for icon in ("🔤", "🔊", "🇬🇧", "🇻🇳", "📝", "ℹ️"):
        assert icon in text
    run(edit.pick_field(do, 111, 31, "note", message_id=500))
    run(edit.on_value(do, 111, do.storage.kv.get("fsm:111"), "ghi chú mới"))
    assert "Page 4/4" in rich_text(do)


def test_detail_view_edit_and_delete_return_to_view_table(do):
    seed(do, 35)
    from tests.test_vocab_do import feed_cb, feed_msg

    feed_msg(do, "/vocab")
    mid = do.env.sent[-1]["result"]["message_id"]
    feed_cb(do, "vpg:3", message_id=mid)
    feed_msg(do, "31")
    assert {"vedit:31", "vdel:31"}.issubset(set(callbacks(do)))
    feed_cb(do, "vedit:31", message_id=mid)
    feed_cb(do, "editf:31:meaning", message_id=mid)
    feed_msg(do, "nghĩa mới")
    assert do.storage.kv.get("fsm:111")["action"] == "vocab"
    assert "Page 4/4" in rich_text(do)
    feed_msg(do, "31")
    feed_cb(do, "vdel:31", message_id=mid)
    assert "Delete permanently" in str(payload(do)["reply_markup"])
    feed_cb(do, "del:cancel", message_id=mid)
    assert do.storage.kv.get("fsm:111")["action"] == "vocab"
    assert "Page 4/4" in rich_text(do)


def test_every_keyboard_button_has_leading_icon():
    import keyboards as kbs

    boards = [
        kbs.MENU_KB, kbs.ADD_EN_KB, kbs.ADD_INPUT_KB, kbs.GAMES_MENU_KB, kbs.SETTINGS_MENU_KB,
        kbs.MODE_KB, kbs.QUIET_KB, kbs.REMINDER_KB, kbs.CONFIRM_ADD_KB,
        kbs.delete_all_confirm_kb(), kbs.kb_back_menu(),
        kbs.fmt_rate_kb(1, dict(again="1m", hard="6m", good="10m", easy="8d")),
        edit._edit_picker_kb(1),
    ]
    for board in boards:
        for row in board:
            for btn in row:
                assert not btn["text"][0].isascii(), f"Button missing icon: {btn['text']}"


def test_add_import_and_lookup_have_icons_and_cancel_buttons(do, monkeypatch):
    from handlers import add, import_export
    from services import dict_service

    run(add.start(do, 111, "", message_id=500))
    assert payload(do).get("reply_markup") is not None
    run(import_export.start_import(do, 111, 500))
    assert payload(do).get("reply_markup") is not None

    async def fake_lookup(word):
        return {"word": word, "phonetic": "/hə/", "pos": "noun",
                "definition": "a greeting", "example": "Hello"}

    monkeypatch.setattr(dict_service, "lookup", fake_lookup)
    run(add.start(do, 111, "hello", message_id=500))
    first_screen = rich_text(do)
    assert "🇬🇧" in first_screen and "a greeting" in first_screen
    run(add.on_en_choice(do, 111, 500, "ok"))
    assert "hello||a greeting|||" in rich_text(do)


def test_menu_settings_and_games_reuse_message_and_clear_fsm(do):
    from tests.test_vocab_do import feed_cb, feed_msg

    feed_msg(do, "/menu")
    mid = do.env.sent[-1]["result"]["message_id"]
    feed_cb(do, "menu:settings", message_id=mid)
    assert payload(do).get("message_id") == mid
    feed_cb(do, "set:quiet", message_id=mid)
    feed_cb(do, "quiet:custom", message_id=mid)
    assert do.storage.kv.get("fsm:111") is not None
    feed_cb(do, "menu:settings", message_id=mid)
    assert do.storage.kv.get("fsm:111") is None
    assert payload(do).get("message_id") == mid
    feed_cb(do, "menu:games", message_id=mid)
    feed_cb(do, "game:story", message_id=mid)
    assert do.storage.kv.get("fsm:111") is not None
    feed_cb(do, "menu:games", message_id=mid)
    assert do.storage.kv.get("fsm:111") is None
    assert sum(c["method"] in ("sendMessage", "sendRichMessage") for c in do.env.sent) == 1


def test_vocab_command_resets_previous_delete_mode_and_sends_fresh_message(do):
    from tests.test_vocab_do import feed_msg

    seed(do, 2)
    feed_msg(do, "/delete")
    first_mid = do.env.sent[-1]["result"]["message_id"]
    assert do.storage.kv.get("fsm:111")["action"] == "delete"

    feed_msg(do, "/vocab")
    last = do.env.sent[-1]
    assert last["method"] == "sendRichMessage"
    assert last["result"]["message_id"] != first_mid
    assert do.storage.kv.get("fsm:111")["action"] == "vocab"
    assert do.storage.kv.get("fsm:111")["table"] is True
    assert "Vocabulary" in rich_text(do)


def test_markdown_filter_backticks_and_multiline_notice_do_not_inject_blocks(do):
    do.insert_words_bulk(111, [
        {"word": "don`t_ panic", "phonetic": None, "define_en": None,
         "meaning": "đừng hoảng", "example": None, "note": None}
    ])
    run(edit.search(do, 111, "don`t_"))
    md = payload(do)["rich_message"]["markdown"]
    assert "`don\\`t\\_" not in md  # no broken backtick code span with literal backslashes

    run(edit.pick_word(do, 111, 1, message_id=500))
    run(edit.pick_field(do, 111, 1, "note", message_id=500))
    run(edit.on_value(do, 111, do.storage.kv.get("fsm:111"), "line1\n# Injected\n- bullet\n<b>tag</b>"))
    md2 = payload(do)["rich_message"]["markdown"]
    assert "\n# Injected" not in md2
    assert "\n- bullet" not in md2
    assert "\\<b\\>tag\\</b\\>" in md2  # <b> preserved as escaped literal, not stripped


def test_duplicate_word_selection_respects_active_query_and_persists_on_invalid_stt(do):
    do.insert_words_bulk(111, [
        {"word": "bank", "phonetic": None, "define_en": "river", "meaning": "bờ sông", "example": None, "note": None},
        {"word": "bank", "phonetic": None, "define_en": "money 1", "meaning": "ngân hàng TW", "example": None, "note": None},
        {"word": "bank", "phonetic": None, "define_en": "money 2", "meaning": "ngân hàng TM", "example": None, "note": None},
    ])
    run(vocab_list.show_page(do, 111, 0, 500, action="delete", query="ngân hàng", table=True))
    run(vocab_list.select_word(do, 111, "bank", 500))
    md = payload(do)["rich_message"]["markdown"]
    assert "ngân hàng TW" in md and "ngân hàng TM" in md
    assert "bờ sông" not in md

    run(vocab_list.select_word(do, 111, "999", 500))
    md_retry = payload(do)["rich_message"]["markdown"]
    assert "ngân hàng TW" in md_retry and "bờ sông" not in md_retry


def test_delete_all_button_hidden_when_vocabulary_is_empty(do):
    run(delete.start(do, 111, ""))
    assert "del:all" not in callbacks(do)


def test_single_delete_clears_pending_review_atomically_before_network_finish(do, monkeypatch):
    seed(do, 2)
    do.put_session(700, {"card_id": 1, "word_id": 1, "chat_id": "111"})
    do.storage.kv.put("review:pending", {"card_id": 1, "chat_id": "111", "message_id": 700})

    async def broken_finish(*args, **kwargs):
        raise RuntimeError("network down during finish")

    monkeypatch.setattr(vocab_list, "finish", broken_finish)
    with pytest.raises(RuntimeError, match="network down"):
        run(delete.confirm(do, 111, 1, message_id=500))

    assert do.word_row(1) is None
    assert do.storage.kv.get("review:pending") is None
    assert do.get_session(700) is None
    assert do.storage.alarm is not None


def test_add_phrase_lookup_and_callback_ack_resilience(do, monkeypatch):
    from services import dict_service
    from tests.test_vocab_do import feed_cb, feed_msg
    import telegram as tg

    seen = []

    async def fake_lookup(word):
        seen.append(word)
        return None

    monkeypatch.setattr(dict_service, "lookup", fake_lookup)
    feed_msg(do, "/add")
    mid = do.env.sent[-1]["result"]["message_id"]
    feed_msg(do, "make up")
    assert seen == ["make up"]
    assert payload(do).get("message_id") == mid

    # Callback ack network failure must not abort main dispatch
    orig_fetch = tg.fetch

    async def flaky_ack_fetch(url, method=None, headers=None, body=None):
        if "answerCallbackQuery" in url:
            raise RuntimeError("ack timeout")
        return await orig_fetch(url, method=method, headers=headers, body=body)

    monkeypatch.setattr(tg, "fetch", flaky_ack_fetch)
    feed_cb(do, "menu:home", message_id=mid)
    assert "Vocabking" in rich_text(do)

    # Unicode superscript digit rejected cleanly in settings & games
    feed_cb(do, "menu:settings", message_id=mid)
    feed_cb(do, "set:target", message_id=mid)
    feed_msg(do, "²")
    assert "positive whole number" in rich_text(do).lower()


@pytest.mark.parametrize("field", ["word", "define_en", "meaning"])
def test_required_edit_fields_cannot_be_cleared(do, field):
    seed(do, 1)
    run(edit.start(do, 111, message_id=500))
    run(vocab_list.select_word(do, 111, "1", message_id=500))
    run(edit.pick_field(do, 111, 1, field, message_id=500))
    old = getattr(do.word_row(1), field)
    run(edit.on_value(do, 111, do.storage.kv.get("fsm:111"), "-"))
    assert getattr(do.word_row(1), field) == old
    assert "Enter a nonempty value" in rich_text(do)


def test_bulk_chunks_within_sql_binding_limit_and_rolls_back_late_error(do, monkeypatch):
    sql = do.storage.sql
    original = sql.exec
    inserts = []

    def limited(query, *bindings):
        assert len(bindings) <= 100
        if query.startswith("INSERT INTO words"):
            inserts.append(query)
            if len(inserts) == 3:
                raise RuntimeError("late write failure")
        return original(query, *bindings)

    monkeypatch.setattr(sql, "exec", limited)
    entries = [{"word": str(i), "define_en": "definition", "meaning": "nghĩa"} for i in range(31)]
    with pytest.raises(RuntimeError, match="late write failure"):
        do.insert_words_bulk(111, entries)
    assert do.count_words() == 0
    assert do.get_card(1) is None
    assert do.insert_words_bulk(111, entries) == 31
    assert do.get_card(31) is not None
