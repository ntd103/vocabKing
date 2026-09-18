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
        assert "Vocaboss" in last_text(do)


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
        feed_msg(do, "/add hello|/həˈloʊ/|xin chào|Hi Paul|note")
        assert "1 từ" in last_text(do)  # preview
        assert do.storage.data.get("fsm:111", {}).get("flow") == "add_confirm"
        feed_cb(do, "add:confirm")
        assert "Đã thêm 1 từ" in last_text(do)
        rows = list(do.storage.sql.exec("SELECT word, phonetic, meaning FROM words"))
        assert rows[0].word == "hello"

    def test_add_bulk_wrapped(self):
        do = _fresh()
        feed_msg(do, "/add a1|m1\na2|m2|n2\na3|m3|n3")
        assert "3 từ" in last_text(do)
        feed_cb(do, "add:confirm")
        words = [r.word for r in do.storage.sql.exec("SELECT word FROM words")]
        assert words == ["a1", "a2", "a3"]

    def test_add_cancel(self):
        do = _fresh()
        feed_msg(do, "/add x|y")
        feed_cb(do, "add:cancel")
        assert "huỷ" in last_text(do).lower()
        assert list(do.storage.sql.exec("SELECT 1 FROM words")) == []

    def test_add_via_fsm_input(self):
        do = _fresh()
        feed_msg(do, "/add")
        assert "mỗi dòng" in last_text(do).lower()
        feed_msg(do, "solo|/soʊ/|một mình")
        feed_cb(do, "add:confirm")
        assert do.word_row(1).word == "solo"

    def test_add_creates_card_due_now(self):
        do = _fresh()
        feed_msg(do, "/add w1")
        feed_cb(do, "add:confirm")
        card = do.get_card(1)
        due = dt.datetime.fromisoformat(card.due)
        assert due <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1)


class TestDefinitionReviewFlow:
    def _add_and_prompt(self, do):
        feed_msg(do, "/add hello|/həˈloʊ/|xin chào|Hi Paul|friendly")
        feed_cb(do, "add:confirm")
        do.storage.kv.put("set:mode", "definition")
        do.env.sent.clear()
        feed_msg(do, "/study")
        # find the prompt message (definition prompt asks "Nghĩa là gì?")
        prompts = [s for s in do.env.sent if "Nghĩa là gì" in s["payload"].get("text", "")]
        assert prompts, f"no prompt in {sent_texts(do.env)}"
        prompt_id = prompts[0]["result"]["message_id"]
        return prompt_id

    def test_study_sends_prompt(self):
        do = _fresh()
        self._add_and_prompt(do)
        kb = do.env.sent[-1]["payload"]["reply_markup"]["inline_keyboard"]
        assert kb[0][0]["callback_data"].startswith("show:")

    def test_show_answer_then_rate(self):
        do = _fresh()
        prompt_id = self._add_and_prompt(do)
        card_id = 1
        do.env.sent.clear()
        feed_cb(do, f"show:{card_id}", message_id=prompt_id)
        assert "Nghĩa:" in last_text(do) and "xin chào" in last_text(do)
        # rate good
        old_due = dt.datetime.fromisoformat(do.get_card(card_id).due)
        feed_cb(do, f"rate:{card_id}:good", message_id=prompt_id)
        assert "đã chấm" in last_text(do)
        new_due = dt.datetime.fromisoformat(do.get_card(card_id).due)
        assert new_due > old_due
        # review logged
        assert list(do.storage.sql.exec("SELECT rating FROM reviews"))

    def test_rating_updates_fsm_alarm(self):
        do = _fresh()
        self._add_and_prompt(do)
        feed_cb(do, "rate:1:good", message_id=do.env.sent[-1]["payload"].get("message_id", 500))
        # alarm rescheduled to future due
        assert do.storage.alarm is not None


