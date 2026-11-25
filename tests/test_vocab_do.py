"""End-to-end integration tests of the DO router with faked Workers runtime.

Covers: whitelist, /menu, add flow (input → preview → confirm), /study +
definition prompt + show-answer + rating (FSRS due updates), cloze reply flow
with ? / ???, edit flow, delete flow, alarm scheduling.
"""

import asyncio
import datetime as dt

from tests.conftest import (
    FakeEnv,
    _Req,
    last_message_id,
    make_update_cb,
    make_update_msg,
    sent_texts,
)


def feed(do, update):
    """Synchronously run handle_update (handle_update awaits async parts)."""
    asyncio.run(do.handle_update(update))


def feed_msg(do, text, **kw):
    feed(do, make_update_msg(text, **kw))


def feed_cb(do, data, **kw):
    feed(do, make_update_cb(data, **kw))


def send_count(do):
    return len(do.env.sent)


def last_text(do):
    return sent_texts(do.env)[-1]


class TestWhitelist:
    def test_stranger_message_ignored(self):
        do = _fresh()
        feed_msg(do, "/menu", user_id=999)
        assert send_count(do) == 0

    def test_stranger_callback_ignored(self):
        do = _fresh()
        feed_cb(do, "menu:study", user_id=999)
        assert send_count(do) == 0

    def test_owner_menu_works(self):
        do = _fresh()
        feed_msg(do, "/menu")
        assert send_count(do) == 1
        assert "Vocabking" in last_text(do)


def _fresh():
    """Rebuild a DO per test (isolation between tests)."""
    from tests.conftest import _Ctx, _install_workers_stub, _patch_telegram_fetch

    _install_workers_stub()
    from src.vocab_do import VocabularyDO

    env = FakeEnv()
    _patch_telegram_fetch(env)
    return VocabularyDO(_Ctx(), env)


class TestAddFlow:
    def test_add_single_with_confirm(self):
        do = _fresh()
        feed_msg(do, "/add hello|/həˈloʊ/|a greeting|xin chào|Hi Paul|note")
        assert "Preview (1)" in last_text(do)  # preview
        assert do.storage.data.get("fsm:111", {}).get("flow") == "add_confirm"
        feed_cb(do, "add:confirm")
        assert "Added: 1" in last_text(do)
        rows = list(do.storage.sql.exec("SELECT word, phonetic, meaning FROM words"))
        assert rows[0].word == "hello"

    def test_add_bulk_wrapped(self):
        do = _fresh()
        feed_msg(do, "/add a1||def|m1\na2||def|m2\na3||def|m3")
        assert "Preview (3)" in last_text(do)
        feed_cb(do, "add:confirm")
        words = [r.word for r in do.storage.sql.exec("SELECT word FROM words")]
        assert words == ["a1", "a2", "a3"]

    def test_add_cancel(self):
        do = _fresh()
        feed_msg(do, "/add x||def|y")
        feed_cb(do, "add:cancel")
        assert "no words added" in last_text(do).lower()
        assert list(do.storage.sql.exec("SELECT 1 FROM words")) == []

    def test_add_via_fsm_input(self):
        do = _fresh()
        feed_msg(do, "/add")
        assert do.storage.kv.get("fsm:111")["flow"] == "add_ask_word"
        feed_msg(do, "solo|/soʊ/|alone|một mình")
        feed_cb(do, "add:confirm")
        assert do.word_row(1).word == "solo"

    def test_add_creates_card_due_after_learning_step(self):
        do = _fresh()
        feed_msg(do, "/add word||definition|nghĩa")
        feed_cb(do, "add:confirm")
        card = do.get_card(1)
        due = dt.datetime.fromisoformat(card.due)
        # New cards are seeded with an initial Hard grade (~5.5m on default FSRS).
        assert dt.timedelta(minutes=5) < due - do._now() <= dt.timedelta(minutes=6)


def make_cards_due(do):
    from services import fsrs_service
    for row in list(do.storage.sql.exec("SELECT id, card_json FROM cards")):
        card = fsrs_service.card_from_json(row.card_json)
        card.due = do._now() - dt.timedelta(seconds=1)
        do.save_card(row.id, card)


