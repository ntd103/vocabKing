"""VocabularyDO — the stateful heart of Vocaboss.

One Durable Object instance (SQLite storage) owns all bot state:
words, FSRS cards, review sessions, settings, FSM dialogs — plus the alarm
that fires reminders 24/7 on Cloudflare's free plan.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from workers import DurableObject, Response

import texts
from keyboards import MENU_KB
from handlers import add, delete, edit, review, settings
from services import fsrs_service
from telegram import answer_callback, send_message

IDLE_TIMEOUT_SEC = 15

SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  word TEXT NOT NULL,
  phonetic TEXT,
  pos TEXT,
  define_en TEXT,       -- English definition
  meaning TEXT,          -- Vietnamese meaning
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
        if not self.storage.kv.get("schema:v3"):
            self.storage.sql.exec(SCHEMA)
            columns = {r.name for r in self.storage.sql.exec("PRAGMA table_info(words)")}
            if "define_en" not in columns:
                self.storage.sql.exec("ALTER TABLE words ADD COLUMN define_en TEXT")
            if "pos" not in columns:
                self.storage.sql.exec("ALTER TABLE words ADD COLUMN pos TEXT")
            for k, v in DEFAULTS.items():
                if self.storage.kv.get(f"set:{k}") is None:
                    self.storage.kv.put(f"set:{k}", v)
            self.storage.kv.put("schema:v3", "1")
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
                if cb.get("data", "").startswith("io:"):
                    chat = cb.get("message", {}).get("chat", {})
                    if (chat.get("type") != "private"
                            or str(chat.get("id")) != str(self.env.OWNER_CHAT_ID or "")):
                        return
                return await self.on_callback(cb)
            msg = update.get("message")
            if msg:
                if str(msg.get("from", {}).get("id")) != owner:
                    return
                if msg.get("document") or msg.get("text", "").strip().lower().split(" ", 1)[0].split("@", 1)[0] in ("/import", "/export"):
                    chat = msg.get("chat", {})
                    if (chat.get("type") != "private"
                            or str(chat.get("id")) != str(self.env.OWNER_CHAT_ID or "")):
                        return
                return await self.on_message(msg)
        except Exception as e:  # never let Telegram retry-loop on our bugs
            print("handle_update error:", repr(e))

    async def on_callback(self, cb: dict):
        data = cb.get("data", "")
        chat_id = cb["message"]["chat"]["id"]
        message_id = cb["message"]["message_id"]
        results = await asyncio.gather(
            answer_callback(self.env, cb["id"]),
            self._dispatch_callback(cb, chat_id, message_id, data),
            return_exceptions=True,
        )
        if isinstance(results[1], BaseException):
            raise results[1]

    async def _dispatch_callback(self, cb: dict, chat_id, message_id, data: str):
        parts = data.split(":")
        fsm = self.storage.kv.get(f"fsm:{chat_id}") or {}
        if add.is_add_flow(fsm.get("flow")):
            allowed = data.startswith("add:") or data == "menu:home"
            if not allowed:
                await send_message(self.env, chat_id, texts.ADD_BUSY)
                return

        if parts[0] == "rate" and len(parts) == 3:
            await review.rate(self, chat_id, message_id, int(parts[1]), parts[2])
        elif parts[0] == "hint" and len(parts) == 2:
            session = self.get_session(message_id)
            if session and session["card_id"] == int(parts[1]):
                await review.on_reply(self, chat_id, message_id, "?")
        elif parts[0] == "show" and len(parts) == 2:
            await review.show_answer(self, chat_id, message_id, int(parts[1]))
        elif parts[0] == "add" and parts[1] in ("confirm", "cancel"):
            await add.on_confirm(self, chat_id, message_id, parts[1])
        elif parts[0] == "add" and parts[1] in ("en_ok", "en_manual"):
            await add.on_en_choice(
                self, chat_id, message_id, "ok" if parts[1] == "en_ok" else "manual",
            )
        elif parts[0] == "menu":
            await self.on_menu(chat_id, parts[1], message_id)
        elif parts[0] == "vact" and len(parts) == 2:
            from handlers import vocab_list
            await vocab_list.select_action(self, chat_id,
                                           "vocab" if parts[1] == "view" else parts[1], message_id)
        elif parts[0] == "game" and parts[1] == "story":
            from handlers import games

            await games.story_ask_count(self, chat_id, message_id)
        elif data == "edit:cancel":
            await edit.cancel(self, chat_id, message_id=message_id)
        elif parts[0] == "io" and len(parts) == 2:
            from handlers import import_export
            if parts[1] in ("export", "csv", "json"):
                await import_export.export_words(self, chat_id, parts[1])
            elif parts[1] == "import":
                await import_export.start_import(self, chat_id, message_id)
            elif parts[1] in ("confirm", "cancel"):
                await import_export.on_confirm(self, chat_id, parts[1], message_id)
        elif parts[0] == "editf" and len(parts) == 3:
            await edit.pick_field(self, chat_id, int(parts[1]), parts[2], message_id=message_id)
        elif parts[0] == "editfill" and len(parts) == 2:
            await edit.fill_missing(self, chat_id, int(parts[1]), message_id=message_id)
        elif parts[0] == "del" and parts[1] == "all":
            await delete.confirm_all_prompt(self, chat_id, message_id=message_id)
        elif parts[0] == "delall" and parts[1] == "confirm":
            await delete.confirm_all(self, chat_id, message_id=message_id)
        elif parts[0] == "delall" and parts[1] == "cancel":
            await delete.cancel_all(self, chat_id, message_id=message_id)
        elif parts[0] == "del" and parts[1] == "confirm" and len(parts) == 3:
            await delete.confirm(self, chat_id, int(parts[2]), message_id=message_id)
        elif parts[0] == "del" and parts[1] == "cancel":
            await delete.cancel(self, chat_id, message_id=message_id)
        elif parts[0] == "mode" and len(parts) == 2:
            await settings.set_mode(self, chat_id, message_id, parts[1])
        elif parts[0] == "quiet" and len(parts) >= 2:
            await settings.set_quiet(self, chat_id, message_id, ":".join(parts[1:]))
        elif parts[0] == "set" and len(parts) == 2:
            await settings.show_section(self, chat_id, message_id, parts[1])
        elif parts[0] == "remmode" and len(parts) == 2:
            await settings.set_reminder_mode(self, chat_id, message_id, parts[1])
        elif parts[0] == "vpg" and len(parts) == 2:
            from handlers import vocab_list

            await vocab_list.show_page(self, chat_id, int(parts[1]), message_id)
        elif parts[0] == "vsrch":
            from handlers import vocab_list

            await vocab_list.start_search(self, chat_id, message_id)
        elif parts[0] == "vclr":
            from handlers import vocab_list

            await vocab_list.clear_filter(self, chat_id, message_id)
        elif parts[0] in ("vedit", "vdel") and len(parts) == 2:
            state = self.storage.kv.get(f"fsm:{chat_id}") or {}
            self.set_fsm(chat_id, {
                **state, "return_action": "vocab", "from_table": True, "message_id": message_id,
            })
            target = edit if parts[0] == "vedit" else delete
            await target.pick_word(self, chat_id, int(parts[1]), message_id=message_id)

    async def on_menu(self, chat_id, what: str, message_id=None):
        from telegram import edit_message

        if what == "home":
            self.set_fsm(chat_id, None)
            if message_id:
                await edit_message(self.env, chat_id, message_id, texts.MENU, reply_markup=MENU_KB)
            else:
                await send_message(self.env, chat_id, texts.MENU, reply_markup=MENU_KB)
            return
        if what == "help":
            from keyboards import kb_back_menu

            self.set_fsm(chat_id, None)
            if message_id:
                await edit_message(self.env, chat_id, message_id, texts.HELP,
                                   reply_markup=kb_back_menu())
            else:
                await send_message(self.env, chat_id, texts.HELP, reply_markup=kb_back_menu())
            return
        if what == "games":
            from handlers import games

            return await games.show_menu(self, chat_id, message_id)
        if what == "settings":
            return await settings.show(self, chat_id, message_id)
        if what == "import_export":
            from handlers import import_export
            return await import_export.show_menu(self, chat_id, message_id)
        if what == "add":
            self.set_fsm(chat_id, None)
            await add.start(self, chat_id, "", message_id=message_id)
            return
        if what == "vocab":
            from handlers import vocab_list

            return await vocab_list.show_menu(self, chat_id, message_id)
        if what in ("edit", "delete"):
            handler = edit if what == "edit" else delete
            return await handler.start(self, chat_id, "", message_id=message_id)
        commands = {
            "study": "/study", "edit": "/edit",
            "delete": "/delete", "settings": "/settings",
            "vocab": "/vocab",
        }
        if what in commands:
            await self.handle_command(chat_id, commands[what])

    async def on_message(self, msg: dict):
        chat_id = msg["chat"]["id"]
        if msg.get("document"):
            from handlers import import_export
            return await import_export.on_document(self, chat_id, msg)
        text = (msg.get("text") or "").strip()
        if not text:
            return

        if text.startswith("/"):
            return await self.handle_command(chat_id, text)

        # reply to a review prompt?
        reply_to = msg.get("reply_to_message", {}).get("message_id")
        if reply_to and await review.on_reply(self, chat_id, reply_to, text):
            return
        if reply_to and text in ("1", "2", "3", "4"):
            return

        # Bare text goes to a pending quiz only when no dialog is waiting.
        fsm = self.storage.kv.get(f"fsm:{chat_id}")
        pending = self.storage.kv.get("review:pending") if not reply_to and not fsm else None
        if pending and pending.get("message_id") and pending.get("chat_id") == str(chat_id):
            if await review.on_reply(self, chat_id, pending["message_id"], text):
                return

        # active dialog (add / search / edit / import / game)?
        if fsm:
            flow = fsm.get("flow")
            if add.is_add_flow(flow):
                return await add.on_input(self, chat_id, text)
            if flow in ("vocab_search", "edit_search", "delete_search"):
                from handlers import vocab_list

                return await vocab_list.on_search_input(self, chat_id, text)
            if flow in ("vocab_select", "edit_select", "delete_select"):
                from handlers import vocab_list
                return await vocab_list.select_word(self, chat_id, text, fsm.get("message_id"))
            if flow == "edit_value":
                return await edit.on_value(self, chat_id, fsm, text)
            if flow == "set_target":
                await settings.clean_input(self, chat_id, msg.get("message_id"))
                return await settings.on_target_input(self, chat_id, text)
            if flow in ("set_quiet_start", "set_quiet_end"):
                await settings.clean_input(self, chat_id, msg.get("message_id"))
                return await settings.on_quiet_input(self, chat_id, fsm, text)
            if flow == "import_input":
                from handlers import import_export

                return await import_export.on_import_input(self, chat_id, text)
            if flow == "game_story_count":
                from handlers import games

                return await games.story_on_count(self, chat_id, text)

        await send_message(self.env, chat_id, texts.HINT_ROOT)

    # ---------- commands ----------

    async def handle_command(self, chat_id, raw: str):
        cmd, _, arg = raw.partition(" ")
        cmd = cmd.split("@")[0].lower()  # strip /cmd@botname
        fsm = self.storage.kv.get(f"fsm:{chat_id}") or {}
        if add.is_add_flow(fsm.get("flow")) and cmd not in ("/cancel", "/add"):
            await send_message(self.env, chat_id, texts.ADD_BUSY)
            return
        if cmd in ("/start", "/menu"):
            await self.on_menu(chat_id, "home")
        elif cmd == "/help":
            await send_message(self.env, chat_id, texts.HELP)
        elif cmd == "/add":
            self.set_fsm(chat_id, None)
            await add.start(self, chat_id, arg.strip())
        elif cmd == "/study":
            await review.start_study(self, chat_id)
        elif cmd == "/edit":
            self.set_fsm(chat_id, None)
            await edit.start(self, chat_id, arg.strip())
        elif cmd == "/delete":
            self.set_fsm(chat_id, None)
            await delete.start(self, chat_id, arg.strip())
        elif cmd == "/settings":
            await settings.show(self, chat_id)
        elif cmd == "/games":
            from handlers import games

            await games.show_menu(self, chat_id)
        elif cmd == "/vocab":
            from handlers import vocab_list

            self.set_fsm(chat_id, None)
            await vocab_list.show_menu(self, chat_id)
        elif cmd == "/import":
            from handlers import import_export

            self.set_fsm(chat_id, None)
            await import_export.start_import(self, chat_id)
        elif cmd == "/export":
            from handlers import import_export

            await import_export.export_words(self, chat_id, arg.strip().lower())
        elif cmd == "/cancel":
            state = self.storage.kv.get(f"fsm:{chat_id}") or {}
            if state.get("flow", "").startswith("edit"):
                return await edit.cancel(self, chat_id)
            if state.get("flow", "").startswith("delete"):
                return await delete.cancel(self, chat_id)
            from handlers.vocab_list import finish
            await finish(self, chat_id, "Action cancelled.", state.get("message_id"))
        else:
            await send_message(self.env, chat_id, texts.HINT_ROOT)

    # ---------- fsm helpers ----------

    def set_fsm(self, chat_id, state: dict | None):
        if state is None:
            self.storage.kv.delete(f"fsm:{chat_id}")
        elif add.is_add_flow(state.get("flow")):
            # Keep the format prompt visible — no idle timeout while adding.
            cleaned = {k: v for k, v in state.items() if k != "expires_at"}
            self.storage.kv.put(f"fsm:{chat_id}", cleaned)
        else:
            expires = (now_utc() + timedelta(seconds=IDLE_TIMEOUT_SEC)).isoformat()
            self.storage.kv.put(f"fsm:{chat_id}", {**state, "expires_at": expires})
        self._reschedule()

    async def _expire_fsm(self, chat_id, fsm: dict):
        """Clear an idle dialog and edit its message; never touches review:pending."""
        mid = fsm.get("message_id")
        self.storage.kv.delete(f"fsm:{chat_id}")
        if mid:
            from telegram import edit_message
            from keyboards import kb_back_menu

            await edit_message(
                self.env, chat_id, mid, texts.IDLE_TIMEOUT, reply_markup=kb_back_menu(),
            )

    def _owner_fsm(self):
        return self.storage.kv.get(f"fsm:{self.env.OWNER_CHAT_ID}")

    def _fsm_expires_at(self, fsm: dict | None) -> datetime | None:
        if not fsm or not fsm.get("expires_at"):
            return None
        return datetime.fromisoformat(fsm["expires_at"])

    # ---------- words / cards helpers ----------

    def insert_words_bulk(self, user_id: int, entries: list[dict]) -> int:
        """Insert many words (+ a fresh FSRS card each) atomically."""
        if not entries:
            return 0
        created = self._now()
        now = created.isoformat()
        card_json = fsrs_service.new_card_json(created)
        due = fsrs_service.due_from_json(card_json)
        # SQLite-backed DO statements accept at most 100 bindings. Keep all
        # chunks in the same transaction so a later error rolls back the batch.
        def insert():
            for start in range(0, len(entries), 11):
                chunk = entries[start:start + 11]
                flat = [value for entry in chunk for value in (
                    user_id, entry["word"], entry.get("phonetic"), entry.get("define_en"),
                    entry.get("meaning"), entry.get("example"), entry.get("note"), entry.get("pos"), now,
                )]
                ids = [r.id for r in self.storage.sql.exec(
                    "INSERT INTO words (user_id,word,phonetic,define_en,meaning,example,note,pos,created_at) VALUES "
                    + ", ".join("(?,?,?,?,?,?,?,?,?)" for _ in chunk) + " RETURNING id", *flat,
                )]
                self.storage.sql.exec(
                    "INSERT INTO cards (word_id, card_json, due) VALUES "
                    + ", ".join("(?,?,?)" for _ in ids),
                    *[v for wid in ids for v in (wid, card_json, due)],
                )
            return len(entries)

        return self.storage.transactionSync(insert)

    def count_words(self) -> int:
        rows = list(self.storage.sql.exec("SELECT COUNT(*) AS n FROM words"))
        return rows[0].n if rows else 0

    def word_row(self, word_id: int):
        rows = list(self.storage.sql.exec(
            "SELECT id, word, phonetic, define_en, meaning, example, note, pos FROM words WHERE id = ?",
            word_id,
        ))
        return rows[0] if rows else None

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

    # ---------- alarms (the 24/7 reminder engine) ----------

    def _reschedule(self):
        """Wake for idle FSM expiry and/or next due card. Pending review waits forever."""
        if self.storage.kv.get("review:pending"):
            self.storage.deleteAlarm()
            return
        now = now_utc()
        wakes: list[datetime] = []
        fsm = self._owner_fsm()
        expires = self._fsm_expires_at(fsm)
        if expires is not None:
            wakes.append(expires)

        # Defer review alarms while a dialog is open; idle expiry will reopen the slot.
        if fsm is None:
            rows = list(self.storage.sql.exec("SELECT MIN(due) AS next_due FROM cards"))
            next_due = rows[0].next_due if rows and rows[0].next_due else None
            if next_due is not None:
                nxt = max(datetime.fromisoformat(next_due), now + timedelta(seconds=1))
                if self.review_quota_left() <= 0:
                    local = now + timedelta(hours=self._tz_offset())
                    midnight = (local + timedelta(days=1)).replace(
                        hour=0, minute=0, second=0, microsecond=0,
                    )
                    nxt = max(nxt, midnight - timedelta(hours=self._tz_offset()))
                wakes.append(self.wake_time(nxt))

        if not wakes:
            self.storage.deleteAlarm()
            return
        self.storage.setAlarm(int(min(wakes).timestamp() * 1000))

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
        owner = self.env.OWNER_CHAT_ID
        fsm = self._owner_fsm()
        expires = self._fsm_expires_at(fsm)
        if fsm and expires is not None and expires <= now:
            await self._expire_fsm(owner, fsm)
            fsm = None

        if self.storage.kv.get("review:pending"):
            return
        if fsm is not None:
            return  # do not inject a quiz into an active dialog
        if self.is_quiet(now):
            return  # _reschedule() sets the wake-up alarm
        card_row = self._pick_due_random()
        if card_row is None:
            return  # nothing due, or today's quota spent
        word = self.word_row(card_row.word_id)
        if word is None:
            return
        await review.send_prompt(self, owner, card_row, word)

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