class TestClozeFlow:
    def _add_example_and_prompt(self, do):
        feed_msg(do, "/add apple|/ˈæp.əl/|quả táo|An apple a day keeps the doctor away")
        feed_cb(do, "add:confirm")
        do.storage.put("set:mode", "cloze")
        do.env.sent.clear()
        feed_msg(do, "/study")
        prompts = [s for s in do.env.sent if "Điền từ" in s["payload"].get("text", "")]
        assert prompts, sent_texts(do.env)
        return prompts[0]["result"]["message_id"]

    def test_cloze_prompt_masks(self):
        do = _fresh()
        mid = self._add_example_and_prompt(do)
        text = last_text(do)
        assert "A_ a____ a d__ k____ t__ d_____ a___" in text  # first letters kept

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
        feed_msg(do, "an apple a day keeps the doctor away", reply_to=mid)
        assert "Chính xác" in last_text(do)
        feed_cb(do, "rate:1:good", message_id=mid)
        assert "đã chấm" in last_text(do)

    def test_cloze_answer_wrong(self):
        do = _fresh()
        mid = self._add_example_and_prompt(do)
        feed_msg(do, "something else entirely", reply_to=mid)
        assert "Chưa đúng" in last_text(do)


class TestEditDeleteFlow:
    def test_edit_flow(self):
        do = _fresh()
        feed_msg(do, "/add hello|xin chào")
        feed_cb(do, "add:confirm")
        do.env.sent.clear()
        feed_msg(do, "/edit hel")
        # single match -> straight to field picker
        assert "Chọn trường" in last_text(do)
        feed_cb(do, "editf:1:meaning")
        assert "Gửi nội dung mới" in last_text(do)
        feed_msg(do, "xin chào đã sửa")
        assert "Đã cập nhật" in last_text(do)
        assert do.word_row(1).meaning == "xin chào đã sửa"

    def test_delete_flow(self):
        do = _fresh()
        feed_msg(do, "/add goodbye|tạm biệt")
        feed_cb(do, "add:confirm")
        do.env.sent.clear()
        feed_msg(do, "/delete good")
        feed_cb(do, "delw:1")
        assert "Chắc chắn" in last_text(do)
        feed_cb(do, "del:confirm:1")
        assert "Đã xoá" in last_text(do)
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
        do.storage.put("set:quiet_start", "1")
        do.storage.put("set:quiet_end", "1")
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


class TestUnknownInput:
    def test_random_text_gets_hint(self):
        do = _fresh()
        feed_msg(do, "hello there")
        assert "chưa hiểu" in last_text(do).lower() or "menu" in last_text(do).lower()

    def test_cancel_clears_fsm(self):
        do = _fresh()
        feed_msg(do, "/add")
        feed_msg(do, "/cancel")
        assert "fsm:111" not in do.storage.data


class TestAlarmFlow:
    def test_alarm_sends_prompt_when_due(self):
        do = _fresh()
        feed_msg(do, "/add w1|m1")
        feed_cb(do, "add:confirm")
        do.storage.kv.put("set:quiet_start", "1")
        do.storage.kv.put("set:quiet_end", "1")  # quiet off (1..1)
        do.env.sent.clear()
        asyncio.run(do.alarm())
        texts = sent_texts(do.env)
        assert any("w1" in t for t in texts)  # prompt arrived via alarm

    def test_alarm_reschedules_for_future_due(self):
        do = _fresh()
        feed_msg(do, "/add w1|m1")
        feed_cb(do, "add:confirm")
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
        feed_msg(do, "/add w1|m1")
        feed_cb(do, "add:confirm")
        do.env.sent.clear()
        asyncio.run(do._alarm_tick())
        assert send_count(do) == 0

    def test_alarm_tick_daytime_sends_prompt(self, monkeypatch):
        import src.vocab_do as vocab_do

        # pin the clock outside quiet hours so the check is time-independent
        day_time = dt.datetime(2026, 9, 17, 4, 0, tzinfo=dt.timezone.utc)  # 11:00+7
        monkeypatch.setattr(vocab_do, "now_utc", lambda: day_time)
        do = _fresh()
        feed_msg(do, "/add w1|m1")
        feed_cb(do, "add:confirm")
        do.env.sent.clear()
        asyncio.run(do._alarm_tick())
        assert send_count(do) == 1