class TestDefinitionReviewFlow:
    def _add_and_prompt(self, do):
        feed_msg(do, "/add hello|/həˈloʊ/|a greeting|xin chào|Hi Paul|friendly")
        feed_cb(do, "add:confirm")
        do.put_setting("mode", "definition")
        do.env.sent.clear()
        make_cards_due(do)
        feed_msg(do, "/study")
        # find the prompt message (definition prompt asks "Type the missing word?")
        prompts = [s for s in do.env.sent if "Type the missing word" in s["payload"].get("text", "")]
        assert prompts, f"no prompt in {sent_texts(do.env)}"
        prompt_id = prompts[0]["result"]["message_id"]
        return prompt_id

    def test_study_sends_prompt(self):
        do = _fresh()
        self._add_and_prompt(do)
        # quiz asks for the English vocabulary word
        assert "Type the missing word" in last_text(do)

    def test_show_answer_then_rate(self):
        do = _fresh()
        prompt_id = self._add_and_prompt(do)
        card_id = 1
        do.env.sent.clear()
        # user replies to the prompt; bot reveals the answer with rate buttons
        feed_msg(do, "không biết", reply_to=prompt_id)
        assert "Incorrect." in last_text(do) and "xin chào" in last_text(do)
        # rate good
        old_due = dt.datetime.fromisoformat(do.get_card(card_id).due)
        feed_cb(do, f"rate:{card_id}:good", message_id=prompt_id)
        assert "Good" in last_text(do)
        new_due = dt.datetime.fromisoformat(do.get_card(card_id).due)
        assert new_due > old_due
        # review logged
        assert list(do.storage.sql.exec("SELECT rating FROM reviews"))

    def test_rating_updates_fsm_alarm(self):
        do = _fresh()
        mid = self._add_and_prompt(do)
        feed_msg(do, "hello", reply_to=mid)
        feed_cb(do, "rate:1:good", message_id=mid)
        # alarm rescheduled to future due
        assert do.storage.alarm is not None


class TestClozeFlow:
    def _add_example_and_prompt(self, do):
        feed_msg(do, "/add apple|/ˈæp.əl/|a fruit|quả táo|An apple a day keeps the doctor away")
        feed_cb(do, "add:confirm")
        do.put_setting("mode", "cloze")
        do.env.sent.clear()
        make_cards_due(do)
        feed_msg(do, "/study")
        prompts = [s for s in do.env.sent if "Type the missing word" in s["payload"].get("text", "")]
        assert prompts, sent_texts(do.env)
        return prompts[0]["result"]["message_id"]

    def test_cloze_prompt_masks(self):
        do = _fresh()
        mid = self._add_example_and_prompt(do)
        text = last_text(do)
        assert "An a _ _ _ _ a day keeps the doctor away" in text
        assert "quả táo" in text and "apple" not in text

    def test_cloze_hint_question_reveals(self):
        do = _fresh()
        mid = self._add_example_and_prompt(do)
        n_before = last_text(do).count("_")
        feed_msg(do, "?", reply_to=mid)
        text = last_text(do)
        n_mid = text.count("_")
        # more letters revealed than before but not everything
        assert n_mid < n_before and n_mid > 0
        feed_msg(do, "???", reply_to=mid)
        full = last_text(do)
        assert "An apple a day keeps the doctor away" in full
        assert "apple" in full  # word + rate buttons shown

    def test_cloze_answer_correct_and_rate(self):
        do = _fresh()
        mid = self._add_example_and_prompt(do)
        feed_msg(do, "apple", reply_to=mid)
        assert "Correct!" in last_text(do)
        feed_cb(do, "rate:1:good", message_id=mid)
        assert "Good" in last_text(do)

    def test_cloze_answer_wrong(self):
        do = _fresh()
        mid = self._add_example_and_prompt(do)
        feed_msg(do, "something else entirely", reply_to=mid)
        assert "Incorrect." in last_text(do)


