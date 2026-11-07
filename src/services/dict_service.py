"""Dictionary lookup via freedictionaryapi.com (free, no key).

Returns a normalized dict or None on miss. Network errors are swallowed into
None so the caller can show a friendly "not found" instead of a crash.
"""

from workers import fetch

API = "https://freedictionaryapi.com/api/v1/entries/en/{word}"


async def lookup(word: str) -> dict | None:
    """Fetch word info. Returns {word, phonetic, pos, definition, example}."""
    try:
        res = await fetch(API.format(word=word))
        if res.status != 200:
            return None
        data = await res.json()
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    # Normalize across the API's schema.
    phonetic = ""
    phonetics = data.get("phonetics") or []
    for p in phonetics:
        if isinstance(p, dict) and p.get("text"):
            phonetic = p["text"]
            break

    pos = ""
    definition = ""
    example = ""
    entries = data.get("entries") or data.get("meanings") or []
    for e in entries:
        if not isinstance(e, dict):
            continue
        pos = pos or e.get("partOfSpeech", "")
        senses = e.get("senses") or []
        for s in senses:
            if isinstance(s, dict):
                definition = definition or s.get("definition", "") or s.get("gloss", "")
                exs = s.get("examples") or []
                if exs and not example:
                    example = exs[0] if isinstance(exs[0], str) else exs[0].get("text", "")
        if definition:
            break

    if not definition:
        return None
    return {
        "word": word,
        "phonetic": phonetic,
        "pos": pos,
        "definition": definition,
        "example": example,
    }
