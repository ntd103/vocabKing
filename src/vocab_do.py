"""VocabularyDO — the stateful heart of Vocaboss.

One Durable Object instance (SQLite storage) owns all bot state:
words, FSRS cards, review sessions, settings, FSM dialogs — plus the alarm
that fires reminders 24/7 on Cloudflare's free plan.
"""

import json
import random
import time
from datetime import datetime, timedelta, timezone

from workers import DurableObject, Response

import texts
from keyboards import MENU_KB
from handlers import add, delete, edit, review, settings
from services import fsrs_service
from telegram import answer_callback, send_message

SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  word TEXT NOT NULL,
  phonetic TEXT,
  meaning TEXT,
  example TEXT,
  note TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  word_id INTEGER NOT NULL UNIQUE REFERENCES words(id) ON DELETE CASCADE,
  card_json TEXT NOT NULL,
  due TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(due);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  card_id INTEGER NOT NULL,
  rating INTEGER NOT NULL,
  reviewed_at TEXT NOT NULL
);
"""

DEFAULTS = {"quiet_start": "23", "quiet_end": "7", "mode": "mix"}

EDIT_FIELD_LABELS = {
    "word": "Từ", "phonetic": "Phiên âm", "meaning": "Nghĩa",
    "example": "Ví dụ", "note": "Note",
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def esc(s) -> str:
    """HTML-escape user content for Telegram parse_mode=HTML."""
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class VocabularyDO(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.storage = ctx.storage
        self.storage.sql.exec(SCHEMA)
        for k, v in DEFAULTS.items():
            if self.storage.kv.get(f"set:{k}") is None:
                self.storage.kv.put(f"set:{k}", v)

    def _now(self) -> datetime:
        return now_utc()

    # ---------- settings ----------

    def setting(self, key: str) -> str:
        return self.storage.kv.get(f"set:{key}") or DEFAULTS.get(key)

    # ---------- quiet hours ----------

    def _tz_offset(self) -> int:
        try:
            return int(self.env.TZ_OFFSET_HOURS or "7")
        except (TypeError, ValueError):
            return 7

    def local_hour(self, dt: datetime) -> int:
        return (dt.hour + self._tz_offset()) % 24

    def is_quiet(self, dt: datetime) -> bool:
        """Quiet window: quiet_start (inclusive) -> quiet_end (exclusive); may wrap midnight."""
        try:
            start, end = int(self.setting("quiet_start")), int(self.setting("quiet_end"))
        except ValueError:
            start, end = 23, 7
        if start == end:
            return False
        h = self.local_hour(dt)
        if start > end:
            return h >= start or h < end
        return start <= h < end

    def wake_time(self, dt: datetime) -> datetime:
        """If dt falls in quiet hours, the next quiet_end (local), else dt."""
        if not self.is_quiet(dt):
            return dt
        end_hour = int(self.setting("quiet_end"))
        wake_utc_hour = (end_hour - self._tz_offset()) % 24
        candidate = dt.replace(hour=wake_utc_hour, minute=0, second=0, microsecond=0)
        if candidate <= dt:
            candidate += timedelta(days=1)
        return candidate

    # ---------- RPC entry (called by the Worker via stub) ----------

    async def handle_update(self, update: dict):
        try:
            owner = str(self.env.OWNER_ID or "")
            cb = update.get("callback_query")
            if cb:
                if str(cb.get("from", {}).get("id")) != owner:
                    return
                return await self.on_callback(cb)
            msg = update.get("message")
            if msg:
                if str(msg.get("from", {}).get("id")) != owner:
                    return
                return await self.on_message(msg)
        except Exception as e:  # never let Telegram retry-loop on our bugs
            print("handle_update error:", repr(e))

    async def on_callback(self, cb: dict):
        data = cb.get("data", "")
        chat_id = cb["message"]["chat"]["id"]
        message_id = cb["message"]["message_id"]
        await answer_callback(self.env, cb["id"])
        parts = data.split(":")

        if parts[0] == "rate" and len(parts) == 3:
            await review.rate(self, chat_id, message_id, int(parts[1]), parts[2])
        elif parts[0] == "show" and len(parts) == 2:
            await review.show_answer(self, chat_id, message_id, int(parts[1]))
        elif parts[0] == "add":
            await add.on_confirm(self, chat_id, message_id, parts[1])
        elif parts[0] == "menu":
            await self.on_menu(chat_id, parts[1])
        elif parts[0] == "editf" and len(parts) == 3:
            await edit.pick_field(self, chat_id, int(parts[1]), parts[2])
        elif parts[0] == "editw" and len(parts) == 2:
            await edit.pick_word(self, chat_id, int(parts[1]))
        elif parts[0] == "delw" and len(parts) == 2:
            await delete.pick_word(self, chat_id, int(parts[1]))
        elif parts[0] == "del" and parts[1] == "confirm" and len(parts) == 3:
            await delete.confirm(self, chat_id, int(parts[2]))
        elif parts[0] == "del" and parts[1] == "cancel":
            from telegram import edit_message

            await edit_message(self.env, chat_id, message_id, "Đã giữ lại từ.")
        elif parts[0] == "mode" and len(parts) == 2:
            await settings.set_mode(self, chat_id, message_id, parts[1])
        elif parts[0] == "quiet" and len(parts) >= 2:
            await settings.set_quiet(self, chat_id, message_id, ":".join(parts[1:]))

    async def on_menu(self, chat_id, what: str):
        commands = {
            "study": "/study", "add": "/add", "edit": "/edit",
            "delete": "/delete", "settings": "/settings",
        }
        if what in commands:
            await self.handle_command(chat_id, commands[what])
        elif what == "help":
            await send_message(self.env, chat_id, texts.HELP)

    async def on_message(self, msg: dict):
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        if not text:
            return

        # reply to a review prompt?
        reply_to = msg.get("reply_to_message", {}).get("message_id")
        if reply_to and await review.on_reply(self, chat_id, reply_to, text):
            return

        if text.startswith("/"):
            return await self.handle_command(chat_id, text)

        # active dialog (add / search-by-keyword / edit-value)?
        fsm = self.storage.kv.get(f"fsm:{chat_id}")
        if fsm:
            flow = fsm.get("flow")
            if flow in ("add_input", "add_confirm"):
                return await add.on_input(self, chat_id, text)
            if flow in ("edit_search", "delete_search"):
                do_search = edit.search if flow == "edit_search" else delete.search
                return await do_search(self, chat_id, text)
            if flow == "edit_value":
                return await edit.on_value(self, chat_id, fsm, text)

        await send_message(self.env, chat_id, texts.HINT_ROOT)

    # ---------- commands ----------

    async def handle_command(self, chat_id, raw: str):
        cmd, _, arg = raw.partition(" ")
        cmd = cmd.split("@")[0].lower()  # strip /cmd@botname
        if cmd in ("/start", "/menu"):
            await send_message(self.env, chat_id, texts.MENU, reply_markup=MENU_KB)
        elif cmd == "/help":
            await send_message(self.env, chat_id, texts.HELP)
        elif cmd == "/add":
            await add.start(self, chat_id, arg.strip())
        elif cmd == "/study":
            await review.start_study(self, chat_id)
        elif cmd == "/edit":
            await edit.start(self, chat_id, arg.strip())
        elif cmd == "/delete":
            await delete.start(self, chat_id, arg.strip())
        elif cmd == "/settings":
            await settings.show(self, chat_id)
        elif cmd == "/cancel":
            self.set_fsm(chat_id, None)
            await send_message(self.env, chat_id, "Đã huỷ thao tác đang dở.")
        else:
            await send_message(self.env, chat_id, texts.HINT_ROOT)

    # ---------- fsm helpers ----------

    def set_fsm(self, chat_id, state: dict | None):
        if state is None:
            self.storage.kv.delete(f"fsm:{chat_id}")
        else:
            self.storage.kv.put(f"fsm:{chat_id}", state)

    # ---------- words / cards helpers ----------

    def insert_word(self, user_id: int, entry: dict) -> int:
        self.storage.sql.exec(
            "INSERT INTO words (user_id, word, phonetic, meaning, example, note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            user_id, entry["word"], entry["phonetic"], entry["meaning"],
            entry["example"], entry["note"], now_utc().isoformat(),
        )
        # DO SQL cursor has no last_insert_rowid — read it back (SQL is sync and
        # private to this DO instance, so no race between INSERT and SELECT).
        rows = list(self.storage.sql.exec("SELECT MAX(id) AS id FROM words"))
        word_id = rows[0].id if rows else 0
        self.storage.sql.exec(
            "INSERT INTO cards (word_id, card_json, due) VALUES (?, ?, ?)",
            word_id, fsrs_service.new_card_json(), now_utc().isoformat(),
        )
        return word_id

    def word_row(self, word_id: int):
        rows = list(self.storage.sql.exec(
            "SELECT id, word, phonetic, meaning, example, note FROM words WHERE id = ?",
            word_id,
        ))
        return rows[0] if rows else None

    def search_words(self, kw: str, limit: int = 10):
        cur = self.storage.sql.exec(
            "SELECT id, word, meaning FROM words WHERE word LIKE ? OR meaning LIKE ?"
            " ORDER BY word LIMIT ?",
            f"%{kw}%", f"%{kw}%", limit,
        )
        return list(cur)

    def get_card(self, card_id: int):
        rows = list(self.storage.sql.exec(
            "SELECT id, word_id, card_json, due FROM cards WHERE id = ?", card_id
        ))
        return rows[0] if rows else None

    def save_card(self, card_id: int, card):
        self.storage.sql.exec(
            "UPDATE cards SET card_json = ?, due = ? WHERE id = ?",
            card.to_json(), card.due.isoformat(), card_id,
        )

    def log_review(self, card_id: int, rating_name: str):
        from services.fsrs_service import RATINGS

        self.storage.sql.exec(
            "INSERT INTO reviews (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
            card_id, int(RATINGS[rating_name]), now_utc().isoformat(),
        )

    # ---------- alarms (the 24/7 reminder engine) ----------

    def _pick_due(self):
        now = now_utc().isoformat()
        rows = list(self.storage.sql.exec(
            "SELECT id, word_id, card_json, due FROM cards WHERE due <= ?"
            " ORDER BY due LIMIT 1",
            now,
        ))
        return rows[0] if rows else None

    def _next_future_due(self):
        rows = list(self.storage.sql.exec(
            "SELECT due FROM cards WHERE due > ? ORDER BY due LIMIT 1",
            now_utc().isoformat(),
        ))
        if rows:
            return datetime.fromisoformat(rows[0].due)
        return None

    def _reschedule(self):
        """Next alarm: soon if cards are due, else next future due (delayed past
        quiet hours). Nothing left -> clear the alarm."""
        if self._pick_due() is not None:
            self.storage.setAlarm(int(time.time() * 1000) + 60_000)
            return
        nxt = self._next_future_due()
        if nxt is None:
            self.storage.deleteAlarm()
            return
        self.storage.setAlarm(int(self.wake_time(nxt).timestamp() * 1000))

    async def alarm(self):
        try:
            await self._alarm_tick()
        except Exception as e:
            print("alarm error:", repr(e))
            raise  # let Cloudflare retry with backoff
        finally:
            self._reschedule()

    async def _alarm_tick(self):
        now = now_utc()
        if self.is_quiet(now):
            return  # _reschedule() sets the wake-up alarm
        card_row = self._pick_due()
        if card_row is None:
            return
        word = self.word_row(card_row.word_id)
        if word is None:
            return
        await review.send_prompt(self, self.env.OWNER_CHAT_ID, card_row, word)

    # ---------- review session persistence ----------

    def put_session(self, message_id, session: dict):
        self.storage.kv.put(f"session:{message_id}", json.dumps(session))

    def get_session(self, message_id):
        raw = self.storage.kv.get(f"session:{message_id}")
        return json.loads(raw) if raw else None

    def pop_session(self, message_id):
        self.storage.kv.delete(f"session:{message_id}")
