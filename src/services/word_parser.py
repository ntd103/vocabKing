"""Parser for the add-word pipe format:
`word|phonetic|defineEN|meaning|example|note`.

Pure functions — unit-testable. Handles Telegram's automatic line wrapping:
a line that does NOT contain `|` is a continuation of the previous line and is
joined back with a space.

Fields trimmed of leading/trailing whitespace; empty fields become None.
Missing trailing fields are None. Example: `hello||greeting|xin chào|hi||` ->
word=hello, phonetic=None, defineEN=greeting, meaning=xin chào, example=hi,
note=None.
"""

import re
from html import escape

FIELD_COUNT = 6  # word|phonetic|defineEN|meaning|example|note


def join_wrapped_lines(text: str) -> list[str]:
    """Split input into logical records.

    Rule (kept simple & predictable — documented in /help):
    - a line containing `|` starts a new record
    - a line WITHOUT `|` is a Telegram wrap continuation of the previous record
    (so wrapped content itself must not contain `|`).
    """
    records: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "|" in line or not records:
            records.append(line)
        else:
            records[-1] += " " + line
    return records


def parse_line(line: str) -> dict | None:
    """Parse word/phonetic/define_en/meaning/example/note.
    Missing/empty fields (including delimiter-only notes) become None.
    Returns None if there is no word."""
    parts = [p.strip() for p in line.split("|", FIELD_COUNT - 1)]
    parts += [None] * (FIELD_COUNT - len(parts))
    word = parts[0]
    if not word:
        return None
    return {
        "word": word,
        "phonetic": parts[1] or None,
        "define_en": parts[2] or None,
        "meaning": parts[3] or None,
        "example": parts[4] or None,
        "note": parts[5] if parts[5] and parts[5].replace("|", "").strip() else None,
    }


def parse_add_input(text: str) -> list[dict]:
    """Parse the whole /add payload into a list of word dicts (deduped)."""
    out: list[dict] = []
    seen: set[str] = set()
    for rec in join_wrapped_lines(text):
        entry = parse_line(rec)
        if entry is None or not (entry["define_en"] and entry["meaning"]):
            return []  # Never silently accept only part of a pasted batch.
        key = re.sub(r"\s+", " ", entry["word"]).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def format_preview(entries: list[dict]) -> str:
    """Human-readable preview of parsed entries shown before confirmation."""
    lines = [f"📋 Preview ({len(entries)})", ""]
    for e in entries:
        lines.append(" • 📖 " + escape(e["word"]))
        if e["phonetic"]:
            lines.append(f"   🔊 /{escape(e['phonetic'].strip('/'))}/")
        lines.append("   🇬🇧 " + escape(e["define_en"] or "—"))
        lines.append("   🇻🇳 " + escape(e["meaning"] or "—"))
        if e["example"]:
            lines.append(f"   📝 {escape(e['example'])}")
        if e["note"]:
            lines.append(f"   ℹ️ {escape(e['note'])}")
    return "\n".join(lines)


__all__ = ["join_wrapped_lines", "parse_line", "parse_add_input", "format_preview"]
