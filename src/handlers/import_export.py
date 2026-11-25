"""Owner-only vocabulary backup and confirmed CSV/JSON imports."""

import csv
import io
import json
from datetime import timedelta

import texts
from handlers.vocab_list import display, finish
from keyboards import kb
from telegram import send_message, read_document, send_document

MAX_BYTES = 512 * 1024
MAX_ROWS = 2000
FIELDS = ("word", "phonetic", "define_en", "meaning", "example", "note", "pos")
REQUIRED = ("word", "define_en", "meaning")


def parse_records(source):
    if len(source.encode("utf-8")) > MAX_BYTES:
        raise ValueError("File exceeds 512 KiB.")
    source = source.lstrip("\ufeff").strip()
    try:
        if source.startswith("["):
            records = json.loads(source)
        elif source.startswith("{"):
            try:
                records = [json.loads(source)]
            except json.JSONDecodeError:
                records = [json.loads(line) for line in source.splitlines() if line.strip()]
        else:
            records = csv.DictReader(io.StringIO(source, newline=""), strict=True)
            cols = records.fieldnames or []
            if len(cols) != len(set(cols)) or not set(REQUIRED) <= set(cols) <= set(FIELDS):
                raise ValueError("Invalid CSV header.")
        result = []
        for index, row in enumerate(records, 1):
            if index > MAX_ROWS:
                raise ValueError("Import up to 2000 words at once.")
            if (not isinstance(row, dict) or set(row) - set(FIELDS)
                    or any(v is not None and not isinstance(v, str) for v in row.values())
                    or any(not (row.get(f) or "").strip() for f in REQUIRED)):
                raise ValueError(f"Check the fields in record {index}.")
            result.append({f: (row.get(f) or "") for f in FIELDS})
            result[-1]["word"] = result[-1]["word"].strip()
    except (json.JSONDecodeError, csv.Error, RecursionError) as exc:
        raise ValueError("Invalid CSV or JSON.") from exc
    if not result:
        raise ValueError("No words found.")
    return result


IMPORT_CANCEL_KB = kb([[("◀️ Import / Export", "menu:import_export"), ("🏠 Menu", "menu:home")]])


async def show_menu(do, chat_id, message_id=None):
    do.set_fsm(chat_id, {"flow": "import_export_menu", "message_id": message_id})
    await display(do, chat_id, texts.IMPORT_EXPORT_MENU, kb([
        [("📤 Export CSV", "io:csv"), ("📤 Export JSON", "io:json")],
        [("📥 Import", "io:import")],
        [("🏠 Menu", "menu:home")],
    ]), message_id)


async def start_import(do, chat_id, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    message_id = message_id or state.get("message_id")
    do.set_fsm(chat_id, {"flow": "import_input", "message_id": message_id})
    await display(do, chat_id, "Reply to this message with a UTF-8 CSV or JSON file (up to 512 KiB), or paste the data here.", IMPORT_CANCEL_KB, message_id)


async def on_import_input(do, chat_id, source, *, file=False):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    try:
        if not file and len(source) > 4096:
            raise ValueError("Paste up to 4096 characters or attach a file.")
        rows = parse_records(source)
    except ValueError as exc:
        await display(do, chat_id, f"{texts.IMPORT_INVALID}\n{exc}", IMPORT_CANCEL_KB, state.get("message_id"))
        return
    do.set_fsm(chat_id, {"flow": "import_confirm", "entries": rows,
                         "message_id": state.get("message_id")})
    await display(do, chat_id, texts.IMPORT_CONFIRM.format(count=len(rows)), kb([
        [("✅ Import", "io:confirm"), ("❌ Cancel", "io:cancel")],
    ]), state.get("message_id"))


async def on_confirm(do, chat_id, action, mid):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    message_id = state.get("message_id")
    if state.get("flow") != "import_confirm" or message_id != mid:
        return
    if action != "confirm":
        return await finish(do, chat_id, texts.IMPORT_CANCELLED, message_id)
    count = do.insert_words_bulk(int(do.env.OWNER_ID), state["entries"])
    do.daily_add(count)
    do._reschedule()
    await finish(do, chat_id, texts.IMPORT_DONE.format(count=count), message_id)


async def on_document(do, chat_id, msg):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    if state.get("flow") != "import_input":
        return
    mid = state.get("message_id")
    if not mid or msg.get("reply_to_message", {}).get("message_id") != mid:
        await display(do, chat_id, "Reply to this message with the file.", IMPORT_CANCEL_KB, mid)
        return
    try:
        source = await read_document(do.env, msg["document"], MAX_BYTES)
    except ValueError as exc:
        await display(do, chat_id, str(exc), IMPORT_CANCEL_KB, mid)
        return
    if do.storage.kv.get(f"fsm:{chat_id}") == state:
        await on_import_input(do, chat_id, source, file=True)


async def export_words(do, chat_id, fmt="json"):
    if fmt not in ("json", "csv"):
        await send_message(do.env, chat_id, "Choose CSV or JSON.", reply_markup=kb([
            [("📤 CSV", "io:csv"), ("📤 JSON", "io:json")]]))
        return
    rows = do.storage.sql.exec("SELECT " + ", ".join(FIELDS) + " FROM words ORDER BY id")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    if fmt == "csv":
        writer.writeheader()
    else:
        stream.write("[")
    count = 0
    for row in rows:
        values = {field: row[field] or "" for field in FIELDS}
        if fmt == "csv":
            writer.writerow(values)
        else:
            if count:
                stream.write(",\n")
            stream.write(json.dumps(values, ensure_ascii=False))
        count += 1
        if stream.tell() > MAX_BYTES or count > MAX_ROWS:
            break
    if not count:
        return await send_message(do.env, chat_id, texts.EXPORT_EMPTY)
    if fmt == "json":
        stream.write("]")
    content = stream.getvalue()
    if len(content.encode("utf-8")) > MAX_BYTES or count > MAX_ROWS:
        return await send_message(do.env, chat_id, "Export exceeds the file limit (512 KiB or 2000 words).")
    timestamp = do._now() + timedelta(hours=do._tz_offset())
    filename = f"export_{timestamp:%Y-%m-%d_%H-%M}.{fmt}"
    if not await send_document(do.env, chat_id, filename, content, "text/csv" if fmt == "csv" else "application/json"):
        await send_message(do.env, chat_id, "Could not send the file. Try exporting again.")
