"""One outstanding quiz, target-word cloze and bounded reminders."""
import asyncio
from datetime import datetime, timedelta, timezone

from tests.test_vocab_do import _fresh, feed_msg, feed_cb, last_text, make_cards_due


def seed(do):
    do.insert_words_bulk(111, [dict(word=w, phonetic=None, define_en='greeting',
        meaning='xin chào', example=ex, note=None) for w, ex in
        [('hello', 'hello Bob'), ('apple', 'An apple a day'), ('bye', 'Say bye'), ('cat', 'A cat sleeps')]])
    make_cards_due(do)
    do.put_setting('quiet_start', '1')
    do.put_setting('quiet_end', '1')


def messages(do):
    return [s for s in do.env.sent if s['method'] == 'sendMessage']


def test_200_alarm_ticks_send_only_one_quiz_even_after_restart():
    do = _fresh()
    from src.vocab_do import VocabularyDO
    seed(do)
    for _ in range(200):
        asyncio.run(do.alarm())
    assert len(messages(do)) == 1
    assert do.storage.alarm is None
    restarted = VocabularyDO(do.ctx, do.env)
    asyncio.run(restarted.alarm())
    assert len(messages(do)) == 1


def test_quiz_masks_vocab_not_whole_example_and_accepts_bare_answer():
    do = _fresh()
    do.insert_words_bulk(111, [dict(word='hello', phonetic=None, define_en='greeting',
        meaning='xin chào', example='hello Bob, HELLO again!', note=None)])
    make_cards_due(do)
    feed_msg(do, '/study')
    quiz = last_text(do)
    assert 'xin chào' in quiz and 'Bob' in quiz and 'again!' in quiz
    assert 'hello' not in quiz.lower()
    mid = messages(do)[-1]['result']['message_id']
    feed_msg(do, 'hello')
    assert 'Correct!' in last_text(do)
    assert 'rate:1:good' in str(do.env.sent[-1]['payload'])
    assert do.env.sent[-1]['method'] == 'editMessageText'
    assert do.env.sent[-1]['payload']['message_id'] == mid
    asyncio.run(do.alarm())
    assert len(messages(do)) == 1
    feed_cb(do, 'rate:1:good', message_id=mid)
    assert do.daily_counts() == (0, 1)
    assert do.storage.alarm is not None
    assert do.storage.alarm >= datetime.fromisoformat(do.get_card(1).due).timestamp()*1000 - 1


def test_study_reuses_pending_question_and_rating_is_required():
    do = _fresh()
    seed(do)
    feed_msg(do, '/study')
    mid = messages(do)[0]['result']['message_id']
    feed_msg(do, '/study')
    assert len(messages(do)) == 1
    feed_msg(do, 'example', reply_to=mid)
    for _ in range(5):
        asyncio.run(do.alarm())
    assert len(messages(do)) == 1
    feed_msg(do, '/study')
    assert 'rate:' in str(do.env.sent[-1]['payload'])


