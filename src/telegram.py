"""Telegram Bot API client — thin async wrappers over global fetch.

No framework: the bot is single-user, so plain Bot API calls are enough.
"""

import json

from workers import fetch

API_BASE = "https://api.telegram.org/bot{token}/{method}"

# Local-testing override: set TG_API_BASE (e.g. "http://127.0.0.1:9999" in
# .dev.vars) to redirect all Bot API calls to a mock server. Absent/empty in
# production.


async def tg_call(env, method: str, payload: dict) -> dict:
    """Call a Bot API method; returns the parsed Telegram response."""
    base = getattr(env, "TG_API_BASE", "")
    url = (base.rstrip("/") if base else "https://api.telegram.org") + (
        "/bot{token}/{method}".format(token=env.BOT_TOKEN, method=method)
    )
    res = await fetch(
        url,
        method="POST",
        headers={"Content-Type": "application/json"},
        body=json.dumps(payload),
    )
    try:
        data = await res.json()
    except Exception:
        return {"ok": False, "description": f"non-json response ({res.status})"}
    return data if isinstance(data, dict) else {"ok": False, "description": "bad payload"}


async def send_message(env, chat_id, text, reply_markup=None, reply_to=None) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = {"inline_keyboard": reply_markup}
    if reply_to is not None:
        payload["reply_parameters"] = {"message_id": reply_to}
    return await tg_call(env, "sendMessage", payload)


async def edit_message(env, chat_id, message_id, text, reply_markup=None) -> dict:
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = {"inline_keyboard": reply_markup}
    return await tg_call(env, "editMessageText", payload)


async def answer_callback(env, callback_query_id, text=None) -> dict:
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return await tg_call(env, "answerCallbackQuery", payload)


def kb(rows: list[list[tuple[str, str]]]) -> list[list[dict]]:
    """Build an inline keyboard from (label, callback_data) tuples."""
    return [[{"text": t, "callback_data": d} for t, d in row] for row in rows]


__all__ = ["tg_call", "send_message", "edit_message", "answer_callback", "kb"]
