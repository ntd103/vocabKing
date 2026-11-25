"""Independent FSRS reference values and due-time reminder behavior."""

import asyncio
import math
from datetime import datetime, timedelta, timezone

import pytest
from fsrs import Card, Scheduler, State

from tests.conftest import _install_workers_stub

_install_workers_stub()
from tests.test_vocab_do import _fresh


def test_fsrs_review_matches_hand_calculated_reference(monkeypatch):
    from services import fsrs_service

    when = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    card = Card(state=State.Review, stability=10.0, difficulty=5.0,
                due=when, last_review=when - timedelta(days=8))
    monkeypatch.setattr(fsrs_service, "_SCHEDULER", Scheduler(enable_fuzzing=False))

    updated, days = fsrs_service.review(card, "good", when=when)

    # FSRS default weights; retrievability is independently calculated from
    # elapsed=8 days and S=10 using its published power-law equation.
    p = (0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001,
         1.8722, 0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014,
         1.8729, 0.5425, 0.0912, 0.0658, 0.1542)
    decay = -p[20]
    factor = 0.9 ** (1 / decay) - 1
    retrievability = (1 + factor * 8 / 10) ** decay
    expected_stability = 10 * (
        1 + math.exp(p[8]) * (11 - 5) * 10 ** (-p[9])
        * (math.exp((1 - retrievability) * p[10]) - 1)
    )
    recall_growth = math.exp(p[8]) * (11 - 5) * 10 ** (-p[9]) * (
        math.exp((1 - retrievability) * p[10]) - 1
    )
    expected_easy_stability = 10 * (1 + recall_growth * p[16])
    initial_easy_difficulty = p[4] - math.exp(p[5] * (4 - 1)) + 1
    delta = -(p[6] * (3 - 3))
    adjusted_difficulty = 5 + (10 - 5) * delta / 9
    expected_difficulty = max(1, min(10, p[7] * initial_easy_difficulty + (1 - p[7]) * adjusted_difficulty))
    expected_interval = max(1, round(expected_stability / factor))

    assert expected_stability == pytest.approx(28.703691642552318)
    assert updated.stability == pytest.approx(expected_stability)
    assert updated.difficulty == pytest.approx(expected_difficulty)
    assert updated.difficulty == pytest.approx(4.9902283692968386)
    assert days == expected_interval == 29
    assert updated.due == when + timedelta(days=29)

    easy_card, easy_days = fsrs_service.review(card, "easy", when=when)
    easy_initial = p[4] - math.exp(p[5] * (4 - 1)) + 1
    easy_adjusted = 5 + (10 - 5) * (-(p[6] * (4 - 3))) / 9
    expected_easy_difficulty = max(1, min(10,
        p[7] * easy_initial + (1 - p[7]) * easy_adjusted))
    expected_easy_interval = max(1, round((expected_easy_stability / factor) * (0.9 ** (1 / decay) - 1)))
    assert easy_card.stability == pytest.approx(expected_easy_stability)
    assert easy_card.difficulty == pytest.approx(expected_easy_difficulty)
    assert easy_days == expected_easy_interval
    assert easy_card.due == when + timedelta(days=easy_days)


def test_alarm_sends_at_due_time_not_before(monkeypatch):
    import src.vocab_do as vocab_do

    due = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    now = due - timedelta(seconds=1)
    monkeypatch.setattr(vocab_do, "now_utc", lambda: now)
    do = _fresh()
    do.insert_words_bulk(111, [dict(word="hello", phonetic=None,
        define_en="greeting", meaning="xin chào", example=None, note=None)])
    do.storage.sql.exec("UPDATE cards SET due = ? WHERE id = 1", due.isoformat())
    do._reschedule()

    assert do.storage.alarm == int(due.timestamp() * 1000)
    asyncio.run(do.alarm())
    assert not [call for call in do.env.sent if call["method"] == "sendMessage"]

    now = due
    asyncio.run(do.alarm())
    assert len([call for call in do.env.sent if call["method"] == "sendMessage"]) == 1
