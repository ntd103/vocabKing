from datetime import datetime, timezone

from fsrs import Card

from src.services.fsrs_service import (
    card_due,
    card_from_json,
    due_from_dict,
    due_from_json,
    new_card_json,
    review,
)


class TestSerialization:
    def test_new_card_json_roundtrip(self):
        card = card_from_json(new_card_json())
        assert card is not None
        assert card_due(card) is not None

    def test_due_from_json(self):
        j = new_card_json()
        assert due_from_json(j) == card_due(card_from_json(j))

    def test_due_from_dict(self):
        card = Card()
        assert due_from_dict(card.to_dict()) == card_due(card)


class TestReview:
    def test_review_good_schedules_future(self):
        card = Card()
        now = datetime.now(timezone.utc)
        updated, days = review(card, "good", when=now)
        assert card_due(updated) > now.isoformat()
        assert days >= 0

    def test_review_again_due_sooner_than_good(self):
        card = Card()
        now = datetime.now(timezone.utc)
        again_card, _ = review(card, "again", when=now)
        good_card, _ = review(card, "good", when=now)
        assert card_due(again_card) < card_due(good_card)

    def test_repeated_good_grows_interval(self):
        # Learning steps schedule by minutes (scheduled_days=0 at first);
        # after graduating, intervals grow with each successful review.
        from datetime import timedelta

        card = Card()
        when = datetime.now(timezone.utc)
        days_seen = []
        for _ in range(8):
            card, days = review(card, "good", when=when)
            days_seen.append(days)
            when = card.due  # review at exactly due time each round
        assert max(days_seen) > 0  # eventually leaves learning steps
        assert days_seen[-1] > days_seen[0]  # interval grows

    def test_all_rating_keys(self):
        card = Card()
        for key in ("again", "hard", "good", "easy"):
            updated, _ = review(card, key)
            assert updated is not None
