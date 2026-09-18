"""Parser for the add-word input format: `word|phonetic|meaning|example|note`.

Pure functions — unit-testable. Handles Telegram's automatic line wrapping:
a line that does NOT contain `|` is a continuation of the previous line and is
joined back with a space.
"""

import re

FIELD_COUNT = 5  # word|phonetic|meaning|example|note


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
    """Parse one record into a dict with keys word/phonetic/meaning/example/note.
    Missing/empty fields become None. Returns None if there is no word."""
    parts = [p.strip() for p in line.split("|", FIELD_COUNT - 1)]
    parts += [None] * (FIELD_COUNT - len(parts))
    word = parts[0]
    if not word:
        return None
    return {
        "word": word,
        "phonetic": parts[1] or None,
        "meaning": parts[2] or None,
        "example": parts[3] or None,
        "note": parts[4] or None,
    }


def parse_add_input(text: str) -> list[dict]:
    """Parse the whole /add payload into a list of word dicts (deduped)."""
    out: list[dict] = []
    seen: set[str] = set()
    for rec in join_wrapped_lines(text):
        entry = parse_line(rec)
        if entry is None:
            continue
        key = re.sub(r"\s+", " ", entry["word"]).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def format_preview(entries: list[dict]) -> str:
    """Human-readable preview of parsed entries shown before confirmation."""
    lines = [f"📋 Xem trước {len(entries)} từ:", ""]
    for e in entries:
        parts = [e["word"]]
        if e["phonetic"]:
            parts.append(f"/{e['phonetic'].strip('/')}/")
        parts.append(e["meaning"] or "(chưa có nghĩa)")
        lines.append(" • " + " — ".join(parts))
        if e["example"]:
            lines.append(f"   📝 {e['example']}")
        if e["note"]:
            lines.append(f"   ℹ️ {e['note']}")
    lines += ["", "Thêm những từ này?"]
    return "\n".join(lines)


__all__ = ["join_wrapped_lines", "parse_line", "parse_add_input", "format_preview"]