def test_alarm_quota_exhaustion_waits_until_next_local_day(monkeypatch):
    import src.vocab_do as vd
    now = datetime(2026, 11, 8, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(vd, 'now_utc', lambda: now)
    do = _fresh()
    seed(do)
    do.put_setting('daily_target', '1')
    do.daily_add(1)
    do._reschedule()
    assert do.storage.alarm == int(datetime(2026,11,8,17,tzinfo=timezone.utc).timestamp()*1000)


def test_concurrent_alarm_and_study_reserve_before_network(monkeypatch):
    from handlers import review
    do = _fresh()
    seed(do)
    original = review.send_message
    async def interleaved(*args, **kwargs):
        await review.start_study(do, 111)
        await do._alarm_tick()
        return await original(*args, **kwargs)
    monkeypatch.setattr(review, 'send_message', interleaved)
    asyncio.run(do.alarm())
    assert len(messages(do)) == 1


def test_numeric_rating_grades_only_the_active_ready_review():
    from services import fsrs_service

    for number, rating in enumerate(('again', 'hard', 'good', 'easy'), 1):
        do = _fresh()
        seed(do)
        feed_msg(do, '/study')
        mid = messages(do)[0]['result']['message_id']
        feed_msg(do, 'hello')
        assert do.get_session(mid)['ready']
        assert 'Again (1m)' in str(do.env.sent[-1]['payload']['reply_markup'])
        assert 'Easy (' in str(do.env.sent[-1]['payload']['reply_markup'])

        feed_msg(do, str(number))

        assert do.daily_counts() == (0, 1)
        assert do.get_session(mid) is None
        row = list(do.storage.sql.exec('SELECT rating FROM reviews'))[0]
        assert row.rating == int(fsrs_service.RATINGS[rating])


def test_invalid_numeric_rating_is_rejected_without_grading():
    do = _fresh()
    seed(do)
    feed_msg(do, '/study')
    mid = messages(do)[0]['result']['message_id']
    feed_msg(do, 'hello')
    card_before = do.get_card(do.get_session(mid)['card_id']).card_json

    feed_msg(do, '5')

    assert do.daily_counts() == (0, 0)
    assert do.get_session(mid)['ready']
    assert do.get_card(do.get_session(mid)['card_id']).card_json == card_before
    assert '1' in last_text(do) and '4' in last_text(do)


def test_invalid_rating_from_other_chat_with_colliding_message_id_is_ignored():
    do = _fresh()
    from handlers import review

    seed(do)
    feed_msg(do, '/study')
    mid = messages(do)[0]['result']['message_id']
    feed_msg(do, 'hello')
    do.env.sent.clear()

    asyncio.run(review.rate_text(do, 222, mid, '5'))

    assert do.env.sent == []
    assert do.daily_counts() == (0, 0)
    assert do.get_session(mid)['ready']


    do = _fresh()
    seed(do)
    feed_msg(do, '/study')
    old_mid = messages(do)[0]['result']['message_id']
    feed_msg(do, 'hello')
    feed_msg(do, '3')
    assert do.daily_counts() == (0, 1)

    feed_msg(do, '/study')
    active_mid = messages(do)[-1]['result']['message_id']
    assert active_mid != old_mid
    feed_msg(do, '2', reply_to=old_mid)

    assert do.daily_counts() == (0, 1)
    assert do.get_session(active_mid) is not None


def test_all_ratings_match_fsrs_and_do_not_prompt_before_due(monkeypatch):
    import src.vocab_do as vd
    from services import fsrs_service
    now = datetime(2026,11,8,5,tzinfo=timezone.utc)
    monkeypatch.setattr(vd, 'now_utc', lambda: now)
    for rating in ('again', 'hard', 'good', 'easy'):
        do = _fresh()
        seed(do)
        # Only one card is due; the rest cannot produce immediate reminders.
        do.storage.sql.exec('UPDATE cards SET due=? WHERE id>1', (now+timedelta(days=30)).isoformat())
        feed_msg(do, '/study')
        mid = messages(do)[0]['result']['message_id']
        previous = fsrs_service.card_from_json(do.get_card(1).card_json)
        import random
        state = random.getstate()
        expected, _ = fsrs_service.review(previous, rating, when=now)
        random.setstate(state)  # FSRS fuzzing legitimately randomizes multi-day intervals.
        feed_msg(do, 'hello')
        assert do.storage.alarm is None
        feed_cb(do, f'rate:1:{rating}', message_id=mid)
        card = fsrs_service.card_from_json(do.get_card(1).card_json)
        assert card.due == expected.due and card.last_review == now
        assert card.stability == expected.stability and card.difficulty == expected.difficulty
        assert do.get_card(1).due == card.due.isoformat()
        assert do.storage.alarm == int(card.due.timestamp()*1000)
        asyncio.run(do._alarm_tick())
        assert len(messages(do)) == 1


def test_quiet_hours_defer_overdue_reminders(monkeypatch):
    import src.vocab_do as vd
    now = datetime(2026,11,8,18,tzinfo=timezone.utc)  # 01:00 local
    monkeypatch.setattr(vd, 'now_utc', lambda: now)
    do = _fresh()
    seed(do)
    do.put_setting('quiet_start', '23')
    do.put_setting('quiet_end', '7')
    do._reschedule()
    assert do.storage.alarm == int(datetime(2026,11,9,0,tzinfo=timezone.utc).timestamp()*1000)


def test_deleting_pending_word_unblocks_queue():
    do = _fresh()
    seed(do)
    feed_msg(do, '/study')
    pending = do.storage.kv.get('review:pending')
    word_id = do.get_card(pending['card_id']).word_id
    feed_msg(do, '/delete')
    feed_msg(do, str(word_id))
    feed_cb(do, f'del:confirm:{word_id}')
    assert not do.storage.kv.get('review:pending')
    assert do.get_session(pending['message_id']) is None
    assert do.storage.alarm is not None


def test_review_button_recovers_from_stale_pending_without_session():
    do = _fresh()
    seed(do)
    # Delivered once but session gone — old code returned silently forever.
    do.storage.kv.put("review:pending", {"card_id": 1, "chat_id": "111", "message_id": 700})
    do.env.sent.clear()
    feed_cb(do, "menu:study")
    assert "Type the missing word" in last_text(do)
    pending = do.storage.kv.get("review:pending")
    assert pending and pending.get("message_id")
    assert do.get_session(pending["message_id"])


def test_review_button_recovers_from_abandoned_reserve_without_sending_flag():
    do = _fresh()
    seed(do)
    do.storage.kv.put("review:pending", {"card_id": 1, "chat_id": "111"})
    do.env.sent.clear()
    feed_cb(do, "menu:study")
    assert "Type the missing word" in last_text(do)


def test_cancel_edits_transient_workflow_instead_of_sending():
    do = _fresh()
    feed_msg(do, '/add')
    mid = messages(do)[0]['result']['message_id']
    assert do.storage.kv.get('fsm:111')['flow'] == 'add_ask_word'
    feed_msg(do, '/cancel')
    assert len(messages(do)) == 1
    assert do.env.sent[-1]['payload']['message_id'] == mid
    assert do.storage.kv.get('fsm:111')['flow'] == 'vocab_select'
    body = do.env.sent[-1]['payload'].get('text') or ''
    assert 'Action cancelled' in body and 'No vocabulary yet' in body


def test_no_example_still_tests_english_vocab():
    do = _fresh()
    do.insert_words_bulk(111, [dict(word='hello', phonetic=None, define_en='greeting',
        meaning='xin chào', example='hi Bob', note=None)])
    make_cards_due(do)
    feed_msg(do, '/study')
    assert 'hi Bob' not in last_text(do)
    assert 'xin chào' in last_text(do) and 'hello' not in last_text(do)
    feed_msg(do, 'hi Bob')
    assert 'Incorrect.' in last_text(do)


def test_mask_spacing_preserves_word_boundaries_and_hints():
    from types import SimpleNamespace
    from handlers.review import _quiz_body
    word = SimpleNamespace(word='make up', meaning='trang điểm', example='do make up now')
    assert '<pre>do _ _ _ _   _ _ now</pre>' in _quiz_body(word, '____ __')
    assert '<pre>do m _ _ e   _ p now</pre>' in _quiz_body(word, 'm__e _p')
    word = SimpleNamespace(word='apple', meaning='quả táo', example='An apple a day')
    assert '<pre>An _ _ _ _ _ a day</pre>' in _quiz_body(word, '_____')


def test_first_learning_step_and_bare_reminder_shortcuts_after_add(monkeypatch):
    import src.vocab_do as vd
    from services import fsrs_service
    clock = {'now': datetime(2026, 11, 8, 5, tzinfo=timezone.utc)}
    monkeypatch.setattr(vd, 'now_utc', lambda: clock['now'])
    do = _fresh()
    feed_msg(do, '/add continent|/ˈkɑntɪnənt/|a landmass|châu lục|Africa is a vast continent.')
    feed_cb(do, 'add:confirm')
    row = do.get_card(1)
    due = clock['now'] + timedelta(minutes=5, seconds=30)  # initial Hard grade
    assert fsrs_service.card_from_json(row.card_json).due.isoformat() == row.due == due.isoformat()
    do.set_fsm(111, None)  # leave vocabulary so the due alarm can be scheduled
    assert do.storage.alarm == int(due.timestamp() * 1000)
    assert do._pick_due_random() is None
    clock['now'] = due - timedelta(microseconds=1)
    asyncio.run(do._alarm_tick())
    assert not do.storage.kv.get('review:pending')
    clock['now'] = due
    asyncio.run(do._alarm_tick())
    assert 'Africa is a vast c _ _ _ _ _ _ _ _.' in last_text(do)
    feed_msg(do, '?')
    assert 0 < last_text(do).count('_') < 8
    feed_msg(do, '???')
    assert 'Africa is a vast continent.' in last_text(do)
    assert '/ˈkɑntɪnənt/' in last_text(do).splitlines()
    assert 'Again' in last_text(do) and '1m' in last_text(do)
    assert [r.rating for r in do.storage.sql.exec('SELECT rating FROM reviews')] == [1]
    assert do.storage.alarm == int((clock['now'] + timedelta(minutes=1)).timestamp() * 1000)
    assert not do.storage.kv.get('review:pending')
