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
CREATE TABLE IF NOT EXISTS daily (
  date TEXT PRIMARY KEY,
  added INTEGER NOT NULL DEFAULT 0,
  reviewed INTEGER NOT NULL DEFAULT 0
);
"""

DEFAULTS = {
    "quiet_start": "23", "quiet_end": "7", "mode": "mix",
    "daily_target": "200", "reminder_mode": "quiz",
}

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
        # In-memory settings cache: this DO is the only writer and instances
        # are long-lived, so re-reading KV per call is pure waste. Reset to
        # None on DO eviction (fresh instance) — self-healing.
        self._settings: dict | None = None

    def _now(self) -> datetime:
        return now_utc()

    # ---------- settings ----------

    def setting(self, key: str) -> str:
        s = self._settings
        if s is None:
            s = self._settings = {
                k: (self.storage.kv.get(f"set:{k}") or v) for k, v in DEFAULTS.items()
            }
        return s[key]

    def put_setting(self, key: str, value: str):
        self.storage.kv.put(f"set:{key}", value)
        # Always refresh the cache, even if it wasn't loaded yet — otherwise a
        # later setting() call would serve the stale pre-write snapshot.
        if self._settings is None:
            self._settings = {
                k: (self.storage.kv.get(f"set:{k}") or v) for k, v in DEFAULTS.items()
            }
        self._settings[key] = value

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
        elif parts[0] == "add" and parts[1] in ("confirm", "cancel"):
            await add.on_confirm(self, chat_id, message_id, parts[1])
        elif parts[0] == "add" and parts[1] in ("lookup", "manual"):
            await add.on_mode_pick(self, chat_id, message_id, parts[1])
        elif parts[0] == "menu":
            await self.on_menu(chat_id, parts[1], message_id)
        elif parts[0] == "game" and parts[1] == "story":
            from handlers import games

            await games.story_ask_count(self, chat_id, message_id)
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
        elif parts[0] == "set" and len(parts) == 2:
            await settings.show_section(self, chat_id, message_id, parts[1])
        elif parts[0] == "remmode" and len(parts) == 2:
            await settings.set_reminder_mode(self, chat_id, message_id, parts[1])
        elif parts[0] == "lkex" and len(parts) == 2:
            from handlers import lookup

            await lookup.on_example_choice(self, chat_id, message_id, parts[1])
        elif parts[0] == "lksv" and len(parts) == 2:
            from handlers import lookup

            await lookup.on_save(self, chat_id, message_id, parts[1])

    async def on_menu(self, chat_id, what: str, message_id=None):
        from telegram import edit_message

        if what == "home":
            if message_id:
                await edit_message(self.env, chat_id, message_id, texts.MENU, reply_markup=MENU_KB)
            else:
                await send_message(self.env, chat_id, texts.MENU, reply_markup=MENU_KB)
            return
        if what == "help":
            from keyboards import kb_back_menu

            if message_id:
                await edit_message(self.env, chat_id, message_id, texts.HELP,
                                   reply_markup=kb_back_menu())
            else:
                await send_message(self.env, chat_id, texts.HELP, reply_markup=kb_back_menu())
            return
        if what == "games":
            from keyboards import GAMES_MENU_KB

            await edit_message(self.env, chat_id, message_id, texts.GAMES_MENU,
                               reply_markup=GAMES_MENU_KB)
            return
        if what == "add":
            await add.show_menu(self, chat_id, message_id)
            return
        commands = {
            "study": "/study", "edit": "/edit",
            "delete": "/delete", "settings": "/settings",
        }
        if what in commands:
            await self.handle_command(chat_id, commands[what])

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

        # active dialog (add / search-by-keyword / edit-value / lookup / game)?
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
            if flow == "set_target":
                return await settings.on_target_input(self, chat_id, text)
            if flow in ("lookup_vi", "lookup_example_manual"):
                from handlers import lookup

                return await lookup.on_text_input(self, chat_id, fsm, text)
            if flow == "game_story_count":
                from handlers import games

                return await games.story_on_count(self, chat_id, text)

        # bare English word → dictionary lookup shortcut
        if text.isascii() and text.replace("-", "").replace("'", "").isalpha():
            from handlers import lookup

            return await lookup.start(self, chat_id, text.lower())

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
        elif cmd == "/games":
            from handlers import games

            await games.show_menu(self, chat_id)
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

    def insert_words_bulk(self, user_id: int, entries: list[dict]) -> int:
        """Insert many words (+ a fresh FSRS card each) in constant storage ops.

        One multi-row INSERT ... RETURNING per table (~3N rows written in 2
        calls) instead of the old per-word INSERT + SELECT MAX(id) loop (3N
        round-trips + a full-table MAX scan per word). Safe to combine: each
        rows statement is atomic, and SQLite runs them sequentially.
        """
        if not entries:
            return 0
        now = now_utc().isoformat()
        card_json = fsrs_service.new_card_json()
        cols = ", ".join(f"(?,?,?,?,?,?,?)" for _ in entries)
        flat = [
            v
            for e in entries
            for v in (user_id, e["word"], e["phonetic"], e["meaning"],
                      e["example"], e["note"], now)
        ]
        ids = [r.id for r in self.storage.sql.exec(
            "INSERT INTO words (user_id, word, phonetic, meaning, example, note, created_at)"
            f" VALUES {cols} RETURNING id", *flat,
        )]
        if ids:
            self.storage.sql.exec(
                "INSERT INTO cards (word_id, card_json, due) VALUES "
                + ", ".join("(?,?,?)" for _ in ids),
                *[v for wid in ids for v in (wid, card_json, now)],
            )
        return len(ids)

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
        rows = list(self.storage.sql.exec(
            "SELECT id, word_id, card_json, due FROM cards WHERE due <= ?"
            " ORDER BY due LIMIT 1",
            now_utc().isoformat(),
        ))
        return rows[0] if rows else None

    def _reschedule(self):
        """Next alarm: soon if cards are due, else next future due (delayed past
        quiet hours). Nothing left -> clear the alarm. One indexed query
        (MIN(due) over the due index) instead of two sequential SELECTs."""
        rows = list(self.storage.sql.exec("SELECT MIN(due) AS next_due FROM cards"))
        next_due = rows[0].next_due if rows and rows[0].next_due else None
        if next_due is None:
            self.storage.deleteAlarm()
            return
        if next_due <= now_utc().isoformat():
            self.storage.setAlarm(int(time.time() * 1000) + 60_000)
            return
        nxt = datetime.fromisoformat(next_due)
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
        card_row = self._pick_due_random()
        if card_row is None:
            return  # nothing due, or today's quota spent
        word = self.word_row(card_row.word_id)
        if word is None:
            return
        await review.send_prompt(self, self.env.OWNER_CHAT_ID, card_row, word)

    # ---------- daily target ----------

    def today_local(self) -> str:
        """Local date string (YYYY-MM-DD) using the configured TZ offset."""
        local = now_utc() + timedelta(hours=self._tz_offset())
        return local.strftime("%Y-%m-%d")

    def daily_counts(self) -> tuple[int, int]:
        """(added, reviewed) for today. Creates the row lazily."""
        d = self.today_local()
        rows = list(self.storage.sql.exec(
            "SELECT added, reviewed FROM daily WHERE date = ?", d
        ))
        return (rows[0].added, rows[0].reviewed) if rows else (0, 0)

    def daily_add(self, n: int = 1):
        d = self.today_local()
        self.storage.sql.exec(
            "INSERT INTO daily (date, added, reviewed) VALUES (?, ?, 0)"
            " ON CONFLICT(date) DO UPDATE SET added = added + ?",
            d, n, n,
        )

    def daily_review(self, n: int = 1):
        d = self.today_local()
        self.storage.sql.exec(
            "INSERT INTO daily (date, added, reviewed) VALUES (?, 0, ?)"
            " ON CONFLICT(date) DO UPDATE SET reviewed = reviewed + ?",
            d, n, n,
        )

    def target(self) -> int:
        try:
            return max(1, int(self.setting("daily_target")))
        except ValueError:
            return 200

    def review_quota_left(self) -> int:
        """Review slots left today: target minus words added minus reviews done."""
        added, reviewed = self.daily_counts()
        return max(0, self.target() - added - reviewed)

    def _pick_due_random(self):
        """One random due card within today's remaining review quota."""
        if self.review_quota_left() <= 0:
            return None
        rows = list(self.storage.sql.exec(
            "SELECT id, word_id, card_json, due FROM cards WHERE due <= ?"
            " ORDER BY RANDOM() LIMIT 1",
            now_utc().isoformat(),
        ))
        return rows[0] if rows else None

    # ---------- review session persistence ----------

    def put_session(self, message_id, session: dict):
        self.storage.kv.put(f"session:{message_id}", json.dumps(session))

    def get_session(self, message_id):
        raw = self.storage.kv.get(f"session:{message_id}")
        return json.loads(raw) if raw else None

    def pop_session(self, message_id):
        self.storage.kv.delete(f"session:{message_id}")
