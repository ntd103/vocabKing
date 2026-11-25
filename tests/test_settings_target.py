import asyncio

from tests.conftest import make_update_cb, make_update_msg


def run(coro):
    return asyncio.run(coro)


def test_daily_target_updates_settings_message_without_extra_send(do):
    run(do.on_message(make_update_msg("/settings")["message"]))
    message_id = do.env.sent[-1]["result"]["message_id"]
    run(do.on_callback(make_update_cb("set:target", message_id=message_id)["callback_query"]))

    msg = dict(make_update_msg("250")["message"], message_id=731)
    run(do.on_message(msg))
    assert any(call["method"] == "deleteMessage" and call["payload"]["message_id"] == 731 for call in do.env.sent)

    assert do.setting("daily_target") == "250"
    assert do.storage.kv.get("fsm:111") is None
    assert [call["method"] for call in do.env.sent].count("sendMessage") == 1
    assert do.env.sent[-1]["method"] == "editMessageText"
    assert do.env.sent[-1]["payload"]["message_id"] == message_id
    assert "Vocabking" in do.env.sent[-1]["payload"]["text"]