class TestEditDeleteFlow:
    def test_edit_flow(self):
        do = _fresh()
        feed_msg(do, "/add hello||greeting|xin chào")
        feed_cb(do, "add:confirm")
        do.env.sent.clear()
        feed_msg(do, "/edit hel")
        # even a single result is a Markdown table before typed row selection
        assert "| # | Word |" in last_text(do) and "hello" in last_text(do)
        feed_msg(do, "hello")
        assert "hello" in last_text(do)
        feed_cb(do, "editf:1:meaning")
        assert "hello" in last_text(do)
        feed_msg(do, "xin chào đã sửa")
        assert "Updated" in last_text(do)
        assert do.word_row(1).meaning == "xin chào đã sửa"

    def test_delete_flow(self):
        do = _fresh()
        feed_msg(do, "/add goodbye||farewell|tạm biệt")
        feed_cb(do, "add:confirm")
        do.env.sent.clear()
        feed_msg(do, "/delete good")
        feed_msg(do, "1")
        assert "goodbye" in last_text(do)
        feed_cb(do, "del:confirm:1")
        assert "Deleted" in last_text(do)
        assert do.word_row(1) is None
        assert do.get_card(1) is None


class TestQuietHours:
    def test_is_quiet_default_window(self):
        do = _fresh()
        utc7pm = dt.datetime(2026, 9, 17, 16, 0, tzinfo=dt.timezone.utc)  # 23:00 UTC+7
        utc6am = dt.datetime(2026, 9, 17, 23, 0, tzinfo=dt.timezone.utc)  # 06:00 UTC+7
        noon = dt.datetime(2026, 9, 17, 5, 0, tzinfo=dt.timezone.utc)  # 12:00 UTC+7
        assert do.is_quiet(utc7pm)
        assert do.is_quiet(utc6am)
        assert not do.is_quiet(noon)

    def test_quiet_off(self):
        do = _fresh()
        do.put_setting("quiet_start", "1")
        do.put_setting("quiet_end", "1")
        assert not do.is_quiet(dt.datetime.now(dt.timezone.utc))

    def test_wake_time_delays_to_morning(self):
        do = _fresh()
        night = dt.datetime(2026, 9, 17, 18, 0, tzinfo=dt.timezone.utc)  # 01:00 VN
        wake = do.wake_time(night)
        assert do.local_hour(wake) == 7  # quiet end (local)
        assert wake > night

    def test_alarm_silent_during_quiet_hours(self, monkeypatch):
        import src.vocab_do as vd

        # pin the clock inside the quiet window (01:00 VN) BEFORE adding so the
        # card's due lands on the pinned clock too (no real-clock reads)
        monkeypatch.setattr(
            vd, "now_utc",
            lambda: dt.datetime(2026, 9, 17, 18, 0, tzinfo=dt.timezone.utc),
        )
        do = _fresh()
        feed_msg(do, "/add w1")
        feed_cb(do, "add:confirm")
        do.env.sent.clear()
        asyncio.run(do._alarm_tick())
        assert send_count(do) == 0  # nothing sent during quiet hours


class TestSettings:
    def test_set_mode_and_quiet(self):
        do = _fresh()
        feed_msg(do, "/settings")
        feed_cb(do, "mode:cloze")
        assert do.setting("mode") == "cloze"
        feed_cb(do, "quiet:0:6")
        assert do.setting("quiet_start") == "0"
        assert do.setting("quiet_end") == "6"
        feed_cb(do, "quiet:off")
        assert do.setting("quiet_start") == "1"

    def test_custom_quiet_hours_input_updates_existing_message(self):
        do = _fresh()
        feed_msg(do, "/settings")
        menu_id = do.env.sent[0]["result"]["message_id"]
        feed_cb(do, "set:quiet", message_id=menu_id)
        feed_cb(do, "quiet:custom", message_id=menu_id)
        message_sends = sum(s["method"] == "sendMessage" for s in do.env.sent)
        assert do.storage.data["fsm:111"]["flow"] == "set_quiet_start"
        assert do.env.sent[-1]["payload"]["message_id"] == menu_id

        feed_msg(do, "nonsense")
        assert do.setting("quiet_start") == "23"
        assert do.setting("quiet_end") == "7"
        assert do.storage.data["fsm:111"]["flow"] == "set_quiet_start"
        assert sum(s["method"] == "sendMessage" for s in do.env.sent) == message_sends
        edits = [s for s in do.env.sent if s["method"] == "editMessageText"]
        assert "start hour" in edits[-1]["payload"]["text"]

        feed_msg(do, "24")
        assert do.setting("quiet_start") == "23"
        assert do.storage.data["fsm:111"]["flow"] == "set_quiet_start"
        assert "0 to 23" in do.env.sent[-1]["payload"]["text"]

        feed_msg(do, "22")
        assert do.storage.data["fsm:111"]["flow"] == "set_quiet_end"
        assert do.storage.data["fsm:111"]["quiet_start"] == 22

        feed_msg(do, "23:00")
        assert do.setting("quiet_start") == "23"
        assert do.setting("quiet_end") == "7"
        assert do.storage.data["fsm:111"]["flow"] == "set_quiet_end"
        assert sum(s["method"] == "sendMessage" for s in do.env.sent) == message_sends

        feed_msg(do, "6")
        assert do.setting("quiet_start") == "22"
        assert do.setting("quiet_end") == "6"
        assert "fsm:111" not in do.storage.data
        assert sum(s["method"] == "sendMessage" for s in do.env.sent) == message_sends
        edits = [s for s in do.env.sent if s["method"] == "editMessageText"]
        assert edits[-1]["payload"]["message_id"] == menu_id
        assert "22:00 – 06:00" in edits[-1]["payload"]["text"]

    def test_custom_quiet_hours_accepts_zero_and_23(self):
        do = _fresh()
        feed_msg(do, "/settings")
        menu_id = do.env.sent[0]["result"]["message_id"]
        feed_cb(do, "set:quiet", message_id=menu_id)
        feed_cb(do, "quiet:custom", message_id=menu_id)
        feed_msg(do, "0")
        feed_msg(do, "23")
        assert do.setting("quiet_start") == "0"
        assert do.setting("quiet_end") == "23"


