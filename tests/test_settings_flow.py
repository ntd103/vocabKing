import asyncio

from tests.conftest import make_update_cb, make_update_msg


def run(coro):
    return asyncio.run(coro)


def test_valid_target_updates_existing_settings_menu(do):
    run(do.on_message(make_update_msg("/settings")["message"]))
    menu_id = do.env.sent[-1]["result"]["message_id"]
    run(do.on_callback(make_update_cb("set:target", message_id=menu_id)["callback_query"]))

    msg = dict(make_update_msg("250")["message"], message_id=731)
    run(do.on_message(msg))
    assert any(call["method"] == "deleteMessage" and call["payload"]["message_id"] == 731 for call in do.env.sent)

    assert do.setting("daily_target") == "250"
    assert do.storage.kv.get("fsm:111") is None
    assert [call["method"] for call in do.env.sent].count("sendMessage") == 1
    edit = do.env.sent[-1]
    assert edit["method"] == "editMessageText"
    assert edit["payload"]["message_id"] == menu_id
    assert "Vocabking" in edit["payload"]["text"]
