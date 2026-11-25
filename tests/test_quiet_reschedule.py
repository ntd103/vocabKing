import asyncio

from tests.conftest import make_update_cb, make_update_msg


def run(coro):
    return asyncio.run(coro)


def test_quiet_preset_reschedules_existing_alarm(do, monkeypatch):
    calls = []
    monkeypatch.setattr(do, "_reschedule", lambda: calls.append(True))
    run(do.on_callback(make_update_cb("quiet:22:6")["callback_query"]))

    assert do.setting("quiet_start") == "22"
    assert do.setting("quiet_end") == "6"
    assert True in calls


def test_quiet_off_reschedules_existing_alarm(do, monkeypatch):
    calls = []
    monkeypatch.setattr(do, "_reschedule", lambda: calls.append(True))
    run(do.on_callback(make_update_cb("quiet:off")["callback_query"]))

    assert do.setting("quiet_start") == do.setting("quiet_end") == "1"
    assert True in calls


def test_custom_quiet_input_completion_reschedules_existing_alarm(do, monkeypatch):
    calls = []
    monkeypatch.setattr(do, "_reschedule", lambda: calls.append(True))
    run(do.on_message(make_update_msg("/settings")["message"]))
    message_id = do.env.sent[-1]["result"]["message_id"]
    run(do.on_callback(make_update_cb("quiet:custom", message_id=message_id)["callback_query"]))
    run(do.on_message(make_update_msg("21")["message"]))
    run(do.on_message(make_update_msg("5")["message"]))

    assert do.setting("quiet_start") == "21"
    assert do.setting("quiet_end") == "5"
    assert True in calls