class TestUnknownInput:
    def test_random_text_gets_hint(self):
        do = _fresh()
        feed_msg(do, "hello there")
        assert "chưa hiểu" in last_text(do).lower() or "menu" in last_text(do).lower()

    def test_cancel_returns_to_vocabulary_menu(self):
        do = _fresh()
        feed_msg(do, "/add")
        feed_msg(do, "/cancel")
        assert do.storage.kv.get("fsm:111")["flow"] == "vocab_select"
        assert "vact:edit" in str(do.env.sent[-1]["payload"])


class TestAlarmFlow:
    def test_alarm_sends_prompt_when_due(self):
        do = _fresh()
        feed_msg(do, "/add word||definition|m1")
        feed_cb(do, "add:confirm")
        do.put_setting("quiet_start", "1")
        do.put_setting("quiet_end", "1")  # quiet off (1..1)
        make_cards_due(do)
        do.set_fsm(111, None)
        do.env.sent.clear()
        asyncio.run(do.alarm())
        texts = sent_texts(do.env)
        assert any("Type the missing word" in t for t in texts)
        assert "w o r d" not in texts[-1]  # answer is hidden

    def test_alarm_reschedules_for_future_due(self):
        do = _fresh()
        feed_msg(do, "/add word||definition|m1")
        feed_cb(do, "add:confirm")
        do.set_fsm(111, None)
        from src.services import fsrs_service

        card = fsrs_service.card_from_json(do.get_card(1).card_json)
        updated, _ = fsrs_service.review(card, "good")
        do.save_card(1, updated)
        do._reschedule()
        now_ms = dt.datetime.now(dt.timezone.utc).timestamp() * 1000
        assert do.storage.kv.alarm > now_ms  # next reminder in the future

    def test_alarm_tick_quiet_sends_nothing(self, monkeypatch):
        import src.vocab_do as vocab_do

        # pin the clock inside the default quiet window (23:00-07:00 local = UTC+7);
        # patch BEFORE adding so the card's due lands on the pinned clock too
        quiet_time = dt.datetime(2026, 9, 17, 21, 0, tzinfo=dt.timezone.utc)  # 04:00+7
        monkeypatch.setattr(vocab_do, "now_utc", lambda: quiet_time)
        do = _fresh()
        feed_msg(do, "/add word||definition|m1")
        feed_cb(do, "add:confirm")
        make_cards_due(do)
        do.set_fsm(111, None)  # home — reminders only fire outside an open dialog
        do.env.sent.clear()
        asyncio.run(do._alarm_tick())
        assert send_count(do) == 0

    def test_alarm_tick_daytime_sends_prompt(self, monkeypatch):
        import src.vocab_do as vocab_do

        # pin the clock outside quiet hours so the check is time-independent
        day_time = dt.datetime(2026, 9, 17, 4, 0, tzinfo=dt.timezone.utc)  # 11:00+7
        monkeypatch.setattr(vocab_do, "now_utc", lambda: day_time)
        do = _fresh()
        feed_msg(do, "/add word||definition|m1")
        feed_cb(do, "add:confirm")
        make_cards_due(do)
        do.set_fsm(111, None)
        do.env.sent.clear()
        asyncio.run(do._alarm_tick())
        assert send_count(do) == 1


