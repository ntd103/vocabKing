"""Integration-test fixtures: stub the Cloudflare `workers` module so the DO
code can run under plain pytest, with an in-memory SQLite DO-storage fake.
"""

import sqlite3
import sys
import time
import types

import pytest

# The worker code imports top-level names (handlers, services, telegram, ...)
# because wrangler bundles src/ as the root. Alias those names to the src.*
# modules so tests can import either way.
sys.path.insert(0, ".")
sys.path.insert(0, "src")


class _StubResponse:
    def __init__(self, body="", status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {}


class _StubDO:
    """Minimal base class matching workers.DurableObject's surface."""
    def __init__(self, ctx, env):
        self.ctx = ctx
        self.env = env


def _install_workers_stub():
    mod = types.ModuleType("workers")
    mod.WorkerEntrypoint = type("WorkerEntrypoint", (), {})
    mod.DurableObject = _StubDO
    mod.Response = _StubResponse

    async def _fetch(*args, **kwargs):
        raise RuntimeError("network fetch not available in unit tests")

    mod.fetch = _fetch
    sys.modules.setdefault("workers", mod)
    return mod


class _Cur:
    """Cursor over sqlite3 results mimicking DO storage SQL API."""

    def __init__(self, conn, sql, args):
        self._conn = conn
        self._sql = sql
        self._args = args
        self._rows: list[dict] = []
        self.last_insert_rowid = 0
        self._execute()

    def _execute(self):
        statements = [s.strip() for s in self._sql.split(";") if s.strip()]
        cur = None
        wrote = False
        for stmt in statements:
            cur = self._conn.execute(stmt, self._args)
            if stmt.upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP")):
                wrote = True
                self.last_insert_rowid = cur.lastrowid or 0
        if wrote:
            self._conn.commit()
            self._rows = []
            return
        cols = [d[0] for d in cur.description or []]
        raw = cur.fetchall()

        class Row:
            def __init__(self, d):
                self.__dict__.update(d)

            def __getitem__(self, k):
                return self.__dict__[k]

        self._rows = [Row(dict(zip(cols, r))) for r in raw]

    def one(self):
        if len(self._rows) != 1:
            raise RuntimeError(f"expected 1 row, got {len(self._rows)}")
        return self._rows[0]

    def __iter__(self):
        return iter(self._rows)


class _SQL:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")

    def exec(self, sql, *args):
        return _Cur(self.conn, sql, args)


class _KV:
    def __init__(self):
        self.data: dict = {}
        self.alarm: int | None = None

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)

    def getAlarm(self):
        return self.alarm

    def setAlarm(self, ts_ms):
        self.alarm = ts_ms

    def deleteAlarm(self):
        self.alarm = None


class _Storage(_KV):
    """DO storage surface: sync KV via .kv, SQL via .sql, alarms sync."""
    def __init__(self):
        super().__init__()
        self.kv = self
        self.sql = _SQL()


class _Ctx:
    def __init__(self):
        self.storage = _Storage()


class FakeEnv:
    """Env vars + capture of outgoing Telegram calls."""

    def __init__(self):
        self.BOT_TOKEN = "test:token"
        self.WEBHOOK_SECRET = "s3cr3t"
        self.OWNER_ID = "111"
        self.OWNER_CHAT_ID = "111"
        self.OWNER_CHAT_ID = "111"
        self.TZ_OFFSET_HOURS = "7"
        self.sent: list[dict] = []  # captured sendMessage/editMessageText payloads


def _patch_telegram_fetch(env: FakeEnv):
    """Route telegram.tg_call through capture instead of network."""
    import telegram as tg

    async def fake_fetch(url, method=None, headers=None, body=None):
        import json

        payload = json.loads(body)
        m = url.split("/bot")[1].split("/")[1]
        result = {}
        if m == "sendMessage":
            result = {"message_id": 1000 + len(env.sent), "chat": {"id": payload["chat_id"]}}
        env.sent.append({"method": m, "payload": payload, "result": dict(result)})
        async def _json():
            return {"ok": True, "result": result}

        return types.SimpleNamespace(status=200, json=_json)

    tg.fetch = fake_fetch


class _AsyncJson:
    def __init__(self, data):
        self.data = data

    async def json(self):
        return self.data


def _async_result(data):
    return data


class _Req:
    def __init__(self, data):
        self._data = data

    async def json(self):
        return self._data


@pytest.fixture
def do():
    """A VocabularyDO instance with fakes, Telegram calls captured."""
    _install_workers_stub()
    from src.vocab_do import VocabularyDO

    env = FakeEnv()
    _patch_telegram_fetch(env)
    ctx = _Ctx()
    instance = VocabularyDO(ctx, env)
    return instance


def make_update_msg(text, chat_id=111, user_id=111, reply_to=None):
    msg = {"chat": {"id": chat_id}, "from": {"id": user_id}, "text": text}
    if reply_to:
        msg["reply_to_message"] = {"message_id": reply_to}
    return {"message": msg}


def make_update_cb(data, chat_id=111, user_id=111, message_id=500):
    return {
        "callback_query": {
            "id": "cb1",
            "data": data,
            "from": {"id": user_id},
            "message": {"chat": {"id": chat_id}, "message_id": message_id},
        }
    }


def sent_texts(env):
    return [s["payload"].get("text", "") for s in env.sent]


def last_message_id(env):
    ids = [
        s["payload"]["message_id"]
        for s in env.sent
        if "message_id" in s["payload"]
    ]
    return ids[-1] if ids else None


TIME = time
