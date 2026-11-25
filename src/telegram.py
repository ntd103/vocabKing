"""Telegram Bot API client — thin async wrappers over global fetch.

No framework: the bot is single-user, so plain Bot API calls are enough.
"""

import json
import re

from workers import fetch

API_BASE = "https://api.telegram.org/bot{token}/{method}"
_MD_SPECIAL = re.compile(r"([\\_*|~`\[\]()<>&=$!])")
_WS = re.compile(r"[\r\n\t]+")
_ALIGN_SPEC = {"left": ":---", "center": ":---:", "right": "---:"}

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


def _multipart_document(chat_id, filename: str, content: bytes, mime: str) -> tuple[bytes, str]:
    """Build multipart/form-data without Workers FormData/File FFI (unreliable on Pyodide)."""
    import secrets

    boundary = "vocabking" + secrets.token_hex(16)
    disposition = (
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    )
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode(),
        f"--{boundary}\r\n{disposition}".encode() + content + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


async def send_document(env, chat_id, filename, content, mime) -> bool:
    """Upload a UTF-8 text/CSV/JSON file via Telegram sendDocument."""
    raw = content.encode("utf-8") if isinstance(content, str) else content
    body, content_type = _multipart_document(chat_id, filename, raw, mime)
    base = (getattr(env, "TG_API_BASE", "") or "https://api.telegram.org").rstrip("/")
    try:
        res = await fetch(
            f"{base}/bot{env.BOT_TOKEN}/sendDocument",
            method="POST",
            headers={"Content-Type": content_type},
            body=body,
        )
        data = await res.json()
        return isinstance(data, dict) and bool(data.get("ok"))
    except Exception:
        return False  # Never log URLs containing the bot credential.


async def read_document(env, document, limit):
    try:
        if not document.get("file_id") or document.get("file_size", 0) > limit:
            raise ValueError
        info = (await tg_call(env, "getFile", {"file_id": document["file_id"]})).get("result", {})
        path = info.get("file_path", "")
        if not re.fullmatch(r"(?:[\w-]+/)*[\w-]+\.[\w-]+", path) or not 0 < info.get("file_size", 0) <= limit:
            raise ValueError
        base = (getattr(env, "TG_API_BASE", "") or "https://api.telegram.org").rstrip("/")
        res = await fetch(f"{base}/file/bot{env.BOT_TOKEN}/{path}", redirect="error")
        if res.status != 200:
            raise ValueError
        raw = await res.bytes()
        if len(raw) > limit:
            raise ValueError
        return raw.decode("utf-8-sig")
    except Exception:
        raise ValueError("Could not read this file. Check the size and UTF-8 encoding.") from None


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


async def send_rich_message(env, chat_id, markdown: str, reply_markup=None) -> dict:
    payload = {
        "chat_id": chat_id,
        "rich_message": {"markdown": markdown, "skip_entity_detection": True},
    }
    if reply_markup is not None:
        payload["reply_markup"] = {"inline_keyboard": reply_markup}
    return await tg_call(env, "sendRichMessage", payload)


async def edit_message(env, chat_id, message_id, text: str | None = None, reply_markup=None, *, markdown: str | None = None) -> dict:
    if markdown is not None:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "rich_message": {"markdown": markdown, "skip_entity_detection": True},
        }
    else:
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


def md_escape(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", str(text))


def md_cell(text: str | None, limit: int = 36) -> str:
    cleaned = _WS.sub(" ", str(text or "")).strip()
    if not cleaned:
        return "—"
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1] + "…"
    return md_escape(cleaned)


def md_table(
    headers: list[str],
    rows: list[list[str]],
    aligns: list[str] | None = None,
    limits: list[int] | None = None,
) -> str:
    cols = len(headers)
    align_row = [_ALIGN_SPEC.get(aligns[i] if aligns and i < len(aligns) else "left", ":---") for i in range(cols)]
    lines = [
        "| " + " | ".join(md_escape(h) for h in headers) + " |",
        "|" + "|".join(align_row) + "|",
    ]
    for row in rows:
        cells = [md_cell(row[i] if i < len(row) else None, limits[i] if limits and i < len(limits) else 36) for i in range(cols)]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


async def answer_callback(env, callback_query_id, text=None) -> dict:
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    return await tg_call(env, "answerCallbackQuery", payload)


def kb(rows: list[list[tuple[str, str]]]) -> list[list[dict]]:
    """Build an inline keyboard from (label, callback_data) tuples."""
    return [[{"text": t, "callback_data": d} for t, d in row] for row in rows]


__all__ = [
    "tg_call", "send_message", "send_rich_message", "edit_message",
    "answer_callback", "kb", "md_escape", "md_cell", "md_table",
]