class TestVocabList:
    def _seed(self, do, n=35):
        import asyncio

        for i in range(n):
            feed_msg(do, f"/add word{i}|/w{i}/|definition|nghĩa {i}")
            feed_cb(do, "add:confirm")
        # /add wordN now routes to lookup (API fails in tests) -> insert directly
        return n

    def test_vocab_table_paginates(self):
        do = _fresh()
        n = do.insert_words_bulk(111, [
            {"word": f"word{i}", "phonetic": None, "meaning": f"nghĩa {i}",
             "example": None, "note": None} for i in range(35)
        ])
        feed_msg(do, "/vocab")
        t = last_text(do)
        assert "(35)" in t
        markup = do.env.sent[-1]["payload"]["reply_markup"]["inline_keyboard"]
        buttons = [b["callback_data"] for row in markup for b in row]
        assert {"vact:edit", "vact:delete"}.issubset(buttons)
        assert "menu:add" not in buttons and "vact:view" not in buttons
        assert "Page 1/4" in t
        assert "word0" in t and "word9" in t and "word10" not in t

    def test_vocab_page2(self):
        do = _fresh()
        do.insert_words_bulk(111, [
            {"word": f"word{i}", "phonetic": None, "meaning": f"nghĩa {i}",
             "example": None, "note": None} for i in range(35)
        ])
        feed_cb(do, "vpg:3")
        t = last_text(do)
        assert "word30" in t and "Page 4/4" in t
        assert "word14" not in t

    def test_vocab_search_by_stt(self):
        do = _fresh()
        do.insert_words_bulk(111, [
            {"word": f"word{i}", "phonetic": None, "meaning": f"nghĩa {i}",
             "example": None, "note": None} for i in range(10)
        ])
        feed_msg(do, "/vocab")
        feed_cb(do, "vsrch")
        feed_msg(do, "3")
        t = last_text(do)
        assert "word2" in t  # stt 3 = word2 (0-based id 3rd)

    def test_vocab_search_by_word(self):
        do = _fresh()
        do.insert_words_bulk(111, [
            {"word": "hello", "phonetic": "/hə/", "meaning": "xin chào",
             "example": "Hi there", "note": None},
            {"word": "world", "phonetic": None, "meaning": "thế giới",
             "example": None, "note": None},
        ])
        feed_cb(do, "vsrch", message_id=1)
        feed_msg(do, "world")
        t = last_text(do)
        assert "world" in t and "thế giới" in t

    def test_add_single_word_opens_en_confirm_or_format(self, monkeypatch):
        """`/add hello` looks up EN definition, then asks agree/manual."""
        from services import dict_service

        async def fake_lookup(word):
            return {"word": word, "phonetic": "", "pos": "", "definition": "a greeting", "example": ""}

        monkeypatch.setattr(dict_service, "lookup", fake_lookup)
        do = _fresh()
        feed_msg(do, "/add hello")
        assert do.storage.kv.get("fsm:111")["flow"] == "add_confirm_en"
        assert "a greeting" in last_text(do)


def test_second_do_wakeup_skips_schema_ddl():
    from src.vocab_do import VocabularyDO

    do = _fresh()
    sql_calls = []
    orig = do.ctx.storage.sql.exec
    do.ctx.storage.sql.exec = lambda sql, *a: (sql_calls.append(sql), orig(sql, *a))[1]
    VocabularyDO(do.ctx, do.env)
    assert sql_calls == []


def test_callback_runs_ack_and_edit_concurrently(monkeypatch):
    import json
    import types
    import telegram as tg

    do = _fresh()
    in_flight = 0
    max_in_flight = 0

    async def tracked_fetch(url, method=None, headers=None, body=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        async def _json():
            return {"ok": True, "result": {"message_id": 500}}
        return types.SimpleNamespace(status=200, json=_json)

    monkeypatch.setattr(tg, "fetch", tracked_fetch)
    feed_cb(do, "menu:help", message_id=500)
    assert max_in_flight >= 2
