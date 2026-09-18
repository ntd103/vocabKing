"""Thin wrapper around py-fsrs: serialize/deserialize Card for SQLite storage,
perform reviews, and compute the next due time.

py-fsrs is pure Python and works on Cloudflare's Pyodide runtime. All datetimes
are UTC (py-fsrs requirement; Workers default clock is UTC).
"""

from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler

# Stable schedule configuration (could become a setting later).
_SCHEDULER = Scheduler()

RATINGS = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}


def new_card_json() -> str:
    """Serialize a fresh Card (due = now) to JSON for the cards table."""
    return Card().to_json()


def card_from_json(card_json: str) -> Card:
    """Deserialize a Card from the cards table. Accepts str or dict."""
    return Card.from_json(card_json)


def review(card: Card, rating_key: str, when: datetime | None = None) -> tuple[Card, int]:
    """Apply a rating to a card. Returns (updated_card, scheduled_days).

    `when` defaults to now(UTC). `scheduled_days` is the interval until next
    due, in whole days (0 for minute-level learning steps).
    """
    rating = RATINGS[rating_key]
    updated, _log = _SCHEDULER.review_card(
        card,
        rating,
        review_datetime=when or datetime.now(timezone.utc),
    )
    scheduled_days = 0
    if updated.last_review:
        scheduled_days = max(0, (updated.due - updated.last_review).days)
    return updated, scheduled_days


def card_due(card: Card) -> str:
    """ISO string of the card's due time (UTC)."""
    return card.due.isoformat()


def due_from_json(card_json: str) -> str:
    return card_from_json(card_json).due.isoformat()


def due_from_dict(card_dict: dict) -> str:
    return Card.from_dict(card_dict).due.isoformat()


__all__ = [
    "RATINGS",
    "new_card_json",
    "card_from_json",
    "review",
    "card_due",
    "due_from_json",
    "due_from_dict",
]
