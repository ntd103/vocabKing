"""Regressions for old storage and real review callbacks."""
import asyncio

from tests.conftest import FakeEnv, _Ctx, _install_workers_stub
from tests.test_vocab_do import _fresh, feed_cb, feed_msg, last_text, make_cards_due


def test_bulk_insert_rolls_back_words_when_card_insert_fails(monkeypatch):
    import pytest

    do = _fresh()
    original = do.storage.sql.exec

    def fail_cards(sql, *args):
        if sql.startswith("INSERT INTO cards"):
            raise RuntimeError("simulated card insert failure")
        return original(sql, *args)

    monkeypatch.setattr(do.storage.sql, "exec", fail_cards)
    with pytest.raises(RuntimeError, match="simulated card insert failure"):
        do.insert_words_bulk(111, [
            {"word": "atomic", "phonetic": None, "define_en": None,
             "meaning": "atomic", "example": None, "note": None},
        ])

    assert do.count_words() == 0
    assert list(original("SELECT id FROM cards")) == []


def test_old_schema_migration_preserves_data():
    _install_workers_stub()
    from src.vocab_do import SCHEMA, VocabularyDO
    ctx = _Ctx()
    ctx.storage.sql.exec(SCHEMA.replace('  define_en TEXT,       -- English definition\n', ''))
    ctx.storage.sql.exec("INSERT INTO words(user_id,word,meaning,created_at) VALUES(111,'hello','xin chào','2026-01-01')")
    do = VocabularyDO(ctx, FakeEnv())
    assert do.word_row(1).meaning == 'xin chào'
    assert do.word_row(1).define_en is None
    VocabularyDO(ctx, do.env)
    assert do.count_words() == 1


def prompt(mode='definition'):
    do = _fresh()
    feed_msg(do, '/add hello||a greeting|xin chào|Hello there|note')
    feed_cb(do, 'add:confirm')
    make_cards_due(do)
    do.put_setting('mode', mode)
    feed_msg(do, '/study')
    mid = do.env.sent[-1]['result']['message_id']
    return do, mid


def test_definition_hint_button_and_reveal_auto_grades():
    do, mid = prompt()
    keyboard = do.env.sent[-1]['payload'].get('reply_markup', {})
    assert 'hint:1' in str(keyboard)
    feed_cb(do, 'hint:1', message_id=mid)
    assert 'x' in last_text(do)
    assert do.get_session(mid)
    feed_cb(do, 'show:1', message_id=mid)
    assert 'a greeting' in last_text(do) and 'xin chào' in last_text(do)
    assert do.get_session(mid) is None
    assert [r.rating for r in do.storage.sql.exec('SELECT rating FROM reviews')] == [1]


def test_rating_is_bound_to_revealed_session_and_idempotent():
    from services import fsrs_service
    do, mid = prompt()
    old = do.get_card(1).card_json
    feed_cb(do, 'rate:1:good', message_id=mid)
    assert do.get_card(1).card_json == old
    feed_msg(do, 'hello', reply_to=mid)
    feed_cb(do, 'rate:1:invalid', message_id=mid)
    feed_cb(do, 'rate:1:good', message_id=mid+100)
    assert do.get_card(1).card_json == old
    feed_cb(do, 'rate:1:good', message_id=mid)
    updated = do.get_card(1)
    assert 'menu:study' in str(do.env.sent[-1]['payload'])
    feed_cb(do, 'rate:1:good', message_id=mid)
    assert do.get_card(1).card_json == updated.card_json
    card = fsrs_service.card_from_json(updated.card_json)
    assert card.due.isoformat() == updated.due
    logs = list(do.storage.sql.exec('SELECT reviewed_at FROM reviews'))
    assert len(logs) == 1 and logs[0].reviewed_at == card.last_review.isoformat()
    assert do.daily_counts() == (1, 1)


def test_add_completion_returns_menu():
    do = _fresh()
    feed_msg(do, '/add word||definition|nghĩa')
    feed_cb(do, 'add:confirm')
    assert 'vact:edit' in str(do.env.sent[-1]['payload'])
    assert do.storage.kv.get('fsm:111')['flow'] == 'vocab_select'


def test_grading_rolls_back_if_logging_fails(monkeypatch):
    import pytest
    from handlers import review
    do, mid = prompt()
    feed_msg(do, 'hello', reply_to=mid)
    before = do.get_card(1).card_json
    original = do.storage.sql.exec
    def fail_log(sql, *args):
        if sql.startswith('INSERT INTO reviews'):
            raise RuntimeError('simulated write failure')
        return original(sql, *args)
    monkeypatch.setattr(do.storage.sql, 'exec', fail_log)
    with pytest.raises(RuntimeError, match='simulated'):
        asyncio.run(review.rate(do, 111, mid, 1, 'good'))
    assert do.get_card(1).card_json == before
    assert do.get_session(mid)['ready']
    assert do.daily_counts() == (1, 0)


def test_dictionary_workflow_persists_both_meanings(monkeypatch):
    from services import dict_service
    async def lookup(word):
        return {'word': word, 'phonetic': '/hə/', 'pos': 'noun',
                'definition': 'a greeting', 'example': 'Hello there'}
    monkeypatch.setattr(dict_service, 'lookup', lookup)
    do = _fresh()
    feed_msg(do, '/add hello')
    assert do.storage.kv.get('fsm:111')['flow'] == 'add_confirm_en'
    assert do.count_words() == 0
    feed_msg(do, '1')
    assert do.storage.kv.get('fsm:111')['flow'] == 'add_input'
    feed_msg(do, 'hello||a greeting|xin chào|Hello there')
    feed_cb(do, 'add:confirm')
    word = do.word_row(1)
    assert (word.define_en, word.meaning, word.example) == ('a greeting', 'xin chào', 'Hello there')
    assert do.get_card(1) and do.daily_counts() == (1, 0)
    assert 'vact:edit' in str(do.env.sent[-1]['payload'])


def test_cancel_returns_menu_and_clears_dialog():
    do = _fresh()
    feed_msg(do, '/add')
    feed_msg(do, '/cancel')
    assert do.storage.kv.get('fsm:111')['flow'] == 'vocab_select'
    assert 'vact:edit' in str(do.env.sent[-1]['payload'])
