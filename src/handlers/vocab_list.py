"""Shared paginated Markdown vocabulary tables and word details (CRUD Mode B)."""

from datetime import datetime, timezone
from html import escape

import texts
from telegram import edit_message, kb, md_cell, md_table, send_message, send_rich_message

PAGE_SIZE = 10
CELL_LIMITS = [6, 24, 18, 36, 12]
CELL_ALIGNS = ["right", "left", "left", "left", "left"]
ACTION_VERBS = {"vocab": "view details", "edit": "edit", "delete": "delete"}


def _md_notice(notice: str) -> str:
    rendered = md_cell(notice, 240)
    if rendered.startswith(("#", "-", ">")):
        return "\\" + rendered
    return rendered


def _due_human(due_iso: str | None, now_iso: str) -> str:
    if not due_iso:
        return "—"
    delta = (datetime.fromisoformat(due_iso) - datetime.fromisoformat(now_iso)).total_seconds()
    if delta <= 0:
        return "due"
    if delta < 3600:
        return f"{int(delta // 60)}m"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    days = int(delta // 86400)
    return f"{days // 365}y" if days > 365 else f"{days}d"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _filter_sql(query: str, exact_word: str = "") -> tuple[str, tuple]:
    clauses: list[str] = []
    params: list = []
    if query:
        if query.isascii() and query.isdigit() and len(query) <= 18:
            clauses.append("stt = ?")
            params.append(int(query))
        else:
            pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            clauses.append("(word LIKE ? ESCAPE '\\' OR meaning LIKE ? ESCAPE '\\')")
            params.extend([pattern, pattern])
    if exact_word:
        clauses.append("word = ? COLLATE NOCASE")
        params.append(exact_word)
    if not clauses:
        return "", ()
    return " WHERE " + " AND ".join(clauses), tuple(params)


async def display(do, chat_id, body: str, markup, message_id=None, *, rich: bool = False):
    """Reuse the workflow message and retain its ID for text-input steps."""
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    message_id = message_id or state.get("message_id")
    if message_id:
        if rich:
            await edit_message(do.env, chat_id, message_id, reply_markup=markup, markdown=body)
        else:
            await edit_message(do.env, chat_id, message_id, body, reply_markup=markup)
    else:
        if rich:
            result = await send_rich_message(do.env, chat_id, body, reply_markup=markup)
        else:
            result = await send_message(do.env, chat_id, body, reply_markup=markup)
        message_id = result.get("result", {}).get("message_id")
    if state:
        do.set_fsm(chat_id, {**state, "message_id": message_id})


async def show_menu(do, chat_id, message_id=None, *, notice: str | None = None):
    """Vocabulary opens the paginated browse table directly (no separate View hub)."""
    await show_page(
        do, chat_id, 0, message_id,
        action="vocab", query="", exact_word="", table=True, notice=notice,
    )


async def finish(do, chat_id, body: str, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    target = state.get("return_action") or state.get("action", "vocab")
    message_id = message_id or state.get("message_id")
    if target in ("edit", "delete") or (target == "vocab" and state.get("from_table")):
        await show_page(
            do, chat_id, state.get("page", 0), message_id,
            action=target, query=state.get("query", ""),
            exact_word=state.get("exact_word", ""), notice=body, table=True,
        )
    else:
        await show_menu(do, chat_id, message_id, notice=body)


def _table_controls(action: str, page: int, max_page: int, has_filter: bool, has_rows: bool) -> list[list[dict]]:
    nav: list[tuple[str, str]] = []
    if page > 0:
        nav.append(("⬅️ Previous", f"vpg:{page - 1}"))
    if page < max_page:
        nav.append(("➡️ Next", f"vpg:{page + 1}"))
    nav.append(("🔎 Search", "vsrch"))
    rows = [nav]
    if action == "vocab":
        rows.append([("✏️ Edit", "vact:edit"), ("🗑 Delete", "vact:delete")])
    if has_filter:
        rows.append([("✖️ Clear filter", "vclr")])
    if action == "delete" and has_rows:
        rows.append([("🗑 Delete all", "del:all")])
    if action in ("edit", "delete"):
        rows.append([("◀️ Vocabulary", "menu:vocab"), ("🏠 Menu", "menu:home")])
    else:
        rows.append([("🏠 Menu", "menu:home")])
    return kb(rows)


async def show_page(
    do, chat_id, page: int = 0, message_id=None, *,
    action=None, query=None, notice=None, table=None, exact_word: str | None = None,
):
    """Render shared 1-query Markdown table while preserving CRUD action & filter."""
    prev = do.storage.kv.get(f"fsm:{chat_id}") or {}
    if action is None:
        action = prev.get("action", "vocab") if (message_id or prev) else "vocab"
    if query is None:
        query = prev.get("query", "") if (message_id or prev.get("action") == action) else ""
    if exact_word is None:
        exact_word = prev.get("exact_word", "") if (message_id or prev.get("action") == action) else ""
    table = True if table is None else table
    query = (query or "").strip()
    exact_word = (exact_word or "").strip()

    mid = message_id or (prev.get("message_id") if prev.get("action") == action or prev.get("return_action") == action else None)
    where, args = _filter_sql(query, exact_word)
    cte = (
        "WITH numbered AS ("
        " SELECT w.id, w.word, w.phonetic, w.meaning, c.due,"
        " ROW_NUMBER() OVER (ORDER BY w.id) AS stt"
        " FROM words w LEFT JOIN cards c ON c.word_id = w.id"
        "), filtered AS ("
        " SELECT *, COUNT(*) OVER () AS total FROM numbered" + where + ")"
    )
    page = max(0, page)
    rows = list(do.storage.sql.exec(
        cte + " SELECT * FROM filtered ORDER BY id LIMIT ? OFFSET ?",
        *args, PAGE_SIZE, page * PAGE_SIZE,
    ))
    if rows:
        total = rows[0].total
    elif page == 0:
        total = 0
    else:
        total = list(do.storage.sql.exec(
            "WITH numbered AS (SELECT w.id, w.word, w.meaning,"
            " ROW_NUMBER() OVER (ORDER BY w.id) AS stt FROM words w)"
            " SELECT COUNT(*) AS n FROM numbered" + where, *args,
        ))[0].n
        if total:
            page = (total - 1) // PAGE_SIZE
            rows = list(do.storage.sql.exec(
                cte + " SELECT * FROM filtered ORDER BY id LIMIT ? OFFSET ?",
                *args, PAGE_SIZE, page * PAGE_SIZE,
            ))
        else:
            page = 0

    max_page = max(0, (total - 1) // PAGE_SIZE)
    state = {
        "flow": f"{action}_select", "action": action, "query": query,
        "exact_word": exact_word, "page": page, "table": True,
        "from_table": True, "message_id": mid,
    }
    do.set_fsm(chat_id, state)
    controls = _table_controls(action, page, max_page, bool(query or exact_word), bool(total))

    if not total:
        body = texts.VOCAB_NOT_FOUND.format(escape(query or exact_word)) if (query or exact_word) else texts.VOCAB_EMPTY
        if notice:
            body = escape(notice) + "\n\n" + body
        await display(do, chat_id, body, controls, mid, rich=False)
        return

    now_iso = _now_iso()
    table_md = md_table(
        ["#", "Word", "IPA", "Meaning", "Due"],
        [
            [
                str(r.stt),
                r.word,
                f"/{r.phonetic.strip('/')}/" if r.phonetic else "—",
                r.meaning,
                _due_human(r.due, now_iso),
            ]
            for r in rows
        ],
        aligns=CELL_ALIGNS,
        limits=CELL_LIMITS,
    )
    title_tpl = {
        "vocab": texts.VOCAB_VIEW_TITLE,
        "edit": texts.EDIT_PICKED,
        "delete": texts.DELETE_PICKED,
    }[action]
    parts = [title_tpl.format(total=total)]
    if query:
        parts.append(f"🔎 Filter: **{md_cell(query, 60)}** ({total} results)")
    if notice:
        parts.append(_md_notice(notice))
    parts.append(table_md)
    body = "\n\n".join(parts) + texts.VOCAB_FOOTER.format(
        page=page + 1, pages=max_page + 1, verb=ACTION_VERBS[action],
    )
    await display(do, chat_id, body, controls, mid, rich=True)


async def select_action(do, chat_id, action: str, message_id=None):
    if action not in ("vocab", "edit", "delete"):
        return
    await show_page(do, chat_id, 0, message_id, action=action, query="", exact_word="", table=True)


async def clear_filter(do, chat_id, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    await show_page(
        do, chat_id, 0, message_id,
        action=state.get("action", "vocab"), query="", exact_word="", table=True,
    )


async def select_word(do, chat_id, selection: str, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    action = state.get("action", "vocab")
    query = (state.get("query") or "").strip()
    exact_word = (state.get("exact_word") or "").strip()
    page = state.get("page", 0)
    mid = message_id or state.get("message_id")
    selection = selection.strip()

    numeric_query = query.isascii() and query.isdigit() and len(query) <= 18
    active_where, active_args = _filter_sql("" if numeric_query else query, exact_word)
    extra = (" AND " + active_where[7:]) if active_where else ""

    base_cte = (
        "WITH numbered AS ("
        " SELECT w.id, w.word, w.meaning, ROW_NUMBER() OVER (ORDER BY w.id) AS stt"
        " FROM words w)"
    )
    if selection.isascii() and selection.isdigit() and len(selection) <= 18:
        rows = list(do.storage.sql.exec(
            base_cte + " SELECT id FROM numbered WHERE stt = ?" + extra,
            int(selection), *active_args,
        ))
    else:
        rows = list(do.storage.sql.exec(
            base_cte + " SELECT id FROM numbered WHERE word = ? COLLATE NOCASE"
            + extra + " ORDER BY id LIMIT 2",
            selection, *active_args,
        ))

    if not rows:
        return await show_page(
            do, chat_id, page, mid, action=action, query=query,
            exact_word=exact_word, table=True,
            notice="⚠️ No match. Enter a listed number or an exact word.",
        )
    if len(rows) > 1:
        return await show_page(
            do, chat_id, 0, mid, action=action, query=query,
            exact_word=selection, table=True,
            notice="⚠️ Multiple matches. Enter a listed number.",
        )

    word_id = rows[0].id
    if action == "edit":
        from handlers import edit
        return await edit.pick_word(do, chat_id, word_id, mid)
    if action == "delete":
        from handlers import delete
        return await delete.pick_word(do, chat_id, word_id, mid)
    return await pick_word(do, chat_id, word_id, mid)


async def start_search(do, chat_id, message_id=None):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    action = state.get("action", "vocab")
    mid = message_id or state.get("message_id")
    do.set_fsm(chat_id, {
        **state, "flow": f"{action}_search", "action": action, "message_id": mid,
    })
    back = f"vpg:{state.get('page', 0)}"
    await display(do, chat_id, texts.VOCAB_SEARCH_ASK, kb([
        [("◀️ Back", back), ("🏠 Menu", "menu:home")],
    ]), mid)


async def on_search_input(do, chat_id, text: str):
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    await show_page(
        do, chat_id, 0, message_id=state.get("message_id"),
        action=state.get("action", "vocab"), query=text, exact_word="", table=True,
    )


async def pick_word(do, chat_id, word_id: int, message_id=None):
    row = do.word_row(word_id)
    if row is None:
        return
    stt = list(do.storage.sql.exec(
        "WITH numbered AS (SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS stt FROM words)"
        " SELECT stt FROM numbered WHERE id = ?", word_id,
    ))[0].stt
    cards = list(do.storage.sql.exec("SELECT due FROM cards WHERE word_id = ?", word_id))
    state = do.storage.kv.get(f"fsm:{chat_id}") or {}
    page = state.get("page", 0)
    mid = message_id or state.get("message_id")
    do.set_fsm(chat_id, {
        **state, "flow": "vocab_select", "action": "vocab",
        "table": True, "from_table": True, "page": page, "message_id": mid,
    })
    phonetic = f"/{escape(row.phonetic.strip('/'))}/" if row.phonetic else "—"
    markup = kb([
        [("✏️ Edit", f"vedit:{word_id}"), ("🗑 Delete", f"vdel:{word_id}")],
        [("◀️ List", f"vpg:{page}"), ("🏠 Menu", "menu:home")],
    ])
    await display(do, chat_id, texts.VOCAB_DETAIL.format(
        stt=stt, word=escape(row.word), pos=escape(row.pos or "—"), phonetic=phonetic,
        define_en=escape(row.define_en or "—"), meaning=escape(row.meaning or "—"),
        example=escape(row.example or "—"), note=escape(row.note or "—"),
        due=_due_human(cards[0].due if cards else None, _now_iso()),
    ), markup, mid)
